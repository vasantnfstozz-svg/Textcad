// viewport.js — the 3D view: scene, camera, model loading (face-tagged mesh
// from /api/model), view buttons, and face/edge picking with the info panel.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { bus } from './bus.js';
import { S } from './state.js';
import { setBusy, clearBusy } from './api.js';
import { initSketch3D, sketch3DActive } from './sketch3d.js';
import { SETTINGS } from './settings.js';
import { gridStepFor, planeHalfFor, buildGridLines, patchFor,
         viewFootprintOn } from './grid3d.js';

let scene, camera, renderer, controls;
let groundGrid = null;           // the XY GridHelper (hidden while sketching)
let mesh = null;                 // the RESULT body's mesh (bodyObjs entry too)
const edgeLines = [];            // crisp OCCT topology edges of ALL bodies
const sketchObjs = [];           // floating 2D sketch profiles (Fusion-style)
/* Every unconsumed solid, each a REAL pickable body (Fusion's Bodies folder):
   [{ id, result, mesh, data:{positions,indices,faceId,faces} }].
   Non-result bodies used to be translucent grey ghosts, so extruding a second
   sketch turned the first body into a ghost and read as "it went blank". */
const bodyObjs = [];
let hlMesh = null;               // orange overlay for a tree-selected feature
let pickHl = null;               // orange overlay for a picked face/edge
let MODEL = null;                // /api/model payload (faceId, faces, edges)
let fitRadius = 100;
const fitCenter = new THREE.Vector3();
// Fusion parity rule 2 (select-then-command): clicking a face SELECTS it, with
// no mode to enable first — Fusion has no "Select mode" button. It used to
// default off, so on a freshly loaded design clicking a surface did nothing at
// all, which is indistinguishable from broken (and made face->feature lookup
// undiscoverable). The toggle stays, for turning picking OFF.
let pickMode = true;
let placeCb = null;              // when set, the next viewport click places a shape
let planePickCb = null;          // when set, click an origin plane / face to sketch on
const originPlanes = [];         // the 3 clickable origin planes during plane-pick
let exArrow = null;              // the draggable Extrude manipulator arrow
let exArrow2 = null;             // a SECOND arrow (Rectangular Pattern's direction 2), same mechanics
let dragArrow = null;            // whichever arrow the pointer is dragging
const raycaster = new THREE.Raycaster();
const GROUND = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);   // Z=0 workplane

/* The world is Z-UP: build123d/OCCT models are built in a Z-up frame, the
   ground workplane is XY (GROUND, z=0) and the ground grid is rotated into XY.
   The camera must share that convention or the horizon rolls while orbiting
   and nothing lines up with the origin planes. WORLD_UP is the default orbit
   axis; sketch mode overrides it with its plane's up via setOrbitUp.

   OrbitControls freezes its ORBIT AXIS at construction time
   (`setFromUnitVectors(object.up, (0,1,0))` lives in update()'s closure), so
   `camera.up = …` afterwards is ignored. Looking straight down an axis that is
   a pole of that frozen frame makes orbiting dead (the XZ sketch view sat at
   phi = π exactly). Rebuilding the controls with the wanted up is the only
   reliable way — cheap, and it preserves pose. up=null restores WORLD_UP. */
const WORLD_UP = new THREE.Vector3(0, 0, 1);

/* What the LEFT button does when Shift is NOT held: orbit in the design tab,
   nothing in sketch mode (it draws there). Holding Shift turns LEFT into PAN
   in both — kept alongside right-drag pan as a fallback gesture.
   OrbitControls reads mouseButtons at pointerdown, so flipping it on the
   Shift keydown is enough. */
let leftBase = THREE.MOUSE.ROTATE;
let shiftPan = false;

function applyLeftButton() {
  if (controls) controls.mouseButtons.LEFT = shiftPan ? THREE.MOUSE.PAN : leftBase;
}

/* sketch mode calls this with null so LEFT is free for drawing */
export function setLeftButton(action) {
  leftBase = action;
  applyLeftButton();
}

export function shiftPanActive() { return shiftPan; }

/* How close the camera may get. Scaled to the model so a keychain and a
   200 mm panel both zoom about as far in proportional terms, and kept above the
   near clip plane (fitRadius/100) — inside that, faces get clipped away and you
   see through the part, which looks identical to the bug this prevents. */
function zoomFloor() {
  const r = fitRadius || 100;
  return Math.max(r / 40, (r / 100) * 3);
}

/* One physical notch, whatever the hardware says. deltaMode 1 is LINES
   (Firefox sends ~3 per notch) and 2 is PAGES; deltaMode 0 is pixels, where a
   notch is ~100 in Chrome but free-spinning and high-resolution wheels send
   far more. Clamped so a fast flick cannot rocket across the model. */
const ZOOM_PER_NOTCH = 0.95;          // matches three's default feel at DPR 1

function wheelNotches(e) {
  const per = e.deltaMode === 1 ? 3          // lines
            : e.deltaMode === 2 ? 1          // pages
            : 100;                           // pixels
  // CAP AT ONE. A mouse click is one notch however big a number the device
  // puts on it — measured, plausible mice report 100, 240 and 400 for the same
  // physical click, which without this cap zoomed x0.95, x0.88 and x0.86. Fast
  // spinning still zooms fast because it fires more EVENTS. The low floor keeps
  // a trackpad's fine-grained stream smooth instead of stair-stepping.
  const n = Math.abs(e.deltaY) / per;
  return Math.min(Math.max(n, 0.05), 1);
}

function onWheelZoom(e) {
  if (!controls || !controls.enabled) return;
  e.preventDefault();
  const offset = camera.position.clone().sub(controls.target);
  const factor = Math.pow(ZOOM_PER_NOTCH,
                          wheelNotches(e) * (e.deltaY < 0 ? 1 : -1));
  const r = Math.min(Math.max(offset.length() * factor,
                              controls.minDistance), controls.maxDistance);
  camera.position.copy(controls.target).add(offset.setLength(r));
  controls.update();
  bus.emit('view-changed');
}

function buildControls(up) {
  const pos = camera.position.clone();
  const tgt = controls ? controls.target.clone() : new THREE.Vector3();
  if (controls) controls.dispose();
  camera.up.copy(up || WORLD_UP);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.12;
  /* ONE navigation mapping for the whole app. The tabs used to disagree —
     design was OrbitControls' stock LEFT orbit / MIDDLE dolly / RIGHT pan
     while sketch mode had LEFT draw / MIDDLE pan / RIGHT orbit — so the same
     drag did different things depending on where you were, and left-dragging
     in a sketch (which draws) read as "rotating is broken".
     RIGHT-drag PANS, MIDDLE-drag orbits and the wheel zooms EVERYWHERE
     (user mandate 2026-08-31: "for right click I can move the body front and
     back, up and down — right click I don't wanna rotate", in the sketch tab
     and design tab both); sketch mode only takes LEFT away (it draws). The
     design tab deliberately KEEPS left-drag orbit (user's call) since nothing
     else needs left there. */
  leftBase = THREE.MOUSE.ROTATE;        // design default; sketch mode frees it
  controls.mouseButtons = { LEFT: leftBase,
                            MIDDLE: THREE.MOUSE.ROTATE,
                            RIGHT: THREE.MOUSE.PAN };
  applyLeftButton();                    // a rebuild must not drop Shift-pan
  // never dolly past the far clip plane — beyond it the whole scene (model,
  // grids, everything) is clipped to a black void that reads as a crash
  controls.maxDistance = camera.far * 0.85;
  controls.minDistance = zoomFloor();
  /* WE own the wheel, not OrbitControls. three r160 computes its zoom step as

         Math.pow(0.95, zoomSpeed * Math.abs(delta) / (100 * (devicePixelRatio|0)))

     which has two faults. It scales by the RAW deltaY and ignores deltaMode, so
     one notch means something different on every mouse and browser; measured
     across plausible devices, one click ranged from x0.9985 to x0.8145 — an 8x
     spread in how far a click travels. And `devicePixelRatio | 0` TRUNCATES: at
     any DPR below 1 — a browser zoomed out below 100%, which is ordinary — it
     becomes 0 and the expression divides by zero. Reproduced at DPR 0.8: one
     notch in went 192.44 -> 2.12 and one notch out 2.12 -> 6018.43, i.e.
     straight to the clamps ("it goes so far zoom and far back").

     That divide-by-zero is also the original report. With no floor, dollyIn(0)
     put the camera exactly ON the target — inside the solid — in a single
     click, which is the full-screen grey wash, not the gradual creep it looked
     like.

     So the wheel is normalised here instead: deltaMode-aware, capped, and a
     fixed ratio per notch regardless of device, browser or display scaling. */
  controls.enableZoom = false;
  renderer.domElement.addEventListener('wheel', onWheelZoom, { passive: false });
  camera.position.copy(pos);
  controls.target.copy(tgt);
  controls.addEventListener('change', () => bus.emit('view-changed'));
  controls.update();
  return controls;
}

/* used by sketch mode: orbit around the SKETCH PLANE's up, so the view can be
   rotated freely from a flat-on sketch view (no pole at the start pose) */
export function setOrbitUp(upArr) {
  return buildControls(upArr ? new THREE.Vector3(...upArr).normalize() : null);
}
export function getControls() { return controls; }

/* where the model actually is, so a tool can frame on the PART instead of the
   world origin (entering a sketch used to always look at 0,0) */
export function modelExtent() {
  return { center: fitCenter.toArray(), radius: fitRadius,
           hasModel: bodyObjs.length > 0 };
}

