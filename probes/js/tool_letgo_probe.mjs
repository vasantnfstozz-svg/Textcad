/* Section 11 round three — the REAL static/js/tool.js run in node, to answer
   ONE question by measurement instead of by reading: can round two's
   'doc-updated' let-go (tabMoved) FALSE-FIRE while the user works normally on
   the SAME design?  The neighbours are stubs; tool.js, bus.js and state.js are
   the shipped bytes (copied next to this file by tool_letgo_probe.py).

   Run it with:  C:\Python314\python.exe probes/tool_letgo_probe.py          */
import { bus } from './bus.js';
import { S } from './state.js';
import { tool } from './tool.js';
import { calls, said } from './api.js';

const out = [];
const log = (name, o) => out.push({ case: name, ...o });

/* the fake DOM lives in boot.mjs: tool.js touches `window` at import time */
const els = globalThis.els;

const panelShown = () => document.getElementById('xPanel').style.display === 'block';

/* --- the smallest real tool --- */
const spec = {
  name: 'Probe', icon: '^', tool: 'extrude', panel: 'xPanel', ids: 'x',
  ops: { profile: 'extrude' },
  fields: { change: [], typed: [] },
  show() {}, params: () => ({ amount: 5 }), snapshot: f => ({ ...(f.params || {}) }),
  isEmpty: () => false, describe: () => '5 mm', nothing: 'nothing',
  gizmos: { begin() {}, end() {} },
};
const ctl = tool(spec);

const DOC = (tab, name, extra = {}) => ({
  active_tab: tab, name, ok: true,
  features: [
    { id: 's1', op: 'sketch', params: {}, inputs: [], volume: null },
    { id: 'plate1', op: 'plate', params: {}, inputs: [], volume: 1000, status: 'ok' },
  ],
  ...extra,
});

async function session(doc) {                 // open a panel on `doc`
  S.lastDoc = doc;
  S.modalTool = null;
  els.clear();
  calls.length = 0; said.length = 0;
  ctl.open('s1');
  await new Promise(r => setTimeout(r, 0));   // setupTool's plan
  return { opened: panelShown(), modal: S.modalTool, tab: ctl.st && ctl.st.tab,
           docName: ctl.st && ctl.st.docName };
}

function fire(doc) {                          // what the browser hears
  said.length = 0;
  const before = calls.length;
  bus.emit('doc-updated', doc);
  return { stillOpen: panelShown(), modal: S.modalTool,
           letGo: said.some(s => s.includes('let go')),
           posted: calls.slice(before).map(c => c[0]),
           said: said.slice() };
}

/* 1. a plain rebuild of the SAME design (the commonest doc-updated of all) */
let s = await session(DOC('t3', 'bracket'));
log('opened', s);
log('same design rebuilt', fire(DOC('t3', 'bracket', { rebuild_ms: 42 })));

/* 2. the tool's own write coming back */
log('own write', fire(DOC('t3', 'bracket', { geom_version: 9 })));

/* 3. Undo, then Redo (same tab, fewer/more features) */
log('undo', fire({ ...DOC('t3', 'bracket'), features: [] }));
log('redo', fire(DOC('t3', 'bracket')));

/* 4. RENAME — File > Save As, or a design saved under a new name.  Same tab
      id, different name.  A name key would false-fire here. */
log('renamed', fire(DOC('t3', 'my-bracket-v2')));

/* 5. a struck / unstruck feature */
log('feature struck', fire({ ...DOC('t3', 'my-bracket-v2'),
  features: [{ id: 's1', op: 'sketch', suppressed: true, inputs: [], volume: null }] }));

/* 6. a version restore (same tab, different content) */
log('version restored', fire({ ...DOC('t3', 'my-bracket-v2'), restored: 'v3' }));

/* 7. a doc-updated with NO active_tab at all (a partial payload) */
log('payload without a tab', fire({ name: 'bracket', features: [] }));

/* 8. THE REAL MOVE: another design took the tab (the MCP doorbell) */
log('another design arrived', fire(DOC('t7', 'arrives-from-mcp')));

/* 9. ...and a SECOND tab holding a design of the SAME NAME */
s = await session(DOC('t3', 'untitled'));
log('reopened on t3', s);
log('other tab, same name', fire(DOC('t4', 'untitled')));

/* 10. a tab RE-CREATED after a crash: same design, new tab id */
s = await session(DOC('t3', 'bracket'));
log('reopened again', s);
log('tab re-created (t3 -> t1)', fire(DOC('t1', 'bracket')));

/* 11. ...but a CRASH tells the panel first (server-recovered), so the let-go
       must not be the thing that speaks */
s = await session(DOC('t3', 'bracket'));
said.length = 0;
bus.emit('server-recovered', DOC('t1', 'bracket'));
const afterCrash = { closedByRecover: !panelShown(), modalAfterRecover: S.modalTool };
log('crash: server-recovered first', { ...afterCrash, ...fire(DOC('t1', 'bracket')) });

/* 12. S.lastDoc is null when the panel opens (boot race) */
S.lastDoc = null;
S.modalTool = null;
els.clear();
ctl.open('s1');
await new Promise(r => setTimeout(r, 0));
log('opened with no lastDoc', { tab: ctl.st && ctl.st.tab, opened: panelShown() });
if (panelShown()) log('no lastDoc, then a real move', fire(DOC('t7', 'other')));

console.log(JSON.stringify(out, null, 1));
