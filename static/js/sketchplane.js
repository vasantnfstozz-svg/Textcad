// sketchplane.js — Fusion's Construct > Offset Plane (specs/offset-plane.md).
//
// The user (2026-09-22): "offset plane only: I can just move the plane and
// draw sketch whatever I want". A construction plane is its OWN feature
// (`offset_plane`) a distance from an origin plane or a flat face; sketches
// are drawn ON it (Create Sketch, click the plane — or press Create Sketch
// with the plane's row selected) and move with it when its offset changes.
// This replaces the first design (2026-09-21), where the number lived on the
// sketch and a "Move Plane" button inside the sketch dragged the drawn shapes
// along with the plane — the user tried it and found it the wrong tool.
//
// The step: Offset Plane → pick an origin plane or a flat face in the viewport
// → the plane is drawn where it will land, ONE arrow along its normal and an
// Offset box → drag or type → OK adds the feature, Esc / Cancel adds nothing.
// The tree's ✎ on a plane row reopens the same step at the plane's offset.
//
// EVERY geometric fact is the server's (LAUNCH-PLAN R1): the base frame comes
// from /api/tool/plan (plane) or /api/face-outline (face), which SIGN goes
// into the material is that response's `into_sign`, the ghost moves along the
// frame's z by the dragged amount exactly as Plane.offset does on the server,
// and the plane the document draws afterwards is the feature's `plane_frame`.
//
// ONE COMMAND AT A TIME (fusion-parity rule 9): the step takes the modal lock
// like a tool panel, so Extrude & co. refuse until OK or Cancel.

import { bus } from './bus.js';
import { S } from './state.js';
import { planRequest, postJSON } from './api.js';
import { modalGuard } from './dialogs.js';
import { g, mm, setLen, say, pickedBody } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginPlaneGhost, setPlaneGhost, endPlaneGhost, beginPlanePick,
         retakeSectionHandles } from './viewport.js';
import { fetchFaceOutline } from './sketcher.js';

const NAME = 'Offset Plane';
const PANEL = 'planeDialog';
const PRINCIPAL = ['XY', 'XZ', 'YZ'];
// { mode: 'new' | 'edit', kind, what, frame, loops, intoSign, owner, plane,
//   pick, offset, shown, featureId } while open
let stage = null;

/* for tests and other modules: is the step open, and on what */
export const offsetPlaneStage = () => stage
  ? { mode: stage.mode, kind: stage.kind, plane: stage.kind === 'plane' ? stage.plane : null,
      owner: stage.owner, offset: mm('plOffset'), intoSign: stage.intoSign,
      featureId: stage.featureId || null }
  : null;

/* The plane's frame at offset 0 — the base the arrow and the ghost measure
   from — fetched from the server: kind 'plane' (plane = 'XY' | 'XZ' | 'YZ')
   or 'face' (face = {center, normal, area, face}, owner = the body it is on).
   null when it cannot be had; the reason has been said. */
async function baseFrame(kind, plane, face, owner) {
  if (kind === 'face') {
    // by geometry (a pick's centre) or by NAME (an authored face: "top") — both
    // are how offset_plane itself names its face
    const out = await fetchFaceOutline({ center: face.center || null, normal: face.normal || null,
                                         area: face.area ?? null, face: face.face || null,
                                         featureId: owner });
    if (!out?.planar || !out.frame) {
      say('⚠ ' + (out?.error || 'That face is curved — an offset plane needs a FLAT face. ' +
                                'Pick a planar face, or an origin plane instead.'));
      return null;
    }
    return { kind, owner, frame: out.frame, intoSign: out.into_sign ?? null,
             loops: [{ outer: out.outer || [], holes: out.holes || [] }],
             what: `a face of "${owner}"` };
  }
  const p = await planRequest({ tool: 'sketch', plane, offset: 0 });
  if (!p.ok) { say(`⚠ Cannot place the plane: ${p.error}.`); return null; }
  return { kind, plane, owner: null, frame: p.frame, intoSign: null, loops: null,
           what: `the ${plane} plane` };
}

