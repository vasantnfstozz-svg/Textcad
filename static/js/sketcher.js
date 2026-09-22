// sketcher.js — sketch mode tool logic (Fusion-style). A sketch is NEVER a
// separate screen (fusion-parity rule 9): whether it starts on an origin plane
// or on a picked FACE of a body, the viewport IS the editor — the grid lands
// on the sketch plane in the 3D scene, every body stays visible, and the user
// orbits (middle-drag) / pans (right / shift+left) / zooms at any moment.
//   * pick a tool in the contextual ribbon, then CLICK IN THE VIEWPORT to draw
//     (circle: click center, click radius; rectangle: two corners;
//      polygon: click points, double-click to close)
//   * no tool active = select / drag-move shapes
//   * Esc cancels the tool, Delete removes the selected shape
// This module owns the tool state machine in plane-local coordinates;
// sketch3d.js renders its spec and converts pointer rays to plane points.

import { S } from './state.js';
import { askConfirm, askNumber } from './ask.js';
import { bus } from './bus.js';
import { postJSON, planRequest } from './api.js';
import { modalGuard } from './dialogs.js';
import { pickedBody } from './tool.js';
import { loadMesh, modelExtent } from './viewport.js';
import { enterSketch3D, exitSketch3D, renderSketch3D,
         planeToScreen, gridStep, setSketchPointerPaused } from './sketch3d.js';
import { SETTINGS, unitLabel, fmtLen, toMm } from './settings.js';

/* ---------------- state ---------------- */

let skEnts = [];          // the sketch's entities
let skOnFace = null;      // {center, normal, area, inputId, frame} on a face
let skEditId = null;      // feature id when EDITING an existing committed sketch
// {outer:[[x,y]..], holes:[[[x,y]..]..], fit_box:[w,h,cx,cy]} reference outline.
// fit_box is the SERVER's inscribed box — the biggest rectangle that fits
// INSIDE this face — and it is carried here because it is the only place
// anything auto-fitted onto the face can read it (R1: the browser took the
// outline's min/max instead, which is the face only when the face is a
// rectangle; on a 30 mm disc that fitted a square 60x60 and put every traced
// point off the material, the furthest 37.85 mm out).
let faceRef = null;
let sketchActive = false; // true while in sketch MODE (in-viewport, non-modal)
let skName = 'sketch1';   // feature id the sketch will be created/saved as
let skPlaneName = 'XY';   // origin plane for plane sketches (unused on a face)
let skPlaneOffset = 0;    // plane offset in mm (kept when re-editing)
/* WHAT TO WRITE BACK for `offset`. A named parameter makes it a FORMULA
   string ("-wall"): the editor needs a number to draw the grid at — the
   server's own resolved value (R1) — but writing that number back would
   silently replace the formula and MOVE the sketch plane. So the value as
   WRITTEN is kept beside the number, and only Move Plane replaces it. */
let skOffsetRaw = 0;
let tool = null;          // active drawing tool (entity kind) or null = select
let clicks = [];          // world-space clicks collected for the current tool
let ghost = null;         // preview entity while placing
let selEnt = -1;          // selected entity index

// path tool (chained lines + arcs)
let pathStart = null;     // first point of the profile
let pathSegs = [];        // committed segments
/* 'path' draws a closed profile (auto-closes); 'openpath' the same chain left
   OPEN (`closed: false`) — the path a Sweep follows (specs/sweep.md). One set
   of drawing code, one flag at the end. */
const isPathTool = () => tool === 'path' || tool === 'openpath';
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

/* the frame a PLANE sketch is drawn in — the SERVER's (LAUNCH-PLAN.md R1):
   build123d's plane frames are not copied here any more (the XZ plane's
   normal points -Y and an offset moves the origin along z_dir; one home for
   that fact — sketch.sketch_plane — is the only way it stays true). Fetched
   from /api/tool/plan {tool: "sketch"} when the sketch opens. */
let skFrame = null;
const planeFrames = new Map();     // `${plane}|${offset}` -> frame: a pure function of both

async function fetchPlaneFrame(plane, offset) {
  const key = `${plane}|${offset}`;
  if (!planeFrames.has(key)) {
    const p = await planRequest({ tool: 'sketch', plane, offset });
    if (!p.ok) { bus.emit('msg', 'bot', `⚠ Cannot open the sketch: ${p.error}.`); return null; }
    planeFrames.set(key, p.frame);
  }
  return planeFrames.get(key);
}

/* Pull in the model geometry that lies ON this sketch plane, so the part's own
   corners / hole centres / edge midpoints become snap targets — drawing against
   an existing body was pure guesswork before. Fetched ONCE per sketch (never
   per mousemove); failure is silent, snapping just falls back to the sketch's
   own entities. FACE sketches pass their world frame (offset already baked
   in) — they had no model snapping at all before that. */
async function loadModelSnaps(plane, offset = 0, frame = null) {
  modelSnaps = []; modelEdges = [];
  try {
    const r = await fetch('/api/sketch/snap', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plane, offset, frame }) });
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
function focusOnModel(f) {                    // f = the plane's frame
  const { center, radius, hasModel } = modelExtent();
  if (!hasModel) return { cx: 0, cy: 0, extent: 90 };
  const dot = d => center[0] * d[0] + center[1] * d[1] + center[2] * d[2];
  return { cx: dot(f.x_dir), cy: dot(f.y_dir),
           extent: Math.max(radius * 1.35, 60) };
}

/* EVERY sketch happens IN the 3D viewport (sketch3d.js) — Fusion's sketch
   mode: entities live on the plane as real geometry, and the user can orbit
   (middle-drag) / pan (right-drag) / zoom at any time while drawing with LEFT. */
let snapTol3d = 2;        // mm for ~12 px — updated with every 3D pointer event
let pendingFocus = null;  // {cx, cy, extent} camera framing for the next enter
let edgeOnView = false;   // view rotated (nearly) parallel to the sketch plane

/* snap/close tolerance in plane mm — derived from the screen scale */
const snapTolWorld = () => snapTol3d;

/* ---------------- open / close ---------------- */

function resetEditor() {
  skEnts = []; tool = null; clicks = []; ghost = null; selEnt = -1;
  scaleDrag = null;                 // see exitMode: a scale never outlives its
  faceRef = null;                   // sketch

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
    bus.emit('msg', 'bot', 'Sketch mode: left-drag draws · RIGHT-drag pans '
      + '(shift+left too) · middle-drag orbits (the model stays live — you '
      + 'never leave 3D) · wheel zooms · Look At re-faces the plane.');
  }
  enterSketch3D(skOnFace ? skOnFace.frame : skFrame,
                { gridMm: SETTINGS.gridMm, focus: pendingFocus || undefined });
  pendingFocus = null;
  document.getElementById('sk3dBar').style.display = '';
  bus.emit('sketch-mode', { active: true });
}

function exitMode() {
  sketchActive = false;
  // A scale in progress DIES with the sketch. Finish already commits it; every
  // other way out (Cancel, picking another tool's mode, an editor reset) used
  // to leave scaleDrag set, and it owns the keyboard: in the NEXT sketch
  // Delete and typed dimensions were dead, the first click committed a phantom
  // "Scaled x1.000 - now <old W> x <old H> mm" into the chat, and Escape wrote
  // the DISCARDED sketch's entities into the new one (code review 2026-09-09).
  scaleDrag = null;
  exitSketch3D();
  for (const id of ['sk3dBar', 'sk3dDim', 'sk3dSnap', 'sk3dScale',
                    'sk3dScaleW', 'skDimEdit3d', 'skDimDraw']) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  }
  bus.emit('sketch-mode', { active: false });
  releaseIsolation();               // fallback — normally released by create()
}

/* Fusion edit-sketch isolation (R3): editing a committed sketch rolls the
   model back to that sketch's point in history — its extrude and everything
   later vanish while editing, earlier bodies stay. Built on the backend
   rollback machinery (the UI bar is gone, the engine remains). */
let skIsolated = false;

async function isolateAt(featureId) {
  skIsolated = true;
  await postJSON('/api/rollback', { feature_id: featureId });
}

