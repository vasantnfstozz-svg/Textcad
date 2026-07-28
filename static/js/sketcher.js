// sketcher.js — the visual 2D sketch editor: shape palette, entity list with
// live SVG preview, and the two flows:
//   * plane sketch  (Sketch tab)   -> creates a "sketch" feature
//   * face sketch   (pick a face)  -> guided boss/pocket in one action

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh } from './viewport.js';

const SHAPE_FIELDS = {
  rectangle: { w: 40, h: 20, x: 0, y: 0, rotation: 0 },
  circle: { r: 15, x: 0, y: 0 },
  ellipse: { rx: 20, ry: 10, x: 0, y: 0, rotation: 0 },
  slot: { length: 30, height: 10, x: 0, y: 0, rotation: 0 },
  regular_polygon: { radius: 20, sides: 6, x: 0, y: 0, rotation: 0 },
  polygon: { points: [[0, 0], [30, 0], [15, 25]], x: 0, y: 0 },
};

let skEnts = [];
let skOnFace = null;      // {center, normal, inputId} when sketching on a face

const dlg = () => document.getElementById('sketchDialog');

function nextName() {
  const n = (S.lastDoc?.features.filter(
    f => f.op === 'sketch' || f.op === 'sketch_on_face').length || 0) + 1;
  return 'sketch' + n;
}

export function openSketchEditor() {
  skOnFace = null;
  skEnts = [{ kind: 'rectangle', mode: 'add', ...SHAPE_FIELDS.rectangle }];
  document.getElementById('skName').value = nextName();
  document.getElementById('skOffset').value = '0';
  document.getElementById('skPlaneRow').style.display = '';
  document.getElementById('skFaceNote').style.display = 'none';
  document.getElementById('skFaceExtrude').style.display = 'none';
  renderEnts();
  dlg().showModal();
}

export function openSketchOnFace(faceInfo) {
  const tip = [...(S.lastDoc?.features || [])].reverse()
    .find(f => f.volume != null);
  if (!tip) { bus.emit('msg', 'bot', '⚠ No solid to sketch on yet.'); return; }
  skOnFace = { center: faceInfo.center, normal: faceInfo.normal || null,
               inputId: tip.id };
  skEnts = [{ kind: 'circle', mode: 'add', ...SHAPE_FIELDS.circle }];
  document.getElementById('skName').value = nextName();
  document.getElementById('skPlaneRow').style.display = 'none';
  document.getElementById('skFaceNote').style.display = '';
  document.getElementById('skFaceExtrude').style.display = '';
  document.getElementById('skFaceNote').textContent =
    `On face at (${faceInfo.center.join(', ')}) of "${skOnFace.inputId}". ` +
    `Draw, set depth + Join/Cut, then Create — it builds the boss/pocket in one step.`;
  renderEnts();
  dlg().showModal();
}
bus.on('sketch-on-face', openSketchOnFace);

export function initSketcher() {
  for (const b of document.querySelectorAll('.skpalette button')) {
    b.onclick = () => {
      const kind = b.dataset.shape;
      skEnts.push({ kind, mode: 'add',
                    ...JSON.parse(JSON.stringify(SHAPE_FIELDS[kind])) });
      renderEnts();
    };
  }
  document.getElementById('skCancel').onclick = () => dlg().close();
  document.getElementById('skCreate').onclick = create;
}

function renderEnts() {
  const box = document.getElementById('skEntities');
  box.innerHTML = '';
  skEnts.forEach((e, i) => {
    const card = document.createElement('div'); card.className = 'skent';
    const head = document.createElement('div'); head.className = 'eh';
    head.innerHTML = `<b>${OP_ICONS[e.kind] || ''} ${e.kind}</b>`;
    const mode = document.createElement('select');
    mode.innerHTML = '<option value="add">add</option>' +
                     '<option value="subtract">cut</option>';
    mode.value = e.mode;
    mode.disabled = i === 0;                 // first must be additive
    mode.onchange = () => { e.mode = mode.value; draw(); };
    const del = document.createElement('button'); del.className = 'del';
    del.textContent = '✕'; del.disabled = skEnts.length === 1;
    del.onclick = () => { skEnts.splice(i, 1); renderEnts(); };
    head.append(mode, del);
    card.appendChild(head);

    const f = document.createElement('div'); f.className = 'ef';
    for (const k of Object.keys(e)) {
      if (k === 'kind' || k === 'mode' || k === 'points') continue;
      const lab = document.createElement('label');
      lab.textContent = k;
      const inp = document.createElement('input'); inp.value = e[k];
      inp.oninput = () => { e[k] = Number(inp.value) || 0; draw(); };
      lab.appendChild(inp); f.appendChild(lab);
    }
    if (e.points) {
      const lab = document.createElement('label');
      lab.textContent = 'points';
      const inp = document.createElement('input'); inp.style.width = '150px';
      inp.value = JSON.stringify(e.points);
      inp.oninput = () => {
        try { e.points = JSON.parse(inp.value); draw(); } catch {}
      };
      lab.appendChild(inp); f.appendChild(lab);
    }
    card.appendChild(f);
    box.appendChild(card);
  });
  draw();
}

