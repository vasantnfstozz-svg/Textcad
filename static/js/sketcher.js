// sketcher.js — sketch mode tool logic (Fusion-style). A sketch is NEVER a
// separate screen (fusion-parity rule 9): whether it starts on an origin plane
// or on a picked FACE of a body, the viewport IS the editor — the grid lands
// on the sketch plane in the 3D scene, every body stays visible, and the user
// orbits (right-drag) / pans (middle / shift+left) / zooms at any moment.
//   * pick a tool in the contextual ribbon, then CLICK IN THE VIEWPORT to draw
//     (circle: click center, click radius; rectangle: two corners;
//      polygon: click points, double-click to close)
//   * no tool active = select / drag-move shapes
//   * Esc cancels the tool, Delete removes the selected shape
// This module owns the tool state machine in plane-local coordinates;
// sketch3d.js renders its spec and converts pointer rays to plane points.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh, modelExtent } from './viewport.js';
import { enterSketch3D, exitSketch3D, renderSketch3D,
         planeToScreen, gridStep } from './sketch3d.js';
import { SETTINGS, unitLabel, fmtLen, toMm } from './settings.js';

/* ---------------- state ---------------- */

let skEnts = [];          // the sketch's entities
let skOnFace = null;      // {center, normal, inputId, frame} when on a face
let skEditId = null;      // feature id when EDITING an existing committed sketch
let faceRef = null;       // {outer:[[x,y]..], holes:[[[x,y]..]..]} reference outline
let sketchActive = false; // true while in sketch MODE (in-viewport, non-modal)
let skName = 'sketch1';   // feature id the sketch will be created/saved as
let skPlaneName = 'XY';   // origin plane for plane sketches (unused on a face)
let skPlaneOffset = 0;    // plane offset in mm (kept when re-editing)
let tool = null;          // active drawing tool (entity kind) or null = select
let clicks = [];          // world-space clicks collected for the current tool
let ghost = null;         // preview entity while placing
let selEnt = -1;          // selected entity index

// path tool (chained lines + arcs)
let pathStart = null;     // first point of the profile
let pathSegs = [];        // committed segments
let segMode = 'line';     // what the next segment is: 'line' | 'arc'
let pendingVia = null;    // arc: the middle (via) point, waiting for the end

// snapping (P4)
let activeSnap = null;    // {x, y, label} — geometry point the cursor snapped to
let axisLock = null;      // {axis:'h'|'v', ref:{x,y}} — inference guide line
let gridMark = null;      // {x, y} — grid corner the cursor is locked to (the
                          // Fusion-style pick box; geometry snaps outrank it)

// trim tool (last P1): entity outlines split at their crossings into PIECES
// by the backend; hovering highlights one red, clicking removes it
let trimPieces = null;    // [{id, ent, whole, pts:[[x,y]..]}] or null=loading
let trimHover = -1;       // index into trimPieces
let trimFor = '';         // JSON of the skEnts the pieces were computed for
let trimBusy = false;     // an apply is in flight

// S5 — the MODEL's own geometry as snap targets (corners / edge midpoints /
// hole centres / where an edge pierces the plane), fetched once per sketch from
// /api/sketch/snap and drawn faintly so the user can SEE what is snappable.
let modelSnaps = [];      // [{x, y, kind, body}] in plane-local mm
let modelEdges = [];      // [{body, pts:[[x,y]..]}] in plane-local mm

/* principal-plane frames, PROBED from build123d 0.11.1 (never assume — the
   XZ plane's normal points -Y, and offset moves the origin along z_dir) */
const PLANE_FRAMES = {
  XY: { x_dir: [1, 0, 0], y_dir: [0, 1, 0], z_dir: [0, 0, 1] },
  XZ: { x_dir: [1, 0, 0], y_dir: [0, 0, 1], z_dir: [0, -1, 0] },
  YZ: { x_dir: [0, 1, 0], y_dir: [0, 0, 1], z_dir: [1, 0, 0] },
};

function planeFrame() {
  const f = PLANE_FRAMES[skPlaneName] || PLANE_FRAMES.XY;
  const off = skPlaneOffset || 0;
  return { origin: f.z_dir.map(c => c * off),
           x_dir: f.x_dir, y_dir: f.y_dir, z_dir: f.z_dir };
}

