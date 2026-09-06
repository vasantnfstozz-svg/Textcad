// hole.js — Fusion's Hole on the tool framework (tool.js) — LAUNCH-PLAN.md P4,
// specs/hole.md. ONE op (`hole`) that EATS its body: click a flat face where
// the hole goes, press Hole, drag the arrow into the material. This file says
// only what makes a hole different: its panel, boxes <-> params, and its
// handles — the gold circle where the hole will cut and the arrow that drags
// the depth. Selection, the modal lock, the lazy verified preview, edit-in-
// isolation, Cancel/OK, Esc and the failure sentences are inherited.
//
// EVERY geometric fact is the plan's (R1): the point on the face in the
// face's own coordinates (`at`, what the op stores), the face in stored form,
// the axis INTO the material, the marker's frame, and how much material lies
// under the point. A second click on the body's face moves the hole (the
// framework's `repick`). There is no ghost: a cut is drawn only by the kernel
// — the value box follows the drag live and the real hole appears on release.

import { tool, g, num, say, setBox } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginHoleMarker, setHoleMarker, endHoleMarker } from './viewport.js';

const ROWS = { counterbore: ['hoCbDiaRow', 'hoCbDepthRow'],
               countersink: ['hoCsDiaRow', 'hoCsAngleRow'] };
const ALL_ROWS = [...ROWS.counterbore, ...ROWS.countersink];
let lastDia = 6;                          // Fusion remembers the last hole's size; so do we
const through = () => g('hoThrough').checked;

/* the boxes -> the op's params. `at` and the face are the plan's; before the
   plan lands (OK pressed straight after an edit opened) the feature's OWN
   values stand in, so a rebuild is never asked for a hole nowhere. */
function params(st) {
  const kind = g('hoKind').value;
  const src = (st && st.plan) || (st && st.original) || {};
  const p = { at: src.at || null, diameter: Math.max(0, num('hoDia')),
              depth: Math.max(0, num('hoDepth')), through: through(), kind,
              face_center: src.face_center || (st && st.input.center) || null,
              face_normal: src.face_normal || (st && st.input.normal) || null };
  if (kind === 'counterbore') { p.cbore_diameter = num('hoCbDia'); p.cbore_depth = num('hoCbDepth'); }
  if (kind === 'countersink') { p.csink_diameter = num('hoCsDia'); p.csink_angle = num('hoCsAngle'); }
  return p;
}
/* {} = the honest default: nothing drilled yet — depth 0, the remembered size
   (a diameter is a size, not an amount: nothing is cut until there is a depth) */
function show(st, p) {
  g('hoKind').value = p.kind || 'simple';
  g('hoDia').value = p.diameter != null ? p.diameter : lastDia;
  g('hoDepth').value = p.depth || 0;
  g('hoThrough').checked = !!p.through;
  g('hoCbDia').value = p.cbore_diameter || 0;
  g('hoCbDepth').value = p.cbore_depth || 0;
  g('hoCsDia').value = p.csink_diameter || 0;
  g('hoCsAngle').value = p.csink_angle || 90;
}
/* every param the tool can write, normalized — Cancel-in-edit puts it back verbatim */
function snapshot(f) {
  const p = f.params || {};
  return { at: p.at || null, diameter: Number(p.diameter) || 0, depth: Number(p.depth) || 0,
           through: !!p.through, kind: p.kind || 'simple',
           cbore_diameter: Number(p.cbore_diameter) || 0, cbore_depth: Number(p.cbore_depth) || 0,
           csink_diameter: Number(p.csink_diameter) || 0, csink_angle: Number(p.csink_angle) || 90,
           face_center: p.face_center || null, face_normal: p.face_normal || null };
}
function sync() {
  const rows = ROWS[g('hoKind').value] || [];
  for (const id of ALL_ROWS) g(id).style.display = rows.includes(id) ? '' : 'none';
  g('hoDepth').disabled = through();      // Through all: the depth is the body's
}
/* honest zero: no plan yet (its arrival applies), no point, no size, no depth */
const isEmpty = (pr, st) =>
  !st.plan || !pr.at || !(pr.diameter > 0) || (!pr.through && !(pr.depth > 0));

/* ---------------- the handles: the circle and the depth arrow ---------------- */
function place(st, plan) {
  beginHoleMarker(plan.frame, num('hoDia') / 2);
  if (through()) return;                  // nothing to drag: the hole runs out the far side
  beginExtrudeArrow(plan.origin, plan.axis, num('hoDepth'),
    v => setBox('hoDepth', v),                                // dragging: the box follows
    async v => { setBox('hoDepth', v); await ho.apply(); },   // release: ONE verified rebuild
    v => Math.max(0, v));                                     // a depth has no sign
}
const gizmos = {
  begin(st, plan) {
    place(st, plan);
    // a depth typed or Through ticked before the plan arrived waits for it
    if (!st.featureId && (through() || num('hoDepth') > 0)) ho.apply();
  },
  end() { endHoleMarker(); endExtrudeArrow(); },
};
/* Type or Through changed: the rows follow (sync) and the arrow comes or goes */
function refresh(st) { if (st && st.plan) { gizmos.end(); place(st, st.plan); } }
/* the material under the point is the plan's: a blind depth past it comes out
   the other side — allowed, as in Fusion, but said once (rule 7) */
function beforeApply(st) {
  const m = st && st.plan && st.plan.limits && st.plan.limits.material;
  if (m && !through() && num('hoDepth') > m + 1e-6 && !st.saidThrough) {
    st.saidThrough = true;
    say(`ℹ The material under this point is ${m} mm — a depth of ${num('hoDepth')} mm ` +
        'comes out the other side. Through all says that on purpose.');
  }
}
function afterApply() {
  setExtrudeArrowAmount(num('hoDepth'));
  setHoleMarker(num('hoDia') / 2);
  if (num('hoDia') > 0) lastDia = num('hoDia');
}
const KIND_WORD = { simple: '', counterbore: ', counterbored', countersink: ', countersunk' };

const ho = tool({
  name: 'Hole', icon: '◎', tool: 'hole',
  panel: 'holeDialog', ids: 'ho',
  ops: { face: 'hole' },        // face only — Fusion's At Point placement; no sketch profile
  eats: true,                   // the op returns the body WITH the hole: no Join / Cut row
  repick: 'Click a flat face of the body to move the hole · drag the arrow for the depth · Esc cancels',
  fields: { change: ['Kind', 'Through'],
            typed: ['Dia', 'Depth', 'CbDia', 'CbDepth', 'CsDia', 'CsAngle'] },
  show, params, snapshot, sync, refresh, gizmos, beforeApply, afterApply, isEmpty,
  nothing: 'Nothing drilled — the depth was 0. Open Hole again, then drag the arrow or ' +
           'type a depth (or tick Through all) before OK.',
  split: () => 'the hole cuts the part in two — move it, or make it smaller.',
  describe: p => `⌀${p.diameter} ${p.through ? 'through' : `${p.depth} mm deep`}` +
                 (KIND_WORD[p.kind] || ''),
});

export const openHole = () => ho.open();
export function initHole() {
  ho.init();
  // the circle follows the Diameter box at once; the hole itself after the usual pause
  g('hoDia').addEventListener('input', () => setHoleMarker(num('hoDia') / 2));
}