/* The ribbon's Offset Plane: pick what the plane is measured from, then the
   step. The pick is the shared sketch-plane pick (origin quads + flat faces +
   existing planes); an existing plane is refused — the op measures from an
   origin plane or a face. */
export function openOffsetPlane() {
  if (modalGuard()) return;
  beginPlanePick((kind, data) => stageNew(kind, data));
}

/* the pick landed (exported for the browser tests, which stage a pick directly) */
export async function stageOffsetPlane(kind, data) { return stageNew(kind, data); }

async function stageNew(kind, data) {
  if (modalGuard()) return;             // the pick is a viewport CLICK — guard here too
  if (kind === 'plane' && !PRINCIPAL.includes(data)) {
    say('⚠ An offset plane is measured from an origin plane or a flat face — ' +
        'pick one of those (to move an existing plane, press ✎ on its row).');
    beginPlanePick((k, d) => stageNew(k, d));
    return;
  }
  let owner = null;
  if (kind === 'face') {
    owner = pickedBody(data);
    if (!owner) { say('⚠ No solid to measure from yet.'); return; }
  }
  const base = await baseFrame(kind, kind === 'plane' ? data : null,
                               kind === 'face' ? data : null, owner);
  if (!base) return;
  open({ ...base, mode: 'new', offset: 0, pick: data });
}

/* The tree's ✎ on an offset_plane row: the same step at the plane's current
   offset; OK writes the new offset (the plane and every sketch on it move). */
export async function editOffsetPlane(f) {
  if (modalGuard()) return;
  const p = f.params || {};
  const onFace = !!(f.inputs && f.inputs.length);
  const base = await baseFrame(onFace ? 'face' : 'plane', p.plane || 'XY',
    onFace ? { center: p.face_center || null, normal: p.face_normal || null,
               area: p.face_area ?? null, face: p.face || null } : null,
    onFace ? f.inputs[0] : null);
  if (!base) return;
  // the number to DRAW at is the server's resolved value; a FORMULA offset
  // ("-wall") is only replaced when the user really moves the plane (the
  // rule the sketch-plane review proved, 2026-09-22)
  const num = Number(f.resolved?.offset ?? p.offset ?? 0) || 0;
  open({ ...base, mode: 'edit', offset: num, featureId: f.id });
}

function open(o) {
  if (stage) close();                       // a pick while a step is open replaces it
  stage = o;
  S.modalTool = NAME; S.modalToolPanel = PANEL;
  g(PANEL).firstElementChild.textContent =
    o.mode === 'edit' ? `▱ Edit offset plane "${o.featureId}"` : '▱ Offset Plane';
  g('plWhat').textContent = o.what;
  g('plInto').textContent = o.intoSign == null ? ''
    : `${o.intoSign < 0 ? 'negative' : 'positive'} = into the material`;
  setLen('plOffset', o.offset);
  // what the box READS as, the moment it was filled. The box speaks the
  // DISPLAY unit and the offset is millimetres, so in inches the round trip
  // mm -> "-0.1575" -> mm comes back as -4.0005, not -4. Untouched means
  // untouched: `ok` then uses the offset the step opened with.
  o.shown = g('plOffset').value;
  g(PANEL).style.display = 'block';
  beginPlaneGhost(o.frame, o.loops);
  setPlaneGhost(o.offset);
  beginExtrudeArrow(o.frame.origin, o.frame.z_dir, o.offset, follow, follow, null);
  window.addEventListener('keydown', onKey, true);
  bus.on('doc-updated', onDoc);
  const box = g('plOffset');
  box.focus(); box.select();
}

/* the arrow moved: the box and the ghost follow (tenths of a mm) */
function follow(v) {
  const r = Math.round(v * 10) / 10;
  setLen('plOffset', r, 1);
  setPlaneGhost(r);
}
/* the box changed: the ghost and the arrow follow */
function typed() {
  if (!stage) return;
  const v = mm('plOffset');
  setPlaneGhost(v);
  setExtrudeArrowAmount(v);
}