export function initViewport() {
  const pane = document.getElementById('viewer');
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f1115);
  camera = new THREE.PerspectiveCamera(50, 1, 0.1, 8000);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  pane.appendChild(renderer.domElement);
  buildControls(null);

  // Three-light rig tuned for the grey body: a cool sky fill so the top faces
  // lift off the dark background, a strong white key for the machined
  // highlight, a blue rim for the edge separation that reads as "cool", and a
  // soft opposite fill so faces turned away from the key are shaded rather
  // than black.
  scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x2a2f3a, 1.0));
  const key = new THREE.DirectionalLight(0xffffff, 1.35);
  key.position.set(1, -1, 2); scene.add(key);
  const rim = new THREE.DirectionalLight(0x9ec5ff, 0.55);
  rim.position.set(-2, 2, -1); scene.add(rim);
  const fill = new THREE.DirectionalLight(0xffffff, 0.32);
  fill.position.set(-1, 1.5, 0.6); scene.add(fill);
  // the ground workplane is ADAPTIVE like the sketch grid (grid3d.js): cells
  // subdivide with zoom down to gridMm/10, and the plate is a finite,
  // model-sized square — a persistent Group whose children are rebuilt, so
  // sketch mode's visible-toggle always points at the live object
  groundGrid = new THREE.Group();
  scene.add(groundGrid);
  bus.on('view-changed', updateGroundGrid);
  updateGroundGrid();

  const resize = () => {
    camera.aspect = pane.clientWidth / pane.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(pane.clientWidth, pane.clientHeight);
    updateGroundGrid();       // first layout builds the boot grid; the canvas
  };                          // has no size before the observer fires
  new ResizeObserver(resize).observe(pane);
  // a real starting pose: the camera used to boot AT the origin (inside the
  // ground plane — nothing visible until the first fit), so an empty doc
  // showed a black void with no workplane at all
  setView('iso');
  // in-viewport sketch layer (Fusion-style sketch mode) — needs the internals.
  // controls are REBUILT when the orbit axis changes, so pass a getter.
  initSketch3D({ scene, camera, dom: renderer.domElement, groundGrid,
                 getControls, setOrbitUp, setLeftButton,
                 getFitRadius: () => fitRadius,
                 refreshGroundGrid: updateGroundGrid });
  // e2e/debug handle (read-only use): camera, controls and the fit volume the
  // origin-plane quads are sized from, plus body/pick introspection so tests
  // can assert on what is actually IN the scene (a body drawn as a translucent
  // ghost passes every DOM check while looking broken to the user)
  window.__vp = {
    camera, getControls,
    getFit: () => ({ r: fitRadius, c: fitCenter.toArray(),
                     minDistance: controls ? controls.minDistance : null,
                     zoomToCursor: controls ? !!controls.zoomToCursor : null,
                     ownWheel: controls ? !controls.enableZoom : null,
                     target: controls ? controls.target.toArray() : null }),
    bodyCount: () => bodyObjs.length,
    bodyInfo: () => bodyObjs.map(b => ({
      id: b.id, result: b.result, faces: (b.data.faces || []).length,
      edges: (b.data.edges || []).length,
      opacity: b.mesh.material.opacity,
      transparent: b.mesh.material.transparent,
      color: '#' + b.mesh.material.color.getHexString() })),
    bodyObjsRaw: () => bodyObjs,
    /* the origin-plane quads: which plane, where they sit, how big — a quad
       must lie IN the plane it names (normal component 0) */
    originPlaneInfo: () => originPlanes.filter(o => o.userData.plane).map(o => ({
      plane: o.userData.plane, position: o.position.toArray(),
      size: o.geometry.parameters.width })),
    /* the adaptive ground grid actually in the scene (step/half/clip) */
    groundGridInfo: () => groundState ? { step: groundState.step,
      half: groundState.half, clip: { ...groundState.clip } } : null,
    /* which extrude gizmos are live — a face-sketch extrude must have ALL
       three (the ghost/ring were silently missing there once) */
    gizmos: () => ({ arrow: !!exArrow, arrow2: !!exArrow2, ghost: !!exGhost, ring: !!taperRing,
                     axis: !!axisLine, lathe: !!rvGhost, glow: edgeGlow.length,
                     edgePick: !!edgePickCb, hole: !!holeMarker, plane: !!planeQuad,
                     facePick: !!profilePickCb }),
    /* the mirror plane as drawn: where it sits and which way it faces */
    planeQuadInfo: () => planeQuad ? { origin: planeQuad.frame.origin,
                                       normal: planeQuad.frame.z_dir } : null,
    /* the hole marker as drawn: its world centre and radius */
    holeMarkerInfo: () => holeMarker ? {
      centre: new THREE.Vector3().setFromMatrixPosition(holeMarker.line.matrix).toArray(),
      radius: holeMarker.radius } : null,
    /* screen position of the middle point of a body edge's drawn line — so a
       test clicks where a USER would click on that edge */
    edgeScreen: (bodyId, i) => {
      const b = bodyObjs.find(x => x.id === bodyId);
      const e = b && b.data.edges[i];
      if (!e) return null;
      // a straight edge is drawn with TWO points: its middle is between them,
      // never an end (a corner vertex where three edges meet)
      const P = e.points, n = P.length;
      const p = n % 2 === 0
        ? [0, 1, 2].map(k => (P[n / 2 - 1][k] + P[n / 2][k]) / 2)
        : P[Math.floor(n / 2)];
      return window.__vp.worldToScreen(p);
    },
    edgeCount: (bodyId) => {
      const b = bodyObjs.find(x => x.id === bodyId);
      return b ? b.data.edges.length : 0;
    },
    /* the revolve ghost as drawn: its angle and the world centre of its
       swept volume — a positive angle must land on the kernel's side */
    revolveGhostInfo: () => {
      if (!rvGhost || !rvGhost.parts.length) return null;
      const box = new THREE.Box3();
      for (const P of rvGhost.parts) box.expandByObject(P.mesh);
      return { visible: rvGhost.parts[0].mesh.visible, angle: rvGhost.angle, back: rvGhost.back,
               centre: box.getCenter(new THREE.Vector3()).toArray() };
    },
    axisLineInfo: () => axisLine ? { from: axisLine.geometry.attributes.position.array.slice(0, 3),
                                     to: axisLine.geometry.attributes.position.array.slice(3, 6) } : null,
    ghostLoopTops,
    /* the extrude gizmos' DIRECTIONS: the arrow's axis and the way the ghost
       box actually grows (its matrix z column, which carries the signed
       depth). They MUST point the same way — three disagreeing direction
       sources is the 2026-09-01 "the ghost box goes to another side" bug. */
    extrudeDirs: () => ({
      arrow: exArrow ? { origin: exArrow.O.toArray(), axis: exArrow.N.toArray(),
                         amount: exArrow.amount, points: arrowDir().toArray() }
                     : null,
      ghost: exGhost ? { visible: exGhost.mesh.visible,
                         grows: [exGhost.mesh.matrix.elements[8],
                                 exGhost.mesh.matrix.elements[9],
                                 exGhost.mesh.matrix.elements[10]] }
                     : null }),
    /* how many of each thing is actually in the scene — catches duplicate
       objects piling up from overlapping loads */
    sceneCounts: () => ({ bodies: bodyObjs.length, edges: edgeLines.length,
                          sketchObjs: sketchObjs.length,
                          sceneChildren: scene.children.length }),
    /* raycast at a WORLD point (e.g. a face centre) as if the user clicked
       there, and report what got picked — deterministic, no screen maths */
    /* deterministic for tests: set the mode instead of toggling it, so a
       test never depends on what the default happens to be */
    setPickMode: (on) => {
      pickMode = !!on;
      const b = document.getElementById('vSelect');
      if (b) b.classList.toggle('on', pickMode);
      if (!pickMode) clearPick();
      return pickMode;
    },
    getPickMode: () => pickMode,
    /* screen position of a world point — lets a test click where a USER
       would click, instead of calling the raycast directly (which hides
       whether the face is even visible from here) */
    worldToScreen: (world) => {
      const v = new THREE.Vector3(...world);
      if (v.clone().project(camera).z > 1) return null;   // behind the camera
      const s = toScreen(v);
      const r = renderer.domElement.getBoundingClientRect();
      return { x: s.x, y: s.y, cx: s.x - r.left, cy: s.y - r.top };
    },
    pickAtWorld: (world) => {
      const rect = renderer.domElement.getBoundingClientRect();
      const v = new THREE.Vector3(...world).project(camera);
      pickAt({ clientX: rect.left + (v.x + 1) / 2 * rect.width,
               clientY: rect.top + (1 - (v.y + 1) / 2) * rect.height });
      return S.pickedFace || S.pickedCurved || null;
    },
  };

  (function animate() { requestAnimationFrame(animate);
    controls.update(); paintDimLabel(); paintSelBadges();
    renderer.render(scene, camera); })();

  initDimDrag();               // the draggable Measure dimension label
  document.getElementById('vFit').onclick = () => setView('iso');
  document.getElementById('vTop').onclick = () => setView('top');
  document.getElementById('vFront').onclick = () => setView('front');
  document.getElementById('vIso').onclick = () => setView('iso');
  const paintPickMode = () => {
    const b = document.getElementById('vSelect');
    if (b) b.classList.toggle('on', pickMode);
    renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  };
  document.getElementById('vSelect').onclick = () => {
    pickMode = !pickMode;
    paintPickMode();
    if (!pickMode) clearPick();
  };
  paintPickMode();               // picking is ON by default — show it

  let downXY = null;
  renderer.domElement.addEventListener('pointerdown',
    e => downXY = [e.clientX, e.clientY]);
  renderer.domElement.addEventListener('pointerup', e => {
    if (!downXY) return;
    const moved = Math.hypot(e.clientX - downXY[0], e.clientY - downXY[1]);
    downXY = null;
    if (e.button !== 0) return;            // right/middle navigate, never pick
    if (sketch3DActive()) return;          // sketch mode owns viewport clicks
    if (moved > 5) return;                 // that was an orbit-drag
    if (edgePickCb) { edgePickAt(e); return; }
    if (profilePickCb) { profilePickAt(e); return; }
    if (planePickCb) { planePickAt(e); return; }
    if (placeCb) { placeGround(e); return; }
    if (pickMode) pickAt(e);
  });
  renderer.domElement.addEventListener('pointermove', e => {
    if (planePickCb || (profilePickCb && profilePickOpts.planes)) planePickHover(e);
    else if (edgePickCb) edgePickHover(e);
  });
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape' && placeCb) cancelPlacement();
    if (e.key === 'Escape' && planePickCb) endPlanePick();
    if (e.key === 'Escape' && profilePickCb) cancelProfilePick();
    if (e.key === 'Shift' && !shiftPan) { shiftPan = true; applyLeftButton(); }
  });
  const dropShift = () => {
    if (shiftPan) { shiftPan = false; applyLeftButton(); }
  };
  window.addEventListener('keyup', e => { if (e.key === 'Shift') dropShift(); });
  window.addEventListener('blur', dropShift);   // alt-tab must not stick in pan
  // any document change (tab switch, sample opened, external design) while a
  // plane-pick is pending would leave the 3 plane quads stranded — cancel it
  bus.on('doc-updated', doc => {
    if (planePickCb) endPlanePick();
    // a command-then-select pick is stale once the document changed under it;
    // a session's own re-pick (sticky) lives as long as the session — but only
    // through the session's OWN rebuilds, which run inside holdViewport. An
    // undo, another window or a design arriving over MCP is not this session's
    // doing and may have removed the very feature the pick would move.
    if (profilePickCb && !(profilePickOpts.sticky && holds)) cancelProfilePick();
    follow(doc);                  // R3: the scene follows the document
  });

  // Extrude gizmo drags (arrow + taper ring) — capture phase so we grab them
  // BEFORE OrbitControls, then disable orbit for the drag. Move/up on window
  // so the drag survives the pointer leaving the canvas.
  renderer.domElement.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;            // a right/middle drag must still
                                           // navigate, even starting ON a gizmo
    for (const a of [exArrow, exArrow2])
      if (a && !a.dragging && arrowGrab(e, a)) { e.stopPropagation(); return; }
    if (taperRing && !taperRing.dragging && taperGrab(e)) e.stopPropagation();
  }, true);
  window.addEventListener('pointermove', e => {
    if (dragArrow) arrowDrag(e);
    else if (taperRing && taperRing.dragging) taperDrag(e);
  });
  window.addEventListener('pointerup', e => {
    if (dragArrow) arrowRelease(e);
    else if (taperRing && taperRing.dragging) taperRelease(e);
  });
}

/* ---------------- click-to-place on the Z=0 ground plane ---------------- */

export function beginPlacement(label, onPlace) {
  placeCb = onPlace;
  renderer.domElement.style.cursor = 'crosshair';
  const h = document.getElementById('placeHint');
  h.textContent = `Click a point on the ground to place the ${label} · Esc to cancel`;
  h.style.display = 'block';
}

export function cancelPlacement() {
  placeCb = null;
  renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  document.getElementById('placeHint').style.display = 'none';
}

function placeGround(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hit = new THREE.Vector3();
  const cb = placeCb;
  cancelPlacement();
  if (raycaster.ray.intersectPlane(GROUND, hit)) {
    cb(Math.round(hit.x * 100) / 100, Math.round(hit.y * 100) / 100);
  } else {
    cb(0, 0);                              // ray parallel to ground — fall back
  }
}

/* ---------------- the adaptive ground grid (design tab) ----------------
   Same two rules as the sketch grid (grid3d.js): cell size follows the
   camera (1-2-5 subdivision, floored at gridMm/10), plate size follows the
   MODEL — a finite square that jumps to the next ladder size when the model
   outgrows it, never sized by how far the camera happens to look. */

let groundState = null;      // {step, half, clip} of the built ground grid

function groundFootprint() {
  const rect = renderer.domElement.getBoundingClientRect();
  const toPx = w => {
    const v = w.clone().project(camera);
    return v.z > 1 ? null
      : { x: (v.x + 1) / 2 * rect.width, y: (1 - (v.y + 1) / 2) * rect.height };
  };
  return viewFootprintOn({
    camera, dom: renderer.domElement, plane: GROUND,
    hitToLocal: w => ({ x: w.x, y: w.y }),           // ground IS world XY
    pxPerMmAt: p => {
      const a = toPx(new THREE.Vector3(p.x, p.y, 0));
      const b = toPx(new THREE.Vector3(p.x + 1, p.y, 0));
      if (!a || !b) return null;
      return Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1e-4);
    },
  });
}

let lastGroundFp = null;     // reused when the view is momentarily
                             // unprojectable (edge-on, far-clipped)
function updateGroundGrid() {
  if (!groundGrid || !groundGrid.visible) return;    // hidden while sketching
  const fp = groundFootprint() || lastGroundFp;
  if (!fp) return;
  lastGroundFp = fp;
  const pxPerMm = fp.pxPerMm;
  // the plate covers the MODEL (origin-centred), not the camera's reach
  const need = Math.max(Math.abs(fitCenter.x), Math.abs(fitCenter.y))
             + fitRadius * 1.3;
  const half = planeHalfFor(Math.max(need, 220));
  const step = gridStepFor(pxPerMm, Math.max(SETTINGS.gridMm / 10, 0.01),
                           half / 2);
  const bounds = { minX: -half, maxX: half, minY: -half, maxY: half };
  const patch = patchFor(fp, step);
  const clip = {
    minX: Math.max(bounds.minX, patch.minX),
    maxX: Math.min(bounds.maxX, patch.maxX),
    minY: Math.max(bounds.minY, patch.minY),
    maxY: Math.min(bounds.maxY, patch.maxY),
  };
  if (groundState && groundState.step === step && groundState.half === half
      && groundState.clip.minX === clip.minX && groundState.clip.maxX === clip.maxX
      && groundState.clip.minY === clip.minY && groundState.clip.maxY === clip.maxY)
    return;
  for (const c of [...groundGrid.children]) {
    groundGrid.remove(c);
    c.traverse(o => { if (o.geometry) o.geometry.dispose();
                      if (o.material) o.material.dispose(); });
  }
  groundGrid.add(buildGridLines({ step, bounds, patch,
    colors: { minor: 0x1b1f28, major: 0x2b303c, axes: 0x39404e } }));
  groundState = { step, half, clip };
}

/* ------- pick a PROFILE or planar face for a tool (Fusion: Extrude) -------
   Command-then-select: the tool is pressed with nothing selected, so the
   NEXT viewport click chooses its input — a sketch profile or a flat face.
   The user picks; nothing is auto-selected for them. */

let profilePickCb = null;
// whose pick, may a face do, may a profile do (Hole: faces only), a hint of its
// own, and `sticky`: a pick that belongs to an OPEN tool session (Hole's move-
// by-clicking) — a document change does not cancel it, the session's end does
let profilePickOpts = { name: 'Extrude', faces: true, profiles: true, hint: null, sticky: false };

/* WHAT this pick takes, in words — one place, so the hint, the chat line and
   every refusal sentence say the same thing (a face-only tool must never be
   told to click "a sketch profile"). */
export const pickWhat = (opts = {}) =>
  [opts.profiles !== false && 'a sketch profile', opts.faces !== false && 'a flat face',
   opts.planes && 'an origin plane']
    .filter(Boolean).join(' or ') || 'nothing';

