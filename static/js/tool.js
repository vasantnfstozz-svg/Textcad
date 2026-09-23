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
import { SETTINGS, toMm, fmtLen } from './settings.js';
import { holdViewport, cancelPlanePick, beginProfilePick, cancelProfilePick,
         beginEdgePick, endEdgePick, clearPick, pickWhat,
         profilePickArmed, retakeSectionHandles } from './viewport.js';

const OPMAP = { join: 'fuse', cut: 'cut', intersect: 'intersect' };   // panel op -> tree op
const COMBINER_LABEL = Object.fromEntries(Object.entries(OPMAP).map(([k, v]) => [v, k]));
// how a SENTENCE names a combiner (the panel's own words, capitalised)
const OP_WORD = { fuse: 'Join', cut: 'Cut', intersect: 'Intersect' };

const feats = () => (S.lastDoc && S.lastDoc.features) || [];
const isSketch = f => f.op === 'sketch' || f.op === 'sketch_on_face';
const solids = () => feats().filter(f => f.volume != null && !f.suppressed);
/* shared plumbing every tool file imports instead of re-typing */
export const g = id => document.getElementById(id);
export const num = id => Number(g(id).value) || 0;
export const say = text => bus.emit('msg', 'bot', text);
/* a handle's value into its box, rounded to what the box can show. For an
   ANGLE or a COUNT — anything the display unit does not touch. */
export const setBox = (id, v, decimals = 1) => {
  const f = 10 ** decimals; g(id).value = Math.round(v * f) / f;
};

/* ---------------- LENGTHS: the box is the only thing in the display unit ----
   Millimetres are the working unit end to end in this browser — the plan, the
   gizmos, every param the server stores. Settings ▸ Length unit changes only
   the TEXT in a length box and the word beside it, so the conversion lives at
   exactly two places: `mm(id)` reads a box AS millimetres, `setLen(id, v)`
   writes millimetres INTO one. Everything between them stays mm and needs no
   thought. A count, an angle in degrees and a taper are not lengths: they keep
   num() and setBox().

   In millimetres `setLen` writes the number itself (an edit that reopens a
   12.7183 mm feature and presses OK must push 12.7183 back, not a rounded
   copy); in another unit it writes that unit's own precision, the rule the
   sketcher's dimension boxes already follow. `decimals` is the granularity in
   MILLIMETRES a dragged handle rounds to, so a drag reads the same however the
   screen is labelled. */
export const mm = id => toMm(num(id));
export const setLen = (id, v, decimals = null) => {
  const r = decimals == null ? v : Math.round(v * 10 ** decimals) / 10 ** decimals;
  g(id).value = SETTINGS.unit === 'mm' ? r : fmtLen(r, false);
};
/* a length in mm as a SENTENCE says it ("12 mm", "0.4724 in") */
export const len = v => fmtLen(v);

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
   argument (a tree row's action button), the viewport's edge pick, its face
   pick, its profile pick, a curved-face pick (a tool that needs a FLAT face
   refuses it with a sentence) and then — last of all — the tree row: the
   sketch it names, or the feature itself (Pattern's seed). EVERY viewport
   pick outranks a tree row: a tree click REPLACES the viewport pick
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
             area: face.area == null ? null : face.area,   // how big it was when clicked
             point: face.point || null };     // where it was clicked (Hole's centre)
  }
  if (S.pickedProfile) return { kind: 'profile', id: S.pickedProfile.id };
  // a curved face carries where it is and whose it is, so a tool that takes ANY
  // face (Pattern: a bore's wall names the hole) can read it like a face pick.
  // It outranks EVERY tree row — sketch rows included: a tree click clears the
  // viewport pick but not the other way round, so a row selected minutes ago hid
  // the face just clicked, and Extrude / Revolve lost their "needs a FLAT face"
  // refusal (P4 review). The feature row was moved below this then; the SKETCH
  // row stayed above it and kept the same hole open — select a sketch row, click
  // a cylinder wall, press Extrude and the sketch was extruded with never a word
  // about the face just clicked (section 11 review, 2026-09-16).
  if (S.pickedCurved) {
    const c = S.pickedCurved;
    return { kind: 'curved', type: c.type, center: c.center, normal: c.normal || null,
             area: c.area == null ? null : c.area,   // how big it was when clicked
             body: pickedBody(c), point: c.point || null };
  }
  // ...and only now the tree row: the sketch it names, or the FEATURE itself
  // (Pattern's seed)
  const sel = feats().find(f => f.id === S.selected);
  if (sel && isSketch(sel) && !sel.suppressed) return { kind: 'profile', id: sel.id };
  if (sel && !sel.suppressed) return { kind: 'feature', id: sel.id };
  return null;
}
/* WHAT is selected, for a router that picks the tool from the pick (Fusion's
   Press Pull: a face or profile is Extrude, an edge is Fillet). The same
   answer open() will read a moment later — one selection set, read once. */
