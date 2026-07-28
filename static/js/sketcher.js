// sketcher.js — the interactive 2D sketch editor (Fusion-style):
//   * pick a tool in the palette, then CLICK ON THE CANVAS to draw
//     (circle: click center, click radius; rectangle: two corners;
//      polygon: click points, double-click to close)
//   * no tool active = select / drag-move shapes, drag empty space to pan
//   * mouse wheel zooms around the cursor; grid-snapped coordinates
//   * Esc cancels the tool, Delete removes the selected shape
// Two flows: plane sketch (Sketch tab) and face sketch (guided boss/pocket).

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh } from './viewport.js';
import { openFeatDialog } from './dialogs.js';

/* ---------------- state ---------------- */

const DEFAULT_FIELDS = {
  rectangle: { w: 40, h: 20, x: 0, y: 0, rotation: 0 },
  circle: { r: 15, x: 0, y: 0 },
  ellipse: { rx: 20, ry: 10, x: 0, y: 0, rotation: 0 },
  slot: { length: 30, height: 10, x: 0, y: 0, rotation: 0 },
  regular_polygon: { radius: 20, sides: 6, x: 0, y: 0, rotation: 0 },
  polygon: { points: [[0, 0], [30, 0], [15, 25]], x: 0, y: 0 },
};

let skEnts = [];          // the sketch's entities
let skOnFace = null;      // {center, normal, inputId} when sketching on a face
let tool = null;          // active drawing tool (entity kind) or null = select
let clicks = [];          // world-space clicks collected for the current tool
let ghost = null;         // preview entity while placing
let selEnt = -1;          // selected entity index
let view = { cx: 0, cy: 0, ext: 60 };   // world-space view (ext = half-width)
const SNAP = 1;           // click snap in mm

// path tool (chained lines + arcs)
let pathStart = null;     // first point of the profile
let pathSegs = [];        // committed segments
let segMode = 'line';     // what the next segment is: 'line' | 'arc'
let pendingVia = null;    // arc: the middle (via) point, waiting for the end

const dlg = () => document.getElementById('sketchDialog');
const svg = () => document.getElementById('sketchCanvas');

/* ---------------- open / close ---------------- */

function resetEditor() {
  skEnts = []; tool = null; clicks = []; ghost = null; selEnt = -1;
  view = { cx: 0, cy: 0, ext: 60 };
  document.querySelectorAll('.skpalette button')
    .forEach(b => b.classList.remove('active'));
  renderEnts();
}

function nextName() {
  const n = (S.lastDoc?.features.filter(
    f => f.op === 'sketch' || f.op === 'sketch_on_face').length || 0) + 1;
  return 'sketch' + n;
}

export function openSketchEditor() {
  skOnFace = null;
  resetEditor();
  document.getElementById('skName').value = nextName();
  document.getElementById('skOffset').value = '0';
  document.getElementById('skPlaneRow').style.display = '';
  document.getElementById('skFaceNote').style.display = 'none';
  document.getElementById('skFaceExtrude').style.display = 'none';
  dlg().showModal();
  draw();
}

export function openSketchOnFace(faceInfo) {
  const tip = [...(S.lastDoc?.features || [])].reverse()
    .find(f => f.volume != null);
  if (!tip) { bus.emit('msg', 'bot', '⚠ No solid to sketch on yet.'); return; }
  skOnFace = { center: faceInfo.center, normal: faceInfo.normal || null,
               inputId: tip.id };
  resetEditor();
  document.getElementById('skName').value = nextName();
  document.getElementById('skPlaneRow').style.display = 'none';
  document.getElementById('skFaceNote').style.display = '';
  document.getElementById('skFaceExtrude').style.display = '';
  document.getElementById('skFaceNote').textContent =
    `On face at (${faceInfo.center.join(', ')}) of "${skOnFace.inputId}". ` +
    `Pick a shape, click to draw, set depth + Join/Cut, then Create.`;
  dlg().showModal();
  draw();
}
bus.on('sketch-on-face', openSketchOnFace);

/* ---------------- init: palette, canvas, keyboard ---------------- */

