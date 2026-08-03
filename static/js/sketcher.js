// sketcher.js — the interactive 2D sketch editor (Fusion-style):
//   * pick a tool in the palette, then CLICK ON THE CANVAS to draw
//     (circle: click center, click radius; rectangle: two corners;
//      polygon: click points, double-click to close)
//   * no tool active = select / drag-move shapes, drag empty space to pan
//   * mouse wheel zooms around the cursor; grid-snapped coordinates
//   * Esc cancels the tool, Delete removes the selected shape
// Two flows: plane sketch (Sketch tab) and face sketch (guided boss/pocket).

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh } from './viewport.js';
import { enterSketch3D, exitSketch3D, renderSketch3D,
         planeToScreen } from './sketch3d.js';
import { openFeatDialog } from './dialogs.js';
import { SETTINGS, unitLabel, fmtLen, toMm } from './settings.js';

/* ---------------- state ---------------- */

const DEFAULT_FIELDS = {
  rectangle: { w: 40, h: 20, x: 0, y: 0, rotation: 0 },
  circle: { r: 15, x: 0, y: 0 },
  ellipse: { rx: 20, ry: 10, x: 0, y: 0, rotation: 0 },
  slot: { length: 30, height: 10, x: 0, y: 0, rotation: 0 },
  regular_polygon: { radius: 20, sides: 6, x: 0, y: 0, rotation: 0 },
  polygon: { points: [[0, 0], [30, 0], [15, 25]], x: 0, y: 0 },
};

let skEnts = [];          // the sketch's entities
let skOnFace = null;      // {center, normal, inputId} when sketching on a face
let skEditId = null;      // feature id when EDITING an existing committed sketch
let faceRef = null;       // {outer:[[x,y]..], holes:[[[x,y]..]..]} reference outline
let sketchActive = false; // true while in sketch MODE (non-modal, docked)
let tool = null;          // active drawing tool (entity kind) or null = select
let clicks = [];          // world-space clicks collected for the current tool
let ghost = null;         // preview entity while placing
let selEnt = -1;          // selected entity index
let view = { cx: 0, cy: 0, ext: 60 };   // world-space view (ext = half-width)

// path tool (chained lines + arcs)
let pathStart = null;     // first point of the profile
let pathSegs = [];        // committed segments
let segMode = 'line';     // what the next segment is: 'line' | 'arc'
let pendingVia = null;    // arc: the middle (via) point, waiting for the end

// snapping (P4)
let activeSnap = null;    // {x, y, label} — geometry point the cursor snapped to
let axisLock = null;      // {axis:'h'|'v', ref:{x,y}} — inference guide line

// trim tool (last P1): entity outlines split at their crossings into PIECES
// by the backend; hovering highlights one red, clicking removes it
let trimPieces = null;    // [{id, ent, whole, pts:[[x,y]..]}] or null=loading
let trimHover = -1;       // index into trimPieces
let trimFor = '';         // JSON of the skEnts the pieces were computed for
let trimBusy = false;     // an apply is in flight

const dlg = () => document.getElementById('sketchDialog');
const svg = () => document.getElementById('sketchCanvas');

/* principal-plane frames, PROBED from build123d 0.11.1 (never assume — the
   XZ plane's normal points -Y, and offset moves the origin along z_dir) */
const PLANE_FRAMES = {
  XY: { x_dir: [1, 0, 0], y_dir: [0, 1, 0], z_dir: [0, 0, 1] },
  XZ: { x_dir: [1, 0, 0], y_dir: [0, 0, 1], z_dir: [0, -1, 0] },
  YZ: { x_dir: [0, 1, 0], y_dir: [0, 0, 1], z_dir: [1, 0, 0] },
};

function planeFrame() {
  const f = PLANE_FRAMES[document.getElementById('skPlane').value] || PLANE_FRAMES.XY;
  const off = Number(document.getElementById('skOffset').value) || 0;
  return { origin: f.z_dir.map(c => c * off),
           x_dir: f.x_dir, y_dir: f.y_dir, z_dir: f.z_dir };
}

/* PLANE sketches happen IN the 3D viewport (sketch3d.js) — Fusion's sketch
   mode: entities live on the plane as real geometry, and the user can orbit
   (right-drag) / pan (middle) / zoom at any time while drawing with LEFT.
   Face sketches still use the docked 2D editor until they are unified. */
const inPlane3D = () => sketchActive && !skOnFace;
let snapTol3d = 2;        // mm for ~12 px — updated with every 3D pointer event
let pendingFocus = null;  // {cx, cy, extent} camera framing for the next enter
let gridStep3d = 10;
let edgeOnView = false;   // view rotated (nearly) parallel to the sketch plane

/* snap/close tolerance in plane mm — screen-derived in 3D mode */
const snapTolWorld = () => inPlane3D() ? snapTol3d : view.ext / 40;

/* ---------------- open / close ---------------- */

function resetEditor() {
  skEnts = []; tool = null; clicks = []; ghost = null; selEnt = -1;
  faceRef = null;
  trimPieces = null; trimHover = -1; trimFor = '';
  view = { cx: 0, cy: 0, ext: 90 };          // roomier default, Fusion-like
  document.querySelectorAll('.skpalette button')
    .forEach(b => b.classList.remove('active'));
  renderEnts();
}

/* Fit the view to a set of [x,y] points (with margin). */
function fitToPoints(pts) {
  if (!pts.length) return;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(Math.max(...xs) - Math.min(...xs),
                        Math.max(...ys) - Math.min(...ys), 20);
  view = { cx, cy, ext: span * 0.65 };
}

function nextName() {
  const n = (S.lastDoc?.features.filter(
    f => f.op === 'sketch' || f.op === 'sketch_on_face').length || 0) + 1;
  return 'sketch' + n;
}

/* Enter/leave sketch MODE (Fusion-style): the editor shows NON-modally, docked
   over the main area, so the contextual green SKETCH ribbon tab stays clickable
   above it. 'sketch-mode' tells the ribbon to swap in the contextual tab. */
function enterMode() {
  sketchActive = true;
  if (!skOnFace) {
    // Fusion-style: NO separate editor — the viewport IS the sketch. Tools sit
    // in the contextual ribbon; a floating hint bar + dim labels overlay the
    // 3D view; the camera turns to the plane but stays free to orbit.
    enterSketch3D(planeFrame(), { gridMm: SETTINGS.gridMm,
                                  focus: pendingFocus || undefined });
    pendingFocus = null;
    document.getElementById('sk3dBar').style.display = '';
  } else {
    // face sketches: keep the docked 2D editor (side panel has depth/Join-Cut)
    const d = dlg();
    d.classList.add('docked', 'facemode');
    d.classList.remove('planemode');
    const dt = document.getElementById('doctabs');
    d.style.top = (dt ? dt.getBoundingClientRect().bottom : 130) + 'px';
    d.show();                        // NON-modal — no backdrop, ribbon stays live
  }
  bus.emit('sketch-mode', { active: true });
}

function exitMode() {
  sketchActive = false;
  exitSketch3D();                    // no-op unless a plane sketch was open
  for (const id of ['sk3dBar', 'sk3dDim', 'sk3dSnap', 'skDimEdit3d']) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  }
  const d = dlg();
  d.classList.remove('docked', 'facemode', 'planemode');
  d.style.top = '';
  try { d.close(); } catch { /* already closed */ }
  bus.emit('sketch-mode', { active: false });
}

// ribbon-facing controls for the contextual SKETCH tab
export function setSketchTool(kind) { setTool(tool === kind ? null : kind); }
export function finishSketch() { create(); }
export function cancelSketch() {
  if (skEnts.length && !confirm(
    `Discard this sketch (${skEnts.length} shape${skEnts.length > 1 ? 's' : ''})?`)) return;
  exitMode();
}

export function openSketchEditor(plane = 'XY') {
  skOnFace = null; skEditId = null;
  resetEditor();
  document.getElementById('skCreate').textContent = 'Create';
  document.getElementById('skName').value = nextName();
  document.getElementById('skPlane').value = plane;      // chosen in the viewport
  document.getElementById('skOffset').value = '0';
  document.getElementById('skPlaneRow').style.display = '';
  document.getElementById('skFaceNote').style.display = 'none';
  document.getElementById('skFaceExtrude').style.display = 'none';
  pendingFocus = { cx: 0, cy: 0, extent: 90 };
  enterMode();
  updateHint();
  draw();
}

