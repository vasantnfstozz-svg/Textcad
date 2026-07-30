// viewport.js — the 3D view: scene, camera, model loading (face-tagged mesh
// from /api/model), view buttons, and face/edge picking with the info panel.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { bus } from './bus.js';
import { S } from './state.js';

let scene, camera, renderer, controls;
let groundGrid = null;           // the XY GridHelper (hidden while sketching)
let sketchCam = null;            // ortho camera while sketch-view is active
let sketchFrame = null;          // {o,x,y,z} basis of the active sketch plane
let mesh = null;                 // the body
const edgeLines = [];            // crisp OCCT topology edges
const sketchObjs = [];           // floating 2D sketch profiles (Fusion-style)
const ghostObjs = [];            // other unconsumed solid bodies (translucent)
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

export function initViewport() {
  const pane = document.getElementById('viewer');
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f1115);
  camera = new THREE.PerspectiveCamera(50, 1, 0.1, 8000);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  pane.appendChild(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.12;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x223, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.5);
  key.position.set(1, -1, 2); scene.add(key);
  const rim = new THREE.DirectionalLight(0x88bbff, 0.5);
  rim.position.set(-2, 2, -1); scene.add(rim);
  groundGrid = new THREE.GridHelper(400, 40, 0x2b303c, 0x1b1f28);
  groundGrid.rotation.x = Math.PI / 2; scene.add(groundGrid);

  const resize = () => {
    camera.aspect = pane.clientWidth / pane.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(pane.clientWidth, pane.clientHeight);
  };
  new ResizeObserver(resize).observe(pane);
  (function animate() { requestAnimationFrame(animate);
    controls.update(); renderer.render(scene, sketchCam || camera); })();

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
    if (moved > 5) return;                 // that was an orbit-drag
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
  });
  // any document change (tab switch, sample opened, external design) while a
  // plane-pick is pending would leave the 3 plane quads stranded — cancel it
  bus.on('doc-updated', () => { if (planePickCb) endPlanePick(); });

  // Extrude gizmo drags (arrow + taper ring) — capture phase so we grab them
  // BEFORE OrbitControls, then disable orbit for the drag. Move/up on window
  // so the drag survives the pointer leaving the canvas.
  renderer.domElement.addEventListener('pointerdown', e => {
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

function buildOriginPlanes() {
  clearOriginPlanes();
  const s = Math.max(fitRadius * 1.15, 55);      // half-size of each plane quad
  const defs = [
    { plane: 'XY', rot: [0, 0, 0], color: 0x4d7fff, lpos: [s * 0.72, s * 0.72, 0] },
    { plane: 'XZ', rot: [Math.PI / 2, 0, 0], color: 0x43c579, lpos: [s * 0.72, 0, s * 0.72] },
    { plane: 'YZ', rot: [0, Math.PI / 2, 0], color: 0xff6b6b, lpos: [0, s * 0.72, s * 0.72] },
  ];
  for (const d of defs) {
    const geo = new THREE.PlaneGeometry(2 * s, 2 * s);
    const mat = new THREE.MeshBasicMaterial({ color: d.color, transparent: true,
      opacity: 0.16, side: THREE.DoubleSide, depthWrite: false });
    const m = new THREE.Mesh(geo, mat);
    m.rotation.set(...d.rot);
    m.position.copy(fitCenter);
    m.userData.plane = d.plane; m.userData.base = 0.16;
    m.renderOrder = 998;
    scene.add(m); originPlanes.push(m);
    const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: d.color, transparent: true, opacity: 0.6 }));
    edge.rotation.set(...d.rot); edge.position.copy(fitCenter);
    edge.renderOrder = 999; scene.add(edge); originPlanes.push(edge);
    const label = makeLabelSprite(d.plane, d.color);
    label.position.set(fitCenter.x + d.lpos[0], fitCenter.y + d.lpos[1],
                       fitCenter.z + d.lpos[2]);
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
  const hit = raycaster.intersectObjects(quads, false)[0];
  for (const q of quads) q.material.opacity = q.userData.base;
  renderer.domElement.style.cursor = 'pointer';
  if (hit) { hit.object.material.opacity = 0.4; }
  else if (mesh && raycaster.intersectObject(mesh, false).length)
    renderer.domElement.style.cursor = 'crosshair';   // hovering a face
}

