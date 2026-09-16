// pattern.js — Circular and Rectangular Pattern on the tool framework
// (tool.js) — LAUNCH-PLAN.md P4, specs/pattern.md. One declaring function
// each, on the ops that already existed (`polar_pattern`, `linear_pattern`),
// which now repeat a FEATURE: the seed is a tree row or the maker of the face
// you clicked, the server works out what that means (a hole's wall is the
// hole, a plate's own top is the body) and which body the result goes on.
// This file says only what makes a pattern different: its panel, boxes <->
// params, and its handles — Circular's ring (the total angle) on the plan's
// frame, Rectangular's two arrows (the distances) along the plan's directions.
// Selection, the modal lock, the lazy verified preview, edit-in-isolation,
// Cancel/OK, Esc and the failure sentences are inherited.
//
// EVERY geometric fact is the plan's (R1): the seed's centre, the axis in its
// ONE stored form and the words for it, the ring's frame and radius, the axis
// line, the arrows' directions and the swap alternatives. A click on a face
// while Circular is open means "this face's axis" (the framework's `onRepick`).
// There is no ghost: the copies are drawn only by the kernel — the value box
// follows the drag live and the real pattern appears on release.

import { tool, g, num, setBox } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginSecondArrow, endSecondArrow, setSecondArrowAmount,
         beginAxisLine, endAxisLine,
         beginTaperRing, setTaperRingAngle, endTaperRing } from './viewport.js';

const FULL = 360;
const count = id => Math.max(1, Math.round(num(id)) || 1);
/* the stored forms the plan chose (seed, axis / directions); before the plan
   lands (OK pressed straight after an edit opened) the feature's OWN stand in,
   so a rebuild is never asked for a pattern of nothing */
const stored = st => (st && st.plan && st.plan.params) || (st && st.original) || {};

/* ----------------------------------- Circular: a ring for the angle ----------------------------------- */
function circular() {
  const clampAngle = t => Math.max(1, Math.min(FULL, Math.round(Math.abs(t) * 10) / 10));
  const ctl = tool({
    name: 'Circular Pattern', icon: '✳', tool: 'polar_pattern',
    panel: 'cpDialog', ids: 'cp',
    ops: { feature: 'polar_pattern', face: 'polar_pattern' },
    eats: true,                   // the op returns the body WITH the copies: no Join / Cut row
    anyFace: true,                // a bore's wall is a seed (its hole) and an axis
    repick: 'Click a bore or a flat face of the body for the axis · type the count · Esc cancels',
    onRepick(st, data, replan) {
      replan({ axis_pick: { center: data.center, normal: data.normal || null,
                            area: data.area ?? null } });
    },
    fields: { typed: ['Count', 'Angle'] },
    /* once this session HAS built its pattern, every replan is about that
       feature: without it the server walks the tree down from the seed and
       lands on the pattern's own output, re-aiming the axis at the already-
       patterned solid (P4 code review) */
    planExtra: st => (st.featureId ? { own_id: st.featureId } : {}),
    params: st => ({ seed: stored(st).seed ?? null, axis: stored(st).axis ?? null,
                     count: count('cpCount'), angle: num('cpAngle') || FULL }),
    show(st, p) {
      g('cpCount').value = p.count || 1;            // the honest zero: only the seed, nothing built
      g('cpAngle').value = p.angle == null ? FULL : p.angle;
    },
    snapshot(f) {
      const p = f.params || {};
      return { seed: p.seed ?? null, axis: p.axis ?? null, count: Number(p.count) || 1,
               angle: p.angle == null ? FULL : Number(p.angle) };
    },
    isEmpty: (pr, st) => !st.plan || !(pr.count > 1),
    nothing: 'Nothing patterned — the count was 1. Open Circular Pattern again and type how ' +
             'many copies before OK.',
    describe: p => `${p.count} copies over ${p.angle}°`,
    split: () => 'separate copies are what a body pattern makes — pattern a feature of the ' +
                 'body instead if you wanted one part.',
    gizmos: {
      begin(st, plan) {
        g('cpAxis').value = plan.axis_words;
        beginAxisLine(plan.origin, plan.axis_dir, plan.axis_half);
        beginTaperRing(plan.origin, plan.frame, plan.radius, num('cpAngle'),
          t => setBox('cpAngle', t),                              // dragging: the box follows
          async t => { setBox('cpAngle', t); await ctl.apply(); },   // release: ONE verified rebuild
          clampAngle);
        if (!st.featureId && num('cpCount') > 1) ctl.apply();    // a count typed before the plan arrived
      },
      end() { endAxisLine(); endTaperRing(); },
    },
    afterApply() { setTaperRingAngle(num('cpAngle')); },
  });
  return ctl;
}