/* Reopen a committed sketch to edit its entities (the alternative to
   delete-and-redraw). Loads the stored entities back onto the canvas. */
export function editSketch(feature) {
  skOnFace = null; skEditId = feature.id;
  resetEditor();
  skEnts = (feature.params.entities || []).map(e => ({ ...e }));
  document.getElementById('skName').value = feature.id;
  document.getElementById('skPlaneRow').style.display = '';
  document.getElementById('skPlane').value = feature.params.plane || 'XY';
  document.getElementById('skOffset').value = feature.params.offset ?? 0;
  document.getElementById('skFaceNote').style.display = 'none';
  document.getElementById('skFaceExtrude').style.display = 'none';
  document.getElementById('skCreate').textContent = 'Save changes';
  // frame the existing geometry (camera focus in 3D, viewBox in the SVG editor)
  const xs = skEnts.map(e => e.x || 0), ys = skEnts.map(e => e.y || 0);
  if (xs.length) {
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
    const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    pendingFocus = { cx, cy, extent: 90 };
    view = { cx, cy, ext: 60 };
  }
  enterMode();
  updateHint();
  renderEnts();
}
bus.on('edit-sketch', editSketch);

export function openSketchOnFace(faceInfo) {
  const tip = [...(S.lastDoc?.features || [])].reverse()
    .find(f => f.volume != null);
  if (!tip) { bus.emit('msg', 'bot', '⚠ No solid to sketch on yet.'); return; }
  skOnFace = { center: faceInfo.center, normal: faceInfo.normal || null,
               inputId: tip.id };
  skEditId = null;
  resetEditor();
  document.getElementById('skCreate').textContent = 'Create';
  document.getElementById('skName').value = nextName();
  document.getElementById('skPlaneRow').style.display = 'none';
  document.getElementById('skFaceNote').style.display = '';
  document.getElementById('skFaceExtrude').style.display = '';
  document.getElementById('skFaceNote').textContent =
    `On the selected face of "${skOnFace.inputId}" (grey = the surface outline). ` +
    `Pick a shape, click to draw, set depth + Join/Cut, then Create.`;
  enterMode();
  draw();
  loadFaceRef(faceInfo);          // fetch + show the selected surface as reference
}
bus.on('sketch-on-face', openSketchOnFace);

/* Fetch the picked face's boundary (in the sketch plane's 2D coords) and show
   it as grey reference geometry, so the user draws against the real surface. */
async function loadFaceRef(faceInfo) {
  try {
    const r = await fetch('/api/face-outline', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ face_center: faceInfo.center,
                             face_normal: faceInfo.normal || null }) });
    const data = await r.json();
    if (!data.planar || !(data.outer || []).length) return;
    faceRef = { outer: data.outer, holes: data.holes || [] };
    if (!skEnts.length) fitToPoints(faceRef.outer);   // frame the surface
    draw();
  } catch (e) { /* reference is a nicety; ignore fetch errors */ }
}

/* ---------------- init: palette, canvas, keyboard ---------------- */

export function initSketcher() {
  for (const b of document.querySelectorAll('.skpalette button[data-shape]')) {
    b.onclick = () => setTool(tool === b.dataset.shape ? null : b.dataset.shape);
  }
  document.getElementById('skCancel').onclick = cancelSketch;
  document.getElementById('skCreate').onclick = create;

  // non-modal now, but keep guarding the modal 'cancel' (Esc) just in case:
  // cancel the active TOOL, never destroy the sketch.
  dlg().addEventListener('cancel', e => {
    e.preventDefault();
    setTool(null);
  });
  // sketch mode is non-modal, so key handling lives on the window (guarded)
  window.addEventListener('keydown', e => {
    if (!sketchActive || e.target.tagName === 'INPUT') return;
    if (e.key === 'Escape' && (tool || clicks.length)) {
      e.preventDefault(); setTool(null);
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && selEnt >= 0) {
      e.preventDefault(); skEnts.splice(selEnt, 1); selEnt = -1; renderEnts();
    }
  });
  document.getElementById('skMirrorV').onclick = () => modifySel(e => mirrorEntity(e, 'v'));
  document.getElementById('skMirrorH').onclick = () => modifySel(e => mirrorEntity(e, 'h'));
  document.getElementById('skDup').onclick = () => modifySel(duplicateEntity);
  // NB: 'skOffset' is the plane-offset INPUT — the tool button is skOffsetTool
  // (they shared an id once, which hung this prompt on the input instead)
  document.getElementById('skOffsetTool').onclick = () => {
    const d = Number(prompt('Offset distance in mm (+ bigger / − smaller):', '5'));
    if (!d) return;
    modifySel(e => offsetEntity(e, d));
  };

  const c = svg();
  c.addEventListener('pointerdown', onDown);
  c.addEventListener('pointermove', onMove);
  c.addEventListener('pointerup', onUp);
  c.addEventListener('dblclick', onDblClick);
  c.addEventListener('wheel', onWheel, { passive: false });

  window.addEventListener('resize', () => { if (sketchActive) draw(); });

  // 3D sketch mode input: plane-local points arrive over the bus (sketch3d.js)
  bus.on('sk3d-down', p => {
    if (!inPlane3D()) return;
    snapTol3d = p.tol; pointerDown(p);
  });
  bus.on('sk3d-move', p => {
    if (!inPlane3D()) return;
    snapTol3d = p.tol; pointerMove(p);
  });
  bus.on('sk3d-up', () => { if (inPlane3D()) pointerUp(); });
  bus.on('sk3d-dbl', () => { if (inPlane3D()) onDblClick(); });
  bus.on('sk3d-grid', ({ step }) => {
    gridStep3d = step;
    const el = document.getElementById('sk3dGrid');
    if (el) el.textContent = `grid ${fmtLen(gridStep3d, false)} ${unitLabel()}`;
  });
  // orbiting moves the camera — re-place the HTML labels over the 3D scene
  bus.on('sk3d-view', () => { if (inPlane3D()) updateFloatingLabels(); });
  // rotated (nearly) edge-on to the plane: say so instead of taking nonsense
  // clicks — orbiting there is fine, drawing is not
  bus.on('sk3d-edge', ({ edgeOn }) => {
    edgeOnView = edgeOn;
    if (inPlane3D()) updateHint();
  });
}

function setTool(kind) {
  tool = kind; clicks = []; ghost = null; selEnt = -1;   // deselect on tool pick
  activeSnap = null; axisLock = null;
  pathStart = null; pathSegs = []; pendingVia = null; segMode = 'line';
  trimHover = -1;
  if (tool === 'trim') fetchTrimPieces(); else trimPieces = null;
  document.querySelectorAll('.skpalette button').forEach(b =>
    b.classList.toggle('active', b.dataset.shape === tool));
  svg().style.cursor = tool ? 'crosshair' : 'default';
  bus.emit('sketch-tool', { tool });        // highlight the active tool in the ribbon
  updateHint();
  draw();
}

/* ---------------- coordinates ---------------- */

function worldPoint(e) {
  const el = svg();
  const pt = new DOMPoint(e.clientX, e.clientY)
    .matrixTransform(el.getScreenCTM().inverse());
  return { x: pt.x, y: -pt.y };            // flip: world +y is up
}
const snap = v => {                       // snap increment from Settings (0 = off)
  const s = SETTINGS.snapMm;
  return s > 0 ? Math.round(v / s) * s : Math.round(v * 100) / 100;
};
const snapPt = p => ({ x: snap(p.x), y: snap(p.y) });
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/* ---------------- smart snapping (P4) ---------------- */

