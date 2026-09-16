// api.js — all HTTP calls to the Studio backend, plus the busy overlay.
// postJSON automatically announces the updated document on the bus, so the
// tree, tabs and status bar refresh no matter who triggered the change.

import { bus } from './bus.js';
import { S } from './state.js';

const busyEl = () => document.getElementById('busy');

/* The overlay SAYS SOMETHING while a long step runs. A round, bevel or shell
   on a body with hundreds of edges genuinely takes minutes — the overnight
   journey run of 2026-09-13 measured 156 s, 630 s and 1195 s on the user's own
   traced parts, all of them CORRECT answers — and an overlay that shows one
   unchanging word for ten minutes is indistinguishable from a frozen app.
   That was three of that run's eight findings, filed as one class.

   No number is quoted here on purpose (R1): how long a step may run before the
   kernel worker stops it is the server's fact, not the browser's.

   Neither line says WHICH step is running, and the second does not promise the
   step will stop itself. This overlay is shown for EVERY request — the AI
   writing a design, a model loading, a boolean — and only a round, a bevel and
   a hollow have a budget that ends them (kernelguard.py). Telling someone
   waiting on a boolean that it stops itself would be a sentence the product
   cannot keep, and would keep them waiting instead of reloading. */
let busySteps = [];

function busyStep(text) {
  const el = document.getElementById('busyText');
  if (el && isBusy()) el.textContent = text;
}

export function setBusy(msg) {
  const base = msg || 'rebuilding…';
  document.getElementById('busyText').textContent = base;
  busyEl().style.display = 'flex';
  busySteps.forEach(clearTimeout);
  busySteps = [
    setTimeout(() => busyStep(`${base} · still working — a big body can take `
      + 'minutes; rounding, bevelling and hollowing are the slow ones'), 20000),
    setTimeout(() => busyStep(`${base} · still working — nothing you have made `
      + 'will be lost, whether this finishes or is refused'), 90000),
  ];
}
export function clearBusy() {
  busySteps.forEach(clearTimeout);
  busySteps = [];
  busyEl().style.display = 'none';
}
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
    const data = await r.json();
    /* Same trap askJSON closed: a 422 (a field pydantic will not take) or a
       500 answers with `detail`, never `ok` — so the panel refused with
       "cannot start: undefined" and closed itself, which tells the user
       nothing at all (rule 7). Turn it into the sentence it should have been. */
    if (!r.ok || data == null || data.ok === undefined) {
      const d = data && data.detail;
      const why = Array.isArray(d)
        ? d.map(x => `${(x.loc || []).at(-1)}: ${x.msg}`).join('; ')
        : (typeof d === 'string' ? d : null);
      return { ok: false, error: why || `the server said ${r.status}` };
    }
    return data;
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
    const data = await r.json();
    // Silent to the USER, never silent to the CALLER (second code review,
    // 2026-09-09): a 422 or 500 body has no `error` key of its own, so it
    // used to read exactly like a successful "there are no arcs" — and the
    // caller then cached that as the answer.
    if (!r.ok) return { error: data?.detail || `the server said ${r.status}`,
                        status: r.status };
    return data;
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

/* THE DOORBELL. A design that arrived from outside the browser (an AI over
   MCP) is announced ONCE and then forgotten by the server. Whether something
   arrived is the SERVER's fact, never arithmetic here (R1): this used to be
   inferred from the active tab differing from the last poll, which made every
   page load replay the banner and reset the view — sometimes from under an
   open dialog — long after the design landed (BACKLOG, seen 2026-09-01).

   Two guards, both needed: S.arrivalAt stops THIS page saying it twice while
   the ack is in flight, and the ack stops any other page (or the next reload)
   saying it at all. The ack is a bare fetch on purpose — postJSON would raise
   the busy overlay over a banner nobody is waiting on. */
export function noteArrival(doc) {
  const a = doc && doc.arrival;
  if (!a || a.at === S.arrivalAt) return false;
  S.arrivalAt = a.at;
  bus.emit('msg', 'bot',
    `📡 "${a.name}" just arrived (designed externally, e.g. via MCP) — loaded it.`);
  fetch('/api/arrival/ack', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ at: a.at }),
  }).catch(() => { /* the banner is spoken; the ack is best-effort */ });
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
