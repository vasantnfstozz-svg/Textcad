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
    gizmos: () => ({ arrow: !!exArrow, ghost: !!exGhost, ring: !!taperRing }),
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
    if (profilePickCb) { profilePickAt(e); return; }
    if (planePickCb) { planePickAt(e); return; }
    if (placeCb) { placeGround(e); return; }
    if (pickMode) pickAt(e);
  });
  renderer.domElement.addEventListener('pointermove', e => {
    if (planePickCb) planePickHover(e);
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
  bus.on('doc-updated', () => {
    if (planePickCb) endPlanePick();
    if (profilePickCb) cancelProfilePick();
  });

  // Extrude gizmo drags (arrow + taper ring) — capture phase so we grab them
  // BEFORE OrbitControls, then disable orbit for the drag. Move/up on window
  // so the drag survives the pointer leaving the canvas.
  renderer.domElement.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;            // a right/middle drag must still
                                           // navigate, even starting ON a gizmo
    if (exArrow && !exArrow.dragging && arrowGrab(e)) { e.stopPropagation(); return; }
    if (taperRing && !taperRing.dragging && taperGrab(e)) e.stopPropagation();
  }, true);
  window.addEventListener('pointermove', e => {
    if (exArrow && exArrow.dragging) arrowDrag(e);
    else if (taperRing && taperRing.dragging) taperDrag(e);
  });
  window.addEventListener('pointerup', e => {
    if (exArrow && exArrow.dragging) arrowRelease(e);
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

export function beginProfilePick(onPick) {
  profilePickCb = onPick;
  renderer.domElement.style.cursor = 'crosshair';
  const h = document.getElementById('placeHint');
  h.textContent = 'Select a sketch profile or a flat face to extrude · Esc to cancel';
  h.style.display = 'block';
}

export function cancelProfilePick() {
  if (!profilePickCb) return;
  profilePickCb = null;
  renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  document.getElementById('placeHint').style.display = 'none';
}

function profilePickAt(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const sHit = raycaster.intersectObjects(sketchMeshes(), false)[0];
  const fHit = raycaster.intersectObjects(bodyMeshes(), false)[0];
  const cb = profilePickCb;
  // coplanar tie: the profile drawn ON the face wins, same rule as pickAt
  if (sHit && (!fHit || sHit.distance <= fHit.distance + 0.5)) {
    cancelProfilePick(); cb('profile', sHit.object.userData.sketchId); return;
  }
  if (fHit) {
    const entry = bodyObjs.find(b => b.mesh === fHit.object);
    const fid = entry && entry.data.faceId[fHit.face.a];
    const info = entry && entry.data.faces.find(f => f.id === fid);
    const flat = info && (info.planar ?? (info.type === 'PLANE'));
    if (info && flat && info.center) {
      cancelProfilePick(); cb('face', info); return;
    }
    if (info) {
      bus.emit('msg', 'bot', `⚠ That face is ${info.type} (curved) — Extrude ` +
        'needs a sketch profile or a FLAT face. Keep picking, or Esc.');
      return;
    }
  }
  // clicked empty space — keep waiting (don't cancel)
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
  exArrow = { arrow, hit, O, N, amount: Number(amount) || 0, len, onChange,
              onCommit, clampFn, dragging: false, grab: 0 };
  updateArrow();
}

export function endExtrudeArrow() {
  if (!exArrow) return;
  scene.remove(exArrow.arrow); scene.remove(exArrow.hit);
  exArrow.hit.geometry.dispose();
  exArrow = null;
}

export function hasExtrudeArrow() { return !!exArrow; }

/* ---------------- extrude GHOST (instant drag preview) ----------------
   While dragging, a translucent white prism in the TRUE SHAPE of the profile
   (outer outline + holes — a circle face gives a circular ghost) shows where
   the material will go — no geometry rebuild per frame. The REAL verified
   extrude builds once on release. frame = {origin, x_dir, y_dir, z_dir};
   loops = [{outer: [[x,y],…], holes: [[[x,y],…],…]}, …] in plane-local coords. */
let exGhost = null;

export function beginExtrudeGhost(frame, loops) {
  endExtrudeGhost();
  const shapes = [];
  for (const L of loops || []) {
    if (!L.outer || L.outer.length < 3) continue;
    const s = new THREE.Shape(L.outer.map(p => new THREE.Vector2(p[0], p[1])));
    for (const h of L.holes || [])
      if (h.length >= 3) s.holes.push(new THREE.Path(h.map(p => new THREE.Vector2(p[0], p[1]))));
    shapes.push(s);
  }
  if (!shapes.length) return;
  // unit-depth prism of the real profile; drags scale it along the normal
  const geo = new THREE.ExtrudeGeometry(shapes, { depth: 1, bevelEnabled: false });
  // depthTest OFF: the ghost must stay visible when pushed INSIDE the body
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0.13, depthWrite: false,
    depthTest: false, side: THREE.DoubleSide }));
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 15),
    new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true,
      opacity: 0.65, depthTest: false }));
  mesh.renderOrder = 990; edges.renderOrder = 991;
  mesh.matrixAutoUpdate = false; edges.matrixAutoUpdate = false;
  scene.add(mesh); scene.add(edges);
  // centroid + mean radius of the profile (for the taper morph)
  let cx = 0, cy = 0, np = 0;
  for (const L of loops) for (const p of L.outer) { cx += p[0]; cy += p[1]; np++; }
  cx /= np || 1; cy /= np || 1;
  let mr = 0;
  for (const L of loops) for (const p of L.outer)
    mr += Math.hypot(p[0] - cx, p[1] - cy);
  mr = Math.max(mr / (np || 1), 0.5);
  exGhost = {
    mesh, edges, cx, cy, meanR: mr, lastTaper: null, lastAmount: null,
    basePos: Float32Array.from(geo.attributes.position.array),
    x: new THREE.Vector3(...frame.x_dir), y: new THREE.Vector3(...frame.y_dir),
    z: new THREE.Vector3(...frame.z_dir), o: new THREE.Vector3(...frame.origin),
  };
  ghostVisible(false);
}

