// move.js — Move and Rotate on the tool framework (tool.js) — LAUNCH-PLAN.md P4,
// specs/move-rotate.md. TWO tools from one file, as fillet.js declares Fillet
// and Chamfer: Move drags a BODY along X / Y / Z with three arrows, Rotate
// turns it about X / Y / Z through its own centre with one ring. Both ops EAT
// their body (the result is the body in its new place): no Join / Cut row.
// This file says only what makes them different: the panels, boxes <-> params
// and the handles. Selection, the modal lock, the verified preview,
// edit-in-isolation, Cancel/OK, Esc and the failure sentences are inherited.
//
// EVERY geometric fact is the plan's (R1): the body's centre, the world axes,
// the ring's right-handed frame, its radius, the axis line, the pivot in its
// stored form. The browser adds the boxes' own values along the plan's axes to
// place the arrows — nothing else. The GHOST is the body itself: its mesh,
// translucent, offset or turned by the change since the last build while a
// handle is dragged; the real body follows on release.

import { tool, g, num, mm, len, setBox, setLen } from './tool.js';
import { beginArrows, endArrows, arrowsDragging, beginTaperRing, endTaperRing,
         setTaperRingAngle, beginAxisLine, endAxisLine,
         beginMoveGhost, setMoveGhost, endMoveGhost } from './viewport.js';

const XYZ = ['x', 'y', 'z'];
const ARROW_COLOURS = { x: 0xe5484d, y: 0x46a758, z: 0x3e8bff };   // Fusion's X / Y / Z
/* the bodies the ghost may be cloned from: this session's result once built, the input before */
const ghostOf = st => [st.featureId, st.input.body].filter(Boolean);
/* Σ v[k]·axis_k along the plan's axes — the offset the arrows meet at (added to
   the centre) and the ghost's shift */
const along = (axes, v) =>
  [0, 1, 2].map(i => XYZ.reduce((s, k) => s + (v[k] || 0) * axes[k][i], 0));

/* ---------------- Move: three arrows meeting at the moved centre ---------------- */
const mvBox = k => 'mv' + k.toUpperCase();
// an offset is a LENGTH: typed in the display unit, sent (and planned) in mm
const mvParams = () => ({ x: mm('mvX'), y: mm('mvY'), z: mm('mvZ') });

function placeArrows(st, plan) {
  endArrows();
  const p = mvParams();
  const off = along(plan.axes, p);
  const met = plan.origin.map((c, i) => c + off[i]);       // centre + the offset
  beginArrows(XYZ.map(k => ({
    // base = origin + axis·amount must be the meeting point: this arrow rides its own offset
    origin: met.map((c, i) => c - plan.axes[k][i] * p[k]),
    axis: plan.axes[k], amount: p[k], color: ARROW_COLOURS[k],
    onChange: v => { setLen(mvBox(k), v, 1); ghostMove(st, plan); },
    onCommit: async v => { setLen(mvBox(k), v, 1); endMoveGhost(); await mv.apply(); },
  })));
}
function ghostMove(st, plan) {
  beginMoveGhost(ghostOf(st));
  const p = mvParams(), s = st.shown || {};
  const d = along(plan.axes, { x: p.x - (s.x || 0), y: p.y - (s.y || 0), z: p.z - (s.z || 0) });
  setMoveGhost({ dx: d[0], dy: d[1], dz: d[2] });
}

const mv = tool({
  name: 'Move', icon: '↗', tool: 'move',
  panel: 'mvDialog', ids: 'mv',
  ops: { face: 'move' },        // a body, named by any face of it
  eats: true,                   // the op returns the body in its new place: no Join / Cut row
  bodyRow: true,                // a body's tree row opens the tool on it
  anyFace: true,                // a curved face names its body just as well
  fields: { typed: ['X', 'Y', 'Z'] },
  /* a replan after the first OK is about the feature THIS session built, not a
     second move of the same body (the plan refuses that) — as Mirror and the
     Patterns already say */
  planExtra: st => (st.featureId ? { own_id: st.featureId } : {}),
  show(st, p) { for (const k of XYZ) setLen(mvBox(k), p[k] || 0); },
  params: mvParams,
  snapshot(f) {
    const p = f.params || {};
    return { x: Number(p.x) || 0, y: Number(p.y) || 0, z: Number(p.z) || 0 };
  },
  isEmpty: pr => !(pr.x || pr.y || pr.z),      // honest zero: 0 / 0 / 0 moves nothing
  gizmos: {
    begin(st, plan) {
      // what the visible body HAS: the boxes at open (an edit's stored offsets,
      // a new session's zeros) — the ghost's delta is measured from here
      if (!st.shown) st.shown = mvParams();
      placeArrows(st, plan);
    },
    end() { endArrows(); endMoveGhost(); },
  },
  /* the body is where the boxes say now: the triad rides with it */
  afterApply(st) {
    st.shown = mvParams();
    if (st.plan && !arrowsDragging()) placeArrows(st, st.plan);
  },
  nothing: 'Nothing moved — the offsets were 0. Open Move again, then drag an arrow or ' +
           'type an offset before OK.',
  describe: p => `an offset of ${len(p.x)}, ${len(p.y)}, ${len(p.z)}`,
});

