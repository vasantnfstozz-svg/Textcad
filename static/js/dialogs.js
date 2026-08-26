// dialogs.js — the Add Feature dialog, the Spec editor, the design library,
// and the File actions (new / open / save / export / undo). These are the
// handlers the ribbon's buttons call.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON, getJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh, clearMesh, cancelPlanePick } from './viewport.js';
import { cancelExtrude } from './extrude.js';

const featDialog = () => document.getElementById('featDialog');
const libDialog = () => document.getElementById('libDialog');
const exDialog = () => document.getElementById('exDialog');
const specDialog = () => document.getElementById('specDialog');

/* ---------------- one command at a time ----------------
   User mandate (2026-08-05, applies to EVERY design tool): while a tool's
   panel is open (e.g. Extrude), other tools must REFUSE — say why in chat
   and flash the open panel — until the user presses OK or Cancel. */
export function modalGuard() {
  if (!S.modalTool) return false;
  bus.emit('msg', 'bot', `⚠ Finish the ${S.modalTool} first — press OK or ` +
    `Cancel in its panel (flashing on the right).`);
  const el = S.modalToolPanel && document.getElementById(S.modalToolPanel);
  if (el) {
    el.classList.remove('modalflash');
    void el.offsetWidth;                    // restart the CSS animation
    el.classList.add('modalflash');
    setTimeout(() => el.classList.remove('modalflash'), 1300);
  }
  return true;
}

/* ---------------- File actions ---------------- */

export async function actionNew() {
  const name = prompt('Name for the new design:', 'my-part');
  if (name === null) return;
  await postJSON('/api/new', { name });          // opens as a NEW TAB
  clearMesh();
  bus.emit('msg', 'bot', `Opened "${name}" in a new tab — the previous design ` +
    `is still open. Describe a part, or build with the Create / Sketch tabs.`);
}

export async function actionSave() {
  const res = await postJSON('/api/save', {}, 'saving…');
  if (res.saved) bus.emit('msg', 'bot', `Saved "${res.saved}" to the design library.`);
}

export function actionTracePng() {
  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = 'image/png,image/jpeg';
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    const h = prompt('Traced artwork height in mm:', '50');
    if (h === null) return;
    const dataUrl = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = rej;
      r.readAsDataURL(f);
    });
    const out = await postJSON('/api/trace-png', {
      png_base64: dataUrl,
      height_mm: parseFloat(h) || 50,
      feature_id: (f.name.replace(/\.[^.]*$/, '').replace(/[^\w-]+/g, '-')
                   .slice(0, 24) || 'traced-image'),
    }, 'tracing…');
    if (out && !out.error) {
      const i = out.trace_info || {};
      bus.emit('msg', 'bot',
        `Traced "${f.name}" into sketch "${i.feature_id}" — ` +
        `${i.width_mm}×${i.height_mm}mm, ${i.contours} outline(s), ` +
        `${i.holes} hole(s). Select it in the tree and Extrude.`);
    }
  };
  inp.click();
}

export function actionImportStl() {
  if (modalGuard()) return;
  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = '.stl,model/stl';
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    const dataUrl = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = rej;
      r.readAsDataURL(f);
    });
    const out = await postJSON('/api/import-stl', {
      stl_base64: dataUrl,
      feature_id: (f.name.replace(/\.[^.]*$/, '').replace(/[^\w-]+/g, '-')
                   .slice(0, 24) || 'imported-stl'),
    }, 'importing STL…');
    if (out && !out.error) {
      loadMesh(out.features.length === 1);   // fit on the very first body
      const i = out.import_info || {};
      const bodies = i.bodies > 1 ? `${i.bodies} bodies` : 'a body';
      bus.emit('msg', 'bot',
        `Imported "${f.name}" as ${bodies} in feature "${i.feature_id}" — ` +
        `${(i.size_mm || []).join('×')}mm, ${i.triangles} triangles` +
        (i.repair ? ` (${i.repair})` : '') + `. ` +
        `Move / Cut / Fuse it like any other body (units read as mm — ` +
        `edit the feature's scale if it came in the wrong size).`);
    }
  };
  inp.click();
}

export async function actionOpen() {
  const list = await getJSON('/api/designs');
  const el = document.getElementById('libList');
  el.innerHTML = list.length ? '' :
    '<div style="color:var(--dim);padding:8px">No saved designs yet — use Save.</div>';
  for (const d of list) {
    const item = document.createElement('div'); item.className = 'libitem';
    item.innerHTML = `<span><b>${d.name}</b></span>
      <span class="meta">${d.features} features</span>`;
    item.onclick = async () => {
      libDialog().close();
      await postJSON('/api/open/' + d.file, {}, 'opening…');   // new tab
      loadMesh(true);
    };
    el.appendChild(item);
  }
  libDialog().showModal();
}

