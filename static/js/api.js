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
    /* A plan asks the kernel too (tangent chains, face normals), so this is a
       route into the crash — same recovery as any other request, and an honest
       sentence instead of "the server did not answer". */
    const back = await serverGone();
    return { ok: false, error: back && back.recovery
      ? 'the geometry kernel crashed on that step, and Studio restarted itself'
      : 'the server did not answer' };
  }
}

/* A read-only QUESTION for the backend: like planRequest, no busy overlay and
   no doc-updated, because nothing changed. This is how a panel gets a fact it
   must not work out for itself (R1) without flashing "rebuilding…" at the user
   — the tree asks it which path curves are tangent corner rounds. A failure is
   silent on purpose: the caller renders without the answer rather than toasting
   about a label. */
export async function askJSON(url, body) {
  try {
    const r = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) });
    return await r.json();
  } catch {
    return { error: 'the server did not answer' };
  }
}

/* THE SERVER VANISHED MID-REQUEST. The geometry kernel can segfault and take
   the process with it (LAUNCH-PLAN §10 ★P0); studio.py's supervisor relaunches
   it with every tab as of the last completed step. Here we wait for it to
   answer again and hand the restored document to everyone. Nothing in the UI
   guesses geometry meanwhile — the document is the authority (R1, R3).
   The wait is generous on purpose: the relaunched child rebuilds the active
   tab BEFORE it opens the port (measured: 26 s for the heaviest design in the
   library), and telling the user to start a second server while the first one
   is still starting is how two processes end up on one port. */
export async function waitForServer(ms = 300000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    await new Promise(r => { setTimeout(r, 1000); });
    try { return await getJSON('/api/doc'); } catch (e) { /* still restarting */ }
  }
  return null;
}

/* The server's crash note is spoken ONCE and, in the same breath, open tool
   panels are told to let go — by whoever sees it first: the failed request,
   the 3 s watcher, or a page that booted right after the crash. Both jobs live
   here so that no caller can do one and forget the other. WHAT happened and
   WHAT to do next are separate, and whether this server rebuilt the restored
   tabs is the SERVER's to say (R1: `unbuilt`, never inferred here). */
export function noteRecovery(doc) {
  const r = doc && doc.recovery;
  if (!r || r.at === S.recoveredAt) return false;
  S.recoveredAt = r.at;
  const when = r.startup ? 'while rebuilding the restored tabs at startup'
    : r.request ? `while handling ${r.request.path}`
    : 'on its own, between requests';
  const then = r.unbuilt
    ? 'Studio is back with your tabs open but NOT built, so nothing is drawn ' +
      'yet: click a tab to build it, and leave the one that keeps crashing closed'
    : r.request
    ? 'Studio restarted itself and the design is back at the last completed ' +
      'step; the step that crashed it was not kept — try a different value'
    : 'Studio restarted itself and the tabs are back';
  bus.emit('msg', 'bot', `⚠ The geometry kernel crashed (${r.code}) ${when}. ${then}.`);
  bus.emit('server-recovered', doc);          // open tool panels let go
  return true;
}

/* No answer at all: the process is gone. Wait for the supervisor to bring it
   back, then let everyone see what came back. A fetch that rejects while the
   server is ALIVE is not a case this app produces — there is no AbortController
   anywhere, and fetch resolves on every HTTP status — so treating "no answer"
   as "gone" costs nothing and never leaves a tool panel locked. */
async function serverGone() {
  setBusy('Studio is restarting…');
  try {
    const doc = await waitForServer();
    if (!doc) {
      bus.emit('msg', 'bot', '⚠ Studio has not come back. Look at the window ' +
        'you started it in: if it gave up, your tabs are still saved — start ' +
        'it again with python studio.py.');
      bus.emit('server-recovered', null);     // never leave a panel locked
      return null;
    }
    if (!noteRecovery(doc)) {      // no NEW crash note: restarted by hand, or
      bus.emit('msg', 'bot',       // the 3 s watcher spoke this one a tick ago
        '⚠ The server went away and came back; the design was reloaded.');
      bus.emit('server-recovered', doc);
    }
    if (doc.features) bus.emit('doc-updated', doc);
    return doc;
  } finally {
    clearBusy();
  }
}

export async function postJSON(url, body, busyMsg) {
  setBusy(busyMsg);
  try {
    let doc;
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
      doc = await r.json();     // a body that dies mid-flight throws here too
    } catch (e) {                                  // no reply at all: gone
      const back = await serverGone();
      return { error: 'the server restarted during this step', ...(back || {}) };
    }
    if (doc.error) bus.emit('msg', 'bot', '⚠ ' + doc.error);
    noteRecovery(doc);
    if (doc.features) bus.emit('doc-updated', doc);
    return doc;
  } finally {
    clearBusy();
  }
}
