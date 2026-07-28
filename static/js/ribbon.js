// ribbon.js — the tool tabs (File / Create / Sketch / Modify / Inspect) and
// the ribbon showing only the active tab's tools, Fusion-style.

import { S } from './state.js';
import { bus } from './bus.js';
import { OP_ICONS, TOOL_NAMES } from './icons.js';
import { openFeatDialog, actionNew, actionOpen, actionSave, actionExport,
         actionUndo, actionSpec, loadSample } from './dialogs.js';
import { openSketchEditor } from './sketcher.js';

// The Sketch tool: if a flat face is currently picked in the viewport, sketch
// ON that face (Fusion-style: select a surface, then sketch on it). Otherwise
// open a blank plane sketch.
function startSketch() {
  if (S.pickedFace) bus.emit('sketch-on-face', S.pickedFace);
  else openSketchEditor();
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
  ex_flange:     { icon: '⚙', name: 'Flange',     fn: () => loadSample('flange') },
  ex_impeller:   { icon: '🌀', name: 'Impeller',   fn: () => loadSample('impeller') },
  ex_compressor: { icon: '💨', name: 'Compressor', fn: () => loadSample('compressor') },
};

// each tab -> list of [group-label, items]; an item is an op name or {a:action}
const TABS = {
  File: [
    ['Design', [{ a: 'new' }, { a: 'open' }, { a: 'save' }, { a: 'export' }]],
    ['Examples', [{ a: 'ex_flange' }, { a: 'ex_impeller' }, { a: 'ex_compressor' }]],
  ],
  Create: [
    ['Primitives', ['plate', 'disc', 'ball', 'cone', 'tube', 'hex_plate',
                    'polygon_plate']],
    ['From profile', ['revolve_profile', 'curved_blade']],
  ],
  Sketch: [
    ['Sketch', ['sketch']],
    ['From sketch', ['extrude', 'revolve', 'loft', 'sweep']],
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
const TAB_ORDER = ['File', 'Create', 'Sketch', 'Modify', 'Inspect'];
let activeTab = 'Create';

export function initRibbon() { renderTabs(); renderRibbon(); }

function renderTabs() {
  const strip = document.getElementById('tabstrip');
  strip.innerHTML = '';
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
  for (const [label, items] of TABS[activeTab]) {
    const g = document.createElement('div'); g.className = 'rgroup';
    const tools = document.createElement('div'); tools.className = 'rtools';
    for (const item of items) {
      const b = document.createElement('button'); b.className = 'rbtn';
      if (typeof item === 'object') {                 // named action
        const a = ACTIONS[item.a];
        b.title = a.name;
        b.innerHTML = `<span class="rico">${a.icon}</span><span>${a.name}</span>`;
        b.onclick = a.fn;
      } else {                                        // an op
        b.title = item;
        b.innerHTML = `<span class="rico">${OP_ICONS[item] || '□'}</span>` +
                      `<span>${TOOL_NAMES[item] || item}</span>`;
        b.onclick = item === 'sketch' ? startSketch
                                      : () => openFeatDialog(item);
      }
      tools.appendChild(b);
    }
    const cap = document.createElement('div'); cap.className = 'rlabel';
    cap.textContent = label;
    g.append(tools, cap); rb.appendChild(g);
  }
}
