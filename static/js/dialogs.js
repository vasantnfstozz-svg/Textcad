// dialogs.js — the Add Feature dialog, the Spec editor, the design library,
// and the File actions (new / open / save / export / undo). These are the
// handlers the ribbon's buttons call.

import { S } from './state.js';
import { bus } from './bus.js';
import { postJSON, getJSON } from './api.js';
import { askText } from './ask.js';
import { OP_ICONS } from './icons.js';
import { loadMesh, clearMesh, cancelPlanePick } from './viewport.js';
import { cancelTool, uid, toolSessionOpen } from './tool.js';

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
  const el = S.modalToolPanel && document.getElementById(S.modalToolPanel);
  if (el && el.style.display === 'none') {   // OK/Cancel pressed, its rebuild still landing
    bus.emit('msg', 'bot', `⚠ ${S.modalTool} is still finishing — one moment.`);
    return true;
  }
  bus.emit('msg', 'bot', `⚠ Finish the ${S.modalTool} first — press OK or ` +
    `Cancel in its panel (flashing on the right).`);
  if (el) {
    // The panels STACK in one column now, so the one we are pointing at may
    // have been scrolled out of sight by a second panel below it — a flash
    // nobody can see is the same as no answer at all.
    el.scrollIntoView({ block: 'nearest' });
    el.classList.remove('modalflash');
    void el.offsetWidth;                    // restart the CSS animation
    el.classList.add('modalflash');
    setTimeout(() => el.classList.remove('modalflash'), 1300);
  }
  return true;
}

/* ---------------- File actions ---------------- */

/* A default that does not collide: "my-part", then "my-part-2", ... The user
   asked for "some default name", and a default that is already taken is worse
   than none — saving would silently land on somebody else's design. */
async function freeDesignName(base = 'my-part') {
  let taken = new Set();
  try {
    taken = new Set((await getJSON('/api/designs')).map(d => d.file));
  } catch (e) { /* offline: the plain base is still a fine suggestion */ }
  if (!taken.has(base)) return base;
  for (let n = 2; n < 999; n++) if (!taken.has(`${base}-${n}`)) return `${base}-${n}`;
  return base;
}

export async function actionNew() {
  const name = await askText('New design', {
    label: 'Name',
    value: await freeDesignName(),
    body: 'Opens in a new tab. The design you have open now stays open.',
    ok: 'Create',
    validate: v => v ? null : 'Give the design a name.',
  });
  if (!name) return;
  await postJSON('/api/new', { name });          // opens as a NEW TAB
  clearMesh();
  bus.emit('msg', 'bot', `Opened "${name}" in a new tab — the previous design ` +
    `is still open. Describe a part, or build with the Create / Sketch tabs.`);
}

export async function actionSave() {
  const res = await postJSON('/api/save', {}, 'saving…');
  if (res.saved) bus.emit('msg', 'bot', `Saved "${res.saved}" to the design library.`);
}

// Trace PNG moved into the SKETCH ribbon (user request 2026-09-01): it now
// inserts into the open sketch — see traceIntoSketch in sketcher.js. The
// feature-creating API path (/api/trace-png without entities_only) stays for
// scripts and the MCP tools.

export function actionImportStl() {
  if (modalGuard()) return;
  const inp = document.createElement('input');
  inp.type = 'file';
  // one button, both formats — the user's own STEP exports must come back in
  // (2026-08-31: "i have exported a compressor design here, but if i want to
  // open it again the same file here, its not working")
  inp.accept = '.stl,.step,.stp,model/stl,model/step';
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    const dataUrl = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = rej;
      r.readAsDataURL(f);
    });
    const isStep = /\.(step|stp)$/i.test(f.name);
    const fid = (f.name.replace(/\.[^.]*$/, '').replace(/[^\w-]+/g, '-')
                 .slice(0, 24) || (isStep ? 'imported-step' : 'imported-stl'));
    const out = isStep
      ? await postJSON('/api/import-step',
                       { step_base64: dataUrl, feature_id: fid },
                       'importing STEP…')
      : await postJSON('/api/import-stl',
                       { stl_base64: dataUrl, feature_id: fid },
                       'importing STL…');
    if (out && !out.error) {
      // FORCE the reload: an imported BREP's first tessellation can take many
      // seconds (a compressor's splined blades), and a non-forced load shows
      // no busy overlay — the user stared at an empty viewport with a green
      // tree and no clue anything was still happening (seen in UI
      // verification of the STEP import).
      loadMesh(out.features.length === 1, true);
      const i = out.import_info || {};
      const bodies = i.bodies > 1 ? `${i.bodies} bodies` : 'a body';
      bus.emit('msg', 'bot',
        `Imported "${f.name}" as ${bodies} in feature "${i.feature_id}" — ` +
        `${(i.size_mm || []).join('×')}mm` +
        (isStep ? ' (exact BREP — nothing was meshed)'
                : `, ${i.triangles} triangles`
                  + (i.repair ? ` (${i.repair})` : '')) + `. ` +
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
      const doc = await postJSON('/api/open/' + d.file, {}, 'opening…');
      loadMesh(true);
      if (!doc.error) openedMsg(doc);
    };
    el.appendChild(item);
  }
  libDialog().showModal();
}

