// doctabs.js — the DOCUMENT tab bar: one tab per open design, like a browser.
// New / Open / Examples / AI-create all open new tabs; click to switch back,
// ✕ to close. The server keeps each design (and its undo history) alive.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON } from './api.js';
import { loadMesh } from './viewport.js';
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
      await postJSON('/api/tabs/close', { id: t.id }, 'closing…');
      loadMesh(true);
    };
    el.appendChild(x);
    if (!t.active) {
      el.onclick = async () => {
        await postJSON('/api/tabs/switch', { id: t.id }, 'switching…');
        loadMesh(true);
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
