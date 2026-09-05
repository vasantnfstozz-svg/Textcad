// main.js — boot: wire every module up, load the initial document, and run
// the live watcher that picks up designs arriving from outside (e.g. MCP).

import { bus } from './bus.js';
import { S } from './state.js';
import { getJSON, isBusy, noteRecovery } from './api.js';
import { initViewport, loadMesh } from './viewport.js';
import { initTreeFind } from './tree.js';  // + the find box
import './provenance.js';     // face pick -> which feature made it
import './doctabs.js';         // subscribes to doc-updated
import { initChat, addMsg } from './chat.js';
import { initDialogs, actionUndo, actionRedo } from './dialogs.js';
import { initSketcher } from './sketcher.js';
import { initRibbon } from './ribbon.js';
import { initSplitters } from './splitters.js';
import { initSettings } from './settings.js';
import { initExtrude } from './extrude.js';
import { initRevolve } from './revolve.js';
import { initFillet } from './fillet.js';
import { initMeasure } from './measure.js';
import { initVersions } from './versions.js';

initSettings();          // load prefs before anything renders (fmtVol/fmtLen)
initViewport();
initChat();
initDialogs();
initSketcher();
initExtrude();
initRevolve();
initFillet();     // Fillet + Chamfer on picked edges
initMeasure();    // the Measure tool (face/edge dimensions)
initRibbon();
initSplitters();
initVersions();   // version tree under the feature tree
initTreeFind();   // the feature-tree find box

/* Stamp the build this tab is running. A tab left open across a code
   change keeps its old modules in memory whatever the server sends, and
   a stale tab is indistinguishable from a real bug — it cost a whole
   round trip of 'the zoom is broken' when the zoom on disk was fine. */
try {
  const v = new URL(import.meta.url).searchParams.get('v');
  const el = document.getElementById('sBuild');
  if (el && v) el.textContent = 'ui v' + v;
} catch (e) { /* a build stamp must never break the app */ }

/* keyboard shortcuts */
window.addEventListener('keydown', e => {
  if (document.activeElement.tagName === 'INPUT') return;
  const mod = e.ctrlKey || e.metaKey;
  if (!mod) return;
  const k = e.key.toLowerCase();
  // Ctrl+Shift+Z and Ctrl+Y are both "redo" — Windows apps use Ctrl+Y, the
  // rest of the world Ctrl+Shift+Z, and guessing wrong is a silent no-op.
  if (k === 'z' && e.shiftKey) { e.preventDefault(); actionRedo(); }
  else if (k === 'y') { e.preventDefault(); actionRedo(); }
  else if (k === 'z') { e.preventDefault(); actionUndo(); }
});

/* live watcher: if a design arrives from outside (e.g. an AI over MCP) or the
   doc changes in another window, pop it up here. */
function docSig(d) {
  return d ? `${d.active_tab}|${d.name}|${d.features.length}|${d.rebuild_ms}|${d.ok}`
           : '';
}
setInterval(async () => {
  if (isBusy()) return;                              // don't fight an edit
  try {
    const d = await getJSON('/api/doc');
    // A crash is not an external change, so it is checked BEFORE the typing
    // guard below: a tool panel's own number box is an INPUT, and testing that
    // first hid the crash from the very panel that had to hear about it.
    if (noteRecovery(d)) {          // speaks, and open tool panels let go
      bus.emit('doc-updated', d);   // the restored document is what was already
      loadMesh();                   // on screen: keep the camera and the pick
      return;
    }
    // Typing in a field: don't yank an EXTERNAL change out from under the
    // keystroke (a design arriving over MCP, another window's edit).
    if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
    if (docSig(d) !== docSig(S.lastDoc)) {
      const newTab = !S.lastDoc || d.active_tab !== S.lastDoc.active_tab;
      bus.emit('doc-updated', d);
      loadMesh(newTab);
      if (newTab) addMsg('bot',
        `📡 "${d.name}" just arrived (designed externally, e.g. via MCP) — loaded it.`);
    }
  } catch (e) { /* server briefly busy */ }
}, 3000);

/* boot */
const doc = await getJSON('/api/doc');
bus.emit('doc-updated', doc);
loadMesh(true);
addMsg('bot', 'Welcome to TextCAD Studio.\n' +
  '• Describe a part to design it from scratch (opens in a new tab)\n' +
  '• Ask for changes ("make the bore 12mm")\n' +
  '• Or build manually: Create tab → Create Sketch, primitives, Extrude… — every path is verified.');
/* A crash note older than a few minutes is history to a freshly opened page;
   a recent one (the user hit F5 while Studio was restarting) is still news. */
if (doc.recovery && Date.now() / 1000 - doc.recovery.at > 300) S.recoveredAt = doc.recovery.at;
noteRecovery(doc);
