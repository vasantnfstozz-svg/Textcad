// extrude.js — Fusion-style Extrude (v1). A non-modal panel with LIVE PREVIEW:
// it creates the extrude (and optional Join/Cut/Intersect) feature immediately
// and edits it in place through the verified rebuild as you change settings, so
// the 3D preview is always a real, checked solid. Cancel removes it; OK keeps.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh, beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginExtrudeGhost, setExtrudeGhost, hideExtrudeGhost,
         endExtrudeGhost } from './viewport.js';

// plane normals = the direction a positive offset/extrude actually goes
// (probed against build123d: XZ offset +7 lands at y=-7, so XZ is -Y!)
const PLANE_N = { XY: [0, 0, 1], XZ: [0, -1, 0], YZ: [1, 0, 0] };
// sketch-local (u,v) + offset o -> world, per plane (probed)
const PLANE_MAP = {
  XY: (u, v, o) => [u, v, o],
  XZ: (u, v, o) => [u, -o, v],
  YZ: (u, v, o) => [o, u, v],
};
// full frame per plane for the ghost box (x_dir/y_dir = local axes in world)
const PLANE_FRAME = {
  XY: o => ({ origin: [0, 0, o], x_dir: [1, 0, 0], y_dir: [0, 1, 0], z_dir: [0, 0, 1] }),
  XZ: o => ({ origin: [0, -o, 0], x_dir: [1, 0, 0], y_dir: [0, 0, 1], z_dir: [0, -1, 0] }),
  YZ: o => ({ origin: [o, 0, 0], x_dir: [0, 1, 0], y_dir: [0, 0, 1], z_dir: [1, 0, 0] }),
};

/* conservative bbox of one entity in sketch-local coords */
function entLocalBBox(e) {
  const x = e.x || 0, y = e.y || 0;
  const pts = p => p.reduce((b, q) => ({
    minX: Math.min(b.minX, x + q[0]), maxX: Math.max(b.maxX, x + q[0]),
    minY: Math.min(b.minY, y + q[1]), maxY: Math.max(b.maxY, y + q[1]) }),
    { minX: 1e9, maxX: -1e9, minY: 1e9, maxY: -1e9 });
  if (e.kind === 'polygon' && e.points) return pts(e.points);
  if (e.kind === 'path' && e.start)
    return pts([e.start, ...(e.segments || []).flatMap(s => s.via ? [s.via, s.to] : [s.to])]);
  let rx = 1, ry = 1;
  if (e.kind === 'circle') rx = ry = e.r || 1;
  else if (e.kind === 'regular_polygon') rx = ry = e.radius || 1;
  else if (e.kind === 'ellipse') { rx = e.rx || 1; ry = e.ry || 1; }
  else if (e.kind === 'rectangle') { rx = (e.w || 1) / 2; ry = (e.h || 1) / 2; }
  else if (e.kind === 'slot') { rx = (e.length || 1) / 2; ry = (e.height || 1) / 2; }
  const r = Math.max(rx, ry);                    // rotation-safe (conservative)
  const rot = e.rotation ? r : 0;
  return { minX: x - (rot || rx), maxX: x + (rot || rx),
           minY: y - (rot || ry), maxY: y + (rot || ry) };
}