/* Pull in the model geometry that lies ON this sketch plane, so the part's own
   corners / hole centres / edge midpoints become snap targets — drawing against
   an existing body was pure guesswork before. Fetched ONCE per sketch (never
   per mousemove); failure is silent, snapping just falls back to the sketch's
   own entities. */
async function loadModelSnaps(plane, offset = 0) {
  modelSnaps = []; modelEdges = [];
  try {
    const r = await fetch('/api/sketch/snap', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plane, offset }) });
    const data = await r.json();
    if (!sketchActive) return;                 // sketch closed while fetching
    modelSnaps = data.points || [];
    modelEdges = data.edges || [];
    draw();
  } catch { /* offline / no bodies — snapping still works on own entities */ }
}

/* Frame the sketch camera on the MODEL projected into the chosen plane, not on
   the world origin: with a part sitting 200mm out, entering a sketch used to
   stare at empty space at 0,0 while the part sat off-screen. */
function focusOnModel(plane) {
  const f = PLANE_FRAMES[plane] || PLANE_FRAMES.XY;
  const { center, radius, hasModel } = modelExtent();
  if (!hasModel) return { cx: 0, cy: 0, extent: 90 };
  const dot = d => center[0] * d[0] + center[1] * d[1] + center[2] * d[2];
  return { cx: dot(f.x_dir), cy: dot(f.y_dir),
           extent: Math.max(radius * 1.35, 60) };
}

/* EVERY sketch happens IN the 3D viewport (sketch3d.js) — Fusion's sketch
   mode: entities live on the plane as real geometry, and the user can orbit
   (right-drag) / pan (middle) / zoom at any time while drawing with LEFT. */
let snapTol3d = 2;        // mm for ~12 px — updated with every 3D pointer event
let pendingFocus = null;  // {cx, cy, extent} camera framing for the next enter
let edgeOnView = false;   // view rotated (nearly) parallel to the sketch plane

/* snap/close tolerance in plane mm — derived from the screen scale */
const snapTolWorld = () => snapTol3d;

/* ---------------- open / close ---------------- */

function resetEditor() {
  skEnts = []; tool = null; clicks = []; ghost = null; selEnt = -1;
  faceRef = null;
  trimPieces = null; trimHover = -1; trimFor = '';
  modelSnaps = []; modelEdges = [];
  draw();
}

/* Camera framing that covers a set of plane-local [x,y] points (with margin). */
function focusOnPoints(pts) {
  if (!pts || !pts.length) return null;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(Math.max(...xs) - Math.min(...xs),
                        Math.max(...ys) - Math.min(...ys), 20);
  return { cx, cy, extent: Math.max(span * 0.8, 60) };
}

function nextName() {
  const n = (S.lastDoc?.features.filter(
    f => f.op === 'sketch' || f.op === 'sketch_on_face').length || 0) + 1;
  return 'sketch' + n;
}

/* Enter/leave sketch MODE (Fusion-style). ONE path for planes AND faces: the
   viewport IS the sketch (rule 9) — tools sit in the contextual green ribbon,
   a floating hint bar + dim labels overlay the 3D view, the camera turns to
   the sketch plane but stays free to orbit, and every body stays visible. */
let navTipShown = false;      // the orbit tip goes to chat once per page load

function enterMode() {
  sketchActive = true;
  if (!navTipShown) {
    navTipShown = true;
    bus.emit('msg', 'bot', 'Sketch mode: left-drag draws · RIGHT-drag orbits '
      + '(the model stays live — you never leave 3D) · middle-drag or '
      + 'shift+left-drag pans · wheel zooms · Look At re-faces the plane.');
  }
  enterSketch3D(skOnFace ? skOnFace.frame : planeFrame(),
                { gridMm: SETTINGS.gridMm, focus: pendingFocus || undefined });
  pendingFocus = null;
  document.getElementById('sk3dBar').style.display = '';
  bus.emit('sketch-mode', { active: true });
}

function exitMode() {
  sketchActive = false;
  exitSketch3D();
  for (const id of ['sk3dBar', 'sk3dDim', 'sk3dSnap', 'skDimEdit3d']) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  }
  bus.emit('sketch-mode', { active: false });
}

