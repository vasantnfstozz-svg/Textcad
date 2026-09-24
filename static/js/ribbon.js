// ribbon.js — the tool tabs (File / Create / Sketch / Modify / Inspect) and
// the ribbon showing only the active tab's tools, Fusion-style.

import { S } from './state.js';
import { bus } from './bus.js';
import { OP_ICONS, TOOL_NAMES } from './icons.js';
import { openFeatDialog, actionNew, actionOpen, actionSave, actionExport, actionUndo, actionRedo, actionSpec, actionImportStl, modalGuard, actionExamples } from './dialogs.js';
import { finishSketch, cancelSketch,
         setSketchTool, sketchModify, editSketch,
         traceIntoSketch, openSketchEditor, openSketchOnFace } from './sketcher.js';
import { openSettings } from './settings.js';
import { startPlacement, PLACEABLE } from './placement.js';
import { beginPlanePick } from './viewport.js';
import { lookAtSketch } from './sketch3d.js';
import { openOffsetPlane } from './sketchplane.js';
import { openExtrude, openPressPull } from './extrude.js';
import { openRevolve } from './revolve.js';
import { openFillet, openChamfer } from './fillet.js';
import { openHole } from './hole.js';
import { openShell } from './shell.js';
import { openCircularPattern, openRectangularPattern } from './pattern.js';
import { openMirror } from './mirror.js';
import { openSweep } from './sweep.js';
import { openLoft } from './loft.js';
import { openMove, openRotate } from './move.js';
import { cancelTool } from './tool.js';
import { openMeasure, cancelMeasure } from './measure.js';
import { toggleSection } from './section.js';
import { toggleParams } from './params.js';

// sketch draw tools shown in the contextual SKETCH tab's CREATE group (top)
const SKETCH_TOOLS = {
  path: { icon: '⌇', name: 'Line/Arc' },
  // an OPEN chain (`closed: false`): the path a Sweep follows, no profile
  openpath: { icon: '⤳', name: 'Path' },
  rectangle: { icon: '▭', name: 'Rectangle' },
  circle: { icon: '●', name: 'Circle' },
  regular_polygon: { icon: '⬡', name: 'Polygon' },
  slot: { icon: '⬭', name: 'Slot' },
  ellipse: { icon: '⬯', name: 'Ellipse' },
  text: { icon: 'T', name: 'Text' },        // a word as glyph faces (specs/text-entity.md)
  trim: { icon: '✂', name: 'Trim' },        // modify, not create (see groups)
};
const SKETCH_CREATE = ['path', 'openpath', 'rectangle', 'circle', 'regular_polygon',
                       'slot', 'ellipse', 'text'];
let curSketchTool = null;      // which draw tool is active (for ribbon highlight)

// Create Sketch (Fusion): pick a plane or a planar face IN THE VIEWPORT, then
// enter sketch mode on it.
function startSketch() {
  cancelTool();                          // don't leave extrude gizmos eating clicks
  cancelMeasure();                          // nor a measure panel floating
  // select-then-command (fusion-parity rule 2): a selected offset plane row IS
  // the pick — Offset Plane selects the plane it just made, so Create Sketch
  // right after it opens there with no second click
  const sel = (S.lastDoc?.features || []).find(f => f.id === S.selected);
  if (sel && sel.op === 'offset_plane' && !sel.suppressed && sel.status === 'ok') {
    openSketchEditor(sel.id);
    bus.emit('select-feature', null);   // used up: the next Create Sketch picks again
    return;
  }
  // the pick: an origin plane, an offset plane (by its id) or a flat face
  beginPlanePick((kind, data) => (kind === 'face' ? openSketchOnFace(data)
                                                  : openSketchEditor(data)));
}

