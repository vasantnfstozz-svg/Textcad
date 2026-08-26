// extrude.js — Fusion-style Extrude (v1). A non-modal panel with LIVE PREVIEW:
// it creates the extrude (and optional Join/Cut/Intersect) feature immediately
// and edits it in place through the verified rebuild as you change settings, so
// the 3D preview is always a real, checked solid. Cancel removes it; OK keeps.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { loadMesh, beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginExtrudeGhost, setExtrudeGhost, hideExtrudeGhost, endExtrudeGhost,
         beginTaperRing, setTaperRingAngle, endTaperRing,
         cancelPlanePick, beginProfilePick, cancelProfilePick } from './viewport.js';

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
/* the feature the Extrude tool is live-editing right now (null when idle) —
   lets the tree's failure toasts stay quiet about a feature whose failures
   this tool already explains + auto-repairs (settleValid) */
export const activeExtrudeId = () => (st && st.extrudeId) || null;
let timer = null;
const debounce = fn => { clearTimeout(timer); timer = setTimeout(fn, 200); };

const feats = () => (S.lastDoc && S.lastDoc.features) || [];
const isSketch = f => f.op === 'sketch' || f.op === 'sketch_on_face';
const solids = () => feats().filter(f => f.volume != null && !f.suppressed);

/* The body a solid feature has BECOME: follow solid-producing consumers down
   the tree (a cut/fillet/pattern of X is the current state of X). Inputs
   always reference earlier features, so the walk strictly advances. */
function latestDescendant(id) {
  let cur = id;
  for (;;) {
    const next = [...feats()].reverse().find(f =>
      f.volume != null && !f.suppressed && (f.inputs || []).includes(cur));
    if (!next) return cur;
    cur = next.id;
  }
}

/* Fusion parity: Join/Cut applies to the body the sketch LIVES ON — a
   face sketch targets its parent body (walked to its current state), a
   plane sketch defaults to the NEWEST solid. Defaulting to the first body
   in the tree cut the raw stock instead of the part the user was looking
   at (reported 2026-08-24 on the sat-side-panel design). */
function defaultTarget(profileId) {
  const bods = solids();
  const sk = feats().find(f => f.id === profileId);
  if (sk && sk.op === 'sketch_on_face' && (sk.inputs || []).length) {
    const cur = latestDescendant(sk.inputs[0]);
    if (bods.some(b => b.id === cur)) return cur;
  }
  const tip = [...bods].pop();
  return tip ? tip.id : null;
}
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

function setHeader(text) { panel().querySelector('.exhead').textContent = text; }
/* one-command-at-a-time (user mandate 2026-08-05): while this panel is open,
   dialogs.modalGuard() makes every other tool refuse until OK/Cancel */
function showPanel() {
  panel().style.display = 'block';
  S.modalTool = 'Extrude';
  S.modalToolPanel = 'extrudeDialog';
}
function releaseModal() {
  if (S.modalTool === 'Extrude') { S.modalTool = null; S.modalToolPanel = null; }
}
function unlockDialog() {           // edit mode locks rows — a NEW session resets
  setHeader('↑ Extrude');
  g('exProfile').title = '';
  g('exOp').disabled = false; g('exOp').title = '';
  g('exTarget').disabled = false;
}

