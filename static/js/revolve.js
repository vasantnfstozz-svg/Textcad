// revolve.js — Fusion-style Revolve ON the tool framework (tool.js), the first
// tool born on it (LAUNCH-PLAN.md P3, specs/revolve.md). This file declares
// only what makes Revolve different: its panel, its op, boxes ↔ params, and its
// handles — the gold axis line, the angle ring and the lathe ghost. Selection,
// the modal lock, the lazy verified preview, Join/Cut, edit-in-isolation,
// Cancel/OK and the failure sentences are inherited.
//
// THE AXIS IS DERIVED, NOT ASKED FOR (R1): the server tests the sketch plane's
// two axes through the sketch origin (u = the plane's x, v = its y) and hands
// back the one the profile does not cross — the lathe axis v first — plus the
// ring's frame, radius and the profile outline as (radial, axial) pairs, and
// the same for every other axis that works (a swap is a local choice between
// server answers, no request). This file draws what it is told.

import { tool, g, num, say, setBox } from './tool.js';
import { beginAxisLine, endAxisLine,
         beginTaperRing, setTaperRingAngle, endTaperRing,
         beginRevolveGhost, setRevolveGhost, hideRevolveGhost, endRevolveGhost }
  from './viewport.js';

/* the limit is the server's (plan.limits.max_angle: one full turn either way;
   the kernel would quietly wrap 400° to 40°) */
const maxAngle = st => (st && st.plan && Number(st.plan.limits.max_angle)) || 360;
const clampAngle = (st, t) => Math.max(-maxAngle(st), Math.min(maxAngle(st), t));
const LOCAL = ['u', 'v'];

/* ---------------- the panel <-> params ---------------- */
function params(st) {                          // typed values are clamped in beforeApply, drags by the ring
  return { axis: g('rvAxis').value || 'v', angle: num('rvAngle') };
}
/* write params into the boxes; {} = the honest default: 0°, nothing built yet.
   The select starts on the lathe axis; the plan moves it if that one is crossed. */
function show(st, p) {
  g('rvAngle').value = p.angle || 0;
  g('rvAxis').value = LOCAL.includes(p.axis) ? p.axis : 'v';
}
/* the op's defaults ARE the feature's values when a tree names none (a legacy
   revolve with only an angle spins about Z; one without an angle is a full turn)
   — Cancel must push back what the feature meant, not a 0 that fails */
function snapshot(f) {
  const p = f.params || {};
  return { axis: p.axis || 'Z', angle: p.angle == null ? 360 : Number(p.angle) };
}

/* ---------------- the handles: axis line, ring, lathe ghost ---------------- */
function setAxisOptions(plan) {
  const sel = g('rvAxis');
  if (!LOCAL.includes(plan.axis_name) && ![...sel.options].some(o => o.value === plan.axis_name))
    sel.add(new Option(`${plan.axis_name} — world axis`, plan.axis_name));   // a legacy tree's axis
  for (const o of sel.options) o.disabled = !plan.candidates.includes(o.value);
  sel.value = plan.axis_name;
}
const gizmos = {
  begin(st, plan) {
    setAxisOptions(plan);
    if (plan.fallback && !st.saidFallback) {   // rule 7: the stored axis is not usable
      st.saidFallback = true;
      say(`⚠ This revolve's axis ${plan.fallback.from} cannot be used: ${plan.fallback.why}. ` +
        `The tool opened on ${plan.axis_name} — OK saves that, Cancel keeps the old one.`);
    }
    beginAxisLine(plan.origin, plan.axis, plan.limits.axis_half);
    beginRevolveGhost(plan.frame, plan.loops);
    beginTaperRing(plan.origin, plan.frame, plan.limits.radius * 1.15, num('rvAngle'),
      t => { setBox('rvAngle', t); setRevolveGhost(t); },     // dragging: the ghost only
      async t => {                                            // release: ONE verified rebuild
        setBox('rvAngle', t);
        await rv.apply();
        hideRevolveGhost();                                   // the real solid replaces the ghost
      },
      t => clampAngle(st, t));
    // a value typed or Full pressed before the plan arrived waits for it
    if (!st.featureId && num('rvAngle') !== 0) rv.apply();
  },
  end() { endAxisLine(); endTaperRing(); endRevolveGhost(); },
};
/* the user swapped the axis: the plan already carries the other axis's
   handles — a local choice, no request, nothing to race */
function refresh(st) {
  if (!st || !st.plan) return;
  const name = g('rvAxis').value;
  const alt = name !== st.plan.axis_name && st.plan.alternatives && st.plan.alternatives[name];
  if (!alt) return;
  const rest = { ...st.plan.alternatives, [st.plan.axis_name]: {
    axis: st.plan.axis, origin: st.plan.origin, frame: st.plan.frame,
    loops: st.plan.loops, limits: st.plan.limits } };
  delete rest[name];
  st.plan = { ...st.plan, ...alt, axis_name: name, alternatives: rest, fallback: null };
  gizmos.end();
  gizmos.begin(st, st.plan);
}
function beforeApply(st) {                   // a typed value obeys the server's limit
  const a = num('rvAngle'), c = clampAngle(st, a);
  if (c !== a) { g('rvAngle').value = c; say(`Angle limited to ${c}° — one full turn.`); }
}
function afterApply(st) { setTaperRingAngle(num('rvAngle')); }

const rv = tool({
  name: 'Revolve', icon: '↻', tool: 'revolve',
  panel: 'revolveDialog', ids: 'rv',
  ops: { profile: 'revolve' },
  fields: { change: ['Axis'], typed: ['Angle'] },
  show, params, snapshot, refresh, gizmos, beforeApply, afterApply,
  isEmpty: (pr, st) => pr.angle === 0 || !st.plan,   // no plan yet: the plan's arrival applies
  nothing: 'Nothing revolved — the angle was 0. Open Revolve again, then drag the ' +
           'ring or type an angle before OK.',
  split: () => 'the revolved cut leaves material on both sides — revolve the ' +
               'full 360°, or move the profile.',
  describe: p => `${p.angle}° about ${p.axis}`,
});

export const openRevolve = profileId => rv.open(profileId);
export function initRevolve() {
  rv.init();
  g('rvFull').onclick = () => { g('rvAngle').value = 360; rv.apply(); };
}
