// extrude.js — Fusion-style Extrude (v1). A non-modal panel with LIVE PREVIEW:
// it creates the extrude (and optional Join/Cut/Intersect) feature immediately
// and edits it in place through the verified rebuild as you change settings, so
// the 3D preview is always a real, checked solid. Cancel removes it; OK keeps.
//
// GEOMETRY COMES FROM THE SERVER (LAUNCH-PLAN.md R1, P1). Which way a positive
// distance moves material, where the arrow sits, the profile's frame and
// outline for the ghost, the taper limits, the default Join/Cut target and
// which sign goes INTO the body all arrive in ONE answer from
// POST /api/tool/plan (toolplan.py). This file draws what it is told and
// computes nothing: the arrow, the ghost and the solid cannot disagree because
// only one answer exists. (Until 2026-09-02 it carried its own copy of
// build123d's plane frames and a JS re-implementation of
// sketch.face_sketch_plane(); the two disagreed on half the faces of a box.)

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh, beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         extrudeArrowDragging,
         beginExtrudeGhost, setExtrudeGhost, hideExtrudeGhost, endExtrudeGhost,
         beginTaperRing, setTaperRingAngle, endTaperRing,
         cancelPlanePick, beginProfilePick, cancelProfilePick } from './viewport.js';

const OPMAP = { join: 'fuse', cut: 'cut', intersect: 'intersect' };
const panel = () => document.getElementById('extrudeDialog');
let st = null;                    // active session
/* the feature the Extrude tool is live-editing right now (null when idle) —
   lets the tree's failure toasts stay quiet about a feature whose failures
   this tool already explains + auto-repairs (settleValid) */
export const activeExtrudeId = () => (st && st.extrudeId) || null;
let timer = null;
const debounce = fn => { clearTimeout(timer); timer = setTimeout(fn, 200); };

const feats = () => (S.lastDoc && S.lastDoc.features) || [];
const isSketch = f => f.op === 'sketch' || f.op === 'sketch_on_face';
const solids = () => feats().filter(f => f.volume != null && !f.suppressed);

function uid(base) {
  const ex = new Set(feats().map(f => f.id));
  let n = 1; while (ex.has(base + n)) n++; return base + n;
}
function fill(id, items, val) {
  const s = document.getElementById(id);
  s.innerHTML = items.map(i => `<option value="${i}">${i}</option>`).join('');
  if (val != null) s.value = val;
}
const g = id => document.getElementById(id);

function setHeader(text) { panel().querySelector('.exhead').textContent = text; }
/* one-command-at-a-time (user mandate 2026-08-05): while this panel is open,
   dialogs.modalGuard() makes every other tool refuse until OK/Cancel */
function showPanel() {
  panel().style.display = 'block';
  S.modalTool = 'Extrude';
  S.modalToolPanel = 'extrudeDialog';
}
function releaseModal() {
  if (S.modalTool === 'Extrude') { S.modalTool = null; S.modalToolPanel = null; }
}
function unlockDialog() {           // edit mode locks rows — a NEW session resets
  setHeader('↑ Extrude');
  g('exProfile').title = '';
  g('exOp').disabled = false; g('exOp').title = '';
  g('exTarget').disabled = false;
}