export function openExtrude(preProfile) {
  cancelPlanePick();                 // a pending plane-pick must not linger
  cancelProfilePick();               // nor a pending profile-pick
  cancelExtrude();                   // clear any prior extrude session's gizmos
  unlockDialog();
  const bods = solids();
  // FACE MODE (Fusion: click a planar face, press Extrude, pull the arrow).
  // Capture the pick now — loadMesh() clears it.
  const face = S.pickedFace;
  const tip = [...feats()].reverse().find(f => f.volume != null && !f.suppressed);
  if (face && tip) {
    // Extrude the body the face was PICKED FROM, not whatever happens to be
    // the tip — with several bodies visible those differ, and resolving the
    // face on the wrong body silently extrudes the wrong thing (or fails).
    const owner = face.body && feats().some(f => f.id === face.body)
      ? face.body : tip.id;
    st = { mode: 'face', face: { center: face.center, normal: face.normal || [0, 0, 1],
                                 body: owner },
           inputId: owner, extrudeId: null, opId: null, opType: null, opTarget: null };
    fill('exProfile', ['(selected face)'], '(selected face)');
    g('exProfile').disabled = true;
    fill('exTarget', bods.map(b => b.id), owner);
    g('exDir').value = 'one'; g('exDist').value = '1'; g('exDist2').value = '10';
    g('exTaper').value = '0'; g('exFlip').checked = false;
    g('exOp').value = 'join';            // pulling a face usually grows the body
    g('exDir').disabled = true;          // face extrude is one-directional (drag ± instead)
    syncRows();
    showPanel();
    createPreview();
    return;
  }
  // an explicitly SELECTED profile (viewport pick) counts like the tree's ⬆
  if (!preProfile && S.pickedProfile) preProfile = S.pickedProfile.id;
  if (S.pickedCurved && !preProfile) {
    bus.emit('msg', 'bot',
      `⚠ Extrude needs a FLAT face — the selected surface is ` +
      `${S.pickedCurved.type} (curved). Flat faces (including tilted ones) ` +
      `extrude fine; a rounded face like a cone or cylinder side can't.`);
    return;
  }
  // only UNCONSUMED sketches are offered — a sketch already used by an extrude
  // must not silently become the profile again ("goes back to the old sketch").
  // An explicit preProfile (tree ⬆ / viewport pick) is honoured even if consumed.
  const consumed = new Set(feats().flatMap(f => f.inputs));
  const sks = feats().filter(isSketch)
    .filter(s => !consumed.has(s.id) || s.id === preProfile);
  if (!sks.length && !bods.length) {
    bus.emit('msg', 'bot',
      '⚠ Draw a sketch first (Create → Create Sketch), then Extrude it.');
    return;
  }
  if (preProfile && sks.some(s => s.id === preProfile)) {
    st = { mode: 'sketch', sketches: sks.map(s => s.id), extrudeId: null,
           opId: null, opType: null, opTarget: null, profileId: preProfile };
    fill('exProfile', st.sketches, preProfile);
    g('exProfile').disabled = false;
    fill('exTarget', bods.map(b => b.id), defaultTarget(preProfile));
    // start tiny — the solid should grow when YOU pull the arrow, not jump to
    // a big default the moment the panel opens
    g('exDir').value = 'one'; g('exDist').value = '1'; g('exDist2').value = '10';
    g('exTaper').value = '0'; g('exFlip').checked = false; g('exOp').value = 'new';
    g('exDir').disabled = false;
    syncRows();
    showPanel();
    createPreview();
    return;
  }
  // NOTHING selected: Fusion's command-then-select — the USER picks what to
  // extrude (a sketch profile or a flat face); never auto-grab a sketch
  beginProfilePick((kind, data) => {
    if (kind === 'profile') { openExtrude(data); return; }
    S.pickedFace = data;                 // planar face — reuse face mode
    openExtrude();
  });
  bus.emit('msg', 'bot', 'Extrude: click a sketch profile or a flat face in ' +
    'the viewport — your pick, nothing is chosen for you. Esc cancels.');
}

/* EDIT FEATURE (Fusion parity): reopen an EXISTING extrude in the same tool
   that created it — arrow, ghost, taper ring, live verified preview. Every
   change is pushed to the real feature via /api/feature/params; Cancel
   restores the exact params it had when the dialog opened. Profile and
   Operation rows are shown but locked — rewiring the tree is a later step. */
const COMBINER_LABEL = { fuse: 'join', cut: 'cut', intersect: 'intersect' };