/* test/debug accessor: what is currently drawn on the sketch canvas, and the
   snap targets in play. Tests must be able to assert that a sloppy click landed
   on an EXACT coordinate — that is the whole point of snapping. */
export function sketchEntities() { return skEnts.map(e => ({ ...e })); }
export function sketchSnapTargets() {
  return { model: modelSnaps.map(m => ({ ...m })), edges: modelEdges.length };
}
/* the increment a click would snap by right now (tests assert grid snapping) */
export function snapStepInfo() {
  return { snapMm: SETTINGS.snapMm, gridStep3d: gridStep() };
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
  skName = nextName();
  skPlaneName = plane;               // chosen in the viewport
  skPlaneOffset = 0;
  pendingFocus = focusOnModel(plane);
  enterMode();
  updateHint();
  draw();
  loadModelSnaps(plane, 0);          // the part's own corners/centres to snap to
}

/* Reopen a committed sketch to edit its entities (the alternative to
   delete-and-redraw) — plane sketches AND face sketches, both in the viewport.
   A face sketch's plane is re-resolved by geometry via /api/face-outline. */
export async function editSketch(feature) {
  const onFace = feature.op === 'sketch_on_face';
  let outline = null;
  if (onFace) {
    outline = await fetchFaceOutline(feature.params.face_center,
      feature.params.face_normal || null, feature.inputs?.[0] || null);
    if (!outline?.planar || !outline.frame) {
      bus.emit('msg', 'bot', '⚠ Could not re-resolve the face this sketch ' +
        'sits on' + (outline?.error ? `: ${outline.error}` : '.'));
      return;
    }
  }
  skOnFace = onFace
    ? { center: feature.params.face_center,
        normal: feature.params.face_normal || null,
        inputId: feature.inputs?.[0] || null, frame: outline.frame }
    : null;
  skEditId = feature.id;
  resetEditor();
  skEnts = (feature.params.entities || []).map(e => ({ ...e }));
  skName = feature.id;
  skPlaneName = feature.params.plane || 'XY';
  skPlaneOffset = Number(feature.params.offset) || 0;
  if (onFace) faceRef = { outer: outline.outer, holes: outline.holes || [] };
  // frame the existing geometry (fall back to the face outline, then origin)
  pendingFocus = focusOnPoints(skEnts.map(e => [e.x || 0, e.y || 0]))
    || focusOnPoints(faceRef?.outer);
  enterMode();
  updateHint();
  renderEnts();
  if (!onFace) loadModelSnaps(skPlaneName, skPlaneOffset);
}
bus.on('edit-sketch', editSketch);

export async function openSketchOnFace(faceInfo) {
  const feats = S.lastDoc?.features || [];
  const tip = [...feats].reverse().find(f => f.volume != null);
  if (!tip) { bus.emit('msg', 'bot', '⚠ No solid to sketch on yet.'); return; }
  // sketch on the body the face was PICKED FROM (several bodies are visible and
  // clickable now); the tip is only a fallback
  const owner = faceInfo.body && feats.some(f => f.id === faceInfo.body)
    ? faceInfo.body : tip.id;
  // the face's plane IS the sketch frame, so it must arrive BEFORE the mode
  // can open — same fetch also brings the boundary shown as reference
  const data = await fetchFaceOutline(faceInfo.center, faceInfo.normal || null,
                                      owner);
  if (!data?.planar || !data.frame) {
    bus.emit('msg', 'bot', '⚠ ' + (data?.error ||
      'That face is curved — a sketch needs a FLAT face. Pick a planar face, ' +
      'or sketch on an origin plane instead.'));
    return;
  }
  skOnFace = { center: faceInfo.center, normal: faceInfo.normal || null,
               inputId: owner, frame: data.frame };
  skEditId = null;
  resetEditor();
  skName = nextName();
  faceRef = { outer: data.outer || [], holes: data.holes || [] };
  pendingFocus = focusOnPoints(faceRef.outer);
  enterMode();
  updateHint();
  draw();
  bus.emit('msg', 'bot', `Sketching on a face of "${owner}" — the grey dashed ` +
    'outline is that surface. Draw your profile, Finish Sketch, then ' +
    'Create → Extrude to raise a boss or cut a pocket.');
}
bus.on('sketch-on-face', openSketchOnFace);

