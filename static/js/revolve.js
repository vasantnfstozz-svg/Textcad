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
// the straight edges of the outline — and hands back the list (`axes`, each
// with the label to show and the `param` the feature stores: a name, or a line
// in the sketch plane), the chosen one's ring frame, radius and lathe outline,
// and the same handles for every other axis that works (a swap is a local
// choice between server answers, no request). This file draws what it is told.

import { tool, g, num, say, setBox } from './tool.js';
import { beginAxisLine, endAxisLine,
         beginTaperRing, setTaperRingAngle, endTaperRing,
         beginRevolveGhost, setRevolveGhost, hideRevolveGhost, endRevolveGhost }
  from './viewport.js';

/* the limits are the server's (plan.limits): max_angle = one full turn either
   way (the kernel would quietly wrap 400° to 40°), max_each_side = what a
   symmetric sweep may take each way. That two sides SHARE the turn is the op's
   own rule; the panel restates it only to keep a typed pair inside it. */
const lim = st => (st && st.plan && st.plan.limits) || {};
const maxAngle = st => Number(lim(st).max_angle) || 360;
const maxEach = st => Number(lim(st).max_each_side) || maxAngle(st) / 2;
const isFace = st => !!(st && st.input && st.input.kind === 'face');

/* ONE reading of the Direction row: the mode, the two angles, what sweeps the
   other way (for the ghost) and the ring's ceiling */
function extents(st) {
  const mode = g('rvDir').value, angle = num('rvAngle');
  const angle2 = mode === 'two' ? Math.max(0, num('rvAngle2')) : 0;
  return { mode, angle, angle2, both: mode === 'sym',
           back: mode === 'sym' ? Math.abs(angle) : angle2,
           ceiling: mode === 'sym' ? maxEach(st) : maxAngle(st) };
}
const clampAngle = (st, t) => { const c = extents(st).ceiling; return Math.max(-c, Math.min(c, t)); };
let lastTyped = 'angle';        // two sides: the box the user touched last wins the turn

/* ---------------- the panel <-> params ---------------- */
/* the axis the select names → what the feature stores: the plan's `param` for
   that entry ("u", "v", a world name, or a line in the sketch plane). Until the
   plan has arrived (an edit reopened and a value typed at once) the feature's
   OWN axis stands — never the select's static default. */
function axisParam(st) {
  const name = g('rvAxis').value;
  const e = st && st.plan && (st.plan.axes || []).find(a => a.name === name);
  if (e) return e.param;
  if (st && st.original) return st.original.axis;
  return name || 'v';
}
function params(st) {                          // typed values are clamped in beforeApply, drags by the ring
  const x = extents(st);
  const p = { axis: axisParam(st), angle: x.angle, angle2: x.angle2, both: x.both };
  if (isFace(st)) {
    p.face_center = st.input.center; p.face_normal = st.input.normal;
    p.face_area = st.input.area == null ? null : st.input.area;
  }
  return p;
}
/* the option whose param IS this axis — by name for u / v / a world axis, by
   the same line for an edge; null while the plan has not listed it */
function optionFor(st, axis) {
  const axes = (st && st.plan && st.plan.axes) || [];
  const key = JSON.stringify(axis);
  const e = axes.find(a => a.name === axis || JSON.stringify(a.param) === key);
  if (e) return e.name;
  return typeof axis === 'string' && [...g('rvAxis').options].some(o => o.value === axis) ? axis : null;
}
/* write params into the boxes; {} = the honest default: 0°, one side, nothing
   built yet. The select FOLLOWS the params — a revert to the last good values
   must not leave it on the axis that broke the solid. */
function show(st, p) {
  g('rvDir').value = p.both ? 'sym' : (p.angle2 ? 'two' : 'one');
  g('rvAngle').value = p.angle || 0;
  g('rvAngle2').value = p.angle2 || 0;
  const name = optionFor(st, p.axis);
  if (name) g('rvAxis').value = name;
}
/* the op's defaults ARE the feature's values when a tree names none (a legacy
   revolve with only an angle spins about Z; one without an angle is a full turn)
   — Cancel must push back what the feature meant, not a 0 that fails */
function snapshot(f) {
  const p = f.params || {};
  const s = { axis: p.axis == null ? (f.op === 'revolve_face' ? null : 'Z') : p.axis,
              angle: p.angle == null ? 360 : Number(p.angle),
              angle2: Number(p.angle2) || 0, both: !!p.both };
  if (f.op === 'revolve_face') {
    s.face_center = p.face_center; s.face_normal = p.face_normal || null;
    s.face_area = p.face_area == null ? null : p.face_area;
  }
  return s;
}
function sync() { g('rvAngle2Row').style.display = g('rvDir').value === 'two' ? '' : 'none'; }

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
      t => { lastTyped = 'angle'; setBox('rvAngle', t); setRevolveGhost(t, extents(st).back); },
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
/* typed values obey the server's limits; with two sides, the box the user
   touched last keeps its value and the other one gives way */
function beforeApply(st) {
  const x = extents(st), max = maxAngle(st);
  if (x.mode === 'two' && num('rvAngle2') < 0) {
    g('rvAngle2').value = 0;
    say('The second side is a size, not a direction — it turns the other way from the ' +
        'first; the first angle\'s sign chooses the direction.');
  }
  if (x.mode === 'two' && Math.abs(x.angle) + x.angle2 > max) {
    if (lastTyped === 'angle2') {
      const a = Math.sign(x.angle || 1) * Math.max(0, max - x.angle2);
      g('rvAngle').value = a;
      say(`Angle set to ${a}° — the two sides together make one full turn.`);
    } else {
      const a2 = Math.max(0, max - Math.abs(x.angle));
      g('rvAngle2').value = a2;
      say(`Second side set to ${a2}° — the two sides together make one full turn.`);
    }
  }
  const a = num('rvAngle'), c = clampAngle(st, a);
  if (c !== a) {
    g('rvAngle').value = c;
    say(x.mode === 'sym' ? `Angle limited to ${c}° — half a turn each side is the full turn.`
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
  describe: p => `${p.angle}°${p.both ? ' each side' : p.angle2 ? ` + ${p.angle2}°` : ''}` +
                 ` about ${axisWord(p.axis)}`,
});

export const openRevolve = profileId => rv.open(profileId);
export function initRevolve() {
  rv.init();
  g('rvAngle').addEventListener('input', () => { lastTyped = 'angle'; });
  g('rvAngle2').addEventListener('input', () => { lastTyped = 'angle2'; });
  g('rvFull').onclick = () => {              // a full turn is one thing: one side, 360
    g('rvDir').value = 'one'; sync();
    g('rvAngle').value = 360; lastTyped = 'angle'; rv.apply();
  };
}