export function openExtrude(preProfile) {
  cancelPlanePick();                 // a pending plane-pick must not linger
  cancelProfilePick();               // nor a pending profile-pick
  cancelExtrude();                   // clear any prior extrude session's gizmos
  unlockDialog();
  const bods = solids();
  // FACE MODE (Fusion: click a planar face, press Extrude, pull the arrow).
  // Capture the pick now — loadMesh() clears it. An EXPLICIT profile (tree ⬆)
  // always beats a lingering face pick — the click on the sketch row is the
  // user's latest word on what to extrude.
  const face = preProfile ? null : S.pickedFace;
  const tip = [...feats()].reverse().find(f => f.volume != null && !f.suppressed);
  if (face && tip) {
    // Extrude the body the face was PICKED FROM, not whatever happens to be
    // the tip — with several bodies visible those differ, and resolving the
    // face on the wrong body silently extrudes the wrong thing (or fails).
    const owner = face.body && feats().some(f => f.id === face.body)
      ? face.body : tip.id;
    st = { mode: 'face', face: { center: face.center, normal: face.normal || [0, 0, 1],
                                 body: owner },
           inputId: owner, extrudeId: null, opId: null, opType: null, opTarget: null };
    fill('exProfile', ['(selected face)'], '(selected face)');
    g('exProfile').disabled = true;
    fill('exTarget', bods.map(b => b.id), owner);
    // the distance starts at 0 — the box tells the truth: nothing has been
    // extruded yet, and geometry appears only when the user drags or types
    // (user 2026-09-01: "the distance is always starting from 1mm, even I am
    // not extruding — it should be 0")
    g('exDir').value = 'one'; g('exDist').value = '0'; g('exDist2').value = '10';
    g('exTaper').value = '0'; g('exFlip').checked = false;
    g('exOp').value = 'join';            // pulling a face usually grows the body
    g('exDir').disabled = true;          // face extrude is one-directional (drag ± instead)
    syncRows();
    showPanel();
    createPreview();
    return;
  }
  // an explicitly SELECTED profile (viewport pick) counts like the tree's ⬆
  if (!preProfile && S.pickedProfile) preProfile = S.pickedProfile.id;
  // ...and so does a sketch row SELECTED IN THE TREE (select-then-command
  // must work from either place — reported 2026-09-01: "when I touch the
  // sketch in the feature tree, it should also work")
  if (!preProfile && S.selected) {
    const sel = feats().find(f => f.id === S.selected);
    if (sel && isSketch(sel) && !sel.suppressed) preProfile = sel.id;
  }
  if (S.pickedCurved && !preProfile) {
    bus.emit('msg', 'bot',
      `⚠ Extrude needs a FLAT face — the selected surface is ` +
      `${S.pickedCurved.type} (curved). Flat faces (including tilted ones) ` +
      `extrude fine; a rounded face like a cone or cylinder side can't.`);
    return;
  }
  // only UNCONSUMED sketches are offered — a sketch already used by an extrude
  // must not silently become the profile again ("goes back to the old sketch").
  // An explicit preProfile (tree ⬆ / viewport pick) is honoured even if consumed.
  // A SUPPRESSED (struck-out) consumer does not count: striking out a failed
  // extrude must free its sketch to be extruded again.
  const consumed = new Set(feats().filter(f => !f.suppressed)
                                  .flatMap(f => f.inputs));
  const sks = feats().filter(isSketch)
    .filter(s => !consumed.has(s.id) || s.id === preProfile);
  if (!sks.length && !bods.length) {
    bus.emit('msg', 'bot',
      '⚠ Draw a sketch first (Create → Create Sketch), then Extrude it.');
    return;
  }
  if (preProfile && sks.some(s => s.id === preProfile)) {
    st = { mode: 'sketch', sketches: sks.map(s => s.id), extrudeId: null,
           opId: null, opType: null, opTarget: null, profileId: preProfile };
    fill('exProfile', st.sketches, preProfile);
    g('exProfile').disabled = false;
    // the Join/Cut target list; the DEFAULT arrives with the plan (the body
    // the sketch lives on, walked to its current state — never the first
    // body in the tree)
    fill('exTarget', bods.map(b => b.id), null);
    // start at ZERO — the box tells the truth: nothing has been extruded yet,
    // and the solid appears when YOU pull the arrow or type a distance
    g('exDir').value = 'one'; g('exDist').value = '0'; g('exDist2').value = '10';
    g('exTaper').value = '0'; g('exFlip').checked = false; g('exOp').value = 'new';
    g('exDir').disabled = false;
    syncRows();
    showPanel();
    createPreview();
    return;
  }
  // NOTHING selected: Fusion's command-then-select — the USER picks what to
  // extrude (a sketch profile or a flat face); never auto-grab a sketch
  beginProfilePick((kind, data) => {
    if (kind === 'profile') { openExtrude(data); return; }
    S.pickedFace = data;                 // planar face — reuse face mode
    openExtrude();
  });
  bus.emit('msg', 'bot', 'Extrude: click a sketch profile or a flat face in ' +
    'the viewport — your pick, nothing is chosen for you. Esc cancels.');
}

/* EDIT FEATURE (Fusion parity): reopen an EXISTING extrude in the same tool
   that created it — arrow, ghost, taper ring, live verified preview. Every
   change is pushed to the real feature via /api/feature/params; Cancel
   restores the exact params it had when the dialog opened. Profile and
   Operation rows are shown but locked — rewiring the tree is a later step. */
