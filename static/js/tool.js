// tool.js — THE tool framework (LAUNCH-PLAN.md R2, P2), extracted from the
// Extrude tool with zero behaviour change. A tool declares only what makes it
// different — its panel, its ops, how its boxes turn into params, its gizmos —
// and inherits everything every tool must do the same way:
//
//   R4  one selection resolver: explicit argument > viewport pick > tree row
//   9   one command at a time (S.modalTool; dialogs.modalGuard refuses others)
//   2   select-then-command, command-then-select as the fallback
//   4   honest zero: opening builds nothing; a 0 OK creates nothing and says so
//   5   live, real previews: lazy create, then verified rebuilds; Cancel
//       removes the preview features, OK keeps them; edits in isolation
//   6   Join / Cut as separate features, the default target from the plan
//   7   failures speak: a plan that cannot be made, a split part, a build the
//       kernel refused — each is a sentence in the chat, never just a red dot
//   R1  every geometric fact comes from POST /api/tool/plan
//   R3  the viewport follows the document — no tool refreshes it by hand
//
// Before this file, each of those lived as hand-typed code inside extrude.js,
// and the reverted Revolve of 2026-09-02 typed them all a second time.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON, planRequest } from './api.js';
import { holdViewport, cancelPlanePick, beginProfilePick, cancelProfilePick,
         beginEdgePick, endEdgePick, clearPick, pickWhat,
         profilePickArmed } from './viewport.js';

const OPMAP = { join: 'fuse', cut: 'cut', intersect: 'intersect' };   // panel op -> tree op
const COMBINER_LABEL = Object.fromEntries(Object.entries(OPMAP).map(([k, v]) => [v, k]));

const feats = () => (S.lastDoc && S.lastDoc.features) || [];
const isSketch = f => f.op === 'sketch' || f.op === 'sketch_on_face';
const solids = () => feats().filter(f => f.volume != null && !f.suppressed);
/* shared plumbing every tool file imports instead of re-typing */
export const g = id => document.getElementById(id);
export const num = id => Number(g(id).value) || 0;
export const say = text => bus.emit('msg', 'bot', text);
/* a handle's value into its box, rounded to what the box can show */
export const setBox = (id, v, decimals = 1) => {
  const f = 10 ** decimals; g(id).value = Math.round(v * f) / f;
};

/* a backend failure as a sentence: unwrap the Python repr the tree stores
   (moved here from tree.js so a tool can relay WHY its build failed) */
