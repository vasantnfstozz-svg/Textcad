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
// ring's frame, radius and the profile outline as (radial, axial) pairs. This
// file draws what it is told and computes nothing: no vector maths in JS.

import { tool, g, num, say } from './tool.js';
import { beginAxisLine, endAxisLine,
         beginTaperRing, setTaperRingAngle, endTaperRing,
         beginRevolveGhost, setRevolveGhost, hideRevolveGhost, endRevolveGhost }
  from './viewport.js';

/* the limit is the server's (plan.limits.max_angle: one full turn either way;
   the kernel would quietly wrap 400° to 40°) */
const maxAngle = st => (st && st.plan && Number(st.plan.limits.max_angle)) || 360;
const clampAngle = (st, t) => Math.max(-maxAngle(st), Math.min(maxAngle(st), t));

/* ---------------- the panel <-> params ---------------- */
function params(st) {
  return { axis: g('rvAxis').value || 'v', angle: clampAngle(st, num('rvAngle')) };
}
/* write params into the boxes; {} = the honest default: 0°, nothing built yet */
function show(st, p) {
  g('rvAngle').value = p.angle || 0;
  // a legacy world-axis name ("Z", from an authored tree) is mapped onto u / v
  // by the plan; the select shows the plan's answer when it arrives
  if (p.axis === 'u' || p.axis === 'v') g('rvAxis').value = p.axis;
}
function snapshot(f) {
  const p = f.params || {};
  return { axis: p.axis || 'Z', angle: Number(p.angle) || 0 };
}

/* ---------------- the handles: axis line, ring, lathe ghost ---------------- */
const gizmos = {
  begin(st, plan) {
    g('rvAxis').value = plan.axis_name;
    for (const o of g('rvAxis').options) o.disabled = !plan.candidates.includes(o.value);
    beginAxisLine(plan.origin, plan.axis, plan.limits.axis_half);
    beginRevolveGhost(plan.frame, plan.loops);
    beginTaperRing(plan.origin, plan.frame, plan.limits.radius * 1.15, num('rvAngle'),
      t => {                                   // dragging: the instant ghost only
        g('rvAngle').value = Math.round(t * 10) / 10;
        setRevolveGhost(t);
      },
      async t => {                             // release: ONE real verified rebuild
        g('rvAngle').value = Math.round(t * 10) / 10;
        await rv.apply();
        hideRevolveGhost();                    // the real solid replaces the ghost
      },
      t => clampAngle(st, t), { continuous: true });   // 0..±360, not a ±180 wrap
  },
  end() { endAxisLine(); endTaperRing(); endRevolveGhost(); },
};
/* the user swapped the axis: a new plan places the handles on the other one */
function refresh(st) {
  if (!st || !st.plan || g('rvAxis').value === st.plan.axis_name) return;
  rv.plan({ axis: g('rvAxis').value }).then(plan => {
    if (!plan || rv.st !== st) return;
    st.plan = plan;
    gizmos.end();
    gizmos.begin(st, plan);
  });
}
function beforeApply(st) {                   // a typed value obeys the box's limit
  const a = num('rvAngle'), c = clampAngle(st, a);
  if (c !== a) { g('rvAngle').value = c; say(`Angle limited to ${c}° — one full turn.`); }
}
function afterApply(st) { setTaperRingAngle(num('rvAngle')); }

const rv = tool({
  name: 'Revolve', icon: '↻', tool: 'revolve',
  panel: 'revolveDialog', ids: 'rv',
  ops: { profile: 'revolve' },
  fields: { change: ['Axis'], typed: ['Angle'] },
  planExtra: st => ({ axis: st.editing ? st.original.axis : null }),
  show, params, snapshot, refresh, gizmos, beforeApply, afterApply,
  isEmpty: pr => pr.angle === 0,
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