export function initSketcher() {
  for (const b of document.querySelectorAll('.skpalette button')) {
    b.onclick = () => setTool(tool === b.dataset.shape ? null : b.dataset.shape);
  }
  document.getElementById('skCancel').onclick = () => dlg().close();
  document.getElementById('skCreate').onclick = create;

  const c = svg();
  c.addEventListener('pointerdown', onDown);
  c.addEventListener('pointermove', onMove);
  c.addEventListener('pointerup', onUp);
  c.addEventListener('dblclick', onDblClick);
  c.addEventListener('wheel', onWheel, { passive: false });

  dlg().addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'Escape' && (tool || clicks.length)) {
      e.preventDefault(); setTool(null);
    }
    if ((e.key === 'Delete' || e.key === 'Backspace') && selEnt >= 0) {
      e.preventDefault(); skEnts.splice(selEnt, 1); selEnt = -1; renderEnts();
    }
  });
}

function setTool(kind) {
  tool = kind; clicks = []; ghost = null;
  pathStart = null; pathSegs = []; pendingVia = null; segMode = 'line';
  document.querySelectorAll('.skpalette button').forEach(b =>
    b.classList.toggle('active', b.dataset.shape === tool));
  svg().style.cursor = tool ? 'crosshair' : 'default';
  updateHint();
  draw();
}

/* ---------------- coordinates ---------------- */

function worldPoint(e) {
  const el = svg();
  const pt = new DOMPoint(e.clientX, e.clientY)
    .matrixTransform(el.getScreenCTM().inverse());
  return { x: pt.x, y: -pt.y };            // flip: world +y is up
}
const snap = v => Math.round(v / SNAP) * SNAP;
const snapPt = p => ({ x: snap(p.x), y: snap(p.y) });
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/* ---------------- pointer interaction ---------------- */

let dragging = null;      // {idx, startX, startY, ex, ey} moving an entity
let panning = null;       // {px, py, cx, cy} moving the view

function onDown(e) {
  if (e.button !== 0) return;
  const p = snapPt(worldPoint(e));

  if (tool) { placeClick(p); return; }

  const hit = hitTest(worldPoint(e));
  if (hit >= 0) {
    selEnt = hit;
    const ent = skEnts[hit];
    dragging = { idx: hit, startX: p.x, startY: p.y,
                 ex: ent.x || 0, ey: ent.y || 0 };
    svg().setPointerCapture(e.pointerId);
    renderCards(); draw();
  } else {
    selEnt = -1;
    const raw = worldPoint(e);
    panning = { px: raw.x, py: raw.y, cx: view.cx, cy: view.cy };
    svg().setPointerCapture(e.pointerId);
    renderCards(); draw();
  }
}

function onMove(e) {
  const p = worldPoint(e);
  document.getElementById('skCoords').textContent =
    `x ${snap(p.x)}, y ${snap(p.y)}`;

  if (tool === 'path' && pathStart) { ghost = pathGhost(snapPt(p)); draw(); return; }
  if (tool && clicks.length) { ghost = buildGhost(snapPt(p)); draw(); return; }
  if (dragging) {
    const ent = skEnts[dragging.idx];
    ent.x = snap(dragging.ex + (p.x - dragging.startX));
    ent.y = snap(dragging.ey + (p.y - dragging.startY));
    draw(); return;
  }
  if (panning) {
    view.cx = panning.cx - (p.x - panning.px);
    view.cy = panning.cy - (p.y - panning.py);
    draw();
  }
}

function onUp(e) {
  if (dragging) { renderCards(); }
  dragging = null; panning = null;
  try { svg().releasePointerCapture(e.pointerId); } catch {}
}

function onDblClick() {
  if (tool === 'polygon' && clicks.length >= 3) finishPolygon();
  if (tool === 'path' && pathSegs.length >= 1) finishPath();
}

