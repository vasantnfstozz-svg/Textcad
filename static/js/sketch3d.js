// sketch3d.js — the in-viewport sketch layer (Fusion-style Sketch Mode v2).
// A sketch is NOT a separate screen: entities, grid, ghosts and snap markers
// are real geometry ON the sketch plane inside the 3D scene, and the user can
// orbit/pan/zoom at any moment while sketching:
//   * LEFT  = draw / select (raycast onto the sketch plane -> plane-local x,y)
//   * RIGHT = orbit, MIDDLE = pan, wheel = zoom  (remapped only in sketch mode)
// sketcher.js owns ALL tool logic (state machine in plane coordinates); this
// module only renders its spec and converts pointer rays to plane points.
// Wiring: viewport.js calls initSketch3D(ctx); sketcher.js calls enter/render/
// exit; pointer events flow back over the bus ('sk3d-down/move/up/dbl').

import * as THREE from 'three';
import { bus } from './bus.js';

let ctx = null;        // {scene, camera, dom, groundGrid, getControls,
                       //  setOrbitUp, getFitRadius}
let active = false;
let frame = null;      // {o,x,y,z} THREE.Vector3 basis of the sketch plane
let group = null;      // everything of the current sketch lives under here
let gridObj = null;
let leftDown = false;
let tween = null;
const raycaster = new THREE.Raycaster();
const plane = new THREE.Plane();
// |cos| between the pick ray and the plane normal below this = the view is so
// edge-on that a click maps to a point hundreds of mm away (it produced 1x1
// slivers at x=692mm). Orbiting there is fine; DRAWING there is not.
const GRAZE = 0.15;
let edgeOn = false;

const V = a => new THREE.Vector3(a[0], a[1], a[2]);
const ctrl = () => ctx.getControls();

export function initSketch3D(context) {
  ctx = context;
  ctx.dom.addEventListener('pointerdown', e => {
    // Shift+left is PAN (viewport.setLeftButton): without this guard the same
    // gesture would pan AND drop a sketch point
    if (!active || e.button !== 0 || e.shiftKey || tween) return;
    const p = planePoint(e);
    if (!p) return;
    leftDown = true;
    bus.emit('sk3d-down', { ...p, tol: tolMm(p) });
  });
  // move/up on window so drags survive leaving the canvas (gizmo pattern)
  window.addEventListener('pointermove', e => {
    if (!active || tween) return;
    const p = planePoint(e);
    if (!p) return;
    bus.emit('sk3d-move', { ...p, tol: tolMm(p), down: leftDown });
  });
  window.addEventListener('pointerup', e => {
    if (!active || e.button !== 0) return;
    leftDown = false;
    bus.emit('sk3d-up', {});
  });
  ctx.dom.addEventListener('dblclick', () => { if (active) bus.emit('sk3d-dbl', {}); });
  bus.on('sketch-tool', ({ tool }) => {
    if (active) ctx.dom.style.cursor = tool ? 'crosshair' : '';
  });
  // orbiting/zooming re-fits the ADAPTIVE grid and moves the HTML labels
  // (dims, snap tag) — let the sketcher re-place them. viewport.js re-emits
  // this for whichever controls instance is live.
  bus.on('view-changed', () => {
    if (!active) return;
    updateGrid();
    bus.emit('sk3d-view', {});
  });
}

export function sketch3DActive() { return active; }

/* ---------------- enter / exit ---------------- */

export function enterSketch3D(frameSpec, opts = {}) {
  exitSketch3D();
  frame = { o: V(frameSpec.origin), x: V(frameSpec.x_dir).normalize(),
            y: V(frameSpec.y_dir).normalize(), z: V(frameSpec.z_dir).normalize() };
  plane.setFromNormalAndCoplanarPoint(frame.z, frame.o);
  group = new THREE.Group();
  group.matrixAutoUpdate = false;
  group.matrix.makeBasis(frame.x, frame.y, frame.z).setPosition(frame.o);
  ctx.scene.add(group);
  gridBase = Math.max(opts.gridMm || 10, 0.1);
  gridState = null;
  active = true;                 // updateGrid and pointer events are gated on it
  updateGrid();
  if (!gridState) {
    // camera not facing the plane yet (the tween runs next): build the first
    // grid from where the tween will land instead of the current view
    const f = opts.focus || { cx: 0, cy: 0, extent: 90 };
    const rect = ctx.dom.getBoundingClientRect();
    const ext = f.extent || 90;
    const pxPerMm = rect.height ? rect.height / (2 * ext * 1.15) : 3;
    buildGridFor({ minX: f.cx - ext, maxX: f.cx + ext,
                   minY: f.cy - ext, maxY: f.cy + ext,
                   cx: f.cx, cy: f.cy }, pxPerMm);
  }
  ctx.groundGrid.visible = false;
  // orbit around the PLANE's up so the flat-on sketch view is never a gimbal
  // pole (looking down world -Y at XZ was exactly phi=pi => orbit was dead)
  const c = ctx.setOrbitUp(frame.y.toArray());
  // Sketch mode changes exactly ONE thing about navigation: LEFT stops
  // orbiting because it draws. MIDDLE=pan / RIGHT=orbit / wheel=zoom are the
  // app-wide mapping set in viewport.buildControls — do not diverge here, the
  // tabs disagreeing is what made "I can't rotate while sketching" happen.
  // Going through setLeftButton (not c.mouseButtons directly) keeps the
  // Shift+left = pan fallback working while sketching.
  ctx.setLeftButton(null);                     // left draws
  edgeOn = false;                              // (active was set before the grid)
  const f = opts.focus || { cx: 0, cy: 0, extent: 90 };
  lookAtPlanePoint(f.cx, f.cy, distanceFor(f.extent || 90));
}