/* The picked face's plane frame + boundary (in the plane's own 2D coords),
   resolved by geometry on the body it was picked from. */
async function fetchFaceOutline(center, normal, featureId) {
  try {
    const r = await fetch('/api/face-outline', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ face_center: center, face_normal: normal,
                             feature_id: featureId }) });
    return await r.json();
  } catch { return null; }
}

/* ---------------- init: keyboard + viewport events ---------------- */

export function initSketcher() {
  // sketch mode is non-modal, so key handling lives on the window (guarded)
  window.addEventListener('keydown', e => {
    if (!sketchActive || e.target.tagName === 'INPUT') return;
    if (e.key === 'Escape' && (tool || clicks.length)) {
      e.preventDefault(); setTool(null);
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && selEnt >= 0) {
      e.preventDefault(); skEnts.splice(selEnt, 1); selEnt = -1; renderEnts();
    }
  });

  // sketch input: plane-local points arrive over the bus (sketch3d.js)
  bus.on('sk3d-down', p => {
    if (!sketchActive) return;
    snapTol3d = p.tol; pointerDown(p);
  });
  bus.on('sk3d-move', p => {
    if (!sketchActive) return;
    snapTol3d = p.tol; pointerMove(p);
  });
  bus.on('sk3d-up', () => { if (sketchActive) pointerUp(); });
  bus.on('sk3d-dbl', () => { if (sketchActive) onDblClick(); });
  bus.on('sk3d-grid', ({ step }) => {
    const el = document.getElementById('sk3dGrid');
    if (el) el.textContent = `grid ${fmtLen(step, false)} ${unitLabel()}`;
  });
  // orbiting moves the camera — re-place the HTML labels over the 3D scene
  bus.on('sk3d-view', () => { if (sketchActive) updateFloatingLabels(); });
  // rotated (nearly) edge-on to the plane: say so instead of taking nonsense
  // clicks — orbiting there is fine, drawing is not
  bus.on('sk3d-edge', ({ edgeOn }) => {
    edgeOnView = edgeOn;
    if (sketchActive) updateHint();
  });
}

function setTool(kind) {
  tool = kind; clicks = []; ghost = null; selEnt = -1;   // deselect on tool pick
  activeSnap = null; axisLock = null; gridMark = null;
  pathStart = null; pathSegs = []; pendingVia = null; segMode = 'line';
  trimHover = -1;
  if (tool === 'trim') fetchTrimPieces(); else trimPieces = null;
  bus.emit('sketch-tool', { tool });        // highlight the active tool in the ribbon
  updateHint();
  draw();
}

/* ---------------- coordinates ---------------- */

/* Snap increment: an explicit value from Settings wins; otherwise follow the
   LIVE adaptive grid (Fusion: clicks stick to the visible cells — every grid
   corner is a start point, and zooming in refines the snap with the grid).
   Read straight from sketch3d, so the snap can never disagree with the grid
   that is actually on screen. */
const snap = v => {
  const s = SETTINGS.snapMm > 0 ? SETTINGS.snapMm : gridStep();
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
  // the MODEL's geometry on this plane (S5) — labelled so the marker says what
  // it locked onto ("model corner" reads very differently from "grid")
  const LABEL = { corner: 'model corner', midpoint: 'model edge midpoint',
                  center: 'model centre', crossing: 'model edge' };
  for (const m of modelSnaps)
    pts.push({ x: m.x, y: m.y, label: LABEL[m.kind] || 'model' });
  return pts;
}

/* The reference point of the segment being drawn (for axis inference). */
function refPoint() {
  if (tool === 'path' && pathStart) return pendingVia || pathCursor();
  if (tool && clicks.length) return clicks[clicks.length - 1];
  return null;
}

/* Geometry snap > axis lock > grid snap. Sets activeSnap/axisLock/gridMark
   for draw() — the grid lock gets a visible PICK BOX (Fusion's little square)
   so every cell corner reads as a real start point, not just the origin. */
function smartSnap(raw) {
  activeSnap = null; axisLock = null; gridMark = null;
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
  gridMark = { x: p.x, y: p.y };        // where the click will actually land
  return p;
}