async function releaseIsolation() {
  if (!skIsolated) return;
  skIsolated = false;
  await postJSON('/api/rollback', { feature_id: null });
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
export function finishSketch() {
  if (scaleDrag) commitScale();          // keep the size the user is seeing
  create();
}
export async function cancelSketch() {
  // Nothing drawn -> just leave. Asking "are you sure?" about discarding an
  // empty sketch was pure friction (user: "when nothing is there to sketch, i
  // simply press cancel and a tab is opening from the browser").
  if (skEnts.length) {
    const n = skEnts.length;
    const go = await askConfirm('Discard this sketch?', {
      body: `${n} shape${n > 1 ? 's' : ''} will be thrown away.`,
      ok: 'Discard', cancel: 'Keep editing', danger: true,
    });
    if (!go) return;
  }
  exitMode();
}

/* `offset` (mm along the plane's own normal) is the Offset step of Create
   Sketch (sketchplane.js) — the frame is fetched FROM the server at that
   offset, so the grid lands where make_sketch will build (R1). */
export async function openSketchEditor(plane = 'XY', offset = 0) {
  offset = Number(offset) || 0;
  const frame = await fetchPlaneFrame(plane, offset);   // where the kernel will build
  if (!frame) return;
  skOnFace = null; skEditId = null;
  resetEditor();
  skName = nextName();
  skPlaneName = plane;               // chosen in the viewport
  skPlaneOffset = offset;
  skOffsetRaw = offset;
  skFrame = frame;
  pendingFocus = focusOnModel(frame);
  enterMode();
  updateHint();
  draw();
  loadModelSnaps(plane, offset);     // the part's own corners/centres to snap to
  if (offset) bus.emit('msg', 'bot', `Sketching on the ${plane} plane, offset ${offset} mm.`);
}

/* Reopen a committed sketch to edit its entities (the alternative to
   delete-and-redraw) — plane sketches AND face sketches, both in the viewport.
   A face sketch's plane is re-resolved by geometry via /api/face-outline. */
export async function editSketch(feature) {
  if (modalGuard()) return;         // finish the open tool (OK/Cancel) first
  const onFace = feature.op === 'sketch_on_face';
  // the offset AS WRITTEN (a formula string when it names a parameter) and the
  // NUMBER to draw at — the server resolves the formula and says so in
  // `resolved`, which is the only place this browser may learn it (R1)
  const rawOffset = feature.params.offset ?? 0;
  const offNum = Number(feature.resolved?.offset ?? rawOffset) || 0;
  let outline = null;
  if (onFace) {
    // a face sketch names its face by geometry (face_center, a real pick) OR
    // by direction (face: "top", the authoring path) — send whichever it has,
    // plus its plane offset so the grid lands where the sketch actually lives
    outline = await fetchFaceOutline({
      center: feature.params.face_center || null,
      normal: feature.params.face_normal || null,
      area: feature.params.face_area ?? null,
      face: feature.params.face || null,
      offset: offNum,
      featureId: feature.inputs?.[0] || null });
    if (!outline?.planar || !outline.frame) {
      bus.emit('msg', 'bot', '⚠ Could not re-resolve the face this sketch ' +
        'sits on' + (outline?.error ? `: ${outline.error}` : '.'));
      return;
    }
  }
  const frame = onFace ? outline.frame
    : await fetchPlaneFrame(feature.params.plane || 'XY', offNum);
  if (!frame) return;
  skOnFace = onFace
    ? { center: feature.params.face_center || null,
        normal: feature.params.face_normal || null,
        area: feature.params.face_area ?? null,
        face: feature.params.face || null,          // a NAMED face (authored: "top")
        inputId: feature.inputs?.[0] || null, frame }
    : null;
  if (skOnFace) skOnFace.offset = offNum;
  skOffsetRaw = rawOffset;
  skFrame = frame;
  skEditId = feature.id;
  resetEditor();
  skEnts = (feature.params.entities || []).map(e => ({ ...e }));
  skName = feature.id;
  skPlaneName = feature.params.plane || 'XY';
  skPlaneOffset = offNum;
  if (onFace) faceRef = { outer: outline.outer, holes: outline.holes || [],
                          fit_box: outline.fit_box || null };
  // frame the existing geometry (fall back to the face outline, then origin).
  // entSamplePts, not [e.x, e.y]: a hand-drawn polygon or path stores x:0,y:0
  // with ABSOLUTE points, so a profile drawn around (150, 200) framed the
  // world origin and opened off-screen (code review 2026-09-09).
  pendingFocus = focusOnPoints(skEnts.flatMap(entSamplePts))
    || focusOnPoints(faceRef?.outer);
  await isolateAt(feature.id);      // Fusion: the model rolls back to here
  enterMode();
  updateHint();
  renderEnts();
  // AFTER isolateAt, so the snaps reflect the rolled-back bodies. A face
  // sketch snaps via its frame (offset baked in by face_outline_2d).
  if (onFace) loadModelSnaps('XY', 0, outline.frame);
  else loadModelSnaps(skPlaneName, skPlaneOffset);
}
bus.on('edit-sketch', editSketch);

/* `offset` (mm along the face sketch's frame z — the offset method, its sign
   the server's `into_sign`) comes from Create Sketch's Offset step; the pick
   panel's own "Sketch on this face" button opens at 0. */
export async function openSketchOnFace(faceInfo, offset = 0) {
  offset = Number(offset) || 0;
  if (modalGuard()) return;         // finish the open tool (OK/Cancel) first
  // sketch on the body the face was PICKED FROM (several bodies are visible
  // and clickable); the newest solid is only a fallback — one rule, shared
  // with every tool (tool.pickedBody)
  const owner = pickedBody(faceInfo);
  if (!owner) { bus.emit('msg', 'bot', '⚠ No solid to sketch on yet.'); return; }
  // the face's plane IS the sketch frame, so it must arrive BEFORE the mode
  // can open — same fetch also brings the boundary shown as reference
  const data = await fetchFaceOutline({ center: faceInfo.center,
    normal: faceInfo.normal || null, area: faceInfo.area ?? null,
    offset, featureId: owner });
  if (!data?.planar || !data.frame) {
    bus.emit('msg', 'bot', '⚠ ' + (data?.error ||
      'That face is curved — a sketch needs a FLAT face. Pick a planar face, ' +
      'or sketch on an origin plane instead.'));
    return;
  }
  skOnFace = { center: faceInfo.center, normal: faceInfo.normal || null,
               area: faceInfo.area ?? null, inputId: owner, frame: data.frame,
               offset };
  skOffsetRaw = offset;
  skEditId = null;
  resetEditor();
  skName = nextName();
  faceRef = { outer: data.outer || [], holes: data.holes || [],
              fit_box: data.fit_box || null };
  pendingFocus = focusOnPoints(faceRef.outer);
  enterMode();
  updateHint();
  draw();
  loadModelSnaps('XY', 0, data.frame);   // model corners/centres on THIS face
  bus.emit('msg', 'bot', `Sketching on a face of "${owner}"` +
    (offset ? `, offset ${offset} mm` : '') + ' — the grey dashed ' +
    'outline is that surface. Draw your profile, Finish Sketch, then ' +
    'Create → Extrude to raise a boss or cut a pocket.');
}
bus.on('sketch-on-face', info => openSketchOnFace(info));

/* ---------------- the open sketch's plane (Move Plane, sketchplane.js) ------
   The user (2026-09-21): "when I draw some shapes in the sketch tab and then
   want to move the plane in the same sketch" — the entities are plane-local,
   so re-planing the sketch keeps every shape where it was drawn ON the plane
   and moves the plane under them. */
export function currentSketchPlane() {
  if (!sketchActive) return null;
  return skOnFace
    ? { kind: 'face', offset: skOnFace.offset || 0,
        face: { center: skOnFace.center, normal: skOnFace.normal,
                area: skOnFace.area ?? null, face: skOnFace.face || null,
                inputId: skOnFace.inputId } }
    : { kind: 'plane', plane: skPlaneName, offset: skPlaneOffset };
}

/* while the step is open no draw tool is armed and the sketch takes no
   pointer input (see sketch3d.setSketchPointerPaused) */
export function pauseSketchInput(on) {
  if (on) { setTool(null); clicks = []; ghost = null; draw(); }
  setSketchPointerPaused(on);
}

/* re-plane the OPEN sketch at `offset`: the frame comes from the server at
   that offset (R1), the 3D plane is rebuilt under the same entities, the
   model snaps are fetched again for the new plane */
export async function setSketchPlaneOffset(offset) {
  if (!sketchActive) return false;
  offset = Number(offset) || 0;
  // Only a REAL move replaces a formula with the number it resolved to. The
  // box opens at that number, so OK without touching it is a no-op — and a
  // no-op must not change the document, the same rule `sameSketch` states for
  // opening a sketch and pressing Finish.
  if (offset !== (skOnFace ? skOnFace.offset || 0 : skPlaneOffset))
    skOffsetRaw = offset;
  let frame;
  if (skOnFace) {
    const out = await fetchFaceOutline({ center: skOnFace.center, normal: skOnFace.normal,
      area: skOnFace.area ?? null, face: skOnFace.face || null, offset,
      featureId: skOnFace.inputId });
    if (!out?.planar || !out.frame) {
      bus.emit('msg', 'bot', '⚠ Could not move the sketch plane' +
        (out?.error ? `: ${out.error}` : '.'));
      return false;
    }
    frame = out.frame; skOnFace.frame = frame; skOnFace.offset = offset;
  } else {
    frame = await fetchPlaneFrame(skPlaneName, offset);
    if (!frame) return false;
    skPlaneOffset = offset;
  }
  skFrame = frame;
  enterSketch3D(frame, { gridMm: SETTINGS.gridMm,
    focus: focusOnPoints(skEnts.flatMap(entSamplePts))
           || focusOnPoints(faceRef?.outer) || focusOnModel(frame) });
  draw();
  if (skOnFace) loadModelSnaps('XY', 0, frame);
  else loadModelSnaps(skPlaneName, offset);
  bus.emit('msg', 'bot', `Sketch plane moved to offset ${offset} mm — ` +
    `${skEnts.length ? 'the shapes came along' : 'nothing drawn yet'}.`);
  return true;
}

/* The picked face's plane frame + boundary (in the plane's own 2D coords),
   resolved on the body it was picked from — by geometry (center/normal) or
   by name (face: "top"), plus the sketch plane's offset off that face. */
export async function fetchFaceOutline({ center = null, normal = null, area = null,
                                         face = null, offset = 0, featureId = null }) {
  try {
    const r = await fetch('/api/face-outline', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ face_center: center, face_normal: normal,
                             face_area: area,
                             face, offset, feature_id: featureId }) });
    return await r.json();
  } catch { return null; }
}

/* The file as a PNG data-URL the raster tracer can eat. An SVG (the user's
   logo, 2026-09-01: "its not even working man, but rocky png is coming") is
   VECTOR data cv2 cannot decode — the BROWSER is a perfect SVG renderer, so
   rasterize it here onto a canvas at high resolution and feed the raster
   pipeline. Everything else passes through as-is. */
async function fileToPngDataUrl(f) {
  const dataUrl = await new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(f);
  });
  if (!/svg/i.test(f.type) && !/\.svg$/i.test(f.name)) return dataUrl;
  const img = new Image();
  await new Promise((res, rej) => {
    img.onload = res;
    img.onerror = () => rej(new Error('the SVG did not render'));
    img.src = dataUrl;
  });
  // ~2k px on the long side: crisp curves for the tracer whatever tiny
  // nominal size the SVG declares (a mm-sized logo renders at ~640px raw)
  const w = img.naturalWidth || 1000, h = img.naturalHeight || 1000;
  const scale = 2048 / Math.max(w, h);
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w * scale));
  c.height = Math.max(1, Math.round(h * scale));
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
  return c.toDataURL('image/png');
}

