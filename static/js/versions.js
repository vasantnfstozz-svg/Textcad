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
import { askText, askConfirm } from './ask.js';
import { loadMesh } from './viewport.js';

let open = false;
let seq = 0;                     // only the newest fetch may paint
let lastDirty = null;            // refresh the summary when dirtiness flips

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
    // just recorded something (`version`), reported a history fault, restored,
    // or the design's dirtiness FLIPPED (edits no longer mint versions, so the
    // ● in the summary is how you see there is something to push) — otherwise
    // the one-line summary would quietly go stale while collapsed. Not on
    // every keystroke beyond that: /api/versions is kept out of /api/doc
    // precisely so it is not on the hot path.
    const dirty = !!doc.dirty;
    const flipped = lastDirty !== null && dirty !== lastDirty;
    lastDirty = dirty;
    if (open || doc.version || doc.history_error || doc.restored || flipped)
      refresh();
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
  // Changes since the current version live HERE until the user decides —
  // nothing mints a version on its own any more (2026-09-01), and finishing
  // a round of edits is a CHOICE (same user, later that day): fold them into
  // the version you are on, or push them as the next one.
  if (d.dirty) {
    const w = document.createElement('div');
    w.className = 'vpending';
    w.innerHTML = '<span class="vdirty">●</span> unsaved changes';
    if (d.current) {
      const upd = document.createElement('button');
      upd.className = 'vpush';
      upd.textContent = `update ${d.current}`;
      upd.title = `these changes belong to ${d.current}: rewrite it in ` +
                  `place — no new version`;
      upd.onclick = async () => {
        const r = await postJSON('/api/versions/amend', {}, 'updating…');
        if (r.error) bus.emit('msg', 'bot', '⚠ ' + r.error);
        else bus.emit('msg', 'bot', `Updated ${r.amended} in place and ` +
          `saved "${r.saved}" — no new version was made.`);
        refresh();
      };
      w.appendChild(upd);
    }
    const b = document.createElement('button');
    b.className = 'vpush';
    b.textContent = d.next_id && d.current
      ? `push ${d.next_id}` : 'save as version';
    b.title = 'record everything changed since ' +
              (d.current || 'the start') + ' as one NEW version';
    b.onclick = async () => {
      const r = await postJSON('/api/save', {}, 'saving…');
      if (r.error) bus.emit('msg', 'bot', '⚠ ' + r.error);
      else if (r.saved) bus.emit('msg', 'bot', `Saved "${r.saved}"` +
        (r.version ? ` — recorded as ${r.version}` : '') + '.');
      refresh();
    };
    w.appendChild(b);
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
  const dot = d.dirty
    ? ' <span class="vdirty" title="changes not saved as a version">●</span>'
    : '';
  if (d.unsaved) return 'unsaved' + dot;
  const n = (d.versions || []).length;
  if (!n) return 'none yet' + dot;
  const star = d.starred ? ` <span class="star">★ ${d.starred}</span>` : '';
  return `${d.current || '—'} of ${n}${star}${dot}`;
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
    '\n\nclick to put it back on screen · ✎ rename · ⇄ what changed · ✕ delete';

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

  // A version recorded while verification FAILED used to be struck through —
  // which reads as "deleted", not "check failed" (user, 2026-09-01: "why the
  // version name is striked out"). A warning mark says what it means.
  const warn = document.createElement('span');
  if (v.rebuildable === false) {
    warn.className = 'vwarn';
    warn.textContent = '⚠';
    warn.title = 'recorded while the design FAILED verification — the ' +
                 'version opens fine, but check the ✗ badge after restoring';
  }

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

  // Rename existed as double-click-the-label, and nobody found it (user
  // request 2026-09-01: "add a option where i can delete the version and
  // rename it") — so both get a visible button. The dblclick still works.
  const edit = document.createElement('button');
  edit.className = 'vedit';
  edit.textContent = '✎';
  edit.title = 'rename this version';
  edit.onclick = e => { e.stopPropagation(); rename(v); };

  // On the CURRENT row deleting is refused anyway (you are on it), so its ✕
  // is the "trim" gesture instead: delete everything AFTER this version.
  // That is the user's real cleanup (2026-09-01: "deleted version after v15
  // ... i dont need them") — they had cleared a tail one refused click at a
  // time before this existed.
  const del = document.createElement('button');
  del.className = 'vdel';
  del.textContent = '✕';
  const below = v.id === d.current ? descendantsOf(v.id, d.versions) : [];
  if (v.id === d.current) {
    del.title = below.length
      ? `delete the ${below.length} version${below.length === 1 ? '' : 's'} ` +
        `after this one (${v.id} stays)`
      : 'this is the version you are on, and nothing comes after it';
    del.onclick = e => { e.stopPropagation(); removeAfter(v, below); };
  } else {
    del.title = 'delete this version permanently';
    del.onclick = e => { e.stopPropagation(); remove(v, d); };
  }

  el.append(star, id, label,
            ...(v.rebuildable === false ? [warn] : []),
            who, meta, edit, why, del);
  el.onclick = () => restore(v, d);
  return el;
}