function onKey(e) {
  if (!stage || e.key !== 'Escape' || e.repeat) return;
  e.preventDefault(); e.stopPropagation();
  cancel();
}
/* the document changed under the step (chat / MCP / another tab): the frame
   may be stale — let go, the user picks again */
function onDoc() { if (stage) close(); }

function close() {
  if (!stage) return;
  stage = null;
  endExtrudeArrow();
  endPlaneGhost();
  retakeSectionHandles();                   // the arrow is shared with Section view
  g(PANEL).style.display = 'none';
  if (S.modalTool === NAME) { S.modalTool = null; S.modalToolPanel = null; }
  window.removeEventListener('keydown', onKey, true);
  bus.off('doc-updated', onDoc);
}

export function cancelOffsetPlane() { cancel(); }
function cancel() {
  if (!stage) return;
  const wasEdit = stage.mode === 'edit';
  close();
  say(wasEdit ? 'Plane not moved.' : 'Offset Plane cancelled — nothing was added.');
}

/* plane1, plane2, … — the first name not in the tree */
function nextPlaneName() {
  const ids = new Set((S.lastDoc?.features || []).map(f => f.id));
  let n = 1;
  while (ids.has(`plane${n}`)) n++;
  return `plane${n}`;
}

/* OK / Enter: the step closes FIRST (it holds the modal lock), then the
   feature is added — or its offset written */
async function ok() {
  if (!stage) return;
  const st = stage;
  // the box untouched (still the exact string `open` filled it with) means the
  // offset it was opened with, not that string read back through the display
  // unit — see `open`
  const untouched = g('plOffset').value === st.shown;
  const off = untouched ? st.offset : mm('plOffset');
  close();
  if (st.mode === 'edit') {
    // NOTHING CHANGED? Then the document is not touched: no rebuild, no undo
    // entry, and a formula offset keeps its formula.
    if (untouched) { say(`Offset plane "${st.featureId}" unchanged.`); return; }
    const doc = await postJSON('/api/feature/params',
      { feature_id: st.featureId, params: { offset: off } }, 'moving the plane…');
    const f = (doc.features || []).find(x => x.id === st.featureId);
    say(doc.error || (f && f.status === 'failed')
      ? `⚠ Offset plane "${st.featureId}" problem: ${doc.error || f.problems.join('; ')}`
      : `Offset plane "${st.featureId}" moved to ${off} mm — every sketch on it followed.`);
    return;
  }
  const id = nextPlaneName();
  const params = st.kind === 'face'
    ? { face_center: st.pick.center, face_normal: st.pick.normal || null,
        face_area: st.pick.area ?? null, offset: off }
    : { plane: st.plane, offset: off };
  const doc = await postJSON('/api/feature/add',
    { id, op: 'offset_plane', params, inputs: st.kind === 'face' ? [st.owner] : [] },
    'adding the plane…');
  const f = (doc.features || []).find(x => x.id === id);
  if (doc.error || (f && f.status === 'failed')) {
    say(`⚠ Offset plane failed: ${doc.error || f.problems.join('; ')}`);
    return;
  }
  // select-then-command (fusion-parity rule 2): the new plane is the
  // selection, so Create Sketch lands on it without another pick
  bus.emit('select-feature', id);
  say(`Offset plane "${id}" placed ${off} mm from ${st.what}. Press Create Sketch ` +
      'to draw on it now. It stays out of the way until then: Create Sketch shows it ' +
      'again to click, and its row in the tree selects it.');
}

export function initOffsetPlane() {
  g('plOk').onclick = ok;
  g('plCancel').onclick = cancel;
  const box = g('plOffset');
  box.oninput = typed;
  box.onkeydown = e => {
    if (e.key === 'Enter') { e.preventDefault(); ok(); }
  };
}
