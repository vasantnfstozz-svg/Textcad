// tree.js — the feature tree panel: Fusion-style rows, inline editing,
// suppress/delete/rollback actions, the spec verdict, and the status bar.

import { bus } from './bus.js';
import { askConfirm } from './ask.js';
import { S } from './state.js';
import { postJSON, getJSON, askJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { showFeatureOverlay, clearHighlight, clearPick }
  from './viewport.js';
import { modalGuard } from './dialogs.js';
import { openExtrude } from './extrude.js';
import { openRevolve } from './revolve.js';
import { openSweep } from './sweep.js';
import { openLoft } from './loft.js';
import { activeToolFeature, canEdit, editFeature, humanProblem } from './tool.js';
import { editOffsetPlane } from './sketchplane.js';
import { fmtVol } from './settings.js';

const treeEl = () => document.getElementById('tree');

/* Booleans that ride on their tool's row (see renderDoc). Anything that wants
   to point AT a feature has to ask this first: a folded boolean has no row of
   its own, and face->feature attribution answers with exactly those ids, so
   without this a picked pocket face highlighted nothing at all. */
const FOLDED = {};
export const rowFor = fid => FOLDED[fid] || fid;


/* ---------------- find (filter) ----------------
   The dimensions in this tree were already editable; what was missing was any
   way to LOCATE one. esp32-remote has 79 features with names like
   `esp_pilots_sketch`, so "the hole in that pillar" meant scrolling and
   guessing. This matches feature ids, ops, parameter names and their values,
   and the shapes inside a sketch — type "hole", "pilot", "3" or "circle".

   A node stays visible when it matches OR when anything nested under it does,
   so a match is never hidden by a parent that did not match. */
let findQ = '';

/* The user thinks "hole"; the design says "pilots". Searching only the literal
   names found nothing, which is the vocabulary gap behind "without much
   effort". These synonyms come from STRUCTURE, not a word list: a circle is a
   hole when something cuts with it, a cut is a pocket, a sketch feeding an
   extrude is a profile. */
function synonyms(f) {
  const out = [];
  if (f.op === 'cut') out.push('hole', 'pocket', 'remove', 'subtract');
  if (f.op === 'fuse') out.push('join', 'add', 'boss');
  if (f.op === 'extrude') out.push('height', 'depth', 'thickness', 'boss',
                                   'pillar');
  if (f.op === 'sketch') out.push('profile', 'shape');
  for (const e of (f.params || {}).entities || []) {
    if (e.kind === 'circle') out.push('hole', 'bore', 'round', 'dia');
    if (e.kind === 'rectangle') out.push('square', 'slot', 'box');
    if (e.kind === 'slot') out.push('slot', 'oval');
  }
  return out;
}

function haystack(f) {
  const bits = [f.id, f.op, ...synonyms(f)];
  for (const [k, v] of Object.entries(f.params || {})) {
    bits.push(k);
    if (Array.isArray(v) && k === 'entities') {
      for (const e of v) {
        bits.push(e.kind || '');
        for (const [ek, ev] of Object.entries(e)) {
          if (typeof ev === 'number' || typeof ev === 'string') {
            bits.push(ek, String(ev));
            if (/(^|_)r$|radius/i.test(ek) && typeof ev === 'number') {
              bits.push('diameter', String(round4(ev * 2)));   // people type Ø
            }
          }
        }
      }
    } else if (typeof v === 'number' || typeof v === 'string'
               || typeof v === 'boolean') {
      bits.push(String(v));
      if (/(^|_)r$|radius/i.test(k) && typeof v === 'number') {
        bits.push('diameter', String(round4(v * 2)));
      }
    }
  }
  return bits.join(' ').toLowerCase();
}

export function applyTreeFilter(q) {
  findQ = (q || '').trim().toLowerCase();
  const box = document.getElementById('treeFind');
  if (box) box.classList.toggle('on', !!findQ);
  const el = treeEl();
  el.querySelectorAll('.findnone').forEach(n => n.remove());
  const nodes = [...el.querySelectorAll('.node[data-fid]')];
  if (!findQ) {
    nodes.forEach(n => n.classList.remove('nomatch', 'hit'));
    return;
  }
  const byId = new Map((S.lastDoc?.features || []).map(f => [f.id, f]));
  const hit = new Set();
  for (const n of nodes) {
    const f = byId.get(n.dataset.fid);
    if (f && haystack(f).includes(findQ)) hit.add(n);
  }
  let shown = 0;
  for (const n of nodes) {
    const self = hit.has(n);
    const deep = self || [...n.querySelectorAll('.node[data-fid]')]
      .some(c => hit.has(c));
    n.classList.toggle('nomatch', !deep);
    n.classList.toggle('hit', self);
    if (self) {
      shown++;
      n.classList.add('open');            // a hit opens so its rows are visible
      S.openNodes.add(n.dataset.fid);
    }
  }
  if (!shown) {
    const p = document.createElement('div');
    p.className = 'findnone';
    p.textContent = `Nothing matches "${q}".`;
    el.appendChild(p);
  }
}

export function initTreeFind() {
  const inp = document.getElementById('treeFilter');
  if (!inp) return;
  inp.oninput = () => applyTreeFilter(inp.value);
  inp.onkeydown = e => {
    if (e.key === 'Escape') { inp.value = ''; applyTreeFilter(''); inp.blur(); }
    e.stopPropagation();          // Del/arrows here must not drive the tree
  };
  document.getElementById('treeFilterX').onclick = () => {
    inp.value = ''; applyTreeFilter(''); inp.focus();
  };
}

export function renderDoc(doc) {
  S.lastDoc = doc;
  arcKindsFor(doc.name);
  document.getElementById('docTitle').innerHTML = `<b>${doc.name}</b>`;
  document.getElementById('sDoc').innerHTML = `<b>${doc.name}</b>`;
  document.getElementById('featCount').textContent =
    doc.features.length ? doc.features.length + ' features' : '';
  document.getElementById('sFeatures').textContent =
    doc.features.length + ' features';
  // the RESULT body's volume, as the document works it out — not "the last
  // non-suppressed row", which is a sketch on a design that ends with one
  // (the readout went blank) and a stray tool body on one that ends with
  // that (it reported the tool's volume as the part's). R1.
  document.getElementById('sVolume').textContent =
    doc.result_volume != null ? 'volume ' + fmtVol(doc.result_volume) : '';
  document.getElementById('sRebuild').textContent =
    doc.rebuild_ms != null ? 'rebuild ' + doc.rebuild_ms + ' ms' : '';

  const badge = document.getElementById('verifyBadge');
  const nWarn = (doc.warnings || []).length;
  if (!doc.features.length) { badge.className = 'none'; badge.textContent = 'empty'; }
  else if (doc.ok && doc.result_pieces > 1) {
    // the part fell into pieces: green tick, but SAY it (reducing an extrude
    // until a boss floats used to read as "it created a new body")
    badge.className = 'warn';
    badge.textContent = `✓ built — ${doc.result_pieces} separate pieces`;
    badge.title = (doc.warnings || []).join('\n');
  }
  else if (doc.ok && doc.bodies > 1) {
    // separate bodies are NORMAL (Fusion's Bodies folder) — say how many,
    // don't cry "stray". Counted from the document now: it used to be
    // "warnings + 1", so an unrelated note made the badge claim 13 bodies.
    badge.className = 'ok';
    badge.textContent = `✓ verified — ${doc.bodies} bodies`;
    badge.title = (doc.warnings || []).join('\n');
  }
  else if (doc.ok && nWarn) {
    badge.className = 'ok';
    badge.textContent = '✓ verified';
    badge.title = doc.warnings.join('\n');
  }
  else if (doc.ok) { badge.className = 'ok'; badge.textContent = '✓ verified'; badge.title = ''; }
  else { badge.className = 'fail'; badge.textContent = '✗ check failed'; badge.title = ''; }

  const el = treeEl();
  el.innerHTML = '';
  // rolled-back marking follows BUILD order (the features list), independent
  // of how the rows are nested for display below
  const rolled = new Set();
  {
    let past = false;
    for (const f of doc.features) {
      if (past) rolled.add(f.id);
      if (doc.rollback === f.id) past = true;
    }
  }
  // Fusion grouping: a sketch and the feature that consumed it render as ONE
  // group, not two sibling rows — the tree then reads as design history, not
  // a flat op list. The SKETCH owns the group row and its consumer nests
  // underneath (user mandate 2026-08-27: "first sketch and then extrude below
  // that"), because that is the order the part was actually built in.
  const isSk = f => f.op === 'sketch' || f.op === 'sketch_on_face';

  /* Fusion shows an extrude with a Cut operation as ONE timeline entry. Our
     tree stores it as three features — sketch, tool prism, boolean — and the
     boolean's own row was both redundant and misleading: clicking it selected
     the WHOLE body, because its output IS the whole body (user, 2026-08-26:
     "if i am clicking the third whole body is being selected, i dont need the
     third one").

     So the boolean folds into its tool's row as a chip. The feature itself
     stays exactly where it was — it is what actually applies the pocket, and
     deleting the row still removes the whole group — but the tree now reads
     the way the user builds: sketch, then extrude. */
  const PULLED = new Set(['extrude', 'revolve', 'loft', 'sweep',
                          'extrude_face', 'revolve_face']);
  const foldedInto = FOLDED;    // boolean id -> the tool row it rides on
  for (const k of Object.keys(foldedInto)) delete foldedInto[k];
  const chipOn = {};            // tool id -> the boolean it applies
  for (const f of doc.features) {
    if (!['cut', 'fuse', 'intersect'].includes(f.op)) continue;
    if ((f.inputs || []).length !== 2) continue;      // 3-input cut: ambiguous
    const tool = doc.features.find(x => x.id === f.inputs[1]);
    if (!tool || !PULLED.has(tool.op)) continue;
    // only if that tool feeds NOTHING else — otherwise it is shared geometry
    const others = doc.features.filter(
      x => x.id !== f.id && (x.inputs || []).includes(tool.id));
    if (others.length) continue;
    foldedInto[f.id] = tool.id;
    chipOn[tool.id] = f;
  }

  const consumerOf = {};        // sketch id -> the feature that consumed it
  for (const f of doc.features)
    for (const d of f.inputs) {
      const src = doc.features.find(x => x.id === d);
      if (src && isSk(src) && !(d in consumerOf)) consumerOf[d] = f.id;
    }
  // consumer id -> its sketches, in build order. A loft eats two sketches, so
  // the consumer hangs under the LAST of them and both sketches keep a row.
  const sketchesOf = {};
  for (const [skId, consId] of Object.entries(consumerOf))
    (sketchesOf[consId] = sketchesOf[consId] || []).push(skId);
  const makeNode = (f, child) => {
    const node = document.createElement('div');
    node.dataset.fid = f.id;
    const hasKids = Object.keys(f.params).length > 0 || f.volume != null;
    node.className = 'node' + (S.openNodes.has(f.id) ? ' open' : '')
      + (f.suppressed ? ' suppressed' : '')
      + (S.selected === f.id ? ' sel' : '')
      + (rolled.has(f.id) ? ' rolledback' : '')
      + (hasKids ? ' haskids' : '') + (child ? ' child' : '');
    node.appendChild(buildRow(doc, f, chipOn[f.id] || null));
    node.appendChild(buildBody(f));
    // '(after rollback bar)' is edit-isolation plumbing, not a user problem —
    // the dimmed row already says "not built right now"
    const own = chipOn[f.id] ? (chipOn[f.id].problems || []) : [];
    const probs = [...f.problems, ...own]
      .filter(p => p !== '(suppressed)' && p !== '(after rollback bar)')
      .map(humanProblem);
    if (probs.length) {
      const pd = document.createElement('div'); pd.className = 'nproblems';
      pd.textContent = probs.join(' • '); node.appendChild(pd);
    }
    el.appendChild(node);
  };
  const done = new Set();
  for (const f of doc.features) {
    if (foldedInto[f.id]) continue;          // rides on its tool's row
    if (done.has(f.id)) continue;            // already nested under its sketch
    makeNode(f, false);
    // a sketch owns the row; its consumer nests below it (once its LAST
    // sketch has been drawn, so a loft does not appear twice)
    const cons = consumerOf[f.id];
    if (!cons) continue;
    const sibs = sketchesOf[cons] || [];
    if (sibs[sibs.length - 1] !== f.id) continue;   // wait for the last one
    const cf = doc.features.find(x => x.id === cons);
    if (cf && !foldedInto[cf.id]) { makeNode(cf, true); done.add(cf.id); }
    else if (cf) done.add(cf.id);
  }
  renderWarnings(doc, el);
  renderSpecRow(doc, el);
  if (findQ) applyTreeFilter(findQ);
}
bus.on('doc-updated', renderDoc);
bus.on('settings-changed', () => { if (S.lastDoc) renderDoc(S.lastDoc); });

/* Failures speak (Fusion parity rule 7): the moment a feature NEWLY fails,
   say so in chat in human words — never just the little red dot. The extrude
   panel's live feature is excluded: that tool already explains and auto-
   repairs its own failures. */
let prevFailed = new Set();
bus.on('doc-updated', doc => {
  const failed = new Map();
  for (const f of doc.features)
    if (f.status === 'failed' && !f.problems.includes('(after rollback bar)'))
      failed.set(f.id, f);
  for (const [id, f] of failed)
    if (!prevFailed.has(id) && id !== activeToolFeature())
      bus.emit('msg', 'bot', failMessage(f));
  prevFailed = new Set(failed.keys());
});

function failMessage(f) {
  const probs = f.problems.filter(p => p !== '(suppressed)').map(humanProblem);
  return `⚠ Feature "${f.id}" (${f.op}) failed to build: ` +
         `${probs.join('; ')} — click it in the tree to adjust it, or ✕ to ` +
         `delete it (whatever depends on it is reconnected).`;
}

function renderWarnings(doc, el) {
  if (!doc.warnings || !doc.warnings.length) return;
  // neutral info styling — multiple bodies are a normal modeling state, and
  // the old amber ⚠ box made every boss/pocket-in-progress read as an error
  const w = document.createElement('div');
  w.style.cssText = 'margin:8px 6px;padding:7px 9px;border:1px solid var(--line);' +
    'background:rgba(120,140,170,.07);color:var(--dim);border-radius:6px;' +
    'font-size:11.5px;line-height:1.45';
  w.innerHTML = doc.warnings.map(t => `<div>ℹ ${t}</div>`).join('');
  el.appendChild(w);
}

function buildRow(doc, f, chip = null) {
  const row = document.createElement('div'); row.className = 'nrow';
  row.innerHTML = `
    <span class="twisty" title="expand">▶</span>
    <span class="nico">${OP_ICONS[f.op] || '□'}</span>
    <span class="nname">${f.id}</span>
    <span class="nop">${f.op}${f.inputs.length ? ' ← ' + f.inputs.join(', ') : ''}</span>
    <span class="nspacer"></span>`;
  if (chip) {
    // what this extrude DOES to the body it lands on — the folded boolean
    const c = document.createElement('span');
    c.className = 'nchip ' + chip.op;
    c.textContent = chip.op;
    c.title = `applied to the body by '${chip.id}' (${chip.op} ← ` +
      `${(chip.inputs || []).join(', ')}). Deleting this row removes both.`;
    row.querySelector('.nspacer').before(c);
  }
  row.querySelector('.twisty').onclick = e => {
    e.stopPropagation();
    S.openNodes.has(f.id) ? S.openNodes.delete(f.id) : S.openNodes.add(f.id);
    renderDoc(S.lastDoc);
  };

  // Fusion's browser rename: double-click the NAME itself (double-click
  // elsewhere on the row is Edit Feature)
  const nameEl = row.querySelector('.nname');
  nameEl.title = 'double-click to rename';
  nameEl.ondblclick = e => {
    e.stopPropagation();
    if (!modalGuard()) beginRename(nameEl, f);
  };

  const acts = document.createElement('span'); acts.className = 'nacts';
  if (f.suppressed) {
    // a struck-out row: the geometry is gone but the operation is one click
    // from coming back (user mandate 2026-08-31) — editing waits until then
    addAct(acts, '↩', 'restore this operation — the struck-out geometry ' +
      'comes back exactly as it was', () => restoreFeature(f.id));
    addAct(acts, '✕', 'delete permanently (removes the row; anything that ' +
      'must go with it is listed first)', () => deleteFeature(f.id));
  } else {
    if (f.op === 'sketch' || f.op === 'sketch_on_face') {
      addAct(acts, '✎', 'edit this sketch (reopens on its plane in the viewport)',
        () => bus.emit('edit-sketch', f));
    }
    if (f.op === 'offset_plane') {
      addAct(acts, '✎', 'move this plane (the arrow and Offset box reopen; every ' +
        'sketch on it follows)', () => editOffsetPlane(f));
    }
    // a PATH sketch (open lines, area 0 — the server says so: `path_sketch`)
    // is what Sweep FOLLOWS, never a profile: no pull buttons on its row
    if ((f.op === 'sketch' || f.op === 'sketch_on_face') && !f.path_sketch) {
      addAct(acts, '⬆', 'extrude this sketch into a solid',
        () => openExtrude(f.id));
      addAct(acts, '↻', 'revolve this sketch into a solid',
        () => openRevolve(f.id));
      addAct(acts, '〜', 'sweep this sketch along a path sketch',
        () => openSweep(f.id));
      addAct(acts, '⏢', 'loft this sketch with other profiles',
        () => openLoft(f.id));
    }
    if (canEdit(f.op)) {
      // Edit Feature (Fusion parity): reopen the tool that CREATED the feature
      addAct(acts, '✎', `edit this ${f.op.replace('_', ' ')} (reopens the tool ` +
        'that made it, with its handles and live preview)', () => editFeature(f.id));
    }
    // ✕ is a SOFT delete now: the geometry goes, the row stays struck out,
    // and ↩ brings it back (user mandate 2026-08-31). Permanent delete lives
    // on the struck row.
    addAct(acts, '✕', 'strike out this feature — the geometry is removed ' +
      'but the row stays; ↩ brings it back, ✕ again deletes for good',
      () => strikeFeature(f.id));
  }

  const worst = chip && chip.status === 'failed' ? 'failed' : f.status;
  const dot = document.createElement('span'); dot.className = 'ndot ' + worst;
  row.append(acts, dot);
  row.onclick = () => selectFeature(f.id);
  // Fusion's gesture: double-click a feature = edit it with its own tool
  row.ondblclick = () => {
    if (modalGuard()) return;
    if (f.suppressed) { restoreFeature(f.id); return; }   // dblclick = bring it back
    if (f.op === 'sketch' || f.op === 'sketch_on_face') bus.emit('edit-sketch', f);
    else if (f.op === 'offset_plane') editOffsetPlane(f);
    else if (canEdit(f.op)) editFeature(f.id);
  };
  return row;
}

// a tool that just MADE a feature makes it the selection (Offset Plane: the
// next Create Sketch lands on the new plane) — through selectFeature, so the
// row, the overlay and the one selection set all agree
bus.on('select-feature', fid => {
  if (fid == null) { if (S.selected) selectFeature(S.selected); }   // null = clear
  else if (S.selected !== fid) selectFeature(fid);
});

/* Soft delete (the tree's ✕): geometry removed, rows kept struck-out. No
   confirm dialog on purpose — the whole point is that it is one click to do
   and one click (↩ on the row) to take back. */
async function strikeFeature(fid) {
  const doc = await postJSON('/api/feature/strike', { feature_id: fid },
                             'striking out…');
  if (doc.error) return;
  // The ROW survives a strike (unlike a permanent delete), so the selection
  // survives with it — only the 3D highlight goes, because there is no
  // geometry left to highlight. Dropping the selection here made the Del key's
  // own second half unreachable: the handler says "Del again deletes for good"
  // and the second Del had nothing selected to act on (measured 2026-09-16).
  if (S.selected === fid) clearHighlight();
  const plan = doc.strike_plan;
  const also = plan && plan.deleted.filter(id => id !== fid);
  bus.emit('msg', 'bot', `Struck out "${fid}"` +
    (also && also.length ? ` (with ${also.join(', ')})` : '') +
    ' — the geometry is removed, the row stays. ↩ on the row brings it back.');
}

async function restoreFeature(fid) {
  const doc = await postJSON('/api/feature/strike',
    { feature_id: fid, restore: true }, 'restoring…');
  if (doc.error) return;
  const plan = doc.strike_plan;
  const also = plan && (plan.restored || plan.deleted).filter(id => id !== fid);
  bus.emit('msg', 'bot', `Restored "${fid}"` +
    (also && also.length ? ` (with ${also.join(', ')})` : '') +
    ' — the geometry is back.');
}

/* Fusion's browser Delete. The backend REPAIRS the history around the node
   (dependents reconnect to its upstream body), so a mid-tree sketch or extrude
   is deletable — it used to be refused with "used by [...]", which made every
   feature but the last permanent in an AI-authored tree. Whatever has to go
   WITH it is shown before anything changes (rule 7: never a silent surprise),
   and the whole delete is one undo step. */
export async function deleteFeature(fid) {
  const dry = await postJSON('/api/feature/remove',
    { feature_id: fid, dry_run: true }, 'checking dependencies…');
  const plan = dry.remove_plan;
  if (!plan) return;                 // postJSON already showed the error
  if (plan.deleted.length > 1) {
    const go = await askConfirm(`Delete ${plan.deleted.length} features?`, {
      body: plan.summary, ok: 'Delete', danger: true,
    });
    if (!go) return;
  }
  const doc = await postJSON('/api/feature/remove',
    { feature_id: fid }, 'deleting…');
  if (doc.error) return;
  if (S.selected === fid) { S.selected = null; clearHighlight(); }
  for (const id of plan.deleted) S.openNodes.delete(id);
  const applied = doc.remove_plan;
  if (applied && applied.deleted.length > 1)
    bus.emit('msg', 'bot', '\ud83d\uddd1 ' + applied.summary.replace(/^Delete /, 'Deleted ') +
      ' Undo (Ctrl+Z) puts it back.');
}

/* Del on the selected feature — the same gesture as Fusion's browser. Sketch
   mode owns Delete for sketch entities, so stay out of its way. */
let sketchOn = false;
bus.on('sketch-mode', ({ active }) => { sketchOn = active; });
window.addEventListener('keydown', e => {
  if (e.key !== 'Delete' || sketchOn || !S.selected) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (modalGuard()) return;
  e.preventDefault();
  // same gesture as the row's ✕: strike out first; Del again deletes for good
  const f = (S.lastDoc?.features || []).find(x => x.id === S.selected);
  if (f && f.suppressed) deleteFeature(S.selected);
  else strikeFeature(S.selected);
});

/* Reveal a feature the user did not click on: expand it, flash it, and scroll
   it into view. Used by provenance.js when a picked FACE is traced back to the
   feature that created it — on a 79-feature tree the row is usually far off
   screen, so highlighting without scrolling would highlight nothing the user
   can see.

   Deliberately does NOT touch S.selected: selection drives the tools (Modify ->
   Scale routes on the selected feature), and merely looking at a face must not
   re-aim them. */
export function revealFeature(fid, related = []) {
  const el = treeEl();
  if (!el) return null;
  for (const n of el.querySelectorAll('.node.fromface, .node.fromface-rel'))
    n.classList.remove('fromface', 'fromface-rel');
  if (!fid) return null;                    // null = just clear the marks
  fid = rowFor(fid);                        // a folded boolean has no row
  const node = el.querySelector(`.node[data-fid="${CSS.escape(fid)}"]`);
  for (const rid of related) {
    const r = rowFor(rid);
    if (r === fid) continue;
    const rn = el.querySelector(`.node[data-fid="${CSS.escape(r)}"]`);
    if (rn) rn.classList.add('fromface-rel');
  }
  if (!node) return null;
  node.classList.add('fromface');
  node.scrollIntoView({ block: 'center', behavior: 'smooth' });
  return node;
}

function addAct(parent, label, title, fn) {
  const b = document.createElement('button'); b.className = 'nact';
  b.textContent = label; b.title = title;
  b.onclick = e => { e.stopPropagation(); if (!modalGuard()) fn(); };
  parent.appendChild(b);
}

/* a stored form the user can read: {center: [0,0,6], normal: [0,0,1]} ->
   "center 0, 0, 6 · normal 0, 0, 1". A part that is ITSELF a form reads as its
   own parts in brackets — a fillet's stored edge carries `faces: [{center,
   normal}, ...]`, and joining that list wrote "[object Object]" straight into
   the tree on the user's live designs (round two of the review of fb0b8c8),
   which is the very thing the P4 review's rule forbids. */
const isNamedParts = v => !!v && typeof v === 'object' && !Array.isArray(v);
const readable = v => Array.isArray(v) ? v.map(readable).join(', ')
  : isNamedParts(v) ? `(${namedParts(v)})` : `${v}`;
const namedParts = v => Object.entries(v).map(([pk, pv]) =>
  `${pk} ${readable(pv)}`).join(' · ');

function buildBody(f) {
  const body = document.createElement('div'); body.className = 'nbody';
  for (const [k, v] of Object.entries(f.params)) {
    const pr = document.createElement('div'); pr.className = 'prow';
    pr.innerHTML = `<span class="pname">${k}</span>`;
    const val = document.createElement('span');
    if (typeof v === 'boolean') {          // real toggle — typing "false" into a
      val.className = 'pval';              // text edit reads as truthy in Python
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = v; cb.style.width = 'auto';
      cb.onclick = e => e.stopPropagation();
      cb.onchange = async () => {
        if (modalGuard()) { cb.checked = !cb.checked; return; }
        await postJSON('/api/edit', { feature_id: f.id, param: k, value: cb.checked });
      };
      val.appendChild(cb); pr.appendChild(val); body.appendChild(pr);
    } else if (typeof v === 'number' || typeof v === 'string') {
      val.className = 'pval';
      // a FORMULA (named parameters): the row reads `wall*2 = 6` — the value
      // is the server's (`resolved`), the text is what the user typed and
      // what the edit box opens on; a formula that does not work out reads
      // `wall*2 = ?` and the row's problem says why
      const formula = f.resolved && Object.hasOwn(f.resolved, k);
      val.textContent = formula ? `${v} = ${f.resolved[k] == null ? '?' : round4(f.resolved[k])}` : v;
      val.title = formula ? 'a formula — click to edit it; type a number or another formula'
        : 'click to edit — a number, or a formula such as wall*2';
      if (formula) val.classList.add('formula');
      val.onclick = e => {
        e.stopPropagation();
        if (!modalGuard()) beginEdit(val, f.id, k, v);
      };
      pr.appendChild(val); body.appendChild(pr);
      // a pillar's outer/inner size reads as a DIAMETER on any drawing, so
      // offer Ø next to every radius and write back radius = Ø / 2
      if (typeof v === 'number' && isRadius(k))
        body.appendChild(diameterRow(f.id, k, v));
    } else if (k === 'entities' && Array.isArray(v)) {
      // NEVER dump raw entity JSON (user, 2026-08-25: "we dont need see to
      // entities, and all"). Each shape gets its own dimension rows instead.
      body.appendChild(shapeList(f, v));
    } else if (k === 'axis' && Array.isArray(v) && v.length === 2 && Array.isArray(v[0])) {
      // a Revolve axis stored as a LINE in the sketch plane (P3b): shown, not
      // edited here — the Revolve tool's Axis list is where it changes (the
      // points editor below is for revolve_profile outlines; it would offer
      // ＋ / ✕ on the two points and break the axis)
      val.className = 'pro';
      val.textContent = `edge (${v[0].join(', ')}) → (${v[1].join(', ')})`;
      pr.appendChild(val); body.appendChild(pr);
    } else if (Array.isArray(v) && v.length && Array.isArray(v[0])) {
      body.appendChild(pr);                       // label row
      body.appendChild(pointsTable(f.id, k, v));  // editable table below
    } else {
      val.className = 'pro';
      // a stored form with named parts (Mirror's plane {mid: "X"} or a face
      // {face_center, face_normal}, a Pattern axis {origin, dir}) reads as its
      // parts, never as "[object Object]" (P4 review)
      // ...and a LIST of them (Shell's open faces) reads as one line each, not
      // as raw JSON — including the MIXED list a click on a second face makes,
      // since the planner keeps a stored NAME a name: ["top", {center, normal}]
      val.textContent = Array.isArray(v)
        ? (v.length && v.every(x => isNamedParts(x) || typeof x === 'string')
          ? v.map(x => isNamedParts(x) ? namedParts(x) : x).join(' ; ')
          : JSON.stringify(v))
        : isNamedParts(v) ? namedParts(v) : v;
      pr.appendChild(val); body.appendChild(pr);
    }
  }
  if (f.volume != null) {
    const pr = document.createElement('div'); pr.className = 'prow';
    pr.innerHTML = `<span class="pname">volume</span>
                    <span class="pro">${fmtVol(f.volume)}</span>`;
    body.appendChild(pr);
  }
  if (f.pieces > 1) {
    const pr = document.createElement('div'); pr.className = 'prow';
    pr.innerHTML = `<span class="pname">pieces</span>
      <span class="pro warnval" title="this feature's solid is in ${f.pieces}
      separate lumps — something does not touch the rest">${f.pieces}</span>`;
    body.appendChild(pr);
  }
  return body;
}

/* ---------------- shapes inside a sketch ----------------
   A sketch's `entities` used to render as a raw JSON dump — unreadable, and
   un-editable. Now every shape lists the dimensions it is actually defined by
   (rectangle -> width/height, circle -> radius + Ø, slot -> length/height),
   editable in place, so a square can be resized without opening the sketch
   editor at all. Shapes defined by a coordinate list (traced paths, polygons)
   cannot be sensibly typed as numbers, so they show a summary and a button
   into the sketch editor. */

let SHAPES = null;                  // /api/sketch/kinds, fetched once
async function shapeCatalog() {
  if (!SHAPES) {
    try {
      const got = await getJSON('/api/sketch/kinds');
      SHAPES = got && got.fields ? { ...got, ok: true } : null;
    } catch (e) { /* fall through */ }
    // A server older than this page has no /api/sketch/kinds. That must NOT
    // leave the user with shape cards that are empty except a dropdown (it
    // did, and it reads as "the tree is broken"). Fall back to the entity's
    // OWN numeric fields, with raw key names, and say why.
    if (!SHAPES) SHAPES = { ok: false, fields: {}, common: [], diameter: {},
                            geometry: {} };
  }
  return SHAPES;
}
// warm it up at boot AND re-render once it lands: the first paint can happen
// before the fetch returns, and a shape card with no catalog has no rows
shapeCatalog().then(() => { if (S.lastDoc) renderDoc(S.lastDoc); });

const isRadius = k =>
  /(^|_)r$|radius/i.test(k) && !/pitch_circle/i.test(k);

function diameterRow(fid, param, radius) {
  const pr = document.createElement('div');
  pr.className = 'prow dia';
  pr.innerHTML = `<span class="pname">Ø ${param.replace(/radius/i, '')
    .replace(/[_ ]+$/, '') || 'dia'}</span>`;
  const val = document.createElement('span');
  val.className = 'pval';
  val.textContent = round4(radius * 2);
  val.title = 'diameter — click to edit (sets the radius to half of it)';
  val.onclick = e => {
    e.stopPropagation();
    if (modalGuard()) return;
    beginEditWith(val, radius * 2, async d => {
      await postJSON('/api/edit',
        { feature_id: fid, param, value: round4(d / 2) });
    });
  };
  pr.appendChild(val);
  return pr;
}

function round4(n) { return Math.round(n * 10000) / 10000; }

function shapeList(feat, entities) {
  const box = document.createElement('div');
  box.className = 'shapes';
  const cat = SHAPES || { fields: {}, common: [], diameter: {}, geometry: {} };

  entities.forEach((ent, i) => {
    const kind = ent.kind || '?';
    const card = document.createElement('div');
    card.className = 'shape';

    const head = document.createElement('div');
    head.className = 'shead';
    head.innerHTML = `<span class="sidx">${i + 1}</span>` +
      `<span class="skind">${kind.replace(/_/g, ' ')}</span>`;
    head.appendChild(modeToggle(feat, entities, i));
    card.appendChild(head);

    const known = cat.ok && cat.fields[kind];
    // a WORD first (a text entity's `text`): edited as text, not as a number
    for (const f of (known && cat.strings && cat.strings[kind]) || [])
      if (ent[f.key] !== undefined)
        card.appendChild(entTextRow(feat, entities, i, f.key, f.label));
    const dims = known ? cat.fields[kind] : genericFields(ent);
    for (const f of dims)
      if (ent[f.key] !== undefined)
        card.appendChild(entRow(feat, entities, i, f.key, f.label, f.unit));

    // Ø for round shapes, right under the radius
    const dkey = known ? (cat.diameter || {})[kind] : genericRadius(ent);
    if (dkey && typeof ent[dkey] === 'number')
      card.appendChild(entRow(feat, entities, i, dkey, 'Ø diameter', 'mm',
                              2));

    for (const f of (known ? (cat.common || []) : GENERIC_COMMON))
      if (ent[f.key] !== undefined)
        card.appendChild(entRow(feat, entities, i, f.key, f.label, f.unit));

    // every CURVE of a path gets an editable radius ("wherever we have a
    // curve, it should be there in the tree" — user, 2026-08-31)
    if (kind === 'path')
      for (const row of pathArcRows(feat, entities, i)) card.appendChild(row);

    const gkey = known ? (cat.geometry || {})[kind] : genericGeometry(ent);
    if (gkey) card.appendChild(geometryNote(feat, ent, gkey));

    box.appendChild(card);
  });
  if (!entities.length) {
    const none = document.createElement('div');
    none.className = 'shempty';
    none.textContent = 'no shapes in this sketch';
    box.appendChild(none);
  } else if (cat.ok === false) {
    box.appendChild(staleCatalogNote());     // failures speak (rule 7)
  }
  return box;
}

/* ---- working without the catalog ----
   Everything above prefers /api/sketch/kinds (labels live next to the geometry
   that reads them). When that endpoint is missing — a server started before it
   existed — we still show every numeric field the shape actually has, under its
   raw key name, so dimensions stay editable instead of vanishing. */

const GENERIC_SKIP = new Set(['kind', 'mode', 'x', 'y', 'rotation']);
const GENERIC_COMMON = [{ key: 'x', label: 'x', unit: 'mm' },
                        { key: 'y', label: 'y', unit: 'mm' },
                        { key: 'rotation', label: 'angle', unit: 'deg' }];

function genericFields(ent) {
  return Object.keys(ent)
    .filter(k => !GENERIC_SKIP.has(k) && typeof ent[k] === 'number')
    .map(k => ({ key: k, label: k, unit: '' }));
}

function genericRadius(ent) {
  for (const k of ['r', 'radius'])
    if (typeof ent[k] === 'number') return k;
  return null;
}

function genericGeometry(ent) {
  for (const k of ['segments', 'points'])
    if (Array.isArray(ent[k])) return k;
  return null;
}

function staleCatalogNote() {
  const d = document.createElement('div');
  d.className = 'shstale';
  d.textContent = 'raw field names — restart the server (studio.py) for '
    + 'labelled dimensions like width / Ø diameter';
  return d;
}

/* ---- path arc radii ----
   A path's curves are stored as 3-POINT ARCS — no radius number exists in
   the JSON, which is why curves used to be invisible in the tree. These rows
   compute the radius for display and hand edits to the backend solver
   (/api/sketch/arc-radius): a corner arc re-fillets tangent to its
   neighbouring lines, a free arc re-bulges between its fixed endpoints.
   The rewritten entities then go through the normal /api/edit path, so
   undo and the rebuild come for free. */

function circumR(a, b, c) {
  const d = 2 * Math.abs((b[0] - a[0]) * (c[1] - a[1])
                       - (b[1] - a[1]) * (c[0] - a[0]));
  if (d < 1e-9) return null;                    // collinear: not a real arc
  const l = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);
  return l(b, c) * l(a, c) * l(a, b) / d;
}

