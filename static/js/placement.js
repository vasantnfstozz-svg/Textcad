// placement.js — click-to-place for Create primitives. Instead of a blocking
// dialog, you pick the primitive, click a point on the ground (Z=0), and it is
// created there (its CENTER at the click). A small modeless popup then lets you
// fine-tune the dimensions and position live; everything stays editable in the
// feature tree afterwards.

import { bus } from './bus.js';
import { postJSON } from './api.js';
import { beginPlacement, loadMesh, cancelPlanePick } from './viewport.js';
import { cancelTool, uid } from './tool.js';
import { SETTINGS, toMm, fmtLen, unitLabel } from './settings.js';

// sensible starting dimensions (mm) per primitive — blocks have no defaults
const DEFAULTS = {
  plate: { width: 40, depth: 40, thickness: 10 },
  disc: { radius: 20, thickness: 10 },
  ball: { radius: 20 },
  cone: { bottom_radius: 20, top_radius: 10, height: 30 },
  tube: { outer_radius: 20, inner_radius: 10, height: 30 },
  polygon_plate: { sides: 6, circumradius: 20, thickness: 10 },
  hex_plate: { across_flats: 30, thickness: 10 },
};
export const PLACEABLE = Object.keys(DEFAULTS);

const popup = () => document.getElementById('placePopup');

export function startPlacement(op) {
  cancelPlanePick();                       // a pending plane-pick must not linger
  cancelTool();                         // a lingering extrude gizmo would eat clicks
  closePlacePopup();                       // clear any stale popup from before
  beginPlacement(op, (x, y) => createAt(op, x, y));
}

async function createAt(op, x, y) {
  const id = uid(op);
  const dims = { ...DEFAULTS[op] };
  const doc = await postJSON('/api/feature/add', { id, op, params: dims, inputs: [] });
  if (doc.error) { bus.emit('msg', 'bot', '⚠ ' + doc.error); return; }
  let posId = null;
  const pos = { x, y, z: 0 };
  if (x !== 0 || y !== 0) {
    posId = id + '_at';
    await postJSON('/api/feature/add',
      { id: posId, op: 'move', params: { ...pos }, inputs: [id] });
  }
  loadMesh(doc.features.length <= 2);      // fit on the very first shape
  openPlacePopup({ op, id, dims, pos, posId });
}

/* ---------------- the modeless placement popup ---------------- */

/* ONE timer per destination, not one for the whole popup. With a single timer,
   typing a thickness and then touching x within 250 ms cleared the pending
   applyDims and it never ran: the popup kept showing the new thickness and the
   document kept the old one (section 5 review, 2026-09-10). */
const timers = {};
function debounce(key, fn) {
  clearTimeout(timers[key]);
  timers[key] = setTimeout(fn, 250);
}

/* Which of a primitive's params is a LENGTH. Everything in DEFAULTS above is
   a millimetre except polygon_plate's `sides`, which is a COUNT — and the
   popup labelled every box "(mm)", `sides` included, until 2026-09-19. */
const COUNTS = new Set(['sides']);

/* The LENGTH boxes of the popup that is open, so the display unit can be
   changed under it: it takes no modal lock (Settings is a ribbon action and
   modalGuard only refuses those for a tool holding the lock), which makes this
   the second panel — after Section view — whose numbers have to be rewritten
   under the user's hands. Each entry knows how to read its own millimetres
   back out of the state. */
let liveBoxes = null;

/* a length in mm -> what the box shows, the way every tool panel writes one:
   millimetres keep the number itself, another unit is quantised to the box's
   own precision (settings.js `fmtLen`) */
const shown = v => SETTINGS.unit === 'mm' ? v : fmtLen(v, false);

