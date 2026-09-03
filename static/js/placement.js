// placement.js — click-to-place for Create primitives. Instead of a blocking
// dialog, you pick the primitive, click a point on the ground (Z=0), and it is
// created there (its CENTER at the click). A small modeless popup then lets you
// fine-tune the dimensions and position live; everything stays editable in the
// feature tree afterwards.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON } from './api.js';
import { beginPlacement, loadMesh, cancelPlanePick } from './viewport.js';
import { cancelTool } from './tool.js';

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

function nextId(op) {
  const existing = new Set((S.lastDoc?.features || []).map(f => f.id));
  let n = 1;
  while (existing.has(op + n)) n++;
  return op + n;
}

async function createAt(op, x, y) {
  const id = nextId(op);
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

let timer = null;
function debounce(fn) { clearTimeout(timer); timer = setTimeout(fn, 250); }

function openPlacePopup(st) {
  const el = popup();
  const field = (label, key, val, onIn) => {
    const wrap = document.createElement('label');
    wrap.className = 'pp-field';
    wrap.innerHTML = `<span>${label}</span>`;
    const inp = document.createElement('input');
    inp.type = 'number'; inp.step = 'any'; inp.value = val;
    inp.oninput = () => onIn(inp.value);
    wrap.appendChild(inp); return wrap;
  };

  el.innerHTML = '';
  const head = document.createElement('div'); head.className = 'pp-head';
  head.innerHTML = `<b>${st.op}</b> <span class="pp-id">${st.id}</span>`;
  el.appendChild(head);

  const dimBox = document.createElement('div'); dimBox.className = 'pp-grid';
  for (const k of Object.keys(st.dims))
    dimBox.appendChild(field(`${k} (mm)`, k, st.dims[k], v => {
      st.dims[k] = Number(v) || 0;
      debounce(() => applyDims(st));
    }));
  el.appendChild(dimBox);

  const posHead = document.createElement('div'); posHead.className = 'pp-sub';
  posHead.textContent = 'Position (mm)'; el.appendChild(posHead);
  const posBox = document.createElement('div'); posBox.className = 'pp-grid';
  for (const axis of ['x', 'y', 'z'])
    posBox.appendChild(field(axis, axis, st.pos[axis], v => {
      st.pos[axis] = Number(v) || 0;
      debounce(() => applyPos(st));
    }));
  el.appendChild(posBox);

  const foot = document.createElement('div'); foot.className = 'pp-foot';
  const done = document.createElement('button'); done.className = 'primary';
  done.textContent = 'Done'; done.onclick = closePlacePopup;
  foot.appendChild(done); el.appendChild(foot);

  el.style.display = 'block';
}

export function closePlacePopup() {
  const el = popup(); el.style.display = 'none'; el.innerHTML = '';
}

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
