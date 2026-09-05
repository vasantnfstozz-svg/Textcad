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
         beginEdgePick, endEdgePick, clearPick } from './viewport.js';

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
   viewport's profile pick, the sketch row selected in the tree, and — only
   when none of those gave a profile — a curved-face pick, which the tool
   refuses with a sentence. The tree click already REPLACES the viewport pick
   (tree.selectFeature calls viewport.clearPick), so this is one set, like
   Fusion. Direction and sign are the server's (the plan), never decided here. */

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
    return { kind: 'face', center: face.center, normal: face.normal || null, body: owner };
  }
  if (S.pickedProfile) return { kind: 'profile', id: S.pickedProfile.id };
  const sel = feats().find(f => f.id === S.selected);
  if (sel && isSketch(sel) && !sel.suppressed) return { kind: 'profile', id: sel.id };
  if (S.pickedCurved) return { kind: 'curved', type: S.pickedCurved.type };
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
export const canEdit = op => !!byOp[op];
export function editFeature(fid) {
  const f = feats().find(x => x.id === fid);
  const t = f && byOp[f.op];
  if (t) t.openEdit(fid);
}

/* Close a lingering tool session when ANOTHER tool starts — otherwise its
   gizmos stay in the viewport and swallow the next click. A NEW session's
   committed feature stays (it is a real verified feature); an unfinished EDIT
   is cancelled, so its original values come back. Also clears a pending
   "pick a profile" and never leaves the rollback bar parked. */
export function cancelTool() {
  cancelProfilePick();
  releaseIso();
  if (active) active.abandon();
}

/* The server died under an open session (a kernel crash) and came back as of
   the last completed step. The panel lets go WITHOUT the usual teardown: the
   fatal step never landed, rollback state is not persisted, and the feature's
   last good values are in the restored document. */