/* Corner-vs-arc is the BACKEND's answer (R1), not something the tree works
   out. It used to: `prev = j > 0 ? segs[j-1].type : 'close'` reads segment 0's
   predecessor as the auto-close line, but on a CLOSED path the real neighbour
   is the LAST segment — so two arcs meeting at the start were both called
   "corner"s and both promised "the round stays tangent to its edges", which
   `set_arc_radius` then does not do: it takes the free-arc branch and just
   re-bulges (code review 2026-09-09). /api/sketch/path-arcs runs the very
   function the edit acts on, so the row and the edit cannot disagree.

   The radius itself stays local — that is plain geometry off three points,
   with no neighbour to get wrong. Only the LABEL waits for the server, and
   until it lands the row says "curve" and promises nothing. */
const arcKinds = new Map();          // "<featId>:<entIdx>:<segIdx>" -> kind
const arcKindsSeen = new Map();      // featId -> the entity list it describes
const arcKindsFlight = new Set();    // "<featId> <entities>" asked, not back
let arcKindsDoc = null;              // which design those two describe

/* Feature ids are unique inside ONE document, so `sketch3` in a second open
   tab read the first tab's answer, and neither map ever shrank (second code
   review, 2026-09-09). Both are a cache of one design's labels: when the
   design on screen changes, they are simply not about it any more. */
