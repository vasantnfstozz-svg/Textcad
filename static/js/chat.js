// chat.js — the AI designer panel: message log + sending chat requests.
//
// P5 (LAUNCH-PLAN.md §5 step B): a "design" or "add" request is a server JOB
// that builds ONE verified feature per step. This panel follows the job and
// prints each step as it lands; the viewport follows the document (R3) when
// the design being built is the one on screen.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON, getJSON, setBusy, clearBusy } from './api.js';
import { loadMesh } from './viewport.js';

export function addMsg(who, text) {
  const log = document.getElementById('chatLog');
  const d = document.createElement('div'); d.className = 'msg ' + who;
  d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight;
}
bus.on('msg', addMsg);

const sig = d => (d ? `${d.active_tab}|${d.features.length}|${d.ok}|${d.geom_version}` : '');
const pause = ms => new Promise(r => { setTimeout(r, ms); });

/* Follow one job to its end. An "add" job edits the design on screen, so the
   busy overlay holds the user's own edits off it until the job is done — the
   undo stack and the kernel are one line. A "create" job builds in its own
   tab, and the user keeps working. */
async function followJob(id, kind) {
  let seen = 0, last = sig(S.lastDoc), misses = 0;
  const busy = kind === 'add';
  if (busy) setBusy('the AI is adding to this design…');
  try {
    for (;;) {
      await pause(700);
      let j;
      /* A crashed-and-relaunched server answers again within seconds, so a
         failed poll is worth retrying — but not for ever: an unbounded retry
         held the busy overlay up with nothing to say. ~40 s, then say so. */
      try { j = await getJSON(`/api/chat/job/${id}`); misses = 0; }
      catch {
        if (++misses < 60) continue;
        addMsg('bot', '⚠ lost contact with the AI while it was building — '
          + 'reload the page and check the design before carrying on');
        return;
      }
      if (j.error) { addMsg('bot', '⚠ ' + j.error); return; }
      const grew = seen < j.log.length;
      for (; seen < j.log.length; seen++) addMsg('step', j.log[seen]);
      if (busy) setBusy(`the AI is adding to this design… step ${j.log.length}`);
      // the tab strip (name, health of the tab being built) rides every
      // step; the viewport only when the design ON SCREEN changed (R3)
      if (j.features && (grew || j.done)) bus.emit('doc-updated', j);
      if (j.features && sig(j) !== last) {
        last = sig(j);
        loadMesh();
      }
      if (j.done) { addMsg('bot', j.reply || 'done'); return; }
    }
  } finally {
    if (busy) clearBusy();
  }
}

export function initChat() {
  document.getElementById('chatForm').onsubmit = async e => {
    e.preventDefault();
    const input = document.getElementById('chatInput');
    const text = input.value.trim(); if (!text) return;
    input.value = ''; addMsg('user', text);
    const before = S.lastDoc ? S.lastDoc.active_tab : null;
    const doc = await postJSON('/api/chat', { message: text }, 'thinking…');
    addMsg('bot', doc.reply || '…');
    if (doc.job && !doc.job_done) {
      await followJob(doc.job, doc.new_tab ? 'create' : 'add');
      return;
    }
    loadMesh(doc.active_tab !== before);   // new tab (AI create) -> refit view
  };
}