/* ------------------------------- Rectangular: an arrow per direction ------------------------------- */
function rectangular() {
  const ctl = tool({
    name: 'Rectangular Pattern', icon: '⋯', tool: 'linear_pattern',
    panel: 'rpDialog', ids: 'rp',
    ops: { feature: 'linear_pattern', face: 'linear_pattern' },
    eats: true, anyFace: true,
    fields: { change: ['DistType'], typed: ['Count', 'Dist', 'Count2', 'Dist2'] },
    /* the directions are the plan's; `along` says which alternative leads, and
       `own_id` keeps a replan on the feature this session built (see Circular) */
    planExtra: st => ({ ...(st.plan ? { along: g('rpAlong').value } : {}),
                        ...(st.featureId ? { own_id: st.featureId } : {}) }),
    params: st => ({ seed: stored(st).seed ?? null,
                     direction: stored(st).direction ?? null, direction2: stored(st).direction2 ?? null,
                     count: count('rpCount'), distance: num('rpDist'),
                     distance_type: g('rpDistType').value,
                     count2: count('rpCount2'), distance2: num('rpDist2') }),
    show(st, p) {
      g('rpCount').value = p.count || 2;            // the smallest pattern: the seed and one copy
      g('rpDist').value = p.distance || 0;          // 0: the copy sits on the seed — nothing built
      g('rpDistType').value = p.distance_type || 'spacing';
      g('rpCount2').value = p.count2 || 1;
      g('rpDist2').value = p.distance2 || 0;
    },
    snapshot(f) {
      const p = f.params || {};
      return { seed: p.seed ?? null, direction: p.direction ?? null, direction2: p.direction2 ?? null,
               count: Number(p.count) || 2, distance: Number(p.distance) || 0,
               distance_type: p.distance_type || 'spacing',
               count2: Number(p.count2) || 1, distance2: Number(p.distance2) || 0 };
    },
    /* honest zero: nothing is built until ONE of the two rows has both a count
       above 1 and a distance — Direction 2 alone is a pattern too (it used to be
       refused silently, and OK then blamed "the distance", P4 review) */
    isEmpty: (pr, st) => !st.plan
      || !((pr.count > 1 && pr.distance) || (pr.count2 > 1 && pr.distance2)),
    /* half-made: a second row asked for without its distance, or the distance
       taken away — the op would refuse and the revert would undo the choice */
    hold(pr) {
      if (pr.count > 1 && !pr.distance)
        return 'The pattern is unchanged until it has a distance — drag the arrow or type one.';
      if (pr.count2 > 1 && !pr.distance2)
        return 'Direction 2: drag the second arrow or type its distance (or set Count 2 back to 1).';
      return null;
    },
    nothing: 'Nothing patterned — no direction had both a count above 1 and a distance. Open ' +
             'Rectangular Pattern again, then drag an arrow or type a distance before OK.',
    describe: p => `${p.count} × ${p.count2} copies, ${p.distance} / ${p.distance2} mm`,
    split: () => 'separate copies are what a body pattern makes — pattern a feature of the ' +
                 'body instead if you wanted one part.',
    gizmos: {
      begin(st, plan) {
        const sel = g('rpAlong');
        sel.innerHTML = plan.alternatives.map(a => `<option value="${a.name}">${a.label}</option>`).join('');
        sel.value = plan.along;
        // a LEGACY pattern (a per-copy dx / dy / dz step, no stored direction):
        // the plan read that step as a direction AND a distance — show the
        // distance, or the first one typed here would re-aim the pattern (R1:
        // the number is the server's, never derived from the step in JS)
        if (plan.params && plan.params.distance != null && !st.legacyShown) {
          st.legacyShown = true;
          g('rpDist').value = plan.params.distance;
        }
        beginExtrudeArrow(plan.centre, plan.direction, num('rpDist'),
          v => setBox('rpDist', v),
          async v => { setBox('rpDist', v); await ctl.apply(); });
        beginSecondArrow(plan.centre, plan.direction2, num('rpDist2'),
          v => setBox('rpDist2', v),
          async v => {                                  // Fusion: a distance wakes Direction 2
            setBox('rpDist2', v);
            if (num('rpCount2') < 2 && Math.abs(v) > 1e-9) setBox('rpCount2', 2, 0);
            await ctl.apply();
          });
        if (!st.featureId && num('rpDist') && num('rpCount') > 1) ctl.apply();
      },
      end() { endExtrudeArrow(); endSecondArrow(); },
    },
    afterApply() { setExtrudeArrowAmount(num('rpDist')); setSecondArrowAmount(num('rpDist2')); },
  });
  g('rpAlong').onchange = () => ctl.replan();      // the directions come back from the plan
  return ctl;
}

let cp = null, rp = null;
export function initPattern() {
  cp = circular(); rp = rectangular();
  cp.init(); rp.init();
}
export const openCircularPattern = () => cp.open();
export const openRectangularPattern = () => rp.open();