/* Trace Image lives in the SKETCH ribbon (user request 2026-09-01, replacing
   the Create-tab button): it inserts the traced art into the sketch that is
   open right now, as normal entities you can move / scale / delete before
   Finish. On a FACE sketch the art auto-fits the face (the boundary is
   already here as faceRef); on a plane sketch it asks for a height. */
export function traceIntoSketch() {
  if (!sketchActive) {
    bus.emit('msg', 'bot', '⚠ Trace Image inserts into the open sketch — ' +
      'Create Sketch (or pick a face → Sketch on this face) first.');
    return;
  }
  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = 'image/png,image/jpeg,image/svg+xml,.svg';
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    const req = { entities_only: true };
    if (skOnFace && faceRef?.outer?.length) {
      // the box the art belongs in is the SERVER's inscribed box (R1) —
      // /api/face-outline computes it and faceRef carries it here. The
      // outline's own min/max, which this used to send, is the face only
      // when the face is a rectangle: on a 30 mm disc it fitted a square to
      // 60x60 and every traced point landed off the material.
      // An old response with no fit_box falls back to that bounding box.
      const xs = faceRef.outer.map(p => p[0]);
      const ys = faceRef.outer.map(p => p[1]);
      req.fit_box = faceRef.fit_box?.length === 4 ? faceRef.fit_box
        : [Math.max(...xs) - Math.min(...xs),
           Math.max(...ys) - Math.min(...ys),
           (Math.max(...xs) + Math.min(...xs)) / 2,
           (Math.max(...ys) + Math.min(...ys)) / 2];
    } else {
      // min/max are the server's own limits (imgtrace.image_to_entities):
      // the box used to accept 0.1 and the trace then came back "height_mm
      // must be between 1 and 1000" with nothing drawn (review 2026-09-17)
      const h = await askNumber('Trace image', {
        label: 'Artwork height in mm',
        value: 50, min: 1, max: 1000,
        body: `Tracing ${f.name}. The width follows from the image's own aspect.`,
        ok: 'Trace',
      });
      if (h === null) return;
      req.height_mm = parseFloat(h) || 50;
    }
    try {
      req.png_base64 = await fileToPngDataUrl(f);
    } catch {
      bus.emit('msg', 'bot', `⚠ Could not read "${f.name}" as an image — ` +
        `is the file a valid PNG/JPG/SVG?`);
      return;
    }
    const out = await postJSON('/api/trace-png', req, 'tracing…');
    if (out && !out.error && (out.entities || []).length) {
      skEnts.push(...out.entities);
      selEnt = -1;
      assignModes();                 // holes stay holes (even-odd, R10)
      renderEnts(); updateHint();
      const i = out.trace_info || {};
      bus.emit('msg', 'bot',
        `Traced "${f.name}" into this sketch — ${i.width_mm}×${i.height_mm}mm` +
        // fit_mm is the FIT BOX, not the face: the biggest rectangle that
        // fits inside this face. On a 60 mm disc it is 42×42, and calling
        // that "the face" is a wrong measurement in the user's chat. The
        // server still sends the old name `face_mm` beside it; nothing reads
        // it any more, so it can go.
        (i.fit_mm ? `, auto-fitted into the ${i.fit_mm.join('×')}mm ` +
                    `rectangle that fits inside this face` : '') +
        (i.rotated ? `, rotated 90° to run along the face (Mirror ↔ then ` +
                     `Mirror ↕ turns it 180°)` : '') +
        `, ${i.contours} outline(s), ${i.holes} hole(s). Move / Scale it if ` +
        `needed, then Finish Sketch and Extrude.`);
      // The tracer's own sentence about the PART, on its own line so a long
      // success message cannot bury it. imgtrace writes `note` when the weld
      // could not join the art into one piece, and when two parts of it pass
      // within a hair of each other ("the sketch builds, but trace it taller
      // if the extrude ever refuses") — both are things to know before
      // cutting, and neither had ever reached a user: this was the only call
      // site of /api/trace-png and it printed every other field but this one.
      if (i.note) bus.emit('msg', 'bot', `⚠ ${i.note}`);
    }
  };
  inp.click();
}

/* ---------------- init: keyboard + viewport events ---------------- */

export function initSketcher() {
  // sketch mode is non-modal, so key handling lives on the window (guarded)
  window.addEventListener('keydown', e => {
    if (!sketchActive || e.target.tagName === 'INPUT') return;
    if (scaleDrag) {                      // interactive scale owns the keys
      if (e.key === 'Escape') { e.preventDefault(); cancelScale(); }
      return;
    }
    if (routeDigitToDrawBox(e)) return;   // typing a number = dimension entry
    if (e.key === 'Escape' && (tool || clicks.length)) {
      e.preventDefault(); setTool(null);
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && selEnt >= 0) {
      e.preventDefault(); skEnts.splice(selEnt, 1); selEnt = -1;
      assignModes(); renderEnts();
    }
  });

  // sketch input: plane-local points arrive over the bus (sketch3d.js)
  bus.on('sk3d-down', p => {
    if (!sketchActive) return;
    snapTol3d = p.tol;
    if (scaleDrag) { scaleDown(p); return; }    // grab an arrow / finish
    pointerDown(p);
  });
  bus.on('sk3d-move', p => {
    if (!sketchActive) return;
    snapTol3d = p.tol;
    if (scaleDrag) { scaleMove(p); return; }    // resize only while grabbed
    pointerMove(p);
  });
  bus.on('sk3d-up', () => {
    if (!sketchActive) return;
    if (scaleDrag) { scaleUp(); return; }       // release = value stays
    pointerUp();
  });
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
  if (scaleDrag) cancelScale();          // picking a tool abandons the scale
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
  const q = s > 0 ? Math.round(v / s) * s : Math.round(v * 100) / 100;
  return Math.round(q * 1e6) / 1e6;   // 92 * 0.1 = 9.200000000000001 otherwise
};
const snapPt = p => ({ x: snap(p.x), y: snap(p.y) });
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/* ---------------- smart snapping (P4) ---------------- */

/* centroid of a face-outline ring, IGNORING the duplicated closing point —
   averaging it in pulled every "hole center" r/n off-centre (0.32mm on a
   Ø16 bore: the user could never find the true centre of a circle) */
function ringCentroid(h) {
  if (!h || !h.length) return null;
  const closed = h.length > 1
    && Math.hypot(h[0][0] - h[h.length - 1][0],
                  h[0][1] - h[h.length - 1][1]) < 1e-6;
  const n = closed ? h.length - 1 : h.length;
  let sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { sx += h[i][0]; sy += h[i][1]; }
  return { x: sx / n, y: sy / n };
}

/* bbox centre of the CURRENT sketch's entities (via their own snap points) —
   "the centre of the design" while it is still being drawn */
function sketchCentreOf(pts) {
  if (skEnts.length < 2 || !pts.length) return null;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of pts) {
    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
  }
  return { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
}

function collectSnapPoints() {
  const pts = [{ x: 0, y: 0, label: 'origin' }];
  const entFrom = pts.length;          // entity-derived points start here
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
        pts.push({ ...entToSketch(e, p[0], p[1]), label: 'vertex' });
    if (e.kind === 'path' && e.start) {
      pts.push({ ...entToSketch(e, e.start[0], e.start[1]), label: 'vertex' });
      for (const s of e.segments || [])
        pts.push({ ...entToSketch(e, s.to[0], s.to[1]), label: 'vertex' });
    }
  });
  const sc = sketchCentreOf(pts.slice(entFrom));
  if (sc) pts.push({ ...sc, label: 'sketch centre' });
  if (faceRef) {                       // snap to the selected surface too
    for (const p of faceRef.outer) pts.push({ x: p[0], y: p[1], label: 'edge' });
    for (const h of faceRef.holes) {
      const c = ringCentroid(h);
      // the model snaps carry the EXACT arc centre for round holes — never
      // offer an approximate centroid 0.3mm beside it
      if (c && !modelSnaps.some(m => m.kind === 'center'
                                  && Math.hypot(m.x - c.x, m.y - c.y) < 0.5))
        pts.push({ x: c.x, y: c.y, label: 'hole center' });
    }
  }
  // the MODEL's geometry on this plane (S5) — labelled so the marker says what
  // it locked onto ("model corner" reads very differently from "grid")
  const LABEL = { corner: 'model corner', midpoint: 'model edge midpoint',
                  center: 'model centre', crossing: 'model edge',
                  design_center: 'design centre' };
  for (const m of modelSnaps)
    pts.push({ x: m.x, y: m.y, label: LABEL[m.kind] || 'model' });
  return pts;
}

/* The reference point of the segment being drawn (for axis inference). */
function refPoint() {
  if (isPathTool() && pathStart) return pendingVia || pathCursor();
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
  // RESIZE handles first (step 8): a grab point on a shape beats moving it
  const grab = resizeGrab(raw);
  if (grab) {
    selEnt = grab.idx;
    dragging = { resize: grab };
    draw();
    return 'drag';
  }
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
    lastMove = s;                 // the draw-time dimension box follows this
    setCoordsReadout(s);
    if (isPathTool() && pathStart) ghost = pathGhost(s);
    else if (clicks.length) ghost = buildGhost(s);
    draw();
    return;
  }
  setCoordsReadout(p);
  if (dragging && dragging.resize) {
    applyResize(dragging.resize, snapPt(p));
    draw();
    return;
  }
  if (dragging) {
    const ent = skEnts[dragging.idx];
    ent.x = snap(dragging.ex + (p.x - dragging.startX));
    ent.y = snap(dragging.ey + (p.y - dragging.startY));
    draw();
  }
}

function pointerUp() {
  if (dragging) {                 // moved OR resized: nesting may have changed
    dragging = null;
    assignModes();
    renderEnts();
  }
}