export async function actionExport() {
  const r = await fetch('/api/export', { method: 'POST' });
  const res = await r.json();
  bus.emit('msg', 'bot', res.error ? '⚠ ' + res.error : '⬇ Exported: ' + res.path);
}

export async function actionUndo() {
  const doc = await postJSON('/api/undo', {}, 'undoing…');
  if (!doc.error) { loadMesh(true); bus.emit('msg', 'bot', '↶ Undone.'); }
}

/* The Examples gallery: the designs the user actually built in this tool,
   grouped, with a thumbnail each. It replaces three hardcoded sample buttons —
   a 97-feature satellite panel and a four-part pump answer "show me what this
   does" far better than a demo flange, and they were previously buried in
   File > Open among the scratch files. */
export async function actionExamples() {
  const dlg = exDialog();
  const host = document.getElementById('exList');
  host.innerHTML = '<div class="exempty">loading…</div>';
  dlg.showModal();
  let data;
  try { data = await getJSON('/api/examples'); }
  catch (e) { data = { groups: [] }; }
  host.innerHTML = '';
  if (!data.groups || !data.groups.length) {
    host.innerHTML = '<div class="exempty">No examples catalogued yet ' +
      '(designs/examples.json).</div>';
    return;
  }
  for (const g of data.groups) {
    const h = document.createElement('div');
    h.className = 'exgroup';
    h.innerHTML = `<b>${g.group}</b><span>${g.blurb || ''}</span>`;
    host.appendChild(h);
    const grid = document.createElement('div');
    grid.className = 'exgrid';
    for (const d of g.designs) grid.appendChild(exampleCard(d, dlg));
    host.appendChild(grid);
  }
}

function exampleCard(d, dlg) {
  const card = document.createElement('button');
  card.className = 'excard';
  card.dataset.file = d.file;
  card.title = `${d.description || d.title}\n\n${d.features} features`;
  const thumb = document.createElement('div');
  thumb.className = 'exthumb';
  if (d.preview) {
    const img = document.createElement('img');
    img.src = `/api/design-preview/${d.file}`;
    img.alt = d.title;
    img.loading = 'lazy';
    thumb.appendChild(img);
  } else {
    // nothing rendered on disk yet: say what the design is made of rather
    // than showing an empty box
    thumb.classList.add('noimg');
    thumb.textContent = (d.ops && d.ops.length ? d.ops : ['design'])
      .slice(0, 3).join(' · ');
  }
  const body = document.createElement('div');
  body.className = 'exbody';
  body.innerHTML =
    `<div class="extitle">${d.title || d.file}</div>` +
    `<div class="exdesc">${d.description || ''}</div>` +
    `<div class="exmeta">${d.features} features</div>`;
  card.append(thumb, body);
  card.onclick = async () => {
    dlg.close();
    clearMesh();
    const doc = await postJSON(`/api/open/${d.file}`, {},
                              `opening ${d.title || d.file}…`);
    if (doc.error) return;
    await loadMesh(true, true);
    bus.emit('msg', 'bot', `Opened "${doc.name}" — ` +
      `${(doc.features || []).length} features. ${d.description || ''}`);
  };
  return card;
}

export async function loadSample(name) {
  const doc = await postJSON('/api/sample/' + name, {},
    name === 'compressor' ? 'building compressor (slow)…' : 'building…');
  loadMesh(true);
  bus.emit('msg', 'bot', `Opened example "${doc.name}" in a new tab. Expand a ` +
    `feature and click a blue value to edit, or tell me what to change.`);
}

/* ---------------- Add Feature dialog ---------------- */

export async function openFeatDialog(preselect, preInputs) {
  cancelPlanePick();                 // a pending plane-pick must not linger
  cancelExtrude();                   // a lingering extrude gizmo would eat clicks
  if (!S.OPS.length) S.OPS = await getJSON('/api/ops');
  const sel = document.getElementById('featOp');
  sel.innerHTML = S.OPS.map(o =>
    `<option value="${o.op}">${OP_ICONS[o.op] || ''} ${o.op} — ${o.kind}</option>`)
    .join('');
  if (preselect) sel.value = preselect;
  sel.onchange = renderFeatForm; renderFeatForm();
  if (preInputs && preInputs.length) {   // explicit inputs replace the default
    document.querySelectorAll('#featInputs input')
      .forEach(cb => cb.checked = preInputs.includes(cb.value));
  }
  featDialog().showModal();
}

function paramField(p) {
  const label = p.unit ? `${p.name} <span class="punit">(${p.unit})</span>` : p.name;
  if (typeof p.default === 'boolean')
    // real checkbox: sending the STRING "false" reads as true in Python and
    // silently flipped flags like extrude's `both` (doubled every part)
    return `<label style="flex-direction:row;align-items:center;gap:6px">${label}
        <input type="checkbox" data-param="${p.name}" data-bool="1"
          ${p.default ? 'checked' : ''} style="width:auto">
      </label>`;
  if (p.enum)                            // dropdown — no more guessing valid words
    return `<label>${label}
        <select data-param="${p.name}" data-enum="1">${p.enum.map(v =>
          `<option value="${v}" ${v === p.default ? 'selected' : ''}>${v}</option>`
        ).join('')}</select>
      </label>`;
  return `<label>${label}
      <input data-param="${p.name}" value="${p.default ?? ''}"
        placeholder="${p.name === 'points' ? '[[r,z],[r,z],...]' : (p.unit || 'number')}">
    </label>`;
}