export function exitSketch3D() {
  if (!active) return;
  active = false; leftDown = false; tween = null; edgeOn = false;
  disposeDeep(group); ctx.scene.remove(group);
  group = null; gridObj = null; gridState = null; frame = null;
  ctx.groundGrid.visible = true;
  ctx.setOrbitUp(null).enabled = true;      // default axis + default button map
  ctx.dom.style.cursor = '';
}

/* Fusion's "Look At": re-align the view flat onto the sketch plane, keeping
   the current pan target and zoom distance. */
export function lookAtSketch() {
  if (!active) return;
  const t = ctrl().target.clone();
  const d = t.clone().sub(frame.o).dot(frame.z);
  const onPlane = t.sub(frame.z.clone().multiplyScalar(d));   // project target
  const local = worldToLocal(onPlane);
  const dist = ctx.camera.position.distanceTo(ctrl().target);
  lookAtPlanePoint(local.x, local.y, dist);
}

function distanceFor(extent) {
  // perspective fov 50deg: visible half-height at dist D is D*tan(25deg)
  const fit = ctx.getFitRadius();
  return Math.max(extent * 1.15 / Math.tan(25 * Math.PI / 180), fit * 1.6 + 40);
}

function lookAtPlanePoint(cx, cy, dist) {
  const target = frame.o.clone()
    .add(frame.x.clone().multiplyScalar(cx))
    .add(frame.y.clone().multiplyScalar(cy));
  tweenCamera(target.clone().add(frame.z.clone().multiplyScalar(dist)), target);
}

function tweenCamera(pos, target, ms = 350) {
  tween = { t0: performance.now(), ms, p0: ctx.camera.position.clone(), p1: pos,
            q0: ctrl().target.clone(), q1: target };
  ctrl().enabled = false;
  requestAnimationFrame(stepTween);
}

function stepTween(now) {
  if (!tween) return;
  const k = Math.min((now - tween.t0) / tween.ms, 1);
  const e = k < 0.5 ? 2 * k * k : 1 - 2 * (1 - k) * (1 - k);   // easeInOut
  ctx.camera.position.lerpVectors(tween.p0, tween.p1, e);
  ctrl().target.lerpVectors(tween.q0, tween.q1, e);
  if (k < 1) { requestAnimationFrame(stepTween); return; }
  tween = null;
  ctrl().enabled = true;
  updateGrid();                              // fit the grid to the landed view
  bus.emit('sk3d-view', {});                 // re-place labels at the new pose
}

/* ---------------- coordinates ---------------- */

function worldToLocal(w) {
  const r = w.clone().sub(frame.o);
  return { x: r.dot(frame.x), y: r.dot(frame.y) };
}

function localToWorld(x, y) {
  return frame.o.clone()
    .add(frame.x.clone().multiplyScalar(x))
    .add(frame.y.clone().multiplyScalar(y));
}

function planePoint(e) {
  const rect = ctx.dom.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, ctx.camera);
  setEdgeOn(Math.abs(raycaster.ray.direction.dot(frame.z)) < GRAZE);
  if (edgeOn) return null;                  // too grazing to mean anything
  const hit = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(plane, hit)) return null;
  return worldToLocal(hit);
}

function setEdgeOn(v) {
  if (v === edgeOn) return;
  edgeOn = v;
  bus.emit('sk3d-edge', { edgeOn });         // the hint bar says why + how out
}

/* snap tolerance: ~12 screen px expressed in plane mm at the cursor point */
function tolMm(p) {
  const a = toScreen(localToWorld(p.x, p.y));
  const b = toScreen(localToWorld(p.x + 1, p.y));
  if (!a || !b) return 2;
  const pxPerMm = Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1e-3);
  return Math.min(12 / pxPerMm, 60);
}

