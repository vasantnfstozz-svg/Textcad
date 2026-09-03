// extrude.js — Fusion-style Extrude ON the tool framework (tool.js, LAUNCH-PLAN
// R2). This file declares only what makes Extrude different: its panel, its
// two ops (extrude for a sketch profile, extrude_face for a picked face), how
// its boxes become params, and its three handles — the drag arrow, the ghost
// and the taper ring. Selection, the modal lock, the lazy verified preview,
// Join/Cut, edit-in-isolation, Cancel/OK and every failure sentence are
// inherited from the framework, not typed here.
//
// GEOMETRY COMES FROM THE SERVER (R1, P1): the axis a positive distance moves
// material, the arrow's origin, the ghost's frame and outline, the taper
// limits, the default target and which sign goes INTO the body all arrive in
// ONE plan (toolplan.py). This file draws what it is told and computes nothing.

import { tool, g, num, say } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         extrudeArrowDragging,
         beginExtrudeGhost, setExtrudeGhost, hideExtrudeGhost, endExtrudeGhost,
         beginTaperRing, setTaperRingAngle, endTaperRing } from './viewport.js';

const isFace = st => st.input.kind === 'face';

/* which SIGN of the distance goes INTO the material — from the plan (a face
   sketch on a bottom / -x / +y face has the canonical frame pointing into the
   body, so there the pocket direction is POSITIVE); null for a plane sketch */
const intoSign = st => (st.plan && st.plan.into_sign) || null;
/* the taper constants and meeting depths are the SERVER's (plan.limits) */
const lim = st => (st.plan && st.plan.limits) || {};
const maxTaper = st => Number(lim(st).max_taper) || 89;

/* ---------------- the panel <-> params ---------------- */
function params(st) {
  const d = num('exDist'), taper = num('exTaper');
  const flip = g('exFlip').checked, through = g('exThrough').checked;
  if (isFace(st))
    return { face_center: st.input.center, face_normal: st.input.normal,
             amount: d, taper, flip };
  const dir = g('exDir').value;
  if (dir === 'sym') return { amount: d, both: true, amount2: 0, taper, flip: false, through };
  if (dir === 'two') return { amount: d, both: false, amount2: num('exDist2'), taper, flip, through };
  let amt = d;
  if (through && amt === 0 && intoSign(st)) {
    // THROUGH ALL with the untouched 0 distance: only the SIGN matters (the
    // cut runs 2 m that way) — default INTO the body for a face sketch.
    // Dragging the arrow first still wins: any nonzero value keeps its sign.
    amt = intoSign(st);
  }
  return { amount: amt, both: false, amount2: 0, taper, flip, through };
}
/* write params into the boxes; {} = the honest defaults: the distance starts
   at 0 because nothing has been extruded yet (user 2026-09-01) */
function show(st, p) {
  g('exDir').value = p.both ? 'sym' : (p.amount2 ? 'two' : 'one');
  g('exDir').disabled = isFace(st);        // a face extrude is one-directional (drag ± instead)
  g('exDist').value = p.amount || 0;
  g('exDist2').value = p.amount2 || 10;
  g('exTaper').value = p.taper || 0;
  g('exFlip').checked = !!p.flip;
  g('exThrough').checked = !!p.through;
}
/* a normalized copy of EVERY param this tool can write, so Cancel-in-edit
   pushes it back verbatim and keys the session added are reset too */
function snapshot(f) {
  const p = f.params || {};
  return f.op === 'extrude_face'
    ? { face_center: p.face_center, face_normal: p.face_normal || null,
        amount: Number(p.amount) || 0, taper: Number(p.taper) || 0, flip: !!p.flip }
    : { amount: Number(p.amount) || 0, both: !!p.both, amount2: Number(p.amount2) || 0,
        taper: Number(p.taper) || 0, flip: !!p.flip, through: !!p.through };
}
function sync(st) {
  g('exDist2Row').style.display = g('exDir').value === 'two' ? '' : 'none';
  // THROUGH ALL is a cut idea: a boss running 2 m past the part is useless,
  // but a cut that stops inside the material slices the part
  const isCut = g('exOp').value === 'cut';
  g('exThroughRow').style.display = isCut ? '' : 'none';
  if (!isCut) g('exThrough').checked = false;
  const thru = g('exThrough').checked;
  g('exDist').disabled = thru;
  g('exDist').title = thru ? 'not used — the cut runs all the way through' : '';
  if (st && !isCut) st.cutFlipped = false;   // leaving Cut re-arms the one-shot flip
}