/* test/debug accessor: what the cursor is locked to right now */
export function hoverInfo() {
  return { grid: gridMark ? { ...gridMark } : null,
           snap: activeSnap ? { x: activeSnap.x, y: activeSnap.y,
                                label: activeSnap.label } : null };
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

/* select/draw logic in PLANE coordinates — the 3D viewport feeds points in
   here over the bus ('sk3d-down/move/up') */
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
    draw();
    return 'drag';
  }
  selEnt = -1;
  draw();
  return 'miss';
}

function pointerMove(p) {
  if (tool === 'trim') { setCoordsReadout(p); updateTrimHover(p); draw(); return; }
  if (tool) {
    // snap FIRST, then report: the readout has to say where the click will
    // actually land, not where the raw cursor is (it read "28, 19" while the
    // point was snapping to a model corner at 30, 20)
    const s = smartSnap(p);
    setCoordsReadout(s);
    if (tool === 'path' && pathStart) ghost = pathGhost(s);
    else if (clicks.length) ghost = buildGhost(s);
    draw();
    return;
  }
  setCoordsReadout(p);
  if (dragging) {
    const ent = skEnts[dragging.idx];
    ent.x = snap(dragging.ex + (p.x - dragging.startX));
    ent.y = snap(dragging.ey + (p.y - dragging.startY));
    draw();
  }
}

function pointerUp() {
  dragging = null;
}