function toScreen(world) {
  const rect = ctx.dom.getBoundingClientRect();
  const v = world.clone().project(ctx.camera);
  if (v.z > 1) return null;                       // behind the camera
  return { x: rect.left + (v.x + 1) / 2 * rect.width,
           y: rect.top + (1 - (v.y + 1) / 2) * rect.height };
}

/* plane-local (x,y) -> client px, for HTML labels (dim editor, snap label) */
export function planeToScreen(x, y) {
  if (!active) return null;
  return toScreen(localToWorld(x, y));
}

/* ---------------- the adaptive grid (Fusion-style) ----------------
   The grid is DERIVED FROM THE VIEW, not built once: zooming in subdivides
   the cells along a 1-2-5 ladder down to a floor of gridMm/10 — past that
   the cells simply get bigger on screen (Fusion stops subdividing too) —
   and the covered patch follows the camera, so the plane never "ends" while
   panning, zooming out, or drawing something big. Rebuilt on 'view-changed';
   a no-op when step, size and centre are unchanged. */

let gridBase = 10;         // SETTINGS.gridMm at sketch enter
let gridState = null;      // {step, major, size, cx, cy} of the built grid
const MIN_CELL_PX = 10;    // never draw a minor cell narrower than this

/* test/debug accessor for what grid is really in the scene */
export function gridInfo() { return gridState ? { ...gridState } : null; }

/* the LIVE minor step — the sketcher snaps by this, so clicks always stick
   to the grid that is actually displayed (never a stale cached step) */
export function gridStep() { return gridState ? gridState.step : 10; }

function nextStep(s) {     // the 1-2-5 ladder, decade-normalized
  const e = Math.floor(Math.log10(s) + 1e-9);
  const m = s / 10 ** e;
  return (m < 1.5 ? 2 : m < 3.5 ? 5 : 10) * 10 ** e;
}

/* plane-local bbox of the visible patch of the sketch plane: rays through
   the viewport corners + centre, intersected with the plane. null when the
   view is (nearly) edge-on — the caller keeps the current grid. */
function viewFootprint() {
  const rect = ctx.dom.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const pts = [];
  for (const [nx, ny] of [[-1, -1], [1, -1], [-1, 1], [1, 1], [0, 0]]) {
    raycaster.setFromCamera(new THREE.Vector2(nx, ny), ctx.camera);
    if (Math.abs(raycaster.ray.direction.dot(frame.z)) < 0.02) continue;
    const hit = new THREE.Vector3();
    if (raycaster.ray.intersectPlane(plane, hit)) pts.push(worldToLocal(hit));
  }
  if (pts.length < 3) return null;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of pts) {
    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
  }
  return { minX, maxX, minY, maxY,
           cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 };
}

function updateGrid() {
  if (!active || !frame) return;
  const fp = viewFootprint();
  if (!fp) return;                       // edge-on: keep what we have
  const a = toScreen(localToWorld(fp.cx, fp.cy));
  const b = toScreen(localToWorld(fp.cx + 1, fp.cy));
  if (!a || !b) return;
  buildGridFor(fp, Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1e-4));
}

function buildGridFor(fp, pxPerMm) {
  const floor = Math.max(gridBase / 10, 0.01);   // where subdivision ENDS
  let step = floor;
  while (step * pxPerMm < MIN_CELL_PX && step < 1e6) step = nextStep(step);
  const major = step * 10;
  // cover the visible patch with margin, but cap the line count — when the
  // horizon is in view the footprint runs to infinity and a grid should not
  const spanNeed = Math.max(fp.maxX - fp.minX, fp.maxY - fp.minY) * 1.3;
  const size = Math.max(Math.min(Math.ceil(spanNeed / major) * major,
                                 24 * major), 2 * major);
  // centre on a MAJOR multiple so the lines stay put in the world while the
  // grid re-centres under a pan (a drifting grid reads as swimming lines)
  const cx = Math.round(fp.cx / major) * major;
  const cy = Math.round(fp.cy / major) * major;
  if (gridState && gridState.step === step && gridState.size === size
      && gridState.cx === cx && gridState.cy === cy) return;
  const stepChanged = !gridState || gridState.step !== step;
  if (gridObj) { group.remove(gridObj); disposeDeep(gridObj); }
  gridObj = new THREE.Group();
  const minor = new THREE.GridHelper(size, Math.round(size / step),
                                     0x20242e, 0x20242e);
  const majorG = new THREE.GridHelper(size, Math.round(size / major),
                                      0x3a4150, 0x3a4150);
  let z = 0;
  for (const g of [minor, majorG]) {
    g.rotation.x = Math.PI / 2;         // GridHelper is XZ; we draw XY
    g.position.z = z; z += 0.004;       // majors paint over minors, no z-fight
    g.material.transparent = true;
    g.material.opacity = 0.8;
    g.material.depthWrite = false;
    gridObj.add(g);
  }
  // the plane's own axes through the origin, while the origin is on-grid
  const half = size / 2;
  const axis = (p1, p2) => {
    const geo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
    const l = new THREE.Line(geo, new THREE.LineBasicMaterial({
      color: 0x4a5468, transparent: true, depthWrite: false }));
    l.position.z = z;
    gridObj.add(l);
  };
  if (Math.abs(cx) <= half)
    axis(new THREE.Vector3(-cx, -half, 0), new THREE.Vector3(-cx, half, 0));
  if (Math.abs(cy) <= half)
    axis(new THREE.Vector3(-half, -cy, 0), new THREE.Vector3(half, -cy, 0));
  gridObj.position.set(cx, cy, 0);
  group.add(gridObj);
  gridState = { step, major, size, cx, cy };
  if (stepChanged) bus.emit('sk3d-grid', { step });   // readout + snap step
}

