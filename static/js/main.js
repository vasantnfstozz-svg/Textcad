// main.js — boot: wire every module up, load the initial document, and run
// the live watcher that picks up designs arriving from outside (e.g. MCP).

import { bus } from './bus.js';
import { S } from './state.js';
import { getJSON, isBusy } from './api.js';
import { initViewport, loadMesh } from './viewport.js';
import './tree.js';            // subscribes to doc-updated
import './provenance.js';     // face pick -> which feature made it
import './doctabs.js';         // subscribes to doc-updated
import { initChat, addMsg } from './chat.js';
import { initDialogs, actionUndo } from './dialogs.js';
import { initSketcher } from './sketcher.js';
import { initRibbon } from './ribbon.js';
import { initSplitters } from './splitters.js';
import { initSettings } from './settings.js';
import { initExtrude } from './extrude.js';

initSettings();          // load prefs before anything renders (fmtVol/fmtLen)
initViewport();
initChat();
initDialogs();
initSketcher();
initExtrude();
initRibbon();
initSplitters();

/* keyboard shortcuts */
window.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'z'
      && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault(); actionUndo();
  }
});

/* live watcher: if a design arrives from outside (e.g. an AI over MCP) or the
   doc changes in another window, pop it up here. */
function docSig(d) {
  return d ? `${d.active_tab}|${d.name}|${d.features.length}|${d.rebuild_ms}|${d.ok}`
           : '';
}
setInterval(async () => {
  if (isBusy()) return;                              // don't fight an edit
  if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
  try {
    const d = await getJSON('/api/doc');
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