/* ---------------- drag-resize handles (step 8, R6) ----------------
   Grab a point ON a shape and pull: circle/N-gon rim -> radius, rectangle
   corner -> resize about the OPPOSITE corner, ellipse cardinal -> rx/ry,
   slot end -> length+direction, polygon/path vertex -> move that vertex. */

function entityHandles(e) {
  const x = e.x || 0, y = e.y || 0, a = (e.rotation || 0) * Math.PI / 180;
  const rot = (px, py) => ({ x: x + px * Math.cos(a) - py * Math.sin(a),
                             y: y + px * Math.sin(a) + py * Math.cos(a) });
  const hs = [];
  if (e.kind === 'circle')
    for (const [px, py] of [[e.r, 0], [-e.r, 0], [0, e.r], [0, -e.r]])
      hs.push({ ...rot(px, py), kind: 'radius' });
  else if (e.kind === 'regular_polygon')
    for (let k = 0; k < e.sides; k++) {
      const t = Math.PI / 2 + k * 2 * Math.PI / e.sides;
      hs.push({ ...rot(e.radius * Math.cos(t), e.radius * Math.sin(t)),
                kind: 'radius' });
    }
  else if (e.kind === 'rectangle') {
    const c = [[-e.w / 2, -e.h / 2], [e.w / 2, -e.h / 2],
               [e.w / 2, e.h / 2], [-e.w / 2, e.h / 2]];
    c.forEach(([px, py], i) => {
      const opp = c[(i + 2) % 4];
      hs.push({ ...rot(px, py), kind: 'corner', anchor: rot(opp[0], opp[1]) });
    });
  } else if (e.kind === 'ellipse') {
    hs.push({ ...rot(e.rx, 0), kind: 'rx' }, { ...rot(-e.rx, 0), kind: 'rx' },
            { ...rot(0, e.ry), kind: 'ry' }, { ...rot(0, -e.ry), kind: 'ry' });
  } else if (e.kind === 'slot') {
    const hx = e.length / 2;
    hs.push({ ...rot(hx, 0), kind: 'slotend', anchor: rot(-hx, 0) },
            { ...rot(-hx, 0), kind: 'slotend', anchor: rot(hx, 0) },
            { ...rot(0, e.height / 2), kind: 'height' },
            { ...rot(0, -e.height / 2), kind: 'height' });
  } else if (e.kind === 'polygon' && e.points) {
    e.points.forEach((p, i) =>
      hs.push({ ...rot(p[0], p[1]), kind: 'vertex', index: i }));
  } else if (e.kind === 'path' && e.start) {
    hs.push({ ...rot(e.start[0], e.start[1]), kind: 'pathpt', field: 'start' });
    (e.segments || []).forEach((s, i) => {
      hs.push({ ...rot(s.to[0], s.to[1]), kind: 'pathpt',
                field: 'to', index: i });
      if (s.via) hs.push({ ...rot(s.via[0], s.via[1]), kind: 'pathpt',
                           field: 'via', index: i });
    });
  }
  return hs;
}

function resizeGrab(p) {
  // Handles are DRAWN only on the selected shape, so only IT is grabbable.
  // Grabbing the invisible handles of every other shape turned "drag a circle
  // to move it" into "the circle gets bigger" (user report 2026-08-31).
  if (selEnt < 0 || !skEnts[selEnt]) return null;
  const tolW = snapTolWorld();
  const hs = entityHandles(skEnts[selEnt]);
  let best = null, bestD = Infinity;
  for (const h of hs) {
    const d = Math.hypot(p.x - h.x, p.y - h.y);
    if (d <= tolW && d < bestD) { best = { idx: selEnt, handle: h }; bestD = d; }
  }
  if (!best) return null;
  // A shape smaller than the grab tolerance is COVERED by its own handles —
  // resize would win everywhere and the shape could never be moved again.
  // Grabbing the shape nearer its middle than any handle means MOVE.
  const ax = hs.reduce((s, h) => s + h.x, 0) / hs.length;
  const ay = hs.reduce((s, h) => s + h.y, 0) / hs.length;
  if (hitTest(p) === selEnt && Math.hypot(p.x - ax, p.y - ay) < bestD)
    return null;
  return best;
}

function applyResize(grab, p) {
  const e = skEnts[grab.idx];
  const h = grab.handle;
  const x = e.x || 0, y = e.y || 0, a = -(e.rotation || 0) * Math.PI / 180;
  // cursor in the entity's local (un-rotated) frame
  const lx = (p.x - x) * Math.cos(a) - (p.y - y) * Math.sin(a);
  const ly = (p.x - x) * Math.sin(a) + (p.y - y) * Math.cos(a);
  if (h.kind === 'radius') {
    const r = Math.max(Math.hypot(p.x - x, p.y - y), 0.5);
    if (e.kind === 'circle') e.r = r; else e.radius = r;
  } else if (h.kind === 'rx') e.rx = Math.max(Math.abs(lx), 0.5);
  else if (h.kind === 'ry') e.ry = Math.max(Math.abs(ly), 0.5);
  else if (h.kind === 'height') {
    e.height = Math.min(Math.max(Math.abs(ly) * 2, 0.5), e.length - 0.5);
  } else if (h.kind === 'corner') {
    // the opposite corner stays PUT; the grabbed one follows the cursor
    const A = h.anchor, ra = (e.rotation || 0) * Math.PI / 180;
    const dxl = (p.x - A.x) * Math.cos(-ra) - (p.y - A.y) * Math.sin(-ra);
    const dyl = (p.x - A.x) * Math.sin(-ra) + (p.y - A.y) * Math.cos(-ra);
    e.w = Math.max(Math.abs(dxl), 0.5);
    e.h = Math.max(Math.abs(dyl), 0.5);
    e.x = A.x + (dxl / 2) * Math.cos(ra) - (dyl / 2) * Math.sin(ra);
    e.y = A.y + (dxl / 2) * Math.sin(ra) + (dyl / 2) * Math.cos(ra);
  } else if (h.kind === 'slotend') {
    // re-aim: the other end cap stays PUT, length + rotation follow
    const A = h.anchor;
    const d = Math.max(Math.hypot(p.x - A.x, p.y - A.y), e.height + 0.5);
    const ang = Math.atan2(p.y - A.y, p.x - A.x);
    e.length = d;
    e.rotation = Math.round(ang * 180 / Math.PI);
    e.x = A.x + (d / 2) * Math.cos(ang);
    e.y = A.y + (d / 2) * Math.sin(ang);
  } else if (h.kind === 'vertex') {
    e.points[h.index] = [lx, ly];              // local frame: rotation undone
  } else if (h.kind === 'pathpt') {
    if (h.field === 'start') e.start = [lx, ly];
    else if (h.field === 'via') e.segments[h.index].via = [lx, ly];
    else e.segments[h.index].to = [lx, ly];
  }
}

function setCoordsReadout(p) {
  const el = document.getElementById('sk3dCoords');
  if (el) el.textContent =
    `x ${fmtLen(snap(p.x), false)}, y ${fmtLen(snap(p.y), false)} ${unitLabel()}`;
}

function onDblClick() {
  if (tool === 'polygon' && clicks.length >= 3) finishPolygon();
  if (isPathTool() && pathSegs.length >= 1) finishPath(false);
}

function pathGhost(p) {
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
  if (kind === 'scale') return scaleSel();
  if (kind === 'offset') {
    return askNumber('Offset', {
      label: 'Distance in mm', value: 5,
      body: 'Positive grows the shape outward, negative shrinks it inward.',
      ok: 'Offset',
      validate: v => Number(v) === 0 ? 'Zero would not move anything.' : null,
    }).then(d => { if (d) modifySel(e => offsetEntity(e, d)); });
  }
}

/* Scale — INTERACTIVE: press the button, then move the cursor UP to enlarge
   / DOWN to shrink; the shapes resize live and a readout shows the current
   W × H in real mm. Click commits, Esc cancels. Works IN PLACE (resizing a
   traced logo must not clone it). With a selection: that shape, about its
   own centre. With NOTHING selected: every shape, about the sketch origin —
   so multi-piece art (outline + holes) stays registered. */
let scaleDrag = null;

function scaleSel() {
  const all = selEnt < 0 || !skEnts[selEnt];
  if (all && !skEnts.length) {
    // Empty editor, but shapes are visible on screen? They belong to a
    // COMMITTED sketch (e.g. the traced logo) — jump there and scale it
    // instead of dead-ending on "the sketch is empty" (reported 2026-08-21).
    const cands = (S.lastDoc?.features || []).filter(f =>
      (f.op === 'sketch' || f.op === 'sketch_on_face')
      && f.id !== skEditId && (f.params?.entities || []).length);
    if (!skEditId && cands.length === 1) {
      const target = cands[0];
      exitMode();                       // this sketch is empty — nothing lost
      bus.emit('msg', 'bot', `This sketch was empty — opening ` +
        `"${target.id}" (the shapes you see) for scaling instead.`);
      editSketch(target).then(() => scaleSel());
      return;
    }
    bus.emit('msg', 'bot', '⚠ Nothing to scale — this sketch is empty.'
      + (cands.length
         ? ` The shapes you see belong to ${cands.map(c => `"${c.id}"`).join(', ')}` +
           ' — Cancel this sketch, then double-click that feature (or use' +
           ' Modify → Scale).'
         : ''));
    return;
  }
  const idxs = all ? skEnts.map((_, i) => i) : [selEnt];
  const base = idxs.map(i => JSON.parse(JSON.stringify(skEnts[i])));
  const bb = entsBBox(base);
  if (!(bb.h > 1e-6)) return;
  scaleDrag = { idxs, base, all, w0: bb.w, h0: bb.h, f: 1, grab: null };
  renderEnts();                       // show the rulers + markers immediately
  setScaleReadout(1);
  bus.emit('msg', 'bot',
    (all ? `Scaling ALL ${idxs.length} shape(s). ` : 'Scaling the selected shape. ') +
    'GRAB one of the amber arrows and drag — up/right enlarges, down/left ' +
    'shrinks; release to set. Click anywhere else to finish, Esc to cancel.');
}