export const selectionKind = () => { const s = currentSelection(null); return s ? s.kind : null; };

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

/* EVERYTHING a command press ends before it does anything else: a plane pick
   still waiting for a click (Create Sketch), a prior session's gizmos and the
   profile pick / row waiter that belong to it. open() has always done this
   first; it lives here so a command that decides NOT to open a panel does the
   same. A router that only speaks (Press Pull on a curved face) used to return
   with the previous button's pick still armed, and the very click its sentence
   asked for fell into THAT pick instead. Idempotent: each part no-ops when
   there is nothing to end. */
export function endPending() { cancelPlanePick(); cancelTool(); }

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

/* THE DESIGN ON SCREEN BECAME ANOTHER ONE, under the open panel. The panel
   remembers its feature by ID and nothing else, and every write it makes
   (/api/feature/params, /api/feature/add, /api/rollback) is addressed to
   whatever design is ACTIVE — while `uid()` hands out the same names in every
   design, so two of them normally both hold an `extrude1`. a3d6b03 made the
   tab BAR refuse while a panel is open, but the active tab also moves with no
   tab click at all: a design arriving from outside takes it (studio's
   /api/open/<slug>?external=1 — the MCP doorbell, the door doctabs.js's own
   closeTab comment has recorded since 2026-09-01), and so does a switch made
   in a second browser window on the same server. Measured 2026-09-16
   (probes/tool_tab_moves_itself_probe.py): with a panel open on 'panel-design'
   an arriving design took the tab, and the panel's next write moved the
   ARRIVING design's extrude1 from 9 mm to 30 mm — green, unasked — while the
   design the panel was opened on never changed.

   So the session lets go, the same way it lets go of a crashed server and for
   the same reason: its next write belongs to nobody. It writes NOTHING on the
   way out — a preview left behind in the other design is a row the user can
   see and remove, and that beats a silent edit to a design they never opened a
   tool on. */