const COMBINER_LABEL = { fuse: 'join', cut: 'cut', intersect: 'intersect' };

export function openExtrudeEdit(fid) {
  cancelPlanePick();
  cancelProfilePick();
  cancelExtrude();
  unlockDialog();
  const f = feats().find(x => x.id === fid);
  if (!f || (f.op !== 'extrude' && f.op !== 'extrude_face')) return;
  const p = f.params || {};
  const face = f.op === 'extrude_face';
  // normalized snapshot of EVERY param this dialog can write in this mode —
  // Cancel pushes it back verbatim, so keys the session added are reset too
  const original = face
    ? { face_center: p.face_center, face_normal: p.face_normal || [0, 0, 1],
        amount: Number(p.amount) || 0, taper: Number(p.taper) || 0,
        flip: !!p.flip }
    : { amount: Number(p.amount) || 0, both: !!p.both,
        amount2: Number(p.amount2) || 0, taper: Number(p.taper) || 0,
        flip: !!p.flip, through: !!p.through };
  if (face) {
    st = { mode: 'face', editing: true, extrudeId: f.id, original,
           inputId: f.inputs[0],
           face: { center: original.face_center, normal: original.face_normal,
                   body: f.inputs[0] },
           opId: null, opType: null, opTarget: null,
           lastGood: { amount: original.amount, taper: original.taper } };
    fill('exProfile', [`(face of ${f.inputs[0]})`], `(face of ${f.inputs[0]})`);
    g('exDir').value = 'one'; g('exDir').disabled = true;
  } else {
    st = { mode: 'sketch', editing: true, extrudeId: f.id, original,
           profileId: f.inputs[0], sketches: [f.inputs[0]],
           opId: null, opType: null, opTarget: null,
           lastGood: { amount: original.amount, taper: original.taper } };
    fill('exProfile', [f.inputs[0]], f.inputs[0]);
    g('exDir').disabled = false;
    g('exDir').value = original.both ? 'sym' : (original.amount2 ? 'two' : 'one');
  }
  g('exProfile').disabled = true;
  g('exProfile').title = 'changing the profile of an existing extrude comes later';
  g('exDist').value = original.amount;
  g('exDist2').value = original.amount2 || 10;
  g('exTaper').value = original.taper;
  g('exFlip').checked = original.flip;
  g('exThrough').checked = !!original.through;
  // Operation row: show what the tree ACTUALLY does with this extrude (the
  // downstream combiner, if any) — honest but locked in edit mode
  const comb = feats().find(x => COMBINER_LABEL[x.op]
    && (x.inputs || []).includes(f.id));
  g('exOp').value = comb ? COMBINER_LABEL[comb.op] : 'new';
  g('exOp').disabled = true;
  g('exOp').title = 'changing the operation of an existing extrude comes later';
  if (comb) {
    const target = (comb.inputs || []).find(i => i !== f.id) || '';
    fill('exTarget', [target], target);
    g('exTarget').disabled = true;
  }
  setHeader(`✎ Edit ${f.id}`);
  syncRows();
  showPanel();
  setupTool().then(() => setExtrudeArrowAmount(original.amount));   // st.axis carries Flip
  isolateFor(f.id).then(() => loadMesh());   // downstream waits for OK/Cancel
}

/* ------------- editing in isolation (same trick as edit-sketch) -------------
   Editing an extrude in the MIDDLE of a tree rebuilt everything below it on
   every keystroke: `esp_pillar_trim_tool` is feature 23 of 73, so each value
   change paid for 49 downstream features — 5.4 s a keystroke (user, 2026-08-26:
   "its taking a lot of times, when i am changing the values").

   So park the rollback bar on the feature that APPLIES this extrude (its
   boolean, if it has one — otherwise the extrude itself) while the panel is
   open. Everything downstream is skipped, the change is instant, and the one
   full rebuild happens when the panel closes. The bar goes on the BOOLEAN, not
   on the extrude, so what you see is the pocket applied to the body rather than
   a floating tool prism. */
let isoActive = false;

function boolOf(fid) {
  return feats().find(x => COMBINER_LABEL[x.op]
                           && (x.inputs || []).includes(fid));
}