/* ---------------- Rotate: one ring about the chosen axis, through the centre -------- */
/* the pivot in its STORED form is the plan's (an edit of a legacy rotate turns
   about the world origin and must go on doing so); before the plan lands the
   feature's own stands in; a new rotate is about the centre */
const stored = st => (st && st.plan) || (st && st.original) || null;
const rtParams = st => ({ axis: g('rtAxis').value, angle_deg: num('rtAngle'),
                          pivot: stored(st) ? (stored(st).pivot ?? null) : 'center' });
const rtShow = (st, p) => { g('rtAxis').value = p.axis || 'Z'; g('rtAngle').value = p.angle_deg || 0; };

function ghostTurn(st, plan) {
  beginMoveGhost(ghostOf(st));
  setMoveGhost({ origin: plan.origin, dir: plan.axis_dir,
                 deg: num('rtAngle') - ((st.shown && st.shown.angle_deg) || 0) });
}

const rt = tool({
  name: 'Rotate', icon: '⟳', tool: 'rotate',
  panel: 'rtDialog', ids: 'rt',
  ops: { face: 'rotate' },
  eats: true, bodyRow: true, anyFace: true,
  fields: { change: ['Axis'], typed: ['Angle'] },
  planExtra: st => ({ axis: g('rtAxis').value,      // the ring is planned about the box's axis
                      ...(st && st.featureId ? { own_id: st.featureId } : {}) }),
  show: rtShow,
  params: rtParams,
  snapshot(f) {
    // VERBATIM: Cancel pushes this back, so a legacy rotate that has no `pivot`
    // must not GAIN one (`pivot: null` builds the same body, but the design
    // went dirty from merely opening and cancelling the panel — the user's one
    // saved rotate, planetary-assembly). rtParams reads the pivot from the
    // plan first, so nothing needs it spelled out here.
    const p = f.params || {};
    const s = { axis: p.axis || 'Z', angle_deg: Number(p.angle_deg) || 0 };
    if (p.pivot !== undefined) s.pivot = p.pivot;
    return s;
  },
  isEmpty: pr => !pr.angle_deg,                // honest zero: 0° turns nothing
  gizmos: {
    begin(st, plan) {
      if (!st.shown) {                             // the FIRST plan of this session
        // What a feature that spells NOTHING out actually does is the server's
        // to say (R1): plan.params carries the op's own defaults — blocks.rotate
        // turns 90° about Z through the world origin. The panel read the
        // feature's params raw, so a rotate stored as {} opened at 0° on a body
        // standing turned (measured): the ring and the drag ghost both started
        // 90° behind the body, and the only thing that saved the solid was the
        // honest-zero gate refusing to write a 0. Round one put the defaults in
        // plan_rotate's `params` — but nothing in this file read that field.
        // The boxes and what Cancel puts back read the one answer now.
        if (st.editing && plan.params && plan.params.angle_deg != null) {
          const eff = { ...plan.params };
          if (!(st.original && 'pivot' in st.original)) delete eff.pivot;   // no pivot GAINED
          rtShow(st, eff);
          st.original = eff; st.lastGood = eff;
        }
        st.shown = rtParams(st);                   // the angle the visible body already has
      }
      beginAxisLine(plan.origin, plan.axis_dir, plan.axis_half);
      beginTaperRing(plan.origin, plan.frame, plan.radius, num('rtAngle'),
        v => { setBox('rtAngle', v); ghostTurn(st, plan); },
        async v => { setBox('rtAngle', v); endMoveGhost(); await rt.apply(); });
    },
    end() { endAxisLine(); endTaperRing(); endMoveGhost(); },
  },
  /* Axis changed: the ring's frame is the plan's, so ask again */
  refresh: st => { if (st && st.plan) rt.replan(); },
  afterApply(st) { st.shown = rtParams(st); setTaperRingAngle(num('rtAngle')); },
  nothing: 'Nothing rotated — the angle was 0. Open Rotate again, then drag the ring or ' +
           'type an angle before OK.',
  describe: p => `${p.angle_deg}° about ${p.axis}`,
});

export const openMove = () => mv.open();
export const openRotate = () => rt.open();
export function initMove() { mv.init(); rt.init(); }
