// extrude.js — Fusion-style Extrude (v1). A non-modal panel with LIVE PREVIEW:
// it creates the extrude (and optional Join/Cut/Intersect) feature immediately
// and edits it in place through the verified rebuild as you change settings, so
// the 3D preview is always a real, checked solid. Cancel removes it; OK keeps.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh, beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginExtrudeGhost, setExtrudeGhost, hideExtrudeGhost,
         endExtrudeGhost, cancelPlanePick } from './viewport.js';

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

/* outline loop of one sketch entity in local coords — the ghost's TRUE shape */
function entLoop(e) {
  const x = e.x || 0, y = e.y || 0, rot = (e.rotation || 0) * Math.PI / 180;
  const R = (px, py) => [x + px * Math.cos(rot) - py * Math.sin(rot),
                         y + px * Math.sin(rot) + py * Math.cos(rot)];
  const ring = (fx, fy, n = 48) => Array.from({ length: n }, (_, i) => {
    const a = 2 * Math.PI * i / n; return R(fx(a), fy(a));
  });
  switch (e.kind) {
    case 'circle': return ring(a => (e.r || 1) * Math.cos(a), a => (e.r || 1) * Math.sin(a));
    case 'ellipse': return ring(a => (e.rx || 1) * Math.cos(a), a => (e.ry || 1) * Math.sin(a));
    case 'regular_polygon': {
      const n = Math.max(3, e.sides || 6), r = e.radius || 1;
      return Array.from({ length: n }, (_, i) => {
        const a = Math.PI / 2 + 2 * Math.PI * i / n;
        return R(r * Math.cos(a), r * Math.sin(a));
      });
    }
    case 'rectangle': {
      const w = (e.w || 1) / 2, h = (e.h || 1) / 2;
      return [R(-w, -h), R(w, -h), R(w, h), R(-w, h)];
    }
    case 'slot': {
      const c = Math.max((e.length || 1) / 2 - (e.height || 1) / 2, 0);
      const r = (e.height || 1) / 2, pts = [];
      for (let i = 0; i <= 16; i++) {
        const a = -Math.PI / 2 + Math.PI * i / 16;
        pts.push(R(c + r * Math.cos(a), r * Math.sin(a)));
      }
      for (let i = 0; i <= 16; i++) {
        const a = Math.PI / 2 + Math.PI * i / 16;
        pts.push(R(-c + r * Math.cos(a), r * Math.sin(a)));
      }
      return pts;
    }
    case 'polygon': return (e.points || []).map(p => [x + p[0], y + p[1]]);
    case 'path': {
      if (!e.start) return null;
      const out = [[x + e.start[0], y + e.start[1]]];
      for (const s of e.segments || []) {
        if (s.type === 'arc' && s.via) out.push([x + s.via[0], y + s.via[1]]);
        out.push([x + s.to[0], y + s.to[1]]);
      }
      return out;
    }
  }
  return null;
}

/* ghost loops for a plane sketch: each ADD entity's true outline (cut
   entities are skipped — the ghost is a drag aid, not the verified result) */
function loopsForEntities(entities) {
  const loops = [];
  for (const e of entities || []) {
    if (e.mode === 'subtract') continue;
    const pts = entLoop(e);
    if (pts && pts.length >= 3) loops.push({ outer: pts, holes: [] });
  }
  return loops;
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
  cancelPlanePick();                 // a pending plane-pick must not linger
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

/* opening the tool builds NOTHING — just the arrow + ghost. The extrude
   feature is created lazily on the first user action (drag release, typed
   value, or OK). No more surprise 1mm boss the moment the panel opens. */
function createPreview() {
  st.extrudeId = null;
  warned = false;
  placeArrow();
  setupGhost();
}

/* create the extrude feature the first time the user actually acts */
async function ensureCreated() {
  if (st.extrudeId) return;
  st.extrudeId = uid('extrude');
  const op = st.mode === 'face' ? 'extrude_face' : 'extrude';
  const input = st.mode === 'face' ? st.inputId : st.profileId;
  const doc = await postJSON('/api/feature/add',
    { id: st.extrudeId, op, params: params(), inputs: [input] });
  warnIfFailed(doc);
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
      // the ghost is the REAL face shape — outline + holes (circle stays round)
      beginExtrudeGhost(data.frame, [{ outer: data.outer, holes: data.holes }]);
    } else {
      const prof = feats().find(f => f.id === st.profileId);
      if (!prof || prof.op !== 'sketch') return;    // plane sketches only
      const plane = prof.params.plane || 'XY';
      const frame = (PLANE_FRAME[plane] || PLANE_FRAME.XY)(Number(prof.params.offset) || 0);
      beginExtrudeGhost(frame, loopsForEntities(prof.params.entities));
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
  if (!st.extrudeId) return;                  // nothing built yet — nothing to combine
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
  if (!st) return;
  const pr = params();
  if (!st.extrudeId) {
    await ensureCreated();                 // first action creates the feature
  } else {
    const doc = await postJSON('/api/feature/params',
      { feature_id: st.extrudeId, params: pr });
    warnIfFailed(doc);
  }
  await applyOp();
  loadMesh();
  // keep the arrow length in sync when the value is typed (not while dragging)
  const signed = pr.flip ? -pr.amount : pr.amount;
  setExtrudeArrowAmount(signed);
}

async function changeProfile() {
  await teardown();
  st.profileId = g('exProfile').value;
  loadMesh();
  createPreview();
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
  const created = st && st.extrudeId;
  endExtrudeArrow();
  endExtrudeGhost();
  st = null; panel().style.display = 'none';
  bus.emit('msg', 'bot', created
    ? 'Extrude created — editable in the feature tree.'
    : 'Nothing extruded — drag the arrow or type a distance next time.');
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