export function beginProfilePick(onPick, opts = {}) {
  profilePickCb = onPick;
  profilePickOpts = { name: 'Extrude', faces: true, profiles: true, hint: null, sticky: false,
                      anyFace: false, planes: false, ...opts };
  renderer.domElement.style.cursor = 'crosshair';
  const h = document.getElementById('placeHint');
  h.textContent = profilePickOpts.hint
    || `Select ${pickWhat(profilePickOpts)} to ${profilePickOpts.name.toLowerCase()} ` +
       '· Esc to cancel';
  h.style.display = 'block';
  // a tool whose pick may be an ORIGIN PLANE (Mirror's plane) shows the three
  // glass quads the sketch tool shows; a click on one answers ('plane', 'YZ')
  if (profilePickOpts.planes) buildOriginPlanes();
}

/* is a pick waiting for a click? A tool with a session-long pick asks before
   arming, so it re-arms after anything that cancelled it (an external document
   change) instead of trusting a flag of its own. */
export const profilePickArmed = () => !!profilePickCb;

export function cancelProfilePick() {
  if (!profilePickCb) return;
  profilePickCb = null;
  renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  document.getElementById('placeHint').style.display = 'none';
  if (profilePickOpts.planes) clearOriginPlanes();
}

/* A one-shot pick is spent by the click that answers it; a STICKY one belongs
   to an open tool session (Hole's move-by-clicking) and stays armed until the
   session ends — so the hint stays up and a second click during the rebuild
   still reaches the tool instead of falling through to the ordinary picker. */
function answerPick(kind, data) {
  const cb = profilePickCb;
  if (!profilePickOpts.sticky) cancelProfilePick();
  cb(kind, data);
}

function profilePickAt(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const sHit = raycaster.intersectObjects(sketchMeshes(), false)[0];
  const fHit = raycaster.intersectObjects(bodyMeshes(), false)[0];
  // coplanar tie: the profile drawn ON the face wins, same rule as pickAt —
  // unless this tool takes faces only, when the face under it is the pick
  if (sHit && profilePickOpts.profiles && (!fHit || sHit.distance <= fHit.distance + 0.5)) {
    answerPick('profile', sHit.object.userData.sketchId); return;
  }
  if (sHit && !profilePickOpts.profiles && !fHit) {   // a sketch, for a face-only tool
    bus.emit('msg', 'bot', `⚠ ${profilePickOpts.name} starts on a flat face — ` +
      'click a face, not a sketch. Keep picking, or Esc.');
    return;
  }
  if (fHit) {
    const entry = bodyObjs.find(b => b.mesh === fHit.object);
    const fid = entry && entry.data.faceId[fHit.face.a];
    const info = entry && entry.data.faces.find(f => f.id === fid);
    const flat = info && (info.planar ?? (info.type === 'PLANE'));
    if (info && !profilePickOpts.faces) {          // this tool takes profiles only
      bus.emit('msg', 'bot', `⚠ ${profilePickOpts.name} works on a sketch profile — ` +
        'click a sketch, not a face. Keep picking, or Esc.');
      return;
    }
    if (info && (flat || profilePickOpts.anyFace) && info.center) {
      // the face, WHICH body it is on, and WHERE it was clicked (Hole's centre);
      // a tool that takes ANY face (Pattern: a bore's wall names the hole) is
      // given curved ones too — the server says what the face means
      answerPick('face', { ...info, body: info.body || entry.id,
                           point: [fHit.point.x, fHit.point.y, fHit.point.z] });
      return;
    }
    if (info) {
      bus.emit('msg', 'bot', `⚠ That face is ${info.type} (curved) — ${profilePickOpts.name} ` +
        `needs ${pickWhat(profilePickOpts)}. Keep picking, or Esc.`);
      return;
    }
  }
  if (profilePickOpts.planes) {                    // an origin plane, outside the body's silhouette
    const quads = originPlanes.filter(o => o.userData.plane);
    const pHit = raycaster.intersectObjects(quads, false)[0];
    if (pHit) { answerPick('plane', pHit.object.userData.plane); return; }
  }
  // clicked empty space — keep waiting (don't cancel)
}

/* ---------------- pick EDGES for a tool (Fillet / Chamfer) ------------------
   The tool's session is open while this runs: every click on an edge goes to
   the tool (which asks the server whether that adds or removes it), a click on
   a face is reported so the tool can say why it will not do. Hovered edges
   light up. Nothing is remembered here — the plan's gold edges are the truth. */
let edgePickCb = null;
let hoverLine = null, hoverColor = null, hoverPending = false;
const HOVER_COLOR = 0xffd54a;

export function beginEdgePick(onPick, opts = {}) {
  edgePickCb = onPick;
  renderer.domElement.style.cursor = 'crosshair';
  const h = document.getElementById('placeHint');
  h.textContent = `Click the edges to ${(opts.name || 'fillet').toLowerCase()} — ` +
    'a click adds an edge, another click removes it · Esc cancels';
  h.style.display = 'block';
}
export function endEdgePick() {
  if (!edgePickCb) return;
  edgePickCb = null;
  unhoverEdge();
  renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  document.getElementById('placeHint').style.display = 'none';
}
export function edgePickActive() { return !!edgePickCb; }

/* the edge line under the pointer, or null — a face in front of it hides it */
function edgeHitAt(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const fHit = raycaster.intersectObjects(bodyMeshes(), false)[0];
  const depth = fHit ? fHit.distance : camera.position.distanceTo(controls.target);
  raycaster.params.Line.threshold = worldPerPixel(depth) * EDGE_PICK_PX;
  const eHit = raycaster.intersectObjects(edgeLines, false)[0];
  if (eHit && (!fHit || eHit.distance <= fHit.distance + 1e-3)) return { edge: eHit, face: null };
  return { edge: null, face: fHit || null };
}
function unhoverEdge() {
  if (hoverLine) { hoverLine.material.color.setHex(hoverColor); hoverLine = null; }
}
function edgePickHover(e) {
  if (hoverPending) return;                  // one raycast per frame, not per event
  hoverPending = true;
  requestAnimationFrame(() => {
    hoverPending = false;
    if (!edgePickCb) return;
    const { edge } = edgeHitAt(e);
    const line = edge ? edge.object : null;
    if (line === hoverLine) return;
    unhoverEdge();
    if (line) {
      hoverLine = line; hoverColor = line.material.color.getHex();
      line.material.color.setHex(HOVER_COLOR);
    }
    renderer.domElement.style.cursor = line ? 'crosshair' : 'not-allowed';
  });
}
function edgePickAt(e) {
  const { edge, face } = edgeHitAt(e);
  const cb = edgePickCb;
  if (edge) {
    const body = edge.object.userData.body;
    const src = bodyObjs.find(b => b.id === body);
    const info = src && (src.data.edges || []).find(x => x.id === edge.object.userData.edgeId);
    if (info) cb('edge', { ...info, body: src.id });
    return;
  }
  if (face) cb('face', faceInfoAt(face));
  // empty space: keep waiting
}

/* the edges a tool has selected, drawn GOLD on top of everything — from the
   plan's points, never from the model's edge ids */
let edgeGlow = [];
export function beginEdgeGlow(edges) {
  endEdgeGlow();
  for (const e of edges || []) {
    const g = new THREE.BufferGeometry().setFromPoints(
      (e.points || []).map(p => new THREE.Vector3(p[0], p[1], p[2])));
    const line = new THREE.Line(g, new THREE.LineBasicMaterial({
      color: 0xffc83c, depthTest: false, transparent: true, opacity: 0.95 }));
    line.renderOrder = 1003;
    scene.add(line); edgeGlow.push(line);
  }
}
export function endEdgeGlow() {
  for (const l of edgeGlow) { scene.remove(l); l.geometry.dispose(); }
  edgeGlow = [];
}

/* ---------------- pick a plane (or planar face) to sketch on (Fusion) ------- */

/* other tools call this so a pending plane-pick never lingers ("stuck grids") */
export function cancelPlanePick() { if (planePickCb) endPlanePick(); }

export function beginPlanePick(onPick) {
  planePickCb = onPick;
  renderer.domElement.style.cursor = 'pointer';
  const h = document.getElementById('placeHint');
  h.textContent = 'Select a plane or planar face · Esc to cancel';
  h.style.display = 'block';
  buildOriginPlanes();
}

function endPlanePick() {
  planePickCb = null;
  renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  document.getElementById('placeHint').style.display = 'none';
  clearOriginPlanes();
}

function makeLabelSprite(text, color) {
  const c = document.createElement('canvas'); c.width = 128; c.height = 72;
  const ctx = c.getContext('2d');
  ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = '#' + color.toString(16).padStart(6, '0');
  ctx.fillText(text, 64, 38);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex,
    transparent: true, depthTest: false }));
  const h = Math.max(fitRadius * 0.32, 16);
  sp.scale.set(h * (128 / 72), h, 1);
  sp.renderOrder = 1000;
  return sp;
}

/* The three origin planes, drawn WHERE THE SKETCH WILL ACTUALLY LAND.

   They used to be centred on `fitCenter` (the model's bounding-sphere centre),
   so with a part sitting at z=40 the "XY" quad floated at z=40 — but clicking
   it starts a sketch on the TRUE XY plane at z=0. The quad was in the wrong
   place by exactly the model's offset, which is the "coordinate planes are not
   aligned with the design" complaint.

   Each quad is now placed at fitCenter PROJECTED onto its own plane (the
   normal component zeroed), so it lies exactly in the plane it names while
   staying under/through the part rather than off at the origin. `normalAxis`
   is the component that must be 0. */
function buildOriginPlanes() {
  clearOriginPlanes();
  const s = Math.max(fitRadius * 1.15, 55);      // half-size of each plane quad
  const defs = [
    { plane: 'XY', rot: [0, 0, 0], color: 0x4d7fff, normalAxis: 'z',
      lpos: [s * 0.72, s * 0.72, 0] },
    { plane: 'XZ', rot: [Math.PI / 2, 0, 0], color: 0x43c579, normalAxis: 'y',
      lpos: [s * 0.72, 0, s * 0.72] },
    { plane: 'YZ', rot: [0, Math.PI / 2, 0], color: 0xff6b6b, normalAxis: 'x',
      lpos: [0, s * 0.72, s * 0.72] },
  ];
  for (const d of defs) {
    const at = fitCenter.clone();
    at[d.normalAxis] = 0;                        // ON the plane, not beside it
    const geo = new THREE.PlaneGeometry(2 * s, 2 * s);
    const mat = new THREE.MeshBasicMaterial({ color: d.color, transparent: true,
      opacity: 0.16, side: THREE.DoubleSide, depthWrite: false });
    const m = new THREE.Mesh(geo, mat);
    m.rotation.set(...d.rot);
    m.position.copy(at);
    m.userData.plane = d.plane; m.userData.base = 0.16;
    m.renderOrder = 998;
    scene.add(m); originPlanes.push(m);
    const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: d.color, transparent: true, opacity: 0.6 }));
    edge.rotation.set(...d.rot); edge.position.copy(at);
    edge.renderOrder = 999; scene.add(edge); originPlanes.push(edge);
    const label = makeLabelSprite(d.plane, d.color);
    // label offsets are already IN-plane, so they keep the quad's plane
    label.position.set(at.x + d.lpos[0], at.y + d.lpos[1], at.z + d.lpos[2]);
    scene.add(label); originPlanes.push(label);
  }
}

function clearOriginPlanes() {
  for (const o of originPlanes) {
    scene.remove(o);
    if (o.geometry) o.geometry.dispose();
    if (o.material && o.material.map) o.material.map.dispose();
  }
  originPlanes.length = 0;
}

function ndcFrom(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  return new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
}

/* the face of a body mesh under a raycast hit, or null */
function faceInfoAt(hit) {
  const entry = bodyObjs.find(b => b.mesh === hit.object);
  const fid = entry && entry.data.faceId[hit.face.a];
  return (entry && entry.data.faces.find(f => f.id === fid)) || null;
}

function planePickHover(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const quads = originPlanes.filter(o => o.userData.plane);
  for (const q of quads) q.material.opacity = q.userData.base;
  renderer.domElement.style.cursor = 'pointer';
  const fHit = raycaster.intersectObjects(bodyMeshes(), false)[0];
  if (fHit) {
    const info = faceInfoAt(fHit);
    // crosshair only over a face that WILL pick; a curved face (fillet band,
    // cylinder wall) shows not-allowed instead of promising a pick
    renderer.domElement.style.cursor =
      info && info.type === 'PLANE' && info.center ? 'crosshair'
                                                   : 'not-allowed';
    return;
  }
  const hit = raycaster.intersectObjects(quads, false)[0];
  if (hit) hit.object.material.opacity = 0.4;
}

function planePickAt(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const quads = originPlanes.filter(o => o.userData.plane);
  const pHit = raycaster.intersectObjects(quads, false)[0];
  const fHit = raycaster.intersectObjects(bodyMeshes(), false)[0];   // any body
  const cb = planePickCb;
  // A body face under the cursor wins even when an origin-plane quad floats
  // IN FRONT of it. The quads are translucent glass passing THROUGH the
  // model, so "nearest hit wins" made faces unpickable from whole view
  // angles: from iso, the XZ quad sat 4mm in front of a box's top face and
  // every click on the visible solid silently became an XZ plane sketch.
  // Clicking the solid means the solid; the quads keep their ample area
  // OUTSIDE the model's silhouette (they are sized past fitRadius).
  if (fHit) {
    const info = faceInfoAt(fHit);
    if (info && info.type === 'PLANE' && info.center) {
      endPlanePick(); cb('face', info); return;
    }
    // Clicked ON the body but NOT a flat face (a fillet band, a cylinder
    // wall). Never fall through to the origin quad hiding behind the solid:
    // that silently started a sketch on a plane INSIDE the body, so the
    // finished profile was swallowed by the solid — "my shape vanished".
    // Say why (rule 7) and keep waiting for a real pick.
    const kind = info && info.type ? info.type.toLowerCase() : 'curved';
    document.getElementById('placeHint').textContent =
      `That face is ${kind}, not flat — pick a planar face, or an origin ` +
      'plane outside the part · Esc to cancel';
    bus.emit('msg', 'bot', `⚠ That face is ${kind} — a sketch needs a FLAT ` +
      'face. Pick a planar face, or an origin plane outside the part.');
    return;
  }
  if (pHit) { const pl = pHit.object.userData.plane; endPlanePick(); cb('plane', pl); return; }
  // clicked empty space — keep waiting (don't cancel)
}