function planePickAt(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const quads = originPlanes.filter(o => o.userData.plane);
  const pHit = raycaster.intersectObjects(quads, false)[0];
  const fHit = mesh ? raycaster.intersectObject(mesh, false)[0] : null;
  const cb = planePickCb;
  // a planar face closer than the plane quad wins (you clicked the solid)
  if (fHit && (!pHit || fHit.distance < pHit.distance - 1e-3) && MODEL) {
    const fid = MODEL.faceId[fHit.face.a];
    const info = MODEL.faces.find(f => f.id === fid);
    if (info && info.type === 'PLANE' && info.center) {
      endPlanePick(); cb('face', info); return;
    }
  }
  if (pHit) { const pl = pHit.object.userData.plane; endPlanePick(); cb('plane', pl); return; }
  // clicked empty space — keep waiting (don't cancel)
}

/* ---------------- sketch view: look straight at the sketch plane -----------
   While a PLANE sketch is open, the 2D editor becomes a transparent overlay
   and the 3D scene is rendered through it with an ORTHOGRAPHIC camera aimed
   down the plane's normal — so the SVG grid/entities sit exactly ON the plane
   and the model stays visible behind them (Fusion's sketch mode).
   The mapping: the sketcher's world window (cx, cy, ext in plane coords over
   the SVG rect) is re-projected onto the renderer canvas rect, so the two
   line up even when the rects differ by a few px. */

export function enterSketchView(frame) {
  sketchFrame = {
    o: new THREE.Vector3(...frame.origin),
    x: new THREE.Vector3(...frame.x_dir).normalize(),
    y: new THREE.Vector3(...frame.y_dir).normalize(),
    z: new THREE.Vector3(...frame.z_dir).normalize(),
  };
  sketchCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.5, 10);
  controls.enabled = false;              // the overlay owns pan/zoom now
  groundGrid.visible = false;            // the SVG grid replaces it
}

export function updateSketchView(view, svgEl) {
  if (!sketchCam || !sketchFrame) return;
  const sr = svgEl.getBoundingClientRect();
  const rr = renderer.domElement.getBoundingClientRect();
  if (sr.height < 2 || rr.height < 2) return;
  const mmPerPx = (2 * view.ext) / sr.height;       // uniform x/y scale
  // world (plane-local) center of the RENDERER rect
  const cx = view.cx + ((rr.left + rr.width / 2) - (sr.left + sr.width / 2)) * mmPerPx;
  const cy = view.cy - ((rr.top + rr.height / 2) - (sr.top + sr.height / 2)) * mmPerPx;
  const ex = (rr.width / 2) * mmPerPx, ey = (rr.height / 2) * mmPerPx;
  const D = Math.max(fitRadius * 5, 400);           // stand well clear of the body
  const c = sketchFrame.o.clone()
    .add(sketchFrame.x.clone().multiplyScalar(cx))
    .add(sketchFrame.y.clone().multiplyScalar(cy));
  sketchCam.position.copy(c.clone().add(sketchFrame.z.clone().multiplyScalar(D)));
  sketchCam.up.copy(sketchFrame.y);
  sketchCam.lookAt(c);
  sketchCam.left = -ex; sketchCam.right = ex;
  sketchCam.top = ey; sketchCam.bottom = -ey;
  sketchCam.near = 0.5; sketchCam.far = D + Math.max(fitRadius * 10, 800);
  sketchCam.updateProjectionMatrix();
}

export function exitSketchView() {
  sketchCam = null; sketchFrame = null;
  controls.enabled = true;
  groundGrid.visible = true;
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

export function setView(dir) {
  const d = fitRadius * 2.4, c = fitCenter;
  const views = {
    iso:   [c.x + d * 0.7, c.y - d * 0.7, c.z + d * 0.55],
    top:   [c.x, c.y, c.z + d],
    front: [c.x, c.y - d, c.z + d * 0.001],
  };
  camera.position.set(...views[dir]); controls.target.copy(c);
}

function disposeModel() {
  if (mesh) { scene.remove(mesh); mesh.geometry.dispose(); mesh = null; }
  for (const l of edgeLines) { scene.remove(l); l.geometry.dispose(); }
  edgeLines.length = 0;
  for (const o of sketchObjs) { scene.remove(o); o.geometry.dispose(); }
  sketchObjs.length = 0;
  for (const o of ghostObjs) { scene.remove(o); o.geometry.dispose(); }
  ghostObjs.length = 0;
  clearPickHighlight();
}

function addBodies(bodies) {
  // other unconsumed solid bodies — shown translucent so positioning a second
  // body (before it is fused/cut) is not blind. Not pickable.
  for (const b of bodies || []) {
    if (!b.positions || !b.positions.length) continue;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(b.positions, 3));
    g.setIndex(b.indices);
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
      color: 0x8aa0b8, metalness: 0.1, roughness: 0.6, transparent: true,
      opacity: 0.32, depthWrite: false }));
    scene.add(m); ghostObjs.push(m);
    const eg = new THREE.EdgesGeometry(g, 25);
    const el = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({
      color: 0x6b7f96, transparent: true, opacity: 0.5 }));
    scene.add(el); ghostObjs.push(el);
  }
}

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

