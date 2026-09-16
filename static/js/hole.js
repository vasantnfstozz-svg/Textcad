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
// framework's `repick`). While the arrow is dragged a GHOST shows the cut —
// the Extrude ghost fed the hole's own circle (and a counterbore's wider seat)
// in the plan's frame, grown along the plan's axis into the material — and
// the real hole, drawn by the kernel, replaces it on release (user, 2026-09-06:
// the arrow of Extrude and Revolve has one, so must Hole's).

import { tool, g, num, say, setBox } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginExtrudeGhost, setExtrudeGhost, hideExtrudeGhost, endExtrudeGhost,
         beginHoleMarker, setHoleMarker, endHoleMarker } from './viewport.js';

const ROWS = { counterbore: ['hoCbDiaRow', 'hoCbDepthRow'],
               countersink: ['hoCsDiaRow', 'hoCsAngleRow'] };
const ALL_ROWS = [...ROWS.counterbore, ...ROWS.countersink];
let lastDia = 6;                          // Fusion remembers the last hole's size; so do we
const through = () => g('hoThrough').checked;

/* the boxes -> the op's params. `at` and the face are the plan's; before the
   plan lands (OK pressed straight after an edit opened) the feature's OWN
   values stand in, so a rebuild is never asked for a hole nowhere.
   The face goes in ONE form, the plan's: a NAME (an AI-authored hole nobody
   has moved) or the pick's geometry. Sending both lets them disagree — and the
   name wins in the op, so it would pin the hole to its old face for ever,
   however many times the user clicked another one. */
function params(st) {
  const kind = g('hoKind').value;
  const src = (st && st.plan) || (st && st.original) || {};
  const named = src.face || null;
  const p = { at: src.at || null, diameter: Math.max(0, num('hoDia')),
              depth: Math.max(0, num('hoDepth')), through: through(), kind,
              face: named,
              face_center: named ? null : (src.face_center || (st && st.input.center) || null),
              face_normal: named ? null : (src.face_normal || (st && st.input.normal) || null),
              // the plan answers with the size of the face it drilled into; the
              // pick carries it before the first plan lands
              face_area: named ? null
                : (src.face_area ?? (st && st.input.area) ?? null) };
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
           face: p.face || null,
           face_center: p.face_center || null, face_normal: p.face_normal || null,
           face_area: p.face_area == null ? null : p.face_area };
}
function sync() {
  const rows = ROWS[g('hoKind').value] || [];
  for (const id of ALL_ROWS) g(id).style.display = rows.includes(id) ? '' : 'none';
  g('hoDepth').disabled = through();      // Through all: the depth is the body's
}
/* honest zero: no plan yet (its arrival applies), no point, no size, no depth */
const isEmpty = (pr, st) =>
  !st.plan || !pr.at || !(pr.diameter > 0) || (!pr.through && !(pr.depth > 0));

/* Choosing a seat KIND fills sensible sizes at once (Fusion shows a seat the
   moment you pick one) — into boxes still at 0 only, so a typed value is never
   overwritten, and never deeper than the hole has room for. Without them the
   op refuses a ⌀0 seat, the framework reverts, and the Type box springs back
   to Simple: the seat kinds were unreachable once a depth existed. */
function seed() {
  const kind = g('hoKind').value, d = num('hoDia') || lastDia;
  // the room a seat has to sit in. No depth yet (or Through all) puts no limit
  // on it: the seat comes from the diameter, and a depth later typed too small
  // for it is the op's own sentence, not a 0.1 mm seat nobody can see.
  const room = through() || !(num('hoDepth') > 0) ? Infinity : num('hoDepth');
  if (kind === 'counterbore') {
    if (!(num('hoCbDia') > 0)) setBox('hoCbDia', 2 * d);
    if (!(num('hoCbDepth') > 0)) setBox('hoCbDepth', Math.max(0.1, Math.min(d / 2, room * 0.4)));
  } else if (kind === 'countersink') {
    if (!(num('hoCsAngle') > 0)) setBox('hoCsAngle', 90);
    const t = Math.tan(Math.PI / 360 * num('hoCsAngle'));      // the cone's half-angle
    if (!(num('hoCsDia') > 0)) setBox('hoCsDia', Math.min(2 * d, d + 0.8 * room * t));
  }
}
/* Values the op would CERTAINLY refuse because the user is mid-change. The
   framework holds them back: applying would fail, and the automatic revert
   would undo the very choice they just made (the Type box back to Simple,
   Through all re-ticking itself). Said once, then the tool waits. */
function hold(pr) {
  if (!pr.through && !(pr.depth > 0))
    return 'The hole is unchanged until it has a depth — drag the arrow or type one ' +
           '(or tick Through all).';
  if (pr.kind === 'counterbore' && !(pr.cbore_diameter > pr.diameter && pr.cbore_depth > 0))
    return `Counterbore: type a seat ⌀ wider than ${pr.diameter} mm, and a seat depth.`;
  if (pr.kind === 'countersink' && !(pr.csink_diameter > pr.diameter))
    return `Countersink: type a seat ⌀ wider than ${pr.diameter} mm.`;
  return null;
}

