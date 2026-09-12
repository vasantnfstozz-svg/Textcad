// bugreport.js — the bug button (LAUNCH-PLAN.md P5b).
//
// One click saves the open design, the last requests this tab made, what the
// browser reported and a screenshot of the viewport under bugs/ on the server,
// and the user keeps designing. A later chat reads that folder and has the
// repro without a description — "it went wrong when I filleted" becomes the
// exact request, the document before it and the tree as it looked.
//
// The tab keeps two small rings from boot: every fetch (method, url, body,
// status, ms) and every error or warning the user could have seen (window
// errors, unhandled promise rejections, the chat's bot lines). Nothing is sent
// anywhere until the button is pressed.

import { bus } from './bus.js';
import { askText } from './ask.js';
import { postJSON } from './api.js';
import { snapshotPNG } from './viewport.js';

const RING = 40;
const requests = [];
const reported = [];

function push(ring, item) {
  ring.push(item);
  if (ring.length > RING) ring.shift();
}

// Every call the tab makes, as the server saw it from this side. Wrapping
// fetch once here beats touching every call site, and catches the calls
// made before any module of ours ran a line.
function watchFetch() {
  const orig = window.fetch.bind(window);
  window.fetch = async (url, opts = {}) => {
    const rec = { t: new Date().toISOString(), method: opts.method || 'GET',
                  url: String(url),
                  body: typeof opts.body === 'string' ? opts.body.slice(0, 2000) : null };
    const t0 = performance.now();
    try {
      const r = await orig(url, opts);
      rec.status = r.status;
      return r;
    } catch (e) {
      rec.status = 'failed';
      rec.error = String(e);
      throw e;
    } finally {
      rec.ms = Math.round(performance.now() - t0);
      if (!rec.url.endsWith('/api/bug')) push(requests, rec);
    }
  };
}

function watchErrors() {
  window.addEventListener('error', (e) => push(reported, {
    t: new Date().toISOString(), kind: 'error',
    text: `${e.message} (${e.filename || '?'}:${e.lineno || '?'})`,
  }));
  window.addEventListener('unhandledrejection', (e) => push(reported, {
    t: new Date().toISOString(), kind: 'rejection', text: String(e.reason),
  }));
  // what the app itself told the user — warnings, refusals, recovery notes
  bus.on('msg', (who, text) => {
    if (who === 'bot') push(reported, { t: new Date().toISOString(), kind: 'chat', text: String(text).slice(0, 300) });
  });
}

async function report() {
  const note = await askText('What went wrong? One line is enough — the design, ' +
    'the last steps and a screenshot are saved with it.',
    { placeholder: 'e.g. the fillet made the box disappear', ok: 'Save report' });
  if (note === null) return;
  let screenshot = null;
  try { screenshot = snapshotPNG(); } catch (e) { /* no frame; the report still lands */ }
  const build = document.getElementById('sBuild');
  const d = await postJSON('/api/bug', {
    note, screenshot, requests, console: reported,
    ui_build: build ? build.textContent : '',
  }, 'saving the bug report…');
  if (!d || d.error) return;                    // postJSON already said why
  bus.emit('msg', 'bot', `🐞 Saved to ${d.saved}. Keep going — a later fix session reads that folder.`);
}

export function initBugReport() {
  watchFetch();
  watchErrors();
  const btn = document.getElementById('bugBtn');
  if (btn) btn.addEventListener('click', report);
}
