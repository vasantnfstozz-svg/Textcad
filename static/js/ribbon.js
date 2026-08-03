// ribbon.js — the tool tabs (File / Create / Sketch / Modify / Inspect) and
// the ribbon showing only the active tab's tools, Fusion-style.

import { S } from './state.js';
import { bus } from './bus.js';
import { OP_ICONS, TOOL_NAMES } from './icons.js';
import { openFeatDialog, actionNew, actionOpen, actionSave, actionExport,
         actionUndo, actionSpec, loadSample } from './dialogs.js';
import { openSketchEditor, finishSketch, cancelSketch,
         setSketchTool, sketchModify } from './sketcher.js';
import { openSettings } from './settings.js';
import { startPlacement, PLACEABLE } from './placement.js';
import { beginPlanePick } from './viewport.js';
import { lookAtSketch } from './sketch3d.js';
import { openExtrude, cancelExtrude } from './extrude.js';

// sketch draw tools shown in the contextual SKETCH tab's CREATE group (top)
const SKETCH_TOOLS = {
  path: { icon: '⌇', name: 'Line/Arc' },
  rectangle: { icon: '▭', name: 'Rectangle' },
  circle: { icon: '●', name: 'Circle' },
  regular_polygon: { icon: '⬡', name: 'Polygon' },
  slot: { icon: '⬭', name: 'Slot' },
  ellipse: { icon: '⬯', name: 'Ellipse' },
  trim: { icon: '✂', name: 'Trim' },        // modify, not create (see groups)
};
const SKETCH_CREATE = ['path', 'rectangle', 'circle', 'regular_polygon',
                       'slot', 'ellipse'];
let curSketchTool = null;      // which draw tool is active (for ribbon highlight)

// Create Sketch (Fusion): pick a plane or a planar face IN THE VIEWPORT, then
// enter sketch mode on it.
function startSketch() {
  cancelExtrude();                          // don't leave extrude gizmos eating clicks
  beginPlanePick((kind, data) => {
    if (kind === 'face') bus.emit('sketch-on-face', data);
    else openSketchEditor(data);            // data = 'XY' | 'XZ' | 'YZ'
  });
}

// named (non-op) actions that live in the ribbon
const ACTIONS = {
  new:     { icon: '🗋', name: 'New',         fn: actionNew },
  open:    { icon: '📂', name: 'Open',        fn: actionOpen },
  save:    { icon: '💾', name: 'Save',        fn: actionSave },
  export:  { icon: '⬇', name: 'Export STEP', fn: actionExport },
  undo:    { icon: '↶', name: 'Undo',        fn: actionUndo },
  spec:    { icon: '✓', name: 'Spec',        fn: actionSpec },
  select:  { icon: '◉', name: 'Select',
             fn: () => document.getElementById('vSelect').click() },
  settings: { icon: '⚙', name: 'Settings', fn: openSettings },
  newsketch: { icon: '✎', name: 'Create Sketch', fn: startSketch },
  finish_sketch: { icon: '✓', name: 'Finish Sketch', fn: finishSketch },
  cancel_sketch: { icon: '✕', name: 'Cancel Sketch', fn: cancelSketch },
  look_at: { icon: '⌖', name: 'Look At', fn: lookAtSketch },
  // sketch Modify tools (were side-panel buttons of the retired 2D editor)
  sk_mirror_v: { icon: '⇋', name: 'Mirror ↔', fn: () => sketchModify('mirror_v') },
  sk_mirror_h: { icon: '⇅', name: 'Mirror ↕', fn: () => sketchModify('mirror_h') },
  sk_duplicate: { icon: '⧉', name: 'Duplicate', fn: () => sketchModify('duplicate') },
  sk_offset: { icon: '⇢', name: 'Offset', fn: () => sketchModify('offset') },
  ex_flange:     { icon: '⚙', name: 'Flange',     fn: () => loadSample('flange') },
  ex_impeller:   { icon: '🌀', name: 'Impeller',   fn: () => loadSample('impeller') },
  ex_compressor: { icon: '💨', name: 'Compressor', fn: () => loadSample('compressor') },
};