function profileBBox(entities) {
  const b = { minX: 1e9, maxX: -1e9, minY: 1e9, maxY: -1e9 };
  for (const e of entities || []) {
    const eb = entLocalBBox(e);
    b.minX = Math.min(b.minX, eb.minX); b.maxX = Math.max(b.maxX, eb.maxX);
    b.minY = Math.min(b.minY, eb.minY); b.maxY = Math.max(b.maxY, eb.maxY);
  }
  return b.minX > b.maxX ? { minX: -10, maxX: 10, minY: -10, maxY: 10 } : b;
}

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
  const bods = solids();
  // FACE MODE (Fusion: click a planar face, press Extrude, pull the arrow).
  // Capture the pick now — loadMesh() clears it.
  const face = S.pickedFace;
  const tip = [...feats()].reverse().find(f => f.volume != null && !f.suppressed);
  if (face && tip) {
    st = { mode: 'face', face: { center: face.center, normal: face.normal || [0, 0, 1] },
           inputId: tip.id, extrudeId: null, opId: null, opType: null, opTarget: null };
    fill('exProfile', ['(selected face)'], '(selected face)');
    g('exProfile').disabled = true;
    fill('exTarget', bods.map(b => b.id), tip.id);
    g('exDir').value = 'one'; g('exDist').value = '1'; g('exDist2').value = '10';
    g('exTaper').value = '0'; g('exFlip').checked = false;
    g('exOp').value = 'join';            // pulling a face usually grows the body
    g('exDir').disabled = true;          // face extrude is one-directional (drag ± instead)
    syncRows();
    panel().style.display = 'block';
    createPreview();
    return;
  }
  // only UNCONSUMED sketches are offered — a sketch already used by an extrude
  // must not silently become the profile again ("goes back to the old sketch").
  // An explicit preProfile (tree ⬆ action) is honoured even if consumed.
  const consumed = new Set(feats().flatMap(f => f.inputs));
  const sks = feats().filter(isSketch)
    .filter(s => !consumed.has(s.id) || s.id === preProfile);
  if (!sks.length) {
    bus.emit('msg', 'bot', tip
      ? '⚠ Nothing selected to extrude. Pick a flat face of the body first ' +
        '(◉ Select → click a face → Extrude), or draw a new sketch.'
      : '⚠ Draw a sketch first (Create → Create Sketch), then Extrude it.');
    return;
  }
  const profileId = preProfile && sks.some(s => s.id === preProfile) ? preProfile : sks[0].id;
  st = { mode: 'sketch', sketches: sks.map(s => s.id), extrudeId: null, opId: null,
         opType: null, opTarget: null, profileId };
  fill('exProfile', st.sketches, profileId);
  g('exProfile').disabled = false;
  fill('exTarget', bods.map(b => b.id), bods[0] ? bods[0].id : null);
  // start tiny — the solid should grow when YOU pull the arrow, not jump to a
  // big default the moment the panel opens
  g('exDir').value = 'one'; g('exDist').value = '1'; g('exDist2').value = '10';
  g('exTaper').value = '0'; g('exFlip').checked = false; g('exOp').value = 'new';
  g('exDir').disabled = false;
  syncRows();
  panel().style.display = 'block';
  createPreview();
}

function params() {
  const d = Number(g('exDist').value) || 0;
  const taper = Number(g('exTaper').value) || 0;
  const flip = g('exFlip').checked;
  if (st && st.mode === 'face')
    return { face_center: st.face.center, face_normal: st.face.normal,
             amount: d, taper, flip };
  const dir = g('exDir').value;
  const d2 = Number(g('exDist2').value) || 0;
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
  const op = st.mode === 'face' ? 'extrude_face' : 'extrude';
  const input = st.mode === 'face' ? st.inputId : st.profileId;
  const doc = await postJSON('/api/feature/add',
    { id: st.extrudeId, op, params: params(), inputs: [input] });
  warnIfFailed(doc);
  await applyOp();
  loadMesh();
  placeArrow();
  setupGhost();
}

/* prepare the instant white ghost box (frame + profile bbox) for dragging */
async function setupGhost() {
  try {
    if (st.mode === 'face') {
      const r = await fetch('/api/face-outline', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ face_center: st.face.center,
                               face_normal: st.face.normal }) });
      const data = await r.json();
      if (!data.planar || !data.frame) return;
      const pts = [...data.outer, ...data.holes.flat()];
      const b = { minX: 1e9, maxX: -1e9, minY: 1e9, maxY: -1e9 };
      for (const p of pts) {
        b.minX = Math.min(b.minX, p[0]); b.maxX = Math.max(b.maxX, p[0]);
        b.minY = Math.min(b.minY, p[1]); b.maxY = Math.max(b.maxY, p[1]);
      }
      beginExtrudeGhost(data.frame, b);
    } else {
      const prof = feats().find(f => f.id === st.profileId);
      if (!prof || prof.op !== 'sketch') return;    // plane sketches only
      const plane = prof.params.plane || 'XY';
      const frame = (PLANE_FRAME[plane] || PLANE_FRAME.XY)(Number(prof.params.offset) || 0);
      beginExtrudeGhost(frame, profileBBox(prof.params.entities));
    }
  } catch (e) { /* ghost is a nicety — dragging still works, just rebuilds on release */ }
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
  if (st.mode === 'face') {
    beginExtrudeArrow(st.face.center, st.face.normal,
                      Number(g('exDist').value) || 1, onDrag, onDragCommit);
    return;
  }
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

function onDrag(amount) {
  // while dragging: move ONLY the instant white ghost box — no rebuild, no lag
  g('exDist').value = Math.round(amount * 100) / 100;
  setExtrudeGhost(amount);
}
async function onDragCommit(amount) {     // release: ONE real verified rebuild
  g('exDist').value = Math.round(amount * 100) / 100;
  await apply();
  hideExtrudeGhost();                     // the real solid replaces the ghost
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
  endExtrudeGhost();
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
  endExtrudeGhost();
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
