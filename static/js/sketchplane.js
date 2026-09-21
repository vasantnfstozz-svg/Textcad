// sketchplane.js — the OFFSET step of Create Sketch: "move the sketch plane".
//
// Create Sketch picks an origin plane or a flat face in the viewport. Before
// the sketch opens, the picked plane is drawn where the sketch WILL land, with
// ONE arrow along its normal and an Offset box; drag or type, OK (or Enter)
// opens sketch mode on the shifted plane, Esc / Cancel goes back. The offset
// is the sketch feature's own `offset` parameter — a `sketch` on XY at z = 20
// for a loft section, a face sketch 3 mm INTO the material (the offset
// method) — and stays editable in the tree afterwards. Enter with 0 is exactly
// the old flow, so nothing changes for a plain sketch.
//
// EVERY geometric fact is the server's (LAUNCH-PLAN R1): the frame comes from
// /api/tool/plan (plane) or /api/face-outline (face), which SIGN of the offset
// goes into the material is that response's `into_sign`, the ghost moves along
// the frame's z by the dragged amount exactly as Plane.offset does on the
// server, and the sketch reopens its frame FROM the server at the chosen
// offset — the grid is drawn where the kernel will build, never where this
// module thinks it will.
//
// ONE COMMAND AT A TIME (fusion-parity rule 9): the step takes the modal lock
// like a tool panel, so Extrude & co. refuse until OK or Cancel.

import { bus } from './bus.js';
import { S } from './state.js';
import { planRequest } from './api.js';
import { g, mm, setLen, say, pickedBody } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginPlaneGhost, setPlaneGhost, endPlaneGhost,
         retakeSectionHandles } from './viewport.js';
import { openSketchEditor, openSketchOnFace, fetchFaceOutline,
         currentSketchPlane, setSketchPlaneOffset, pauseSketchInput } from './sketcher.js';

const NAME = 'Sketch plane';
const PANEL = 'planeDialog';
// { mode: 'new' | 'move', kind, what, frame, loops, intoSign, owner, onOk } while open
let stage = null;

/* for tests and other modules: is the offset step open, and on what */
export const sketchPlaneStage = () => stage
  ? { mode: stage.mode, kind: stage.kind, plane: stage.kind === 'plane' ? stage.plane : null,
      owner: stage.owner, offset: mm('plOffset'), intoSign: stage.intoSign }
  : null;

/* The plane's frame at offset 0 — the base the arrow and the ghost measure
   from — fetched from the server: kind 'plane' (plane = 'XY' | 'XZ' | 'YZ')
   or 'face' (face = {center, normal, area}, owner = the body it is on).
   null when it cannot be had; the reason has been said. */
async function baseFrame(kind, plane, face, owner) {
  if (kind === 'face') {
    // by geometry (a pick's centre) or by NAME (an authored face: "top") — both
    // are how sketch_on_face itself names its face
    const out = await fetchFaceOutline({ center: face.center || null, normal: face.normal || null,
                                         area: face.area ?? null, face: face.face || null,
                                         featureId: owner });
    if (!out?.planar || !out.frame) {
      say('⚠ ' + (out?.error || 'That face is curved — a sketch needs a FLAT face. ' +
                                'Pick a planar face, or sketch on an origin plane instead.'));
      return null;
    }
    return { kind, owner, frame: out.frame, intoSign: out.into_sign ?? null,
             loops: [{ outer: out.outer || [], holes: out.holes || [] }],
             what: `a face of "${owner}"` };
  }
  const p = await planRequest({ tool: 'sketch', plane, offset: 0 });
  if (!p.ok) { say(`⚠ Cannot open the sketch: ${p.error}.`); return null; }
  return { kind, plane, owner: null, frame: p.frame, intoSign: null, loops: null,
           what: `the ${plane} plane` };
}

