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

/* A cell being edited OWNS the rows. The panel is non-modal on purpose, so the
   document moves under it all the time and every 'doc-updated' redrew #pmRows
   — taking the <input> the user was typing in with it, silently. Measured
   2026-09-19: '3+ha' half typed into a formula cell, a feature added from
   elsewhere, and the input was simply gone. A redraw that arrives during an
   edit waits for it; Enter, Escape and blur all end the edit and then run it. */
let editing = false;
let staleRows = false;

/* an inline edit of one cell: Enter commits the typed text, Escape / blur puts
   the old text back; a value equal to the old one is not posted */
function inlineEdit(cell, oldVal, commit) {
  const input = document.createElement('input');
  input.value = oldVal;
  cell.replaceChildren(input); input.focus(); input.select();
  editing = true;
  let done = false;
  const finish = async ok => {
    if (done) return; done = true;
    const raw = input.value.trim();
    try {
      if (!ok || raw === '' || raw === String(oldVal)) { cell.textContent = oldVal; return; }
      await commit(raw);                 // its own doc-updated redraws the rows
    } finally {
      editing = false;
      if (staleRows) { staleRows = false; render(); }
    }
  };
  input.onclick = e => e.stopPropagation();
  input.onkeydown = e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(false);
}

/* The parameter as the DOCUMENT has it NOW, or null with a sentence and a
   redraw. A row is a SNAPSHOT: the panel is non-modal on purpose — the tree,
   the AI designer, MCP, undo and a version restore all keep working beside
   it — and a cell held open for editing stops the redraw as well, so `p` can
   be minutes old by the time Enter is pressed.

   The note cell is where that hurt, because `/api/parameters` requires the
   formula and the note edit sent the one its row remembered. Measured
   2026-09-19: bore = 6, the note cell opened, the formula changed to 12.5
   from elsewhere, Enter on the note — and the document went back to 6, so
   typing a comment silently undid a dimension and every feature using `bore`
   rebuilt at the old size. The same snapshot re-created a parameter that had
   been DELETED under the edit. */
function current(name) {
  const now = ((S.lastDoc && S.lastDoc.parameters) || []).find(q => q.name === name);
  if (now) return now;
  say(`⚠ Parameters: "${name}" is not in this design any more — nothing was changed.`);
  staleRows = true;              // inlineEdit's finally puts the table back
  return null;
}

function render() {
  const body = g('pmRows');
  if (!body) return;
  if (editing) { staleRows = true; return; }   // see inlineEdit
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
    expr.onclick = () => inlineEdit(expr, p.expr, v => current(p.name)
      && postJSON('/api/parameters', { name: p.name, expr: v }, 'changing…'));
    const val = cell('pmval', p.problem ? '⚠' : `= ${fmt(p.value)}`,
      p.problem || 'the value the formula works out to');
    const comment = cell('pmcomment', p.comment || '', 'click to add a note');
    // the FORMULA comes from the document as it is when the note is saved, not
    // from the row — see current() below
    comment.onclick = () => inlineEdit(comment, p.comment || '', v => {
      const now = current(p.name);
      return now && postJSON('/api/parameters',
        { name: p.name, expr: now.expr, comment: v }, 'noting…');
    });
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
  editing = staleRows = false;    // no cell of a closed panel is being edited
  g('paramsDialog').style.display = 'block';
  render();
  g('pmName').focus();
}
export function closeParams() {
  on = false;
  editing = staleRows = false;
  g('paramsDialog').style.display = 'none';
}
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