async function isolateFor(fid) {
  const comb = boolOf(fid);
  isoActive = true;
  await postJSON('/api/rollback', { feature_id: (comb || { id: fid }).id });
}

async function releaseIso() {
  if (!isoActive) return;
  isoActive = false;
  await postJSON('/api/rollback', { feature_id: null });
}

/* which SIGN of the distance goes INTO the material — from the plan (a face
   sketch on a bottom / -x / +y face has the canonical frame pointing into the
   body, so there the pocket direction is POSITIVE); null for a plane sketch */
const intoSign = () => (st && st.plan && st.plan.into_sign) || null;

function params() {
  const d = Number(g('exDist').value) || 0;
  const taper = Number(g('exTaper').value) || 0;
  const flip = g('exFlip').checked;
  const through = g('exThrough').checked;
  if (st && st.mode === 'face')
    return { face_center: st.face.center, face_normal: st.face.normal,
             amount: d, taper, flip };
  const dir = g('exDir').value;
  const d2 = Number(g('exDist2').value) || 0;
  if (dir === 'sym') return { amount: d, both: true, amount2: 0, taper,
                              flip: false, through };
  if (dir === 'two') return { amount: d, both: false, amount2: d2, taper, flip,
                              through };
  let amt = d;
  if (through && amt === 0 && intoSign()) {
    // THROUGH ALL with the untouched 0 distance: only the SIGN matters (the
    // cut runs 2 m that way) — default INTO the body for a face sketch, the
    // same direction the old 1mm-then-cut-flip default produced. Dragging
    // the arrow first still wins: any nonzero value keeps its sign.
    amt = intoSign();
  }
  return { amount: amt, both: false, amount2: 0, taper, flip, through };
}

function syncRows() {
  g('exDist2Row').style.display = g('exDir').value === 'two' ? '' : 'none';
  g('exTargetRow').style.display = g('exOp').value === 'new' ? 'none' : '';
  // THROUGH ALL is a cut idea: a boss running 2 m past the part is useless,
  // but a cut that stops inside the material is a bug factory — it slices the
  // part and leaves whatever was above the cut floating loose.
  const isCut = g('exOp').value === 'cut';
  g('exThroughRow').style.display = isCut ? '' : 'none';
  if (!isCut) g('exThrough').checked = false;
  const thru = g('exThrough').checked;
  g('exDist').disabled = thru;
  g('exDist').title = thru ? 'not used — the cut runs all the way through' : '';
}

/* opening the tool builds NOTHING — just the arrow + ghost. The extrude
   feature is created lazily on the first user action (drag release, typed
   value, or OK). No more surprise 1mm boss the moment the panel opens. */
function createPreview() {
  st.extrudeId = null;
  // a fresh profile means a fresh plan — never inherit the last one's frame
  st.plan = null; st.axis = st.axisBase = null; st.ghostSign = 1; st.cutFlipped = false;
  setupTool();
}

/* create the extrude feature the first time the user actually acts */
async function ensureCreated() {
  if (st.extrudeId) return null;
  st.extrudeId = uid('extrude');
  const op = st.mode === 'face' ? 'extrude_face' : 'extrude';
  const input = st.mode === 'face' ? st.inputId : st.profileId;
  return await postJSON('/api/feature/add',
    { id: st.extrudeId, op, params: params(), inputs: [input] });
}

/* ------------- ONE answer: the server's plan drives arrow, ghost AND solid ----
   Extrude used to carry THREE direction sources that disagreed (probed
   2026-09-01): the arrow followed the picked face's OUTWARD normal, the ghost
   box grew along the canonicalised sketch frame's z axis, and the solid followed
   whichever the backend op reads. Now POST /api/tool/plan says, from the op
   that will BUILD the solid: the axis a POSITIVE distance moves material, the
   arrow's origin, the ghost's frame and outline, the taper limits, the default
   target and which sign goes into the body. Flip is folded into st.axis so
   ticking it moves the arrow instead of silently negating at apply time. */