/* ---------------- the handles: arrow, ghost, taper ring ----------------
   ONE axis for all three, from the plan; Flip is folded into st.axis so
   ticking it moves the arrow instead of silently negating at apply time. */
const flipOn = () => g('exFlip').checked && g('exDir').value !== 'sym';
function setAxis(st, base) {
  const s = flipOn() ? -1 : 1;
  st.axis = [base[0] * s, base[1] * s, base[2] * s];
  st.ghostSign = s;                        // the ghost's frame z IS the axis
}
function refresh(st) {                     // Flip / direction changed
  if (!st || !st.plan) return;
  setAxis(st, st.plan.axis);
  placeArrow(st);
}
function placeArrow(st) {
  if (!st.axis) setAxis(st, st.plan.axis);
  // the plan can land mid-drag (setup is async): rebuilding the arrow then
  // would kill the drag and leave orbit switched off
  if (extrudeArrowDragging()) return;
  beginExtrudeArrow(st.plan.origin, st.axis, num('exDist'),
    amount => {                          // dragging: the instant ghost only
      g('exDist').value = Math.round(amount * 100) / 100;
      showGhost(st, amount, num('exTaper'));
    },
    async amount => {                    // release: ONE real verified rebuild
      g('exDist').value = Math.round(amount * 100) / 100;
      await ex.apply();
      hideExtrudeGhost();                // the real solid replaces the ghost
    });
}
/* per outline, the height where ITS walls meet for a narrowing taper (the
   server's collapse depths, same order as the plan's loops); null while unknown */
function apexCaps(st, taper) {
  if (!(taper < 0) || !st.collapse) return null;
  const f = Number(lim(st).apex_fraction) || 0.999;
  return st.collapse.map(r => (r == null ? null : f * r / Math.tan(-taper * Math.PI / 180)));
}
const apexMin = (st, taper) => {
  const hs = (apexCaps(st, taper) || []).filter(h => h != null);
  return hs.length ? Math.min(...hs) : null;
};
function showGhost(st, amount, taper) {   // the ghost ends where the solid will
  setExtrudeGhost(amount * (st.ghostSign < 0 ? -1 : 1), taper, apexCaps(st, taper));
}

/* FUSION SEMANTICS (user, 2026-09-03): no barrier — NEGATIVE narrows, POSITIVE
   flares, the DISTANCE is a MAXIMUM. When the narrowing walls meet before it,
   the SERVER ends the solid where they meet (sketch._apex_cap), so a steeper
   angle is a lower cone / pyramid / ridge, flat at 90°. The ring and the box
   accept any angle up to the server's max_taper. The kernel-measured meeting
   depths — fetched lazily, the first time a narrowing taper appears, because
   they cost 18 kernel offsets per face — only decide WHEN to say, once, that
   the tip comes before the distance (rule 7) and how tall to draw the ghost. */
async function ensureCollapse(st) {
  if (st.collapse || st.collapseLoading || !st.plan) return;
  st.collapseLoading = true;
  const plan = await ex.plan({ measure_collapse: true }, true);
  if (ex.st !== st) return;
  if (plan && plan.limits && Array.isArray(plan.limits.collapse))
    st.collapse = plan.limits.collapse;      // per face; null = unmeasurable
  st.collapseLoading = false;
}
function clampTaper(st, t) {
  const m = maxTaper(st);
  t = Math.max(-m, Math.min(m, t));
  if (t < 0) ensureCollapse(st);
  const a = Math.abs(num('exDist'));
  const h = apexMin(st, t);
  if (!st.saidApex && h != null && h < a) {
    st.saidApex = true;                      // once — the server's note repeats it in the tree
    const rMin = Math.min(...st.collapse.filter(r => r != null));
    const meet = -Math.atan(rMin / Math.max(a, 0.01)) * 180 / Math.PI;
    say(`Steeper than ${Math.round(meet * 10) / 10}° the walls meet before ${a} mm, ` +
      `so the solid ends at the tip — lower the angle, the taller it gets ` +
      `(Fusion does the same). The distance stays your maximum.`);
  }
  return t;
}
function setupTaperRing(st, plan) {
  if (!plan.limits.outer_radius) return;
  beginTaperRing(plan.origin, plan.frame, plan.limits.outer_radius * 1.35, num('exTaper'),
    t => {                                   // dragging: ghost + value box only
      g('exTaper').value = Math.round(t * 10) / 10;
      showGhost(st, num('exDist'), t);
    },
    async t => {                             // release: ONE verified rebuild
      g('exTaper').value = Math.round(t * 10) / 10;
      await ex.apply();
      hideExtrudeGhost();
    },
    t => clampTaper(st, t));
}
const gizmos = {
  begin(st, plan) {
    st.collapse = null;                      // measured lazily, when a taper needs it
    st.cutFlipped = false;                   // a fresh profile re-arms the one-shot cut flip
    setAxis(st, plan.axis);
    placeArrow(st);
    beginExtrudeGhost(plan.frame, plan.loops);
    setupTaperRing(st, plan);
  },
  end() { endExtrudeArrow(); endExtrudeGhost(); endTaperRing(); },
};