function setCoordsReadout(p) {
  const el = document.getElementById('sk3dCoords');
  if (el) el.textContent =
    `x ${fmtLen(snap(p.x), false)}, y ${fmtLen(snap(p.y), false)} ${unitLabel()}`;
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

/* ---------------- modify tools (P5): mirror / duplicate / offset ----------
   Ribbon-facing (the contextual SKETCH tab's Modify group): these used to be
   side-panel buttons of the docked 2D editor, which died with S4. */

export function sketchModify(kind) {
  if (kind === 'mirror_v') return modifySel(e => mirrorEntity(e, 'v'));
  if (kind === 'mirror_h') return modifySel(e => mirrorEntity(e, 'h'));
  if (kind === 'duplicate') return modifySel(duplicateEntity);
  if (kind === 'offset') {
    const d = Number(prompt('Offset distance in mm (+ bigger / − smaller):', '5'));
    if (!d) return;
    modifySel(e => offsetEntity(e, d));
  }
}

function modifySel(fn) {
  if (selEnt < 0 || !skEnts[selEnt]) {
    bus.emit('msg', 'bot', '⚠ Select a shape first (click it in the viewport).');
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
  // a and b are ALREADY snapped clicks — never re-snap derived values like
  // the midpoint: rounding (a+b)/2 to the grid used to shift the whole
  // rectangle so its corners no longer sat where the user clicked
  const d = Math.max(dist(a, b), 0.5);
  if (kind === 'circle')
    return { kind, mode: 'add', x: a.x, y: a.y, r: d };
  if (kind === 'regular_polygon')
    return { kind, mode: 'add', x: a.x, y: a.y, radius: d,
             sides: 6, rotation: 0 };
  if (kind === 'rectangle')
    return { kind, mode: 'add',
             x: (a.x + b.x) / 2, y: (a.y + b.y) / 2,
             w: Math.max(Math.abs(b.x - a.x), 1),
             h: Math.max(Math.abs(b.y - a.y), 1), rotation: 0 };
  if (kind === 'ellipse')
    return { kind, mode: 'add', x: a.x, y: a.y,
             rx: Math.max(Math.abs(b.x - a.x), 1),
             ry: Math.max(Math.abs(b.y - a.y), 1), rotation: 0 };
  if (kind === 'slot')
    return { kind, mode: 'add',
             x: (a.x + b.x) / 2, y: (a.y + b.y) / 2,
             length: d, height: 10,
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

function renderEnts() { draw(); }

function updateHint() {
  const el = document.getElementById('sk3dHelp');
  if (edgeOnView) {
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

/* ---------------- rendering ---------------- */

function fmt(v) { return fmtLen(v, false); }   // dimension labels in display unit

function draw() { if (sketchActive) draw3D(); }

/* ---------------- 3D sketch rendering (all sketches) ----------------
   Entities, ghosts, snap markers and reference geometry drawn as real
   geometry on the sketch plane via sketch3d.js, with HTML labels projected
   over the viewport. */

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
  // the model's on-plane edges, faint and dashed: they are reference geometry,
  // not part of the sketch, but you must SEE them to know they will snap
  for (const e of modelEdges)
    if (e.pts && e.pts.length >= 2)
      shapes.push({ pts: e.pts, closed: false, color: 0x8a97a8, dashed: true });
  // face sketches: the picked surface's boundary (outer + holes), same dashed
  // grey — the user draws against the real surface, right on the part
  if (faceRef) {
    for (const ring of [faceRef.outer, ...(faceRef.holes || [])])
      if (ring && ring.length >= 2)
        shapes.push({ pts: ring, closed: true, color: 0x8a97a8, dashed: true });
  }
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
  // Mark every model snap target so it is VISIBLE before you hover it. Without
  // these, a box's corners in plan view are invisible points you have to hunt
  // for — "we need something for selecting to those edges" was exactly this.
  for (const m of modelSnaps)
    dots.push({ x: m.x, y: m.y, r: dR * 0.75, color: 0x8a97a8,
                ring: m.kind === 'center' });      // centres read as a ring
  // face sketches: hole centres of the picked surface are snap targets too —
  // mark them so they are visible BEFORE you hover (same S5 honesty rule)
  if (faceRef) for (const h of faceRef.holes || []) {
    if (!h.length) continue;
    dots.push({ x: h.reduce((s, p) => s + p[0], 0) / h.length,
                y: h.reduce((s, p) => s + p[1], 0) / h.length,
                r: dR * 0.75, color: 0x8a97a8, ring: true });
  }
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
    // the grid pick box shows ONLY while a draw tool is armed and no geometry
    // snap outranks it — every cell corner reads as a start point (Fusion)
    mark: tool && tool !== 'trim' && gridMark && !activeSnap
      ? { x: gridMark.x, y: gridMark.y, size: Math.max(snapTol3d * 0.4, 0.8) }
      : null,
    guide: axisLock ? { axis: axisLock.axis, ref: axisLock.ref } : null,
  });
  updateFloatingLabels();
}

/* dimension label text + anchor, shown as a floating HTML label */
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
  const ok = sketchActive && e && DIM_KEYS[e.kind] && !clicks.length && !ghost;
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

function buildDimEditor(e, el) {
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
  const id = skName || 'sketch1';

  if (skEditId) {
    // editing an existing sketch: replace its entities in place (plane/offset
    // too for plane sketches; a face sketch keeps its stored face reference)
    const params = skOnFace ? { entities }
      : { plane: skPlaneName, offset: skPlaneOffset, entities };
    const doc = await postJSON('/api/feature/params', {
      feature_id: skEditId, params }, 'updating sketch…');
    loadMesh();
    const f = (doc.features || []).find(x => x.id === skEditId);
    bus.emit('msg', 'bot', doc.error || (f && f.status === 'failed')
      ? `⚠ Sketch "${skEditId}" update problem: ${doc.error || f.problems.join('; ')}`
      : `Sketch "${skEditId}" updated — downstream features rebuilt.`);
    skEditId = null;
    return;
  }

  if (skOnFace) {
    // Fusion: finishing a face sketch creates the SKETCH only — no auto
    // boss/pocket. Extrude (which takes sketches and picked faces) does that,
    // with its live preview and Join/Cut, when the user is ready.
    const added = [];
    const problem = await addChecked({ id, op: 'sketch_on_face',
      params: { face_center: skOnFace.center, face_normal: skOnFace.normal,
                entities },
      inputs: [skOnFace.inputId] }, added);
    loadMesh(true);          // the sketch now shows in the viewport (green)
    bus.emit('msg', 'bot', problem
      ? `⚠ Sketch "${id}" failed: ${problem} The feature was removed.`
      : `Sketch "${id}" created on the face of "${skOnFace.inputId}". Use ` +
        `Create → Extrude to raise a boss or cut a pocket.`);
  } else {
    const doc = await postJSON('/api/feature/add', {
      id, op: 'sketch',
      params: { plane: skPlaneName, offset: skPlaneOffset, entities },
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
