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
import { openSketchEditor, openSketchOnFace, fetchFaceOutline } from './sketcher.js';

const NAME = 'Sketch plane';
const PANEL = 'planeDialog';
let stage = null;      // { kind, data, frame, owner, intoSign } while the step is open

/* for tests and other modules: is the offset step open, and on what */
export const sketchPlaneStage = () => stage
  ? { kind: stage.kind, plane: stage.kind === 'plane' ? stage.data : null,
      owner: stage.owner, offset: mm('plOffset'), intoSign: stage.intoSign }
  : null;

/* Create Sketch's pick landed: kind 'plane' (data = 'XY' | 'XZ' | 'YZ') or
   'face' (data = the viewport's face info). Fetch the frame, then show the
   plane, the arrow and the box. */
export async function stageSketchPlane(kind, data) {
  let frame, loops = null, owner = null, intoSign = null, what;
  if (kind === 'face') {
    owner = pickedBody(data);
    if (!owner) { say('⚠ No solid to sketch on yet.'); return; }
    const out = await fetchFaceOutline({ center: data.center, normal: data.normal || null,
                                         area: data.area ?? null, featureId: owner });
    if (!out?.planar || !out.frame) {
      say('⚠ ' + (out?.error || 'That face is curved — a sketch needs a FLAT face. ' +
                                'Pick a planar face, or sketch on an origin plane instead.'));
      return;
    }
    frame = out.frame;
    loops = [{ outer: out.outer || [], holes: out.holes || [] }];
    intoSign = out.into_sign ?? null;
    what = `a face of "${owner}"`;
  } else {
    const p = await planRequest({ tool: 'sketch', plane: data, offset: 0 });
    if (!p.ok) { say(`⚠ Cannot open the sketch: ${p.error}.`); return; }
    frame = p.frame;
    what = `the ${data} plane`;
  }
  if (stage) close();                       // a pick while a step is open replaces it
  stage = { kind, data, frame, owner, intoSign };
  S.modalTool = NAME; S.modalToolPanel = PANEL;
  g('plWhat').textContent = what;
  g('plInto').textContent = intoSign == null ? ''
    : `${intoSign < 0 ? 'negative' : 'positive'} = into the material`;
  setLen('plOffset', 0);
  g(PANEL).style.display = 'block';
  beginPlaneGhost(frame, loops);
  beginExtrudeArrow(frame.origin, frame.z_dir, 0, follow, follow, null);
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

export function cancelSketchPlane() { cancel(); }
function cancel() {
  if (!stage) return;
  close();
  say('Sketch cancelled — nothing was drawn.');
}

/* OK / Enter: the step closes FIRST (it holds the modal lock the sketch
   editor's own guard would refuse on), then the sketch opens at the offset */
function ok() {
  if (!stage) return;
  const st = stage;
  const off = mm('plOffset');
  close();
  if (st.kind === 'face') openSketchOnFace(st.data, off);
  else openSketchEditor(st.data, off);
}

export function initSketchPlane() {
  g('plOk').onclick = ok;
  g('plCancel').onclick = cancel;
  const box = g('plOffset');
  box.oninput = typed;
  box.onkeydown = e => {
    if (e.key === 'Enter') { e.preventDefault(); ok(); }
  };
}