/* ---------------- apply-time rules ---------------- */
function beforeApply(st) {
  // Cut goes INTO the material. On a face sketch a distance pointing OUT of
  // the body removes NOTHING, so the FIRST value pointing out is flipped here
  // — and only the first: after that the sign is the user's (an upward cut
  // that trims bosses above the face is legitimate). Which sign is "in" comes
  // from the plan: negative on a top face, POSITIVE on a bottom / -x / +y face.
  if (!isFace(st) && !st.cutFlipped && g('exOp').value === 'cut'
      && !g('exThrough').checked && g('exDir').value === 'one') {
    const into = intoSign(st), d = num('exDist');
    if (into && d !== 0 && Math.sign(d) !== into) {
      st.cutFlipped = true;
      g('exDist').value = into * Math.abs(d);
      say(`Cut goes INTO the body — distance flipped to ${g('exDist').value}mm. ` +
        `Drag the arrow (or type) to set the pocket depth.`);
    }
  }
  // typed values obey the same limit as the ring, and say so once
  const t0 = num('exTaper'), t1 = clampTaper(st, t0);
  if (Math.abs(t1 - t0) > 0.05) {
    g('exTaper').value = Math.round(t1 * 10) / 10;
    say(`Taper limited to ${g('exTaper').value}° — a wall cannot lean past flat.`);
  }
}
function afterApply(st) {                    // gizmos follow the (adjusted) boxes
  setExtrudeArrowAmount(num('exDist'));      // st.axis already carries Flip
  setTaperRingAngle(num('exTaper'));
}
/* the server told us the build stopped at the tip (feature notes, R7): say
   it once in the chat too, for the typed-value path that never touches the ring */
function afterPush(st, doc) {
  if (st.saidApex || !doc || !doc.features) return;
  const f = doc.features.find(x => x.id === st.featureId);
  const note = f && (f.notes || []).find(n => /walls meet/.test(n));
  if (note) { st.saidApex = true; say(`ℹ ${note}.`); }
}
/* rare backstop when a build still fails: shrink the taper toward zero a few
   times, then try no taper at all — the framework falls back to the last good
   values after that */
async function settle(st, pr, push) {
  const sign = pr.taper < 0 ? -1 : 1;
  const tries = [];
  for (let m = Math.abs(pr.taper) * 0.6; tries.length < 4 && m > 0.2; m *= 0.6)
    tries.push(sign * m);
  tries.push(0);
  let r = null;
  for (const t of tries) {
    r = await push({ ...pr, taper: t });
    if (r.f && r.f.status === 'ok') {
      const val = Math.round(t * 10) / 10;
      g('exTaper').value = val;
      say(`The kernel could not build a ${Math.round(pr.taper * 10) / 10}° taper on ` +
        `this profile — reduced to ${val}°, which builds.`);
      return r;
    }
  }
  return r;
}
/* the part fell into pieces (the framework detects it, R7): a cut that stops
   INSIDE the material slices it instead of clearing it (user, 2026-08-26) */
const split = n => `the cut stops INSIDE the material, so it slices it instead of ` +
  `clearing it and leaves ${n - 1} loose piece(s). Two fixes: tick "Through all" ` +
  `(then no distance can land inside the part), and to raise or lower what is ` +
  `left, edit the SKETCH's offset — that is the height the cut starts from.`;

const ex = tool({
  name: 'Extrude', icon: '↑', tool: 'extrude',
  panel: 'extrudeDialog', ids: 'ex',
  ops: { profile: 'extrude', face: 'extrude_face' },
  fields: { change: ['Dir', 'Flip', 'Through'], typed: ['Dist', 'Dist2', 'Taper'] },
  show, params, snapshot, sync, refresh, gizmos,
  isEmpty: pr => !pr.through && Math.abs(pr.amount) + Math.abs(pr.amount2 || 0) === 0,
  nothing: 'Nothing extruded — the distance was 0. Open Extrude again, then drag ' +
           'the arrow or type a distance before OK.',
  beforeApply, afterApply, afterPush, settle, split,
  describe: p => `${p.amount}mm / ${p.taper}°`,
});

export const openExtrude = profileId => ex.open(profileId);
export const initExtrude = () => ex.init();