function arcKindsFor(name) {
  if (arcKindsDoc === name) return;
  arcKindsDoc = name;
  arcKinds.clear();
  arcKindsSeen.clear();
}

function paintArcKind(pr) {
  const kind = arcKinds.get(pr.dataset.arckind);
  const j = Number(pr.dataset.arckind.split(':').pop());
  const corner = kind === 'corner';
  pr.querySelector('.pname').textContent = `${kind || 'curve'} ${j + 1} R`;
  pr.querySelector('.pval').title = 'click to edit the radius'
    + (corner ? ' — the round stays tangent to its edges' : '');
}

async function loadArcKinds(feat, entities) {
  // The key is stored only once the answer is IN. Set before the await, a
  // single failed fetch (a supervisor relaunch mid-render) pinned the row at
  // its fallback "curve N R" label until the entities themselves changed
  // (second code review, 2026-09-09).
  const key = stableEntities(entities);
  if (arcKindsSeen.get(feat.id) === key) return;
  // ONE request per render, without going back to keying before the await:
  // pathArcRows calls this once per path entity, so a sketch with N of them
  // fired N identical POSTs, each carrying the whole entity list (third code
  // review, 2026-09-09). The in-flight key is dropped again the moment the
  // answer — or the failure — lands, so nothing stays pinned.
  const flight = `${feat.id}\u0000${key}`;
  if (arcKindsFlight.has(flight)) return;
  arcKindsFlight.add(flight);
  // Which design this answer is about. Without it, a reply that lands after
  // the user switched designs repainted the NEW design's rows: the selector
  // below matches on feature id alone, and ids like `sketch1` are unique only
  // within one document, so a free curve got a `corner` label and the
  // tangency promise the backend will not keep (third code review).
  const forDoc = arcKindsDoc;
  let res;
  try {
    res = await askJSON('/api/sketch/path-arcs', { entities });
  } finally {
    arcKindsFlight.delete(flight);
  }
  if (arcKindsDoc !== forDoc) return;
  if (res.error || !res.arcs) return;
  arcKindsSeen.set(feat.id, key);
  for (const [ei, arcs] of Object.entries(res.arcs))
    for (const a of arcs) arcKinds.set(`${feat.id}:${ei}:${a.segment}`, a.kind);
  for (const pr of document.querySelectorAll(
      `[data-arckind^="${CSS.escape(feat.id)}:"]`)) paintArcKind(pr);
}