export async function actionExport() {
  const r = await fetch('/api/export', { method: 'POST' });
  const res = await r.json();
  if (res.error) { bus.emit('msg', 'bot', '⚠ ' + res.error); return; }
  // Echo what was MEASURED FROM THE FILE, not what we hope is in it — a
  // wrong body (stale tab, intermediate solid) or a MISSING one shows up
  // instantly as the wrong count/size/volume next to the path. Every number
  // here is a field on the response; nothing is recomputed (R1).
  const facts = (res.size && res.volume != null)
    ? ` — ${res.n_solids} solid${res.n_solids === 1 ? '' : 's'}, `
      + `${res.size.map(v => Math.round(v * 10) / 10).join('×')} mm, `
      + `${(res.volume / 1000).toFixed(1)} cm³ (measured from the file)`
    : '';
  // A design with several separate bodies is normal CAD, but it changes what
  // the next program does with the file, so say it plainly instead of leaving
  // the user to notice a piece is missing downstream.
  const many = res.bodies > 1
    ? ` This design has ${res.bodies} separate bodies and all of them are in `
      + `the file. Join them with Extrude's Join (or a fuse feature) if you `
      + `want one solid.`
    : '';
  const unsound = (res.is_valid === false || res.is_manifold === false)
    ? ' ⚠ The kernel reports the exported geometry is not a clean solid —'
      + ' check it before machining.'
    : '';
  bus.emit('msg', 'bot', '⬇ Exported: ' + res.path + facts + many + unsound);
}

export async function actionUndo() {
  // rule 9: a tool SESSION owns the document while it is open — undoing under
  // it strands the panel on a feature that has gone (Measure keeps no session,
  // and undoing a typed dimension is what its user is asking for)
  if (toolSessionOpen() && modalGuard()) return;
  const doc = await postJSON('/api/undo', {}, 'undoing…');
  if (!doc.error) { loadMesh(true); bus.emit('msg', 'bot', '↶ Undone.'); }
}

/* Undo without redo makes trying something out a one-way trip — you can
   retreat but never return, so people stop experimenting (user: "it can be
   easily undo and redo in that feature tree"). */
export async function actionRedo() {
  if (toolSessionOpen() && modalGuard()) return;   // its feature is mid-edit
  const doc = await postJSON('/api/redo', {}, 'redoing…');
  if (!doc.error) { loadMesh(true); bus.emit('msg', 'bot', '↷ Redone.'); }
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
  /* Three DIFFERENT empty states, and they used to render as one lie: a
     dead server made getJSON throw, the catch flattened it to {groups:[]},
     and the dialog then blamed designs/examples.json — a file that was
     perfectly fine. Say which one it actually is. */
  let data, unreachable = false;
  try { data = await getJSON('/api/examples'); }
  catch (e) { unreachable = true; data = { groups: [] }; }
  host.innerHTML = '';
  if (unreachable) {
    host.innerHTML = '<div class="exempty">Can’t reach the TextCAD ' +
      'server, so nothing can load here — the gallery is served by it. ' +
      'Is <b>studio.py</b> still running? Start it again, then reload this ' +
      'page.</div>';
    return;
  }
  if (data.error) {                       // backend parsed the catalog and failed
    host.innerHTML = `<div class="exempty">${data.error}</div>`;
    return;
  }
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

/* Opening a design REUSES its tab (studio.py `_find_tab`), so the message has
   to say what actually happened — three "Opened flange-100" lines above a
   single flange-100 tab is exactly the confusion this change set out to end. */
function openedMsg(doc, extra = '') {
  const n = (doc.features || []).length;
  const what = doc.reloaded
    ? `Reloaded "${doc.name}" from disk — ${n} features (Undo restores what the `
      + `tab had before).`
    : doc.tab_reused
      ? `Switched to "${doc.name}" — already open, ${n} features.`
      : `Opened "${doc.name}" — ${n} features.`;
  bus.emit('msg', 'bot', extra ? `${what} ${extra}` : what);
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
    openedMsg(doc, d.description || '');
  };
  return card;
}

