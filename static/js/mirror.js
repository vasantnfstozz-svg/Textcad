// mirror.js — Mirror on the tool framework (tool.js) — LAUNCH-PLAN.md P4,
// specs/mirror.md. One declaring function on the op that already existed
// (`mirror`), which now mirrors a FEATURE (its delta reflected across a plane
// and applied again) or a BODY (fused with its reflection). The seed is a tree
// row or the maker of the face you clicked — the server works out what that
// means and which body the result goes on, exactly as for Pattern. This file
// says only what makes a mirror different: its panel, the plane box, and the
// gold quad that marks the plane. Selection, the modal lock, the lazy verified
// preview, edit-in-isolation, Cancel/OK, Esc and the failure sentences are
// inherited.
//
// There is nothing to drag: the plane is CHOSEN — a click on a flat face or on
// one of the three origin quads while the panel is open (the framework's
// session pick with `planePick`; `onRepick` says the click means the PLANE),
// or a choice in the Plane box. EVERY geometric fact is the plan's (R1): the
// plane in its ONE stored form, the words for it, the alternatives, the quad's
// frame and size. No ghost: the real mirror image appears after one verified
// rebuild, like Pattern's copies.

import { tool, g } from './tool.js';
import { beginPlaneQuad, endPlaneQuad } from './viewport.js';

/* the stored forms the plan chose (seed, plane, join); before the plan lands
   (OK pressed straight after an edit opened) the feature's OWN stand in */
const stored = st => (st && st.plan && st.plan.params) || (st && st.original) || {};

function mirrorTool() {
  const ctl = tool({
    name: 'Mirror', icon: '⇋', tool: 'mirror', verb: 'mirrors',
    sketchNote: 'sketch mirrors come with the sketch tools',
    panel: 'mrDialog', ids: 'mr',
    ops: { feature: 'mirror', face: 'mirror' },
    eats: true,                   // the op returns the body WITH its mirror image: no Join / Cut row
    // no `anyFace`: it flags the RE-PICK, and a mirror plane must be FLAT
    planePick: true,              // the session pick shows the origin quads too
    repick: 'Click a flat face or an origin plane for the mirror plane · Esc cancels',
    onRepick(st, data, replan) {
      replan({ plane_pick: data.world ? { world: data.world }
                                      : { center: data.center, normal: data.normal || null,
                                          area: data.area ?? null } });
    },
    fields: {},
    /* once this session HAS built its mirror, every replan is about that
       feature (Pattern's rule): its stored seed / plane, its own body */
    planExtra: st => (st.featureId ? { own_id: st.featureId } : {}),
    /* `join` comes from the plan or the feature's own snapshot, never from a
       default invented here (R1): `?? true` meant that any state without one
       asked for a whole-body Join, the P0 the server side of this fix closes */
    params: st => ({ seed: stored(st).seed ?? null, plane: stored(st).plane ?? null,
                     join: !!stored(st).join }),
    show() {},                    // nothing is typed: the plane box is the plan's
    snapshot(f) {
      const p = f.params || {};
      return { seed: p.seed ?? null, plane: p.plane ?? null, join: !!p.join };
    },
    isEmpty: pr => !pr.plane,     // honest zero: no plane, nothing built
    nothing: 'Nothing mirrored — no plane was chosen. Open Mirror again and click a flat face ' +
             'or an origin plane before OK.',
    /* the words are the plan's that built those values (tool.js lastGoodPlan),
       never re-derived here from the stored form (R1) */
    describe: (p, st) => `the mirror across ${(st && st.lastGoodPlan && st.lastGoodPlan.plane_words)
                                              || 'the plane that last built'}`,
    split: () => 'the mirror image does not touch the body — pick a plane on the body (a face ' +
                 'or its mid-plane) for one part.',
    /* the kernel refused the new plane and the feature is back on the last one
       that built: plan again so the box and the quad show THAT plane */
    refresh(st) { if (st && st.featureId) ctl.replan(); },
    gizmos: {
      begin(st, plan) {
        const sel = g('mrPlane');
        // the blank is the NO-PLANE state ONLY: once a plane is in force the plan's
        // plane_name is one of the alternatives, so no blank is left to fall back to
        const blank = '<option value="">— click a flat face or an origin plane —</option>';
        sel.innerHTML = (plan.plane_name ? '' : blank) +
          plan.alternatives.map(a => `<option value="${a.name}">${a.label}</option>`).join('');
        sel.value = plan.plane_name || '';
        if (plan.frame) beginPlaneQuad(plan.frame, plan.half);
      },
      end() { endPlaneQuad(); },
    },
  });
  // a choice in the box: the plane comes back from the plan (never made here)
  g('mrPlane').onchange = () => { if (g('mrPlane').value) ctl.replan({ plane: g('mrPlane').value }); };
  return ctl;
}

let mr = null;
export function initMirror() { mr = mirrorTool(); mr.init(); }
export const openMirror = () => mr.open();