/* Create Sketch's pick landed: kind 'plane' (data = 'XY' | 'XZ' | 'YZ') or
   'face' (data = the viewport's face info). Fetch the frame, then show the
   plane, the arrow and the box; OK opens the sketch at the offset. */
export async function stageSketchPlane(kind, data) {
  let owner = null;
  if (kind === 'face') {
    owner = pickedBody(data);
    if (!owner) { say('⚠ No solid to sketch on yet.'); return; }
  }
  const base = await baseFrame(kind, kind === 'plane' ? data : null,
                               kind === 'face' ? data : null, owner);
  if (!base) return;
  open({ ...base, mode: 'new', offset: 0,
         onOk: off => (kind === 'face' ? openSketchOnFace(data, off)
                                       : openSketchEditor(data, off)) });
}

/* The SKETCH tab's Move Plane: the same step over the OPEN sketch, starting
   at its current offset; OK re-planes the sketch with its shapes on it. */
export async function moveSketchPlane() {
  const cur = currentSketchPlane();
  if (!cur) { say('⚠ Move Plane works inside an open sketch — Create Sketch first.'); return; }
  if (S.modalTool && !(stage && stage.mode === 'move')) {
    say(`⚠ Finish the ${S.modalTool} first — press OK or Cancel in its panel.`);
    return;
  }
  const base = await baseFrame(cur.kind, cur.plane || null, cur.face || null,
                               cur.face ? cur.face.inputId : null);
  if (!base) return;
  open({ ...base, mode: 'move', offset: cur.offset,
         onOk: off => setSketchPlaneOffset(off) });
}

function open(o) {
  if (stage) close();                       // a pick while a step is open replaces it
  stage = o;
  S.modalTool = NAME; S.modalToolPanel = PANEL;
  g(PANEL).firstElementChild.textContent =
    o.mode === 'move' ? '✎ Move sketch plane' : '✎ Sketch plane';
  g('plWhat').textContent = o.what;
  g('plInto').textContent = o.intoSign == null ? ''
    : `${o.intoSign < 0 ? 'negative' : 'positive'} = into the material`;
  setLen('plOffset', o.offset);
  g(PANEL).style.display = 'block';
  beginPlaneGhost(o.frame, o.loops);
  setPlaneGhost(o.offset);
  beginExtrudeArrow(o.frame.origin, o.frame.z_dir, o.offset, follow, follow, null);
  if (o.mode === 'move') pauseSketchInput(true);
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
  const wasMove = stage.mode === 'move';
  stage = null;
  if (wasMove) pauseSketchInput(false);
  endExtrudeArrow();
  endPlaneGhost();
  retakeSectionHandles();                   // the arrow is shared with Section view
  g(PANEL).style.display = 'none';
  if (S.modalTool === NAME) { S.modalTool = null; S.modalToolPanel = null; }
  window.removeEventListener('keydown', onKey, true);
  bus.off('doc-updated', onDoc);
}

export function cancelSketchPlane() { cancel(); }
function cancel() {
  if (!stage) return;
  const wasMove = stage.mode === 'move';
  close();
  say(wasMove ? 'Plane not moved — the sketch stays where it was.'
              : 'Sketch cancelled — nothing was drawn.');
}

/* OK / Enter: the step closes FIRST (it holds the modal lock the sketch
   editor's own guard would refuse on), then the sketch opens — or is
   re-planed — at the offset */
function ok() {
  if (!stage) return;
  const st = stage;
  const off = mm('plOffset');
  close();
  st.onOk(off);
}

export function initSketchPlane() {
  // leaving sketch mode (Finish / Cancel Sketch) ends a Move Plane step
  bus.on('sketch-mode', ({ active }) => {
    if (!active && stage && stage.mode === 'move') close();
  });
  g('plOk').onclick = ok;
  g('plCancel').onclick = cancel;
  const box = g('plOffset');
  box.oninput = typed;
  box.onkeydown = e => {
    if (e.key === 'Enter') { e.preventDefault(); ok(); }
  };
}