export function humanProblem(p) {
  const m = p.match(/^(ValueError|KeyError|TypeError|RuntimeError)\((['"])([\s\S]*)\2\)$/);
  if (m) return m[1] === 'TypeError'
    ? 'bad parameters — ' + m[3] : m[3];
  if (/StdFail|Standard_|OCP\.|BRep|TopoDS|GeomAbs/.test(p))
    return 'the geometry kernel rejected this shape — try smaller values ' +
           'or a different face (' + p + ')';
  if (p.includes('is unavailable'))
    return p + ' — fix that upstream feature first';
  return p;
}

export function uid(base) {
  const ex = new Set(feats().map(f => f.id));
  let n = 1; while (ex.has(base + n)) n++; return base + n;
}
function fill(id, items, val) {
  const s = g(id);
  s.innerHTML = items.map(i => `<option value="${i}">${i}</option>`).join('');
  if (val != null) s.value = val;
}

/* ---------------- R4: ONE selection, in one place ----------------
   What a tool works on when it is pressed, in this order: the explicit
   argument (a tree row's action button), the viewport's face pick, the
   viewport's profile pick, the sketch row selected in the tree, a curved-face
   pick (a tool that needs a FLAT face refuses it with a sentence) and, last
   of all, a non-sketch tree row — the feature itself (Pattern's seed). EVERY
   viewport pick outranks a tree row: a tree click REPLACES the viewport pick
   (tree.selectFeature calls viewport.clearPick) but nothing clears the row,
   so the row comes last. One selection set, like Fusion.
   Direction and sign are the server's (the plan), never decided here. */

/* the body a picked face belongs to: the body it was PICKED FROM (several
   bodies are visible and clickable), else the newest solid; null when there
   is no solid at all. One rule for every tool and for sketch-on-face. */
export function pickedBody(face) {
  if (face && face.body && feats().some(f => f.id === face.body)) return face.body;
  const tip = solids().at(-1);
  return tip ? tip.id : null;
}

function currentSelection(explicit) {
  if (explicit) return { kind: 'profile', id: explicit };
  // an edge pick, as the viewport drew it: the server reads the edge off its
  // points — no midpoint is computed here (R1)
  if (S.pickedEdge && S.pickedEdge.info)
    return { kind: 'edges', body: S.pickedEdge.body,
             edges: [{ points: S.pickedEdge.info.points }] };
  const face = S.pickedFace;
  const owner = face && pickedBody(face);
  if (owner) {
    // no normal is invented here: the server resolves the face by its centre
    // and, when the pick gave one, its normal (R1)
    return { kind: 'face', center: face.center, normal: face.normal || null, body: owner,
             point: face.point || null };     // where it was clicked (Hole's centre)
  }
  if (S.pickedProfile) return { kind: 'profile', id: S.pickedProfile.id };
  const sel = feats().find(f => f.id === S.selected);
  if (sel && isSketch(sel) && !sel.suppressed) return { kind: 'profile', id: sel.id };
  // a curved face carries where it is and whose it is, so a tool that takes ANY
  // face (Pattern: a bore's wall names the hole) can read it like a face pick.
  // It outranks a tree ROW: a tree click clears the viewport pick but not the
  // other way round, so a row selected minutes ago hid the face just clicked —
  // and Extrude / Revolve lost their "needs a FLAT face" refusal (P4 review).
  if (S.pickedCurved) {
    const c = S.pickedCurved;
    return { kind: 'curved', type: c.type, center: c.center, normal: c.normal || null,
             body: pickedBody(c), point: c.point || null };
  }
  // a tree row that is not a sketch is the FEATURE itself (Pattern's seed)
  if (sel && !sel.suppressed) return { kind: 'feature', id: sel.id };
  return null;
}

/* ---------------- the registry: one tool open at a time ---------------- */
let active = null;          // the tool whose session / panel is open
const byOp = {};            // op -> the tool that re-opens a feature of that op
let isoActive = false;      // an edit has the rollback bar parked
let isoPending = null;      // the park request in flight: a release never overtakes it

/* the feature the open tool is live-editing (the tree's failure toasts stay
   quiet about it — the tool explains and repairs its own failures) */
export const activeToolFeature = () => (active && active.st && active.st.featureId) || null;
/* is a tool's SESSION open (panel up, its feature mid-edit)? Undo asks: while
   a tool owns the document, stepping the history under it would strand the
   session on a feature that no longer exists. Measure sets the modal lock too
   but keeps no session, and undoing a typed dimension is exactly what its user
   wants. */
export const toolSessionOpen = () => !!(active && active.st);
export const canEdit = op => !!byOp[op];
export function editFeature(fid) {
  const f = feats().find(x => x.id === fid);
  const t = f && byOp[f.op];
  if (t) t.openEdit(fid);
}

/* ---- a tool waiting for a TREE ROW (Pattern's seed) ----
   ONE waiter at a time, dropped whenever the pick it belongs to goes: Esc, the
   viewport cancelling on a document change, another tool starting, the session
   ending. The handler used to be removed only INSIDE its own callbacks, so a
   cancelled wait stayed on the bus and hijacked the next tool's row click —
   Circular, Esc, Rectangular, click a row, and CIRCULAR opened (P4 review). */
let rowWait = null;
function waitForRow(fn) {
  dropRowWait();                    // a second waiter would answer the same click
  rowWait = fn;
  bus.on('feature-selected', fn);
}
function dropRowWait() {
  if (!rowWait) return;
  bus.off('feature-selected', rowWait);
  rowWait = null;
}

/* Close a lingering tool session when ANOTHER tool starts — otherwise its
   gizmos stay in the viewport and swallow the next click. A NEW session's
   committed feature stays (it is a real verified feature); an unfinished EDIT
   is cancelled, so its original values come back. Also clears a pending
   "pick a profile" and never leaves the rollback bar parked. */
export function cancelTool() {
  cancelProfilePick();
  dropRowWait();                    // ...and the row click it was waiting for
  releaseIso();
  if (active) active.abandon();
}

/* The server died under an open session (a kernel crash) and came back as of
   the last completed step. The panel lets go WITHOUT the usual teardown: the
   fatal step never landed, rollback state is not persisted, and the feature's
   last good values are in the restored document. */
bus.on('server-recovered', () => {
  cancelProfilePick();
  dropRowWait();
  isoActive = false; isoPending = null;   // a relaunched server parks no rollback
  if (active) active.recover();           // (releaseIso would post to nothing)
});

/* ------------- editing in isolation (same trick as edit-sketch) -------------
   Editing a feature in the MIDDLE of a tree rebuilt everything below it on
   every keystroke — 5.4 s a keystroke on esp32-remote (user, 2026-08-26). So
   the rollback bar is parked on the feature that APPLIES the edited one (its
   boolean, if any — so you see the pocket, not a floating tool prism) while
   the panel is open; the one full rebuild happens when the panel closes. */
function boolOf(fid) {
  return feats().find(x => COMBINER_LABEL[x.op] && (x.inputs || []).includes(fid));
}
/* Parking and releasing the bar are the SESSION's own document changes, so
   they run inside holdViewport: the scene follows once at the end (R3), and a
   session-long face pick is not cancelled as if the document had changed under
   it (the reply to /api/rollback carries the whole document, so it emits
   'doc-updated' like any other POST). */
async function isolateFor(fid) {
  const comb = boolOf(fid);
  isoActive = true;
  isoPending = holdViewport(() =>
    postJSON('/api/rollback', { feature_id: (comb || { id: fid }).id }));
  try { await isoPending; } finally { isoPending = null; }
}
async function releaseIso() {
  if (isoPending) await isoPending.catch(() => {});
  if (!isoActive) return;
  isoActive = false;
  await holdViewport(() => postJSON('/api/rollback', { feature_id: null }));
}

/* ---------------- the factory ----------------
   spec = {
     name, icon, tool           'Extrude', '↑', the plan's tool name ('extrude')
     panel, ids                 the panel element id and the prefix of its field
                                ids: <ids>Profile / Op / Target / TargetRow /
                                Cancel / Ok are the framework's rows
     ops: {profile, face, feature}  the op created for each input kind; a tool
                                with only `face` takes no sketch (Hole); one
                                with `feature` repeats a tree row or the maker
                                of a clicked face (Pattern) — the plan names the
                                body it goes on (`input`) and describes the seed
     anyFace                    the session RE-PICK hands over curved faces too
                                (Circular: a bore names its axis); the SEED pick
                                of a feature tool always does, flag or not
     onRepick(st, data, replan) what a click during the session means when it
                                is not "move the input" (Pattern: the axis)
     eats                       the face op returns its body CHANGED (Hole): no
                                Join / Cut row, no target
     repick                     face tools: while the panel is open a click on a
                                flat face of the body moves the input there
                                (the value is the hint the picker shows)
     fields: {change, typed}    the tool's own field-id suffixes: `change` fields
                                re-apply on change, `typed` ones after a pause
     show(st, params)           write params (or {} = the honest defaults) into
                                the boxes;  params(st) reads them back
     snapshot(feature)          a normalized copy of EVERY param the tool can
                                write, for Cancel-in-edit to restore verbatim
     isEmpty(params, st)        honest zero: nothing to build yet
     hold(params, st)           HALF-MADE: the sentence to say (once) when these
                                values are a state the op would certainly refuse
                                because the user is mid-change — nothing is
                                applied, so the revert cannot undo their choice
     nothing                    the sentence OK says when nothing was built
     gizmos: {begin(st, plan), end()}   handles, from the plan only
     split(n)                   the remedy when the part falls into n pieces
     sync(st) refresh(st) beforeApply(st) afterApply(st) afterPush(st, doc)
     settle(st, params, push)   milder values to try when the kernel refuses
     describe(params)           the values, for the revert sentence
   }
   returns the controller {open, openEdit, init, abandon, apply, plan, st} */
/* Esc = cancel the open tool (fusion-parity rule 5), inherited by every tool.
   A pending pick without a session is the viewport's to cancel. */
window.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || e.repeat) return;   // held down = ONE cancel
  if (active && active.st) active.cancel();
});

/* THE SESSION VANISHED MID-REQUEST. postJSON's crash branch emits
   'server-recovered' SYNCHRONOUSLY (bus.js), so recover() → hide() → st = null
   lands INSIDE an await down here, and every line after that await would
   dereference null. Rather than a null check after each one, the answer to a
   dead session throws this: thrown in ONE place (post), caught in ONE place
   (apply), and the whole chain unwinds. */
const GONE = Symbol('the tool session went away');

export function tool(spec) {
  const P = spec.ids;
  const id = s => P + s;
  const el = s => g(P + s);
  const panel = () => g(spec.panel);
  let st = null;                    // the open session
  let closing = false;              // a Cancel / OK is already tearing it down
  let timer = null;                 // a typed value waiting for its apply
  const debounce = fn => {
    clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn(); }, 200);
  };
  const lower = spec.name.toLowerCase();

  const ctl = { open, openEdit, init, abandon, apply, cancel, replan, recover,
                plan: fetchPlan, get st() { return st; } };
  for (const op of Object.values(spec.ops)) if (op) byOp[op] = ctl;

  /* -------- panel + the one-command-at-a-time lock (rule 9) -------- */
  function setHeader(text) { panel().firstElementChild.textContent = text; }
  function showPanel() {
    panel().style.display = 'block';
    S.modalTool = spec.name;
    S.modalToolPanel = spec.panel;
    active = ctl;
  }
  function releaseModal() {
    if (S.modalTool === spec.name) { S.modalTool = null; S.modalToolPanel = null; }
  }
  /* the panel and the gizmos go at once; the LOCK is released only when the
     session's last document change has landed (see ok / cancel) — a tool
     opened in between would otherwise be torn down by this very close */
  function hide() {
    spec.gizmos.end();
    endEdgePick();
    cancelProfilePick();              // a re-pick armed for the session goes with it
    dropRowWait();
    st = null;
    panel().style.display = 'none';
    if (active === ctl) active = null;
  }
  function unlock() {                 // edit mode locks rows — a NEW session resets
    setHeader(`${spec.icon} ${spec.name}`);
    el('Profile').title = '';
    el('Op').disabled = false; el('Op').title = '';
    el('Target').disabled = false;
  }
  function sync() {
    el('TargetRow').style.display = el('Op').value === 'new' ? 'none' : '';
    if (spec.sync) spec.sync(st);
  }
  const session = input => ({ input, featureId: null, opId: null, opType: null,
                              opTarget: null, editing: false, plan: null,
                              lastGood: null, lastGoodPlan: null, firstExtra: null, heldWhy: null });

  /* -------- open on the current selection (rules 1, 2, 4) -------- */
  function open(explicit) {
    cancelPlanePick();                // a pending plane-pick must not linger
    cancelTool();                     // nor a prior session's gizmos
    unlock();
    const bods = solids();
    const sel = currentSelection(explicit);
    if (spec.ops.edges) { openEdges(sel, bods); return; }
    if (spec.ops.feature) { openFeature(sel, bods); return; }
    if (sel && sel.kind === 'edges')     // an edge, for a tool that takes profiles / faces
      say(`⚠ ${spec.name} works on ` +
        `${pickWhat({ profiles: !!spec.ops.profile, faces: !!spec.ops.face })}` +
        ' — click one of those, not an edge.');
    if (sel && sel.kind === 'face' && spec.ops.face) {
      // FACE MODE (Fusion: click a planar face, press the tool, pull)
      st = session(sel);
      fill(id('Profile'), ['(selected face)'], '(selected face)');
      el('Profile').disabled = true;
      fill(id('Target'), bods.map(b => b.id), sel.body);
      // pulling a face usually grows the body; an op that EATS it (Hole) combines nothing
      el('Op').value = spec.eats ? 'new' : 'join';
      begin();
      return;
    }
    if (sel && sel.kind === 'curved') {
      say(`⚠ ${spec.name} needs a FLAT face — the selected surface is ` +
        `${sel.type} (curved). Flat faces (including tilted ones) ${lower} ` +
        `fine; a rounded face like a cone or cylinder side can't.`);
      return;
    }
    const canFace = !!spec.ops.face;
    if (sel && sel.kind === 'face')   // picked a face for a tool without face mode
      say(`⚠ ${spec.name} works on a sketch profile — click a sketch, not a face.`);
    if (!spec.ops.profile) {          // a FACE-ONLY tool (Hole): no sketch list to offer
      if (sel && sel.kind === 'profile')
        say(`⚠ ${spec.name} starts on a FLAT face of a body — click a face, not a sketch.`);
      if (!bods.length) {
        say(`⚠ ${spec.name} needs a body — build one first, then click a face of it.`);
        return;
      }
      awaitPick(false);
      return;
    }
    const want = sel && sel.kind === 'profile' ? sel.id : null;
    // only UNCONSUMED sketches are offered — a sketch already used must not
    // silently become the profile again; an explicit pick is honoured even if
    // consumed; a SUPPRESSED (struck-out) consumer frees its sketch
    const consumed = new Set(feats().filter(f => !f.suppressed).flatMap(f => f.inputs));
    const sks = feats().filter(isSketch).filter(s => !consumed.has(s.id) || s.id === want);
    if (!sks.length && !(canFace && bods.length)) {   // bodies only help a tool with face mode
      say(`⚠ Draw a sketch first (Create → Create Sketch), then ${spec.name} it.`);
      return;
    }
    if (want && sks.some(s => s.id === want)) {
      st = session({ kind: 'profile', id: want });
      fill(id('Profile'), sks.map(s => s.id), want);
      el('Profile').disabled = false;
      // the DEFAULT target arrives with the plan (the body the sketch lives
      // on, walked to its current state — never the first body in the tree)
      fill(id('Target'), bods.map(b => b.id), null);
      el('Op').value = 'new';
      begin();
      return;
    }
    awaitPick(true);
  }
  /* NOTHING selected: Fusion's command-then-select — the USER picks what to
     work on (a sketch profile and / or a flat face); never auto-grab a sketch */
  function awaitPick(profiles) {
    const opts = { name: spec.name, faces: !!spec.ops.face, profiles };
    beginProfilePick((kind, data) => {
      if (kind === 'profile') { open(data); return; }
      // ONE selection set. This is the only writer that bypasses the
      // viewport's own selectFace, so it must drop what it replaces here:
      // a stale edge pick outranks this face in currentSelection, and the
      // tool would loop asking for the pick the user had just made. clearPick
      // also takes away the old highlight and the stale readout.
      clearPick();
      S.pickedFace = data;            // planar face (and the point clicked) — face mode
      open();
    }, opts);                                          // the picker speaks for THIS tool
    say(`${spec.name}: click ${pickWhat(opts)} in the viewport — your pick, nothing ` +
      'is chosen for you. Esc cancels.');
  }

  /* -------- EDGE MODE (Fusion: press Fillet, click edges, drag) --------
     The panel opens at once, on whatever edge is already picked or on nothing,
     and every click in the viewport goes to the SERVER as a toggle: it knows
     the tangent chains, so it decides add-or-remove and hands back the picks. */
  const edgesLabel = plan => plan && plan.edges && plan.edges.length
    ? `${plan.edges.length} edge${plan.edges.length === 1 ? '' : 's'} of ${plan.input}`
    : '(click edges)';
  function openEdges(sel, bods) {
    if (!bods.length) {
      say(`⚠ ${spec.name} needs a body — build one first, then click its edges.`);
      return;
    }
    if (sel && sel.kind !== 'edges')
      say(`⚠ ${spec.name} works on the EDGES of a body — click an edge, not a ` +
        `${sel.kind === 'profile' ? 'sketch' : sel.kind === 'feature' ? 'tree row' : 'face'}.`);
    const input = { kind: 'edges', edges: [],
                    body: sel && sel.kind === 'edges' ? sel.body : bods.at(-1).id };
    st = session(input);
    // select-then-command: the edge already picked enters as a CLICK, the same
    // path as clicking in the viewport — so the server's chain default sees an
    // empty selection (fresh picking) rather than a lone unexplained edge
    if (sel && sel.kind === 'edges')
      st.firstExtra = { toggle: { points: sel.edges[0].points } };
    clearPick();                      // the plan's gold edges take over from the pick
    fill(id('Profile'), ['(click edges)'], '(click edges)');
    el('Profile').disabled = true;
    el('Op').value = 'new';
    beginEdgePick(onEdgePick, { name: spec.name });
    begin();
    say(`${spec.name}: click the edges of ${input.body} — a click adds an edge, ` +
      'clicking it again removes it. Esc cancels.');
  }
  function onEdgePick(kind, info) {
    if (!st || st.input.kind !== 'edges') return;
    if (kind !== 'edge') {
      // a whole body of edges at once is the GROUP CHIPS' job (inside/outside
      // × vertical/horizontal), not a face click — which would grab a face's
      // edges on a near-miss, with no hover to warn (face-pick edges: deferred)
      say(`⚠ ${spec.name} works on edges — click an edge of ${st.input.body}, ` +
        `or use the group buttons in the panel to add many at once.`);
      return;
    }
    // while the preview is up the viewport shows THIS tool's result body: its
    // unchanged edges are the input body's edges, so clicks on it count too
    const mine = info.body === st.input.body || info.body === st.featureId;
    if (info.body && !mine) {
      say(`⚠ ${spec.name} works on ONE body at a time — that edge belongs to ` +
        `${info.body}; the selection is on ${st.input.body}.`);
      return;
    }
    replan({ toggle: { points: info.points } });
  }
  /* -------- FEATURE MODE (Pattern: repeat a feature, or a body) --------
     The seed is a tree row (any non-sketch feature) or the face a click landed
     on — flat or curved — whose maker the SERVER looks up (provenance: a
     hole's wall is the hole, a plate's own top is the body). The plan names
     the body the result goes on (`input`: the seed body's current state). */
  const verb = spec.verb || 'repeats';                 // Pattern repeats, Mirror mirrors
  const sketchNote = spec.sketchNote || 'sketch patterns come with the sketch tools';
  function openFeature(sel, bods) {
    if (!bods.length) {
      say(`⚠ ${spec.name} needs a body — build one first, then click a feature of it.`);
      return;
    }
    if (sel && sel.kind === 'profile') {
      say(`⚠ ${spec.name} ${verb} a feature or a body — a sketch is not one (${sketchNote}). ` +
        'Click a hole, a boss, or a body.');
      return;
    }
    if (sel && sel.kind === 'edges') {
      say(`⚠ ${spec.name} ${verb} a feature or a body — click a face of it, or its row ` +
        'in the tree, not an edge.');
      return;
    }
    if (sel && (sel.kind === 'face' || sel.kind === 'curved') && sel.body) {
      st = session({ kind: 'face', center: sel.center, normal: sel.normal || null,
                     body: sel.body, point: sel.point || null });
    } else if (sel && sel.kind === 'feature') {
      st = session({ kind: 'feature', id: sel.id, body: null });   // the plan names the body
    } else {
      awaitFeaturePick();
      return;
    }
    clearPick();                      // the plan's handles take over from the pick
    fill(id('Profile'), ['(the selection)'], '(the selection)');   // the plan brings the words
    el('Profile').disabled = true;
    el('Op').value = 'new';
    begin();
  }
  /* nothing selected: a face in the viewport, or a row in the tree */
  function awaitFeaturePick() {
    const hint = `${spec.name}: click a hole, a boss or a body — or a row in the tree · Esc cancels`;
    const onRow = fid => {
      dropRowWait();
      if (!profilePickArmed() || !fid) return;   // the pick was cancelled meanwhile
      cancelProfilePick();
      open();                         // the row IS the selection now
    };
    waitForRow(onRow);
    beginProfilePick((kind, data) => {
      dropRowWait();
      if (kind === 'profile') {
        say(`⚠ ${spec.name} ${verb} a feature or a body — a sketch is not one. Click a ` +
          'hole, a boss, or a body. Keep picking, or Esc.');
        awaitFeaturePick();
        return;
      }
      clearPick();
      S.pickedFace = data;            // ANY face: the server names its maker
      open();
    }, { name: spec.name, faces: true, profiles: true, hint, anyFace: true });
    say(hint);
  }

  /* the edge set changed (a click, the chain box): plan again, keep the
     feature if there is one, and re-place the handles */
  /* ONE plan request at a time. Each request carries the picks the previous
     answer settled (`st.input.edges`), so two in flight at once meant the
     later click was sent WITHOUT the earlier one — and its answer, landing
     last, won (user, 2026-09-07: "after selecting one edge sometimes another
     edge is not selecting"). The rebuild a plan triggers is not waited for:
     apply() coalesces bursts into one trailing rebuild on its own. */
  let planChain = Promise.resolve();
  function replan(extra = {}) {
    const mine = st;                  // the session this click belongs to, bound
    // NOW and not when the queue gets to it: Cancel / OK do not drain the queue
    // (settled() waits for rebuilds, not for plans), so a click still waiting
    // its turn used to run against whatever session was open by then — its
    // group landed in a fresh session as gold edges nobody picked, and in an
    // EDIT session it rewrote that feature's stored edges (review 2026-09-07).
    const run = planChain.then(() => replanNow(extra, mine));
    planChain = run.catch(() => {});
    return run;
  }
  async function replanNow(extra, mine) {
    if (!st || st !== mine) return;   // the session it was made in is gone
    const plan = await fetchPlan(extra);
    if (st !== mine) return;
    if (!plan) return;                // refused (it said why): the handles, and the
                                      // session's own face pick, stay as they were
    if (st.featureId && plan.edges && !plan.edges.length) {
      say(`⚠ ${spec.name} keeps at least one edge while a value is set — Cancel closes the tool.`);
      return;
    }
    const had = ((st.plan && st.plan.edges) || []).length;
    spec.gizmos.end();
    adoptPlan(plan);
    // a click that RELEASED edges says so (rule 7): with Chain on, one click on
    // a picked smooth rim releases the whole rim, which reads as "the edge will
    // not select" when nothing says otherwise
    if (plan.click === 'removed') {
      const n = had - (plan.edges || []).length;
      say(`${spec.name}: ${plan.click_n > 1 ? 'those edges were' : 'that edge was'} already picked — ` +
        `the click released ${n} edge${n === 1 ? '' : 's'}. Click again to add ${n === 1 ? 'it' : 'them'} back.`);
    } else if (plan.click === 'added' && (plan.click_n || 0) > 1) {
      say(`${spec.name}: added ${plan.click_n} edges — ${(plan.edges || []).length} picked now.`);
    }
    if (st.featureId) apply();        // not awaited: the next click's plan must not wait for a rebuild
  }
  function adoptPlan(plan) {
    st.plan = plan;
    // (armRepick asks the viewport whether a pick is armed, so anything that
    //  cancelled one — an external document change — is re-armed here)
    if (st.input.kind === 'edges') {
      if (plan.picks != null) st.input.edges = plan.picks;   // exact form for the next request
      st.input.body = plan.input;
      fill(id('Profile'), [edgesLabel(plan)], edgesLabel(plan));
    }
    if (st.input.kind === 'feature' && plan.input) st.input.body = plan.input;   // the plan's body
    if (plan.seed_words) fill(id('Profile'), [plan.seed_words], plan.seed_words);
    // an edit opens on values that built (lastGood = the original): this first
    // plan is the one that describes them, for the revert sentence
    if (st.lastGood && !st.lastGoodPlan) st.lastGoodPlan = plan;
    spec.gizmos.begin(st, plan);
    if (spec.repick && (st.input.kind === 'face' || st.input.kind === 'feature')) armRepick();
  }
  /* -------- a tool whose input POINT can move (Hole) --------
     While the session is open, a click on a flat face of the body puts the
     input there: the plan places everything again and the feature, if built,
     follows. The pick is STICKY — armed once, ended by hide() — so it survives
     its own clicks and the session's rebuilds; a click that lands while the
     plan is in flight still belongs to the tool instead of falling through to
     the ordinary picker. `spec.repick` is the hint it shows. */
  function armRepick() {
    if (profilePickArmed()) return;   // ONE pick, until something cancels it
    beginProfilePick((kind, data) => {
      if (!st || (st.input.kind !== 'face' && st.input.kind !== 'feature')) return;
      // an origin plane (a tool with `planePick`: Mirror's plane) — the tool says what it means
      if (kind === 'plane' && spec.onRepick) { spec.onRepick(st, { world: data }, replan); return; }
      // while the preview is up the viewport shows THIS tool's result body
      const mine = data && (data.body === st.input.body || data.body === st.featureId);
      if (kind !== 'face' || !mine) {
        say(`⚠ ${spec.name} stays on ${st.input.body} — click a face of that body` +
          `${spec.onRepick ? '' : ' to move it there'}, or Cancel.`);
        return;
      }
      if (spec.onRepick) { spec.onRepick(st, data, replan); return; }   // the tool says what a click means
      st.input = { ...st.input, center: data.center, normal: data.normal || null,
                   point: data.point || null };
      replan();
    }, { name: spec.name, faces: true, profiles: false, hint: spec.repick, sticky: true,
         anyFace: !!spec.anyFace, planes: !!spec.planePick });
  }

  /* opening builds NOTHING — the boxes start at the honest zero, the gizmos
     come from the plan, and the feature is created on the first user action */
  function begin() {
    spec.show(st, {});
    sync();
    showPanel();
    startPreview();
  }
  function startPreview(closeOnRefusal = true) {
    st.featureId = null;
    st.plan = null;                   // a fresh input means a fresh plan
    setupTool(closeOnRefusal);
  }

  /* -------- EDIT FEATURE (Fusion parity): reopen in the tool that made it --
     Every change goes to the real feature via /api/feature/params; Cancel
     restores the exact params it had when the panel opened. Profile and
     Operation rows are shown but locked — rewiring the tree is a later step. */
  function openEdit(fid) {
    cancelPlanePick();
    cancelTool();
    unlock();
    const f = feats().find(x => x.id === fid);
    if (!f || !Object.values(spec.ops).includes(f.op)) return;
    const feature = !!spec.ops.feature && f.op === spec.ops.feature;
    const face = !feature && f.op === spec.ops.face;
    const edges = f.op === spec.ops.edges;
    const p = f.params || {};
    st = session(feature
      ? { kind: 'feature', id: p.seed || null, body: f.inputs[0] }   // the server reads the stored seed
      : face
        ? { kind: 'face', center: p.face_center, normal: p.face_normal || null,
            body: f.inputs[0], point: null }    // the server reads the stored point
        : edges
          ? { kind: 'edges', body: f.inputs[0], edges: null }   // null: the server reads the stored ones
          : { kind: 'profile', id: f.inputs[0] });
    st.editing = true;
    st.featureId = f.id;
    st.original = spec.snapshot(f);
    st.lastGood = st.original;
    if (edges) { clearPick(); beginEdgePick(onEdgePick, { name: spec.name }); }
    const label = feature ? `${p.seed || 'the body'} on ${f.inputs[0]}`
      : face ? `(face of ${f.inputs[0]})`
        : edges ? `edges of ${f.inputs[0]}` : f.inputs[0];
    fill(id('Profile'), [label], label);
    el('Profile').disabled = true;
    el('Profile').title = `changing the profile of an existing ${lower} comes later`;
    spec.show(st, st.original);
    // Operation row: show what the tree ACTUALLY does with this feature (the
    // downstream combiner, if any) — honest but locked in edit mode
    const comb = boolOf(f.id);
    el('Op').value = comb ? COMBINER_LABEL[comb.op] : 'new';
    el('Op').disabled = true;
    el('Op').title = `changing the operation of an existing ${lower} comes later`;
    if (comb) {
      const target = (comb.inputs || []).find(i => i !== f.id) || '';
      fill(id('Target'), [target], target);
      el('Target').disabled = true;
    }
    setHeader(`✎ Edit ${f.id}`);
    sync();
    showPanel();
    setupTool();
    isolateFor(f.id);                 // downstream waits for OK/Cancel
  }

  /* -------- R1: ONE answer drives every handle and the solid -------- */
  async function fetchPlan(extra = {}, quiet = false) {
    const i = st.input;
    const req = i.kind === 'face'
      ? { tool: spec.tool, body_id: i.body, face_center: i.center, face_normal: i.normal,
          face_point: i.point || null }
      : i.kind === 'edges'
        ? { tool: spec.tool, body_id: i.body, edges: i.edges }
        : i.kind === 'feature'
          ? { tool: spec.tool, seed_id: i.id }
          : { tool: spec.tool, sketch_id: i.id };
    if (st.editing) req.feature_id = st.featureId;   // the server reads the stored params
    const more = spec.planExtra ? spec.planExtra(st) : {};
    const first = st.firstExtra; st.firstExtra = null;   // consumed once
    const plan = await planRequest({ ...req, ...more, ...first, ...extra });
    if (plan.ok) return plan;
    if (!quiet) say(`⚠ ${spec.name} cannot start: ${plan.error}.`);     // rule 7
    return null;
  }
  async function setupTool(closeOnRefusal = true) {
    const mine = st;
    const plan = await fetchPlan();
    if (st !== mine) return;                    // closed / re-opened meanwhile
    if (!plan) {                                // refused (it said why)
      if (closeOnRefusal) { hide(); releaseIso(); releaseModal(); }   // opening: no empty panel
      return;                                   // mid-session: the panel stays, pick another profile
    }
    if (!st.editing && plan.target_body
        && [...el('Target').options].some(o => o.value === plan.target_body))
      el('Target').value = plan.target_body;
    adoptPlan(plan);
  }

  /* -------- the verified preview (rules 4, 5, 6, 7) -------- */
  const featOf = doc => doc && (doc.features || []).find(x => x.id === st.featureId);
  const isOk = f => f && f.status === 'ok';

  /* Every server call this session makes. If the open session is no longer the
     one that made the call by the time the answer lands — the server crashed
     and recover() closed the panel — then the answer belongs to nobody: drop
     it and unwind, instead of writing it into a session that is gone. */
  async function post(url, body) {
    const mine = st;
    const doc = await postJSON(url, body);
    if (st !== mine) throw GONE;
    return doc;
  }

  async function create(pr) {           // the first real user action creates it
    st.featureId = uid(spec.tool);
    const i = st.input;
    return await post('/api/feature/add', {
      id: st.featureId, op: spec.ops[i.kind === 'profile' ? 'profile' : i.kind],
      params: pr,
      // a feature tool's body is the plan's: the seed body's current state
      inputs: [i.kind === 'profile' ? i.id
               : i.kind === 'feature' ? (st.plan && st.plan.input) || i.body : i.body] });
  }
  async function push(pr) {             // one param set → the feature's health
    const doc = await post('/api/feature/params',
      { feature_id: st.featureId, params: pr });
    warnIfSplit(doc);
    if (spec.afterPush) spec.afterPush(st, doc);
    return { doc, f: featOf(doc) };
  }

  /* A cut that stops short of the material it used to reach leaves loose
     pieces (user, 2026-08-26: "it created a new body"). The geometry is real,
     so it is not blocked — but the panel says so while the value is still in
     the user's hand. The framework detects it; the remedy is the tool's. */
  let saidPieces = 0;
  function warnIfSplit(doc) {
    if (!doc || !doc.features) return;
    const n = doc.result_pieces || 0;
    if (n > 1 && n !== saidPieces) {
      saidPieces = n;
      say(`⚠ At this value the part falls into ${n} separate pieces` +
        (spec.split ? ` — ${spec.split(n)}` : '.'));
    } else if (n <= 1) {
      saidPieces = 0;
    }
  }

  /* the kernel refused: let the tool try milder values, then fall back to the
     last values that built — never leave a collapsed solid on screen (red
     tree / blank body) without a word */
  async function settle(pr, failed) {
    // the op's own sentence names what to change (fillet: "the largest that
    // builds here is 5.9 mm") — the tool relays it, the tree stays quiet
    const why = (failed && failed.f && failed.f.problems && failed.f.problems[0]) || '';
    if (why) say(`⚠ ${humanProblem(why)}`);
    const r = spec.settle ? await spec.settle(st, pr, push, humanProblem(why)) : null;
    if (r && isOk(r.f)) return r;
    if (st.lastGood) {
      const back = await push(st.lastGood);
      spec.show(st, st.lastGood);
      sync();                           // rows and gizmos follow the restored boxes
      if (spec.refresh) spec.refresh(st);
      say(`Reverted to ${spec.describe(st.lastGood, st)} — the new values broke the solid.`);
      return { ...back, reverted: true };   // lastGood is what is on the feature now
    }
    return r || failed;               // nothing better is known: the tree says why
  }

  /* Join / Cut / Intersect are separate features with a target (rule 6) */
  async function applyOp() {
    if (!st.featureId) return;          // nothing built yet — nothing to combine
    if (st.editing) return;             // edit mode never rewires combiners (v1)
    const op = el('Op').value;          // new | join | cut | intersect
    const target = el('Target').value;
    if (st.opId && (op === 'new' || st.opType !== op || st.opTarget !== target)) {
      await post('/api/feature/remove', { feature_id: st.opId });
      st.opId = st.opType = st.opTarget = null;
    }
    if (op !== 'new' && !st.opId && target) {
      st.opId = uid(st.featureId + '_' + op);
      st.opType = op; st.opTarget = target;
      await post('/api/feature/add',
        { id: st.opId, op: OPMAP[op], inputs: [target, st.featureId] });
    }
  }

  async function applyOnce() {
    if (spec.beforeApply) spec.beforeApply(st);
    const pr = spec.params(st);
    const plan = st.plan;               // the plan these values came from (see lastGoodPlan)
    const empty = spec.isEmpty(pr, st);
    // honest zero: never create a zero-thickness solid — geometry appears
    // when the user drags or types
    if (!st.featureId && empty) return;
    // HALF-MADE: values the op would certainly refuse because the user is
    // mid-change (a seat kind just chosen, Through just unticked, a seat box
    // half-typed). Applying them fails and the automatic revert would undo the
    // very choice that was made, so the tool waits — and says once what for.
    let held = spec.hold ? spec.hold(pr, st) : null;
    // BACK TO ZERO with a preview up (a value cleared to retype it, the arrow
    // dragged home): the preview goes and the box keeps its 0. Pushing the 0
    // made the kernel refuse it and the revert wrote the OLD value into the box
    // the user had just emptied (2026-09-07: "I change 12 to 0 and it reloads
    // 12"). An EDIT keeps its feature and says so instead. Only once the plan
    // is in: a tool whose params come from it reads them as empty until then,
    // and an edit reopened and typed at once must still push.
    if (!held && empty && st.plan) {
      if (!st.editing) {
        await unbuild();
        if (spec.afterApply) spec.afterApply(st);     // the handles sit at 0
        return;
      }
      held = `${spec.name}: nothing can be built from these values — the feature keeps ` +
             `${spec.describe(st.lastGood, st)} until you type new ones; Cancel puts it back as it was.`;
    }
    if (held) {
      if (st.heldWhy !== held) { st.heldWhy = held; say(held); }
      return;
    }
    st.heldWhy = null;
    let doc = st.featureId ? (await push(pr)).doc : await create(pr);
    let f = featOf(doc);
    // lastGood is what the kernel VERIFIED, never a re-read: `pr` for a plain
    // success (a plan landing mid-push swaps st.plan under us, and a tool whose
    // params come from the plan rather than from a box — Mirror's plane, Hole's
    // `at`, Fillet's edges — would record it), the milder values a settle typed
    // into the boxes, and after a REVERT nothing at all: the revert has just put
    // lastGood back on the feature, so re-reading would store what was refused.
    let good = pr;
    if (f && f.status === 'failed') {
      const settled = await settle(pr, { doc, f });
      doc = settled.doc; f = settled.f;
      good = settled.reverted ? null : spec.params(st);
    }
    // ...and the plan they came from rides along: a tool whose values have no
    // box (Mirror's plane) describes them in the PLAN's words, never in words
    // re-derived from the stored form in JS (LAUNCH-PLAN R1)
    if (isOk(f) && good) { st.lastGood = good; st.lastGoodPlan = plan; }
    await applyOp();
    if (spec.afterApply) spec.afterApply(st);     // gizmos follow the boxes
  }

  // Serialize applies: a settle does several rebuilds and must run to
  // completion, but doc-updated re-renders (and fast input) can call apply()
  // meanwhile. Mark it pending and re-run ONCE after with the latest values —
  // coalescing bursts into a single trailing rebuild. Every caller gets the
  // promise of the burst in flight, so OK can wait for it. The whole burst is
  // ONE document change for the viewport (R3): it refreshes once, after the
  // last pass — never for a state the next pass throws away.
  let applyRun = null, applyPending = false;
  function apply() {
    if (!st) return Promise.resolve();
    if (applyRun) { applyPending = true; return applyRun; }
    applyRun = holdViewport(async () => {
      do { applyPending = false; await applyOnce(); } while (applyPending && st);
    }).catch(e => { if (e !== GONE) throw e; })   // no session left to finish
      .finally(() => { applyRun = null; });
    return applyRun;
  }
  const settled = () => applyRun ? applyRun.catch(() => {}) : Promise.resolve();

  async function changeProfile() {
    await teardown();
    st.input = { kind: 'profile', id: el('Profile').value };
    // the combine target follows the profile (the plan brings the new default)
    fill(id('Target'), solids().map(b => b.id), null);
    startPreview(false);              // a refused profile keeps the panel: choose another
  }

  /* the preview feature(s) go — Cancel, another profile, or the boxes back at
     zero; the session stays as it is */
  async function unbuild() {
    if (st.opId) await post('/api/feature/remove', { feature_id: st.opId });
    await post('/api/feature/remove', { feature_id: st.featureId });
    st.opId = st.opType = st.opTarget = st.featureId = null;
  }

  /* -------- Cancel / OK / another tool (rule 5) -------- */
  async function teardown() {
    spec.gizmos.end();
    if (st && st.featureId)
      await holdViewport(unbuild).catch(e => { if (e !== GONE) throw e; });
  }
  /* Cancel and OK are ONE-WAY DOORS. st is only nulled by hide(), several
     awaits away, so without this a second Escape (auto-repeat fires ~31/s), a
     double-clicked Cancel, or a Cancel/OK crossfire runs the teardown twice and
     posts a second /api/feature/remove for a feature that has already gone —
     "no feature named 'fillet1'" in the chat, about something the user never
     named. Declarations, not consts: ctl and the buttons take them by name. */
  async function guard(fn) {
    if (!st || closing) return;
    closing = true;
    try { await fn(); } finally { closing = false; }
  }
  async function cancel() { await guard(cancelSession); }
  async function ok() { await guard(okSession); }

  async function cancelSession() {
    clearTimeout(timer); timer = null;  // a typed value on its way is dropped
    await settled();                    // a rebuild in flight finishes first
    if (st && st.editing) {             // the feature stays — put its
      const { featureId, original } = st;   // ORIGINAL params back verbatim
      hide();
      await holdViewport(async () => {
        await postJSON('/api/feature/params', { feature_id: featureId, params: original });
        await releaseIso();
      });
    } else {
      await teardown();
      hide();
    }
    releaseModal();
  }
  async function okSession() {
    const editing = st.editing;
    const typed = !!timer;              // a value typed inside the debounce window
    clearTimeout(timer); timer = null;
    let created = false, gone = false, held = null, failed = null;
    // OK COMMITS the panel's values even if the user never dragged or touched
    // an input, typed inside the debounce window, or pressed OK while a
    // rebuild was still running — in edit mode too. The commit and the one
    // full rebuild (rollback bar released) are ONE change for the viewport.
    await holdViewport(async () => {
      if (st && (editing || !st.featureId || typed || applyRun)) await apply();
      if (!st) { gone = true; return; }   // the server crashed under us, and
      created = !!st.featureId;           // recover() already said so
      held = st.heldWhy;                  // nothing built, and the tool knows why
      // the FIRST values the kernel refused leave a red row with nothing good
      // to revert to (a new mirror whose first plane throws the image off the
      // body): OK must say so, not "created" (P4 review)
      const f = created && feats().find(x => x.id === st.featureId);
      failed = f && f.status === 'failed' ? f : null;
      hide();
      await releaseIso();
    });
    releaseModal();
    if (gone) return;        // OK must not claim a step the crash threw away
    const outcome = failed
      ? `${spec.name} was NOT built — ${humanProblem((failed.problems || [])[0] || 'the kernel refused it')}. ` +
        'Its row is red in the feature tree: double-click it to change the values, or ✕ to remove it.'
      : editing ? `${spec.name} updated — the change is in the feature tree.`
      : created ? `${spec.name} created — editable in the feature tree.`
      : held || spec.nothing;
    // a value the hold gate never applied must not hide behind "updated"
    say(held && held !== outcome ? `${outcome}
⚠ ${held}` : outcome);
  }
  function abandon() {                  // another tool started (see cancelTool)
    if (st && st.editing) { cancel(); return; }   // an unfinished edit is a Cancel
    hide();
    releaseModal();
  }
  function recover() {                  // the server crashed and came back
    clearTimeout(timer); timer = null;  // a typed value on its way is dropped
    hide();
    releaseModal();
  }

  function init() {
    el('Profile').onchange = changeProfile;
    el('Op').onchange = () => { sync(); apply(); };
    for (const s of ['Target', ...(spec.fields.change || [])])
      el(s).onchange = () => { sync(); if (spec.refresh) spec.refresh(st); apply(); };
    for (const s of spec.fields.typed || [])
      el(s).oninput = () => debounce(apply);
    el('Cancel').onclick = cancel;
    el('Ok').onclick = ok;
  }

  return ctl;
}