/* ---------------- draggable Extrude arrow (Fusion-style) ---------------- */

export function beginExtrudeArrow(originArr, normalArr, amount, onChange, onCommit,
                                   clampFn) {
  endExtrudeArrow();
  exArrow = makeArrow(originArr, normalArr, amount, onChange, onCommit, clampFn);
}
/* a SECOND arrow with the same mechanics — Rectangular Pattern's direction 2.
   Every helper below takes the arrow it works on (the first by default); the
   pointer handlers try both, and `dragArrow` is the one a drag holds. */
export function beginSecondArrow(originArr, normalArr, amount, onChange, onCommit, clampFn) {
  endSecondArrow();
  exArrow2 = makeArrow(originArr, normalArr, amount, onChange, onCommit, clampFn);
}
export function endSecondArrow() {
  if (!exArrow2) return;
  disposeArrow(exArrow2); exArrow2 = null;
}
export function setSecondArrowAmount(a) {
  if (exArrow2 && !exArrow2.dragging) { exArrow2.amount = a; updateArrow(exArrow2); }
}
function makeArrow(originArr, normalArr, amount, onChange, onCommit, clampFn) {
  const O = new THREE.Vector3(...originArr);
  const N = new THREE.Vector3(...normalArr).normalize();
  const arrow = new THREE.ArrowHelper(N, O, 1, 0xffb85c);
  for (const m of [arrow.line.material, arrow.cone.material]) {
    m.depthTest = false; m.transparent = true;      // always visible, on top of the solid
  }
  arrow.line.renderOrder = 1002; arrow.cone.renderOrder = 1002;
  arrow.renderOrder = 1001;
  // Fusion-style: the arrow has a FIXED comfortable size and RIDES the
  // extruded face (base at O + N·amount) — its length does not encode the
  // distance, so it is always easy to see and grab.
  const len = Math.max(fitRadius * 0.32, 16);
  const grabR = Math.max(fitRadius * 0.07, 4.5);
  const hit = new THREE.Mesh(                    // fat invisible grab cylinder
    new THREE.CylinderGeometry(grabR, grabR, 1, 10),
    new THREE.MeshBasicMaterial({ visible: false }));
  scene.add(arrow); scene.add(hit);
  // amount 0 is a real value (the tool opens at 0 now) — only default nullish
  const a = { arrow, hit, O, N, amount: Number(amount) || 0, len, onChange,
              onCommit, clampFn, dragging: false, grab: 0 };
  updateArrow(a);
  return a;
}

export function endExtrudeArrow() {
  if (!exArrow) return;
  disposeArrow(exArrow); exArrow = null;
}
function disposeArrow(a) {
  if (dragArrow === a) { dragArrow = null; controls.enabled = true; }
  scene.remove(a.arrow); scene.remove(a.hit);
  a.hit.geometry.dispose(); a.hit.material.dispose();
  // the ArrowHelper's line and cone own a MATERIAL each — a tool that
  // re-places its handles on every change (Hole) strands them otherwise. Their
  // GEOMETRIES are not ours: three.js 0.160 builds `_lineGeometry` and
  // `_coneGeometry` once at module scope and hands the same two to every
  // ArrowHelper ever made (checked in the pinned build), so disposing them
  // would throw away the buffers the NEXT arrow is drawn from.
  a.arrow.line.material.dispose(); a.arrow.cone.material.dispose();
}

export function hasExtrudeArrow() { return !!exArrow; }
/* mid-drag? re-placing the arrow under a live drag would strand the drag with
   OrbitControls still disabled, so callers that re-aim it must ask first. */
export function extrudeArrowDragging() { return !!dragArrow; }

/* ---------------- extrude GHOST (instant drag preview) ----------------
   While dragging, a translucent white prism in the TRUE SHAPE of the profile
   (outer outline + holes — a circle face gives a circular ghost) shows where
   the material will go — no geometry rebuild per frame. The REAL verified
   extrude builds once on release. frame = {origin, x_dir, y_dir, z_dir};
   loops = [{outer: [[x,y],…], holes: [[[x,y],…],…]}, …] in plane-local coords. */
let exGhost = null;

/* one translucent ghost part — mesh + outline — the way EVERY tool's drag
   preview looks (Extrude's prism, Revolve's lathe). depthTest OFF: a ghost
   must stay visible when pushed INSIDE the body. */
function ghostPart(geo, edgeGeo = new THREE.EdgesGeometry(geo, 15)) {
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0.13, depthWrite: false,
    depthTest: false, side: THREE.DoubleSide }));
  const edges = new THREE.LineSegments(edgeGeo,
    new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true,
      opacity: 0.65, depthTest: false }));
  mesh.renderOrder = 990; edges.renderOrder = 991;
  mesh.matrixAutoUpdate = false; edges.matrixAutoUpdate = false;
  scene.add(mesh); scene.add(edges);
  return { mesh, edges };
}
function setPartsVisible(parts, v) {
  for (const P of parts) { P.mesh.visible = v; P.edges.visible = v; }
}
function disposeParts(parts) {
  for (const P of parts) {
    scene.remove(P.mesh); scene.remove(P.edges);
    P.mesh.geometry.dispose(); P.edges.geometry.dispose();
  }
}

export function beginExtrudeGhost(frame, loops) {
  endExtrudeGhost();
  // ONE PART PER OUTLINE (user 2026-09-03: "two circles with different
  // diameters — the ghost goes inclined, not a straight cone"): the taper morph
  // used to shrink every outline toward the profile's COMMON centroid, so a
  // small circle beside a big one leaned toward it. The real solid tapers
  // each face toward its own centre and ends at its own tip — so does the
  // ghost now: each loop is its own unit-depth prism with its own centre,
  // mean radius and height cap.
  const parts = [];
  for (const L of loops || []) {
    if (!L.outer || L.outer.length < 3) continue;
    const shape = new THREE.Shape(L.outer.map(p => new THREE.Vector2(p[0], p[1])));
    for (const h of L.holes || [])
      if (h.length >= 3) shape.holes.push(new THREE.Path(h.map(p => new THREE.Vector2(p[0], p[1]))));
    const geo = new THREE.ExtrudeGeometry([shape], { depth: 1, bevelEnabled: false });
    const { mesh, edges } = ghostPart(geo);
    let cx = 0, cy = 0;
    for (const q of L.outer) { cx += q[0]; cy += q[1]; }
    cx /= L.outer.length; cy /= L.outer.length;
    let mr = 0;
    for (const q of L.outer) mr += Math.hypot(q[0] - cx, q[1] - cy);
    mr = Math.max(mr / L.outer.length, 0.5);
    parts.push({ mesh, edges, cx, cy, meanR: mr,
                 basePos: Float32Array.from(geo.attributes.position.array) });
  }
  if (!parts.length) return;
  exGhost = {
    parts, mesh: parts[0].mesh, edges: parts[0].edges,   // .mesh/.edges: test hooks
    lastTaper: null, lastAmount: null, lastCaps: null,
    x: new THREE.Vector3(...frame.x_dir), y: new THREE.Vector3(...frame.y_dir),
    z: new THREE.Vector3(...frame.z_dir), o: new THREE.Vector3(...frame.origin),
  };
  ghostVisible(false);
}

/* amount: the signed depth asked; taper: degrees (Fusion sign, negative
   narrows); caps: per-loop maximum heights (where that loop's walls meet —
   the server's numbers) or null while unknown */
export function setExtrudeGhost(amount, taper = 0, caps = null) {
  if (!exGhost) return;
  ghostVisible(true);
  const changed = taper !== exGhost.lastTaper || amount !== exGhost.lastAmount
    || JSON.stringify(caps) !== JSON.stringify(exGhost.lastCaps);
  const sign = amount < 0 ? -1 : 1;
  exGhost.parts.forEach((P, i) => {
    const cap = caps && caps[i] != null ? caps[i] : Infinity;
    const h = Math.max(Math.min(Math.abs(amount), cap), 0.01);   // this loop's real height
    if (changed) {
      // taper morph: shrink THIS outline's cross-section toward ITS centroid
      // with height (approximate — the ghost is a drag aid; the solid is exact)
      const pos = P.mesh.geometry.attributes.position;
      const base = P.basePos;
      const k = Math.tan(-(taper || 0) * Math.PI / 180) * h / P.meanR;
      for (let v = 0; v < pos.count; v++) {
        const x = base[v * 3], y = base[v * 3 + 1], z = base[v * 3 + 2];
        // the floor is (almost) zero: at the tip the real solid IS a point
        const s = Math.max(1 - k * z, 0.001);
        pos.setXYZ(v, P.cx + (x - P.cx) * s, P.cy + (y - P.cy) * s, z);
      }
      pos.needsUpdate = true;
      P.edges.geometry.dispose();                 // the outline follows the morph
      P.edges.geometry = new THREE.EdgesGeometry(P.mesh.geometry, 15);
    }
    const m = new THREE.Matrix4().makeBasis(exGhost.x, exGhost.y, exGhost.z)
      .scale(new THREE.Vector3(1, 1, sign * h))
      .setPosition(exGhost.o);
    P.mesh.matrix.copy(m);
    P.edges.matrix.copy(m);
  });
  if (changed) { exGhost.lastTaper = taper; exGhost.lastAmount = amount; exGhost.lastCaps = caps; }
}

/* test hook: per outline, the world-space centre of its base and of its top
   ring, and its height — a straight cone keeps top over base */
export function ghostLoopTops() {
  if (!exGhost) return null;
  return exGhost.parts.map(P => {
    const pos = P.mesh.geometry.attributes.position;
    let tx = 0, ty = 0, n = 0;
    for (let v = 0; v < pos.count; v++)
      if (pos.getZ(v) > 0.5) { tx += pos.getX(v); ty += pos.getY(v); n++; }
    const toWorld = (u, w, z) => exGhost.o.clone().addScaledVector(exGhost.x, u)
      .addScaledVector(exGhost.y, w).addScaledVector(exGhost.z, z).toArray();
    const hz = P.mesh.matrix.elements[10] / exGhost.z.length();   // the z scale = signed height
    return { base: toWorld(P.cx, P.cy, 0), top: toWorld(tx / (n || 1), ty / (n || 1), hz),
             height: hz };
  });
}

function ghostVisible(v) { if (exGhost) setPartsVisible(exGhost.parts, v); }
export function hideExtrudeGhost() { ghostVisible(false); }
export function hasExtrudeGhostVisible() { return !!(exGhost && exGhost.mesh.visible); }

export function endExtrudeGhost() {
  if (!exGhost) return;
  disposeParts(exGhost.parts);
  exGhost = null;
}

/* ---------------- taper RING (Fusion's dashed circle + handle) -------------
   A dashed circle in the profile plane with a round handle; dragging the
   handle around the ring changes the taper angle (± around zero). Same ghost
   protocol as the arrow: drag = ghost only, release = one verified rebuild. */
let taperRing = null;

/* the angle accumulates the unwrapped delta of every drag step — 0..±360 for
   Revolve, ±max_taper for Extrude: the tool's clampFn owns the range, the
   gizmo has no wrap or cap of its own.
   A DRAGGED angle lands on round numbers (user 2026-09-07: "revolve goes to
   90.5 — it should recognise 0, 45, 90, 180"): whole degrees, and within
   SNAP_BAND of a multiple of SNAP_STEP the multiple itself, where the handle
   sticks until the pointer leaves the band. The raw turn keeps accumulating
   underneath so the handle never lags the pointer. Typed values stay exact. */
const SNAP_STEP = 45, SNAP_BAND = 3;
function snapAngle(deg) {
  const near = Math.round(deg / SNAP_STEP) * SNAP_STEP;
  return (Math.abs(deg - near) <= SNAP_BAND ? near : Math.round(deg)) || 0;   // never -0
}
export function beginTaperRing(centerArr, frame, radius, taper0, onChange, onCommit,
                               clampFn) {
  endTaperRing();
  const C = new THREE.Vector3(...centerArr);
  const X = new THREE.Vector3(...frame.x_dir).normalize();
  const Y = new THREE.Vector3(...frame.y_dir).normalize();
  const N = new THREE.Vector3(...frame.z_dir).normalize();
  const R = Math.max(radius, 8);
  const ringAt = deg => {
    const a = deg * Math.PI / 180;
    return C.clone().add(X.clone().multiplyScalar(R * Math.cos(a)))
                    .add(Y.clone().multiplyScalar(R * Math.sin(a)));
  };
  const pts = Array.from({ length: 97 }, (_, i) => ringAt(i * 360 / 96));
  const circGeo = new THREE.BufferGeometry().setFromPoints(pts);
  const circle = new THREE.Line(circGeo, new THREE.LineDashedMaterial({
    color: 0x4da3ff, dashSize: 2.4, gapSize: 1.6, transparent: true,
    opacity: 0.9, depthTest: false }));
  circle.computeLineDistances();
  circle.renderOrder = 1001;
  const hr = Math.max(R * 0.055, 2.2);
  const handle = new THREE.Mesh(new THREE.SphereGeometry(hr, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0x4da3ff, depthTest: false }));
  const grab = new THREE.Mesh(new THREE.SphereGeometry(hr * 2.6, 8, 6),
    new THREE.MeshBasicMaterial({ visible: false }));
  handle.renderOrder = 1002;
  scene.add(circle); scene.add(handle); scene.add(grab);
  taperRing = { circle, handle, grab, C, X, Y, N, R, ringAt,
                taper: taper0 || 0, raw: 0, onChange, onCommit, clampFn,
                lastRaw: 0, dragging: false };
  taperRingPlace();
}