function stableEntities(entities) {
  try { return JSON.stringify(entities); } catch { return String(Date.now()); }
}

function pathArcRows(feat, entities, i) {
  const ent = entities[i];
  const segs = ent.segments || [];
  const rows = [];
  let cur = ent.start || [0, 0];
  segs.forEach((s, j) => {
    const from = cur;
    cur = s.to || cur;
    if (s.type !== 'arc' || !s.via || !s.to) return;
    const r = circumR(from, s.via, s.to);
    if (r == null) return;
    const pr = document.createElement('div');
    pr.className = 'prow';
    pr.dataset.arckind = `${feat.id}:${i}:${j}`;
    pr.innerHTML = '<span class="pname"></span>';
    const val = document.createElement('span');
    val.className = 'pval';
    val.textContent = round4(r);
    val.onclick = e => {
      e.stopPropagation();
      if (modalGuard()) return;
      beginEditWith(val, round4(r), async v => {
        const res = await postJSON('/api/sketch/arc-radius',
          { entities, entity: i, segment: j, radius: v }, 'solving radius…');
        if (res.error || !res.entities) return;  // postJSON spoke already
        await postJSON('/api/edit',
          { feature_id: feat.id, param: 'entities', value: res.entities });
      });
    };
    pr.appendChild(val);
    paintArcKind(pr);              // whatever the last answer said, if anything
    rows.push(pr);
  });
  if (rows.length) loadArcKinds(feat, entities);    // patches in when it lands
  return rows;
}