function descendantsOf(vid, versions) {
  const kids = {};
  for (const v of versions || []) (kids[v.parent] ||= []).push(v.id);
  const out = [], stack = [vid];
  while (stack.length)
    for (const c of kids[stack.pop()] || []) { out.push(c); stack.push(c); }
  return out;
}

async function removeAfter(v, below) {
  if (!below.length) {
    bus.emit('msg', 'bot', `${v.id} is the version you are on and nothing ` +
      `comes after it — there is nothing to delete.`);
    return;
  }
  const yes = await askConfirm(`Delete everything after ${v.id}?`, {
    body: `${below.join(', ')} — ${below.length === 1 ? 'this version is' :
          `these ${below.length} versions are`} removed for good. ${v.id} ` +
          `itself and everything before it stay, and the next push counts ` +
          `on from here.`,
    ok: `Delete ${below.length === 1 ? 'it' : `all ${below.length}`}`,
    danger: true,
  });
  if (!yes) return;
  const r = await postJSON('/api/versions/delete_after', { id: v.id });
  if (r.error) bus.emit('msg', 'bot', '⚠ ' + r.error);
  else bus.emit('msg', 'bot', `Deleted ${r.deleted.length} version` +
    `${r.deleted.length === 1 ? '' : 's'} after ${v.id}` +
    (r.next ? ` — the next push will be ${r.next}` : '') + '.');
  refresh();
}

async function remove(v, d) {
  // The one destructive click in this panel, so it confirms — unlike restore,
  // which is deliberately promptless because it destroys nothing.
  const kids = (d.versions || []).filter(x => x.parent === v.id).length;
  const yes = await askConfirm(`Delete ${v.id}?`, {
    body: `"${v.label || v.id}" is removed from the history for good — ` +
          `your design on screen and the saved file are not touched.` +
          (kids ? ` The ${kids === 1 ? 'version' : `${kids} versions`} ` +
                  `branched from it will re-attach to its parent.` : ''),
    ok: 'Delete', danger: true,
  });
  if (!yes) return;
  const r = await postJSON('/api/versions/delete', { id: v.id });
  if (r.error) bus.emit('msg', 'bot', '⚠ ' + r.error);
  else bus.emit('msg', 'bot', `Deleted ${v.id} from the history` +
    (r.rewired?.length ? ` — ${r.rewired.join(', ')} now ` +
      (r.parent ? `branch${r.rewired.length === 1 ? 'es' : ''} from ${r.parent}`
                : `start${r.rewired.length === 1 ? 's' : ''} the tree`)
     : '') + '.');
  refresh();
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

async function restore(v, d) {
  // Clicking the version you are already ON is a no-op, not a reload — the
  // esp32 case takes ~30 s to rebuild, and paying that to arrive where you
  // already are is absurd (user, 2026-09-01). If the tab is DIRTY the click
  // is meaningful again: it puts the pristine version back (undoable).
  if (d && v.id === d.current && !d.dirty) {
    bus.emit('msg', 'bot', `${v.id} is already on screen.`);
    return;
  }
  // No confirmation on purpose: this does NOT overwrite the saved .tcad.json,
  // whatever was on screen goes onto the undo stack, and the versions you came
  // from stay in the tree. Nothing here is destructive, so a dialog every time
  // would just be in the way — the reply below says how to get back.
  const doc = await postJSON('/api/versions/restore', { id: v.id },
                             `opening ${v.id}…`);
  if (doc.error) { bus.emit('msg', 'bot', '⚠ ' + doc.error); refresh(); return; }
  if (doc.already) {
    // the server found the doc already holds this content (e.g. a stale
    // panel) — nothing was rebuilt, so there is nothing to re-fetch
    bus.emit('msg', 'bot', `${v.id} is already on screen.`);
    refresh();
    return;
  }
  await loadMesh(true, true);
  bus.emit('msg', 'bot',
    `Opened ${v.id} — ${v.label || 'no label'} (${v.features} features). ` +
    `Editing from here starts a new branch, so the newer versions stay in the ` +
    `list. Ctrl+Z puts back what was on screen.`);
  refresh();
}