/* which gizmo arrow (if any) is under the pointer — 'v' height, 'h' width */
function scaleHit(p) {
  const bb = scaleGizmoBox();
  if (!bb) return null;
  const m = Math.max(3, bb.h * 0.08);
  const a = Math.max(1.2, Math.min(bb.h, bb.w) * 0.06);
  const tol = Math.max(snapTol3d * 1.5, 2);
  const xr = bb.x1 + m, yb = bb.y0 - m;
  if (Math.abs(p.x - xr) <= tol + a
      && p.y >= bb.y0 - a - tol && p.y <= bb.y1 + a + tol) return 'v';
  if (Math.abs(p.y - yb) <= tol + a
      && p.x >= bb.x0 - a - tol && p.x <= bb.x1 + a + tol) return 'h';
  return null;
}

function scaleDown(p) {
  const axis = scaleHit(p);
  if (axis) {                         // grab an arrow — dragging starts
    scaleDrag.grab = { axis, x0: p.x, y0: p.y, f0: scaleDrag.f };
    return;
  }
  commitScale();                      // click away from the gizmo = done
}

function scaleMove(p) {
  const d = scaleDrag;
  if (!d.grab) return;                // arrows only move while GRABBED
  const delta = d.grab.axis === 'v' ? p.y - d.grab.y0 : p.x - d.grab.x0;
  d.f = Math.min(100, Math.max(0.02, d.grab.f0 * Math.pow(2, delta / 40)));
  d.idxs.forEach((idx, k) => {
    skEnts[idx] = scaleEntity(JSON.parse(JSON.stringify(d.base[k])), d.f, !d.all);
  });
  renderEnts();
  setScaleReadout(d.f);
}

function scaleUp() {
  if (scaleDrag && scaleDrag.grab) scaleDrag.grab = null;   // value stays
}

function setScaleReadout(f) {
  const d = scaleDrag;
  const el = document.getElementById('sk3dCoords');
  if (el && d) el.textContent =
    `scale ×${f.toFixed(3)} — W ${(d.w0 * f).toFixed(1)} × ` +
    `H ${(d.h0 * f).toFixed(1)} ${unitLabel()}`;
}

function commitScale() {
  const d = scaleDrag;
  scaleDrag = null;
  renderEnts();
  bus.emit('msg', 'bot', `Scaled ×${d.f.toFixed(3)} — now ` +
    `${(d.w0 * d.f).toFixed(1)} × ${(d.h0 * d.f).toFixed(1)} mm (W × H).`);
}

function cancelScale() {
  const d = scaleDrag;
  scaleDrag = null;
  d.idxs.forEach((idx, k) => { skEnts[idx] = d.base[k]; });
  renderEnts();
  bus.emit('msg', 'bot', 'Scale cancelled — sizes restored.');
}

function entSamplePts(e) {
  // characteristic points in SKETCH coords (position + rotation applied)
  const pts = [];
  const rot = ((e.rotation || 0) * Math.PI) / 180;
  const c = Math.cos(rot), s = Math.sin(rot);
  const push = (lx, ly) =>
    pts.push([(e.x || 0) + lx * c - ly * s, (e.y || 0) + lx * s + ly * c]);
  if (e.kind === 'circle') {
    push(e.r, 0); push(-e.r, 0); push(0, e.r); push(0, -e.r);
  } else if (e.kind === 'ellipse') {
    push(e.rx, 0); push(-e.rx, 0); push(0, e.ry); push(0, -e.ry);
  } else if (e.kind === 'regular_polygon') {
    push(e.radius, 0); push(-e.radius, 0); push(0, e.radius); push(0, -e.radius);
  } else if (e.kind === 'rectangle') {
    for (const sx of [-1, 1]) for (const sy of [-1, 1])
      push((sx * e.w) / 2, (sy * e.h) / 2);
  } else if (e.kind === 'slot') {
    for (const sx of [-1, 1]) for (const sy of [-1, 1])
      push((sx * e.length) / 2, (sy * e.height) / 2);
  } else if (e.kind === 'polygon') {
    for (const p of e.points || []) push(p[0], p[1]);
  } else if (e.kind === 'path') {
    // `|| []` / `|| [0, 0]` like every sibling reader: the BACKEND treats a
    // missing start as the origin (sketch._path_face), so an entity the AI
    // author wrote without one builds fine and is a legal row in the tree.
    // Unguarded, clicking Edit on it threw TypeError here — inside an
    // unawaited bus handler, before enterMode(), so sketch mode silently
    // never opened and the editor was already half-overwritten (second code
    // review, 2026-09-09).
    const st = e.start || [0, 0];
    push(st[0], st[1]);
    for (const sg of e.segments || []) {
      if (sg.to) push(sg.to[0], sg.to[1]);
      if (sg.via) push(sg.via[0], sg.via[1]);
    }
  }
  return pts;
}

function entsBBox(ents) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const e of ents)
    for (const p of entSamplePts(e)) {
      x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]);
      y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]);
    }
  return { x0, x1, y0, y1, w: x1 - x0, h: y1 - y0 };
}

/* the drag-scale gizmo: amber dimension rulers hugging the LIVE bbox —
   a vertical double-arrow beside the shapes (height) and a horizontal one
   below (width). They grow and shrink with every cursor move, and the
   floating #sk3dScale marker rides them with the current W × H in mm. */
const SCALE_COL = 0xd9a23c;

function scaleGizmoBox() {
  if (!scaleDrag) return null;
  return entsBBox(scaleDrag.idxs.map(i => skEnts[i]).filter(Boolean));
}

function scaleGizmoShapes(bb) {
  const m = Math.max(3, bb.h * 0.08);          // ruler offset from the shapes
  const a = Math.max(1.2, Math.min(bb.h, bb.w) * 0.06);   // arrowhead size
  const xr = bb.x1 + m, yb = bb.y0 - m;
  const V = [
    [[xr, bb.y0], [xr, bb.y1]],                              // shaft
    [[xr - a, bb.y1 - a], [xr, bb.y1]], [[xr, bb.y1], [xr + a, bb.y1 - a]],
    [[xr - a, bb.y0 + a], [xr, bb.y0]], [[xr, bb.y0], [xr + a, bb.y0 + a]],
    [[bb.x1, bb.y1], [xr + a, bb.y1]],                       // end ticks
    [[bb.x1, bb.y0], [xr + a, bb.y0]],
  ];
  const H = [
    [[bb.x0, yb], [bb.x1, yb]],
    [[bb.x0 + a, yb - a], [bb.x0, yb]], [[bb.x0, yb], [bb.x0 + a, yb + a]],
    [[bb.x1 - a, yb - a], [bb.x1, yb]], [[bb.x1, yb], [bb.x1 - a, yb + a]],
    [[bb.x0, bb.y0], [bb.x0, yb - a]],
    [[bb.x1, bb.y0], [bb.x1, yb - a]],
  ];
  return [...V, ...H].map(pts => ({ pts, closed: false, color: SCALE_COL }));
}

/* Can this entity be scaled at all? A malformed one is left ALONE, and that
   has to be decided BEFORE the x/y move below: the early returns added inside
   the path and polygon branches came after it, so a "scale all" drag still
   wrote coordinates into an entity the backend refuses and committed it back
   into the sketch (fourth review follow-up, 2026-09-09). Repairing such an
   entity is not ours to do — the third review's guards did that and saved a
   vertex the user never drew. */
function scalable(e) {
  if (e.kind === 'path')
    return !!e.start && (e.segments || []).length > 0
      && e.segments.every(sg => !!sg.to);
  if (e.kind === 'polygon') return (e.points || []).length > 0;
  return true;
}

