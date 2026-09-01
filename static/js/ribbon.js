// ribbon.js — the tool tabs (File / Create / Sketch / Modify / Inspect) and
// the ribbon showing only the active tab's tools, Fusion-style.

import { S } from './state.js';
import { bus } from './bus.js';
import { OP_ICONS, TOOL_NAMES } from './icons.js';
import { openFeatDialog, actionNew, actionOpen, actionSave, actionExport, actionUndo, actionRedo, actionSpec, actionImportStl, loadSample, modalGuard, actionExamples } from './dialogs.js';
import { openSketchEditor, finishSketch, cancelSketch,
         setSketchTool, sketchModify, editSketch,
         traceIntoSketch } from './sketcher.js';
import { openSettings } from './settings.js';
import { startPlacement, PLACEABLE } from './placement.js';
import { beginPlanePick } from './viewport.js';
import { lookAtSketch } from './sketch3d.js';
import { openExtrude, cancelExtrude } from './extrude.js';
import { openMeasure, cancelMeasure } from './measure.js';

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
  cancelMeasure();                          // nor a measure panel floating
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
  redo:    { icon: '↷', name: 'Redo',        fn: actionRedo },
  spec:    { icon: '✓', name: 'Spec',        fn: actionSpec },
  measure: { icon: '⟺', name: 'Measure',     fn: () => openMeasure() },
  select:  { icon: '◉', name: 'Select',
             fn: () => document.getElementById('vSelect').click() },
  settings: { icon: '⚙', name: 'Settings', fn: openSettings },
  newsketch: { icon: '✎', name: 'Create Sketch', fn: startSketch },
  trace_png: { icon: '🖼', name: 'Trace Image', fn: traceIntoSketch },
  import_stl_file: { icon: '📥', name: 'Import STL/STEP', fn: actionImportStl },
  finish_sketch: { icon: '✓', name: 'Finish Sketch', fn: finishSketch },
  cancel_sketch: { icon: '✕', name: 'Cancel Sketch', fn: cancelSketch },
  look_at: { icon: '⌖', name: 'Look At', fn: lookAtSketch },
  // sketch Modify tools (were side-panel buttons of the retired 2D editor)
  sk_mirror_v: { icon: '⇋', name: 'Mirror ↔', fn: () => sketchModify('mirror_v') },
  sk_mirror_h: { icon: '⇅', name: 'Mirror ↕', fn: () => sketchModify('mirror_h') },
  sk_duplicate: { icon: '⧉', name: 'Duplicate', fn: () => sketchModify('duplicate') },
  sk_offset: { icon: '⇢', name: 'Offset', fn: () => sketchModify('offset') },
  sk_scale: { icon: '⤢', name: 'Scale', fn: () => sketchModify('scale') },
  versions:      { icon: '⏱', name: 'Versions',
                   fn: () => bus.emit('versions-open') },
  examples:      { icon: '🗂', name: 'Examples',   fn: actionExamples },
  ex_flange:     { icon: '⚙', name: 'Flange',     fn: () => loadSample('flange') },
  ex_impeller:   { icon: '🌀', name: 'Impeller',   fn: () => loadSample('impeller') },
  ex_compressor: { icon: '💨', name: 'Compressor', fn: () => loadSample('compressor') },
};

// each tab -> list of [group-label, items]; an item is an op name or {a:action}.
// Fusion-style: Sketch is NOT a permanent tab — "Create Sketch" lives in the
// Create tab beside the sketch-consuming ops (Extrude/Revolve/Loft/Sweep).
const TABS = {
  File: [
    ['Design', [{ a: 'new' }, { a: 'open' }, { a: 'save' },
                { a: 'import_stl_file' }, { a: 'export' }]],
    ['Examples', [{ a: 'examples' }, { a: 'ex_flange' },
                  { a: 'ex_impeller' }, { a: 'ex_compressor' }]],
    ['Preferences', [{ a: 'settings' }]],
  ],
  Create: [
    ['Create', [{ a: 'newsketch' },
                { a: 'import_stl_file' },
                'extrude', 'revolve', 'loft', 'sweep']],
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
    ['Measure', [{ a: 'measure' }]],
    ['Verify', [{ a: 'spec' }]],
    ['History', [{ a: 'undo' }, { a: 'redo' }, { a: 'versions' }]],
  ],
};
const TAB_ORDER = ['File', 'Create', 'Modify', 'Inspect'];
let activeTab = 'Create';

// contextual groups shown ONLY while in sketch mode (Fusion's green SKETCH tab):
// the draw tools live in the top ribbon now, not a side palette.
const SKETCH_CONTEXT = [
  ['Create', SKETCH_CREATE.map(t => ({ t }))],
  ['Modify', [{ t: 'trim' }, { a: 'sk_mirror_v' }, { a: 'sk_mirror_h' },
              { a: 'sk_duplicate' }, { a: 'sk_offset' }, { a: 'sk_scale' }]],
  // Fusion's Insert group: traced art becomes entities of THIS sketch —
  // auto-fitted to the face when the sketch sits on one
  ['Insert', [{ a: 'trace_png' }]],
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

/* Modify → Scale routes by what the user means: a SKETCH (selected in the
   tree, or the only sketch in the doc) opens the sketch editor straight
   into interactive drag-scale — users clicking "Scale" on a traced logo
   were landing in the generic factor dialog instead (reported 2026-08-21).
   Solids keep the scale-modifier dialog. */
async function smartScale() {
  const feats = S.lastDoc?.features || [];
  const sketches = feats.filter(f => f.op === 'sketch' || f.op === 'sketch_on_face');
  const f = feats.find(x => x.id === S.selected && sketches.includes(x))
         || (sketches.length === 1 && !S.selected ? sketches[0] : null);
  if (f) {
    await editSketch(f);
    sketchModify('scale');
    return;
  }
  openFeatDialog('scale');
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
      // one-command-at-a-time: every ribbon tool refuses while a tool panel
      // (e.g. Extrude) is open — OK/Cancel it first (user mandate 2026-08-05)
      const guard = fn => () => { if (!modalGuard()) fn(); };
      if (item.t) {                                   // a sketch draw tool
        const s = SKETCH_TOOLS[item.t];
        b.title = s.name;
        b.classList.toggle('active', curSketchTool === item.t);
        b.innerHTML = `<span class="rico">${s.icon}</span><span>${s.name}</span>`;
        b.onclick = guard(() => setSketchTool(item.t));
      } else if (typeof item === 'object') {          // named action
        const a = ACTIONS[item.a];
        b.title = a.name;
        b.innerHTML = `<span class="rico">${a.icon}</span><span>${a.name}</span>`;
        b.onclick = guard(a.fn);
      } else {                                        // an op
        b.title = item;
        b.innerHTML = `<span class="rico">${OP_ICONS[item] || '□'}</span>` +
                      `<span>${TOOL_NAMES[item] || item}</span>`;
        b.onclick = guard(item === 'extrude' ? () => openExtrude()
          : item === 'scale' ? () => smartScale()
          : PLACEABLE.includes(item) ? () => startPlacement(item)
          : () => openFeatDialog(item));
      }
      tools.appendChild(b);
    }
    const cap = document.createElement('div'); cap.className = 'rlabel';
    cap.textContent = label;
    g.append(tools, cap); rb.appendChild(g);
  }
}