function collectSnapPoints() {
  const pts = [{ x: 0, y: 0, label: 'origin' }];
  skEnts.forEach(e => {
    const cx = e.x || 0, cy = e.y || 0;
    if (e.kind !== 'path') pts.push({ x: cx, y: cy, label: 'center' });
    if (e.kind === 'circle' || e.kind === 'regular_polygon') {
      const r = e.r ?? e.radius;
      for (const [dx, dy] of [[r, 0], [-r, 0], [0, r], [0, -r]])
        pts.push({ x: cx + dx, y: cy + dy, label: 'quadrant' });
    }
    if (e.kind === 'rectangle') {
      const a = (e.rotation || 0) * Math.PI / 180;
      for (const [sx, sy] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
        const lx = sx * e.w / 2, ly = sy * e.h / 2;
        pts.push({ x: cx + lx * Math.cos(a) - ly * Math.sin(a),
                   y: cy + lx * Math.sin(a) + ly * Math.cos(a),
                   label: 'corner' });
      }
    }
    if (e.kind === 'slot') {
      const a = (e.rotation || 0) * Math.PI / 180, h = e.length / 2;
      pts.push({ x: cx + h * Math.cos(a), y: cy + h * Math.sin(a), label: 'end' });
      pts.push({ x: cx - h * Math.cos(a), y: cy - h * Math.sin(a), label: 'end' });
    }
    if (e.kind === 'polygon' && e.points)
      for (const p of e.points)
        pts.push({ x: cx + p[0], y: cy + p[1], label: 'vertex' });
    if (e.kind === 'path' && e.start) {
      pts.push({ x: cx + e.start[0], y: cy + e.start[1], label: 'vertex' });
      for (const s of e.segments || [])
        pts.push({ x: cx + s.to[0], y: cy + s.to[1], label: 'vertex' });
    }
  });
  if (faceRef) {                       // snap to the selected surface too
    for (const p of faceRef.outer) pts.push({ x: p[0], y: p[1], label: 'edge' });
    for (const h of faceRef.holes) {
      const hx = h.reduce((s, p) => s + p[0], 0) / h.length;
      const hy = h.reduce((s, p) => s + p[1], 0) / h.length;
      pts.push({ x: hx, y: hy, label: 'hole center' });
    }
  }
  return pts;
}

/* The reference point of the segment being drawn (for axis inference). */
function refPoint() {
  if (tool === 'path' && pathStart) return pendingVia || pathCursor();
  if (tool && clicks.length) return clicks[clicks.length - 1];
  return null;
}

/* Geometry snap > axis lock > grid snap. Sets activeSnap/axisLock for draw(). */
function smartSnap(raw) {
  activeSnap = null; axisLock = null;
  const tol = snapTolWorld();
  let best = null, bd = tol;
  for (const sp of collectSnapPoints()) {
    const d = dist(raw, sp);
    if (d < bd) { best = sp; bd = d; }
  }
  if (best) { activeSnap = best; return { x: best.x, y: best.y }; }
  const ref = refPoint();
  const p = { x: snap(raw.x), y: snap(raw.y) };
  if (ref) {
    if (Math.abs(raw.x - ref.x) < tol) {
      p.x = ref.x; axisLock = { axis: 'v', ref };
    } else if (Math.abs(raw.y - ref.y) < tol) {
      p.y = ref.y; axisLock = { axis: 'h', ref };
    }
  }
  return p;
}

/* ---------------- the trim tool (last P1) ----------------
   The backend owns the geometry (/api/sketch/trim/*, stateless): pieces are
   fetched for the CURRENT entity list; a click sends the same list back, so
   what is applied is exactly what was highlighted. If the entities changed
   under the pieces (card edit mid-trim), they are refetched, never misused. */

async function fetchTrimPieces() {
  trimPieces = null; trimHover = -1;
  const snapshot = JSON.stringify(skEnts);
  trimFor = snapshot;
  if (!skEnts.length) { updateHint(); draw(); return; }
  try {
    const r = await fetch('/api/sketch/trim/pieces', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: `{"entities":${snapshot}}`,
    });
    const res = await r.json();
    if (tool !== 'trim' || trimFor !== snapshot) return;  // user moved on
    if (res.error) { bus.emit('msg', 'bot', '⚠ ' + res.error); return; }
    trimPieces = res.pieces || [];
  } catch { /* server unreachable — the apply path will say so */ }
  updateHint(); draw();
}

function segDist(p, a, b) {
  const ax = a[0], ay = a[1], dx = b[0] - ax, dy = b[1] - ay;
  const L2 = dx * dx + dy * dy;
  const t = L2
    ? Math.min(Math.max(((p.x - ax) * dx + (p.y - ay) * dy) / L2, 0), 1) : 0;
  return Math.hypot(p.x - (ax + t * dx), p.y - (ay + t * dy));
}

function updateTrimHover(p) {
  if (JSON.stringify(skEnts) !== trimFor) { fetchTrimPieces(); return; }
  const tol = Math.max(snapTolWorld() * 1.2, 0.8);
  let best = -1, bd = tol;
  (trimPieces || []).forEach((piece, i) => {
    for (let k = 0; k + 1 < piece.pts.length; k++) {
      const d = segDist(p, piece.pts[k], piece.pts[k + 1]);
      if (d < bd) { bd = d; best = i; }
    }
  });
  if (best !== trimHover) { trimHover = best; updateHint(); }
}

async function trimClick() {
  if (trimBusy) return;
  if (JSON.stringify(skEnts) !== trimFor) { fetchTrimPieces(); return; }
  if (trimHover < 0 || !trimPieces || !trimPieces[trimHover]) return;
  const piece = trimPieces[trimHover];
  trimBusy = true;
  const res = await postJSON('/api/sketch/trim/apply',
    { entities: skEnts, piece: piece.id }, 'trimming…');
  trimBusy = false;
  if (res.error) return;                     // postJSON already toasted why
  skEnts = res.entities || [];
  selEnt = -1;
  bus.emit('msg', 'bot', res.message || 'trimmed');
  renderEnts();
  fetchTrimPieces();
}

/* ---------------- pointer interaction ---------------- */

let dragging = null;      // {idx, startX, startY, ex, ey} moving an entity
let panning = null;       // {px, py, cx, cy} moving the view

/* shared select/draw logic in PLANE coordinates — the SVG canvas (face
   sketches) and the 3D viewport (plane sketches) both feed points in here */
function pointerDown(raw) {
  if (tool === 'trim') { trimClick(); return 'tool'; }
  if (tool) { placeClick(smartSnap(raw)); return 'tool'; }
  const hit = hitTest(raw);
  if (hit >= 0) {
    selEnt = hit;
    const ent = skEnts[hit];
    const p = snapPt(raw);
    dragging = { idx: hit, startX: p.x, startY: p.y,
                 ex: ent.x || 0, ey: ent.y || 0 };
    renderCards(); draw();
    return 'drag';
  }
  selEnt = -1;
  renderCards(); draw();
  return 'miss';
}

function pointerMove(p) {
  setCoordsReadout(p);
  if (tool === 'trim') { updateTrimHover(p); draw(); return; }
  if (tool === 'path' && pathStart) { ghost = pathGhost(smartSnap(p)); draw(); return; }
  if (tool && clicks.length) { ghost = buildGhost(smartSnap(p)); draw(); return; }
  if (tool) { smartSnap(p); draw(); }         // show snap markers pre-click too
  if (dragging) {
    const ent = skEnts[dragging.idx];
    ent.x = snap(dragging.ex + (p.x - dragging.startX));
    ent.y = snap(dragging.ey + (p.y - dragging.startY));
    draw();
  }
}

function pointerUp() {
  if (dragging) renderCards();
  dragging = null;
}

function setCoordsReadout(p) {
  const el = document.getElementById(inPlane3D() ? 'sk3dCoords' : 'skCoords');
  if (el) el.textContent =
    `x ${fmtLen(snap(p.x), false)}, y ${fmtLen(snap(p.y), false)} ${unitLabel()}`;
}

function onDown(e) {
  if (e.button !== 0) return;
  const raw = worldPoint(e);
  const acted = pointerDown(raw);
  if (acted === 'drag') {
    svg().setPointerCapture(e.pointerId);
  } else if (acted === 'miss') {              // SVG only: drag empty space pans
    panning = { px: raw.x, py: raw.y, cx: view.cx, cy: view.cy };
    svg().setPointerCapture(e.pointerId);
  }
}

function onMove(e) {
  const p = worldPoint(e);
  if (panning) {
    view.cx = panning.cx - (p.x - panning.px);
    view.cy = panning.cy - (p.y - panning.py);
    draw(); return;
  }
  pointerMove(p);
}

function onUp(e) {
  pointerUp(); panning = null;
  try { svg().releasePointerCapture(e.pointerId); } catch {}
}