function taperRingPlace() {
  const p = taperRing.ringAt(taperRing.taper);
  taperRing.handle.position.copy(p);
  taperRing.grab.position.copy(p);
}

export function setTaperRingAngle(deg) {
  if (taperRing && !taperRing.dragging) { taperRing.taper = deg; taperRingPlace(); }
}

export function endTaperRing() {
  if (!taperRing) return;
  for (const o of [taperRing.circle, taperRing.handle, taperRing.grab]) {
    scene.remove(o); o.geometry.dispose();
  }
  taperRing = null;
}

export function hasTaperRing() { return !!taperRing; }

/* screen position of a ring point at `deg` — lets tests drive angular drags */
export function taperRingPointScreen(deg) {
  if (!taperRing) return null;
  return toScreen(taperRing.ringAt(deg));
}

/* pointer ray -> angle (deg) around the ring in its plane */
function taperAngleAt(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(taperRing.N, taperRing.C);
  const hit = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(plane, hit)) return taperRing.taper;
  const v = hit.sub(taperRing.C);
  return Math.atan2(v.dot(taperRing.Y), v.dot(taperRing.X)) * 180 / Math.PI;
}

function taperGrab(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  if (!raycaster.intersectObject(taperRing.grab, false).length) return false;
  taperRing.dragging = true;
  controls.enabled = false;
  taperRing.lastRaw = taperAngleAt(e);
  taperRing.raw = taperRing.taper;                 // the turn starts from what the box shows
  return true;
}

function taperDrag(e) {
  const raw = taperAngleAt(e);
  let d = raw - taperRing.lastRaw;                 // this step's turn, unwrapped
  while (d > 180) d -= 360;
  while (d < -180) d += 360;
  taperRing.lastRaw = raw;
  // no cap of its own (user 2026-09-03: "in Fusion it goes until -90"): the
  // tool's clampFn holds the server's limit — one limit, one place. The snap
  // is clamped too: a mark past the limit (90 on a taper capped at 89) is out
  // of reach, not one step further than the limit allows
  const clamp = taperRing.clampFn || (x => x);
  taperRing.raw = clamp(taperRing.raw + d);
  taperRing.taper = clamp(snapAngle(taperRing.raw));
  taperRingPlace();
  taperRing.onChange(taperRing.taper);
}

function taperRelease() {
  taperRing.dragging = false;
  controls.enabled = true;
  taperRing.onCommit(taperRing.taper);
}

/* ---------------- a tool's AXIS line (Revolve: the spin axis, gold) ---------- */
let axisLine = null;

export function beginAxisLine(originArr, dirArr, half) {
  endAxisLine();
  const o = new THREE.Vector3(...originArr);
  const d = new THREE.Vector3(...dirArr).normalize();
  const geo = new THREE.BufferGeometry().setFromPoints([
    o.clone().addScaledVector(d, -half), o.clone().addScaledVector(d, half)]);
  axisLine = new THREE.Line(geo, new THREE.LineBasicMaterial({
    color: 0xffc400, transparent: true, opacity: 0.95, depthTest: false }));
  axisLine.renderOrder = 1000;
  scene.add(axisLine);
}
export function endAxisLine() {
  if (!axisLine) return;
  scene.remove(axisLine); axisLine.geometry.dispose(); axisLine = null;
}

/* ---------------- a tool's PLANE (Mirror: the mirror plane, a gold square) ----
   Placed by the plan's frame {origin, x_dir, y_dir, z_dir} and sized by its
   `half` — where it is and which way it faces are the server's (R1). */
let planeQuad = null;

export function beginPlaneQuad(frame, half) {
  endPlaneQuad();
  const geo = new THREE.PlaneGeometry(2 * half, 2 * half);
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: 0xffc400, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false }));
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({
    color: 0xffc400, transparent: true, opacity: 0.95, depthTest: false }));
  const basis = new THREE.Matrix4().makeBasis(
    new THREE.Vector3(...frame.x_dir).normalize(),
    new THREE.Vector3(...frame.y_dir).normalize(),
    new THREE.Vector3(...frame.z_dir).normalize()).setPosition(new THREE.Vector3(...frame.origin));
  for (const o of [mesh, edge]) {
    o.matrixAutoUpdate = false; o.matrix.copy(basis); o.renderOrder = 1000; scene.add(o);
  }
  planeQuad = { mesh, edge, frame };
}
export function endPlaneQuad() {
  if (!planeQuad) return;
  for (const o of [planeQuad.mesh, planeQuad.edge]) {
    scene.remove(o); o.geometry.dispose(); o.material.dispose();
  }
  planeQuad = null;
}

/* ---------------- a tool's POINT marker (Hole: the circle it will cut, gold) ----
   A unit circle placed by the plan's frame {origin, x_dir, y_dir, z_dir} at the
   hole's centre and SCALED to the radius — the Diameter box changes it without
   a rebuild, and nothing about where or which way is decided here (R1). */
let holeMarker = null;

export function beginHoleMarker(frame, radius) {
  endHoleMarker();
  const pts = [];
  for (let i = 0; i <= 64; i++) {
    const a = i / 64 * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a), Math.sin(a), 0));
  }
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color: 0xffc400, transparent: true, opacity: 0.95,
                                  depthTest: false }));
  line.renderOrder = 1000;
  line.matrixAutoUpdate = false;
  const basis = new THREE.Matrix4().makeBasis(
    new THREE.Vector3(...frame.x_dir).normalize(),
    new THREE.Vector3(...frame.y_dir).normalize(),
    new THREE.Vector3(...frame.z_dir).normalize()).setPosition(new THREE.Vector3(...frame.origin));
  holeMarker = { line, basis, radius: 0 };
  scene.add(line);
  setHoleMarker(radius);
}
export function setHoleMarker(radius) {
  if (!holeMarker) return;
  const r = Math.max(Number(radius) || 0, 1e-3);
  holeMarker.radius = r;
  holeMarker.line.matrix.copy(holeMarker.basis).scale(new THREE.Vector3(r, r, 1));
}
export function endHoleMarker() {
  if (!holeMarker) return;
  scene.remove(holeMarker.line);
  holeMarker.line.geometry.dispose(); holeMarker.line.material.dispose();
  holeMarker = null;
}

/* ---------------- revolve GHOST (instant drag preview) ----------------
   The profile outline swept by the current angle: a three.js lathe of the
   plan's (radial, axial) outline in the plan's ring frame. LatheGeometry spins
   points (x = radius, y = height) about its local +Y, starting on local +Z and
   turning toward local +X — so local Y is the axis, local Z the ring's x
   (radial, toward the material) and local X the ring's y: a positive angle
   turns the way the kernel sweeps (right-handed about the axis, probed
   2026-09-03). Holes are ignored: a ghost is a hint, the solid is the truth. */
let rvGhost = null;

export function beginRevolveGhost(frame, loops) {
  endRevolveGhost();
  const X = new THREE.Vector3(...frame.y_dir), Y = new THREE.Vector3(...frame.z_dir),
        Z = new THREE.Vector3(...frame.x_dir), O = new THREE.Vector3(...frame.origin);
  const basis = new THREE.Matrix4().makeBasis(X, Y, Z).setPosition(O);
  const parts = [];
  for (const L of loops || []) {
    if (!L.outer || L.outer.length < 3) continue;
    // |r|: a face on the far side of the axis sweeps the same annulus
    const pts = L.outer.map(p => new THREE.Vector2(Math.abs(p[0]), p[1]));
    pts.push(pts[0].clone());                          // close the outline
    // empty until the first drag: an EdgesGeometry cannot be made from nothing
    const part = ghostPart(new THREE.BufferGeometry(), new THREE.BufferGeometry());
    part.mesh.matrix.copy(basis); part.edges.matrix.copy(basis);
    parts.push({ ...part, pts });
  }
  setPartsVisible(parts, false);
  rvGhost = { parts, angle: 0, back: 0, pending: null, raf: 0 };
}

/* one geometry rebuild per animation frame, however fast the pointer moves.
   `back` (P3b, Two sides / Symmetric): degrees swept the OTHER way as well, so
   the lathe runs from the far end of that sweep through the profile to `deg` */
export function setRevolveGhost(deg, back = 0) {
  if (!rvGhost) return;
  rvGhost.pending = { deg, back: Math.max(0, back || 0) };
  if (rvGhost.raf) return;
  rvGhost.raf = requestAnimationFrame(() => {
    if (!rvGhost) return;
    rvGhost.raf = 0;
    const { deg: a, back: b } = rvGhost.pending;
    rvGhost.angle = a; rvGhost.back = b;
    const total = Math.abs(a) + b;
    if (total <= 0.05) { setPartsVisible(rvGhost.parts, false); return; }
    const len = total * Math.PI / 180;
    const start = (a < 0 ? a : -b) * Math.PI / 180;
    const segs = Math.max(8, Math.round(total / 5));
    for (const P of rvGhost.parts) {
      P.mesh.geometry.dispose(); P.edges.geometry.dispose();
      P.mesh.geometry = new THREE.LatheGeometry(P.pts, segs, start, len);
      P.edges.geometry = new THREE.EdgesGeometry(P.mesh.geometry, 15);
    }
    setPartsVisible(rvGhost.parts, true);
  });
}
export function hideRevolveGhost() { if (rvGhost) setPartsVisible(rvGhost.parts, false); }
export function endRevolveGhost() {
  if (!rvGhost) return;
  if (rvGhost.raf) cancelAnimationFrame(rvGhost.raf);
  disposeParts(rvGhost.parts);
  rvGhost = null;
}

/* debug snapshot of the arrow gizmo (used by verification scripts) */
export function extrudeArrowDebug() {
  if (!exArrow) return null;
  const v = axisScreenVector();
  return { amount: exArrow.amount, len: exArrow.len, fitRadius,
           pxPerMm: Math.hypot(v.x, v.y), camDist: camera.position.distanceTo(fitCenter) };
}

/* keep the arrow in sync when the distance is typed in the value box */
export function setExtrudeArrowAmount(a) {
  if (exArrow && !exArrow.dragging) { exArrow.amount = a; updateArrow(exArrow); }
}

function toScreen(p) {
  const v = p.clone().project(camera);
  const r = renderer.domElement.getBoundingClientRect();
  return { x: r.left + (v.x * 0.5 + 0.5) * r.width,
           y: r.top + (-v.y * 0.5 + 0.5) * r.height };
}

/* the arrow's pointing direction — always a COPY: multiplying a reference to
   exArrow.N would scale the stored normal and corrupt every later calculation. */
function arrowDir(a = exArrow) {
  const d = a.N.clone();
  return a.amount >= 0 ? d : d.negate();
}
function arrowBase(a = exArrow) {
  return a.O.clone().add(a.N.clone().multiplyScalar(a.amount));
}

/* screen (client) coords of the arrow's middle — for driving/aiming the drag */
export function extrudeArrowTipScreen() {
  if (!exArrow) return null;
  return toScreen(arrowBase().add(arrowDir().multiplyScalar(exArrow.len * 0.5)));
}

/* screen coords of the arrow base and tip — the true on-screen drag axis */
export function extrudeArrowAxisScreen() {
  if (!exArrow) return null;
  const base = arrowBase();
  const tip = base.clone().add(arrowDir().multiplyScalar(exArrow.len));
  return { base: toScreen(base), tip: toScreen(tip) };
}
export function secondArrowAxisScreen() {          // the same, for Rectangular Pattern's second arrow
  if (!exArrow2) return null;
  const base = arrowBase(exArrow2);
  const tip = base.clone().add(arrowDir(exArrow2).multiplyScalar(exArrow2.len));
  return { base: toScreen(base), tip: toScreen(tip) };
}

function updateArrow(a = exArrow) {
  const len = a.len;
  const dir = arrowDir(a);                       // copy — never mutate N
  const base = arrowBase(a);
  const head = len * 0.42;                       // big, easy-to-see head
  a.arrow.position.copy(base);
  a.arrow.setDirection(dir);
  a.arrow.setLength(len, head, head * 0.62);
  const mid = base.clone().add(dir.clone().multiplyScalar(len / 2));
  a.hit.position.copy(mid);
  a.hit.scale.set(1, len * 1.2, 1);              // grab a bit beyond the tip
  a.hit.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
}

/* signed distance along the axis (O + s·N) nearest to the pointer ray */
function projectAmount(e, a = exArrow) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const rp = raycaster.ray.origin, rd = raycaster.ray.direction;
  const r = new THREE.Vector3().subVectors(a.O, rp);
  const b = a.N.dot(rd), c = rd.dot(rd);
  const d = a.N.dot(r), ee = rd.dot(r);
  const denom = c - b * b;                        // a = N·N = 1
  if (Math.abs(denom) < 1e-6) return a.amount;
  return (b * ee - c * d) / denom;
}