export function setExtrudeGhost(amount, taper = 0) {
  if (!exGhost) return;
  ghostVisible(true);
  const d = Math.abs(amount) < 0.01 ? 0.01 : amount;   // keep non-degenerate
  // taper morph: shrink cross-sections toward the profile centroid with height
  // (approximate — the ghost is a drag aid; the real solid is exact)
  if (exGhost.basePos && (taper !== exGhost.lastTaper || amount !== exGhost.lastAmount)) {
    const pos = exGhost.mesh.geometry.attributes.position;
    const base = exGhost.basePos;
    const k = Math.tan((taper || 0) * Math.PI / 180) * Math.abs(d) / exGhost.meanR;
    for (let i = 0; i < pos.count; i++) {
      const x = base[i * 3], y = base[i * 3 + 1], z = base[i * 3 + 2];
      const s = Math.max(1 - k * z, 0.03);
      pos.setXYZ(i, exGhost.cx + (x - exGhost.cx) * s,
                    exGhost.cy + (y - exGhost.cy) * s, z);
    }
    pos.needsUpdate = true;
    exGhost.lastTaper = taper; exGhost.lastAmount = amount;
  }
  const m = new THREE.Matrix4().makeBasis(exGhost.x, exGhost.y, exGhost.z)
    .scale(new THREE.Vector3(1, 1, d))
    .setPosition(exGhost.o);
  exGhost.mesh.matrix.copy(m);
  exGhost.edges.matrix.copy(m);
}

function ghostVisible(v) {
  if (exGhost) { exGhost.mesh.visible = v; exGhost.edges.visible = v; }
}
export function hideExtrudeGhost() { ghostVisible(false); }
export function hasExtrudeGhostVisible() { return !!(exGhost && exGhost.mesh.visible); }

export function endExtrudeGhost() {
  if (!exGhost) return;
  scene.remove(exGhost.mesh); scene.remove(exGhost.edges);
  exGhost.mesh.geometry.dispose(); exGhost.edges.geometry.dispose();
  exGhost = null;
}

/* ---------------- taper RING (Fusion's dashed circle + handle) -------------
   A dashed circle in the profile plane with a round handle; dragging the
   handle around the ring changes the taper angle (± around zero). Same ghost
   protocol as the arrow: drag = ghost only, release = one verified rebuild. */
let taperRing = null;

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
                taper: taper0 || 0, onChange, onCommit, clampFn,
                dragging: false, grabOff: 0 };
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
  taperRing.grabOff = taperRing.taper - taperAngleAt(e);
  return true;
}

function taperDrag(e) {
  let t = taperAngleAt(e) + taperRing.grabOff;
  while (t > 180) t -= 360;
  while (t < -180) t += 360;
  t = Math.max(-60, Math.min(60, t));
  if (taperRing.clampFn) t = taperRing.clampFn(t);   // barrier (wall collapse)
  taperRing.taper = t;
  taperRingPlace();
  taperRing.onChange(taperRing.taper);
}

function taperRelease() {
  taperRing.dragging = false;
  controls.enabled = true;
  taperRing.onCommit(taperRing.taper);
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
  if (exArrow && !exArrow.dragging) { exArrow.amount = a; updateArrow(); }
}

function toScreen(p) {
  const v = p.clone().project(camera);
  const r = renderer.domElement.getBoundingClientRect();
  return { x: r.left + (v.x * 0.5 + 0.5) * r.width,
           y: r.top + (-v.y * 0.5 + 0.5) * r.height };
}

/* the arrow's pointing direction — always a COPY: multiplying a reference to
   exArrow.N would scale the stored normal and corrupt every later calculation. */
