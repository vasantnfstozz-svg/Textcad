// versions.js — the per-design version tree (VERSION-TREE-PLAN.md P3)
//
// The problem this answers, in the user's words: "every time when we are
// working in the changes, there is always a new tab will pop out with new
// modified design, after some time there will be many tabs, we do not know
// which is my intended design."
//
// P0 stopped the tabs multiplying. This is the other half: every recorded
// version of the design, as a TREE (going back to v3 and editing branches off
// it, it does not delete v4..v10), one click to put any of them back on
// screen, and one star for "this is the one I actually mean" — because recency
// cannot answer that. v10 is not automatically better than v7.
//
// Collapsed by default down to a single line, so the answer to "where am I"
// is visible without opening anything and the feature tree keeps its space.

import { bus } from './bus.js';
import { getJSON, postJSON } from './api.js';
import { askText } from './ask.js';
import { loadMesh } from './viewport.js';

let open = false;
let seq = 0;                     // only the newest fetch may paint

const pane = () => document.getElementById('verPane');
const body = () => document.getElementById('verBody');
const summary = () => document.getElementById('verSummary');

export function initVersions() {
  document.getElementById('verHead').onclick = () => {
    open = !open;
    pane().classList.toggle('collapsed', !open);
    document.getElementById('verCaret').textContent = open ? '▾' : '▸';
    if (open) refresh();
  };
  bus.on('doc-updated', doc => {
    // Refresh when the panel is showing, and ALWAYS when the server says it
    // just recorded something (`version`), reported a history fault, or
    // restored — otherwise the one-line summary would quietly go stale while
    // collapsed. Not on every keystroke beyond that: /api/versions is kept
    // out of /api/doc precisely so it is not on the hot path.
    if (open || doc.version || doc.history_error || doc.restored) refresh();
  });
  bus.on('versions-open', () => {
    if (!open) document.getElementById('verHead').click();
  });
  refresh();
}

export async function refresh() {
  const mine = ++seq;
  let d;
  try { d = await getJSON('/api/versions'); }
  catch (e) { d = { unreachable: true }; }
  if (mine !== seq) return;
  paint(d);
}

function paint(d) {
  summary().innerHTML = summaryText(d);
  if (!open) return;
  const el = body();
  el.innerHTML = '';

  if (d.unreachable) {
    el.innerHTML = '<div class="vprob">Can’t reach the TextCAD server, so ' +
      'the version list can’t load. Is <b>studio.py</b> still running?</div>';
    return;
  }
  // Three different empty states, and they must never read the same — an
  // unsaved design has no history YET, which is nothing like a broken one.
  for (const p of d.problems || []) {
    const w = document.createElement('div');
    w.className = 'vprob';
    w.textContent = '⚠ ' + p;
    el.appendChild(w);
  }
  if (d.unsaved) {
    el.insertAdjacentHTML('beforeend',
      `<div class="vnote">${d.note || 'No history yet.'}</div>`);
    return;
  }
  if (!(d.versions || []).length) {
    el.insertAdjacentHTML('beforeend',
      '<div class="vnote">No versions recorded yet.</div>');
    return;
  }

  // Index by parent so the tree can be walked. A version whose parent is
  // missing (a hand-edited index) is treated as a root rather than dropped —
  // showing it detached beats hiding a version that exists.
  const byId = new Map(d.versions.map(v => [v.id, v]));
  const kids = new Map();
  for (const v of d.versions) {
    const k = v.parent && byId.has(v.parent) ? v.parent : '__root';
    if (!kids.has(k)) kids.set(k, []);
    kids.get(k).push(v.id);
  }
  // Indent counts BRANCHES, not links: a version's first child continues the
  // trunk at the same level and only a second child steps right. Per-link
  // indenting looked fine until the git backfill produced rocky-keychain's
  // linear chain of 24 -- as 24 nested levels the labels left the panel
  // entirely. Same rule as History.depths(), so panel and CLI agree.
  const walk = (id, depth) => {
    el.appendChild(row(byId.get(id), depth, d));
    (kids.get(id) || []).forEach((c, i) => walk(c, i === 0 ? depth : depth + 1));
  };
  for (const r of kids.get('__root') || []) walk(r, 0);
}

function summaryText(d) {
  if (!d || d.unreachable) return '<span class="vprob">server?</span>';
  if ((d.problems || []).length) return '<span class="vprob">⚠ problem</span>';
  if (d.unsaved) return 'unsaved';
  const n = (d.versions || []).length;
  if (!n) return 'none yet';
  const star = d.starred ? ` <span class="star">★ ${d.starred}</span>` : '';
  return `${d.current || '—'} of ${n}${star}`;
}