export async function loadSample(name) {
  const doc = await postJSON('/api/sample/' + name, {},
    name === 'compressor' ? 'building compressor (slow)…' : 'building…');
  loadMesh(true);
  openedMsg(doc, 'Expand a feature and click a blue value to edit, or tell ' +
                 'me what to change.');
}

/* ---------------- Add Feature dialog ---------------- */

export async function openFeatDialog(preselect, preInputs) {
  cancelPlanePick();                 // a pending plane-pick must not linger
  cancelTool();                   // a lingering extrude gizmo would eat clicks
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
function renderFeatForm() {
  const op = S.OPS.find(o => o.op === document.getElementById('featOp').value);
  const idEl = document.getElementById('featId');
  if (!idEl.value.trim() || idEl.value === lastSuggestedId) {
    lastSuggestedId = uid(op.op);
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
    e.preventDefault();
    const params = {};
    for (const inp of document.querySelectorAll('#featParams input')) {
      if (inp.dataset.bool) { params[inp.dataset.param] = inp.checked; continue; }
      const v = inp.value.trim(); if (!v) continue;
      if (v.startsWith('[')) {
        // A missing bracket used to THROW out of this handler — and the dialog
        // had already closed, so the feature was never added and nothing was
        // said at all (rule 7: failures speak). The dialog now stays open on
        // the box that needs fixing.
        try { params[inp.dataset.param] = JSON.parse(v); }
        catch {
          bus.emit('msg', 'bot', `⚠ "${inp.dataset.param}" is not a valid list — ` +
            'it must be JSON like [[r,z],[r,z],…]. Nothing was added; fix that ' +
            'box and press OK again.');
          return;
        }
      } else params[inp.dataset.param] = isNaN(Number(v)) ? v : Number(v);
    }
    for (const sel of document.querySelectorAll('#featParams select[data-enum]'))
      params[sel.dataset.param] = sel.value;
    featDialog().close();
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
    e.preventDefault();
    // These boxes are plain text, so `Number(v)` is NaN for anything that is
    // not a number ("two", "6 mm", a stray letter) and Infinity for "1e999" —
    // and JSON.stringify writes BOTH as null, which /api/spec drops (it keeps
    // only `v is not None`). So a mistyped box deleted that requirement
    // outright and the line below then said "✓ design verifies against the
    // new requirements": measured 2026-09-16, n_solids 2 on a one-body part
    // went from a red "part has 1 separate solids, expected 2" to a green
    // pass, with the box still reading "two". The holes box got this guard in
    // round one; its six siblings share the handler and the consequence.
    const bad = [];
    const num = (id, label) => {
      const v = document.getElementById(id).value.trim();
      if (v === '') return null;
      const n = Number(v);
      if (!Number.isFinite(n)) { bad.push(label); return null; }
      return n;
    };
    const spec = { n_solids: num('spN', 'solid bodies'),
                   symmetry: num('spSym', 'symmetry'),
                   tip_radius: num('spTip', 'tip radius'),
                   tol: num('spTol', 'tolerance') };
    const size = [num('spSX', 'size X'), num('spSY', 'size Y'),
                  num('spSZ', 'size Z')];
    if (size.some(v => v !== null)) spec.size = size;
    if (bad.length) {
      bus.emit('msg', 'bot', `⚠ ${bad.join(' and ')} ` +
        `${bad.length > 1 ? 'are not numbers' : 'is not a number'} — the spec ` +
        `was NOT changed; fix ${bad.length > 1 ? 'those boxes' : 'that box'} ` +
        'and press OK again.');
      return;
    }
    const holesRaw = document.getElementById('spHoles').value.trim();
    if (holesRaw) {
      // /api/spec REPLACES the whole spec with what is sent, so carrying on
      // after a parse failure DELETED the hole requirement and the next line
      // then said "✓ design verifies against the new requirements" — a green
      // verdict from a check the user never meant to drop. Stop instead, and
      // leave the dialog open on the box that needs fixing.
      try { spec.holes = JSON.parse(holesRaw); }
      catch {
        bus.emit('msg', 'bot', '⚠ holes must be JSON like {"4": 6} — the spec ' +
          'was NOT changed; fix that box and press OK again.');
        return;
      }
    }
    specDialog().close();
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
