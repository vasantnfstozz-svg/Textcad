// chat.js — the AI designer panel: message log + sending chat requests.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON } from './api.js';
import { loadMesh } from './viewport.js';

export function addMsg(who, text) {
  const log = document.getElementById('chatLog');
  const d = document.createElement('div'); d.className = 'msg ' + who;
  d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight;
}
bus.on('msg', addMsg);

export function initChat() {
  document.getElementById('chatForm').onsubmit = async e => {
    e.preventDefault();
    const input = document.getElementById('chatInput');
    const text = input.value.trim(); if (!text) return;
    input.value = ''; addMsg('user', text);
    const before = S.lastDoc ? S.lastDoc.active_tab : null;
    const doc = await postJSON('/api/chat', { message: text }, 'thinking…');
    addMsg('bot', doc.reply || '…');
    loadMesh(doc.active_tab !== before);   // new tab (AI create) -> refit view
  };
}