function openPlacePopup(st) {
  const el = popup();
  const boxes = [];
  /* `kind`: 'len' a length that names its own unit, 'pos' a length the
     Position heading names for it, 'count' a plain number that is neither.
     A length is typed in the DISPLAY unit like every other model dimension in
     the app, and settings.js writes the word (data-unit) — a box labelled mm
     that is read in inches is how a 2 becomes 50.8 (static/index.html). */
  const field = (name, kind, val, onIn, read) => {
    const wrap = document.createElement('label');
    wrap.className = 'pp-field';
    // the word is written NOW (unitLabel) and marked `data-unit` so it is
    // repainted later: settings.js only walks the page when the unit CHANGES,
    // so a span built afterwards that spelled "mm" would keep saying mm for
    // as long as the popup stayed open in inches
    wrap.innerHTML = kind === 'len'
      ? `<span>${name} (<span data-unit>${unitLabel()}</span>)</span>`
      : `<span>${name}</span>`;
    const inp = document.createElement('input');
    inp.type = 'number'; inp.step = 'any';
    inp.value = kind === 'count' ? val : shown(val);
    inp.oninput = () => onIn(inp.value);
    wrap.appendChild(inp);
    if (kind !== 'count') boxes.push({ inp, read });
    return wrap;
  };

  el.innerHTML = '';
  const head = document.createElement('div'); head.className = 'pp-head';
  head.innerHTML = `<b>${st.op}</b> <span class="pp-id">${st.id}</span>`;
  el.appendChild(head);

  // A half-typed field is not a dimension. `Number(v) || 0` turned a cleared
  // box (and the lone '-' of a negative number) into 0, which the server then
  // refused as a zero thickness — so clearing a field to retype it flashed a
  // failed feature. An unparseable box simply waits for the rest.
  const num = v => { const n = Number(v); return v !== '' && isFinite(n) ? n : null; };

  const dimBox = document.createElement('div'); dimBox.className = 'pp-grid';
  for (const k of Object.keys(st.dims)) {
    const isLen = !COUNTS.has(k);
    dimBox.appendChild(field(k, isLen ? 'len' : 'count', st.dims[k], v => {
      const n = num(v);
      if (n === null) return;
      st.dims[k] = isLen ? toMm(n) : n;
      debounce('dims', () => applyDims(st));
    }, () => st.dims[k]));
  }
  el.appendChild(dimBox);

  // x / y / z are labelled plain, so this heading is the only thing that names
  // the unit they are typed in — it has to follow the display unit too
  const posHead = document.createElement('div'); posHead.className = 'pp-sub';
  posHead.innerHTML = `Position (<span data-unit>${unitLabel()}</span>)`;
  el.appendChild(posHead);
  const posBox = document.createElement('div'); posBox.className = 'pp-grid';
  for (const axis of ['x', 'y', 'z'])
    posBox.appendChild(field(axis, 'pos', st.pos[axis], v => {
      const n = num(v);
      if (n === null) return;
      st.pos[axis] = toMm(n);
      debounce('pos', () => applyPos(st));
    }, () => st.pos[axis]));
  el.appendChild(posBox);

  const foot = document.createElement('div'); foot.className = 'pp-foot';
  const done = document.createElement('button'); done.className = 'primary';
  done.textContent = 'Done'; done.onclick = closePlacePopup;
  foot.appendChild(done); el.appendChild(foot);

  liveBoxes = boxes;
  el.style.display = 'block';
}

export function closePlacePopup() {
  liveBoxes = null;
  const el = popup(); el.style.display = 'none'; el.innerHTML = '';
}

/* The display unit changed with the popup open — the fourth handler of this
   event (settings.js repaints every [data-unit] label, the tree redraws, the
   section panel rewrites its offset). The millimetres are the STATE's, never
   the box's: re-reading a box under the NEW unit would leave the number alone
   and silently multiply what it means, which is the bug section.js carries a
   comment about. The labels need nothing here — paintUnitLabels walks the
   whole page, this popup included. */
bus.on('settings-changed', () => {
  if (!liveBoxes) return;
  for (const b of liveBoxes) b.inp.value = shown(b.read());
});

async function applyDims(st) {
  await postJSON('/api/feature/params', { feature_id: st.id, params: st.dims });
}

async function applyPos(st) {
  if (!st.posId) {                         // create the move lazily on first use
    if (st.pos.x === 0 && st.pos.y === 0 && st.pos.z === 0) return;
    st.posId = st.id + '_at';
    await postJSON('/api/feature/add',
      { id: st.posId, op: 'move', params: { ...st.pos }, inputs: [st.id] });
  } else {
    await postJSON('/api/feature/params',
      { feature_id: st.posId, params: { ...st.pos } });
  }
}