// the drag-handle tools (born on tool.js): pressed with the current selection
const TOOLS = { extrude: openExtrude, revolve: openRevolve, sweep: openSweep, loft: openLoft,
                press_pull: openPressPull,
                fillet: openFillet, chamfer: openChamfer, hole: openHole, shell: openShell,
                polar_pattern: openCircularPattern, linear_pattern: openRectangularPattern,
                mirror: openMirror, move: openMove, rotate: openRotate };

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
  section: { icon: '◫', name: 'Section',     fn: () => toggleSection() },   // cut the model open on screen
  parameters: { icon: '𝑥', name: 'Parameters', fn: () => toggleParams() },  // named values (wall = 3)
  select:  { icon: '◉', name: 'Select',
             fn: () => document.getElementById('vSelect').click() },
  settings: { icon: '⚙', name: 'Settings', fn: openSettings },
  newsketch: { icon: '✎', name: 'Create Sketch', fn: startSketch },
  trace_png: { icon: '🖼', name: 'Trace Image', fn: traceIntoSketch },
  import_stl_file: { icon: '📥', name: 'Import STL/STEP', fn: actionImportStl },
  finish_sketch: { icon: '✓', name: 'Finish Sketch', fn: finishSketch },
  cancel_sketch: { icon: '✕', name: 'Cancel Sketch', fn: cancelSketch },
  look_at: { icon: '⌖', name: 'Look At', fn: lookAtSketch },
  // Fusion's Construct > Offset Plane: a plane to sketch on, a distance from
  // an origin plane or a flat face (sketchplane.js)
  offset_plane: { icon: OP_ICONS.offset_plane, name: TOOL_NAMES.offset_plane,
                  fn: () => openOffsetPlane() },
  // sketch Modify tools (were side-panel buttons of the retired 2D editor)
  sk_mirror_v: { icon: '⇋', name: 'Mirror ↔', fn: () => sketchModify('mirror_v') },
  sk_mirror_h: { icon: '⇅', name: 'Mirror ↕', fn: () => sketchModify('mirror_h') },
  sk_duplicate: { icon: '⧉', name: 'Duplicate', fn: () => sketchModify('duplicate') },
  sk_offset: { icon: '⇢', name: 'Offset', fn: () => sketchModify('offset') },
  sk_scale: { icon: '⤢', name: 'Scale', fn: () => sketchModify('scale') },
  versions:      { icon: '⏱', name: 'Versions',
                   fn: () => bus.emit('versions-open') },
  examples:      { icon: '🗂', name: 'Examples',   fn: actionExamples },
};

// each tab -> list of [group-label, items]; an item is an op name or {a:action}.
// Fusion-style: Sketch is NOT a permanent tab — "Create Sketch" lives in the
// Create tab beside the sketch-consuming ops (Extrude/Revolve/Loft/Sweep).
const TABS = {
  File: [
    ['Design', [{ a: 'new' }, { a: 'open' }, { a: 'save' },
                { a: 'import_stl_file' }, { a: 'export' }]],
    ['Examples', [{ a: 'examples' }]],
    ['Preferences', [{ a: 'settings' }]],
  ],
  Create: [
    ['Create', [{ a: 'newsketch' },
                { a: 'import_stl_file' },
                'extrude', 'revolve', 'loft', 'sweep', 'hole']],
    ['Construct', [{ a: 'offset_plane' }]],
    // Sphere, Cone, Polygon and Turn profile have no button (user, 2026-09-24:
    // none of the 47 saved designs used the first three). Their ops stay, so
    // a design or an AI tree holding one still builds.
    ['Primitives', ['plate', 'disc', 'tube', 'hex_plate']],
  ],
  Modify: [
    // Press Pull first, as in Fusion: a router, not an op — the pick decides
    // whether it is Extrude (face / profile) or Fillet (edge), extrude.js
    ['Features', ['press_pull', 'with_center_hole', 'with_bolt_circle', 'fillet', 'chamfer',
                  'shell']],
    ['Transform', ['move', 'rotate', 'scale', 'mirror']],
    ['Pattern', ['polar_pattern', 'linear_pattern']],
    ['Parameters', [{ a: 'parameters' }]],
    ['Combine', ['fuse', 'cut', 'intersect']],
  ],
  Inspect: [
    ['Select', [{ a: 'select' }]],
    ['Measure', [{ a: 'measure' }]],
    ['Section', [{ a: 'section' }]],
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
  // a STRUCK sketch is not offered: its row's only actions are ↩ and ✕ until
  // it comes back (the selection now survives a strike, tree.js strikeFeature)
  const sketches = feats.filter(f => (f.op === 'sketch' || f.op === 'sketch_on_face')
                                     && !f.suppressed);
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
        b.onclick = guard(TOOLS[item] ? () => TOOLS[item]()
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