bus.on('doc-updated', doc => { if (active) active.tabMoved(doc); });

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
     onRow(st, fid, replan)     a TREE ROW clicked while the panel is open, for a
                                tool whose second input is a row (Sweep's path)
     planExtra(st)              fields of the tool's own to send with every plan
                                request (Sweep: which path sketch)
     inputs(st)                 a MULTI-INPUT tool's input list for the feature it
                                creates (Loft's sections), instead of the one input
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
  /* the session's FIRST plan, while it is in flight: OK waits for it, so a
     value typed in the moment between pressing the tool and the plan landing
     still builds instead of "nothing was extruded" (R2) */
  let setupWait = null;
  const debounce = fn => {
    clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn(); }, 200);
  };
  const lower = spec.name.toLowerCase();

  const ctl = { open, openEdit, init, abandon, apply, cancel, replan, recover,
                tabMoved, plan: fetchPlan, get st() { return st; } };
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
    if (S.modalTool !== spec.name) return;
    S.modalTool = null; S.modalToolPanel = null;
    // the gold quad and the arrow are shared with Section view, which takes no
    // modal lock and may have been open underneath the whole time. `hide()`
    // ended THIS tool's arrow, and that object was the section's: give them
    // back now the session is over, or the model stays cut open with nothing
    // to drag (measured 2026-09-19).
    retakeSectionHandles();
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
    setupWait = null;                 // its plan belongs to a session that is gone
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
  /* `tab` / `docName`: WHICH design this session belongs to, so it can notice
     it is no longer the one in front (see the 'doc-updated' let-go above). The
     document is the authority for both (R1) — never a name typed here. */
  const session = input => ({ input, featureId: null, opId: null, opType: null,
                              opTarget: null, opUser: false, editing: false, plan: null,
                              tab: (S.lastDoc && S.lastDoc.active_tab) || null,
                              docName: (S.lastDoc && S.lastDoc.name) || null,
                              lastGood: null, lastGoodPlan: null, firstExtra: null, heldWhy: null });

  /* -------- open on the current selection (rules 1, 2, 4) -------- */
  function open(explicit) {
    endPending();                     // a pending plane-pick, a prior session's gizmos
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
    // a BODY's row in the tree, for a face tool whose faces are OPTIONAL
    // (Shell: no face open = a closed hollow) — the tree is a selection surface
    // (parity rule 2); the plan places the handles on the body itself
    if (sel && sel.kind === 'feature' && spec.bodyRow && bods.some(b => b.id === sel.id)) {
      st = session({ kind: 'face', center: null, normal: null, body: sel.id, point: null });
      fill(id('Profile'), ['(the body)'], '(the body)');
      el('Profile').disabled = true;
      fill(id('Target'), bods.map(b => b.id), sel.id);
      el('Op').value = 'new';
      begin();
      return;
    }
    // a CURVED face names its body just as well for a tool whose input IS the
    // body (Move / Rotate: `anyFace` + `bodyRow`) — the face itself plays no part
    if (sel && sel.kind === 'curved' && spec.anyFace && spec.bodyRow && sel.body) {
      st = session({ kind: 'face', center: sel.center, normal: null, body: sel.body, point: null });
      fill(id('Profile'), ['(the body)'], '(the body)');
      el('Profile').disabled = true;
      fill(id('Target'), bods.map(b => b.id), sel.body);
      el('Op').value = 'new';
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
    // ...and never a PATH sketch (open lines for Sweep, area 0 — the server's
    // `path_sketch` flag): it is what Sweep follows, not a profile
    const pathSk = feats().find(f => f.id === want && f.path_sketch);
    if (pathSk) {
      say(`⚠ '${want}' is a path sketch — open lines drawn for Sweep, no closed shape. ` +
        `${spec.name} needs a closed profile: press it on the profile sketch instead.`);
      return;
    }
    const sks = feats().filter(isSketch).filter(s => !s.path_sketch)
      .filter(s => !consumed.has(s.id) || s.id === want);
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
    // a body tool (`anyFace` + `bodyRow`) is offered every face: any one names the body
    const opts = { name: spec.name, faces: !!spec.ops.face, profiles,
                   anyFace: !!(spec.anyFace && spec.bodyRow) };
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
     The panel opens at once, on whatever is already picked or on nothing, and
     every click goes to the SERVER as a toggle — it knows the tangent chains
     and which faces a feature made, so it decides add-or-remove and hands back
     the picks. Fusion's three selection kinds (user, 2026-09-08: "select a
     body, like from the feature tree … those selected face or body edges
     should be selected … another click should deselect"): an EDGE, a FACE
     (every edge of it) and a FEATURE — a tree row, meaning the edges of the
     faces that feature made, as they are now. A second click on the same face
     or row takes its edges out again; a gold edge is released by clicking it. */
  const edgesLabel = plan => plan && plan.edges && plan.edges.length
    ? `${plan.edges.length} edge${plan.edges.length === 1 ? '' : 's'} of ${plan.input}`
    : '(click edges)';
  // select-then-command (parity rule 2): whatever was picked before the tool —
  // an edge, a face, a tree row — enters as the FIRST CLICK, the same path as
  // clicking with the panel open, so the server's chain default sees an empty
  // selection (fresh picking) rather than a lone unexplained pick
  const firstClick = sel => !sel ? null
    : sel.kind === 'edges' ? { toggle: { points: sel.edges[0].points } }
    : sel.kind === 'face' || sel.kind === 'curved'
      ? { face_toggle: { center: sel.center, normal: sel.normal || null,
                         area: sel.area ?? null } }
    : sel.kind === 'feature' ? { feature_toggle: sel.id } : null;
  function openEdges(sel, bods) {
    if (!bods.length) {
      say(`⚠ ${spec.name} needs a body — build one first, then click its edges.`);
      return;
    }
    if (sel && sel.kind === 'profile')
      say(`⚠ ${spec.name} works on the edges of a body — a sketch has none. Click an ` +
        'edge, a face, or the row of a feature.');
    const first = firstClick(sel);
    const row = !!first && sel.kind === 'feature';
    // a row names its own body (the server walks the feature to its current
    // state), so none is chosen here for it
    const input = { kind: 'edges', edges: [],
                    body: row ? null : (sel && sel.body) || bods.at(-1).id };
    st = session(input);
    st.firstExtra = first;
    st.lastRow = row ? sel.id : null;
    clearPick();                      // the plan's gold edges take over from the pick
    fill(id('Profile'), ['(click edges)'], '(click edges)');
    el('Profile').disabled = true;
    el('Op').value = 'new';
    beginEdgePick(onEdgePick, { name: spec.name });
    waitForRow(onRow);                // the tree stays a selection surface all session
    begin();
    say(`${spec.name}: click edges, faces or a row of the tree` +
      `${input.body ? ` on ${input.body}` : ''} — a click adds, clicking the same ` +
      'thing again removes. Esc cancels.');
  }
  function onEdgePick(kind, info) {
    if (!st || st.input.kind !== 'edges') return;
    // a row opened the tool and its first plan has not named the body yet: the
    // click says which body it is on
    if (!st.input.body) st.input.body = info.body || null;
    // while the preview is up the viewport shows THIS tool's result body: its
    // unchanged edges and faces are the input body's, so clicks on it count too
    const mine = info.body === st.input.body || info.body === st.featureId;
    if (info.body && !mine) {
      say(`⚠ ${spec.name} works on ONE body at a time — that ${kind} belongs to ` +
        `${info.body}; the selection is on ${st.input.body}.`);
      return;
    }
    // a face means every edge of it, toggled as one set; the server names the
    // face by its centre and refuses one only the preview has (a new round)
    if (kind === 'face') {
      replan({ face_toggle: { center: info.center || null, normal: info.normal || null,
                              area: info.area ?? null } });
      return;
    }
    replan({ toggle: { points: info.points } });
  }
  /* a tree row while the panel is open: the edges of the faces that feature
     made, as they are now — added, or taken out when they are all picked. The
     tree toggles its own selection, so clicking the lit row again arrives as
     null: it means the same row, toggled again (the user's "deselect"). */
  function onRow(fid) {
    if (!st || st.input.kind !== 'edges') return;
    const rowId = fid || st.lastRow;
    if (!rowId) return;
    st.lastRow = rowId;
    if (rowId === st.featureId) {
      say(`⚠ that row is this ${lower}'s own result — click another feature, a face or an edge.`);
      return;
    }
    replan({ feature_toggle: rowId });
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
    // An EDGE tool (Fillet, Chamfer) must keep at least one pick: an empty set
    // is nothing to round. `plan.edges` means something else for a tool whose
    // input is a FACE — Shell draws the OPEN faces' outlines with it, and no
    // face open is a legitimate answer (a closed hollow body), so gating this
    // on the input kind, not on the key's name (review of fb0b8c8: the last
    // face could not be closed and the reason talked about edges).
    if (st.featureId && st.input.kind === 'edges' && plan.edges && !plan.edges.length) {
      say(`⚠ ${spec.name} keeps at least one edge while a value is set — Cancel closes the tool.`);
      return;
    }
    const had = ((st.plan && st.plan.edges) || []).length;
    spec.gizmos.end();
    adoptPlan(plan);
    speakClick(plan, had);
    if (st.featureId) apply();        // not awaited: the next click's plan must not wait for a rebuild
  }
  /* what a click did, in the chat (rule 7) — for a click during the session
     AND for the pick that opened the tool (setupTool's first plan carries it).
     A click that RELEASED edges says so: with Chain on, one click on a picked
     smooth rim releases the whole rim, which reads as "the edge will not
     select" when nothing says otherwise. A face or a row says what it was —
     the server names it (`click_of`) — and how many edges it brought. */
  function speakClick(plan, had) {
    const of = plan.click_of === 'face' ? "that face's edges"
      : plan.click_of ? `the edges of ${plan.click_of}` : null;
    if (plan.click === 'removed') {
      const n = had - (plan.edges || []).length;
      say(`${spec.name}: ${of ? `${of} were all` : plan.click_n > 1 ? 'those edges were' : 'that edge was'} ` +
        `picked already — the click released ${n} edge${n === 1 ? '' : 's'}. ` +
        `Click again to add ${n === 1 ? 'it' : 'them'} back.`);
    } else if (plan.click === 'added' && ((plan.click_n || 0) > 1 || of)) {
      say(`${spec.name}: added ${plan.click_n} edge${plan.click_n === 1 ? '' : 's'}` +
        `${of ? ` — ${of}` : ''} — ${(plan.edges || []).length} picked now.`);
    }
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
    if (spec.repick && (st.input.kind === 'face' || st.input.kind === 'feature'
                        || (st.input.kind === 'profile' && spec.onRepick))) armRepick();
    // ...and a value that was already in the boxes when the plan landed builds
    // NOW (R2): typed while the request was in flight, carried over from the
    // last session (Hole remembers a diameter), or brought by the plan itself
    // (Mirror's first plane). applyOnce is the one judge of whether there is
    // anything to build, so this needs no condition of its own — it used to be
    // a hand-typed `if (!st.featureId && <this tool's boxes>) apply()` in seven
    // gizmos.begin. With a feature already built it is replan's call, which
    // makes it after speaking (see replanNow).
    if (!st.featureId) apply();
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
      // a PROFILE tool that takes more profiles while open (Loft's sections):
      // a sketch click is the tool's to read, anything else is said no to
      if (st && st.input.kind === 'profile' && spec.onRepick) {
        if (kind === 'profile') spec.onRepick(st, { profile: data }, replan);
        else say(`⚠ ${spec.name} takes sketch profiles — click a sketch, or Cancel.`);
        return;
      }
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
    }, { name: spec.name, faces: st.input.kind !== 'profile', profiles: st.input.kind === 'profile',
         hint: spec.repick, sticky: true, anyFace: !!spec.anyFace, planes: !!spec.planePick });
  }

  /* opening builds NOTHING — the boxes start at the honest zero, the gizmos
     come from the plan, and the feature is created on the first user action */
  function begin() {
    spec.show(st, {});
    sync();
    showPanel();
    if (spec.onRow) waitForRow(fid => { if (st && fid) spec.onRow(st, fid, replan); });
    startPreview();
  }
  function startPreview(closeOnRefusal = true) {
    st.featureId = null;
    st.plan = null;                   // a fresh input means a fresh plan
    // ...and no values that built, because none did on THIS profile. Only
    // changeProfile() reaches here with a session already under way (begin()
    // opens a new one; an edit goes straight to setupTool), and both of these
    // survived the switch: the revert then pushed the OTHER sketch's values
    // and — since the plan they came from rides along now — put the arrow
    // and the safe range on the other sketch too (round two of the review of
    // fb0b8c8). The first values a new profile refuses leave a red row that
    // says why, which is what a session with nothing good to revert to does.
    st.lastGood = null; st.lastGoodPlan = null;
    beginSetup(closeOnRefusal);
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
            area: p.face_area == null ? null : p.face_area,
            body: f.inputs[0], point: null }    // the server reads the stored point
        : edges
          ? { kind: 'edges', body: f.inputs[0], edges: null }   // null: the server reads the stored ones
          : { kind: 'profile', id: f.inputs[0] });
    st.editing = true;
    st.featureId = f.id;
    // A FORMULA stays a formula (Named parameters). Every tool's snapshot
    // read `Number("t") || 0`, so the boxes showed a formula as 0 — and OK in
    // an edit pushes every box, so an extrude with taper `t` came back with
    // taper 0 from OK alone (review, 2026-09-23: 1039.76 -> 1000 mm3). The
    // panel shows the server's VALUE (`resolved`, R1) and a box the user
    // leaves alone goes back as the formula it came from (see keepFormulas).
    st.formulas = {};
    const shown = { ...p };
    for (const [k, v] of Object.entries(f.resolved || {}))
      if (v != null && typeof p[k] === 'string') { st.formulas[k] = p[k]; shown[k] = v; }
    st.original = spec.snapshot({ ...f, params: shown });
    st.lastGood = st.original;
    if (edges) { clearPick(); beginEdgePick(onEdgePick, { name: spec.name }); waitForRow(onRow); }
    // a tool whose SECOND input is a tree row (Sweep's path) listens in an edit too
    if (!edges && spec.onRow) waitForRow(fid => { if (st && fid) spec.onRow(st, fid, replan); });
    const label = feature ? `${p.seed || 'the body'} on ${f.inputs[0]}`
      : face ? `(face of ${f.inputs[0]})`
        : edges ? `edges of ${f.inputs[0]}` : f.inputs[0];
    fill(id('Profile'), [label], label);
    el('Profile').disabled = true;
    el('Profile').title = `changing the profile of an existing ${lower} comes later`;
    spec.show(st, st.original);
    // ...and what those boxes READ BACK as before anyone touches them (a
    // length in inches is rounded to the unit, so it need not equal the
    // value exactly — an untouched box always reads back the same)
    try { st.shownBack = spec.params(st); } catch (e) { st.shownBack = null; }
    // Operation row: show what the tree ACTUALLY does with this feature (the
    // downstream combiner, if any) — honest but locked in edit mode
    const comb = boolOf(f.id);
    // An `eats` tool's Op select carries ONLY "new" (its op returns the body
    // changed — Hole, Shell, Move, Rotate), and assigning a value a <select>
    // has no option for leaves `.value` EMPTY, which sync() reads as "not new"
    // and so opens the hidden Combine-with row. Live on every one of the 45
    // saved move / rotate rows that feed a boolean (review of 9e04ff6).
    const opLabel = comb ? COMBINER_LABEL[comb.op] : 'new';
    el('Op').value = [...el('Op').options].some(o => o.value === opLabel) ? opLabel : 'new';
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
    beginSetup();
    isolateFor(f.id);                 // downstream waits for OK/Cancel
  }

  /* -------- R1: ONE answer drives every handle and the solid -------- */
  async function fetchPlan(extra = {}, quiet = false) {
    const i = st.input;
    const req = i.kind === 'face'
      ? { tool: spec.tool, body_id: i.body, face_center: i.center, face_normal: i.normal,
          face_area: i.area == null ? null : i.area,
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
  function beginSetup(closeOnRefusal) {
    setupWait = setupTool(closeOnRefusal).catch(() => {});
    return setupWait;
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
    if (plan.click) speakClick(plan, 0);        // the pick that opened the tool was a click too
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
    // a feature tool's body is the plan's: the seed body's current state;
    // a MULTI-INPUT tool (Loft's sections) names its own list
    const inputs = spec.inputs ? spec.inputs(st)
      : [i.kind === 'profile' ? i.id
         : i.kind === 'feature' ? (st.plan && st.plan.input) || i.body : i.body];
    st.inputsPushed = JSON.stringify(inputs);
    return await post('/api/feature/add', {
      id: st.featureId, op: spec.ops[i.kind === 'profile' ? 'profile' : i.kind],
      params: pr, inputs });
  }
  /* a value the user never changed goes back as the FORMULA it came from: the
     number the panel opened on (original — also what a revert pushes) or
     what its untouched box reads back as (see openEdit) */
  function keepFormulas(pr, s = st) {
    const fm = (s && s.formulas) || {};
    const out = { ...pr };
    for (const [k, formula] of Object.entries(fm))
      if (k in out && (out[k] === s.original[k] || (s.shownBack && out[k] === s.shownBack[k])))
        out[k] = formula;
    return out;
  }
  async function push(pr) {             // one param set → the feature's health
    st.touched = true;                  // the ONLY writer in edit mode (see cancelSession)
    const doc = await post('/api/feature/params',
      { feature_id: st.featureId, params: st.editing ? keepFormulas(pr) : pr });
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
      // A param with no box of its own lives in the PLAN (Shell's set of open
      // faces, Mirror's plane), so show() cannot put it back — and the very
      // next apply() read it from the stale plan and pushed the values the
      // revert had just undone, which for Shell was an endless revert loop
      // (review of fb0b8c8). The revert restores the whole state the good
      // values came from, gizmos included.
      if (st.lastGoodPlan) st.plan = st.lastGoodPlan;
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
    // 'strict' = that ONE node. The default delete REPAIRS the tree: a cut
    // takes its tool prism and the prism's SKETCH with it (Document
    // _orphan_sweep), so switching Cut to Join here deleted the user's sketch
    // and the very feature this session is editing (2026-09-08, found when
    // Extrude began to follow the drag direction). The combiner is this
    // session's own tail; nothing depends on it.
    if (st.opId && (op === 'new' || st.opType !== op || st.opTarget !== target)) {
      await post('/api/feature/remove', { feature_id: st.opId, mode: 'strict' });
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
    // NOTHING IS BUILT BEFORE THE PLAN LANDS (R2). Every geometric fact a new
    // feature needs is the plan's — Hole's point on the face, Fillet's stored
    // edges, Mirror's plane, Pattern's seed and axis — so creating one without
    // it asks the op to build from nulls. The values already in the boxes are
    // not lost: adoptPlan applies them the moment the plan arrives, and OK
    // waits for one that is still in flight. Seven tools each typed this rule
    // into their own isEmpty as `!st.plan ||`, and each re-applied by hand in
    // their gizmos.begin; it belongs here, once, for every tool. An EDIT
    // already HAS its feature and its stored params, so it goes on writing.
    if (!st.featureId && !st.plan) return;
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
    // a MULTI-INPUT tool whose input LIST changed (Loft: a section added or
    // taken out): inputs are not a parameter, so the preview is made again
    // from the new list — its combiner goes and comes back with it (applyOp),
    // all inside the one document change the caller holds
    if (st.featureId && !st.editing && spec.inputs
        && JSON.stringify(spec.inputs(st)) !== st.inputsPushed) await unbuild();
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
      f = settled.f;
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
      // eslint-disable-next-line no-unmodified-loop-condition -- hide() sets st = null during the await
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
    // one node each, in order (see applyOp): Cancel on a Cut session must
    // leave the SKETCH the user drew before the tool was ever opened
    if (st.opId) await post('/api/feature/remove', { feature_id: st.opId, mode: 'strict' });
    await post('/api/feature/remove', { feature_id: st.featureId, mode: 'strict' });
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
      const { featureId, touched } = st;   // ORIGINAL params back verbatim,
      const original = keepFormulas(st.original);   // formulas as formulas
      hide();
      await holdViewport(async () => {
        // ...but only if the session ever wrote. `push` is the only writer in
        // edit mode, so with nothing written the restore is a no-op — except
        // that `original` is a NORMALIZED snapshot, so writing it added keys
        // the feature never had (a legacy move `{z: 5}` came back `{x: 0,
        // y: 0, z: 5}`) and the design went dirty from opening a panel and
        // pressing Cancel. Review of 9e04ff6.
        if (touched)
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
    let created = false, gone = false, held = null, failed = null, comboBad = null;
    // OK COMMITS the panel's values even if the user never dragged or touched
    // an input, typed inside the debounce window, or pressed OK while a
    // rebuild was still running — in edit mode too. The commit and the one
    // full rebuild (rollback bar released) are ONE change for the viewport.
    await holdViewport(async () => {
      // THE PLAN MAY STILL BE IN FLIGHT. Press the tool, type a value, press
      // OK: nothing can be built until the plan lands (see applyOnce), so OK
      // waits for it — and for the apply its arrival starts — instead of
      // saying "nothing was built" about a value the user did type (R2).
      if (setupWait) await setupWait;
      if (st && (editing || !st.featureId || typed || applyRun)) await apply();
      if (!st) { gone = true; return; }   // the server crashed under us, and
      created = !!st.featureId;           // recover() already said so
      held = st.heldWhy;                  // nothing built, and the tool knows why
      // the FIRST values the kernel refused leave a red row with nothing good
      // to revert to (a new mirror whose first plane throws the image off the
      // body): OK must say so, not "created" (P4 review)
      const f = created && feats().find(x => x.id === st.featureId);
      failed = f && f.status === 'failed' ? f : null;
      // ...and the COMBINER this session added. A cut deep enough to eat the
      // whole body leaves the tool's own feature perfectly green, so OK said
      // "created" over an EMPTY viewport (measured 2026-09-11: push a 20 mm
      // plate's top face in by 30 — extrude_face ok at 72 000 mm3, the cut
      // failed, 0 bodies on screen, "Extrude created"). The tree's own toast
      // already names the red row; OK may not contradict it. Reachable in one
      // gesture since an inward face pull became a Cut by itself.
      const c = created && st.opId && feats().find(x => x.id === st.opId);
      comboBad = c && c.status === 'failed' ? c : null;
      hide();
      await releaseIso();
    });
    releaseModal();
    if (gone) return;        // OK must not claim a step the crash threw away
    const outcome = failed
      ? `${spec.name} was NOT built — ${humanProblem((failed.problems || [])[0] || 'the kernel refused it')}. ` +
        'Its row is red in the feature tree: double-click it to change the values, or ✕ to remove it.'
      : comboBad
        ? `${spec.name} was built, but the ${OP_WORD[comboBad.op] || comboBad.op} after it was NOT — ` +
          `${humanProblem((comboBad.problems || [])[0] || 'the kernel refused it')}. ` +
          `The red row '${comboBad.id}' is in the feature tree: double-click it to change the ` +
          'values, or ✕ to remove it.'
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
  /* the document on screen became ANOTHER design (see the bus handler above).
     Nothing is posted on the way out: every write this session could make
     would land in that other design. */
  function tabMoved(doc) {
    if (!st || !st.tab || !doc || !doc.active_tab
        || doc.active_tab === st.tab) return;
    clearTimeout(timer); timer = null;  // a typed value on its way is dropped
    const parked = isoActive;
    isoActive = false; isoPending = null;   // that bar is in the OTHER design now
    const built = st.featureId, home = st.docName;
    hide();
    releaseModal();
    say(`⚠ ${spec.name} let go: "${doc.name}" became the design on screen while ` +
      'its panel was open, and a panel writes to whatever design is in front — so ' +
      `nothing was written to either. ${home ? `"${home}"` : 'Your design'} is as ` +
      `it was${built ? `, with ${built} in its tree as far as it got` : ''}` +
      `${parked ? ', and its rollback bar still parked' : ''}: switch back to it ` +
      `and press ${spec.name} again.`);
  }

  function init() {
    el('Profile').onchange = changeProfile;
    // a touched Operation box is the user's choice: a tool's own default
    // (Extrude follows the drag direction) stops overriding it
    el('Op').onchange = () => { if (st) st.opUser = true; sync(); apply(); };
    for (const s of ['Target', ...(spec.fields.change || [])])
      el(s).onchange = () => { sync(); if (spec.refresh) spec.refresh(st); apply(); };
    for (const s of spec.fields.typed || [])
      el(s).oninput = () => debounce(apply);
    el('Cancel').onclick = cancel;
    el('Ok').onclick = ok;
  }

  return ctl;
}