/* pixels of screen movement per 1mm along the extrude axis. When the axis is
   nearly head-on to the camera this collapses, so we fall back to the ray
   method — otherwise dragging follows the arrow's ON-SCREEN direction, which is
   what makes a gizmo feel predictable. */
function axisScreenVector(ar = exArrow) {
  const a = ar.amount;
  const p0 = toScreen(ar.O.clone().add(ar.N.clone().multiplyScalar(a)));
  const p1 = toScreen(ar.O.clone().add(ar.N.clone().multiplyScalar(a + 1)));
  return { x: p1.x - p0.x, y: p1.y - p0.y };
}

function arrowGrab(e, a) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  if (!raycaster.intersectObject(a.hit, false).length) return false;
  a.dragging = true;
  dragArrow = a;
  controls.enabled = false;
  const v = axisScreenVector(a);
  const len2 = v.x * v.x + v.y * v.y;
  if (len2 > 4) {                        // >2px per mm — screen-space drag
    a.mode = 'screen';
    a.axis2D = v; a.axisLen2 = len2;
    a.startAmount = a.amount;
    a.startXY = { x: e.clientX, y: e.clientY };
  } else {                               // axis points at the camera — use the ray
    a.mode = 'ray';
    a.grab = a.amount - projectAmount(e, a);
  }
  return true;
}

function arrowDrag(e) {
  const ar = dragArrow;
  let a;
  if (ar.mode === 'screen') {
    const dx = e.clientX - ar.startXY.x, dy = e.clientY - ar.startXY.y;
    const along = (dx * ar.axis2D.x + dy * ar.axis2D.y) / ar.axisLen2;
    a = ar.startAmount + along;
  } else {
    a = projectAmount(e, ar) + ar.grab;
  }
  if (ar.clampFn) a = ar.clampFn(a);     // barrier (e.g. taper collapse)
  ar.amount = a;
  updateArrow(ar);
  ar.onChange(ar.amount);
}

function arrowRelease() {
  const ar = dragArrow;
  dragArrow = null;                      // released BEFORE the commit: it may end the arrow
  ar.dragging = false;
  controls.enabled = true;
  ar.onCommit(ar.amount);
}

/* Standard CAD view poses in the Z-up frame (see WORLD_UP).

   TOP looks down -Z, which is the POLE of the Z-up orbit frame. Parked exactly
   there, up is antiparallel to the view direction: cross(up, viewDir) = 0, the
   camera basis is degenerate (lookAt goes to pieces) and OrbitControls clamps
   phi so orbiting dies — measured 180.0deg and 0.07mm of movement on a full
   drag. So TOP sits TILT_DEG off vertical: screen-up comes out +Y (Fusion's
   top view, X right / Y up), the basis is sound, and the tilt is invisible at
   2deg (~3mm of side wall across a 100mm part). Dragging further past
   straight-down is still clamped by the pole — inherent to a fixed-axis orbit,
   and the gesture is meaningless anyway; every other direction is free.

   FRONT needs no such trick now: looking along +Y with up +Z is already
   perpendicular. It used to be the degenerate one, back when the camera was
   Y-up — that is exactly what its old z*0.001 nudge was patching. */
const TOP_TILT = 2 * Math.PI / 180;

export function setView(dir) {
  const d = fitRadius * 2.4, c = fitCenter;
  const views = {
    iso:   [c.x + d * 0.7, c.y - d * 0.7, c.z + d * 0.55],
    top:   [c.x, c.y - d * Math.sin(TOP_TILT), c.z + d * Math.cos(TOP_TILT)],
    front: [c.x, c.y - d, c.z],
  };
  camera.position.set(...views[dir]); controls.target.copy(c);
  // posing the camera directly bypasses OrbitControls' change event — tell
  // the listeners (adaptive grids, sketch labels) the view moved anyway
  bus.emit('view-changed');
}

function disposeModel() {
  for (const b of bodyObjs) { scene.remove(b.mesh); b.mesh.geometry.dispose(); }
  bodyObjs.length = 0;
  mesh = null;
  for (const l of edgeLines) { scene.remove(l); l.geometry.dispose(); }
  edgeLines.length = 0;
  for (const o of sketchObjs) { scene.remove(o); o.geometry.dispose(); }
  sketchObjs.length = 0;
  clearPickHighlight();
}

/* Every body from /api/model, drawn as a real solid with its own crisp OCCT
   edges and registered so picking works on ALL of them. The result body is
   remembered in `mesh`/`MODEL` because the extrude ghost, plane-pick and fit
   paths still talk about "the" body. */
function addBodies(bodies) {
  for (const b of bodies || []) {
    if (!b.positions || !b.positions.length) continue;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(b.positions, 3));
    g.setIndex(b.indices);
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
      // Machined-metal grey (user, 2026-08-26: "i dont like the blue colour ...
      // it should be grey ... make it more cool"). Metalness stays LOW on
      // purpose: MeshStandardMaterial reflects an environment map, and there
      // is none here, so a genuinely metallic value renders dark and muddy.
      // Light neutral + low metal + medium roughness reads as bead-blasted
      // aluminium under the three-light rig, and the blue rim light does the
      // "cool" without tinting the part blue.
      color: 0xc4cad3, metalness: 0.30, roughness: 0.44,
      flatShading: false }));
    m.userData.body = b.id;
    scene.add(m);
    const entry = { id: b.id, result: !!b.result, mesh: m,
                    data: { positions: b.positions, indices: b.indices,
                            faceId: b.faceId, faces: b.faces,
                            edges: b.edges || [] } };
    bodyObjs.push(entry);
    if (b.result) { mesh = m; MODEL = entry.data; }
    for (const e of b.edges || []) {
      const eg = new THREE.BufferGeometry().setFromPoints(
        e.points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
      // near-black neutral: on a grey body the old dark BLUE edges read as a
      // blue tint at a distance, which is what made the part look blue at all
      const line = new THREE.Line(eg, new THREE.LineBasicMaterial({
        color: 0x232830, transparent: true, opacity: 0.68 }));
      line.userData.edgeId = e.id;
      line.userData.body = b.id;
      scene.add(line); edgeLines.push(line);
    }
  }
}

function bodyMeshes() { return bodyObjs.map(b => b.mesh); }

/* While sketch MODE is on, floating sketch profiles hide (user mandate R3:
   the sketch being edited is drawn by the sketcher itself; other sketches
   must not clutter the isolated view — Fusion behavior). */
let sketchesHidden = false;
bus.on('sketch-mode', ({ active }) => {
  sketchesHidden = active;
  for (const o of sketchObjs) o.visible = !active;
});

function addSketches(sketches) {
  for (const s of sketches || []) {
    if (s.positions.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position',
        new THREE.Float32BufferAttribute(s.positions, 3));
      g.setIndex(s.indices);
      g.computeVertexNormals();
      // polygonOffset: a sketch drawn ON a body's face is COPLANAR with it —
      // without the offset it z-fights and reads as "my sketch disappeared"
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
        color: 0x43c579, transparent: true, opacity: 0.18,
        side: THREE.DoubleSide, depthWrite: false,
        polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }));
      m.userData.sketchId = s.id;      // profiles are PICKABLE (Fusion)
      m.renderOrder = 2;
      m.visible = !sketchesHidden;
      scene.add(m); sketchObjs.push(m);
    }
    for (const line of s.outlines || []) {
      const g = new THREE.BufferGeometry().setFromPoints(
        line.map(p => new THREE.Vector3(p[0], p[1], p[2])));
      const l = new THREE.Line(g, new THREE.LineBasicMaterial({
        color: 0x43c579,
        polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }));
      l.renderOrder = 2;
      l.visible = !sketchesHidden;
      scene.add(l); sketchObjs.push(l);
    }
  }
}

/* the pickable profile fills (outline Lines excluded) */
function sketchMeshes() {
  return sketchObjs.filter(o => o.isMesh && o.userData.sketchId);
}

/* Overlapping loads used to DOUBLE the scene: loadMesh is async and called
   from several places (dialogs, tabs, the 3s watcher), and two in flight each
   added their objects while only one disposed — leaving duplicate ghost
   profiles/bodies stacked on the real ones. The newest load wins; older ones
   drop their payload. */
let loadSeq = 0;

let drawnVersion = null;         // the geometry currently in the scene
let inflight = null;             // {version, fit, busy, promise}: the load fetching now

/* R3 — THE VIEWPORT FOLLOWS THE DOCUMENT (LAUNCH-PLAN.md P2). Every document
   change is announced on the bus with its geometry fingerprint; when that
   differs from what is on screen the scene refreshes by itself, so no tool
   calls loadMesh() by hand (the explicit calls left in other modules join the
   load already running). A multi-step change — create a feature, then its
   Cut — runs inside holdViewport(), and the scene refreshes once, at the end,
   never showing the half-done state. */
let holds = 0, followDue = false;
export async function holdViewport(fn) {
  holds++;
  try { return await fn(); }
  finally { if (--holds === 0 && followDue) { followDue = false; follow(); } }
}
let latestVersion = null;        // fingerprint of the newest document announced
function follow(doc) {
  if (doc && doc.geom_version) latestVersion = doc.geom_version;   // from the event, not S
  if (holds) { followDue = true; return; }
  if (latestVersion && latestVersion !== drawnVersion) loadMesh();
}

/* Re-fetching and re-rendering the model is the most expensive thing the UI
   does (megabytes of triangles, plus a full three.js scene rebuild). Most calls
   ask for geometry that is already on screen — finishing or cancelling a sketch
   without changing anything, undoing back to the same state, switching tools.
   The document carries a geometry fingerprint, so those cost nothing now.
   `force` bypasses it for callers that must reload (imports, tab switches).
   A call for the version that is ALREADY being fetched rides that load (its
   fit wish carried over) instead of transferring the megabytes twice. A load
   for an OLDER version finishes and is dropped on arrival (loadSeq) — not
   aborted: uvicorn logs a protocol-error traceback for every response a
   client abandons mid-transfer. */
export function loadMesh(fit = false, force = false) {
  const version = latestVersion || (S.lastDoc && S.lastDoc.geom_version) || null;
  if (!force && inflight && version && inflight.version === version) {
    inflight.fit = inflight.fit || fit;
    return inflight.promise;
  }
  if (!force && version && version === drawnVersion && bodyObjs.length) {
    clearHighlight(); clearPick();         // already on screen: nothing to fetch
    if (fit) { camera.updateProjectionMatrix(); setView('iso'); }
    return Promise.resolve();
  }
  const job = { version, fit };
  job.promise = loadModel(job, force).finally(() => { if (inflight === job) inflight = null; });
  inflight = job;
  return job.promise;
}

async function loadModel(job, force) {
  const mine = ++loadSeq;
  const version = job.version;
  clearHighlight(); clearPick(); clearSelectionOverlay();
  // A forced load means the whole document changed (a tab switch, an import,
  // an opened design): say so, because it is the one case where the wait is
  // long enough to look like nothing happened.
  if (force) setBusy('loading the model…');
  try {
    const m = await (await fetch('/api/model?t=' + Date.now())).json();
    if (mine !== loadSeq) return;          // a newer load started meanwhile
    disposeModel();
    MODEL = null;
    drawnVersion = version || null;
    addSketches(m.sketches);
    addBodies(m.bodies);          // sets mesh + MODEL for the result body
    const fit = job.fit;                   // a caller may have asked meanwhile
    if (!bodyObjs.length) {
      if (fit && sketchObjs.length) fitToObjects(sketchObjs);
      return;
    }
    // frame on EVERY body, not just the result — a second body off to the side
    // must be in view, otherwise it looks like it never got made
    const all = [...bodyMeshes(), ...sketchObjs];
    const box = new THREE.Box3();
    for (const o of all) box.expandByObject(o);
    if (!box.isEmpty()) {
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      fitRadius = sphere.radius || 100;
      fitCenter.copy(sphere.center);
      updateGroundGrid();               // the plate grows with the model
      // the origin quads are placed and sized from this fit: while a pick shows
      // them (the sketch tool's, Mirror's) they follow the body, or a plate that
      // doubled across a plane sits over quads built for half of it (P4 review)
      if (originPlanes.length) buildOriginPlanes();
    }
    if (fit) {
      camera.near = fitRadius / 100; camera.far = fitRadius * 100;
      controls.maxDistance = camera.far * 0.85;
      controls.minDistance = zoomFloor();      // scales with the model
      camera.updateProjectionMatrix(); setView('iso');
    }
  } catch (e) { /* no model yet */ }
  finally { if (force) clearBusy(); }
}

export function clearMesh() {
  disposeModel(); MODEL = null; S.selected = null; clearHighlight();
  drawnVersion = null;            // the scene no longer matches any document
}

function fitToObjects(objs) {
  const box = new THREE.Box3();
  for (const o of objs) box.expandByObject(o);
  if (box.isEmpty()) return;
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  fitRadius = sphere.radius || 100;
  fitCenter.copy(sphere.center);
  updateGroundGrid();                   // the plate grows with the model
  camera.near = fitRadius / 100; camera.far = fitRadius * 100;
  controls.maxDistance = camera.far * 0.85;
  controls.minDistance = zoomFloor();
  camera.updateProjectionMatrix(); setView('iso');
}

/* ---------------- feature overlay (tree row click) ---------------- */

