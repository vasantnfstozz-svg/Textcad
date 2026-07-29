// extrude.js — Fusion-style Extrude (v1). A non-modal panel with LIVE PREVIEW:
// it creates the extrude (and optional Join/Cut/Intersect) feature immediately
// and edits it in place through the verified rebuild as you change settings, so
// the 3D preview is always a real, checked solid. Cancel removes it; OK keeps.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh, beginExtrudeArrow, endExtrudeArrow,
         setExtrudeArrowAmount } from './viewport.js';

// plane normals = the direction a positive offset/extrude actually goes
// (probed against build123d: XZ offset +7 lands at y=-7, so XZ is -Y!)
const PLANE_N = { XY: [0, 0, 1], XZ: [0, -1, 0], YZ: [1, 0, 0] };
// sketch-local (u,v) + offset o -> world, per plane (probed)
const PLANE_MAP = {
  XY: (u, v, o) => [u, v, o],
  XZ: (u, v, o) => [u, -o, v],
  YZ: (u, v, o) => [o, u, v],
};

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
  // start tiny — the solid should grow when YOU pull the arrow, not jump to a
  // big default the moment the panel opens
  g('exDir').value = 'one'; g('exDist').value = '1'; g('exDist2').value = '10';
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

let warned = false;
function warnIfFailed(doc) {
  const f = (doc.features || []).find(x => x.id === st.extrudeId);
  if (f && f.status === 'failed' && !warned) {
    warned = true;
    bus.emit('msg', 'bot', `⚠ Extrude failed: ${(f.problems || []).join('; ')}`);
  } else if (f && f.status === 'ok') warned = false;
}

async function createPreview() {
  st.extrudeId = uid('extrude');
  warned = false;
  const doc = await postJSON('/api/feature/add',
    { id: st.extrudeId, op: 'extrude', params: params(), inputs: [st.profileId] });
  warnIfFailed(doc);
  await applyOp();
  loadMesh();
  placeArrow();
}

/* centroid of one entity in sketch-local coords */
function entLocalCenter(e) {
  const ox = e.x || 0, oy = e.y || 0;
  if (e.kind === 'polygon' && e.points && e.points.length) {
    const n = e.points.length;
    return [ox + e.points.reduce((s, p) => s + p[0], 0) / n,
            oy + e.points.reduce((s, p) => s + p[1], 0) / n];
  }
  if (e.kind === 'path' && e.start) {
    const pts = [e.start, ...(e.segments || []).map(s => s.to)];
    return [ox + pts.reduce((s, p) => s + p[0], 0) / pts.length,
            oy + pts.reduce((s, p) => s + p[1], 0) / pts.length];
  }
  return [ox, oy];
}

// put the drag arrow at the MIDDLE of the profile, perpendicular to its plane
function placeArrow() {
  const prof = feats().find(f => f.id === st.profileId);
  if (!prof) return;
  let O, N;
  if (prof.op === 'sketch_on_face') {
    O = prof.params.face_center || [0, 0, 0];
    N = prof.params.face_normal || [0, 0, 1];
  } else {
    const plane = prof.params.plane || 'XY';
    N = PLANE_N[plane] || [0, 0, 1];
    const off = Number(prof.params.offset) || 0;
    const ents = prof.params.entities || [];
    let u = 0, v = 0;
    if (ents.length) {
      for (const e of ents) { const c = entLocalCenter(e); u += c[0]; v += c[1]; }
      u /= ents.length; v /= ents.length;
    }
    O = (PLANE_MAP[plane] || PLANE_MAP.XY)(u, v, off);
  }
  beginExtrudeArrow(O, N, Number(g('exDist').value) || 1, onDrag, onDragCommit);
}

function onDrag(amount) {                 // live while dragging the arrow
  g('exDist').value = Math.round(amount * 100) / 100;
  applyThrottled();
}
function onDragCommit(amount) {           // final value on release
  g('exDist').value = Math.round(amount * 100) / 100;
  apply();
}

let inflight = false, pending = false;
async function applyThrottled() {         // one rebuild in flight; coalesce the rest
  if (inflight) { pending = true; return; }
  inflight = true;
  try { await apply(); } finally { inflight = false; }
  if (pending) { pending = false; applyThrottled(); }
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
  const pr = params();
  const doc = await postJSON('/api/feature/params',
    { feature_id: st.extrudeId, params: pr });
  warnIfFailed(doc);
  await applyOp();
  loadMesh();
  // keep the arrow length in sync when the value is typed (not while dragging)
  const signed = pr.flip ? -pr.amount : pr.amount;
  setExtrudeArrowAmount(signed);
}

async function changeProfile() {
  await teardown();
  st.profileId = g('exProfile').value;
  await createPreview();
}

async function teardown() {
  endExtrudeArrow();
  if (st && st.opId) await postJSON('/api/feature/remove', { feature_id: st.opId });
  if (st && st.extrudeId) await postJSON('/api/feature/remove', { feature_id: st.extrudeId });
  if (st) { st.opId = st.opType = st.opTarget = st.extrudeId = null; }
}

async function cancel() {
  await teardown(); loadMesh();
  st = null; panel().style.display = 'none';
}

function ok() {
  endExtrudeArrow();
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