export function openExtrudeEdit(fid) {
  cancelPlanePick();
  cancelProfilePick();
  cancelExtrude();
  unlockDialog();
  const f = feats().find(x => x.id === fid);
  if (!f || (f.op !== 'extrude' && f.op !== 'extrude_face')) return;
  const p = f.params || {};
  const face = f.op === 'extrude_face';
  // normalized snapshot of EVERY param this dialog can write in this mode —
  // Cancel pushes it back verbatim, so keys the session added are reset too
  const original = face
    ? { face_center: p.face_center, face_normal: p.face_normal || [0, 0, 1],
        amount: Number(p.amount) || 0, taper: Number(p.taper) || 0,
        flip: !!p.flip }
    : { amount: Number(p.amount) || 0, both: !!p.both,
        amount2: Number(p.amount2) || 0, taper: Number(p.taper) || 0,
        flip: !!p.flip, through: !!p.through };
  if (face) {
    st = { mode: 'face', editing: true, extrudeId: f.id, original,
           inputId: f.inputs[0],
           face: { center: original.face_center, normal: original.face_normal,
                   body: f.inputs[0] },
           opId: null, opType: null, opTarget: null,
           lastGood: { amount: original.amount, taper: original.taper } };
    fill('exProfile', [`(face of ${f.inputs[0]})`], `(face of ${f.inputs[0]})`);
    g('exDir').value = 'one'; g('exDir').disabled = true;
  } else {
    st = { mode: 'sketch', editing: true, extrudeId: f.id, original,
           profileId: f.inputs[0], sketches: [f.inputs[0]],
           opId: null, opType: null, opTarget: null,
           lastGood: { amount: original.amount, taper: original.taper } };
    fill('exProfile', [f.inputs[0]], f.inputs[0]);
    g('exDir').disabled = false;
    g('exDir').value = original.both ? 'sym' : (original.amount2 ? 'two' : 'one');
  }
  g('exProfile').disabled = true;
  g('exProfile').title = 'changing the profile of an existing extrude comes later';
  g('exDist').value = original.amount;
  g('exDist2').value = original.amount2 || 10;
  g('exTaper').value = original.taper;
  g('exFlip').checked = original.flip;
  g('exThrough').checked = !!original.through;
  // Operation row: show what the tree ACTUALLY does with this extrude (the
  // downstream combiner, if any) — honest but locked in edit mode
  const comb = feats().find(x => COMBINER_LABEL[x.op]
    && (x.inputs || []).includes(f.id));
  g('exOp').value = comb ? COMBINER_LABEL[comb.op] : 'new';
  g('exOp').disabled = true;
  g('exOp').title = 'changing the operation of an existing extrude comes later';
  if (comb) {
    const target = (comb.inputs || []).find(i => i !== f.id) || '';
    fill('exTarget', [target], target);
    g('exTarget').disabled = true;
  }
  setHeader(`✎ Edit ${f.id}`);
  syncRows();
  showPanel();
  placeArrow();
  setupGhost();
  setExtrudeArrowAmount(original.flip ? -original.amount : original.amount);
  isolateFor(f.id).then(() => loadMesh());   // downstream waits for OK/Cancel
}

/* ------------- editing in isolation (same trick as edit-sketch) -------------
   Editing an extrude in the MIDDLE of a tree rebuilt everything below it on
   every keystroke: `esp_pillar_trim_tool` is feature 23 of 73, so each value
   change paid for 49 downstream features — 5.4 s a keystroke (user, 2026-08-26:
   "its taking a lot of times, when i am changing the values").

   So park the rollback bar on the feature that APPLIES this extrude (its
   boolean, if it has one — otherwise the extrude itself) while the panel is
   open. Everything downstream is skipped, the change is instant, and the one
   full rebuild happens when the panel closes. The bar goes on the BOOLEAN, not
   on the extrude, so what you see is the pocket applied to the body rather than
   a floating tool prism. */
let isoActive = false;

function boolOf(fid) {
  return feats().find(x => COMBINER_LABEL[x.op]
                           && (x.inputs || []).includes(fid));
}

async function isolateFor(fid) {
  const comb = boolOf(fid);
  isoActive = true;
  await postJSON('/api/rollback', { feature_id: (comb || { id: fid }).id });
}

async function releaseIso() {
  if (!isoActive) return;
  isoActive = false;
  await postJSON('/api/rollback', { feature_id: null });
}

function params() {
  const d = Number(g('exDist').value) || 0;
  const taper = Number(g('exTaper').value) || 0;
  const flip = g('exFlip').checked;
  const through = g('exThrough').checked;
  if (st && st.mode === 'face')
    return { face_center: st.face.center, face_normal: st.face.normal,
             amount: d, taper, flip };
  const dir = g('exDir').value;
  const d2 = Number(g('exDist2').value) || 0;
  if (dir === 'sym') return { amount: d, both: true, amount2: 0, taper,
                              flip: false, through };
  if (dir === 'two') return { amount: d, both: false, amount2: d2, taper, flip,
                              through };
  return { amount: d, both: false, amount2: 0, taper, flip, through };
}