export function clearHighlight() {
  if (!hlMesh) return;
  scene.remove(hlMesh);
  for (const o of (hlMesh.isGroup ? hlMesh.children : [hlMesh]))
    if (o.geometry) o.geometry.dispose();
  hlMesh = null;
}

export async function showFeatureOverlay(fid) {
  clearHighlight();
  const f = ((S.lastDoc && S.lastDoc.features) || []).find(x => x.id === fid);
  try {
    if (f && (f.op === 'sketch' || f.op === 'sketch_on_face')) {
      // sketches highlight from their own tessellation — a CONSUMED sketch
      // has no scene object at all (it sits inside its extrude), so the
      // overlay must ignore depth to glow through the body
      const m = await (await fetch('/api/sketch-mesh/' + fid
                                   + '?t=' + Date.now())).json();
      if (m.error || S.selected !== fid) return;
      const grp = new THREE.Group();
      if (m.positions.length) {
        const g = new THREE.BufferGeometry();
        g.setAttribute('position',
          new THREE.Float32BufferAttribute(m.positions, 3));
        g.setIndex(m.indices);
        grp.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({
          color: 0xffb85c, transparent: true, opacity: 0.35,
          side: THREE.DoubleSide, depthWrite: false, depthTest: false })));
      }
      for (const line of m.outlines || []) {
        const g = new THREE.BufferGeometry().setFromPoints(
          line.map(p => new THREE.Vector3(p[0], p[1], p[2])));
        grp.add(new THREE.Line(g, new THREE.LineBasicMaterial({
          color: 0xffb85c, depthTest: false })));
      }
      grp.renderOrder = 5;
      grp.traverse(o => { o.renderOrder = 5; });
      hlMesh = grp;
      scene.add(grp);
      return;
    }
    const geo = await new STLLoader()
      .loadAsync('/api/feature-mesh/' + fid + '.stl?t=' + Date.now());
    geo.computeVertexNormals();
    if (S.selected !== fid) return;        // selection moved on while loading
    hlMesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color: 0xffb85c, emissive: 0x8a5a1a, transparent: true, opacity: 0.6,
      depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 }));
    scene.add(hlMesh);
  } catch (e) { /* feature not built (suppressed / rolled back) */ }
}

/* ---------------- the dimension line (Measure) ----------------
   The readout in the panel says WHAT was measured; this says BETWEEN WHAT.
   Without it, a number like "12.00 mm thick" is unfalsifiable — the user
   cannot tell whether the tool measured the two faces they meant. The line
   is drawn between the witness points the backend actually used. */

let dimOverlay = null;           // { group, from, to, text }

/* ---------------- the A/B selection overlay (Measure) ----------------
   A two-pick tool has to show BOTH picks. The normal pick highlight is a
   single transient object, so clicking the second face wiped the first — the
   user's own report: "when i am clicking the sechond face, the selected first
   fase color is vansiheg". These stay lit until the pair changes, each in its
   own colour with an A / B badge floating on it, so the labels in the panel and
   the faces in the model are the same two things. */

const SEL_COLORS = { A: 0x6ee7ff, B: 0xffb85c };   // cyan / amber
let selOverlay = [];             // [{ group, centre, tag }]
let pickHlOff = false;           // a tool is painting its own highlights

/* Let a tool take over highlighting while its panel is open. */
export function setPickHighlightEnabled(on) {
  pickHlOff = !on;
  if (pickHlOff) clearPickHighlight();
}

export function clearSelectionOverlay() {
  for (const s of selOverlay) {
    scene.remove(s.group);
    s.group.traverse(o => { if (o.geometry) o.geometry.dispose(); });
  }
  selOverlay = [];
  for (const tag of ['A', 'B']) {
    const el = document.getElementById('selBadge' + tag);
    if (el) el.style.display = 'none';
  }
}

/* picks = [{tag:'A'|'B', kind:'face'|'edge', id, body}] */
export function showSelectionOverlay(picks) {
  clearSelectionOverlay();
  for (const p of picks || []) {
    if (!p || p.id == null) continue;
    const entry = bodyObjs.find(b => b.id === p.body) || bodyObjs[0];
    if (!entry) continue;
    const colour = SEL_COLORS[p.tag] || 0x6ee7ff;
    const group = new THREE.Group();
    let centre = null;
    if (p.kind === 'face') {
      const g = faceGeometry(entry.data, p.id);
      if (!g) continue;
      group.add(new THREE.Mesh(g, new THREE.MeshStandardMaterial({
        color: colour, emissive: colour, emissiveIntensity: 0.25,
        side: THREE.DoubleSide, transparent: true, opacity: 0.7,
        depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3 })));
      const meta = (entry.data.faces || []).find(f => f.id === p.id);
      if (meta && meta.center) centre = new THREE.Vector3(...meta.center);
      else { g.computeBoundingSphere(); centre = g.boundingSphere.center.clone(); }
    } else {
      const e = (entry.data.edges || []).find(x => x.id === p.id);
      if (!e) continue;
      const g = new THREE.BufferGeometry().setFromPoints(
        e.points.map(q => new THREE.Vector3(q[0], q[1], q[2])));
      group.add(new THREE.Line(g, new THREE.LineBasicMaterial({
        color: colour, linewidth: 3, depthTest: false })));
      const mid = e.points[Math.floor(e.points.length / 2)];
      centre = new THREE.Vector3(mid[0], mid[1], mid[2]);
    }
    group.renderOrder = 999;
    group.traverse(o => { o.renderOrder = 999; });
    scene.add(group);
    selOverlay.push({ group, centre, tag: p.tag });
  }
  paintSelBadges();
}

/* the A / B badges ride their faces every frame, like the dimension label */
function paintSelBadges() {
  const seen = {};
  for (const s of selOverlay) {
    const el = document.getElementById('selBadge' + s.tag);
    if (!el || !s.centre) continue;
    seen[s.tag] = true;
    if (s.centre.clone().project(camera).z > 1) { el.style.display = 'none'; continue; }
    const p = toScreen(s.centre);
    const r = renderer.domElement.getBoundingClientRect();
    el.textContent = s.tag;
    el.style.display = 'block';
    el.style.left = (p.x - r.left) + 'px';
    el.style.top = (p.y - r.top) + 'px';
  }
  for (const tag of ['A', 'B']) {
    if (seen[tag]) continue;
    const el = document.getElementById('selBadge' + tag);
    if (el) el.style.display = 'none';
  }
}

function dimEnd(p) {             // a small ball so a zero-length end still reads
  const s = new THREE.Mesh(
    new THREE.SphereGeometry(1, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0x6ee7ff, depthTest: false }));
  s.position.copy(p);
  s.renderOrder = 1000;
  return s;
}

export function showDimension(fromArr, toArr, label) {
  clearDimension();
  if (!fromArr || !toArr) return;
  const a = new THREE.Vector3(...fromArr), b = new THREE.Vector3(...toArr);
  const group = new THREE.Group();
  // depthTest off: a dimension between two faces runs THROUGH the solid, and a
  // line you cannot see is the same as no line at all
  group.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([a, b]),
    new THREE.LineBasicMaterial({ color: 0x6ee7ff, depthTest: false })));
  // scale the end balls to the part, so they read on a 4 mm boss and a 400 mm plate
  const r = Math.max(fitRadius / 160, 0.15);
  const e1 = dimEnd(a), e2 = dimEnd(b);
  e1.scale.setScalar(r); e2.scale.setScalar(r);
  group.add(e1, e2);
  group.renderOrder = 1000;
  scene.add(group);
  dimOverlay = { group, from: a, to: b, text: label || '',
                 line: group.children[0], e1 };
  paintDimLabel();
}

/* Move the grabbed end of the dimension NOW, before the kernel answers — the
   line must track the cursor at frame rate or the drag feels broken, whatever
   the round trip costs. The exact value and witness point overwrite this a
   couple of frames later. */
function nudgeDimFrom(p) {
  if (!dimOverlay || !dimOverlay.line) return;
  dimOverlay.from.copy(p);
  const attr = dimOverlay.line.geometry.getAttribute('position');
  attr.setXYZ(0, p.x, p.y, p.z);
  attr.needsUpdate = true;
  dimOverlay.e1.position.copy(p);
}

export function clearDimension() {
  if (!dimOverlay) return;
  scene.remove(dimOverlay.group);
  dimOverlay.group.traverse(o => { if (o.geometry) o.geometry.dispose(); });
  dimOverlay = null;
  const el = document.getElementById('dimLabel');
  if (el) el.style.display = 'none';
}

/* the label rides the midpoint every frame, so it stays put while orbiting */
function paintDimLabel() {
  const el = document.getElementById('dimLabel');
  if (!el) return;
  if (!dimOverlay || !dimOverlay.text) { el.style.display = 'none'; return; }
  const mid = dimOverlay.from.clone().add(dimOverlay.to).multiplyScalar(0.5);
  // behind the camera: project() flips the sign and the label would jump to
  // the opposite corner of the screen
  if (mid.clone().project(camera).z > 1) { el.style.display = 'none'; return; }
  const s = toScreen(mid);
  const r = renderer.domElement.getBoundingClientRect();
  // BESIDE the line, not on it: centred on the midpoint the label hid the very
  // line it measures (user report 2026-08-31). Offset perpendicular to the
  // line's on-screen direction, biased upward so the side is predictable.
  const a2 = toScreen(dimOverlay.from), b2 = toScreen(dimOverlay.to);
  let px = 0, py = -1;
  const dx = b2.x - a2.x, dy = b2.y - a2.y;
  const len = Math.hypot(dx, dy);
  if (len > 1) { px = -dy / len; py = dx / len; }
  if (py > 0) { px = -px; py = -py; }          // always the upper side
  el.textContent = dimOverlay.text;
  el.style.display = 'block';
  el.style.left = (s.x - r.left + px * 18) + 'px';
  el.style.top = (s.y - r.top + py * 18) + 'px';
}

/* ---------------- the draggable dimension (Measure probe) ----------------
   Between a slanted wall and a boss — or around a cylinder — the distance
   varies along the geometry, so the witness pair is one sample of many. When a
   probe target is set, GRABBING THE VALUE LABEL and dragging slides the sample
   point across the picked face; every position reports back through onPoint
   (Measure asks the kernel and repaints the line + live value). */

let dimProbe = null;             // { mesh, cb }

export function setDimProbe(target, onPoint) {
  clearDimProbe();
  if (!target || target.id == null) return false;
  const entry = bodyObjs.find(b => b.id === target.body) || bodyObjs[0];
  if (!entry) return false;
  const g = faceGeometry(entry.data, target.id);
  if (!g) return false;
  // an invisible raycast target holding ONLY the probed face's triangles, so
  // the drag cannot wander onto a neighbouring face and silently measure from
  // the wrong surface
  const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
    transparent: true, opacity: 0, depthWrite: false, colorWrite: false,
    side: THREE.DoubleSide }));
  scene.add(mesh);
  // The face's own triangles, for when the ray MISSES it: measuring a blade
  // gap, the cursor naturally rides the channel BETWEEN the blades, and a
  // drag that only works while the pointer covers a thin curved strip feels
  // stuck (user report 2026-08-31: "its not moving countinesly, kind of
  // strucking"). On a miss we snap to the nearest point on the face instead.
  const pa = g.getAttribute('position');
  const tris = [];
  for (let i = 0; i + 2 < pa.count; i += 3)
    tris.push(new THREE.Triangle(
      new THREE.Vector3().fromBufferAttribute(pa, i),
      new THREE.Vector3().fromBufferAttribute(pa, i + 1),
      new THREE.Vector3().fromBufferAttribute(pa, i + 2)));
  dimProbe = { mesh, tris, cb: onPoint, lastDist: null, frozen: false };
  const el = document.getElementById('dimLabel');
  if (el) { el.classList.add('grab'); el.title = 'drag to slide the measurement along the face'; }
  return true;
}

/* Freeze the zero-latency end-tracking while the probe is CLAMPED at a
   curve's limit (past the tangent the across ray misses; the line holds its
   last real crossing, so the local nudge must hold too or the grabbed dot
   runs away from its own line and snaps back every frame). */
export function setDimProbeFrozen(on) {
  if (dimProbe) dimProbe.frozen = !!on;
}

export function clearDimProbe() {
  if (!dimProbe) return;
  scene.remove(dimProbe.mesh);
  dimProbe.mesh.geometry.dispose();
  dimProbe = null;
  const el = document.getElementById('dimLabel');
  if (el) { el.classList.remove('grab', 'grabbing'); el.title = ''; }
}

