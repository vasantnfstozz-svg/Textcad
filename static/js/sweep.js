// sweep.js — Fusion-style Sweep ON the tool framework (tool.js), the first
// Tier 2 tool (LAUNCH-PLAN.md §4, specs/sweep.md). This file declares only
// what makes Sweep different: its panel, its ops (sweep for a sketch profile,
// sweep_face for a picked flat face), its SECOND input — the PATH sketch, a
// reference the feature stores as `path` — and its handles: the gold path
// line, the distance arrow riding the path and the tube ghost. Selection, the
// modal lock, the lazy verified preview, Join/Cut, edit-in-isolation,
// Cancel/OK and the failure sentences are inherited.
//
// EVERYTHING GEOMETRIC IS THE PLAN'S (R1): the server measures the profile
// against the path exactly as the op will (sketch.sweep_geometry — one
// verdict), lists the path sketches to offer, and hands back the path as it
// will be swept, sampled into `stations` {s, p, t, x, y} — arc length, point,
// tangent and the profile frame carried there. The arrow sits on the station
// nearest the distance in the box and points along its tangent; the ghost is
// the profile's loops skinned along those stations. This file computes no
// geometry beyond placing a handle on a point it was given.

import { tool, g, num, mm, len, say, setLen } from './tool.js';
import { beginPathLine, endPathLine,
         beginExtrudeArrow, endExtrudeArrow, extrudeArrowDragging,
         beginSweepGhost, setSweepGhost, hideSweepGhost, endSweepGhost }
  from './viewport.js';

const lim = st => (st && st.plan && st.plan.limits) || {};
const pathLength = st => Number(lim(st).length) || 0;
const isFace = st => !!(st && st.input && st.input.kind === 'face');
/* the station nearest an arc length — a lookup in the plan's list, no maths */
function stationNear(st, d) {
  const S = (st.plan && st.plan.stations) || [];
  let best = S[0];
  for (const s of S) if (Math.abs(s.s - d) < Math.abs(best.s - d)) best = s;
  return best;
}
/* the distance the boxes mean: the whole path, or the mm in the box */
const distanceOf = st => g('swFull').checked ? pathLength(st) : mm('swDist');

/* ---------------- the panel <-> params ---------------- */
function params(st) {
  const full = g('swFull').checked;
  const p = { path: g('swPath').value || (st && st.plan && st.plan.path_id) || null,
              distance: full ? 0 : mm('swDist'), full };
  if (isFace(st)) {
    p.face_center = st.input.center; p.face_normal = st.input.normal;
    p.face_area = st.input.area == null ? null : st.input.area;
  }
  return p;
}
/* write params into the boxes; {} = the honest default: 0 mm, nothing built.
   The Path select FOLLOWS the params once the plan has listed it. */
function show(st, p) {
  g('swFull').checked = !!p.full;
  setLen('swDist', p.full ? pathLength(st) : (Number(p.distance) || 0));
  if (p.path && [...g('swPath').options].some(o => o.value === p.path)) g('swPath').value = p.path;
  sync(st);
}
function snapshot(f) {
  const p = f.params || {};
  const s = { path: p.path || null, distance: Number(p.distance) || 0, full: !!p.full };
  if (f.op === 'sweep_face') {
    s.face_center = p.face_center; s.face_normal = p.face_normal || null;
    s.face_area = p.face_area == null ? null : p.face_area;
  }
  return s;
}
/* Whole path: the box shows the path's length and is not typed into */
function sync(st) {
  const full = g('swFull').checked;
  g('swDist').disabled = full;
  if (full && st && st.plan) setLen('swDist', pathLength(st));
}

/* ---------------- the handles: path line, arrow, tube ghost ---------------- */
function setPathOptions(plan) {
  const sel = g('swPath');
  sel.innerHTML = '';
  for (const p of plan.paths || []) sel.add(new Option(p.label, p.id));
  sel.value = plan.path_id;
}
/* the arrow: on the station at the current distance, pointing along the
   path's tangent there. makeArrow rides its base to O + N·amount, so the base
   is set back by the distance along the local tangent — while the drag lasts
   the handle slides along that tangent (a good local guide); on release it is
   put back onto the path exactly. */
