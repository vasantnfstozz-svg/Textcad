// viewport.js — the 3D view: scene, camera, model loading (face-tagged mesh
// from /api/model), view buttons, and face/edge picking with the info panel.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { bus } from './bus.js';
import { S } from './state.js';
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
let pickMode = false;
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
   in both — a fallback for mice whose wheel-press drag is awkward, since pan
   otherwise lives only on the middle button. OrbitControls reads mouseButtons
   at pointerdown, so flipping it on the Shift keydown is enough. */
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
     Now RIGHT-drag orbits, MIDDLE-drag pans and the wheel zooms EVERYWHERE;
     sketch mode only takes LEFT away (it draws). Fusion never orbits with the
     left button either — it selects, and orbit is Shift+middle — but the
     design tab deliberately KEEPS left-drag orbit (user's call) since nothing
     else needs left there. */
  leftBase = THREE.MOUSE.ROTATE;        // design default; sketch mode frees it
  controls.mouseButtons = { LEFT: leftBase,
                            MIDDLE: THREE.MOUSE.PAN,
                            RIGHT: THREE.MOUSE.ROTATE };
  applyLeftButton();                    // a rebuild must not drop Shift-pan
  // never dolly past the far clip plane — beyond it the whole scene (model,
  // grids, everything) is clipped to a black void that reads as a crash
  controls.maxDistance = camera.far * 0.85;
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

  scene.add(new THREE.HemisphereLight(0xffffff, 0x223, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.5);
  key.position.set(1, -1, 2); scene.add(key);
  const rim = new THREE.DirectionalLight(0x88bbff, 0.5);
  rim.position.set(-2, 2, -1); scene.add(rim);
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
    getFit: () => ({ r: fitRadius, c: fitCenter.toArray() }),
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
    /* how many of each thing is actually in the scene — catches duplicate
       objects piling up from overlapping loads */
    sceneCounts: () => ({ bodies: bodyObjs.length, edges: edgeLines.length,
                          sketchObjs: sketchObjs.length,
                          sceneChildren: scene.children.length }),
    /* raycast at a WORLD point (e.g. a face centre) as if the user clicked
       there, and report what got picked — deterministic, no screen maths */
    pickAtWorld: (world) => {
      const rect = renderer.domElement.getBoundingClientRect();
      const v = new THREE.Vector3(...world).project(camera);
      pickAt({ clientX: rect.left + (v.x + 1) / 2 * rect.width,
               clientY: rect.top + (1 - (v.y + 1) / 2) * rect.height });
      return S.pickedFace || S.pickedCurved || null;
    },
  };

  (function animate() { requestAnimationFrame(animate);
    controls.update(); renderer.render(scene, camera); })();

  document.getElementById('vFit').onclick = () => setView('iso');
  document.getElementById('vTop').onclick = () => setView('top');
  document.getElementById('vFront').onclick = () => setView('front');
  document.getElementById('vIso').onclick = () => setView('iso');
  document.getElementById('vSelect').onclick = e => {
    pickMode = !pickMode;
    e.target.classList.toggle('on', pickMode);
    renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
    if (!pickMode) clearPick();
  };

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

function planePickHover(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const quads = originPlanes.filter(o => o.userData.plane);
  for (const q of quads) q.material.opacity = q.userData.base;
  renderer.domElement.style.cursor = 'pointer';
  if (raycaster.intersectObjects(bodyMeshes(), false).length) {
    renderer.domElement.style.cursor = 'crosshair';   // a face will be picked
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
    const entry = bodyObjs.find(b => b.mesh === fHit.object);
    const fid = entry && entry.data.faceId[fHit.face.a];
    const info = entry && entry.data.faces.find(f => f.id === fid);
    if (info && info.type === 'PLANE' && info.center) {
      endPlanePick(); cb('face', info); return;
    }
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
  exArrow = { arrow, hit, O, N, amount: amount || 1, len, onChange, onCommit,
              clampFn, dragging: false, grab: 0 };
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
      color: 0x5ba7f7, metalness: 0.25, roughness: 0.42 }));
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
      const line = new THREE.Line(eg, new THREE.LineBasicMaterial({
        color: 0x0c2a4a, transparent: true, opacity: 0.55 }));
      line.userData.edgeId = e.id;
      line.userData.body = b.id;
      scene.add(line); edgeLines.push(line);
    }
  }
}

function bodyMeshes() { return bodyObjs.map(b => b.mesh); }