function initDimDrag() {
  const lbl = document.getElementById('dimLabel');
  if (!lbl) return;
  lbl.addEventListener('pointerdown', e => {
    if (!dimProbe) return;
    e.preventDefault();
    e.stopPropagation();
    // same discipline as the gizmos: OrbitControls must never fight the drag
    controls.enabled = false;
    lbl.classList.add('grabbing');
    let queued = null, raf = 0;
    const tmp = new THREE.Vector3(), best = new THREE.Vector3();
    const step = () => {
      raf = 0;
      const ev = queued;
      queued = null;
      if (!ev || !dimProbe) return;
      raycaster.setFromCamera(ndcFrom(ev), camera);
      const hit = raycaster.intersectObject(dimProbe.mesh, false)[0];
      let p = null;
      if (hit) {
        p = hit.point;
        dimProbe.lastDist = hit.distance;
      } else if (dimProbe.tris.length && dimProbe.tris.length < 20000) {
        // the cursor left the face: sample the ray at the last hit depth and
        // snap to the nearest point ON the face, so the drag never freezes
        const depth = dimProbe.lastDist
          ?? camera.position.distanceTo(controls.target);
        const at = raycaster.ray.at(depth, new THREE.Vector3());
        let bd = Infinity;
        for (const t of dimProbe.tris) {
          t.closestPointToPoint(at, tmp);
          const d = tmp.distanceToSquared(at);
          if (d < bd) { bd = d; best.copy(tmp); }
        }
        if (bd < Infinity) p = best;
      }
      if (!p) return;
      if (!dimProbe.frozen)
        nudgeDimFrom(p);               // the line tracks the cursor NOW
      // the kernel is still asked while frozen — it is how we notice the
      // cursor coming back into range and unfreeze
      if (dimProbe.cb) dimProbe.cb([p.x, p.y, p.z]);
    };
    // one raycast per FRAME, not per pointermove — a gaming mouse fires
    // hundreds of moves a second and queueing them all is its own lag
    const move = ev => {
      queued = ev;
      if (!raf) raf = requestAnimationFrame(step);
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      if (raf) cancelAnimationFrame(raf);
      controls.enabled = true;
      lbl.classList.remove('grabbing');
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  });
}

/* ---------------- face / edge picking ---------------- */

function clearPickHighlight() {
  if (pickHl) { scene.remove(pickHl); pickHl.geometry.dispose(); pickHl = null; }
}
/* exported: clicking a TREE row replaces the viewport selection (one selection
   set, like Fusion) — otherwise a stale face pick silently outranks the tree
   sketch the user just clicked when a select-then-command tool opens */
export function clearPick() {
  clearPickHighlight();
  S.pickedFace = null;
  S.pickedCurved = null;
  S.pickedProfile = null;
  S.pickedEdge = null;
  document.getElementById('pickInfo').style.display = 'none';
  bus.emit('pick', { kind: null, clear: true });
}

/* How much model one screen pixel covers at a given depth (perspective). */
function worldPerPixel(dist) {
  const rect = renderer.domElement.getBoundingClientRect();
  const h = Math.max(rect.height, 1);
  return 2 * dist * Math.tan((camera.fov * Math.PI / 180) / 2) / h;
}

// how close to an edge (IN PIXELS) a click has to be to mean the edge
const EDGE_PICK_PX = 5;

function pickAt(e) {
  if (!bodyObjs.length && !sketchMeshes().length) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);

  // ALL bodies are pickable, not just the displayed result
  const fHit = raycaster.intersectObjects(bodyMeshes(), false)[0];
  // The edge halo must be a SCREEN distance, not a model distance. It was
  // fitRadius/60 — about 1.9 mm on a 220 mm part — so every face smaller than
  // ~4 mm across sat entirely inside the halo of its own rim and could never
  // be clicked: the edge always won. That is why the top of a pillar "got
  // never selected" (user report 2026-08-26). Five pixels means five pixels,
  // whatever the part's size or the zoom.
  const depth = fHit ? fHit.distance
                     : camera.position.distanceTo(controls.target);
  raycaster.params.Line.threshold = worldPerPixel(depth) * EDGE_PICK_PX;
  const eHits = raycaster.intersectObjects(edgeLines, false);
  // a SKETCH PROFILE drawn on a face is COPLANAR with it — on a tie the
  // profile wins, or the rectangle you just sketched could never be picked
  // (clicking it always selected the whole face underneath)
  const sHit = raycaster.intersectObjects(sketchMeshes(), false)[0];
  if (sHit && (!fHit || sHit.distance <= fHit.distance + 0.5)
      && (!eHits.length || sHit.distance <= eHits[0].distance + 0.5)) {
    selectProfile(sHit.object.userData.sketchId, sHit.object);
    return;
  }
  if (eHits.length && (!fHit || eHits[0].distance <= fHit.distance + 1e-3)) {
    selectEdge(eHits[0].object.userData.edgeId,
               eHits[0].object.userData.body);
  } else if (fHit) {
    const entry = bodyObjs.find(b => b.mesh === fHit.object);
    // the raycast hit point rides along: it is the best possible interior
    // sample for asking WHICH FEATURE made this face (provenance.js)
    if (entry) selectFace(entry.data.faceId[fHit.face.a], entry, fHit.point);
  }
}

/* a finished sketch is a first-class selectable PROFILE (Fusion): picking it
   remembers it for select-then-command tools (Extrude uses it directly) */
function selectProfile(sketchId, meshObj) {
  clearPickHighlight();
  bus.emit('face-picked', { clear: true });   // ...same for a profile pick
  S.pickedFace = null;
  S.pickedCurved = null;
  S.pickedEdge = null;
  S.pickedProfile = { id: sketchId };
  bus.emit('pick', { kind: 'profile', id: sketchId, body: null, info: null });
  pickHl = new THREE.Mesh(meshObj.geometry.clone(),
    new THREE.MeshBasicMaterial({ color: 0xffb85c, transparent: true,
      opacity: 0.55, side: THREE.DoubleSide, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: -4 }));
  pickHl.renderOrder = 999;
  scene.add(pickHl);
  showPick(`<b>Sketch profile</b> — ${sketchId}`,
    [['feature', sketchId]]);
  const note = document.createElement('div');
  note.style.cssText = 'margin-top:7px;color:var(--dim);font-size:11px;line-height:1.4';
  note.textContent = 'Press Extrude to pull this profile.';
  document.getElementById('pickInfo').appendChild(note);
}

/* The triangles of ONE face, as its own geometry. Factored out of selectFace so
   the Measure overlay can light up two faces at once without duplicating the
   faceId walk. */
function faceGeometry(m, fid) {
  if (!m) return null;
  const pos = m.positions, keep = [];
  for (let t = 0; t < m.indices.length; t += 3) {
    const a = m.indices[t];
    if (m.faceId[a] === fid)
      for (const vi of [m.indices[t], m.indices[t + 1], m.indices[t + 2]])
        keep.push(pos[vi * 3], pos[vi * 3 + 1], pos[vi * 3 + 2]);
  }
  if (!keep.length) return null;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(keep, 3));
  g.computeVertexNormals();
  return g;
}

function selectFace(fid, entry = null, hitPoint = null) {
  clearPickHighlight();
  const m = (entry ? entry.data : MODEL);
  if (!m) return;
  const g = faceGeometry(m, fid);
  // A tool that owns the highlighting (Measure paints its own A and B) turns
  // this off, so the two do not fight over the same face with two colours.
  if (g && !pickHlOff) {
    pickHl = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
      color: 0xffb85c, emissive: 0x8a5a1a, side: THREE.DoubleSide,
      transparent: true, opacity: 0.75, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: -3 }));
    scene.add(pickHl);
  }
  const info = m.faces.find(f => f.id === fid) || {};
  // FLAT is decided geometrically (info.planar), NOT by surface type — a taper/
  // loft wall can be dead flat yet typed BSPLINE, and must still be sketchable.
  // a genuinely CURVED pick is remembered separately so tools can explain it.
  const isFlat = info.planar ?? (info.type === 'PLANE');
  const point = hitPoint ? [hitPoint.x, hitPoint.y, hitPoint.z] : null;
  // the pick carries WHERE the face was clicked — Hole's centre; the tool's
  // plan turns it into the face's own coordinates, nothing is computed here
  S.pickedFace = (info.center && isFlat) ? { ...info, point } : null;
  S.pickedCurved = (info.center && !isFlat)
    ? { ...info, body: info.body || (entry ? entry.id : null), point } : null;
  S.pickedProfile = null;              // a face pick replaces a profile pick
  S.pickedEdge = null;
  // 'pick' is the RAW selection event, for tools that need the identity of
  // whatever was clicked (Measure). 'face-picked' below stays face-only
  // because provenance asks a face-shaped question.
  bus.emit('pick', { kind: 'face', id: fid,
                     body: info.body || (entry ? entry.id : null), info });
  // DIAMETERS FIRST — a machinist reads round things as ⌀, and the user asked
  // for exactly this (2026-08-31: "when i am selecting that face, i can simply
  // see the inner dia and outer dia"). A cylindrical wall has one; a planar
  // face reports its full circular boundaries (an annular face: outer + inner).
  const dia = [];
  if (info.radius != null)
    dia.push(['⌀', (info.radius * 2).toFixed(2) + ' mm']);
  // every surface type reads out its own dimensions (2026-08-31: "for a
  // selected box surface show the length and width, if i am selecting a
  // curve show the radius or dia like that")
  if (info.cone_d)
    dia.push(['⌀', `${info.cone_d[0].toFixed(2)} → ${info.cone_d[1].toFixed(2)} mm`],
             ['taper', info.cone_angle + '° per side']);
  if (info.torus)
    dia.push(['ring ⌀', (info.torus[0] * 2).toFixed(2) + ' mm'],
             ['tube ⌀', (info.torus[1] * 2).toFixed(2) + ' mm']);
  if (info.height != null)
    dia.push(['height', info.height.toFixed(2) + ' mm']);
  if (info.extents)
    dia.push(['size', `${info.extents[0].toFixed(2)} × ` +
                      `${info.extents[1].toFixed(2)} mm`]);
  const circ = (info.circles || []).filter(r =>
    info.radius == null || Math.abs(r - info.radius) > 1e-3);
  if (circ.length === 1)
    dia.push(['⌀', (circ[0] * 2).toFixed(2) + ' mm']);
  else if (circ.length >= 2) {
    dia.push(['outer ⌀', (circ[0] * 2).toFixed(2) + ' mm'],
             ['inner ⌀', (circ[circ.length - 1] * 2).toFixed(2) + ' mm']);
    if (circ.length > 2)     // e.g. a floor with several different holes
      dia.push(['also ⌀', circ.slice(1, -1)
        .map(r => (r * 2).toFixed(1)).join(', ') + ' mm']);
  }
  showPick(`<b>Face ${fid}</b> — ${isFlat && info.type !== 'PLANE' ? info.type + ' (flat)' : info.type}`,
    [// which BODY this face belongs to — but ONLY when several are on screen
     // and the answer is not obvious; with one body it is noise (user request
     // 2026-08-31: "we dont need to mentions body")
     info.body && bodyObjs.length > 1 ? ['body', info.body] : null,
     ...dia,
     ['area', (info.area ?? '?') + ' mm²'],
     info.center ? ['center', info.center.join(', ')] : null]);
  // ask WHO MADE THIS FACE (provenance.js listens) — a face pick is how the
  // user navigates an AI-authored tree they did not build themselves
  bus.emit('face-picked', {
    body: info.body || (entry ? entry.id : null),
    face: fid,
    center: info.center || null,
    area: info.area ?? null,
    point,
  });
  if (info.center && isFlat) {                  // sketching needs a FLAT face
    const btn = document.createElement('button');
    btn.textContent = '✎ Sketch on this face';
    btn.style.cssText = 'margin-top:7px;width:100%;background:var(--accent);' +
      'color:#08111e;border:none;border-radius:6px;padding:6px;cursor:pointer;' +
      'font:inherit;font-weight:700';
    btn.onclick = () => bus.emit('sketch-on-face', info);
    document.getElementById('pickInfo').appendChild(btn);
  } else if (info.center) {
    const note = document.createElement('div');
    note.style.cssText = 'margin-top:7px;color:var(--dim);font-size:11px;line-height:1.4';
    note.textContent = `Sketching needs a FLAT face — this one is ${info.type}. ` +
      'For a slot/pocket here: sketch on a plane at the right offset, extrude, then Cut.';
    document.getElementById('pickInfo').appendChild(note);
  }
}

/* bodyId comes from the picked LINE's userData — edge ids restart per body, so
   'edge 3' is ambiguous without it */
function selectEdge(eid, bodyId = null) {
  clearPickHighlight();
  bus.emit('face-picked', { clear: true });   // drop the face's "created by"
  S.pickedFace = null;                 // an edge pick is not a sketchable face
  S.pickedCurved = null;
  S.pickedProfile = null;
  S.pickedEdge = null;
  const src = bodyObjs.find(b => b.id === bodyId)
    || bodyObjs.find(b => b.result) || bodyObjs[0];
  const e = src && (src.data.edges || []).find(x => x.id === eid);
  if (!e) return;
  // remembered for select-then-command (Fillet / Chamfer read it), as drawn
  S.pickedEdge = { id: eid, body: src ? src.id : null, info: e };
  const g = new THREE.BufferGeometry().setFromPoints(
    e.points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
  pickHl = new THREE.Line(g, new THREE.LineBasicMaterial({
    color: 0xffb85c, linewidth: 3, depthTest: false }));
  pickHl.renderOrder = 999;
  scene.add(pickHl);
  bus.emit('pick', { kind: 'edge', id: eid, body: src ? src.id : null, info: e });
  // a round edge reads out as a DIAMETER, because that is how a machinist
  // reads a bore — the radius/arc_center ride along in the mesh payload
  const dia = e.radius != null
    ? [['diameter', `⌀${(e.radius * 2).toFixed(2)} mm`],
       ['radius', e.radius.toFixed(2) + ' mm']]
    : [];
  showPick(`<b>Edge ${eid}</b> — ${e.type}`,
    [src && bodyObjs.length > 1 ? ['body', src.id] : null,
     ...dia,
     ['length', e.length + ' mm']]);
}

function showPick(title, rows) {
  const el = document.getElementById('pickInfo');
  el.innerHTML = title + rows.filter(Boolean)
    .map(r => `<br><span class="k">${r[0]}:</span> ${r[1]}`).join('');
  el.style.display = 'block';
}