function pathGhost(p) {
  const cur = pathCursor();
  const segs = [...pathSegs];
  if (pendingVia) segs.push({ type: 'arc', via: [pendingVia.x, pendingVia.y],
                              to: [p.x, p.y] });
  else segs.push({ type: 'line', to: [p.x, p.y] });
  return { kind: 'path', mode: 'add', x: 0, y: 0, ghostOpen: true,
           start: [pathStart.x, pathStart.y], segments: segs };
}

function onWheel(e) {
  e.preventDefault();
  const p = worldPoint(e);
  const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
  const ext = Math.max(10, Math.min(2000, view.ext * factor));
  const k = ext / view.ext;
  view.cx = p.x - (p.x - view.cx) * k;
  view.cy = p.y - (p.y - view.cy) * k;
  view.ext = ext;
  draw();
}

/* ---------------- arc / path geometry helpers ---------------- */

function circleFrom3(a, m, b) {
  const d = 2 * (a.x * (m.y - b.y) + m.x * (b.y - a.y) + b.x * (a.y - m.y));
  if (Math.abs(d) < 1e-9) return null;                 // collinear
  const s = p => p.x * p.x + p.y * p.y;
  return {
    cx: (s(a) * (m.y - b.y) + s(m) * (b.y - a.y) + s(b) * (a.y - m.y)) / d,
    cy: (s(a) * (b.x - m.x) + s(m) * (a.x - b.x) + s(b) * (m.x - a.x)) / d,
  };
}

function sampleArc(a, m, b, n = 20) {
  const c = circleFrom3(a, m, b);
  if (!c) return [a, b];
  const r = Math.hypot(a.x - c.cx, a.y - c.cy);
  const ang = p => Math.atan2(p.y - c.cy, p.x - c.cx);
  const a0 = ang(a), am = ang(m), a1 = ang(b);
  const ccw = (from, to) => (to - from + 4 * Math.PI) % (2 * Math.PI);
  const pts = [];
  if (ccw(a0, am) <= ccw(a0, a1)) {                    // ccw passes the via pt
    const sweep = ccw(a0, a1);
    for (let i = 0; i <= n; i++) {
      const t = a0 + sweep * i / n;
      pts.push({ x: c.cx + r * Math.cos(t), y: c.cy + r * Math.sin(t) });
    }
  } else {
    const sweep = 2 * Math.PI - ccw(a0, a1);
    for (let i = 0; i <= n; i++) {
      const t = a0 - sweep * i / n;
      pts.push({ x: c.cx + r * Math.cos(t), y: c.cy + r * Math.sin(t) });
    }
  }
  return pts;
}

function pathOutline(e) {
  const ox = e.x || 0, oy = e.y || 0;
  let cur = { x: e.start[0], y: e.start[1] };
  const pts = [{ ...cur }];
  for (const s of e.segments || []) {
    const to = { x: s.to[0], y: s.to[1] };
    if (s.type === 'arc' && s.via)
      pts.push(...sampleArc(cur, { x: s.via[0], y: s.via[1] }, to).slice(1));
    else pts.push(to);
    cur = to;
  }
  return pts.map(p => ({ x: p.x + ox, y: p.y + oy }));
}

/* ---------------- click-to-place ---------------- */

function placeClick(p) {
  if (tool === 'path') { pathClick(p); return; }
  clicks.push(p);

  if (tool === 'polygon') {
    // click near the first point closes the shape
    if (clicks.length >= 3 && dist(p, clicks[0]) < view.ext / 30) {
      clicks.pop(); finishPolygon();
    }
    ghost = buildGhost(p); draw(); updateHint();
    return;
  }

  if (clicks.length === 2) {
    const ent = twoClickEntity(tool, clicks[0], clicks[1]);
    if (ent) { skEnts.push(ent); selEnt = skEnts.length - 1; }
    clicks = []; ghost = null;
    renderEnts(); updateHint();
  } else {
    ghost = buildGhost(p); draw(); updateHint();
  }
}