function onDblClick() {
  if (tool === 'polygon' && clicks.length >= 3) finishPolygon();
  if (tool === 'path' && pathSegs.length >= 1) finishPath();
}

function pathGhost(p) {
  const cur = pathCursor();
  const segs = [...pathSegs];
  if (pendingVia) segs.push({ type: 'arc', via: [pendingVia.x, pendingVia.y],
                              to: [p.x, p.y] });
  else segs.push({ type: 'line', to: [p.x, p.y] });
  return { kind: 'path', mode: 'add', x: 0, y: 0, ghostOpen: true,
           start: [pathStart.x, pathStart.y], segments: segs };
}

function onWheel(e) {
  e.preventDefault();
  const p = worldPoint(e);
  const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
  const ext = Math.max(10, Math.min(2000, view.ext * factor));
  const k = ext / view.ext;
  view.cx = p.x - (p.x - view.cx) * k;
  view.cy = p.y - (p.y - view.cy) * k;
  view.ext = ext;
  draw();
}

/* ---------------- modify tools (P5): mirror / duplicate / offset ---------- */

function modifySel(fn) {
  if (selEnt < 0 || !skEnts[selEnt]) {
    bus.emit('msg', 'bot', '⚠ Select a shape first (click it on the canvas).');
    return;
  }
  const copy = fn(JSON.parse(JSON.stringify(skEnts[selEnt])));
  if (!copy) return;
  skEnts.push(copy);
  selEnt = skEnts.length - 1;
  renderEnts();
}

function mirrorEntity(e, dir) {
  // dir 'v' = across the vertical Y axis (x -> -x); 'h' = across X (y -> -y)
  const fx = dir === 'v' ? -1 : 1, fy = dir === 'h' ? -1 : 1;
  e.x = (e.x || 0) * fx;
  e.y = (e.y || 0) * fy;
  if (e.rotation !== undefined)
    e.rotation = dir === 'v' ? 180 - e.rotation : -e.rotation;
  if (e.points) e.points = e.points.map(p => [p[0] * fx, p[1] * fy]);
  if (e.start) e.start = [e.start[0] * fx, e.start[1] * fy];
  if (e.segments) e.segments = e.segments.map(s => ({
    ...s,
    to: [s.to[0] * fx, s.to[1] * fy],
    ...(s.via ? { via: [s.via[0] * fx, s.via[1] * fy] } : {}),
  }));
  return e;
}

function duplicateEntity(e) {
  e.x = (e.x || 0) + 10;
  e.y = (e.y || 0) + 10;
  return e;
}

function offsetEntity(e, d) {
  const grow = (v, amt) => Math.max(v + amt, 0.5);
  if (e.kind === 'circle') { e.r = grow(e.r, d); return e; }
  if (e.kind === 'regular_polygon') { e.radius = grow(e.radius, d); return e; }
  if (e.kind === 'rectangle') {
    e.w = grow(e.w, 2 * d); e.h = grow(e.h, 2 * d); return e;
  }
  if (e.kind === 'ellipse') {
    e.rx = grow(e.rx, d); e.ry = grow(e.ry, d); return e;
  }
  if (e.kind === 'slot') { e.height = grow(e.height, 2 * d); return e; }
  bus.emit('msg', 'bot',
    '⚠ Offset works on circles, rectangles, ellipses, slots and N-gons — ' +
    'not on polygons/paths yet.');
  return null;
}

/* ---------------- arc / path geometry helpers ---------------- */

function circleFrom3(a, m, b) {
  const d = 2 * (a.x * (m.y - b.y) + m.x * (b.y - a.y) + b.x * (a.y - m.y));
  if (Math.abs(d) < 1e-9) return null;                 // collinear
  const s = p => p.x * p.x + p.y * p.y;
  return {
    cx: (s(a) * (m.y - b.y) + s(m) * (b.y - a.y) + s(b) * (a.y - m.y)) / d,
    cy: (s(a) * (b.x - m.x) + s(m) * (a.x - b.x) + s(b) * (m.x - a.x)) / d,
  };
}

function sampleArc(a, m, b, n = 20) {
  const c = circleFrom3(a, m, b);
  if (!c) return [a, b];
  const r = Math.hypot(a.x - c.cx, a.y - c.cy);
  const ang = p => Math.atan2(p.y - c.cy, p.x - c.cx);
  const a0 = ang(a), am = ang(m), a1 = ang(b);
  const ccw = (from, to) => (to - from + 4 * Math.PI) % (2 * Math.PI);
  const pts = [];
  if (ccw(a0, am) <= ccw(a0, a1)) {                    // ccw passes the via pt
    const sweep = ccw(a0, a1);
    for (let i = 0; i <= n; i++) {
      const t = a0 + sweep * i / n;
      pts.push({ x: c.cx + r * Math.cos(t), y: c.cy + r * Math.sin(t) });
    }
  } else {
    const sweep = 2 * Math.PI - ccw(a0, a1);
    for (let i = 0; i <= n; i++) {
      const t = a0 - sweep * i / n;
      pts.push({ x: c.cx + r * Math.cos(t), y: c.cy + r * Math.sin(t) });
    }
  }
  return pts;
}

function pathOutline(e) {
  const ox = e.x || 0, oy = e.y || 0;
  let cur = { x: e.start[0], y: e.start[1] };
  const pts = [{ ...cur }];
  for (const s of e.segments || []) {
    const to = { x: s.to[0], y: s.to[1] };
    if (s.type === 'arc' && s.via)
      pts.push(...sampleArc(cur, { x: s.via[0], y: s.via[1] }, to).slice(1));
    else pts.push(to);
    cur = to;
  }
  return pts.map(p => ({ x: p.x + ox, y: p.y + oy }));
}

/* ---------------- click-to-place ---------------- */

function placeClick(p) {
  if (tool === 'path') { pathClick(p); return; }
  clicks.push(p);

  if (tool === 'polygon') {
    // click near the first point closes the shape
    if (clicks.length >= 3 && dist(p, clicks[0]) < snapTolWorld() * 1.4) {
      clicks.pop(); finishPolygon();
    }
    ghost = buildGhost(p); draw(); updateHint();
    return;
  }

  if (clicks.length === 2) {
    const ent = twoClickEntity(tool, clicks[0], clicks[1]);
    if (ent) { skEnts.push(ent); selEnt = skEnts.length - 1; }
    clicks = []; ghost = null;
    renderEnts(); updateHint();
  } else {
    ghost = buildGhost(p); draw(); updateHint();
  }
}

function twoClickEntity(kind, a, b) {
  const d = Math.max(dist(a, b), 0.5);
  if (kind === 'circle')
    return { kind, mode: 'add', x: a.x, y: a.y, r: snap(d) || 1 };
  if (kind === 'regular_polygon')
    return { kind, mode: 'add', x: a.x, y: a.y, radius: snap(d) || 1,
             sides: 6, rotation: 0 };
  if (kind === 'rectangle')
    return { kind, mode: 'add',
             x: snap((a.x + b.x) / 2), y: snap((a.y + b.y) / 2),
             w: Math.max(Math.abs(b.x - a.x), 1),
             h: Math.max(Math.abs(b.y - a.y), 1), rotation: 0 };
  if (kind === 'ellipse')
    return { kind, mode: 'add', x: a.x, y: a.y,
             rx: Math.max(Math.abs(b.x - a.x), 1),
             ry: Math.max(Math.abs(b.y - a.y), 1), rotation: 0 };
  if (kind === 'slot')
    return { kind, mode: 'add',
             x: snap((a.x + b.x) / 2), y: snap((a.y + b.y) / 2),
             length: snap(d) || 1, height: 10,
             rotation: Math.round(Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI) };
  return null;
}

/* ---------------- the path tool (chained lines + arcs) ---------------- */

function pathClick(p) {
  if (!pathStart) { pathStart = p; updateHint(); draw(); return; }

  // clicking near the start closes the profile
  const closeR = snapTolWorld() * 1.4;
  if (pathSegs.length >= 1 && !pendingVia
      && dist(p, pathStart) < closeR) { finishPath(); return; }

  if (segMode === 'arc') {
    if (!pendingVia) { pendingVia = p; updateHint(); draw(); return; }
    pathSegs.push({ type: 'arc', via: [pendingVia.x, pendingVia.y],
                    to: [p.x, p.y] });
    pendingVia = null;
  } else {
    pathSegs.push({ type: 'line', to: [p.x, p.y] });
  }
  updateHint(); draw();
}