/* one editable dimension of one shape. `factor` renders value*factor and
   divides on the way back (that is all a diameter is). */
function entRow(feat, entities, i, key, label, unit, factor = 1) {
  const pr = document.createElement('div');
  pr.className = 'prow' + (factor !== 1 ? ' dia' : '');
  pr.innerHTML = `<span class="pname">${label}</span>`;
  const raw = entities[i][key];
  const shown = typeof raw === 'number' ? round4(raw * factor) : raw;
  const val = document.createElement('span');
  val.className = 'pval';
  val.textContent = shown;
  val.title = `click to edit${unit && unit !== 'count' ? ' (' + unit + ')' : ''}`;
  val.onclick = e => {
    e.stopPropagation();
    if (modalGuard()) return;
    beginEditWith(val, shown, v => applyEntity(feat, entities, i, key,
                                               factor === 1 ? v : v / factor));
  };
  pr.appendChild(val);
  return pr;
}

/* a STRING field of a shape (a text entity's word): the same inline edit as
   the numbers, but the value is kept as typed — beginEditWith would refuse
   anything that is not a number */
function entTextRow(feat, entities, i, key, label) {
  const pr = document.createElement('div');
  pr.className = 'prow';
  pr.innerHTML = `<span class="pname">${label}</span>`;
  const val = document.createElement('span');
  val.className = 'pval';
  val.textContent = entities[i][key];
  val.title = 'click to edit';
  val.onclick = e => {
    e.stopPropagation();
    if (modalGuard()) return;
    const old = String(entities[i][key]);
    const input = document.createElement('input');
    input.value = old;
    val.replaceChildren(input); input.focus(); input.select();
    let done = false;
    const finish = async ok => {
      if (done) return; done = true;
      const raw = input.value.trim();
      if (!ok || raw === '' || raw === old) { val.textContent = old; return; }
      await applyEntity(feat, entities, i, key, raw);
    };
    input.onclick = ev => ev.stopPropagation();
    input.onkeydown = ev => {
      ev.stopPropagation();
      if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
      if (ev.key === 'Escape') finish(false);
    };
    input.onblur = () => finish(false);
  };
  pr.appendChild(val);
  return pr;
}