bus.on('server-recovered', () => {
  cancelProfilePick();
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
async function isolateFor(fid) {
  const comb = boolOf(fid);
  isoActive = true;
  isoPending = postJSON('/api/rollback', { feature_id: (comb || { id: fid }).id });
  try { await isoPending; } finally { isoPending = null; }
}
async function releaseIso() {
  if (isoPending) await isoPending.catch(() => {});
  if (!isoActive) return;
  isoActive = false;
  await postJSON('/api/rollback', { feature_id: null });
}

/* ---------------- the factory ----------------
   spec = {
     name, icon, tool           'Extrude', '↑', the plan's tool name ('extrude')
     panel, ids                 the panel element id and the prefix of its field
                                ids: <ids>Profile / Op / Target / TargetRow /
                                Cancel / Ok are the framework's rows
     ops: {profile, face}       the op created for each input kind
     fields: {change, typed}    the tool's own field-id suffixes: `change` fields
                                re-apply on change, `typed` ones after a pause
     show(st, params)           write params (or {} = the honest defaults) into
                                the boxes;  params(st) reads them back
     snapshot(feature)          a normalized copy of EVERY param the tool can
                                write, for Cancel-in-edit to restore verbatim
     isEmpty(params, st)        honest zero: nothing to build yet
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
                              lastGood: null, firstExtra: null });

  /* -------- open on the current selection (rules 1, 2, 4) -------- */
  function open(explicit) {
    cancelPlanePick();                // a pending plane-pick must not linger
    cancelTool();                     // nor a prior session's gizmos
    unlock();
    const bods = solids();
    const sel = currentSelection(explicit);
    if (spec.ops.edges) { openEdges(sel, bods); return; }
    if (sel && sel.kind === 'edges')     // an edge, for a tool that takes profiles / faces
      say(`⚠ ${spec.name} works on a sketch profile${spec.ops.face ? ' or a flat face' : ''}` +
        ' — click one of those, not an edge.');
    if (sel && sel.kind === 'face' && spec.ops.face) {
      // FACE MODE (Fusion: click a planar face, press the tool, pull)
      st = session(sel);
      fill(id('Profile'), ['(selected face)'], '(selected face)');
      el('Profile').disabled = true;
      fill(id('Target'), bods.map(b => b.id), sel.body);
      el('Op').value = 'join';        // pulling a face usually grows the body
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
    // NOTHING selected: Fusion's command-then-select — the USER picks what to
    // work on (a sketch profile or a flat face); never auto-grab a sketch
    beginProfilePick((kind, data) => {
      if (kind === 'profile') { open(data); return; }
      // ONE selection set. This is the only writer that bypasses the
      // viewport's own selectFace, so it must drop what it replaces here:
      // a stale edge pick outranks this face in currentSelection, and the
      // tool would loop asking for the pick the user had just made. clearPick
      // also takes away the old highlight and the stale readout.
      clearPick();
      S.pickedFace = data;            // planar face — reuse face mode
      open();
    }, { name: spec.name, faces: canFace });   // the picker speaks for THIS tool
    say(`${spec.name}: click a sketch profile${canFace ? ' or a flat face' : ''} in the ` +
      `viewport — your pick, nothing is chosen for you. Esc cancels.`);
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
        `${sel.kind === 'profile' ? 'sketch' : 'face'}.`);
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
      say(`⚠ ${spec.name} works on edges — click an edge of ${st.input.body}, not a face.`);
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
  /* the edge set changed (a click, the chain box): plan again, keep the
     feature if there is one, and re-place the handles */
  async function replan(extra = {}) {
    if (!st) return;
    const mine = st;
    const plan = await fetchPlan(extra);
    if (st !== mine || !plan) return;
    if (st.featureId && plan.edges && !plan.edges.length) {
      say(`⚠ ${spec.name} keeps at least one edge while a value is set — Cancel closes the tool.`);
      return;
    }
    spec.gizmos.end();
    adoptPlan(plan);
    if (st.featureId) await apply();
  }
  function adoptPlan(plan) {
    st.plan = plan;
    if (st.input.kind === 'edges') {
      if (plan.picks != null) st.input.edges = plan.picks;   // exact form for the next request
      st.input.body = plan.input;
      fill(id('Profile'), [edgesLabel(plan)], edgesLabel(plan));
    }
    spec.gizmos.begin(st, plan);
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
    const face = f.op === spec.ops.face;
    const edges = f.op === spec.ops.edges;
    const p = f.params || {};
    st = session(face
      ? { kind: 'face', center: p.face_center, normal: p.face_normal || null,
          body: f.inputs[0] }
      : edges
        ? { kind: 'edges', body: f.inputs[0], edges: null }   // null: the server reads the stored ones
        : { kind: 'profile', id: f.inputs[0] });
    st.editing = true;
    st.featureId = f.id;
    st.original = spec.snapshot(f);
    st.lastGood = st.original;
    if (edges) { clearPick(); beginEdgePick(onEdgePick, { name: spec.name }); }
    const label = face ? `(face of ${f.inputs[0]})`
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
      ? { tool: spec.tool, body_id: i.body, face_center: i.center, face_normal: i.normal }
      : i.kind === 'edges'
        ? { tool: spec.tool, body_id: i.body, edges: i.edges }
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
      params: pr, inputs: [i.kind === 'profile' ? i.id : i.body] });
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
      say(`Reverted to ${spec.describe(st.lastGood)} — the new values broke the solid.`);
      return back;
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
    // honest zero: never create a zero-thickness solid — geometry appears
    // when the user drags or types
    if (!st.featureId && spec.isEmpty(pr, st)) return;
    let doc = st.featureId ? (await push(pr)).doc : await create(pr);
    let f = featOf(doc);
    if (f && f.status === 'failed') {
      const settled = await settle(pr, { doc, f });
      doc = settled.doc; f = settled.f;
    }
    if (isOk(f)) st.lastGood = spec.params(st);   // the boxes may have been adjusted
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

  /* -------- Cancel / OK / another tool (rule 5) -------- */
  async function teardown() {
    spec.gizmos.end();
    await holdViewport(async () => {
      if (st && st.opId) await postJSON('/api/feature/remove', { feature_id: st.opId });
      if (st && st.featureId) await postJSON('/api/feature/remove', { feature_id: st.featureId });
    });
    if (st) { st.opId = st.opType = st.opTarget = st.featureId = null; }
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
    let created = false, gone = false;
    // OK COMMITS the panel's values even if the user never dragged or touched
    // an input, typed inside the debounce window, or pressed OK while a
    // rebuild was still running — in edit mode too. The commit and the one
    // full rebuild (rollback bar released) are ONE change for the viewport.
    await holdViewport(async () => {
      if (st && (editing || !st.featureId || typed || applyRun)) await apply();
      if (!st) { gone = true; return; }   // the server crashed under us, and
      created = !!st.featureId;           // recover() already said so
      hide();
      await releaseIso();
    });
    releaseModal();
    if (gone) return;        // OK must not claim a step the crash threw away
    say(editing ? `${spec.name} updated — the change is in the feature tree.`
      : created ? `${spec.name} created — editable in the feature tree.`
      : spec.nothing);
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