/* Fusion-style auto-name (disc1, fillet2, …): the user should never have to
   INVENT an id — only override it when they want a meaningful one. Re-suggest
   on op change only while the field still holds our previous suggestion. */
let lastSuggestedId = '';
function suggestId(op) {
  const ids = new Set(((S.lastDoc && S.lastDoc.features) || []).map(f => f.id));
  let n = 1; while (ids.has(op + n)) n++;
  return op + n;
}

function renderFeatForm() {
  const op = S.OPS.find(o => o.op === document.getElementById('featOp').value);
  const idEl = document.getElementById('featId');
  if (!idEl.value.trim() || idEl.value === lastSuggestedId) {
    lastSuggestedId = suggestId(op.op);
    idEl.value = lastSuggestedId;
  }
  document.getElementById('featParams').innerHTML =
    op.params.map(paramField).join('') +
    (op.note ? `<div class="opnote">ℹ ${op.note}</div>` : '');
  document.getElementById('featInputsWrap').style.display =
    op.inputs > 0 ? '' : 'none';
  const doc = S.lastDoc || { features: [] };
  const tip = op.inputs > 0
    ? [...doc.features].reverse().find(f => !f.suppressed) : null;
  document.getElementById('featInputs').innerHTML = doc.features.map(f =>
    `<label><input type="checkbox" value="${f.id}"
       ${tip && tip.id === f.id ? 'checked' : ''}>${f.id}</label>`).join('') ||
    '<span style="color:var(--dim)">no features yet</span>';
}

export function initDialogs() {
  document.getElementById('featForm').onsubmit = async e => {
    if (e.submitter && e.submitter.value === 'cancel') return;
    e.preventDefault(); featDialog().close();
    const params = {};
    for (const inp of document.querySelectorAll('#featParams input')) {
      if (inp.dataset.bool) { params[inp.dataset.param] = inp.checked; continue; }
      const v = inp.value.trim(); if (!v) continue;
      params[inp.dataset.param] = v.startsWith('[') ? JSON.parse(v)
        : (isNaN(Number(v)) ? v : Number(v));
    }
    for (const sel of document.querySelectorAll('#featParams select[data-enum]'))
      params[sel.dataset.param] = sel.value;
    const inputs = [...document.querySelectorAll('#featInputs input:checked')]
      .map(c => c.value);
    const doc = await postJSON('/api/feature/add', {
      id: document.getElementById('featId').value,
      op: document.getElementById('featOp').value, params, inputs });
    if (!doc.error) loadMesh(doc.features.length === 1);
    document.getElementById('featId').value = '';
  };

  document.getElementById('libClose').onclick = () => libDialog().close();
  document.getElementById('exClose').onclick = () => exDialog().close();

  document.getElementById('specForm').onsubmit = async e => {
    if (e.submitter && e.submitter.value === 'cancel') return;
    e.preventDefault(); specDialog().close();
    const num = id => { const v = document.getElementById(id).value.trim();
                        return v === '' ? null : Number(v); };
    const spec = { n_solids: num('spN'), symmetry: num('spSym'),
                   tip_radius: num('spTip'), tol: num('spTol') };
    const size = [num('spSX'), num('spSY'), num('spSZ')];
    if (size.some(v => v !== null)) spec.size = size;
    const holesRaw = document.getElementById('spHoles').value.trim();
    if (holesRaw) {
      try { spec.holes = JSON.parse(holesRaw); }
      catch { bus.emit('msg', 'bot', '⚠ holes must be JSON like {"4": 6}'); }
    }
    const doc = await postJSON('/api/spec', { spec }, 're-verifying…');
    if (!doc.error) bus.emit('msg', 'bot', doc.ok
      ? '✓ Spec updated — design verifies against the new requirements.'
      : '✗ Spec updated — design does NOT meet it yet: '
        + doc.spec_problems.join('; '));
  };
}

export function actionSpec() {
  const s = (S.lastDoc && S.lastDoc.spec) || {};
  const set = (id, v) => document.getElementById(id).value = v ?? '';
  set('spN', s.n_solids); set('spSym', s.symmetry); set('spTip', s.tip_radius);
  const size = s.size || [null, null, null];
  set('spSX', size[0]); set('spSY', size[1]); set('spSZ', size[2]);
  set('spHoles', s.holes ? JSON.stringify(s.holes) : '');
  set('spTol', s.tol);
  specDialog().showModal();
}