async function fetchPlan() {
  const req = st.mode === 'face'
    ? { tool: 'extrude', body_id: st.face.body, face_center: st.face.center,
        face_normal: st.face.normal }
    : { tool: 'extrude', sketch_id: st.profileId };
  try {
    const r = await fetch('/api/tool/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req) });
    const plan = await r.json();
    if (!plan.ok) {                           // rule 7: failures speak
      bus.emit('msg', 'bot', `⚠ Extrude cannot start: ${plan.error}`);
      return null;
    }
    return plan;
  } catch (e) {
    bus.emit('msg', 'bot', `⚠ Extrude cannot start: the server did not answer (${e.message}).`);
    return null;
  }
}

/* the arrow + ghost + taper ring, from the plan; nothing is built */
async function setupTool() {
  const mine = st;
  const plan = await fetchPlan();
  if (!plan || st !== mine) return;             // closed / re-opened meanwhile
  st.plan = plan;
  st.safeR = plan.limits.inradius;
  if (!st.editing && plan.target_body
      && [...g('exTarget').options].some(o => o.value === plan.target_body))
    g('exTarget').value = plan.target_body;
  setAxis(plan.axis);
  placeArrow();
  beginExtrudeGhost(plan.frame, plan.loops);
  setupTaperRing(plan);
}

// the flip that will actually be SENT (params() drops it in symmetric mode)
const flipOn = () => g('exFlip').checked && g('exDir').value !== 'sym';
function setAxis(base) {
  st.axisBase = base;                            // unflipped, for re-deriving
  const s = flipOn() ? -1 : 1;
  st.axis = [base[0] * s, base[1] * s, base[2] * s];
  // the ghost lives in the plan's frame, whose z IS the axis — so its depth is
  // the amount, and Flip turns it around together with the arrow
  st.ghostSign = s;
}
function refreshAxis() {                         // Flip / direction changed
  if (!st || !st.plan) return;
  setAxis(st.plan.axis);
  placeArrow();
}
function showGhost(amount, taper) {
  setExtrudeGhost(amount * (st && st.ghostSign < 0 ? -1 : 1), taper);
}

// put the drag arrow at the MIDDLE of the profile, pointing the way a positive
// distance actually moves material — both from the plan
function placeArrow() {
  if (!st || !st.plan) return;
  if (!st.axis) setAxis(st.plan.axis);
  // the plan can land mid-drag (setupTool is async): rebuilding the arrow then
  // would kill the drag and leave orbit switched off
  if (extrudeArrowDragging()) return;
  beginExtrudeArrow(st.plan.origin, st.axis, Number(g('exDist').value) || 0,
                    onDrag, onDragCommit, clampAmountFn);
}

/* Fusion's dashed taper circle: centered on the profile, drag the handle
   around it to set the taper angle — ghost only while dragging, one rebuild
   on release, value box stays in sync. */
function setupTaperRing(plan) {
  if (!plan.limits.outer_radius) return;
  beginTaperRing(plan.origin, plan.frame, plan.limits.outer_radius * 1.35,
    Number(g('exTaper').value) || 0,
    t => {                                   // dragging: ghost + value box only
      g('exTaper').value = Math.round(t * 10) / 10;
      showGhost(Number(g('exDist').value) || 0, t);
    },
    async t => {                             // release: ONE verified rebuild
      g('exTaper').value = Math.round(t * 10) / 10;
      await apply();                         // apply() enforces the real barrier
      hideExtrudeGhost();
    },
    clampTaperFn);                           // live barrier: stop before collapse
}

/* live barrier: keep a NARROWING taper (or a distance under taper) inside the
   buildable range. TAPER SIGN IS FUSION'S (user decision 2026-09-03): NEGATIVE
   narrows, POSITIVE flares — and flaring never collapses, so it stays free.
   If the inradius is unknown, don't block — the verified back-off will catch it.
   The walls may meet: the limit is 99.9% of the collapse angle — probed
   2026-09-03 on a washer face, a rect with a hole, a circle, a rectangle, a
   slot and a plate face: every one builds at 0.999, only the exact singular
   angle fails in OCCT. (The old 0.92 margin for profiles with holes is what
   kept a washer's taper from "going until flat".) st.safeR is the plan's
   inradius — the number is the server's; only the clamp of the user's own
   value happens here. */
const TAPER_F = 0.999;
function clampTaperFn(t) {
  if (t >= 0 || !st || !st.safeR) return t;             // flare = free
  const a = Math.abs(Number(g('exDist').value) || 0);
  const limit = -Math.atan(TAPER_F * st.safeR / Math.max(a, 0.01)) * 180 / Math.PI;
  if (t < limit - 0.05 && !st.saidTaperLimit) {
    // rule 7: the ring's handle stopping dead must say WHY, once per session
    // (user 2026-09-03: "after a certain point it is not moving the dot")
    st.saidTaperLimit = true;
    bus.emit('msg', 'bot', `Taper stops at ${Math.round(limit * 10) / 10}° — at ` +
      `this distance the walls meet there (the top closes to a point or a ridge). ` +
      `A longer distance allows a gentler angle to reach the same point.`);
  }
  return Math.max(t, limit);
}
function clampAmountFn(a) {
  const t = Number(g('exTaper').value) || 0;
  if (t >= 0 || !st || !st.safeR) return a;
  const maxA = TAPER_F * st.safeR / Math.tan(-t * Math.PI / 180);
  return Math.max(-maxA, Math.min(maxA, a));
}

function onDrag(amount) {
  // while dragging: move ONLY the instant white ghost box — no rebuild, no lag
  g('exDist').value = Math.round(amount * 100) / 100;
  showGhost(amount, Number(g('exTaper').value) || 0);
}
async function onDragCommit(amount) {     // release: ONE real verified rebuild
  g('exDist').value = Math.round(amount * 100) / 100;
  await apply();
  hideExtrudeGhost();                     // the real solid replaces the ghost
}

async function applyOp() {
  if (!st.extrudeId) return;                  // nothing built yet — nothing to combine
  if (st.editing) return;                     // edit mode never rewires combiners (v1)
  const op = g('exOp').value;                 // new | join | cut | intersect
  const target = g('exTarget').value;
  if (st.opId && (op === 'new' || st.opType !== op || st.opTarget !== target)) {
    await postJSON('/api/feature/remove', { feature_id: st.opId });
    st.opId = st.opType = st.opTarget = null;
  }
  if (op !== 'new' && !st.opId && target) {
    st.opId = uid(st.extrudeId + '_' + op);
    st.opType = op; st.opTarget = target;
    await postJSON('/api/feature/add',
      { id: st.opId, op: OPMAP[op], inputs: [target, st.extrudeId] });
  }
}

const featOf = doc => doc && (doc.features || []).find(x => x.id === st.extrudeId);
const isOk = f => f && f.status === 'ok';

/* push one set of params and read back the extrude feature's health */
async function push(pr) {
  const doc = await postJSON('/api/feature/params',
    { feature_id: st.extrudeId, params: pr });
  warnIfSplit(doc);
  return { doc, f: featOf(doc) };
}

/* THE REAL BARRIER — verified, not guessed. If the chosen taper (or distance)
   collapses the solid, bisect it back toward zero to the largest magnitude the
   geometry kernel actually accepts, keeping its sign. No reliance on a face-
   shape estimate, so it holds for any profile and both drag directions. */
/* apply the analytic barrier to the CURRENT box values (same limit the ring/
   arrow use live) so typed values behave identically to dragging — and note it
   once when we actually had to reduce something. Returns true if it changed. */
function clampBoxValues() {
  let changed = false;
  const t0 = Number(g('exTaper').value) || 0, t1 = clampTaperFn(t0);
  if (Math.abs(t1 - t0) > 0.05) {
    g('exTaper').value = Math.round(t1 * 10) / 10;
    bus.emit('msg', 'bot', `Taper limited to ${g('exTaper').value}° — ` +
      `steeper collapses the walls at this distance.`);
    changed = true;
  }
  const a0 = Number(g('exDist').value) || 0, a1 = clampAmountFn(a0);
  if (Math.abs(a1 - a0) > 0.05) { g('exDist').value = Math.round(a1 * 100) / 100; changed = true; }
  return changed;
}

/* rare backstop: the analytic clamp already prevents collapse on normal faces,
   but if a build still fails (e.g. a non-convex face where the estimate is off,
   or a value with no inradius), shrink the taper toward zero a few times, then
   fall back to the last values that worked. A few rebuilds at most. */
async function settleValid(pr) {
  const sign = pr.taper < 0 ? -1 : 1;
  let mag = Math.abs(pr.taper);
  for (let k = 0; k < 4 && mag > 0.2; k++) {
    mag *= 0.6;
    const t = await push({ ...pr, taper: sign * mag });
    if (isOk(t.f)) {
      const val = Math.round(sign * mag * 10) / 10;
      g('exTaper').value = val;
      bus.emit('msg', 'bot', `Taper limited to ${val}° — steeper collapses the walls here.`);
      return t;
    }
  }
  if (st.lastGood) {                          // taper wasn't it — restore last good
    const r = await push({ ...pr, amount: st.lastGood.amount, taper: st.lastGood.taper });
    g('exDist').value = st.lastGood.amount;
    g('exTaper').value = st.lastGood.taper;
    bus.emit('msg', 'bot', `Reverted to ${st.lastGood.amount}mm / ` +
      `${st.lastGood.taper}° — the new values broke the solid.`);
    return r;
  }
  return await push({ ...pr, taper: 0 });
}

/* one full apply pass. Serialized by apply() so it always finishes. */
/* A cut that stops short of the material it used to reach leaves loose pieces:
   reducing a pillar-trim from 6 to 2 mm sliced a band out of four pillars and
   left their caps floating (user, 2026-08-26: "it created a new body"). The
   geometry is real, so we do not block it — but the moment it happens the panel
   has to say so, while the user still has the value in their hand. */
let saidPieces = 0;
function warnIfSplit(doc) {
  if (!doc || !doc.features) return;
  const n = doc.result_pieces || 0;
  if (n > 1 && n !== saidPieces) {
    saidPieces = n;
    bus.emit('msg', 'bot', `⚠ At this distance the part falls into ${n} ` +
      `separate pieces — the cut stops INSIDE the material, so it slices ` +
      `it instead of clearing it and leaves ${n - 1} loose piece(s). Two ` +
      `fixes: tick "Through all" (then no distance can land inside the part), ` +
      `and to raise or lower what is left, edit the SKETCH's offset — that is ` +
      `the height the cut starts from.`);
  } else if (n <= 1) {
    saidPieces = 0;
  }
}

async function applyOnce() {
  // Cut goes INTO the material. On a face sketch a distance pointing OUT of
  // the body leaves the tool floating outside and removes NOTHING ("cut is not
  // working"). With the box starting at 0 there is nothing to flip when Cut is
  // chosen, so the FIRST value pointing out of the body is flipped here, at
  // apply time — and only the first: after that the sign is the user's (an
  // upward cut that trims bosses above the face is legitimate, so flipping
  // every apply would make it impossible). Which sign is "in" comes from the
  // plan: negative on a top face, POSITIVE on a bottom / -x / +y face.
  if (st.mode === 'sketch' && !st.cutFlipped && g('exOp').value === 'cut'
      && !g('exThrough').checked && g('exDir').value === 'one') {
    const into = intoSign();
    const d = Number(g('exDist').value) || 0;
    if (into && d !== 0 && Math.sign(d) !== into) {
      st.cutFlipped = true;
      g('exDist').value = into * Math.abs(d);
      bus.emit('msg', 'bot', `Cut goes INTO the body — distance flipped to ` +
        `${g('exDist').value}mm. Drag the arrow (or type) to set the pocket depth.`);
    }
  }
  clampBoxValues();                           // analytic barrier — one rebuild
  const pr = params();
  // distance 0 = nothing yet: never create a zero-thickness solid — the tool
  // opens at 0 now, and geometry appears when the user drags or types
  const total = Math.abs(Number(g('exDist').value) || 0)
    + (g('exDir').value === 'two' ? Math.abs(Number(g('exDist2').value) || 0) : 0);
  if (!st.extrudeId && !pr.through && total === 0) return;
  let doc = st.extrudeId ? (await push(pr)).doc : await ensureCreated();
  if (!st) return;
  let f = featOf(doc);
  // backstop for the rare case the estimate missed — never leave a collapsed
  // solid on screen (red tree / blank body).
  if (f && f.status === 'failed') {
    const settled = await settleValid(pr);
    if (!st) return;
    doc = settled.doc; f = settled.f;
  }
  if (isOk(f))
    st.lastGood = { amount: Number(g('exDist').value) || 0,
                    taper: Number(g('exTaper').value) || 0 };
  await applyOp();
  loadMesh();
  // keep the gizmos in sync with the (possibly adjusted) values
  const amt = Number(g('exDist').value) || 0;
  setExtrudeArrowAmount(amt);          // st.axis already carries Flip
  setTaperRingAngle(Number(g('exTaper').value) || 0);
}

// Serialize applies: a settle does several rebuilds and must run to completion,
// but doc-updated re-renders (and fast user input) can call apply() meanwhile.
// Rather than kill the in-flight pass, mark it pending and re-run ONCE after
// with the latest values — coalescing bursts into a single trailing rebuild.
let applyBusy = false, applyPending = false;
async function apply() {
  if (!st) return;
  if (applyBusy) { applyPending = true; return; }
  applyBusy = true;
  try {
    do { applyPending = false; await applyOnce(); }
    while (applyPending && st);
  } finally { applyBusy = false; }
}

async function changeProfile() {
  await teardown();
  st.profileId = g('exProfile').value;
  // the combine target follows the profile: a different sketch may live on a
  // different body (the plan brings the new default)
  fill('exTarget', solids().map(b => b.id), null);
  loadMesh();
  createPreview();
}

async function teardown() {
  endExtrudeArrow();
  endExtrudeGhost();
  endTaperRing();
  if (st && st.opId) await postJSON('/api/feature/remove', { feature_id: st.opId });
  if (st && st.extrudeId) await postJSON('/api/feature/remove', { feature_id: st.extrudeId });
  if (st) { st.opId = st.opType = st.opTarget = st.extrudeId = null; }
}

async function cancel() {
  releaseModal();
  if (st && st.editing) {                // edit mode: the feature stays — put
    const { extrudeId, original } = st;  // its ORIGINAL params back verbatim
    endExtrudeArrow(); endExtrudeGhost(); endTaperRing();
    st = null; panel().style.display = 'none';
    await postJSON('/api/feature/params',
      { feature_id: extrudeId, params: original });
    await releaseIso();
    loadMesh();
    return;
  }
  await teardown(); loadMesh();
  st = null; panel().style.display = 'none';
}

async function ok() {
  releaseModal();
  const editing = st && st.editing;
  if (st && ((!editing && !st.extrudeId) || editing)) {
    // OK must COMMIT the panel's values even if the user never dragged the
    // arrow or touched an input (reported 2026-08-21: traced-logo sketch
    // "could not extrude" — OK with the default distance did nothing).
    // EDIT mode needs it too: typing a value and pressing OK inside the input
    // debounce window dropped the change silently.
    await apply();
  }
  const created = st && st.extrudeId;
  endExtrudeArrow();
  endExtrudeGhost();
  endTaperRing();
  st = null; panel().style.display = 'none';
  await releaseIso();                 // the one full rebuild, now
  loadMesh();
  bus.emit('msg', 'bot', editing
    ? 'Extrude updated — the change is in the feature tree.'
    : created
    ? 'Extrude created — editable in the feature tree.'
    : 'Nothing extruded — the distance was 0. Open Extrude again, then drag ' +
      'the arrow or type a distance before OK.');
}

/* Close a lingering Extrude session when ANOTHER tool starts — otherwise its
   arrow/ring gizmos stay in the viewport and swallow the next click, so faces
   can't be selected anymore. Keeps any already-committed extrude (it's a real
   verified feature); just clears the gizmos + panel. Mirrors cancelPlanePick. */
export function cancelExtrude() {
  releaseModal();
  cancelProfilePick();               // a pending "pick a profile" dies with us
  releaseIso();                      // never leave the rollback bar parked
  if (!st && panel().style.display === 'none') return;
  endExtrudeArrow();
  endExtrudeGhost();
  endTaperRing();
  st = null;
  panel().style.display = 'none';
}

export function initExtrude() {
  g('exProfile').onchange = changeProfile;
  // Cut's into-the-body flip lives in applyOnce() now — it catches the op
  // change AND a positive distance typed later (the box starts at 0, so at
  // op-change time there is usually nothing to flip yet). Leaving Cut
  // re-arms the one-shot flip for the next time Cut is chosen.
  g('exOp').onchange = () => {
    if (st && g('exOp').value !== 'cut') st.cutFlipped = false;
    syncRows(); apply();
  };
  for (const id of ['exDir', 'exTarget', 'exFlip', 'exThrough'])
    g(id).onchange = () => { syncRows(); refreshAxis(); apply(); };
  for (const id of ['exDist', 'exDist2', 'exTaper'])
    g(id).oninput = () => debounce(apply);
  g('exCancel').onclick = cancel;
  g('exOk').onclick = ok;
}