function addSketches(sketches) {
  for (const s of sketches || []) {
    if (s.positions.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position',
        new THREE.Float32BufferAttribute(s.positions, 3));
      g.setIndex(s.indices);
      g.computeVertexNormals();
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
        color: 0x43c579, transparent: true, opacity: 0.18,
        side: THREE.DoubleSide, depthWrite: false }));
      m.userData.sketchId = s.id;      // profiles are PICKABLE (Fusion)
      scene.add(m); sketchObjs.push(m);
    }
    for (const line of s.outlines || []) {
      const g = new THREE.BufferGeometry().setFromPoints(
        line.map(p => new THREE.Vector3(p[0], p[1], p[2])));
      const l = new THREE.Line(g, new THREE.LineBasicMaterial({
        color: 0x43c579 }));
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

export async function loadMesh(fit = false) {
  const mine = ++loadSeq;
  clearHighlight(); clearPick();
  try {
    const m = await (await fetch('/api/model?t=' + Date.now())).json();
    if (mine !== loadSeq) return;          // a newer load started meanwhile
    disposeModel();
    MODEL = null;
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
      camera.updateProjectionMatrix(); setView('iso');
    }
  } catch (e) { /* no model yet */ }
}

export function clearMesh() {
  disposeModel(); MODEL = null; S.selected = null; clearHighlight();
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
  camera.updateProjectionMatrix(); setView('iso');
}

/* ---------------- feature overlay (tree row click) ---------------- */

export function clearHighlight() {
  if (hlMesh) { scene.remove(hlMesh); hlMesh.geometry.dispose(); hlMesh = null; }
}

export async function showFeatureOverlay(fid) {
  clearHighlight();
  try {
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

/* ---------------- face / edge picking ---------------- */

function clearPickHighlight() {
  if (pickHl) { scene.remove(pickHl); pickHl.geometry.dispose(); pickHl = null; }
}
function clearPick() {
  clearPickHighlight();
  S.pickedFace = null;
  S.pickedCurved = null;
  S.pickedProfile = null;
  document.getElementById('pickInfo').style.display = 'none';
}

function pickAt(e) {
  if (!bodyObjs.length && !sketchMeshes().length) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  raycaster.params.Line.threshold = fitRadius / 60;

  const eHits = raycaster.intersectObjects(edgeLines, false);
  // ALL bodies are pickable, not just the displayed result
  const fHit = raycaster.intersectObjects(bodyMeshes(), false)[0];
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
    if (entry) selectFace(entry.data.faceId[fHit.face.a], entry);
  }
}

/* a finished sketch is a first-class selectable PROFILE (Fusion): picking it
   remembers it for select-then-command tools (Extrude uses it directly) */
function selectProfile(sketchId, meshObj) {
  clearPickHighlight();
  S.pickedFace = null;
  S.pickedCurved = null;
  S.pickedProfile = { id: sketchId };
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

function selectFace(fid, entry = null) {
  clearPickHighlight();
  const m = (entry ? entry.data : MODEL);
  if (!m) return;
  const pos = m.positions, keep = [];
  for (let t = 0; t < m.indices.length; t += 3) {
    const a = m.indices[t];
    if (m.faceId[a] === fid)
      for (const vi of [m.indices[t], m.indices[t + 1], m.indices[t + 2]])
        keep.push(pos[vi * 3], pos[vi * 3 + 1], pos[vi * 3 + 2]);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(keep, 3));
  g.computeVertexNormals();
  pickHl = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
    color: 0xffb85c, emissive: 0x8a5a1a, side: THREE.DoubleSide,
    transparent: true, opacity: 0.75, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -3 }));
  scene.add(pickHl);
  const info = m.faces.find(f => f.id === fid) || {};
  // FLAT is decided geometrically (info.planar), NOT by surface type — a taper/
  // loft wall can be dead flat yet typed BSPLINE, and must still be sketchable.
  // a genuinely CURVED pick is remembered separately so tools can explain it.
  const isFlat = info.planar ?? (info.type === 'PLANE');
  S.pickedFace = (info.center && isFlat) ? info : null;
  S.pickedCurved = (info.center && !isFlat) ? info : null;
  S.pickedProfile = null;              // a face pick replaces a profile pick
  showPick(`<b>Face ${fid}</b> — ${isFlat && info.type !== 'PLANE' ? info.type + ' (flat)' : info.type}`,
    [// which BODY this face belongs to — several are pickable now, and the
     // tools act on the picked one, so the user must see which it is
     info.body ? ['body', info.body] : null,
     ['area', (info.area ?? '?') + ' mm²'],
     info.radius != null ? ['radius', info.radius + ' mm'] : null,
     info.center ? ['center', info.center.join(', ')] : null]);
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
  showPick(`<b>Edge ${eid}</b> — ${e.type}`,
    [src && bodyObjs.length > 1 ? ['body', src.id] : null,
     ['length', e.length + ' mm']]);
}

function showPick(title, rows) {
  const el = document.getElementById('pickInfo');
  el.innerHTML = title + rows.filter(Boolean)
    .map(r => `<br><span class="k">${r[0]}:</span> ${r[1]}`).join('');
  el.style.display = 'block';
}
