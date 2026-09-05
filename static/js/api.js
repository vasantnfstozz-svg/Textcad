// api.js — all HTTP calls to the Studio backend, plus the busy overlay.
// postJSON automatically announces the updated document on the bus, so the
// tree, tabs and status bar refresh no matter who triggered the change.

import { bus } from './bus.js';
import { S } from './state.js';

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

/* ONE way to ask the geometry authority (LAUNCH-PLAN.md R1): POST
   /api/tool/plan. Read-only, so no busy overlay and no doc-updated; the
   answer is {ok, ...} or {ok: false, error} — a network failure is an error
   sentence too, so a caller only ever has to speak it. */
export async function planRequest(req) {
  try {
    const r = await fetch('/api/tool/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req) });
    return await r.json();
  } catch (e) {
    return { ok: false, error: `the server did not answer (${e.message})` };
  }
}

/* THE SERVER VANISHED MID-REQUEST. The geometry kernel can segfault and take
   the process with it (LAUNCH-PLAN §10 ★P0); studio.py's supervisor relaunches
   it with every tab as of the last completed step. Here we wait for it to
   answer again and hand the restored document to everyone. Nothing in the UI
   guesses geometry meanwhile — the document is the authority (R1, R3). */
export async function waitForServer(ms = 120000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    await new Promise(r => setTimeout(r, 1000));
    try { return await getJSON('/api/doc'); } catch (e) { /* still restarting */ }
  }
  return null;
}

/* The server's crash note is spoken ONCE, by whoever sees it first (the failed
   request, the 3 s watcher, or a page that booted right after the crash). */
export function noteRecovery(doc) {
  const r = doc && doc.recovery;
  if (!r || r.at === S.recoveredAt) return false;
  S.recoveredAt = r.at;
  const when = r.startup
    ? 'while rebuilding the restored tabs at startup. They are open but not ' +
      'built: switch to one to build it, and close the one that crashes again'
    : r.request ? `while handling ${r.request.path}. Studio restarted itself ` +
      'and the design is back at the last completed step; the step that ' +
      'crashed it was not kept — try a different value'
    : 'between requests. Studio restarted itself and the tabs are back';
  bus.emit('msg', 'bot', `⚠ The geometry kernel crashed (${r.code}) ${when}.`);
  return true;
}

export async function postJSON(url, body, busyMsg) {
  setBusy(busyMsg);
  try {
    let r;
    try {
      r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
    } catch (e) {                                  // no reply at all: gone
      setBusy('Studio is restarting…');
      const doc = await waitForServer();
      if (!doc) {
        bus.emit('msg', 'bot', '⚠ The server did not come back. Start it again with: python studio.py');
        return { error: 'the server did not answer' };
      }
      if (!noteRecovery(doc))
        bus.emit('msg', 'bot', '⚠ The server went away and came back; the design was reloaded.');
      bus.emit('server-recovered', doc);            // open tool panels let go
      bus.emit('doc-updated', doc);
      return { error: 'the server restarted during this step', ...doc };
    }
    const doc = await r.json();
    if (doc.error) bus.emit('msg', 'bot', '⚠ ' + doc.error);
    noteRecovery(doc);
    if (doc.features) bus.emit('doc-updated', doc);
    return doc;
  } finally {
    clearBusy();
  }
}
