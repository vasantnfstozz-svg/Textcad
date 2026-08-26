// doctabs.js — the DOCUMENT tab bar: one tab per open design, like a browser.
// New / Open / Examples / AI-create all open new tabs; click to switch back,
// ✕ to close. The server keeps each design (and its undo history) alive.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON } from './api.js';
import { loadMesh, clearMesh } from './viewport.js';
import { actionNew } from './dialogs.js';

export function renderDocTabs(doc) {
  const bar = document.getElementById('doctabs');
  bar.innerHTML = '';
  for (const t of doc.tabs || []) {
    const el = document.createElement('div');
    el.className = 'dtab' + (t.active ? ' active' : '');
    el.title = t.name;
    el.innerHTML = `<span class="dot ${t.ok ? 'ok' : 'bad'}"></span>
      <span class="nm">${t.name}</span>`;
    const x = document.createElement('button');
    x.className = 'x'; x.textContent = '✕'; x.title = 'close tab';
    x.onclick = async e => {
      e.stopPropagation();
      clearMesh();                       // the closed design goes at once
      await postJSON('/api/tabs/close', { id: t.id }, 'closing…');
      await loadMesh(true, true);
    };
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
