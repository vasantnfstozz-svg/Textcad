// extrude.js — Fusion-style Extrude (v1). A non-modal panel with LIVE PREVIEW:
// it creates the extrude (and optional Join/Cut/Intersect) feature immediately
// and edits it in place through the verified rebuild as you change settings, so
// the 3D preview is always a real, checked solid. Cancel removes it; OK keeps.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh } from './viewport.js';

const OPMAP = { join: 'fuse', cut: 'cut', intersect: 'intersect' };
const panel = () => document.getElementById('extrudeDialog');
let st = null;                    // active session
let timer = null;
const debounce = fn => { clearTimeout(timer); timer = setTimeout(fn, 200); };

const feats = () => (S.lastDoc && S.lastDoc.features) || [];
const isSketch = f => f.op === 'sketch' || f.op === 'sketch_on_face';
const solids = () => feats().filter(f => f.volume != null && !f.suppressed);
function uid(base) {
  const ex = new Set(feats().map(f => f.id));
  let n = 1; while (ex.has(base + n)) n++; return base + n;
}
function fill(id, items, val) {
  const s = document.getElementById(id);
  s.innerHTML = items.map(i => `<option value="${i}">${i}</option>`).join('');
  if (val != null) s.value = val;
}
const g = id => document.getElementById(id);

export function openExtrude(preProfile) {
  const sks = feats().filter(isSketch);
  if (!sks.length) {
    bus.emit('msg', 'bot', '⚠ Draw a sketch first (Create → Create Sketch), then Extrude it.');
    return;
  }
  const bods = solids();
  const profileId = preProfile && sks.some(s => s.id === preProfile) ? preProfile : sks[0].id;
  st = { sketches: sks.map(s => s.id), extrudeId: null, opId: null,
         opType: null, opTarget: null, profileId };
  fill('exProfile', st.sketches, profileId);
  fill('exTarget', bods.map(b => b.id), bods[0] ? bods[0].id : null);
  g('exDir').value = 'one'; g('exDist').value = '10'; g('exDist2').value = '10';
  g('exTaper').value = '0'; g('exFlip').checked = false; g('exOp').value = 'new';
  syncRows();
  panel().style.display = 'block';
  createPreview();
}

function params() {
  const dir = g('exDir').value;
  const d = Number(g('exDist').value) || 0;
  const d2 = Number(g('exDist2').value) || 0;
  const taper = Number(g('exTaper').value) || 0;
  const flip = g('exFlip').checked;
  if (dir === 'sym') return { amount: d, both: true, amount2: 0, taper, flip: false };
  if (dir === 'two') return { amount: d, both: false, amount2: d2, taper, flip };
  return { amount: d, both: false, amount2: 0, taper, flip };
}

function syncRows() {
  g('exDist2Row').style.display = g('exDir').value === 'two' ? '' : 'none';
  g('exTargetRow').style.display = g('exOp').value === 'new' ? 'none' : '';
}

async function createPreview() {
  st.extrudeId = uid('extrude');
  await postJSON('/api/feature/add',
    { id: st.extrudeId, op: 'extrude', params: params(), inputs: [st.profileId] });
  await applyOp();
  loadMesh();
}

async function applyOp() {
  const op = g('exOp').value;                 // new | join | cut | intersect
  const target = g('exTarget').value;
  if (st.opId && (op === 'new' || st.opType !== op || st.opTarget !== target)) {
    await postJSON('/api/feature/remove', { feature_id: st.opId });
    st.opId = st.opType = st.opTarget = null;
  }
  if (op !== 'new' && !st.opId && target) {
    st.opId = uid(st.extrudeId + '_' + op);
    st.opType = op; st.opTarget = target;
    await postJSON('/api/feature/add',
      { id: st.opId, op: OPMAP[op], inputs: [target, st.extrudeId] });
  }
}

async function apply() {
  if (!st || !st.extrudeId) return;
  await postJSON('/api/feature/params', { feature_id: st.extrudeId, params: params() });
  await applyOp();
  loadMesh();
}

async function changeProfile() {
  await teardown();
  st.profileId = g('exProfile').value;
  await createPreview();
}

async function teardown() {
  if (st && st.opId) await postJSON('/api/feature/remove', { feature_id: st.opId });
  if (st && st.extrudeId) await postJSON('/api/feature/remove', { feature_id: st.extrudeId });
  if (st) { st.opId = st.opType = st.opTarget = st.extrudeId = null; }
}

async function cancel() {
  await teardown(); loadMesh();
  st = null; panel().style.display = 'none';
}

function ok() {
  st = null; panel().style.display = 'none';
  bus.emit('msg', 'bot', 'Extrude created — editable in the feature tree.');
}

export function initExtrude() {
  g('exProfile').onchange = changeProfile;
  for (const id of ['exDir', 'exOp', 'exTarget', 'exFlip'])
    g(id).onchange = () => { syncRows(); apply(); };
  for (const id of ['exDist', 'exDist2', 'exTaper'])
    g(id).oninput = () => debounce(apply);
  g('exCancel').onclick = cancel;
  g('exOk').onclick = ok;
}