function finishPath() {
  if (!pathStart || pathSegs.length < 1) return;
  skEnts.push({ kind: 'path', mode: 'add', x: 0, y: 0,
                start: [pathStart.x, pathStart.y], segments: pathSegs });
  selEnt = skEnts.length - 1;
  pathStart = null; pathSegs = []; pendingVia = null;
  renderEnts(); updateHint();
}

function pathCursor() {
  if (!pathSegs.length) return pathStart;
  const last = pathSegs[pathSegs.length - 1].to;
  return { x: last[0], y: last[1] };
}

function finishPolygon() {
  const pts = clicks.map(p => [p.x, p.y]);
  skEnts.push({ kind: 'polygon', mode: 'add', x: 0, y: 0, points: pts });
  selEnt = skEnts.length - 1;
  clicks = []; ghost = null;
  renderEnts(); updateHint();
}

function buildGhost(p) {
  if (!clicks.length) return null;
  if (tool === 'polygon')
    return { kind: 'polygon', mode: 'add', x: 0, y: 0, ghostOpen: true,
             points: [...clicks.map(q => [q.x, q.y]), [p.x, p.y]] };
  return twoClickEntity(tool, clicks[0], p);
}

/* ---------------- hit testing ---------------- */

function hitTest(p) {
  for (let i = skEnts.length - 1; i >= 0; i--) {
    const e = skEnts[i];
    const lx = p.x - (e.x || 0), ly = p.y - (e.y || 0);
    // un-rotate the point into the entity's local frame
    const a = -(e.rotation || 0) * Math.PI / 180;
    const rx = lx * Math.cos(a) - ly * Math.sin(a);
    const ry = lx * Math.sin(a) + ly * Math.cos(a);
    if (e.kind === 'circle' && Math.hypot(lx, ly) <= e.r) return i;
    if (e.kind === 'regular_polygon' && Math.hypot(lx, ly) <= e.radius) return i;
    if (e.kind === 'rectangle'
        && Math.abs(rx) <= e.w / 2 && Math.abs(ry) <= e.h / 2) return i;
    if (e.kind === 'ellipse'
        && (rx / e.rx) ** 2 + (ry / e.ry) ** 2 <= 1) return i;
    if (e.kind === 'slot'
        && Math.abs(rx) <= e.length / 2
        && Math.abs(ry) <= e.height / 2) return i;
    if (e.kind === 'polygon' && e.points
        && pointInPolygon(lx, ly, e.points)) return i;
    if (e.kind === 'path' && e.start) {
      const pts = pathOutline(e).map(q => [q.x, q.y]);
      if (pointInPolygon(p.x, p.y, pts)) return i;
    }
  }
  return -1;
}

