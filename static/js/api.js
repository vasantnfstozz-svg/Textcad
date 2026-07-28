// api.js — all HTTP calls to the Studio backend, plus the busy overlay.
// postJSON automatically announces the updated document on the bus, so the
// tree, tabs and status bar refresh no matter who triggered the change.

import { bus } from './bus.js';

const busyEl = () => document.getElementById('busy');

export function setBusy(msg) {
  document.getElementById('busyText').textContent = msg || 'rebuilding…';
  busyEl().style.display = 'flex';
}
export function clearBusy() { busyEl().style.display = 'none'; }
export function isBusy() { return busyEl().style.display === 'flex'; }

export async function getJSON(url) {
  return (await fetch(url)).json();
}

export async function postJSON(url, body, busyMsg) {
  setBusy(busyMsg);
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const doc = await r.json();
    if (doc.error) bus.emit('msg', 'bot', '⚠ ' + doc.error);
    if (doc.features) bus.emit('doc-updated', doc);
    return doc;
  } finally {
    clearBusy();
  }
}
