// doctabs.js — the DOCUMENT tab bar: one tab per open design, like a browser.
// New / Open / Examples / AI-create all open new tabs; click to switch back,
// ✕ to close. The server keeps each design (and its undo history) alive.
//
// A tab with changes not yet pushed as a version carries a ● marker, and its
// ✕ asks first: "Save & close" pushes them as a new version, "Discard" throws
// them away (the saved design and its versions are untouched). User
// (2026-09-01): "when i am closing the tabs, a tab should ask me, you made
// changes ... if i press, the edits i did, no need to be saved."

import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh, clearMesh } from './viewport.js';
import { actionNew } from './dialogs.js';
import { askThree } from './ask.js';

async function closeTab(t) {
  if (t.dirty) {
    const pick = await askThree(`Close "${t.name}"?`, {
      body: 'This design has changes that are not saved as a version yet. ' +
            'Save them as a new version, or throw them away? (The versions ' +
            'already in the tree stay either way.)',
      ok: 'Save & close', alt: 'Discard & close', altDanger: true,
    });
    if (pick === null) return;                    // cancelled — tab stays
    if (pick === 'ok') {
      // /api/save works on the ACTIVE tab, so bring this one forward first.
      // Unconditionally: t.active is a snapshot from render time, and the
      // active tab can move underneath an open dialog (the MCP doorbell
      // auto-loads arriving designs) — seen live 2026-09-01. Saving whatever
      // happens to be active would push the WRONG design.
      await postJSON('/api/tabs/switch', { id: t.id });
      const r = await postJSON('/api/save', {}, 'saving…');
      if (!r.saved) {
        bus.emit('msg', 'bot', '⚠ Could not save, so the tab stays open: ' +
                 (r.error || 'the server did not confirm the save.'));
        return;
      }
      bus.emit('msg', 'bot', `Saved "${r.saved}"` +
        (r.version ? ` — recorded as ${r.version}` : '') + ', then closed the tab.');
    }
  }
  clearMesh();                       // the closed design goes at once
  await postJSON('/api/tabs/close', { id: t.id }, 'closing…');
  await loadMesh(true, true);
}

export function renderDocTabs(doc) {
  const bar = document.getElementById('doctabs');
  bar.innerHTML = '';
  for (const t of doc.tabs || []) {
    const el = document.createElement('div');
    el.className = 'dtab' + (t.active ? ' active' : '');
    el.title = t.name + (t.dirty ? ' — has changes not saved as a version' : '');
    // ok true/false = built fine / broken; null = restored from the last
    // session, loads on first click — grey, not red
    const dot = t.ok === true ? 'ok' : t.ok === false ? 'bad' : 'wait';
    el.innerHTML = `<span class="dot ${dot}"></span>
      <span class="nm">${t.name}</span>` +
      (t.dirty ? '<span class="dmark">●</span>' : '');
    const x = document.createElement('button');
    x.className = 'x'; x.textContent = '✕';
    x.title = t.dirty ? 'close tab (asks about the unsaved changes)'
                      : 'close tab';
    x.onclick = e => { e.stopPropagation(); closeTab(t); };
    el.appendChild(x);
    if (!t.active) {
      el.onclick = async () => {
        // Empty the viewport FIRST. Switching used to leave the previous
        // design on screen for as long as the new one took to arrive, so the
        // user stared at the wrong part with no sign anything was happening
        // and clicked the tab again (user report 2026-08-25).
        clearMesh();
        el.classList.add('loading');
        try {
          await postJSON('/api/tabs/switch', { id: t.id },
                         `opening ${t.name}…`);
          await loadMesh(true, true);
        } finally {
          el.classList.remove('loading');
        }
      };
    }
    bar.appendChild(el);
  }
  const plus = document.createElement('button');
  plus.id = 'dtabNew'; plus.textContent = '＋'; plus.title = 'new design';
  plus.onclick = actionNew;
  bar.appendChild(plus);
}
bus.on('doc-updated', renderDocTabs);