function syncRows() {
  g('exDist2Row').style.display = g('exDir').value === 'two' ? '' : 'none';
  g('exTargetRow').style.display = g('exOp').value === 'new' ? 'none' : '';
  // THROUGH ALL is a cut idea: a boss running 2 m past the part is useless,
  // but a cut that stops inside the material is a bug factory — it slices the
  // part and leaves whatever was above the cut floating loose.
  const isCut = g('exOp').value === 'cut';
  g('exThroughRow').style.display = isCut ? '' : 'none';
  if (!isCut) g('exThrough').checked = false;
  const thru = g('exThrough').checked;
  g('exDist').disabled = thru;
  g('exDist').title = thru ? 'not used — the cut runs all the way through' : '';
}

/* opening the tool builds NOTHING — just the arrow + ghost. The extrude
   feature is created lazily on the first user action (drag release, typed
   value, or OK). No more surprise 1mm boss the moment the panel opens. */
function createPreview() {
  st.extrudeId = null;
  placeArrow();
  setupGhost();
}

/* create the extrude feature the first time the user actually acts */
async function ensureCreated() {
  if (st.extrudeId) return null;
  st.extrudeId = uid('extrude');
  const op = st.mode === 'face' ? 'extrude_face' : 'extrude';
  const input = st.mode === 'face' ? st.inputId : st.profileId;
  return await postJSON('/api/feature/add',
    { id: st.extrudeId, op, params: params(), inputs: [input] });
}

/* Inradius of the profile: how far the walls can move inward before it
   collapses. The face-outline samples points ALONG the edges, so the min
   distance from the centroid to a sampled point ≈ the inradius (correct for
   convex faces: rect→half-short-side, circle→radius). Holes shrink it to half
   the thinnest wall. This is the LIVE-barrier estimate; the verified back-off
   in apply() is the backstop when the estimate is off (e.g. non-convex). */
function safeRadius(loops) {
  let minR = Infinity;
  for (const L of loops || []) {
    if (!L.outer || L.outer.length < 3) continue;
    let cx = 0, cy = 0;
    for (const p of L.outer) { cx += p[0]; cy += p[1]; }
    cx /= L.outer.length; cy /= L.outer.length;
    for (const p of L.outer)
      minR = Math.min(minR, Math.hypot(p[0] - cx, p[1] - cy));
    for (const h of L.holes || [])
      for (const hp of h)
        for (const op of L.outer)
          minR = Math.min(minR, Math.hypot(hp[0] - op[0], hp[1] - op[1]) / 2);
  }
  return isFinite(minR) ? Math.max(minR, 0.1) : null;
}

/* live barrier: keep a NARROWING taper (or a distance under taper) inside the
   buildable range. Flaring (negative taper) never collapses, so it stays free.
   If safeR is unknown, don't block — the verified back-off will catch it.
   Fusion parity (user mandate 2026-08-05): a HOLE-LESS profile may narrow all
   the way to full collapse — a wedge/apex "flat" limit (0.995: probed — the
   exact singular angle fails in OCCT, a hair under builds fine). Profiles
   with holes keep the 0.92 margin: hole-wall collision genuinely breaks. */
const taperF = () => (st && st.hasHoles ? 0.92 : 0.995);
function clampTaperFn(t) {
  if (t <= 0 || !st || !st.safeR) return t;             // flare = free
  const a = Math.abs(Number(g('exDist').value) || 1);
  return Math.min(t, Math.atan(taperF() * st.safeR / Math.max(a, 0.01)) * 180 / Math.PI);
}
function clampAmountFn(a) {
  const t = Number(g('exTaper').value) || 0;
  if (t <= 0 || !st || !st.safeR) return a;
  const maxA = taperF() * st.safeR / Math.tan(t * Math.PI / 180);
  return Math.max(-maxA, Math.min(maxA, a));
}

