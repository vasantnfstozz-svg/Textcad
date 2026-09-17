// params.js — Named parameters (Tier 2, specs/named-parameters.md): Fusion's
// Change Parameters dialog. A panel listing the design's named values — name,
// formula, value, comment, who uses it — with a row to add one, inline edits,
// rename and delete. Every fact shown is the server's (`doc.parameters`, R1):
// the value is what the document evaluated, the users are who it found, a
// problem is its sentence. This file posts what the user typed and redraws
// on 'doc-updated'; it computes nothing.
//
// A panel, not a command: no modal lock — the tree and every tool stay live
// while it is open (a formula is typed INTO a tree row, with the panel open
// beside it).

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON } from './api.js';

const g = id => document.getElementById(id);
let on = false;
const say = t => bus.emit('msg', 'bot', t);

const fmt = v => v == null ? '?' : Math.round(v * 10000) / 10000;

/* an inline edit of one cell: Enter commits the typed text, Escape / blur puts
   the old text back; a value equal to the old one is not posted */
function inlineEdit(cell, oldVal, commit) {
  const input = document.createElement('input');
  input.value = oldVal;
  cell.replaceChildren(input); input.focus(); input.select();
  let done = false;
  const finish = async ok => {
    if (done) return; done = true;
    const raw = input.value.trim();
    if (!ok || raw === '' || raw === String(oldVal)) { cell.textContent = oldVal; return; }
    await commit(raw);
  };
  input.onclick = e => e.stopPropagation();
  input.onkeydown = e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(false);
}

function render() {
  const body = g('pmRows');
  if (!body) return;
  body.innerHTML = '';
  const params = (S.lastDoc && S.lastDoc.parameters) || [];
  for (const p of params) {
    const row = document.createElement('div');
    row.className = 'pmrow' + (p.problem ? ' bad' : '');
    row.dataset.name = p.name;
    const name = cell('pmname', p.name, 'click to rename — every formula that uses it follows');
    name.onclick = () => inlineEdit(name, p.name, v => postJSON('/api/parameters/rename',
      { old: p.name, new: v }, 'renaming…'));
    const expr = cell('pmexpr', p.expr, 'click to change the formula');
    expr.onclick = () => inlineEdit(expr, p.expr, v => postJSON('/api/parameters',
      { name: p.name, expr: v }, 'changing…'));
    const val = cell('pmval', p.problem ? '⚠' : `= ${fmt(p.value)}`,
      p.problem || 'the value the formula works out to');
    const comment = cell('pmcomment', p.comment || '', 'click to add a note');
    comment.onclick = () => inlineEdit(comment, p.comment || '', v => postJSON('/api/parameters',
      { name: p.name, expr: p.expr, comment: v }, 'noting…'));
    const n = (p.users || []).length + (p.used_by_parameters || []).length;
    const users = cell('pmusers', n ? `${n} use${n === 1 ? '' : 's'}` : 'unused',
      n ? `used by ${[...(p.users || []), ...(p.used_by_parameters || [])].join(', ')}`
        : 'no feature or parameter names this yet');
    const del = document.createElement('button');
    del.className = 'pmdel'; del.textContent = '✕';
    del.title = n ? 'in use — change its users first' : 'delete this parameter';
    del.onclick = () => postJSON('/api/parameters/remove', { name: p.name }, 'removing…');
    for (const c of [name, expr, val, comment, users, del]) row.appendChild(c);
    body.appendChild(row);
  }
  g('pmEmpty').style.display = params.length ? 'none' : '';
}
function cell(cls, text, title) {
  const s = document.createElement('span');
  s.className = cls; s.textContent = text; s.title = title;
  return s;
}

async function add() {
  const name = g('pmName').value.trim(), expr = g('pmExpr').value.trim();
  const comment = g('pmComment').value.trim();
  if (!name || !expr) { say('⚠ Parameters: give a name and a value (or formula) — for example wall and 3.'); return; }
  const doc = await postJSON('/api/parameters', { name, expr, comment: comment || null }, 'adding…');
  if (doc && (doc.parameters || []).some(p => p.name === name)) {
    g('pmName').value = ''; g('pmExpr').value = ''; g('pmComment').value = '';
    g('pmName').focus();
  }
}

export function isParamsOpen() { return on; }
export function openParams() {
  on = true;
  g('paramsDialog').style.display = 'block';
  render();
  g('pmName').focus();
}
export function closeParams() { on = false; g('paramsDialog').style.display = 'none'; }
export function toggleParams() { if (on) closeParams(); else openParams(); }

export function initParams() {
  g('pmAdd').onclick = add;
  for (const id of ['pmName', 'pmExpr', 'pmComment'])
    g(id).addEventListener('keydown', e => {
      e.stopPropagation();
      if (e.key === 'Enter') { e.preventDefault(); add(); }
    });
  g('pmClose').onclick = closeParams;
  bus.on('doc-updated', () => { if (on) render(); });
}