export async function loadMesh(fit = false) {
  clearHighlight(); clearPick();
  try {
    const m = await (await fetch('/api/model?t=' + Date.now())).json();
    disposeModel();
    addSketches(m.sketches);
    addBodies(m.bodies);
    if (!m.positions || !m.positions.length) {
      MODEL = null;
      if (fit && (sketchObjs.length || ghostObjs.length))
        fitToObjects([...sketchObjs, ...ghostObjs]);
      return;
    }
    MODEL = m;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position',
      new THREE.Float32BufferAttribute(m.positions, 3));
    geo.setIndex(m.indices);
    geo.computeVertexNormals();
    mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color: 0x5ba7f7, metalness: 0.25, roughness: 0.42 }));
    scene.add(mesh);
    for (const e of m.edges) {
      const g = new THREE.BufferGeometry().setFromPoints(
        e.points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
      const line = new THREE.Line(g, new THREE.LineBasicMaterial({
        color: 0x0c2a4a, transparent: true, opacity: 0.55 }));
      line.userData.edgeId = e.id;
      scene.add(line); edgeLines.push(line);
    }
    geo.computeBoundingSphere();
    fitRadius = geo.boundingSphere.radius || 100;
    fitCenter.copy(geo.boundingSphere.center);
    if (fit) {
      if (ghostObjs.length) { fitToObjects([mesh, ...ghostObjs]); }
      else {
        camera.near = fitRadius / 100; camera.far = fitRadius * 100;
        camera.updateProjectionMatrix(); setView('iso');
      }
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
  camera.near = fitRadius / 100; camera.far = fitRadius * 100;
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
  document.getElementById('pickInfo').style.display = 'none';
}

function pickAt(e) {
  if (!mesh || !MODEL) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  raycaster.params.Line.threshold = fitRadius / 60;

  const eHits = raycaster.intersectObjects(edgeLines, false);
  const fHit = raycaster.intersectObject(mesh, false)[0];
  if (eHits.length && (!fHit || eHits[0].distance <= fHit.distance + 1e-3)) {
    selectEdge(eHits[0].object.userData.edgeId);
  } else if (fHit) {
    selectFace(MODEL.faceId[fHit.face.a]);
  }
}

function selectFace(fid) {
  clearPickHighlight();
  const m = MODEL, pos = m.positions, keep = [];
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
  showPick(`<b>Face ${fid}</b> — ${isFlat && info.type !== 'PLANE' ? info.type + ' (flat)' : info.type}`,
    [['area', (info.area ?? '?') + ' mm²'],
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

function selectEdge(eid) {
  clearPickHighlight();
  S.pickedFace = null;                 // an edge pick is not a sketchable face
  S.pickedCurved = null;
  const e = MODEL.edges.find(x => x.id === eid);
  const g = new THREE.BufferGeometry().setFromPoints(
    e.points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
  pickHl = new THREE.Line(g, new THREE.LineBasicMaterial({
    color: 0xffb85c, linewidth: 3, depthTest: false }));
  pickHl.renderOrder = 999;
  scene.add(pickHl);
  showPick(`<b>Edge ${eid}</b> — ${e.type}`, [['length', e.length + ' mm']]);
}

function showPick(title, rows) {
  const el = document.getElementById('pickInfo');
  el.innerHTML = title + rows.filter(Boolean)
    .map(r => `<br><span class="k">${r[0]}:</span> ${r[1]}`).join('');
  el.style.display = 'block';
}