function draw() {
  const svg = document.getElementById('sketchCanvas');
  let ext = 60;
  for (const e of skEnts) {
    const reach = Math.abs(e.x || 0) + Math.abs(e.y || 0) +
      (e.w || e.rx || e.r || e.radius || e.length || 30) + 10;
    ext = Math.max(ext, reach);
  }
  svg.setAttribute('viewBox', `${-ext} ${-ext} ${2 * ext} ${2 * ext}`);
  const grid = 10;
  let out = '';
  for (let g = -Math.ceil(ext / grid) * grid; g <= ext; g += grid) {
    out += `<line x1="${g}" y1="${-ext}" x2="${g}" y2="${ext}" stroke="#20242e" stroke-width="0.5"/>`;
    out += `<line x1="${-ext}" y1="${g}" x2="${ext}" y2="${g}" stroke="#20242e" stroke-width="0.5"/>`;
  }
  out += `<line x1="${-ext}" y1="0" x2="${ext}" y2="0" stroke="#3a4150" stroke-width="0.8"/>`;
  out += `<line x1="0" y1="${-ext}" x2="0" y2="${ext}" stroke="#3a4150" stroke-width="0.8"/>`;
  // NB: SVG y is down; we flip so +y is up, matching CAD
  for (const e of skEnts) {
    const col = e.mode === 'subtract' ? '#ff5d5d' : '#43c579';
    const fill = e.mode === 'subtract' ? 'rgba(255,93,93,.10)' : 'rgba(67,197,121,.13)';
    const x = e.x || 0, y = -(e.y || 0);
    const st = `fill="${fill}" stroke="${col}" stroke-width="1"`;
    if (e.kind === 'rectangle')
      out += `<rect x="${x - e.w / 2}" y="${y - e.h / 2}" width="${e.w}" height="${e.h}" ${st} transform="rotate(${-(e.rotation || 0)} ${x} ${y})"/>`;
    else if (e.kind === 'circle')
      out += `<circle cx="${x}" cy="${y}" r="${e.r}" ${st}/>`;
    else if (e.kind === 'ellipse')
      out += `<ellipse cx="${x}" cy="${y}" rx="${e.rx}" ry="${e.ry}" ${st} transform="rotate(${-(e.rotation || 0)} ${x} ${y})"/>`;
    else if (e.kind === 'slot') {
      const r = e.height / 2;
      out += `<rect x="${x - e.length / 2}" y="${y - r}" width="${e.length}" height="${e.height}" rx="${r}" ${st} transform="rotate(${-(e.rotation || 0)} ${x} ${y})"/>`;
    } else if (e.kind === 'regular_polygon') {
      const pts = [];
      for (let k = 0; k < e.sides; k++) {
        const a = Math.PI / 2 + k * 2 * Math.PI / e.sides;
        pts.push(`${x + e.radius * Math.cos(a)},${y - e.radius * Math.sin(a)}`);
      }
      out += `<polygon points="${pts.join(' ')}" ${st}/>`;
    } else if (e.kind === 'polygon' && e.points) {
      const pts = e.points.map(p => `${(e.x || 0) + p[0]},${-((e.y || 0) + p[1])}`).join(' ');
      out += `<polygon points="${pts}" ${st}/>`;
    }
  }
  svg.innerHTML = out;
}

async function create() {
  const entities = skEnts.map(e => {
    const o = { kind: e.kind, mode: e.mode };
    for (const k of Object.keys(e))
      if (k !== 'kind' && k !== 'mode') o[k] = e[k];
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
    await postJSON('/api/feature/add', {
      id, op: 'sketch',
      params: { plane: document.getElementById('skPlane').value,
                offset: Number(document.getElementById('skOffset').value) || 0,
                entities },
      inputs: [] });
    bus.emit('msg', 'bot', 'Sketch created. Now select it and use Extrude or ' +
      'Revolve from the Sketch tab to turn it into a solid.');
  }
}