function pointInPolygon(x, y, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
    if (((yi > y) !== (yj > y))
        && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

/* ---------------- entity cards (numeric editing) ---------------- */

function renderEnts() { renderCards(); draw(); }

function renderCards() {
  const box = document.getElementById('skEntities');
  box.innerHTML = '';
  skEnts.forEach((e, i) => {
    const card = document.createElement('div');
    card.className = 'skent' + (i === selEnt ? ' sel' : '');
    card.onclick = () => { selEnt = i; renderCards(); draw(); };
    const head = document.createElement('div'); head.className = 'eh';
    head.innerHTML = `<b>${OP_ICONS[e.kind] || ''} ${e.kind}</b>`;
    const mode = document.createElement('select');
    mode.innerHTML = '<option value="add">add</option>' +
                     '<option value="subtract">cut</option>';
    mode.value = e.mode;
    mode.disabled = i === 0;                 // first must be additive
    mode.onchange = () => { e.mode = mode.value; draw(); };
    const del = document.createElement('button'); del.className = 'del';
    del.textContent = '✕';
    del.onclick = ev => { ev.stopPropagation();
      skEnts.splice(i, 1); if (selEnt >= skEnts.length) selEnt = -1;
      renderEnts(); };
    head.append(mode, del);
    card.appendChild(head);

    const f = document.createElement('div'); f.className = 'ef';
    for (const k of Object.keys(e)) {
      if (['kind', 'mode', 'points', 'ghostOpen', 'start', 'segments']
          .includes(k)) continue;
      const lab = document.createElement('label');
      lab.textContent = k;
      const inp = document.createElement('input'); inp.value = e[k];
      inp.onclick = ev => ev.stopPropagation();
      inp.oninput = () => { e[k] = Number(inp.value) || 0; draw(); };
      lab.appendChild(inp); f.appendChild(lab);
    }
    for (const jsonKey of ['points', 'start', 'segments']) {
      if (!e[jsonKey]) continue;
      const lab = document.createElement('label');
      lab.textContent = jsonKey;
      const inp = document.createElement('input'); inp.style.width = '150px';
      inp.value = JSON.stringify(e[jsonKey]);
      inp.onclick = ev => ev.stopPropagation();
      inp.oninput = () => {
        try { e[jsonKey] = JSON.parse(inp.value); draw(); } catch {}
      };
      lab.appendChild(inp); f.appendChild(lab);
    }
    card.appendChild(f);
    box.appendChild(card);
  });
}

function updateHint() {
  const el = document.getElementById(inPlane3D() ? 'sk3dHelp' : 'skHelp');
  if (inPlane3D() && edgeOnView) {
    el.textContent = '⚠ You are looking along the sketch plane — rotate back, '
      + 'or press Look At, to keep drawing';
    return;
  }
  if (tool === 'path') {
    const msg = !pathStart ? 'Click the START point of your profile'
      : pendingVia ? 'Arc: now click the END point'
      : segMode === 'arc' ? 'Arc: click a point the arc passes THROUGH'
      : 'Click the next point · click the start (or double-click) to close';
    el.innerHTML = '';
    const mk = (label, mode) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.style.cssText = 'margin-right:6px;padding:1px 10px;border-radius:5px;' +
        'font:inherit;font-size:11.5px;cursor:pointer;border:1px solid ' +
        (segMode === mode ? 'var(--accent)' : 'var(--line)') + ';background:' +
        (segMode === mode ? 'var(--accent2)' : 'var(--panel2)') +
        ';color:' + (segMode === mode ? 'var(--accent)' : 'var(--text)');
      b.onclick = () => { segMode = mode; pendingVia = null; updateHint(); };
      return b;
    };
    el.append(mk('— Line', 'line'), mk('◠ Arc', 'arc'),
              document.createTextNode(' ' + msg));
    return;
  }
  if (tool === 'trim') {
    el.textContent = trimPieces === null && skEnts.length
      ? 'Trim: finding crossings…'
      : trimHover >= 0 && trimPieces?.[trimHover]?.whole
        ? 'Trim: this shape crosses nothing — a click deletes the WHOLE shape'
        : 'Trim: hover a segment between crossings (turns red), click to ' +
          'remove it · outer boundaries are protected';
    return;
  }
  if (!tool) el.textContent =
    'Pick a shape, then click to draw — clicks snap to centers/corners of ' +
    'existing shapes · drag shapes to move · wheel zooms';
  else if (tool === 'polygon') el.textContent = clicks.length
    ? 'Click the next corner · double-click (or click the first point) to close'
    : 'Polygon: click each corner, double-click to close';
  else el.textContent = clicks.length
    ? 'Now click to set the size'
    : ({ circle: 'Circle: click the CENTER point',
         rectangle: 'Rectangle: click the FIRST corner',
         ellipse: 'Ellipse: click the center',
         slot: 'Slot: click the start center',
         regular_polygon: 'N-gon: click the center' }[tool] || 'Click to place');
}

/* ---------------- on-canvas dimensions (P4) ---------------- */

function fmt(v) { return fmtLen(v, false); }   // dimension labels in display unit

function dimText(x, y, text, fs) {
  return `<text x="${x}" y="${-y}" font-size="${fs}" fill="#dde2ea"
    text-anchor="middle" style="paint-order:stroke" stroke="#0f1115"
    stroke-width="${fs / 5}" font-family="Segoe UI, sans-serif">${text}</text>`;
}

function dimensionSVG(e, fs) {
  const x = e.x || 0, y = e.y || 0, off = fs * 1.2;
  if (e.kind === 'circle') return dimText(x, y + off, `R ${fmt(e.r)}`, fs);
  if (e.kind === 'regular_polygon')
    return dimText(x, y + off, `R ${fmt(e.radius)} × ${e.sides}`, fs);
  if (e.kind === 'rectangle')
    return dimText(x, y + off, `${fmt(e.w)} × ${fmt(e.h)}`, fs);
  if (e.kind === 'ellipse')
    return dimText(x, y + off, `${fmt(e.rx)} × ${fmt(e.ry)}`, fs);
  if (e.kind === 'slot')
    return dimText(x, y + off, `L ${fmt(e.length)}  H ${fmt(e.height)}`, fs);
  if (e.kind === 'path' && e.ghostOpen && e.segments?.length) {
    // live length of the segment being drawn
    const last = e.segments[e.segments.length - 1];
    const from = e.segments.length > 1
      ? e.segments[e.segments.length - 2].to : e.start;
    const mx = (from[0] + last.to[0]) / 2, my = (from[1] + last.to[1]) / 2;
    const len = Math.hypot(last.to[0] - from[0], last.to[1] - from[1]);
    return dimText(mx, my + off, fmt(len), fs);
  }
  return '';
}

/* ---------------- rendering ---------------- */

function entitySVG(e, opts = {}) {
  const col = e.mode === 'subtract' ? '#ff5d5d' : '#43c579';
  const fill = opts.ghost ? 'none'
    : e.mode === 'subtract' ? 'rgba(255,93,93,.10)' : 'rgba(67,197,121,.13)';
  const sw = opts.sel ? 2 : 1;
  const dash = opts.ghost ? ' stroke-dasharray="3 3"' : '';
  const x = e.x || 0, y = -(e.y || 0);
  const st = `fill="${fill}" stroke="${col}" stroke-width="${sw}"` +
             ` vector-effect="non-scaling-stroke"${dash}`;
  const rot = `transform="rotate(${-(e.rotation || 0)} ${x} ${y})"`;
  if (e.kind === 'rectangle')
    return `<rect x="${x - e.w / 2}" y="${y - e.h / 2}" width="${e.w}" height="${e.h}" ${st} ${rot}/>`;
  if (e.kind === 'circle')
    return `<circle cx="${x}" cy="${y}" r="${e.r}" ${st}/>`;
  if (e.kind === 'ellipse')
    return `<ellipse cx="${x}" cy="${y}" rx="${e.rx}" ry="${e.ry}" ${st} ${rot}/>`;
  if (e.kind === 'slot') {
    const r = e.height / 2;
    return `<rect x="${x - e.length / 2}" y="${y - r}" width="${e.length}" height="${e.height}" rx="${r}" ${st} ${rot}/>`;
  }
  if (e.kind === 'regular_polygon') {
    const pts = [];
    for (let k = 0; k < e.sides; k++) {
      const a = Math.PI / 2 + k * 2 * Math.PI / e.sides;
      pts.push(`${x + e.radius * Math.cos(a)},${y - e.radius * Math.sin(a)}`);
    }
    return `<polygon points="${pts.join(' ')}" ${st} ${rot}/>`;
  }
  if (e.kind === 'polygon' && e.points) {
    const pts = e.points.map(p =>
      `${(e.x || 0) + p[0]},${-((e.y || 0) + p[1])}`).join(' ');
    return e.ghostOpen
      ? `<polyline points="${pts}" ${st}/>`
      : `<polygon points="${pts}" ${st}/>`;
  }
  if (e.kind === 'path' && e.start) {
    const pts = pathOutline(e).map(q => `${q.x},${-q.y}`).join(' ');
    return e.ghostOpen
      ? `<polyline points="${pts}" ${st}/>`
      : `<polygon points="${pts}" ${st}/>`;
  }
  return '';
}

function draw() {
  if (inPlane3D()) { draw3D(); return; }          // plane sketches render in 3D
  const el = svg();
  const { cx, cy, ext } = view;
  // viewBox matches the canvas's REAL aspect ratio so the grid fills the whole
  // (wide) canvas edge-to-edge like Fusion — a square viewBox letterboxed it,
  // leaving the grid stuck in a small central square with dark empty sides.
  const rect = el.getBoundingClientRect();
  const aspect = rect.height > 0 ? rect.width / rect.height : 1;
  const ex = ext * aspect, ey = ext;              // half-extents (x wider on wide canvas)
  el.setAttribute('viewBox', `${cx - ex} ${-cy - ey} ${2 * ex} ${2 * ey}`);

  // grid step = the configured grid size, coarsened while zoomed out so lines
  // never crowd (keep at least ~7px apart at the current zoom)
  let step = Math.max(0.1, SETTINGS.gridMm);
  while ((2 * ey) / step > 90) step *= 2;
  let out = '';
  const x0 = Math.floor((cx - ex) / step) * step;
  const y0 = Math.floor((-cy - ey) / step) * step;
  for (let g = x0; g <= cx + ex; g += step)
    out += `<line x1="${g}" y1="${-cy - ey}" x2="${g}" y2="${-cy + ey}" stroke="#20242e" stroke-width="0.5" vector-effect="non-scaling-stroke"/>`;
  for (let g = y0; g <= -cy + ey; g += step)
    out += `<line x1="${cx - ex}" y1="${g}" x2="${cx + ex}" y2="${g}" stroke="#20242e" stroke-width="0.5" vector-effect="non-scaling-stroke"/>`;
  out += `<line x1="${cx - ex}" y1="0" x2="${cx + ex}" y2="0" stroke="#3a4150" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
  out += `<line x1="0" y1="${-cy - ey}" x2="0" y2="${-cy + ey}" stroke="#3a4150" stroke-width="1" vector-effect="non-scaling-stroke"/>`;

  // selected-surface reference (grey, non-editable): outer minus holes
  if (faceRef && faceRef.outer.length) {
    const ring = pts => pts.map(p => `${p[0]},${-p[1]}`).join(' ');
    const path = ['M ' + faceRef.outer.map(p => `${p[0]} ${-p[1]}`).join(' L ') + ' Z'];
    for (const h of faceRef.holes)
      path.push('M ' + h.map(p => `${p[0]} ${-p[1]}`).join(' L ') + ' Z');
    out += `<path d="${path.join(' ')}" fill="#5a6472" fill-rule="evenodd"
      fill-opacity="0.22" stroke="#8a97a8" stroke-width="1.5"
      vector-effect="non-scaling-stroke"/>`;
    for (const h of faceRef.holes)
      out += `<polygon points="${ring(h)}" fill="none" stroke="#8a97a8"
        stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
  }

  skEnts.forEach((e, i) => out += entitySVG(e, { sel: i === selEnt }));
  if (ghost) out += entitySVG(ghost, { ghost: true });
  if (tool === 'trim' && trimPieces && trimHover >= 0) {
    const pl = trimPieces[trimHover].pts.map(q => `${q[0]},${-q[1]}`).join(' ');
    out += `<polyline points="${pl}" fill="none" stroke="#ff3333"
      stroke-width="3.5" vector-effect="non-scaling-stroke" opacity="0.95"/>`;
  }
  for (const c of clicks)
    out += `<circle cx="${c.x}" cy="${-c.y}" r="${ext / 90}" fill="#4da3ff"/>`;
  if (tool === 'path' && pathStart) {
    out += `<circle cx="${pathStart.x}" cy="${-pathStart.y}" r="${ext / 60}"
      fill="none" stroke="#4da3ff" stroke-width="1.5"
      vector-effect="non-scaling-stroke"/>`;      // close target
    for (const s of pathSegs)
      out += `<circle cx="${s.to[0]}" cy="${-s.to[1]}" r="${ext / 110}" fill="#4da3ff"/>`;
    if (pendingVia)
      out += `<circle cx="${pendingVia.x}" cy="${-pendingVia.y}" r="${ext / 110}" fill="#d9a23c"/>`;
  }

  // P4: snap marker, axis guide, live dimensions
  const fs = ext / 26;
  if (axisLock) {
    const r = axisLock.ref;
    const guide = axisLock.axis === 'v'
      ? `<line x1="${r.x}" y1="${-cy - ey}" x2="${r.x}" y2="${-cy + ey}"`
      : `<line x1="${cx - ex}" y1="${-r.y}" x2="${cx + ex}" y2="${-r.y}"`;
    out += guide + ` stroke="#4da3ff" stroke-width="1" stroke-dasharray="4 4"
      vector-effect="non-scaling-stroke" opacity="0.7"/>`;
  }
  if (activeSnap) {
    const s = activeSnap, m = ext / 70;
    out += `<path d="M ${s.x - m} ${-s.y} L ${s.x + m} ${-s.y}
      M ${s.x} ${-s.y - m} L ${s.x} ${-s.y + m}" stroke="#ffb85c"
      stroke-width="2" vector-effect="non-scaling-stroke"/>`;
    out += `<rect x="${s.x - m}" y="${-s.y - m}" width="${2 * m}" height="${2 * m}"
      fill="none" stroke="#ffb85c" stroke-width="1"
      vector-effect="non-scaling-stroke"/>`;
    out += dimText(s.x, s.y - m * 2.2, s.label, fs * 0.85);
  }
  if (ghost) out += dimensionSVG(ghost, fs);
  else if (selEnt >= 0 && skEnts[selEnt]) out += dimensionSVG(skEnts[selEnt], fs);

  el.innerHTML = out;
  const gridEl = document.getElementById('skGrid');
  if (gridEl) gridEl.textContent = `grid ${fmtLen(step, false)} ${unitLabel()}`;
  updateDimEditor();
}