function twoClickEntity(kind, a, b) {
  const d = Math.max(dist(a, b), 0.5);
  if (kind === 'circle')
    return { kind, mode: 'add', x: a.x, y: a.y, r: snap(d) || 1 };
  if (kind === 'regular_polygon')
    return { kind, mode: 'add', x: a.x, y: a.y, radius: snap(d) || 1,
             sides: 6, rotation: 0 };
  if (kind === 'rectangle')
    return { kind, mode: 'add',
             x: snap((a.x + b.x) / 2), y: snap((a.y + b.y) / 2),
             w: Math.max(Math.abs(b.x - a.x), 1),
             h: Math.max(Math.abs(b.y - a.y), 1), rotation: 0 };
  if (kind === 'ellipse')
    return { kind, mode: 'add', x: a.x, y: a.y,
             rx: Math.max(Math.abs(b.x - a.x), 1),
             ry: Math.max(Math.abs(b.y - a.y), 1), rotation: 0 };
  if (kind === 'slot')
    return { kind, mode: 'add',
             x: snap((a.x + b.x) / 2), y: snap((a.y + b.y) / 2),
             length: snap(d) || 1, height: 10,
             rotation: Math.round(Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI) };
  return null;
}

/* ---------------- the path tool (chained lines + arcs) ---------------- */

function pathClick(p) {
  if (!pathStart) { pathStart = p; updateHint(); draw(); return; }

  // clicking near the start closes the profile
  const closeR = view.ext / 30;
  if (pathSegs.length >= 1 && !pendingVia
      && dist(p, pathStart) < closeR) { finishPath(); return; }

  if (segMode === 'arc') {
    if (!pendingVia) { pendingVia = p; updateHint(); draw(); return; }
    pathSegs.push({ type: 'arc', via: [pendingVia.x, pendingVia.y],
                    to: [p.x, p.y] });
    pendingVia = null;
  } else {
    pathSegs.push({ type: 'line', to: [p.x, p.y] });
  }
  updateHint(); draw();
}

function finishPath() {
  if (!pathStart || pathSegs.length < 1) return;
  skEnts.push({ kind: 'path', mode: 'add', x: 0, y: 0,
                start: [pathStart.x, pathStart.y], segments: pathSegs });
  selEnt = skEnts.length - 1;
  pathStart = null; pathSegs = []; pendingVia = null;
  renderEnts(); updateHint();
}

function pathCursor() {
  if (!pathSegs.length) return pathStart;
  const last = pathSegs[pathSegs.length - 1].to;
  return { x: last[0], y: last[1] };
}

function finishPolygon() {
  const pts = clicks.map(p => [p.x, p.y]);
  skEnts.push({ kind: 'polygon', mode: 'add', x: 0, y: 0, points: pts });
  selEnt = skEnts.length - 1;
  clicks = []; ghost = null;
  renderEnts(); updateHint();
}

function buildGhost(p) {
  if (!clicks.length) return null;
  if (tool === 'polygon')
    return { kind: 'polygon', mode: 'add', x: 0, y: 0, ghostOpen: true,
             points: [...clicks.map(q => [q.x, q.y]), [p.x, p.y]] };
  return twoClickEntity(tool, clicks[0], p);
}

/* ---------------- hit testing ---------------- */

function hitTest(p) {
  for (let i = skEnts.length - 1; i >= 0; i--) {
    const e = skEnts[i];
    const lx = p.x - (e.x || 0), ly = p.y - (e.y || 0);
    // un-rotate the point into the entity's local frame
    const a = -(e.rotation || 0) * Math.PI / 180;
    const rx = lx * Math.cos(a) - ly * Math.sin(a);
    const ry = lx * Math.sin(a) + ly * Math.cos(a);
    if (e.kind === 'circle' && Math.hypot(lx, ly) <= e.r) return i;
    if (e.kind === 'regular_polygon' && Math.hypot(lx, ly) <= e.radius) return i;
    if (e.kind === 'rectangle'
        && Math.abs(rx) <= e.w / 2 && Math.abs(ry) <= e.h / 2) return i;
    if (e.kind === 'ellipse'
        && (rx / e.rx) ** 2 + (ry / e.ry) ** 2 <= 1) return i;
    if (e.kind === 'slot'
        && Math.abs(rx) <= e.length / 2 + e.height / 2
        && Math.abs(ry) <= e.height / 2) return i;
    if (e.kind === 'polygon' && e.points
        && pointInPolygon(lx, ly, e.points)) return i;
    if (e.kind === 'path' && e.start) {
      const pts = pathOutline(e).map(q => [q.x, q.y]);
      if (pointInPolygon(p.x, p.y, pts)) return i;
    }
  }
  return -1;
}