function scaleEntity(e, f, inPlace) {
  if (!scalable(e)) return e;
  if (!inPlace) { e.x = (e.x || 0) * f; e.y = (e.y || 0) * f; }
  if (e.kind === 'circle') e.r *= f;
  else if (e.kind === 'ellipse') { e.rx *= f; e.ry *= f; }
  else if (e.kind === 'rectangle') { e.w *= f; e.h *= f; }
  else if (e.kind === 'slot') { e.length *= f; e.height *= f; }
  else if (e.kind === 'regular_polygon') e.radius *= f;
  else if (e.kind === 'polygon')
    e.points = e.points.map(p => [p[0] * f, p[1] * f]);
  else if (e.kind === 'path') {
    // A malformed path is left ALONE, never repaired. The guards added in
    // the third review defaulted a missing start to [0, 0] and then WROTE it
    // back into the entity, so one Scale drag saved a vertex the user never
    // drew — into the very sketch the backend refuses because the editor
    // cannot show it (fourth code review, 2026-09-09). Every sibling reader
    // skips such an entity; so does this one now.
    const sgs = e.segments;
    let cx = 0, cy = 0;
    if (inPlace) {          // about the path's own local centre
      const xs = [e.start[0]], ys = [e.start[1]];
      for (const sg of sgs) {
        xs.push(sg.to[0]); ys.push(sg.to[1]);
        if (sg.via) { xs.push(sg.via[0]); ys.push(sg.via[1]); }
      }
      cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    }
    const sc = p => [cx + (p[0] - cx) * f, cy + (p[1] - cy) * f];
    e.start = sc(e.start);
    e.segments = sgs.map(sg => ({
      ...sg, to: sc(sg.to), ...(sg.via ? { via: sc(sg.via) } : {}),
    }));
  }
  return e;
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
  assignModes();
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
  if (e.kind === 'slot') {
    // BOTH ways. An offset moves the caps too, so a 30 x 8 slot offset by 5
    // is 40 x 18 — growing only the height gave 30 x 18, and at Offset 12 the
    // height overtook the length and Finish blamed the slot: "slot length
    // (30) must be greater than its height (32)" (code review 2026-09-09).
    e.height = grow(e.height, 2 * d);
    e.length = Math.max(grow(e.length, 2 * d), e.height + 0.5);
    return e;
  }
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

/* Point-list entities (polygon, path) hold their points in the entity's OWN
   local frame, exactly like every other kind — so a `rotation` on one turns
   it, and `_entity` in sketch.py duly rotates about the entity origin before
   placing it. Until the code review of 2026-09-09 the editor did not: the
   outline, the handles, the hit test and the snap points all read the raw
   points, so an authored {"kind":"polygon","rotation":30,…} drew and dragged
   in one place and BUILT in another. entSamplePts already rotated, so the
   scale gizmo and the drawn outline disagreed with each other too. One home
   for the mapping; applyResize already holds its inverse (lx, ly). */
function entToSketch(e, px, py) {
  const a = (e.rotation || 0) * Math.PI / 180;
  const c = Math.cos(a), s = Math.sin(a);
  return { x: (e.x || 0) + px * c - py * s,
           y: (e.y || 0) + px * s + py * c };
}

function pathOutline(e) {
  let cur = { x: e.start[0], y: e.start[1] };
  const pts = [{ ...cur }];
  for (const s of e.segments || []) {
    const to = { x: s.to[0], y: s.to[1] };
    if (s.type === 'arc' && s.via)
      pts.push(...sampleArc(cur, { x: s.via[0], y: s.via[1] }, to).slice(1));
    else pts.push(to);
    cur = to;
  }
  return pts.map(p => entToSketch(e, p.x, p.y));
}

/* ---------------- click-to-place ---------------- */

function placeClick(p) {
  if (isPathTool()) { pathClick(p); return; }
  if (tool === 'text') {           // ONE click: the word's centre; the box takes the word
    clicks = [p]; ghost = null;
    updateHint(); draw();
    return;
  }
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
    assignModes();                 // inner shape = hole (even-odd, R10)
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
      && dist(p, pathStart) < closeR) { finishPath(true); return; }

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

/* `viaStart`: the click landed on the start point — that closes even the open
   Path tool's chain into an ordinary profile. A double-click ends the Path
   tool's chain OPEN (`closed: false`, no face, Sweep's path); the Line/Arc
   tool auto-closes either way, exactly as before. */
function finishPath(viaStart = true) {
  if (!pathStart || pathSegs.length < 1) return;
  const open = tool === 'openpath' && !viaStart;
  skEnts.push({ kind: 'path', mode: 'add', x: 0, y: 0,
                ...(open ? { closed: false } : {}),
                start: [pathStart.x, pathStart.y], segments: pathSegs });
  selEnt = skEnts.length - 1;
  pathStart = null; pathSegs = []; pendingVia = null;
  assignModes();
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
  assignModes();
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
        && pointInPolygon(rx, ry, e.points)) return i;   // rx/ry: un-rotated
    if (e.kind === 'text') {                             // the word's box, un-rotated
      const b = textBox(e);
      if (b && rx >= b.x0 && rx <= b.x1 && ry >= b.y0 && ry <= b.y1) return i;
    }
    if (e.kind === 'path' && e.start) {
      const pts = pathOutline(e).map(q => [q.x, q.y]);
      // an OPEN path encloses nothing: it is hit along its line
      if (e.closed === false) {
        if (distToPolyline(p.x, p.y, pts) <= snapTolWorld() * 1.2) return i;
      } else if (pointInPolygon(p.x, p.y, pts)) return i;
    }
  }
  return -1;
}

function distToPolyline(x, y, pts) {
  let best = Infinity;
  for (let i = 0; i + 1 < pts.length; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy || 1e-12;
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / L2));
    best = Math.min(best, Math.hypot(x - (ax + t * dx), y - (ay + t * dy)));
  }
  return best;
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

/* Fusion's even-odd region rule, approximated (R10): a closed shape whose
   centroid lies inside an ODD number of other closed shapes is a HOLE
   (mode subtract) — an inner circle makes a washer, a ring inside it is a
   boss again. Recomputed whenever the user changes the sketch (place, move,
   resize, delete, duplicate) — NOT on merely opening an existing sketch,
   so a committed design never changes by being looked at. */
function assignModes() {
  const outlines = skEnts.map(e => {
    const o = outlinePts(e);
    return o && o.closed && o.pts.length >= 3 ? o.pts : null;
  });
  // CONTAINMENT, not centroid-in: concentric circles share a centre, so the
  // outer's centroid sits "inside" the inner too — sampling the OUTLINE
  // tells them apart (the outer's rim is not inside the inner)
  // EVERY point, not a walk of eight. Sampling one point in eight let a shape
  // that only mostly nests — a traced outline with a spike poking over a
  // rectangle's edge, a star inside a circle — be called contained and turned
  // into a HOLE the user never drew (code review 2026-09-09). An outline is
  // 48-96 points and this runs only when the sketch is edited, so the exact
  // answer is free.
  const containedIn = (a, b) => {
    for (let k = 0; k < a.length; k++)
      if (!pointInPolygon(a[k][0], a[k][1], b)) return false;
    return true;
  };
  skEnts.forEach((e, i) => {
    if (!outlines[i]) return;
    let depth = 0;
    outlines.forEach((pts, j) => {
      if (j !== i && pts && containedIn(outlines[i], pts)) depth++;
    });
    e.mode = depth % 2 === 1 ? 'subtract' : 'add';
  });
}

function updateHint() {
  const el = document.getElementById('sk3dHelp');
  if (edgeOnView) {
    el.textContent = '⚠ You are looking along the sketch plane — rotate back, '
      + 'or press Look At, to keep drawing';
    return;
  }
  if (isPathTool()) {
    const openTool = tool === 'openpath';
    const msg = !pathStart
      ? (openTool ? 'Path: click the START point — on the profile you will sweep'
                  : 'Click the START point of your profile')
      : pendingVia ? 'Arc: now click the END point'
      : segMode === 'arc' ? 'Arc: click a point the arc passes THROUGH'
      : openTool ? 'Click the next point · double-click to END the open path'
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
  else if (tool === 'text') el.textContent = clicks.length
    ? 'Type the word and its height in the box · Enter places it · click again to move the point'
    : 'Text: click where the word\'s CENTRE goes';
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
             pts: e.points.map(p => {
               const q = entToSketch(e, p[0], p[1]);
               return [q.x, q.y];
             }) };
  if (e.kind === 'path' && e.start)
    return { closed: !e.ghostOpen && e.closed !== false,     // an open path stays open
             pts: pathOutline(e).map(q => [q.x, q.y]) };
  if (e.kind === 'text') {          // the word's box: for the even-odd rule and the gizmos
    const b = textBox(e);
    if (!b) return null;
    return { closed: true, pts: rot([[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]]) };
  }
  return null;
}

/* ---------------- text entities: the glyphs are the SERVER's (R1) ----------
   A font lives in the kernel, so the loops of a word come from
   POST /api/sketch/outline, asked once per (word, height, font) with the
   entity at the origin and unrotated, and placed / turned here exactly as
   `entToSketch` places every other entity. Until the answer lands the word
   draws nothing; when it lands the sketch redraws and the even-odd modes are
   assigned again (a word inside a plate is a cut). */
const textCache = new Map();                    // key -> loops in the entity's frame | 'pending'
const textKey = e => `${e.text}|${e.size}|${e.font || ''}`;
function textLoops(e) {
  const k = textKey(e), got = textCache.get(k);
  if (got === undefined) { textCache.set(k, 'pending'); fetchTextLoops(e, k); return []; }
  if (!Array.isArray(got)) return [];
  return got.map(L => L.map(([px, py]) => { const q = entToSketch(e, px, py); return [q.x, q.y]; }));
}
async function fetchTextLoops(e, k) {
  try {
    const r = await fetch('/api/sketch/outline', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entities: [{ ...e, x: 0, y: 0, rotation: 0 }] }) });
    const res = await r.json();
    const err = res.errors && res.errors['0'];
    if (err) bus.emit('msg', 'bot', '⚠ ' + err);
    textCache.set(k, (res.outlines && res.outlines[0]) || []);
  } catch { textCache.set(k, []); }
  if (sketchActive) { assignModes(); draw(); }
}
/* the word's bounding box in its own frame, once its loops are known */
function textBox(e) {
  const got = textCache.get(textKey(e));
  if (!Array.isArray(got) || !got.length) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const L of got) for (const [px, py] of L) {
    x0 = Math.min(x0, px); y0 = Math.min(y0, py); x1 = Math.max(x1, px); y1 = Math.max(y1, py);
  }
  return { x0, y0, x1, y1 };
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
    if (e.kind === 'text') {          // the kernel's glyph loops, outlines only
      const col = !isGhost && i === selEnt ? SEL : (e.mode === 'subtract' ? CUT : ADD);
      for (const L of textLoops(e))
        shapes.push({ pts: L, closed: true, color: col, fill: null, dashed: false });
      return;
    }
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
  if (scaleDrag) {
    const bb = scaleGizmoBox();
    if (bb && bb.w > 0) for (const s of scaleGizmoShapes(bb)) shapes.push(s);
  }

  const dR = Math.max(snapTol3d * 0.35, 0.6);
  const dots = clicks.map(c => ({ x: c.x, y: c.y, r: dR, color: 0x4da3ff }));
  // resize handles of the SELECTED shape — grab one and pull (step 8)
  if (!tool && selEnt >= 0 && skEnts[selEnt])
    for (const h of entityHandles(skEnts[selEnt]))
      dots.push({ x: h.x, y: h.y, r: dR * 0.85, color: 0x4da3ff, ring: true });
  // Mark every model snap target so it is VISIBLE before you hover it. Without
  // these, a box's corners in plan view are invisible points you have to hunt
  // for — "we need something for selecting to those edges" was exactly this.
  for (const m of modelSnaps)
    dots.push({ x: m.x, y: m.y,
                r: m.kind === 'design_center' ? dR : dR * 0.75,
                color: 0x8a97a8,                   // centres read as a ring
                ring: m.kind === 'center' || m.kind === 'design_center' });
  // face sketches: hole centres of the picked surface are snap targets too —
  // mark them so they are visible BEFORE you hover (same S5 honesty rule).
  // Same rule as collectSnapPoints: the model's EXACT arc centre wins over
  // the ring centroid — never draw two "centres" 0.3mm apart.
  if (faceRef) for (const h of faceRef.holes || []) {
    const c = ringCentroid(h);
    if (c && !modelSnaps.some(m => m.kind === 'center'
                                && Math.hypot(m.x - c.x, m.y - c.y) < 0.5))
      dots.push({ x: c.x, y: c.y, r: dR * 0.75, color: 0x8a97a8, ring: true });
  }
  // the centre of the sketch in progress, findable BEFORE you hover it
  {
    const sc = collectSnapPoints().find(p => p.label === 'sketch centre');
    if (sc) dots.push({ x: sc.x, y: sc.y, r: dR, color: 0x8a97a8, ring: true });
  }
  if (tool === 'trim' && trimPieces && trimHover >= 0) {
    const piece = trimPieces[trimHover];        // the doomed segment, in red
    shapes.push({ pts: piece.pts, closed: false, color: 0xff3333 });
    const end = piece.pts[piece.pts.length - 1];
    dots.push({ x: piece.pts[0][0], y: piece.pts[0][1], r: dR * 0.9,
                color: 0xff3333 });
    dots.push({ x: end[0], y: end[1], r: dR * 0.9, color: 0xff3333 });
  }
  if (isPathTool() && pathStart) {
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
  const bb = scaleDrag ? scaleGizmoBox() : null;
  const gm = bb ? Math.max(3, bb.h * 0.08) : 0;
  placeFloat('sk3dScale',              // height marker beside its arrow
    bb ? { x: bb.x1 + gm, y: (bb.y0 + bb.y1) / 2 } : null,
    bb ? `H ${bb.h.toFixed(1)} ${unitLabel()}  (×${scaleDrag.f.toFixed(2)})` : '');
  placeFloat('sk3dScaleW',             // width marker under its arrow
    bb ? { x: (bb.x0 + bb.x1) / 2, y: bb.y0 - gm } : null,
    bb ? `W ${bb.w.toFixed(1)} ${unitLabel()}` : '');
  const e = ghost || (selEnt >= 0 ? skEnts[selEnt] : null) || null;
  const d = e ? dimLabel(e) : null;
  placeFloat('sk3dDim', d, d ? d.text : '');
  placeFloat('sk3dSnap', activeSnap
    ? { x: activeSnap.x, y: activeSnap.y + Math.max(snapTol3d, 1.6) } : null,
    activeSnap ? activeSnap.label : '');
  updateDimEditor3D();
  updateDrawDimBox();
}

