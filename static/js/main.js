// main.js — boot: wire every module up, load the initial document, and run
// the live watcher that picks up designs arriving from outside (e.g. MCP).

import { bus } from './bus.js';
import { S } from './state.js';
import { getJSON, isBusy, noteArrival, noteRecovery } from './api.js';
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
import { initSweep } from './sweep.js';
import { initLoft } from './loft.js';
import { initFillet } from './fillet.js';
import { initHole } from './hole.js';
import { initShell } from './shell.js';
import { initPattern } from './pattern.js';
import { initMirror } from './mirror.js';
import { initMove } from './move.js';
import { initMeasure } from './measure.js';
import { initVersions } from './versions.js';
import { initBugReport } from './bugreport.js';

initSettings();          // load prefs before anything renders (fmtVol/fmtLen)
initBugReport();         // first, so its request ring sees the boot calls too
initViewport();
initChat();
initDialogs();
initSketcher();
initExtrude();
initRevolve();
initSweep();      // Sweep: a profile along a path sketch (Tier 2, specs/sweep.md)
initLoft();       // Loft: two or more profiles blended (Tier 2, specs/loft.md)
initFillet();     // Fillet + Chamfer on picked edges
initHole();       // Hole at the point clicked on a flat face
initShell();      // Shell: walls of one thickness, the clicked faces open
initPattern();    // Circular + Rectangular Pattern of a feature or a body
initMirror();     // Mirror of a feature or a body across a face / an origin plane / a mid-plane
initMove();       // Move (three arrows) and Rotate (a ring through the body's centre)
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
      // a different design is on screen, so the camera starts fresh; WHETHER
      // it arrived from outside is the server's one-shot marker, not this
      // comparison (noteArrival)
      const newTab = !S.lastDoc || d.active_tab !== S.lastDoc.active_tab;
      bus.emit('doc-updated', d);
      loadMesh(newTab);
    }
    /* OUTSIDE that `if` on purpose (review of 6b4c494). The doorbell is the
       server's fact, so it may not hang off a signature the browser computes:
       an MCP redelivery of a design whose bytes did not change reuses the open
       tab WITHOUT rebuilding, so name, feature count, rebuild_ms and ok all
       stay put and the banner the server had ready was never spoken. It also
       left the marker owed for its whole ten minutes, to be announced later
       over some unrelated change. noteArrival carries its own two guards.
       It now SWITCHES to the arriving design as well as announcing it (the
       answer names the tab it is about, so nothing drags this page along any
       more), and the tree comes with that switch — only the viewport has to
       be told, and only when the follow really happened. */
    if (await noteArrival(d)) loadMesh(true);
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
/* A design that arrived while no page was open is still news — once. The
   server drops it if nobody came for it, and forgets it the moment this page
   says it, so a reload never repeats it. */
if (await noteArrival(doc)) loadMesh(true);