function pointInPolygon(x, y, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
    if (((yi > y) !== (yj > y))
        && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

/* ---------------- entity cards (numeric editing) ---------------- */

function renderEnts() { renderCards(); draw(); }

function renderCards() {
  const box = document.getElementById('skEntities');
  box.innerHTML = '';
  skEnts.forEach((e, i) => {
    const card = document.createElement('div');
    card.className = 'skent' + (i === selEnt ? ' sel' : '');
    card.onclick = () => { selEnt = i; renderCards(); draw(); };
    const head = document.createElement('div'); head.className = 'eh';
    head.innerHTML = `<b>${OP_ICONS[e.kind] || ''} ${e.kind}</b>`;
    const mode = document.createElement('select');
    mode.innerHTML = '<option value="add">add</option>' +
                     '<option value="subtract">cut</option>';
    mode.value = e.mode;
    mode.disabled = i === 0;                 // first must be additive
    mode.onchange = () => { e.mode = mode.value; draw(); };
    const del = document.createElement('button'); del.className = 'del';
    del.textContent = '✕';
    del.onclick = ev => { ev.stopPropagation();
      skEnts.splice(i, 1); if (selEnt >= skEnts.length) selEnt = -1;
      renderEnts(); };
    head.append(mode, del);
    card.appendChild(head);

    const f = document.createElement('div'); f.className = 'ef';
    for (const k of Object.keys(e)) {
      if (['kind', 'mode', 'points', 'ghostOpen', 'start', 'segments']
          .includes(k)) continue;
      const lab = document.createElement('label');
      lab.textContent = k;
      const inp = document.createElement('input'); inp.value = e[k];
      inp.onclick = ev => ev.stopPropagation();
      inp.oninput = () => { e[k] = Number(inp.value) || 0; draw(); };
      lab.appendChild(inp); f.appendChild(lab);
    }
    for (const jsonKey of ['points', 'start', 'segments']) {
      if (!e[jsonKey]) continue;
      const lab = document.createElement('label');
      lab.textContent = jsonKey;
      const inp = document.createElement('input'); inp.style.width = '150px';
      inp.value = JSON.stringify(e[jsonKey]);
      inp.onclick = ev => ev.stopPropagation();
      inp.oninput = () => {
        try { e[jsonKey] = JSON.parse(inp.value); draw(); } catch {}
      };
      lab.appendChild(inp); f.appendChild(lab);
    }
    card.appendChild(f);
    box.appendChild(card);
  });
}

function updateHint() {
  const el = document.getElementById('skHelp');
  if (tool === 'path') {
    const msg = !pathStart ? 'Click the START point of your profile'
      : pendingVia ? 'Arc: now click the END point'
      : segMode === 'arc' ? 'Arc: click a point the arc passes THROUGH'
      : 'Click the next point · click the start (or double-click) to close';
    el.innerHTML = '';
    const mk = (label, mode) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.style.cssText = 'margin-right:6px;padding:1px 10px;border-radius:5px;' +
        'font:inherit;font-size:11.5px;cursor:pointer;border:1px solid ' +
        (segMode === mode ? 'var(--accent)' : 'var(--line)') + ';background:' +
        (segMode === mode ? 'var(--accent2)' : 'var(--panel2)') +
        ';color:' + (segMode === mode ? 'var(--accent)' : 'var(--text)');
      b.onclick = () => { segMode = mode; pendingVia = null; updateHint(); };
      return b;
    };
    el.append(mk('— Line', 'line'), mk('◠ Arc', 'arc'),
              document.createTextNode(' ' + msg));
    return;
  }
  if (!tool) el.textContent =
    'Pick a shape, then click on the canvas to draw · drag shapes to move · wheel zooms';
  else if (tool === 'polygon') el.textContent = clicks.length
    ? 'Click the next corner · double-click (or click the first point) to close'
    : 'Polygon: click each corner, double-click to close';
  else el.textContent = clicks.length
    ? 'Now click to set the size'
    : ({ circle: 'Circle: click the CENTER point',
         rectangle: 'Rectangle: click the FIRST corner',
         ellipse: 'Ellipse: click the center',
         slot: 'Slot: click the start center',
         regular_polygon: 'N-gon: click the center' }[tool] || 'Click to place');
}

/* ---------------- rendering ---------------- */

function entitySVG(e, opts = {}) {
  const col = e.mode === 'subtract' ? '#ff5d5d' : '#43c579';
  const fill = opts.ghost ? 'none'
    : e.mode === 'subtract' ? 'rgba(255,93,93,.10)' : 'rgba(67,197,121,.13)';
  const sw = opts.sel ? 2 : 1;
  const dash = opts.ghost ? ' stroke-dasharray="3 3"' : '';
  const x = e.x || 0, y = -(e.y || 0);
  const st = `fill="${fill}" stroke="${col}" stroke-width="${sw}"` +
             ` vector-effect="non-scaling-stroke"${dash}`;
  const rot = `transform="rotate(${-(e.rotation || 0)} ${x} ${y})"`;
  if (e.kind === 'rectangle')
    return `<rect x="${x - e.w / 2}" y="${y - e.h / 2}" width="${e.w}" height="${e.h}" ${st} ${rot}/>`;
  if (e.kind === 'circle')
    return `<circle cx="${x}" cy="${y}" r="${e.r}" ${st}/>`;
  if (e.kind === 'ellipse')
    return `<ellipse cx="${x}" cy="${y}" rx="${e.rx}" ry="${e.ry}" ${st} ${rot}/>`;
  if (e.kind === 'slot') {
    const r = e.height / 2;
    return `<rect x="${x - e.length / 2}" y="${y - r}" width="${e.length}" height="${e.height}" rx="${r}" ${st} ${rot}/>`;
  }
  if (e.kind === 'regular_polygon') {
    const pts = [];
    for (let k = 0; k < e.sides; k++) {
      const a = Math.PI / 2 + k * 2 * Math.PI / e.sides;
      pts.push(`${x + e.radius * Math.cos(a)},${y - e.radius * Math.sin(a)}`);
    }
    return `<polygon points="${pts.join(' ')}" ${st} ${rot}/>`;
  }
  if (e.kind === 'polygon' && e.points) {
    const pts = e.points.map(p =>
      `${(e.x || 0) + p[0]},${-((e.y || 0) + p[1])}`).join(' ');
    return e.ghostOpen
      ? `<polyline points="${pts}" ${st}/>`
      : `<polygon points="${pts}" ${st}/>`;
  }
  if (e.kind === 'path' && e.start) {
    const pts = pathOutline(e).map(q => `${q.x},${-q.y}`).join(' ');
    return e.ghostOpen
      ? `<polyline points="${pts}" ${st}/>`
      : `<polygon points="${pts}" ${st}/>`;
  }
  return '';
}

function draw() {
  const el = svg();
  const { cx, cy, ext } = view;
  el.setAttribute('viewBox', `${cx - ext} ${-cy - ext} ${2 * ext} ${2 * ext}`);

  const step = ext > 300 ? 50 : ext > 120 ? 20 : 10;
  let out = '';
  const x0 = Math.floor((cx - ext) / step) * step;
  const y0 = Math.floor((-cy - ext) / step) * step;
  for (let g = x0; g <= cx + ext; g += step)
    out += `<line x1="${g}" y1="${-cy - ext}" x2="${g}" y2="${-cy + ext}" stroke="#20242e" stroke-width="0.5" vector-effect="non-scaling-stroke"/>`;
  for (let g = y0; g <= -cy + ext; g += step)
    out += `<line x1="${cx - ext}" y1="${g}" x2="${cx + ext}" y2="${g}" stroke="#20242e" stroke-width="0.5" vector-effect="non-scaling-stroke"/>`;
  out += `<line x1="${cx - ext}" y1="0" x2="${cx + ext}" y2="0" stroke="#3a4150" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
  out += `<line x1="0" y1="${-cy - ext}" x2="0" y2="${-cy + ext}" stroke="#3a4150" stroke-width="1" vector-effect="non-scaling-stroke"/>`;

  skEnts.forEach((e, i) => out += entitySVG(e, { sel: i === selEnt }));
  if (ghost) out += entitySVG(ghost, { ghost: true });
  for (const c of clicks)
    out += `<circle cx="${c.x}" cy="${-c.y}" r="${ext / 90}" fill="#4da3ff"/>`;
  if (tool === 'path' && pathStart) {
    out += `<circle cx="${pathStart.x}" cy="${-pathStart.y}" r="${ext / 60}"
      fill="none" stroke="#4da3ff" stroke-width="1.5"
      vector-effect="non-scaling-stroke"/>`;      // close target
    for (const s of pathSegs)
      out += `<circle cx="${s.to[0]}" cy="${-s.to[1]}" r="${ext / 110}" fill="#4da3ff"/>`;
    if (pendingVia)
      out += `<circle cx="${pendingVia.x}" cy="${-pendingVia.y}" r="${ext / 110}" fill="#d9a23c"/>`;
  }

  el.innerHTML = out;
  const gridEl = document.getElementById('skGrid');
  if (gridEl) gridEl.textContent = `grid ${step}mm`;
}

/* ---------------- create the feature(s) ---------------- */

async function create() {
  const clean = skEnts.filter(e => !e.ghostOpen);
  if (!clean.length) {
    bus.emit('msg', 'bot', '⚠ The sketch is empty — pick a shape and click ' +
      'on the canvas to draw first.');
    return;
  }
  if (clean[0].mode === 'subtract') clean[0].mode = 'add';
  const entities = clean.map(e => {
    const o = { kind: e.kind, mode: e.mode };
    for (const k of Object.keys(e))
      if (!['kind', 'mode', 'ghostOpen'].includes(k)) o[k] = e[k];
    return o;
  });
  dlg().close();
  const id = document.getElementById('skName').value || 'sketch1';

  if (skOnFace) {
    // one guided action: sketch on face -> extrude -> join/cut with the body
    const op = document.getElementById('skOp').value;
    const depth = Number(document.getElementById('skDepth').value) || 10;
    await postJSON('/api/feature/add', {
      id, op: 'sketch_on_face',
      params: { face_center: skOnFace.center, face_normal: skOnFace.normal,
                entities },
      inputs: [skOnFace.inputId] });
    await postJSON('/api/feature/add', {
      id: id + '_solid', op: 'extrude', params: { amount: depth },
      inputs: [id] });
    if (op !== 'new') {
      await postJSON('/api/feature/add', {
        id: id + (op === 'cut' ? '_pocket' : '_boss'),
        op: op === 'cut' ? 'cut' : 'fuse',
        inputs: [skOnFace.inputId, id + '_solid'] });
    }
    loadMesh();
    bus.emit('msg', 'bot',
      op === 'cut' ? `Pocket cut into the face (depth ${depth}mm).`
      : op === 'join' ? `Boss added on the face (height ${depth}mm).`
      : `New body extruded from the face (${depth}mm).`);
  } else {
    const doc = await postJSON('/api/feature/add', {
      id, op: 'sketch',
      params: { plane: document.getElementById('skPlane').value,
                offset: Number(document.getElementById('skOffset').value) || 0,
                entities },
      inputs: [] });
    loadMesh(true);          // the sketch now shows in the viewport (green)
    if (!doc.error) {
      bus.emit('msg', 'bot', `Sketch "${id}" created — you can see it in the ` +
        `viewport. Set a depth to turn it into a solid, or Cancel to keep ` +
        `sketching.`);
      openFeatDialog('extrude', [id]);   // Fusion-style: finish sketch -> extrude
    }
  }
}