function updateDimEditor3D() {
  const el = document.getElementById('skDimEdit3d');
  if (!el) return;
  const e = selEnt >= 0 ? skEnts[selEnt] : null;
  const ok = sketchActive && e && DIM_KEYS[e.kind] && !clicks.length && !ghost;
  if (!ok) { el.style.display = 'none'; return; }
  // cache by ENTITY IDENTITY, not index: after a delete, another shape can
  // take the same index and inherit the previous shape's input fields (a
  // circle showing W/H boxes — user report 2026-08-05)
  if (dimEditFor !== e || !el.childElementCount) {
    buildDimEditor(e, el);
    dimEditFor = e;
  }
  // live refresh: dragging a resize handle must update the numbers too
  for (const inp of el.querySelectorAll('input')) {
    if (document.activeElement === inp) continue;
    const key = inp.dataset.dim;
    if (key) inp.value = key === 'sides' ? e.sides : fmtLen(e[key] ?? 0, false);
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
let dimEditFor = null;     // the ENTITY the editor was built for (not an index)

function buildDimEditor(e, el) {
  el.innerHTML = '';
  for (const [key, label] of DIM_KEYS[e.kind]) {
    const w = document.createElement('label');
    w.innerHTML = `<span>${label}</span>`;
    const inp = document.createElement('input');
    inp.type = 'number'; inp.step = 'any'; inp.dataset.dim = key;
    inp.value = key === 'sides' ? e.sides : fmtLen(e[key] ?? 0, false);
    inp.onkeydown = ev => { ev.stopPropagation(); if (ev.key === 'Enter') inp.blur(); };
    inp.oninput = () => {
      const v = Number(inp.value);
      if (isNaN(v)) return;
      e[key] = key === 'sides' ? Math.max(3, Math.round(v)) : toMm(v);
      draw();
    };
    w.appendChild(inp);
    if (key !== 'sides') {                  // "12.5" alone feels off — say mm
      const u = document.createElement('span');
      u.className = 'dimunit'; u.textContent = unitLabel();
      w.appendChild(u);
    }
    el.appendChild(w);
  }
}

/* ---------------- dimension box WHILE DRAWING (Step 7, Fusion) -------------
   After the first click of a shape, a small input follows the cursor with
   the LIVE dimension; just start typing (no click needed) and press Enter to
   commit the exact size. Tab hops between fields (w↹h). Mouse keeps working:
   a second click still commits at the clicked size. */

const DRAW_DIMS = {
  circle: [['r', 'R']],
  rectangle: [['w', 'W'], ['h', 'H']],
  ellipse: [['rx', 'Rx'], ['ry', 'Ry']],
  slot: [['length', 'L'], ['height', 'H']],
  regular_polygon: [['radius', 'R'], ['sides', 'N']],
  text: [['text', 'Text'], ['size', 'H']],     // the word itself is a field (specs/text-entity.md)
};
let lastText = 'TEXT', lastTextSize = 10;       // the Text tool remembers its last word and height
let lastMove = null;         // latest snapped cursor point (plane coords)
let drawDimKey = '';         // state signature — rebuild fields on change
let drawLocked = {};         // field key -> user typed (stop live overwrite)

function drawDimFields() {
  if (!sketchActive || !tool || edgeOnView) return null;
  if (isPathTool())
    return (pathStart && !pendingVia && segMode === 'line')
      ? [['len', 'L']] : null;
  return (DRAW_DIMS[tool] && clicks.length === 1) ? DRAW_DIMS[tool] : null;
}

/* live value of one field from the current ghost / cursor */
function drawDimValue(key) {
  if (tool === 'text') return key === 'text' ? lastText : lastTextSize;
  if (key === 'len') {
    const cur = pathCursor();
    return (cur && lastMove) ? Math.hypot(lastMove.x - cur.x,
                                          lastMove.y - cur.y) : 0;
  }
  const g = ghost || (lastMove && buildGhost(lastMove));
  return g ? (g[key] ?? 0) : 0;
}

function updateDrawDimBox() {
  const el = document.getElementById('skDimDraw');
  if (!el) return;
  const fields = drawDimFields();
  if (!fields) {
    el.style.display = 'none';
    drawDimKey = ''; drawLocked = {};
    return;
  }
  const sig = `${tool}|${clicks.length}|${pathSegs.length}|${pathStart ? 1 : 0}`;
  if (sig !== drawDimKey) {
    drawDimKey = sig; drawLocked = {};
    el.innerHTML = '';
    for (const [key, label] of fields) {
      const w = document.createElement('label');
      w.innerHTML = `<span>${label}</span>`;
      const inp = document.createElement('input');
      if (key === 'text') { inp.type = 'text'; inp.size = 12; }        // the word
      else { inp.type = 'number'; inp.step = 'any'; }
      inp.dataset.dim = key;
      inp.oninput = () => { drawLocked[key] = true; };
      inp.onkeydown = ev => {
        ev.stopPropagation();
        if (ev.key === 'Enter') { ev.preventDefault(); commitDrawDims(); }
        if (ev.key === 'Escape') {           // back to live values, keep tool
          ev.preventDefault(); drawLocked = {}; inp.blur(); updateDrawDimBox();
        }
      };
      w.appendChild(inp);
      if (key !== 'sides' && key !== 'text') {   // "12.5" alone feels off — say mm
        const u = document.createElement('span');
        u.className = 'dimunit'; u.textContent = unitLabel();
        w.appendChild(u);
      }
      el.appendChild(w);
    }
  }
  for (const inp of el.querySelectorAll('input')) {
    const key = inp.dataset.dim;
    if (drawLocked[key] || document.activeElement === inp) continue;
    const v = drawDimValue(key);
    inp.value = key === 'text' ? v : key === 'sides' ? (v || 6) : fmtLen(v, false);
  }
  const at = lastMove || clicks[0] || pathStart;
  const scr = at ? planeToScreen(at.x, at.y) : null;
  const pane = document.getElementById('viewportPane').getBoundingClientRect();
  if (!scr || scr.x < pane.left || scr.x > pane.right
      || scr.y < pane.top || scr.y > pane.bottom) {
    el.style.display = 'none';
    return;
  }
  el.style.left = (scr.x - pane.left + 18) + 'px';
  el.style.top = (scr.y - pane.top + 18) + 'px';
  el.style.display = 'flex';
  // the Text tool: the word is what the user types next, so the word field
  // takes the keys as soon as the box is up (never stealing from a field
  // the user has already tabbed into)
  if (tool === 'text' && !el.contains(document.activeElement)) {
    const t = el.querySelector('input[data-dim="text"]');
    if (t) { t.focus(); t.select(); }
  }
}

/* first digit typed anywhere in sketch mode lands in the box (Fusion) */
function routeDigitToDrawBox(e) {
  if (e.target.tagName === 'INPUT' || e.ctrlKey || e.metaKey) return false;
  if (!/^[0-9.]$/.test(e.key)) return false;
  const el = document.getElementById('skDimDraw');
  if (!el || el.style.display === 'none') return false;
  const inp = el.querySelector('input');
  if (!inp) return false;
  e.preventDefault();
  inp.value = e.key;                 // number inputs put the caret at the end
  drawLocked[inp.dataset.dim] = true;
  inp.focus();
  return true;
}

/* Enter in the box: commit the shape with the TYPED dimensions */
function commitDrawDims() {
  const el = document.getElementById('skDimDraw');
  const fields = drawDimFields();
  if (!el || !fields) return;
  const val = {};
  for (const inp of el.querySelectorAll('input')) {
    const key = inp.dataset.dim;
    if (key === 'text') { val.text = inp.value; continue; }      // a word, not a number
    const n = Number(inp.value);
    val[key] = (!isNaN(n) && inp.value.trim() !== '')
      ? (key === 'sides' ? Math.max(3, Math.round(n)) : Math.max(toMm(n), 0.1))
      : (key === 'sides' ? 6 : Math.max(drawDimValue(key), 0.1));
  }
  el.style.display = 'none'; drawDimKey = ''; drawLocked = {};

  if (isPathTool()) {                      // typed segment LENGTH along the
    const cur = pathCursor();                 // current cursor direction
    if (!cur || !lastMove) return;
    const d = Math.hypot(lastMove.x - cur.x, lastMove.y - cur.y);
    if (d < 1e-6 || !val.len) return;
    const ux = (lastMove.x - cur.x) / d, uy = (lastMove.y - cur.y) / d;
    pathSegs.push({ type: 'line',
                    to: [snap(cur.x + ux * val.len), snap(cur.y + uy * val.len)] });
    updateHint(); draw();
    return;
  }

  const a = clicks[0];
  if (!a) return;
  if (tool === 'text') {                       // the word, centred on the click
    const word = (val.text || '').trim();
    if (!word) { bus.emit('msg', 'bot', '⚠ Text: type the word first, then Enter.'); return; }
    lastText = word; lastTextSize = Math.max(val.size || lastTextSize, 0.1);
    skEnts.push({ kind: 'text', mode: 'add', x: a.x, y: a.y, rotation: 0,
                  text: word, size: lastTextSize });
    selEnt = skEnts.length - 1;
    clicks = []; ghost = null;
    assignModes(); renderEnts(); updateHint();
    return;
  }
  const to = lastMove || a;
  const sx = to.x >= a.x ? 1 : -1, sy = to.y >= a.y ? 1 : -1;
  let ent = null;
  if (tool === 'circle')
    ent = { kind: 'circle', mode: 'add', x: a.x, y: a.y, r: val.r };
  else if (tool === 'regular_polygon')
    ent = { kind: 'regular_polygon', mode: 'add', x: a.x, y: a.y,
            radius: val.radius, sides: val.sides, rotation: 0 };
  else if (tool === 'rectangle')                    // first click = a CORNER,
    ent = { kind: 'rectangle', mode: 'add',         // grows toward the cursor
            x: a.x + sx * val.w / 2, y: a.y + sy * val.h / 2,
            w: val.w, h: val.h, rotation: 0 };
  else if (tool === 'ellipse')
    ent = { kind: 'ellipse', mode: 'add', x: a.x, y: a.y,
            rx: val.rx, ry: val.ry, rotation: 0 };
  else if (tool === 'slot') {
    const d = Math.max(Math.hypot(to.x - a.x, to.y - a.y), 1e-6);
    const ux = (to.x - a.x) / d, uy = (to.y - a.y) / d;
    ent = { kind: 'slot', mode: 'add',
            x: a.x + ux * val.length / 2, y: a.y + uy * val.length / 2,
            length: Math.max(val.length, val.height + 0.5),
            height: val.height,
            rotation: Math.round(Math.atan2(uy, ux) * 180 / Math.PI) };
  }
  if (!ent) return;
  skEnts.push(ent);
  selEnt = skEnts.length - 1;
  clicks = []; ghost = null;
  assignModes();
  renderEnts(); updateHint();
}

/* ---------------- create the feature(s) ---------------- */

async function create() {
  const clean = skEnts.filter(e => !e.ghostOpen);
  if (!clean.length) { await finishEmpty(); return; }
  // NO mode flip here. Until the code review of 2026-09-09 the first entity
  // was forced back to 'add' so the kernel's sequential compose would have
  // something to cut FROM — but drawing order is not nesting order, so a bore
  // drawn before its rim was turned back into solid material: a disc of
  // 2827.43 mm2 where the editor had drawn a 2513.27 washer, status "ok".
  // The kernel now composes outers before the holes inside them (_compose /
  // _nesting_depth in sketch.py), so the modes go up exactly as drawn.
  const entities = clean.map(e => {
    const o = { kind: e.kind, mode: e.mode };
    for (const k of Object.keys(e))
      if (!['kind', 'mode', 'ghostOpen'].includes(k)) o[k] = e[k];
    return o;
  });
  const id = skName || 'sketch1';

  if (skEditId) {
    // editing an existing sketch: replace its entities in place FIRST (a
    // fast rebuild up to the rollback bar), THEN exit — releasing the
    // edit-isolation triggers the one full rebuild with the new entities
    const params = skOnFace ? { entities, offset: offsetParam(skOnFace.offset || 0) }
      : { plane: skPlaneName, offset: offsetParam(skPlaneOffset), entities };
    // NOTHING CHANGED? Then do not touch the document at all: no rebuild of
    // everything downstream, and no pointless entry on the undo stack. Opening
    // a sketch to look at it and pressing Finish is not an edit.
    const saved = (S.lastDoc?.features || []).find(f => f.id === skEditId);
    if (saved && sameSketch(saved.params, params)) {
      exitMode();
      loadMesh();
      bus.emit('msg', 'bot', `Sketch "${skEditId}" closed — nothing changed.`);
      skEditId = null;
      return;
    }
    const doc = await postJSON('/api/feature/params', {
      feature_id: skEditId, params }, 'updating sketch…');
    exitMode();
    const f = (doc.features || []).find(x => x.id === skEditId);
    bus.emit('msg', 'bot', doc.error || (f && f.status === 'failed')
      ? `⚠ Sketch "${skEditId}" update problem: ${doc.error || f.problems.join('; ')}`
      : `Sketch "${skEditId}" updated — downstream features rebuilt.`);
    skEditId = null;
    return;
  }

  exitMode();
  if (skOnFace) {
    // Fusion: finishing a face sketch creates the SKETCH only — no auto
    // boss/pocket. Extrude (which takes sketches and picked faces) does that,
    // with its live preview and Join/Cut, when the user is ready.
    const added = [];
    const problem = await addChecked({ id, op: 'sketch_on_face',
      params: { face_center: skOnFace.center, face_normal: skOnFace.normal,
                face_area: skOnFace.area ?? null, offset: skOnFace.offset || 0,
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

/* The `offset` to WRITE: the formula the sketch was opened with, unless Move
   Plane has since put a number there. `num` is what the editor drew at. */
function offsetParam(num) {
  return typeof skOffsetRaw === 'string' ? skOffsetRaw : num;
}

/* Is what the editor holds the same sketch that is already saved? Compared
   with key order normalised (the editor rebuilds each entity object, so its
   keys come out in a different order than they went in) and numbers compared
   as numbers (-25 and -25.0 are the same place). */
function stableJson(v) {
  if (Array.isArray(v)) return '[' + v.map(stableJson).join(',') + ']';
  if (v && typeof v === 'object')
    return '{' + Object.keys(v).sort().map(k =>
      JSON.stringify(k) + ':' + stableJson(v[k])).join(',') + '}';
  if (typeof v === 'number') return String(Number(v.toFixed(9)));
  return JSON.stringify(v);
}

function sameSketch(saved, next) {
  if (!saved) return false;
  if (stableJson(saved.entities || []) !== stableJson(next.entities || []))
    return false;
  if (next.plane !== undefined && saved.plane !== next.plane) return false;
  // the offset as WRITTEN, not as a number: a formula ("-wall") and the number
  // it happens to resolve to are not the same sketch — one of them survives a
  // change to the parameter and the other does not. stableJson makes -25 and
  // -25.0 the same place, as it does for every entity.
  if (next.offset !== undefined
      && stableJson(saved.offset ?? 0) !== stableJson(next.offset ?? 0)) return false;
  return true;
}

/* Finishing a sketch that has NOTHING left in it.

   Deleting the last shape used to be a DEAD END: create() said "the sketch is
   empty, draw first" and returned, and sketch mode owns the whole tab strip
   (only the green contextual tab shows), so the only way out was Cancel —
   which throws the deletion away. A user deleting a name from its own sketch
   could therefore never save that deletion (report 2026-08-25).

   An empty sketch is a real intent, so honour it: on a COMMITTED sketch it
   means "this sketch should go" (confirmed, listing what goes with it, one
   undo away), on a brand-new one it means "never mind". */
async function finishEmpty() {
  if (!skEditId) {                       // nothing was ever drawn: just leave
    exitMode();
    bus.emit('msg', 'bot', 'Sketch closed — nothing was drawn, so nothing ' +
      'was created.');
    return;
  }
  const fid = skEditId;
  const dry = await postJSON('/api/feature/remove',
    { feature_id: fid, dry_run: true }, 'checking dependencies…');
  const plan = dry.remove_plan;
  if (!plan) return;                     // error already shown; stay in sketch
  const go = await askConfirm(`"${fid}" has no shapes left`, {
    body: `${plan.summary}\n\nDelete the sketch, or keep it open and draw the new shapes?`,
    ok: 'Delete sketch', cancel: 'Keep it open', danger: true,
  });
  if (!go) {
    bus.emit('msg', 'bot', `Kept "${fid}" open — draw the new shapes, or ` +
      `press Cancel Sketch to put the deleted ones back.`);
    return;
  }
  skEditId = null;
  await releaseIsolation();              // rollback bar off BEFORE the delete
  exitMode();
  const doc = await postJSON('/api/feature/remove', { feature_id: fid },
                             'deleting…');
  if (!doc.error)
    bus.emit('msg', 'bot',
      ((doc.remove_plan && doc.remove_plan.summary) || `Deleted "${fid}".`)
        .replace(/^Delete /, 'Deleted ') + ' Undo (Ctrl+Z) puts it back.');
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
