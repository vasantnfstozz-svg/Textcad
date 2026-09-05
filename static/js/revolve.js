// revolve.js — Fusion-style Revolve ON the tool framework (tool.js), the first
// tool born on it (LAUNCH-PLAN.md P3 + P3b, specs/revolve.md). This file
// declares only what makes Revolve different: its panel, its ops (revolve for a
// sketch profile, revolve_face for a picked flat face), boxes ↔ params, and its
// handles — the gold axis line, the angle ring and the lathe ghost. Selection,
// the modal lock, the lazy verified preview, Join/Cut, edit-in-isolation,
// Cancel/OK and the failure sentences are inherited.
//
// THE AXIS IS DERIVED, NOT ASKED FOR (R1): the server tests every axis the
// profile could turn about — the plane's u and v through the sketch origin, and
// each straight edge of the outline — and hands back the list (`axes`, each
// with the label to show and the `param` the feature stores: a name, or a line
// in the sketch plane), the chosen one's ring frame, radius and lathe outline,
// and the same handles for every other axis that works (a swap is a local
// choice between server answers, no request). This file draws what it is told.

import { tool, g, num, say, setBox } from './tool.js';
import { beginAxisLine, endAxisLine,
         beginTaperRing, setTaperRingAngle, endTaperRing,
         beginRevolveGhost, setRevolveGhost, hideRevolveGhost, endRevolveGhost }
  from './viewport.js';

/* the limit is the server's (plan.limits.max_angle: one full turn either way;
   the kernel would quietly wrap 400° to 40°). The Direction row shares it out:
   one side may take the whole turn, symmetric half of it each way, two sides
   split it between them — the mode's own arithmetic, no geometry. */
const maxAngle = st => (st && st.plan && Number(st.plan.limits.max_angle)) || 360;
const dir = () => g('rvDir').value;
const angle2 = () => Math.max(0, num('rvAngle2'));
const ceiling = st => dir() === 'sym' ? maxAngle(st) / 2
  : dir() === 'two' ? Math.max(0, maxAngle(st) - angle2()) : maxAngle(st);
const clampAngle = (st, t) => Math.max(-ceiling(st), Math.min(ceiling(st), t));
/* what sweeps the OTHER way, for the ghost: symmetric mirrors side one */
const back = () => dir() === 'sym' ? Math.abs(num('rvAngle')) : dir() === 'two' ? angle2() : 0;
const isFace = st => !!(st && st.input && st.input.kind === 'face');

/* ---------------- the panel <-> params ---------------- */
/* the axis the select names → what the feature stores: the plan's `param` for
   that entry ("u", "v", a world name, or a line in the sketch plane) */
function axisParam(st) {
  const name = g('rvAxis').value || 'v';
  const e = st && st.plan && (st.plan.axes || []).find(a => a.name === name);
  return e ? e.param : name;
}
function params(st) {                          // typed values are clamped in beforeApply, drags by the ring
  const p = { axis: axisParam(st), angle: num('rvAngle'),
              angle2: dir() === 'two' ? angle2() : 0, symmetric: dir() === 'sym' };
  if (isFace(st)) { p.face_center = st.input.center; p.face_normal = st.input.normal; }
  return p;
}
/* write params into the boxes; {} = the honest default: 0°, one side, nothing
   built yet. The axis list is the plan's (setAxisOptions) — until it arrives
   the static u / v options stand, and a stored line has no row to select. */
function show(st, p) {
  g('rvDir').value = p.symmetric ? 'sym' : (p.angle2 ? 'two' : 'one');
  g('rvAngle').value = p.angle || 0;
  g('rvAngle2').value = p.angle2 || 0;
  const sel = g('rvAxis');
  if (typeof p.axis === 'string' && [...sel.options].some(o => o.value === p.axis)) sel.value = p.axis;
}
/* the op's defaults ARE the feature's values when a tree names none (a legacy
   revolve with only an angle spins about Z; one without an angle is a full turn)
   — Cancel must push back what the feature meant, not a 0 that fails */
function snapshot(f) {
  const p = f.params || {};
  const s = { axis: p.axis == null ? (f.op === 'revolve_face' ? null : 'Z') : p.axis,
              angle: p.angle == null ? 360 : Number(p.angle),
              angle2: Number(p.angle2) || 0, symmetric: !!p.symmetric };
  if (f.op === 'revolve_face') { s.face_center = p.face_center; s.face_normal = p.face_normal || null; }
  return s;
}
function sync() { g('rvAngle2Row').style.display = dir() === 'two' ? '' : 'none'; }

/* ---------------- the handles: axis line, ring, lathe ghost ---------------- */
/* the select shows the server's list: every axis that works, and u / v greyed
   with the reason when the profile crosses them */
function setAxisOptions(plan) {
  const sel = g('rvAxis');
  sel.innerHTML = '';
  for (const a of plan.axes || []) {
    const o = new Option(a.label, a.name);
    o.disabled = !a.ok;
    if (a.why) o.title = a.why;
    sel.add(o);
  }
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
      t => { setBox('rvAngle', t); setRevolveGhost(t, back()); },   // dragging: the ghost only
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
  const entry = (st.plan.axes || []).find(a => a.name === name);
  st.plan = { ...st.plan, ...alt, axis_name: name, axis_param: entry ? entry.param : name,
              alternatives: rest, fallback: null };
  gizmos.end();
  gizmos.begin(st, st.plan);
}
function beforeApply(st) {                   // typed values obey the server's limit
  if (dir() === 'two') {
    const c2 = Math.max(0, Math.min(angle2(), maxAngle(st) - Math.abs(num('rvAngle'))));
    if (c2 !== num('rvAngle2')) {
      g('rvAngle2').value = c2;
      say(`Second side set to ${c2}° — it is a size the other way, and the two sides ` +
          `together make one full turn.`);
    }
  }
  const a = num('rvAngle'), c = clampAngle(st, a);
  if (c !== a) {
    g('rvAngle').value = c;
    say(dir() === 'sym' ? `Angle limited to ${c}° — half a turn each side is the full turn.`
                        : `Angle limited to ${c}° — one full turn.`);
  }
}
function afterApply(st) { setTaperRingAngle(num('rvAngle')); }
const axisWord = a => typeof a === 'string' ? a : 'the picked edge';

const rv = tool({
  name: 'Revolve', icon: '↻', tool: 'revolve',
  panel: 'revolveDialog', ids: 'rv',
  ops: { profile: 'revolve', face: 'revolve_face' },
  fields: { change: ['Axis', 'Dir'], typed: ['Angle', 'Angle2'] },
  show, params, snapshot, sync, refresh, gizmos, beforeApply, afterApply,
  isEmpty: (pr, st) => Math.abs(pr.angle) + (pr.angle2 || 0) === 0 || !st.plan,   // no plan yet: the plan's arrival applies
  nothing: 'Nothing revolved — the angle was 0. Open Revolve again, then drag the ' +
           'ring or type an angle before OK.',
  split: () => 'the revolved cut leaves material on both sides — revolve the ' +
               'full 360°, or move the profile.',
  describe: p => `${p.angle}°${p.symmetric ? ' each side' : p.angle2 ? ` + ${p.angle2}°` : ''}` +
                 ` about ${axisWord(p.axis)}`,
});

export const openRevolve = profileId => rv.open(profileId);
export function initRevolve() {
  rv.init();
  g('rvFull').onclick = () => {              // a full turn is one thing: one side, 360
    g('rvDir').value = 'one'; sync();
    g('rvAngle').value = 360; rv.apply();
  };
}