/* prepare the instant white ghost box (frame + profile bbox) for dragging */
async function setupGhost() {
  try {
    if (st.mode === 'face') {
      const r = await fetch('/api/face-outline', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ face_center: st.face.center,
                               face_normal: st.face.normal,
                               feature_id: st.face.body }) });
      const data = await r.json();
      if (!data.planar || !data.frame) return;
      // the ghost is the REAL face shape — outline + holes (circle stays round)
      const loops = [{ outer: data.outer, holes: data.holes }];
      st.safeR = safeRadius(loops);
      st.hasHoles = !!(data.holes && data.holes.length);
      beginExtrudeGhost(data.frame, loops);
      setupTaperRing(data.frame, loops);
    } else {
      const prof = feats().find(f => f.id === st.profileId);
      if (!prof) return;
      let frame;
      if (prof.op === 'sketch_on_face') {
        // a FACE sketch's frame lives on the body: re-resolve it by geometry
        // — without this, face-sketch extrudes had NO ghost box and NO taper
        // ring ("I can't see how far I am going")
        const r = await fetch('/api/face-outline', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ face_center: prof.params.face_center,
                                 face_normal: prof.params.face_normal || null,
                                 feature_id: (prof.inputs || [])[0] || null }) });
        const data = await r.json();
        if (!data.planar || !data.frame) return;
        frame = data.frame;
      } else {
        const plane = prof.params.plane || 'XY';
        frame = (PLANE_FRAME[plane] || PLANE_FRAME.XY)(Number(prof.params.offset) || 0);
      }
      const loops = loopsForEntities(prof.params.entities);
      st.safeR = safeRadius(loops);
      st.hasHoles = (prof.params.entities || [])
        .some(e => e.mode === 'subtract');
      beginExtrudeGhost(frame, loops);
      setupTaperRing(frame, loops);
    }
  } catch (e) { /* ghost is a nicety — dragging still works, just rebuilds on release */ }
}

/* Fusion's dashed taper circle: centered on the profile, drag the handle
   around it to set the taper angle — ghost only while dragging, one rebuild
   on release, value box stays in sync. */
function setupTaperRing(frame, loops) {
  let cx = 0, cy = 0, np = 0, maxR = 0;
  for (const L of loops || []) for (const p of L.outer) { cx += p[0]; cy += p[1]; np++; }
  if (!np) return;
  cx /= np; cy /= np;
  for (const L of loops) for (const p of L.outer)
    maxR = Math.max(maxR, Math.hypot(p[0] - cx, p[1] - cy));
  const X = frame.x_dir, Y = frame.y_dir, O = frame.origin;
  const center = [O[0] + X[0] * cx + Y[0] * cy,
                  O[1] + X[1] * cx + Y[1] * cy,
                  O[2] + X[2] * cx + Y[2] * cy];
  beginTaperRing(center, frame, maxR * 1.35, Number(g('exTaper').value) || 0,
    t => {                                   // dragging: ghost + value box only
      g('exTaper').value = Math.round(t * 10) / 10;
      setExtrudeGhost(Number(g('exDist').value) || 1, t);
    },
    async t => {                             // release: ONE verified rebuild
      g('exTaper').value = Math.round(t * 10) / 10;
      await apply();                         // apply() enforces the real barrier
      hideExtrudeGhost();
    },
    clampTaperFn);                           // live barrier: stop before collapse
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
                      Number(g('exDist').value) || 1, onDrag, onDragCommit,
                      clampAmountFn);
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
  beginExtrudeArrow(O, N, Number(g('exDist').value) || 1, onDrag, onDragCommit,
                    clampAmountFn);
}

function onDrag(amount) {
  // while dragging: move ONLY the instant white ghost box — no rebuild, no lag
  g('exDist').value = Math.round(amount * 100) / 100;
  setExtrudeGhost(amount, Number(g('exTaper').value) || 0);
}
async function onDragCommit(amount) {     // release: ONE real verified rebuild
  g('exDist').value = Math.round(amount * 100) / 100;
  await apply();
  hideExtrudeGhost();                     // the real solid replaces the ghost
}