/* ---------------- 3D sketch mode rendering (plane sketches) ----------------
   Same entities, same tool state — but drawn as real geometry on the plane
   via sketch3d.js, with HTML labels projected over the viewport. */

function circleOutline(cx, cy, r, n = 48) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = i * 2 * Math.PI / n;
    pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
  }
  return pts;
}

/* entity -> plane-local outline points (rotation applied) */
function outlinePts(e) {
  const x = e.x || 0, y = e.y || 0, a = (e.rotation || 0) * Math.PI / 180;
  const rot = pts => pts.map(([px, py]) => [
    x + px * Math.cos(a) - py * Math.sin(a),
    y + px * Math.sin(a) + py * Math.cos(a)]);
  if (e.kind === 'rectangle')
    return { closed: true, pts: rot([[-e.w / 2, -e.h / 2], [e.w / 2, -e.h / 2],
                                     [e.w / 2, e.h / 2], [-e.w / 2, e.h / 2]]) };
  if (e.kind === 'circle')
    return { closed: true, pts: circleOutline(x, y, e.r) };
  if (e.kind === 'ellipse') {
    const pts = [];
    for (let i = 0; i < 48; i++) {
      const t = i * 2 * Math.PI / 48;
      pts.push([e.rx * Math.cos(t), e.ry * Math.sin(t)]);
    }
    return { closed: true, pts: rot(pts) };
  }
  if (e.kind === 'slot') {
    const r = e.height / 2, hx = Math.max(e.length / 2 - r, 0), pts = [];
    for (let i = 0; i <= 12; i++) {                  // right cap  -90° -> +90°
      const t = -Math.PI / 2 + i * Math.PI / 12;
      pts.push([hx + r * Math.cos(t), r * Math.sin(t)]);
    }
    for (let i = 0; i <= 12; i++) {                  // left cap   +90° -> +270°
      const t = Math.PI / 2 + i * Math.PI / 12;
      pts.push([-hx + r * Math.cos(t), r * Math.sin(t)]);
    }
    return { closed: true, pts: rot(pts) };
  }
  if (e.kind === 'regular_polygon') {
    const pts = [];
    for (let k = 0; k < e.sides; k++) {
      const t = Math.PI / 2 + k * 2 * Math.PI / e.sides;
      pts.push([e.radius * Math.cos(t), e.radius * Math.sin(t)]);
    }
    return { closed: true, pts: rot(pts) };
  }
  if (e.kind === 'polygon' && e.points)
    return { closed: !e.ghostOpen,
             pts: e.points.map(p => [x + p[0], y + p[1]]) };
  if (e.kind === 'path' && e.start)
    return { closed: !e.ghostOpen,
             pts: pathOutline(e).map(q => [q.x, q.y]) };
  return null;
}

function draw3D() {
  const ADD = 0x43c579, CUT = 0xff5d5d, SEL = 0x4da3ff;
  const shapes = [];
  const push = (e, i, isGhost) => {
    const o = outlinePts(e);
    if (!o || o.pts.length < 2) return;
    const col = e.mode === 'subtract' ? CUT : ADD;
    shapes.push({ pts: o.pts, closed: o.closed,
                  color: !isGhost && i === selEnt ? SEL : col,
                  fill: isGhost || !o.closed ? null : col,
                  fillOpacity: e.mode === 'subtract' ? 0.10 : 0.13,
                  dashed: !!isGhost });
  };
  skEnts.forEach((e, i) => push(e, i, false));
  if (ghost) push(ghost, -1, true);

  const dR = Math.max(snapTol3d * 0.35, 0.6);
  const dots = clicks.map(c => ({ x: c.x, y: c.y, r: dR, color: 0x4da3ff }));
  if (tool === 'trim' && trimPieces && trimHover >= 0) {
    const piece = trimPieces[trimHover];        // the doomed segment, in red
    shapes.push({ pts: piece.pts, closed: false, color: 0xff3333 });
    const end = piece.pts[piece.pts.length - 1];
    dots.push({ x: piece.pts[0][0], y: piece.pts[0][1], r: dR * 0.9,
                color: 0xff3333 });
    dots.push({ x: end[0], y: end[1], r: dR * 0.9, color: 0xff3333 });
  }
  if (tool === 'path' && pathStart) {
    dots.push({ x: pathStart.x, y: pathStart.y, r: dR * 1.7,
                color: 0x4da3ff, ring: true });          // the close target
    for (const s of pathSegs)
      dots.push({ x: s.to[0], y: s.to[1], r: dR * 0.8, color: 0x4da3ff });
    if (pendingVia)
      dots.push({ x: pendingVia.x, y: pendingVia.y, r: dR * 0.8, color: 0xd9a23c });
  }

  renderSketch3D({
    shapes, dots,
    cross: activeSnap
      ? { x: activeSnap.x, y: activeSnap.y, size: Math.max(snapTol3d * 0.5, 1) }
      : null,
    guide: axisLock ? { axis: axisLock.axis, ref: axisLock.ref } : null,
  });
  updateFloatingLabels();
}

/* dimension label text + anchor (same semantics as the SVG dimensionSVG) */
function dimLabel(e) {
  const x = e.x || 0, y = e.y || 0;
  const off = Math.max(snapTol3d * 1.2, 2);
  if (e.kind === 'circle') return { x, y: y + off, text: `R ${fmt(e.r)}` };
  if (e.kind === 'regular_polygon')
    return { x, y: y + off, text: `R ${fmt(e.radius)} × ${e.sides}` };
  if (e.kind === 'rectangle')
    return { x, y: y + off, text: `${fmt(e.w)} × ${fmt(e.h)}` };
  if (e.kind === 'ellipse')
    return { x, y: y + off, text: `${fmt(e.rx)} × ${fmt(e.ry)}` };
  if (e.kind === 'slot')
    return { x, y: y + off, text: `L ${fmt(e.length)}  H ${fmt(e.height)}` };
  if (e.kind === 'path' && e.ghostOpen && e.segments?.length) {
    const last = e.segments[e.segments.length - 1];
    const from = e.segments.length > 1
      ? e.segments[e.segments.length - 2].to : e.start;
    const len = Math.hypot(last.to[0] - from[0], last.to[1] - from[1]);
    return { x: (from[0] + last.to[0]) / 2,
             y: (from[1] + last.to[1]) / 2 + off, text: fmt(len) };
  }
  return null;
}

/* place a floating HTML label at a plane-local point (hidden off-pane) */
function placeFloat(id, at, text) {
  const el = document.getElementById(id);
  if (!el) return;
  const scr = at ? planeToScreen(at.x, at.y) : null;
  const pane = document.getElementById('viewportPane').getBoundingClientRect();
  if (!scr || scr.x < pane.left || scr.x > pane.right
      || scr.y < pane.top || scr.y > pane.bottom) {
    el.style.display = 'none';
    return;
  }
  el.textContent = text;
  el.style.left = (scr.x - pane.left) + 'px';
  el.style.top = (scr.y - pane.top) + 'px';
  el.style.display = 'block';
}