// each tab -> list of [group-label, items]; an item is an op name or {a:action}.
// Fusion-style: Sketch is NOT a permanent tab — "Create Sketch" lives in the
// Create tab beside the sketch-consuming ops (Extrude/Revolve/Loft/Sweep).
const TABS = {
  File: [
    ['Design', [{ a: 'new' }, { a: 'open' }, { a: 'save' }, { a: 'export' }]],
    ['Examples', [{ a: 'ex_flange' }, { a: 'ex_impeller' }, { a: 'ex_compressor' }]],
    ['Preferences', [{ a: 'settings' }]],
  ],
  Create: [
    ['Create', [{ a: 'newsketch' }, 'extrude', 'revolve', 'loft', 'sweep']],
    ['Primitives', ['plate', 'disc', 'ball', 'cone', 'tube', 'polygon_plate',
                    'hex_plate']],
    ['Advanced', ['revolve_profile', 'curved_blade']],
  ],
  Modify: [
    ['Features', ['with_center_hole', 'with_bolt_circle', 'fillet', 'chamfer',
                  'shell']],
    ['Transform', ['move', 'rotate', 'scale', 'mirror']],
    ['Pattern', ['polar_pattern', 'linear_pattern']],
    ['Combine', ['fuse', 'cut', 'intersect']],
  ],
  Inspect: [
    ['Select', [{ a: 'select' }]],
    ['Verify', [{ a: 'spec' }]],
    ['History', [{ a: 'undo' }]],
  ],
};
const TAB_ORDER = ['File', 'Create', 'Modify', 'Inspect'];
let activeTab = 'Create';

// contextual groups shown ONLY while in sketch mode (Fusion's green SKETCH tab):
// the draw tools live in the top ribbon now, not a side palette.
const SKETCH_CONTEXT = [
  ['Create', SKETCH_CREATE.map(t => ({ t }))],
  ['Modify', [{ t: 'trim' }, { a: 'sk_mirror_v' }, { a: 'sk_mirror_h' },
              { a: 'sk_duplicate' }, { a: 'sk_offset' }]],
  ['View', [{ a: 'look_at' }]],
  ['Finish', [{ a: 'finish_sketch' }, { a: 'cancel_sketch' }]],
];
let sketchMode = false;

export function initRibbon() {
  bus.on('sketch-mode', ({ active }) => {
    sketchMode = active; curSketchTool = null; renderTabs(); renderRibbon();
  });
  bus.on('sketch-tool', ({ tool }) => {      // reflect the active tool up top
    curSketchTool = tool;
    if (sketchMode) renderRibbon();
  });
  renderTabs(); renderRibbon();
}

function renderTabs() {
  const strip = document.getElementById('tabstrip');
  strip.innerHTML = '';
  if (sketchMode) {                       // contextual: only the green SKETCH tab
    const b = document.createElement('button');
    b.className = 'tab active sketchctx';
    b.textContent = '✎ Sketch';
    strip.appendChild(b);
    return;
  }
  for (const name of TAB_ORDER) {
    const b = document.createElement('button');
    b.className = 'tab' + (name === activeTab ? ' active' : '');
    b.textContent = name;
    b.onclick = () => { activeTab = name; renderTabs(); renderRibbon(); };
    strip.appendChild(b);
  }
}

function renderRibbon() {
  const rb = document.getElementById('ribbon');
  rb.innerHTML = '';
  rb.classList.toggle('sketchctx', sketchMode);
  const groups = sketchMode ? SKETCH_CONTEXT : TABS[activeTab];
  for (const [label, items] of groups) {
    const g = document.createElement('div'); g.className = 'rgroup';
    const tools = document.createElement('div'); tools.className = 'rtools';
    for (const item of items) {
      const b = document.createElement('button'); b.className = 'rbtn';
      if (item.t) {                                   // a sketch draw tool
        const s = SKETCH_TOOLS[item.t];
        b.title = s.name;
        b.classList.toggle('active', curSketchTool === item.t);
        b.innerHTML = `<span class="rico">${s.icon}</span><span>${s.name}</span>`;
        b.onclick = () => setSketchTool(item.t);
      } else if (typeof item === 'object') {          // named action
        const a = ACTIONS[item.a];
        b.title = a.name;
        b.innerHTML = `<span class="rico">${a.icon}</span><span>${a.name}</span>`;
        b.onclick = a.fn;
      } else {                                        // an op
        b.title = item;
        b.innerHTML = `<span class="rico">${OP_ICONS[item] || '□'}</span>` +
                      `<span>${TOOL_NAMES[item] || item}</span>`;
        b.onclick = item === 'extrude' ? () => openExtrude()
          : PLACEABLE.includes(item) ? () => startPlacement(item)
          : () => openFeatDialog(item);
      }
      tools.appendChild(b);
    }
    const cap = document.createElement('div'); cap.className = 'rlabel';
    cap.textContent = label;
    g.append(tools, cap); rb.appendChild(g);
  }
}