/* ---------------- the handles: the circle, the depth arrow, the ghost ----------------
   The ghost is Extrude's (a translucent prism of an outline in a server frame)
   given the hole's outline: a circle of the Diameter in the plan's marker
   frame, plus the seat's wider circle for a counterbore, capped at the seat
   depth (a countersink's cone is not drawn — the ghost is a drag aid, the
   solid is exact). It grows along the plan's AXIS whichever way the frame's z
   points — one tool, one axis (fusion-parity, 2026-09-01) — so the sign is
   the dot product of two plan vectors, never a guess about the face. */
const SIDES = 48;
function circle(r) {
  return Array.from({ length: SIDES }, (_, i) => {
    const a = i / SIDES * Math.PI * 2;
    return [r * Math.cos(a), r * Math.sin(a)];
  });
}
const seated = () => g('hoKind').value === 'counterbore'
  && num('hoCbDia') > num('hoDia') && num('hoCbDepth') > 0;
function ghost(st) {
  endExtrudeGhost();
  const plan = st && st.plan;
  if (!plan || through() || !(num('hoDia') > 0)) return;   // through: no arrow, nothing to drag
  const loops = [{ outer: circle(num('hoDia') / 2), holes: [] }];
  if (seated()) loops.push({ outer: circle(num('hoCbDia') / 2), holes: [] });
  const z = plan.frame.z_dir, a = plan.axis;
  st.ghostSign = z[0] * a[0] + z[1] * a[1] + z[2] * a[2] < 0 ? -1 : 1;
  beginExtrudeGhost(plan.frame, loops);
}
function showGhost(st, depth) {
  setExtrudeGhost(depth * (st.ghostSign || 1), 0, seated() ? [null, num('hoCbDepth')] : null);
}
function arrow(st) {
  beginExtrudeArrow(st.plan.origin, st.plan.axis, num('hoDepth'),
    v => { setBox('hoDepth', v); showGhost(st, v); },        // dragging: the box and the ghost follow
    async v => {                                              // release: ONE verified rebuild
      setBox('hoDepth', v);
      await ho.apply();
      hideExtrudeGhost();                                     // the real hole replaces the ghost
    },
    v => Math.max(0, v));                                     // a depth has no sign
}
const gizmos = {
  begin(st, plan) {
    st.material = undefined;              // a new point: what lies under it is unknown again
    st.saidThrough = false;
    beginHoleMarker(plan.frame, num('hoDia') / 2);
    if (!through()) arrow(st);            // through: nothing to drag, it runs out the far side
    ghost(st);
    // a depth typed or Through ticked before the plan arrived waits for it
    if (!st.featureId && (through() || num('hoDepth') > 0)) ho.apply();
  },
  end() { endHoleMarker(); endExtrudeArrow(); endExtrudeGhost(); },
};
/* Type or Through changed: the rows follow (sync), a seat kind gets its sizes,
   and only the ARROW and the ghost come or go — the circle marks where the
   hole IS, which neither of them moves (re-making it flickered and stranded
   its material). */
function refresh(st) {
  if (!st) return;
  seed();
  if (!st.plan) return;
  endExtrudeArrow();
  if (!through()) arrow(st);
  ghost(st);
}
/* How much material lies under the point is the plan's — and it costs the
   server a kernel boolean (250-510 ms on a real body), so it is asked for the
   FIRST time a blind depth could pass through it, never for a through hole,
   the way Extrude asks for its taper limits. A depth past the material is
   allowed, as in Fusion, but said once (rule 7). */
async function ensureMaterial(st) {
  st.material = null;                     // asked: never twice for the same point
  const asked = st.input.point;           // WHICH point this answer is about — a
  const plan = await ho.plan({ measure_material: true }, true);   // re-pick keeps
  if (ho.st !== st || st.input.point !== asked) return;   // the same session object
  st.material = (plan && plan.limits && plan.limits.material) || null;
  warnMaterial(st);
}
function warnMaterial(st) {
  if (!st.material || through() || st.saidThrough) return;
  if (!(num('hoDepth') > st.material + 1e-6)) return;
  st.saidThrough = true;
  say(`ℹ The material under this point is ${st.material} mm — a depth of ` +
      `${num('hoDepth')} mm comes out the other side. Through all says that on purpose.`);
}
function beforeApply(st) {
  if (through() || !(num('hoDepth') > 0) || !st.plan) return;
  if (st.material === undefined) ensureMaterial(st);   // in the background: it only speaks
  else warnMaterial(st);
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
  show, params, snapshot, sync, refresh, gizmos, beforeApply, afterApply, isEmpty, hold,
  nothing: 'Nothing drilled — the depth was 0. Open Hole again, then drag the arrow or ' +
           'type a depth (or tick Through all) before OK.',
  split: () => 'the hole cuts the part in two — move it, or make it smaller.',
  describe: p => `⌀${p.diameter} ${p.through ? 'through' : `${p.depth} mm deep`}` +
                 (KIND_WORD[p.kind] || ''),
});

export const openHole = () => ho.open();
export function initHole() {
  ho.init();
  // the circle and the ghost's outline follow the size boxes at once; the
  // hole itself after the usual pause
  g('hoDia').addEventListener('input', () => { setHoleMarker(num('hoDia') / 2); ghost(ho.st); });
  for (const id of ['hoCbDia', 'hoCbDepth']) g(id).addEventListener('input', () => ghost(ho.st));
}