/* add / subtract: does this shape ADD material to the profile, or cut into the
   shapes drawn before it. A dropdown, not a text box — "subtract" typed into a
   text field is how holes get lost.

   The FIRST shape cannot subtract: sketch._compose refuses a leading
   subtraction ("first entity cannot be a subtraction"), because there is
   nothing yet to cut into. Offering it there was a guaranteed red feature, so
   the first card shows a fixed 'add' badge that explains itself instead. */
const MODE_HELP =
  'add = this shape becomes material · subtract = it cuts into the shapes '
  + 'above it (a circle inside a rectangle makes a hole; a circle on its own '
  + 'is simply left out)';

function modeToggle(feat, entities, i) {
  if (i === 0) {
    const badge = document.createElement('span');
    badge.className = 'smode first';
    badge.textContent = 'add';
    badge.title = 'the first shape defines the profile, so it always adds — '
      + 'nothing exists yet for it to cut into. ' + MODE_HELP;
    return badge;
  }
  const sel = document.createElement('select');
  sel.className = 'smode';
  sel.title = MODE_HELP;
  for (const m of ['add', 'subtract']) {
    const o = document.createElement('option');
    o.value = m; o.textContent = m;
    if ((entities[i].mode || 'add') === m) o.selected = true;
    sel.appendChild(o);
  }
  sel.onclick = e => e.stopPropagation();
  sel.onchange = e => {
    e.stopPropagation();
    if (modalGuard()) { sel.value = entities[i].mode || 'add'; return; }
    applyEntity(feat, entities, i, 'mode', sel.value);
  };
  return sel;
}