/* ---------------- rendering ---------------- */

/* spec (all in plane-local mm):
   { shapes: [{pts:[[x,y]..], closed, color, fill, fillOpacity, dashed}],
     dots:   [{x, y, r, color, ring}],
     cross:  {x, y, size} | null,
     guide:  {axis:'h'|'v', ref:{x,y}} | null }             */
export function renderSketch3D(spec) {
  if (!active || !group) return;
  for (const c of [...group.children]) {
    if (c === gridObj) continue;
    group.remove(c); disposeDeep(c);
  }
  const Z = 0.05;                                  // float above the grid a hair
  for (const s of spec.shapes || []) {
    if (!s.pts || s.pts.length < 2) continue;
    const v3 = s.pts.map(p => new THREE.Vector3(p[0], p[1], Z));
    if (s.closed) v3.push(v3[0].clone());
    const geo = new THREE.BufferGeometry().setFromPoints(v3);
    const mat = s.dashed
      ? new THREE.LineDashedMaterial({ color: s.color, dashSize: 2.2,
          gapSize: 1.6, transparent: true, depthTest: false })
      : new THREE.LineBasicMaterial({ color: s.color, transparent: true,
          depthTest: false });
    const line = new THREE.Line(geo, mat);
    if (s.dashed) line.computeLineDistances();
    line.renderOrder = 1006;
    group.add(line);
    if (s.fill && s.closed && s.pts.length >= 3) {
      const shape = new THREE.Shape(s.pts.map(p => new THREE.Vector2(p[0], p[1])));
      const fill = new THREE.Mesh(new THREE.ShapeGeometry(shape),
        new THREE.MeshBasicMaterial({ color: s.fill, transparent: true,
          opacity: s.fillOpacity ?? 0.13, depthTest: false,
          depthWrite: false, side: THREE.DoubleSide }));
      fill.renderOrder = 1005;
      group.add(fill);
    }
  }
  for (const d of spec.dots || []) {
    const geo = d.ring ? new THREE.RingGeometry(d.r * 0.72, d.r, 24)
                       : new THREE.CircleGeometry(d.r, 20);
    const dot = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      color: d.color, transparent: true, depthTest: false,
      side: THREE.DoubleSide }));
    dot.position.set(d.x, d.y, Z);
    dot.renderOrder = 1007;
    group.add(dot);
  }
  if (spec.cross) {
    const m = spec.cross.size;
    const pts = [
      new THREE.Vector3(spec.cross.x - m, spec.cross.y, Z),
      new THREE.Vector3(spec.cross.x + m, spec.cross.y, Z),
      new THREE.Vector3(spec.cross.x, spec.cross.y - m, Z),
      new THREE.Vector3(spec.cross.x, spec.cross.y + m, Z)];
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const cross = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
      color: 0xffb85c, depthTest: false }));
    cross.renderOrder = 1008;
    group.add(cross);
  }
  if (spec.guide) {
    const g = spec.guide, L = 100000;
    const pts = g.axis === 'v'
      ? [new THREE.Vector3(g.ref.x, -L, Z), new THREE.Vector3(g.ref.x, L, Z)]
      : [new THREE.Vector3(-L, g.ref.y, Z), new THREE.Vector3(L, g.ref.y, Z)];
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineDashedMaterial({ color: 0x4da3ff, dashSize: 4,
      gapSize: 4, transparent: true, opacity: 0.7, depthTest: false });
    const guide = new THREE.Line(geo, mat);
    guide.computeLineDistances();
    guide.renderOrder = 1006;
    group.add(guide);
  }
}

function disposeDeep(obj) {
  if (!obj) return;
  obj.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      if (o.material.map) o.material.map.dispose();
      o.material.dispose();
    }
  });
}