function row(v, depth, d) {
  const el = document.createElement('div');
  el.className = 'vrow' + (v.id === d.current ? ' cur' : '') +
                 (v.rebuildable === false ? ' dead' : '');
  el.dataset.vid = v.id;
  el.style.marginLeft = `${depth * 11}px`;
  el.title = `${v.id} · ${v.label || '(no label)'}\n${v.created || ''}` +
    `\n${v.features} features · via ${v.source || '?'}` +
    (v.rebuildable === false ? '\nthis version did NOT verify when recorded'
                             : '') +
    '\n\nclick to put it back on screen · double-click the name to rename it';

  const star = document.createElement('button');
  star.className = 'vstar' + (v.id === d.starred ? ' on' : '');
  star.textContent = v.id === d.starred ? '★' : '☆';
  star.title = v.id === d.starred
    ? 'this is the version you marked — click to unmark'
    : 'mark this as the version you actually mean';
  star.onclick = async e => {
    e.stopPropagation();
    const r = await postJSON('/api/versions/star',
                             { id: v.id === d.starred ? null : v.id });
    if (r.error) bus.emit('msg', 'bot', '⚠ ' + r.error);
    refresh();
  };

  const id = document.createElement('span');
  id.className = 'vid';
  id.textContent = v.id;

  const label = document.createElement('span');
  label.className = 'vlabel';
  label.textContent = v.label || '(no label)';
  label.ondblclick = e => {
    e.stopPropagation();
    rename(v);
  };

  // WHO made it. The user asked for manual work to be distinguishable "so ai
  // can recognize the manual changes" — and it has to be visible to them too.
  const who = document.createElement('span');
  who.className = 'vwho ' + (v.author || 'you');
  who.textContent = v.author === 'ai' ? 'AI'
                  : v.author === 'git' ? 'git' : 'you';
  who.title = v.author === 'ai' ? 'the AI made this version'
            : v.author === 'git' ? 'imported from a git commit'
            : 'you made this version by hand';

  const meta = document.createElement('span');
  meta.className = 'vmeta';
  meta.textContent = `${v.features}f`;

  // "what changed here?" is fetched on demand, never precomputed for the whole
  // list: answering it decompresses two snapshots, and this panel repaints
  // whenever the document changes.
  const why = document.createElement('button');
  why.className = 'vwhy';
  why.textContent = '⇄';
  why.title = 'what changed in this version';
  why.onclick = e => { e.stopPropagation(); toggleDiff(el, v); };

  el.append(star, id, label, who, meta, why);
  el.onclick = () => restore(v);
  return el;
}

async function toggleDiff(row, v) {
  const open = row.nextElementSibling &&
               row.nextElementSibling.classList.contains('vdiff');
  if (open) { row.nextElementSibling.remove(); return; }
  const box = document.createElement('div');
  box.className = 'vdiff';
  box.style.marginLeft = row.style.marginLeft;
  box.textContent = 'comparing…';
  row.after(box);

  let d;
  try { d = await getJSON(`/api/versions/diff?target=${encodeURIComponent(v.id)}`); }
  catch (e) { d = { error: 'the server did not answer' }; }
  if (!box.isConnected) return;
  if (d.error) { box.textContent = '⚠ ' + d.error; return; }

  const rows = [];
  const base = d.base ? `vs ${d.base}` : '';
  rows.push(`<b>${d.summary}</b> <span class="vdim">${base}</span>`);
  for (const a of d.added)
    rows.push(`<span class="vadd">+ ${a.id}</span> <span class="vdim">${a.op}</span>`);
  for (const r of d.removed)
    rows.push(`<span class="vdel">− ${r.id}</span> <span class="vdim">${r.op}</span>`);
  for (const c of d.changed) {
    for (const p of c.params)
      rows.push(`${c.id}<span class="vdim">.${p.param}</span> ` +
        (p.scalar ? `${p.from} → ${p.to}`
                  : `<span class="vdim">${p.note}</span>`));
    if (c.op_from) rows.push(`${c.id} <span class="vdim">op</span> ${c.op_from} → ${c.op}`);
    if (c.inputs_to)
      rows.push(`${c.id} <span class="vdim">inputs</span> ` +
                `${c.inputs_from.join(', ')} → ${c.inputs_to.join(', ')}`);
    if (c.suppressed !== undefined)
      rows.push(`${c.id} <span class="vdim">${c.suppressed ? 'suppressed' : 'unsuppressed'}</span>`);
  }
  if (d.spec_changed) rows.push('<span class="vdim">the spec changed</span>');
  if (d.renamed) rows.push(`renamed ${d.renamed[0]} → ${d.renamed[1]}`);
  box.innerHTML = rows.join('<br>');
}

async function rename(v) {
  const name = await askText(`Rename ${v.id}`, {
    label: 'Version name', value: v.label || '',
    body: 'Auto-labels say what happened; a name of your own says why '
          + 'it matters -- "the one for the mill".',
    ok: 'Rename',
  });
  if (name === null) return;
  const r = await postJSON('/api/versions/label', { id: v.id, label: name });
  if (r.error) bus.emit('msg', 'bot', '⚠ ' + r.error);
  refresh();
}

async function restore(v) {
  // No confirmation on purpose: this does NOT overwrite the saved .tcad.json,
  // whatever was on screen goes onto the undo stack, and the versions you came
  // from stay in the tree. Nothing here is destructive, so a dialog every time
  // would just be in the way — the reply below says how to get back.
  const doc = await postJSON('/api/versions/restore', { id: v.id },
                             `opening ${v.id}…`);
  if (doc.error) { bus.emit('msg', 'bot', '⚠ ' + doc.error); refresh(); return; }
  await loadMesh(true, true);
  bus.emit('msg', 'bot',
    `Opened ${v.id} — ${v.label || 'no label'} (${v.features} features). ` +
    `Editing from here starts a new branch, so the newer versions stay in the ` +
    `list. Ctrl+Z puts back what was on screen.`);
  refresh();
}