function geometryNote(feat, ent, gkey) {
  const n = Array.isArray(ent[gkey]) ? ent[gkey].length : 0;
  const wrap = document.createElement('div');
  wrap.className = 'shgeom';
  const size = pathSize(ent, gkey);
  wrap.textContent = `${n} ${gkey}` + (size ? ` · ${size}` : '');
  const btn = document.createElement('button');
  btn.className = 'shbtn';
  btn.textContent = '✎ edit shape';
  btn.title = 'this outline is a coordinate list — reshape it in the sketch editor';
  btn.onclick = e => { e.stopPropagation(); if (!modalGuard()) bus.emit('edit-sketch', feat); };
  wrap.appendChild(btn);
  return wrap;
}

/* overall size of a coordinate-list shape, so the row says something useful
   about a traced outline instead of just "8 segments" */
function pathSize(ent, gkey) {
  const pts = [];
  if (Array.isArray(ent.start)) pts.push(ent.start);
  for (const seg of (ent[gkey] || [])) {
    if (Array.isArray(seg)) { pts.push(seg); continue; }
    if (seg && Array.isArray(seg.to)) pts.push(seg.to);
    if (seg && Array.isArray(seg.via)) pts.push(seg.via);
  }
  if (pts.length < 2) return '';
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const w = Math.max(...xs) - Math.min(...xs);
  const h = Math.max(...ys) - Math.min(...ys);
  return `${round4(w)} × ${round4(h)} mm`;
}