function placeArrow(st) {
  if (!st || !st.plan || extrudeArrowDragging()) return;
  const d = Math.min(distanceOf(st), pathLength(st));
  const s = stationNear(st, d);
  if (!s) return;
  const O = [s.p[0] - s.t[0] * d, s.p[1] - s.t[1] * d, s.p[2] - s.t[2] * d];
  beginExtrudeArrow(O, s.t, d,
    v => { setLen('swDist', v, 1); g('swFull').checked = v >= pathLength(st) - 0.01; sync(st); setSweepGhost(v); },
    async v => {                                       // release: ONE verified rebuild
      setLen('swDist', v, 1);
      g('swFull').checked = v >= pathLength(st) - 0.01;
      sync(st);
      await sw.apply();
      hideSweepGhost();                                // the real solid replaces the ghost
      placeArrow(st);                                  // back onto the path
    },
    v => Math.max(0, Math.min(pathLength(st), v)));
}
const gizmos = {
  begin(st, plan) {
    setPathOptions(plan);
    if (plan.fallback && !st.saidFallback) {          // rule 7: the stored path is not usable
      st.saidFallback = true;
      say(`⚠ This sweep's path '${plan.fallback.from}' cannot be used: ${plan.fallback.why}. ` +
        `The tool opened on '${plan.path_id}' — OK saves that, Cancel keeps the old one.`);
    }
    for (const n of plan.notes || []) if (!(st.saidNotes ||= new Set()).has(n)) {
      st.saidNotes.add(n); say(`Sweep: ${n}.`);
    }
    beginPathLine(plan.path);
    beginSweepGhost(plan.loops, plan.stations);
    if (g('swFull').checked) sync(st);
    placeArrow(st);
  },
  end() { endPathLine(); endExtrudeArrow(); endSweepGhost(); },
};
/* the user chose another path in the select: a new plan for it */
function refresh(st) {
  if (!st || !st.plan || g('swPath').value === st.plan.path_id) { placeArrow(st); return; }
  sw.replan();
}
/* a tree row clicked while the panel is open: a path sketch's row chooses it */
function onRow(st, fid, replan) {
  const opt = [...g('swPath').options].find(o => o.value === fid);
  if (!opt) {
    if (fid !== st.input.id && fid !== st.featureId)
      say(`⚠ '${fid}' is not a path sketch — Sweep follows a sketch drawn with the Path tool ` +
        '(open lines). The Path list holds every one in this design.');
    return;
  }
  if (fid === g('swPath').value) return;
  g('swPath').value = fid;
  replan();
}
/* typed values obey the path: a distance past its end is the whole path */
function beforeApply(st) {
  const L = pathLength(st), d = mm('swDist');
  if (!g('swFull').checked && L && d > L) {
    g('swFull').checked = true; sync(st);
    say(`Distance ${len(d)} is longer than the path (${len(L)}) — swept along the whole path.`);
  }
  if (d < 0) { setLen('swDist', 0); say('A sweep distance is a length along the path — 0 or more.'); }
}
function afterApply(st) { placeArrow(st); }

const sw = tool({
  name: 'Sweep', icon: '〜', tool: 'sweep',
  panel: 'sweepDialog', ids: 'sw',
  ops: { profile: 'sweep', face: 'sweep_face' },
  fields: { change: ['Path', 'Full'], typed: ['Dist'] },
  show, params, snapshot, sync, refresh, gizmos, beforeApply, afterApply, onRow,
  planExtra: () => ({ path_id: g('swPath').value || null }),
  isEmpty: pr => !pr.full && !(pr.distance > 0),
  nothing: 'Nothing swept — the distance was 0. Open Sweep again, then drag the arrow ' +
           'or type a distance (or tick Whole path) before OK.',
  split: () => 'the swept cut leaves material on both sides — sweep the whole path, ' +
               'or move the path.',
  describe: p => `${p.full ? 'the whole path' : len(p.distance)} along ${p.path || 'the path'}`,
});

export const openSweep = profileId => sw.open(profileId);
export function initSweep() {
  sw.init();
  g('swDist').addEventListener('input', () => { if (num('swDist') > 0) g('swFull').checked = false; });
}