/* live dimension + snap tag + numeric dim editor — re-placed on every draw
   AND on every camera move while orbiting ('sk3d-view') */
function updateFloatingLabels() {
  const e = ghost || (selEnt >= 0 ? skEnts[selEnt] : null) || null;
  const d = e ? dimLabel(e) : null;
  placeFloat('sk3dDim', d, d ? d.text : '');
  placeFloat('sk3dSnap', activeSnap
    ? { x: activeSnap.x, y: activeSnap.y + Math.max(snapTol3d, 1.6) } : null,
    activeSnap ? activeSnap.label : '');
  updateDimEditor3D();
}

function updateDimEditor3D() {
  const el = document.getElementById('skDimEdit3d');
  if (!el) return;
  const e = selEnt >= 0 ? skEnts[selEnt] : null;
  const ok = inPlane3D() && e && DIM_KEYS[e.kind] && !clicks.length && !ghost;
  if (!ok) { el.style.display = 'none'; return; }
  if (dimEditFor !== selEnt || !el.childElementCount) {
    buildDimEditor(e, el);
    dimEditFor = selEnt;
  }
  const scr = planeToScreen(e.x || 0, e.y || 0);
  if (!scr) { el.style.display = 'none'; return; }
  const pane = document.getElementById('viewportPane').getBoundingClientRect();
  el.style.left = (scr.x - pane.left + 16) + 'px';
  el.style.top = (scr.y - pane.top + 16) + 'px';
  el.style.display = 'flex';
}

/* ---------------- inline on-canvas dimension entry (Step 3) ---------------- */
// type exact sizes right on the canvas next to the shape — no side box.
const DIM_KEYS = {
  circle: [['r', 'R']],
  rectangle: [['w', 'W'], ['h', 'H']],
  ellipse: [['rx', 'Rx'], ['ry', 'Ry']],
  slot: [['length', 'L'], ['height', 'H']],
  regular_polygon: [['radius', 'R'], ['sides', 'N']],
};
let dimEditFor = -1;

function updateDimEditor() {
  const el = document.getElementById('skDimEdit');
  if (!el) return;
  const inSketch = dlg().classList.contains('docked');   // plane OR face sketch
  const e = skEnts[selEnt];
  const ok = inSketch && e && DIM_KEYS[e.kind] && !clicks.length && !ghost;
  if (!ok) { el.style.display = 'none'; dimEditFor = -1; return; }
  if (dimEditFor !== selEnt) { buildDimEditor(e); dimEditFor = selEnt; }
  const s = svg().createSVGPoint(); s.x = e.x || 0; s.y = -(e.y || 0);
  const scr = s.matrixTransform(svg().getScreenCTM());
  const wrap = document.getElementById('sketchCanvasWrap').getBoundingClientRect();
  el.style.left = (scr.x - wrap.left + 14) + 'px';
  el.style.top = (scr.y - wrap.top + 14) + 'px';
  el.style.display = 'flex';
}

function buildDimEditor(e, el = document.getElementById('skDimEdit')) {
  el.innerHTML = '';
  for (const [key, label] of DIM_KEYS[e.kind]) {
    const w = document.createElement('label');
    w.innerHTML = `<span>${label}</span>`;
    const inp = document.createElement('input');
    inp.type = 'number'; inp.step = 'any';
    inp.value = key === 'sides' ? e.sides : fmtLen(e[key] ?? 0, false);
    inp.onkeydown = ev => { ev.stopPropagation(); if (ev.key === 'Enter') inp.blur(); };
    inp.oninput = () => {
      const v = Number(inp.value);
      if (isNaN(v)) return;
      e[key] = key === 'sides' ? Math.max(3, Math.round(v)) : toMm(v);
      draw();
    };
    w.appendChild(inp); el.appendChild(w);
  }
}

/* ---------------- create the feature(s) ---------------- */

async function create() {
  const clean = skEnts.filter(e => !e.ghostOpen);
  if (!clean.length) {
    bus.emit('msg', 'bot', '⚠ The sketch is empty — pick a shape and click ' +
      'on the canvas to draw first.');
    return;
  }
  if (clean[0].mode === 'subtract') clean[0].mode = 'add';
  const entities = clean.map(e => {
    const o = { kind: e.kind, mode: e.mode };
    for (const k of Object.keys(e))
      if (!['kind', 'mode', 'ghostOpen'].includes(k)) o[k] = e[k];
    return o;
  });
  exitMode();
  const id = document.getElementById('skName').value || 'sketch1';

  if (skEditId) {
    // editing an existing sketch: replace its entities/plane/offset in place
    const doc = await postJSON('/api/feature/params', {
      feature_id: skEditId,
      params: { plane: document.getElementById('skPlane').value,
                offset: Number(document.getElementById('skOffset').value) || 0,
                entities } }, 'updating sketch…');
    loadMesh();
    const f = (doc.features || []).find(x => x.id === skEditId);
    bus.emit('msg', 'bot', doc.error || (f && f.status === 'failed')
      ? `⚠ Sketch "${skEditId}" update problem: ${doc.error || f.problems.join('; ')}`
      : `Sketch "${skEditId}" updated — downstream features rebuilt.`);
    skEditId = null;
    return;
  }

  if (skOnFace) {
    // one guided action: sketch on face -> extrude -> join/cut with the body.
    // Each step is CHECKED — on failure the partial features are removed and
    // the user gets the real error, never a false "pocket cut" success.
    const op = document.getElementById('skOp').value;
    const depth = Number(document.getElementById('skDepth').value) || 10;
    const added = [];
    let problem =
      await addChecked({ id, op: 'sketch_on_face',
        params: { face_center: skOnFace.center, face_normal: skOnFace.normal,
                  entities },
        inputs: [skOnFace.inputId] }, added);
    if (!problem) problem =
      await addChecked({ id: id + '_solid', op: 'extrude',
        params: { amount: depth }, inputs: [id] }, added);
    if (!problem && op !== 'new') problem =
      await addChecked({ id: id + (op === 'cut' ? '_pocket' : '_boss'),
        op: op === 'cut' ? 'cut' : 'fuse',
        inputs: [skOnFace.inputId, id + '_solid'] }, added);
    loadMesh();
    if (problem) {
      bus.emit('msg', 'bot', `⚠ ${op === 'cut' ? 'Pocket' : op === 'join'
        ? 'Boss' : 'Extrude'} failed: ${problem} The partial features were removed.`);
      return;
    }
    bus.emit('msg', 'bot',
      op === 'cut' ? `Pocket cut into the face (depth ${depth}mm).`
      : op === 'join' ? `Boss added on the face (height ${depth}mm).`
      : `New body extruded from the face (${depth}mm).`);
  } else {
    const doc = await postJSON('/api/feature/add', {
      id, op: 'sketch',
      params: { plane: document.getElementById('skPlane').value,
                offset: Number(document.getElementById('skOffset').value) || 0,
                entities },
      inputs: [] });
    loadMesh(true);          // the sketch now shows in the viewport (green)
    const f = (doc.features || []).find(x => x.id === id);
    if (doc.error || (f && f.status === 'failed')) {
      bus.emit('msg', 'bot', `⚠ Sketch "${id}" has a problem: ` +
        (doc.error || f.problems.join('; ')));
    } else {
      // Fusion: finishing a sketch does NOT auto-anything — no popup box. The
      // sketch shows in the viewport; use Create → Extrude/Revolve when ready.
      bus.emit('msg', 'bot', `Sketch "${id}" created. Use Create → Extrude or ` +
        `Revolve to turn it into a solid.`);
    }
  }
}

/* Add one feature and verify it actually BUILT. On failure, remove every
   feature added so far (reverse dependency order) and return the problem. */
async function addChecked(payload, added) {
  const doc = await postJSON('/api/feature/add', payload);
  const f = (doc.features || []).find(x => x.id === payload.id);
  const problem = doc.error
    || (f && f.status === 'failed' ? (f.problems || []).join('; ') : null);
  if (!problem) { added.push(payload.id); return null; }
  if (!doc.error) added.push(payload.id);      // exists in the tree but failed
  for (const fid of [...added].reverse()) {
    await postJSON('/api/feature/remove', { feature_id: fid });
  }
  return problem;
}