function arrowDir() {
  const d = exArrow.N.clone();
  return exArrow.amount >= 0 ? d : d.negate();
}
function arrowBase() {
  return exArrow.O.clone().add(exArrow.N.clone().multiplyScalar(exArrow.amount));
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

function updateArrow() {
  const len = exArrow.len;
  const dir = arrowDir();                        // copy — never mutate N
  const base = arrowBase();
  const head = len * 0.42;                       // big, easy-to-see head
  exArrow.arrow.position.copy(base);
  exArrow.arrow.setDirection(dir);
  exArrow.arrow.setLength(len, head, head * 0.62);
  const mid = base.clone().add(dir.clone().multiplyScalar(len / 2));
  exArrow.hit.position.copy(mid);
  exArrow.hit.scale.set(1, len * 1.2, 1);        // grab a bit beyond the tip
  exArrow.hit.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
}

/* signed distance along the axis (O + s·N) nearest to the pointer ray */
function projectAmount(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const rp = raycaster.ray.origin, rd = raycaster.ray.direction;
  const r = new THREE.Vector3().subVectors(exArrow.O, rp);
  const b = exArrow.N.dot(rd), c = rd.dot(rd);
  const d = exArrow.N.dot(r), ee = rd.dot(r);
  const denom = c - b * b;                        // a = N·N = 1
  if (Math.abs(denom) < 1e-6) return exArrow.amount;
  return (b * ee - c * d) / denom;
}

/* pixels of screen movement per 1mm along the extrude axis. When the axis is
   nearly head-on to the camera this collapses, so we fall back to the ray
   method — otherwise dragging follows the arrow's ON-SCREEN direction, which is
   what makes a gizmo feel predictable. */
function axisScreenVector() {
  const a = exArrow.amount;
  const p0 = toScreen(exArrow.O.clone().add(exArrow.N.clone().multiplyScalar(a)));
  const p1 = toScreen(exArrow.O.clone().add(exArrow.N.clone().multiplyScalar(a + 1)));
  return { x: p1.x - p0.x, y: p1.y - p0.y };
}

function arrowGrab(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  if (!raycaster.intersectObject(exArrow.hit, false).length) return false;
  exArrow.dragging = true;
  controls.enabled = false;
  const v = axisScreenVector();
  const len2 = v.x * v.x + v.y * v.y;
  if (len2 > 4) {                        // >2px per mm — screen-space drag
    exArrow.mode = 'screen';
    exArrow.axis2D = v; exArrow.axisLen2 = len2;
    exArrow.startAmount = exArrow.amount;
    exArrow.startXY = { x: e.clientX, y: e.clientY };
  } else {                               // axis points at the camera — use the ray
    exArrow.mode = 'ray';
    exArrow.grab = exArrow.amount - projectAmount(e);
  }
  return true;
}

function arrowDrag(e) {
  let a;
  if (exArrow.mode === 'screen') {
    const dx = e.clientX - exArrow.startXY.x, dy = e.clientY - exArrow.startXY.y;
    const along = (dx * exArrow.axis2D.x + dy * exArrow.axis2D.y) / exArrow.axisLen2;
    a = exArrow.startAmount + along;
  } else {
    a = projectAmount(e) + exArrow.grab;
  }
  if (exArrow.clampFn) a = exArrow.clampFn(a);   // barrier (e.g. taper collapse)
  exArrow.amount = a;
  updateArrow();
  exArrow.onChange(exArrow.amount);
}

function arrowRelease() {
  exArrow.dragging = false;
  controls.enabled = true;
  exArrow.onCommit(exArrow.amount);
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

/* Re-fetching and re-rendering the model is the most expensive thing the UI
   does (megabytes of triangles, plus a full three.js scene rebuild). Most calls
   ask for geometry that is already on screen — finishing or cancelling a sketch
   without changing anything, undoing back to the same state, switching tools.
   The document carries a geometry fingerprint, so those cost nothing now.
   `force` bypasses it for callers that must reload (imports, tab switches). */
export async function loadMesh(fit = false, force = false) {
  const mine = ++loadSeq;
  const version = S.lastDoc && S.lastDoc.geom_version;
  if (!force && version && version === drawnVersion && bodyObjs.length) {
    clearHighlight(); clearPick();
    if (fit) { camera.updateProjectionMatrix(); setView('iso'); }
    return;
  }
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
  S.pickedFace = (info.center && isFlat) ? info : null;
  S.pickedCurved = (info.center && !isFlat) ? info : null;
  S.pickedProfile = null;              // a face pick replaces a profile pick
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
    point: hitPoint ? [hitPoint.x, hitPoint.y, hitPoint.z] : null,
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
  const src = bodyObjs.find(b => b.id === bodyId)
    || bodyObjs.find(b => b.result) || bodyObjs[0];
  const e = src && (src.data.edges || []).find(x => x.id === eid);
  if (!e) return;
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