/* write ONE field of ONE shape back, as a whole-array param edit (the document
   engine edits a named param; `entities` is that param) */
async function applyEntity(feat, entities, i, key, value) {
  const next = entities.map(e => ({ ...e }));
  next[i][key] = value;
  await postJSON('/api/edit',
    { feature_id: feat.id, param: 'entities', value: next });
}

/* inline edit helper shared by the shape rows and the Ø rows */
function beginEditWith(el, oldVal, commit) {
  const input = document.createElement('input');
  input.value = oldVal;
  el.replaceChildren(input); input.focus(); input.select();
  let done = false;
  const finish = async ok => {
    if (done) return; done = true;
    const raw = input.value.trim();
    const num = Number(raw);
    if (!ok || raw === '' || (isNaN(num) && raw !== String(oldVal))) {
      el.textContent = oldVal; return;
    }
    if (isNaN(num) || num === Number(oldVal)) { el.textContent = oldVal; return; }
    await commit(num);
  };
  input.onclick = e => e.stopPropagation();
  input.onkeydown = e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(false);
}

function renderSpecRow(doc, el) {
  if (!doc.spec || !Object.keys(doc.spec).length) return;
  const sr = document.createElement('div'); sr.className = 'specrow';
  // THREE states, not two. "not checked" is what the server reports while the
  // rollback bar is parked, and painting it red said the design had failed its
  // spec every time an editor opened — on 42 of the 50 saved designs
  // (section 5 review, 2026-09-10). Whether it ran is the server's answer
  // (spec_checked), never guessed from the wording of a problem line (R1).
  const checked = doc.spec_checked !== false;
  const failed = checked && doc.spec_problems.length > 0;
  const colour = !checked ? 'var(--dim)' : failed ? 'var(--fail)' : 'var(--ok)';
  const word = !checked ? 'not checked' : failed ? 'FAIL' : 'PASS';
  sr.innerHTML = `<b style="color:${colour}">spec ${word}</b><br>` +
    Object.entries(doc.spec).filter(([, v]) => v != null).map(([k, v]) =>
      `<span class="schip">${k}: ${JSON.stringify(v)}</span>`).join('') +
    doc.spec_problems.map(p => checked
      ? `<div class="sfail">! ${p}</div>`
      : `<div class="snote">${p}</div>`).join('');
  el.appendChild(sr);
}

function selectFeature(fid) {
  // ONE selection set (Fusion): a tree click replaces any viewport pick —
  // otherwise a stale face pick outranks the sketch row the user just
  // clicked when Extrude opens (reported 2026-09-01)
  clearPick();
  // toggle classes IN PLACE — a full re-render here replaces the row between
  // the two clicks of a double-click, and Chromium then never synthesizes
  // dblclick (rename / Edit Feature silently stopped working)
  const was = S.selected === fid;
  S.selected = was ? null : fid;
  if (was) clearHighlight(); else showFeatureOverlay(fid);
  bus.emit('feature-selected', S.selected);   // a tool waiting for its input (Pattern) takes the row
  for (const n of treeEl().querySelectorAll('.node.sel'))
    n.classList.remove('sel');
  if (!was) {
    const n = treeEl().querySelector(`.node[data-fid="${CSS.escape(fid)}"]`);
    if (n) n.classList.add('sel');
  }
}

function beginRename(el, f) {
  const input = document.createElement('input');
  input.value = f.id;
  el.replaceChildren(input); input.focus(); input.select();
  let done = false;                 // renderDoc may destroy the input mid-way
  const finish = async commit => {
    if (done) return; done = true;
    const v = input.value.trim();
    if (!commit || !v || v === f.id) { el.textContent = f.id; return; }
    const doc = await postJSON('/api/feature/rename',
      { feature_id: f.id, name: v });        // postJSON toasts doc.error itself
    if (doc.error) { el.textContent = f.id; return; }
    if (S.selected === f.id) S.selected = v;
    if (S.openNodes.has(f.id)) { S.openNodes.delete(f.id); S.openNodes.add(v); }
  };
  input.onclick = e => e.stopPropagation();
  input.ondblclick = e => e.stopPropagation();
  input.onkeydown = e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(false);
}

function beginEdit(el, fid, param, oldVal) {
  const input = document.createElement('input');
  input.value = oldVal; el.replaceChildren(input); input.focus(); input.select();
  const done = async commit => {
    const raw = input.value.trim();
    const parsed = raw !== '' && !isNaN(Number(raw)) ? Number(raw) : raw;
    if (commit && raw !== '' && parsed !== oldVal) {
      await postJSON('/api/edit', { feature_id: fid, param, value: parsed });
    } else { el.textContent = oldVal; }
  };
  input.onkeydown = e => {
    if (e.key === 'Enter') { e.preventDefault(); done(true); }
    if (e.key === 'Escape') done(false);
  };
  input.onblur = () => done(false);
}

function pointsTable(fid, param, pts) {
  const box = document.createElement('div'); box.className = 'pts';
  box.innerHTML = `<div class="pthead"><span>radius</span><span>z</span></div>`;
  const rows = pts.map(p => [...p]);
  const render = () => {
    box.querySelectorAll('.ptrow, .apply').forEach(el => el.remove());
    rows.forEach((p, i) => {
      const r = document.createElement('div'); r.className = 'ptrow';
      const ir = document.createElement('input'); ir.value = p[0];
      const iz = document.createElement('input'); iz.value = p[1];
      ir.oninput = () => rows[i][0] = Number(ir.value);
      iz.oninput = () => rows[i][1] = Number(iz.value);
      const add = document.createElement('button'); add.className = 'ptbtn';
      add.textContent = '＋'; add.title = 'insert point after';
      add.onclick = () => { rows.splice(i + 1, 0, [...rows[i]]); render(); };
      const del = document.createElement('button'); del.className = 'ptbtn';
      del.textContent = '✕'; del.title = 'remove point';
      del.onclick = () => { rows.splice(i, 1); render(); };
      r.append(ir, iz, add, del); box.appendChild(r);
    });
    const apply = document.createElement('button'); apply.className = 'apply';
    apply.textContent = 'Apply profile';
    apply.onclick = async () => {
      await postJSON('/api/edit', { feature_id: fid, param,
        value: rows.map(p => [Number(p[0]), Number(p[1])]) });
    };
    box.appendChild(apply);
  };
  render();
  return box;
}
