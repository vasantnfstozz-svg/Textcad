// dialogs.js — the Add Feature dialog, the Spec editor, the design library,
// and the File actions (new / open / save / export / undo). These are the
// handlers the ribbon's buttons call.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON, getJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh, clearMesh } from './viewport.js';

const featDialog = () => document.getElementById('featDialog');
const libDialog = () => document.getElementById('libDialog');
const specDialog = () => document.getElementById('specDialog');

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

export async function loadSample(name) {
  const doc = await postJSON('/api/sample/' + name, {},
    name === 'compressor' ? 'building compressor (slow)…' : 'building…');
  loadMesh(true);
  bus.emit('msg', 'bot', `Opened example "${doc.name}" in a new tab. Expand a ` +
    `feature and click a blue value to edit, or tell me what to change.`);
}

/* ---------------- Add Feature dialog ---------------- */

export async function openFeatDialog(preselect, preInputs) {
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

function renderFeatForm() {
  const op = S.OPS.find(o => o.op === document.getElementById('featOp').value);
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