async function applyOp() {
  if (!st.extrudeId) return;                  // nothing built yet — nothing to combine
  if (st.editing) return;                     // edit mode never rewires combiners (v1)
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

const featOf = doc => doc && (doc.features || []).find(x => x.id === st.extrudeId);
const isOk = f => f && f.status === 'ok';

/* push one set of params and read back the extrude feature's health */
async function push(pr) {
  const doc = await postJSON('/api/feature/params',
    { feature_id: st.extrudeId, params: pr });
  warnIfSplit(doc);
  return { doc, f: featOf(doc) };
}

/* THE REAL BARRIER — verified, not guessed. If the chosen taper (or distance)
   collapses the solid, bisect it back toward zero to the largest magnitude the
   geometry kernel actually accepts, keeping its sign. No reliance on a face-
   shape estimate, so it holds for any profile and both drag directions. */
/* apply the analytic barrier to the CURRENT box values (same limit the ring/
   arrow use live) so typed values behave identically to dragging — and note it
   once when we actually had to reduce something. Returns true if it changed. */
function clampBoxValues() {
  let changed = false;
  const t0 = Number(g('exTaper').value) || 0, t1 = clampTaperFn(t0);
  if (Math.abs(t1 - t0) > 0.05) {
    g('exTaper').value = Math.round(t1 * 10) / 10;
    bus.emit('msg', 'bot', `Taper limited to ${g('exTaper').value}° — ` +
      `steeper collapses the walls at this distance.`);
    changed = true;
  }
  const a0 = Number(g('exDist').value) || 1, a1 = clampAmountFn(a0);
  if (Math.abs(a1 - a0) > 0.05) { g('exDist').value = Math.round(a1 * 100) / 100; changed = true; }
  return changed;
}

/* rare backstop: the analytic clamp already prevents collapse on normal faces,
   but if a build still fails (e.g. a non-convex face where the estimate is off,
   or a value with no safeR), shrink the taper toward zero a few times, then
   fall back to the last values that worked. A few rebuilds at most. */
async function settleValid(pr) {
  const sign = pr.taper < 0 ? -1 : 1;
  let mag = Math.abs(pr.taper);
  for (let k = 0; k < 4 && mag > 0.2; k++) {
    mag *= 0.6;
    const t = await push({ ...pr, taper: sign * mag });
    if (isOk(t.f)) {
      const val = Math.round(sign * mag * 10) / 10;
      g('exTaper').value = val;
      bus.emit('msg', 'bot', `Taper limited to ${val}° — steeper collapses the walls here.`);
      return t;
    }
  }
  if (st.lastGood) {                          // taper wasn't it — restore last good
    const r = await push({ ...pr, amount: st.lastGood.amount, taper: st.lastGood.taper });
    g('exDist').value = st.lastGood.amount;
    g('exTaper').value = st.lastGood.taper;
    bus.emit('msg', 'bot', `Reverted to ${st.lastGood.amount}mm / ` +
      `${st.lastGood.taper}° — the new values broke the solid.`);
    return r;
  }
  return await push({ ...pr, taper: 0 });
}

/* one full apply pass. Serialized by apply() so it always finishes. */
/* A cut that stops short of the material it used to reach leaves loose pieces:
   reducing a pillar-trim from 6 to 2 mm sliced a band out of four pillars and
   left their caps floating (user, 2026-08-26: "it created a new body"). The
   geometry is real, so we do not block it — but the moment it happens the panel
   has to say so, while the user still has the value in their hand. */
let saidPieces = 0;
function warnIfSplit(doc) {
  if (!doc || !doc.features) return;
  const n = doc.result_pieces || 0;
  if (n > 1 && n !== saidPieces) {
    saidPieces = n;
    bus.emit('msg', 'bot', `⚠ At this distance the part falls into ${n} ` +
      `separate pieces — the cut stops INSIDE the material, so it slices ` +
      `it instead of clearing it and leaves ${n - 1} loose piece(s). Two ` +
      `fixes: tick "Through all" (then no distance can land inside the part), ` +
      `and to raise or lower what is left, edit the SKETCH's offset — that is ` +
      `the height the cut starts from.`);
  } else if (n <= 1) {
    saidPieces = 0;
  }
}

async function applyOnce() {
  clampBoxValues();                           // analytic barrier — one rebuild
  const pr = params();
  let doc = st.extrudeId ? (await push(pr)).doc : await ensureCreated();
  if (!st) return;
  let f = featOf(doc);
  // backstop for the rare case the estimate missed — never leave a collapsed
  // solid on screen (red tree / blank body).
  if (f && f.status === 'failed') {
    const settled = await settleValid(pr);
    if (!st) return;
    doc = settled.doc; f = settled.f;
  }
  if (isOk(f))
    st.lastGood = { amount: Number(g('exDist').value) || 1,
                    taper: Number(g('exTaper').value) || 0 };
  await applyOp();
  loadMesh();
  // keep the gizmos in sync with the (possibly adjusted) values
  const amt = Number(g('exDist').value) || 1;
  setExtrudeArrowAmount(g('exFlip').checked ? -amt : amt);
  setTaperRingAngle(Number(g('exTaper').value) || 0);
}

// Serialize applies: a settle does several rebuilds and must run to completion,
// but doc-updated re-renders (and fast user input) can call apply() meanwhile.
// Rather than kill the in-flight pass, mark it pending and re-run ONCE after
// with the latest values — coalescing bursts into a single trailing rebuild.
let applyBusy = false, applyPending = false;
async function apply() {
  if (!st) return;
  if (applyBusy) { applyPending = true; return; }
  applyBusy = true;
  try {
    do { applyPending = false; await applyOnce(); }
    while (applyPending && st);
  } finally { applyBusy = false; }
}

async function changeProfile() {
  await teardown();
  st.profileId = g('exProfile').value;
  // the combine target follows the profile: a different sketch may live on a
  // different body (same rule as on open)
  fill('exTarget', solids().map(b => b.id), defaultTarget(st.profileId));
  loadMesh();
  createPreview();
}

async function teardown() {
  endExtrudeArrow();
  endExtrudeGhost();
  endTaperRing();
  if (st && st.opId) await postJSON('/api/feature/remove', { feature_id: st.opId });
  if (st && st.extrudeId) await postJSON('/api/feature/remove', { feature_id: st.extrudeId });
  if (st) { st.opId = st.opType = st.opTarget = st.extrudeId = null; }
}

async function cancel() {
  releaseModal();
  if (st && st.editing) {                // edit mode: the feature stays — put
    const { extrudeId, original } = st;  // its ORIGINAL params back verbatim
    endExtrudeArrow(); endExtrudeGhost(); endTaperRing();
    st = null; panel().style.display = 'none';
    await postJSON('/api/feature/params',
      { feature_id: extrudeId, params: original });
    await releaseIso();
    loadMesh();
    return;
  }
  await teardown(); loadMesh();
  st = null; panel().style.display = 'none';
}

async function ok() {
  releaseModal();
  const editing = st && st.editing;
  if (st && ((!editing && !st.extrudeId) || editing)) {
    // OK must COMMIT the panel's values even if the user never dragged the
    // arrow or touched an input (reported 2026-08-21: traced-logo sketch
    // "could not extrude" — OK with the default distance did nothing).
    // EDIT mode needs it too: typing a value and pressing OK inside the input
    // debounce window dropped the change silently.
    await apply();
  }
  const created = st && st.extrudeId;
  endExtrudeArrow();
  endExtrudeGhost();
  endTaperRing();
  st = null; panel().style.display = 'none';
  await releaseIso();                 // the one full rebuild, now
  loadMesh();
  bus.emit('msg', 'bot', editing
    ? 'Extrude updated — the change is in the feature tree.'
    : created
    ? 'Extrude created — editable in the feature tree.'
    : 'Nothing extruded — the profile could not be pulled.');
}

/* Close a lingering Extrude session when ANOTHER tool starts — otherwise its
   arrow/ring gizmos stay in the viewport and swallow the next click, so faces
   can't be selected anymore. Keeps any already-committed extrude (it's a real
   verified feature); just clears the gizmos + panel. Mirrors cancelPlanePick. */
export function cancelExtrude() {
  releaseModal();
  cancelProfilePick();               // a pending "pick a profile" dies with us
  releaseIso();                      // never leave the rollback bar parked
  if (!st && panel().style.display === 'none') return;
  endExtrudeArrow();
  endExtrudeGhost();
  endTaperRing();
  st = null;
  panel().style.display = 'none';
}

export function initExtrude() {
  g('exProfile').onchange = changeProfile;
  g('exOp').onchange = () => {
    // Fusion: CUT goes INTO the material. A face sketch's normal points OUT
    // of the body, so a positive distance leaves the tool floating outside
    // and the cut removes NOTHING — that read as "cut is not working". Flip
    // the sign once when Cut is chosen (the user can still drag either way).
    const prof = st && st.mode === 'sketch'
      && feats().find(f => f.id === st.profileId);
    const d = Number(g('exDist').value) || 0;
    if (g('exOp').value === 'cut' && prof
        && prof.op === 'sketch_on_face' && d > 0) {
      g('exDist').value = -d;
      bus.emit('msg', 'bot', `Cut goes INTO the body — distance flipped to ` +
        `${-d}mm. Drag the arrow (or type) to set the pocket depth.`);
    }
    syncRows(); apply();
  };
  for (const id of ['exDir', 'exTarget', 'exFlip', 'exThrough'])
    g(id).onchange = () => { syncRows(); apply(); };
  for (const id of ['exDist', 'exDist2', 'exTaper'])
    g(id).oninput = () => debounce(apply);
  g('exCancel').onclick = cancel;
  g('exOk').onclick = ok;
}
