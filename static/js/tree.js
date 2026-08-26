// tree.js — the feature tree panel: Fusion-style rows, inline editing,
// suppress/delete/rollback actions, the spec verdict, and the status bar.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON, getJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh, showFeatureOverlay, clearHighlight } from './viewport.js';
import { openFeatDialog, modalGuard } from './dialogs.js';
import { openExtrude, openExtrudeEdit, activeExtrudeId } from './extrude.js';
import { fmtVol } from './settings.js';

const treeEl = () => document.getElementById('tree');

export function renderDoc(doc) {
  S.lastDoc = doc;
  document.getElementById('docTitle').innerHTML = `<b>${doc.name}</b>`;
  document.getElementById('sDoc').innerHTML = `<b>${doc.name}</b>`;
  document.getElementById('featCount').textContent =
    doc.features.length ? doc.features.length + ' features' : '';
  document.getElementById('sFeatures').textContent =
    doc.features.length + ' features';
  const last = doc.features.filter(f => !f.suppressed).at(-1);
  document.getElementById('sVolume').textContent =
    last && last.volume != null ? 'volume ' + fmtVol(last.volume) : '';
  document.getElementById('sRebuild').textContent =
    doc.rebuild_ms != null ? 'rebuild ' + doc.rebuild_ms + ' ms' : '';

  const badge = document.getElementById('verifyBadge');
  const nWarn = (doc.warnings || []).length;
  if (!doc.features.length) { badge.className = 'none'; badge.textContent = 'empty'; }
  else if (doc.ok && nWarn) {
    // separate bodies are NORMAL (Fusion's Bodies folder) — say how many,
    // don't cry "stray": the old wording read as an error on every boss
    badge.className = 'ok';
    badge.textContent = `✓ verified — ${nWarn + 1} bodies`;
    badge.title = doc.warnings.join('\n');
  }
  else if (doc.ok) { badge.className = 'ok'; badge.textContent = '✓ verified'; badge.title = ''; }
  else { badge.className = 'fail'; badge.textContent = '✗ check failed'; badge.title = ''; }

  const el = treeEl();
  el.innerHTML = '';
  // rolled-back marking follows BUILD order (the features list), independent
  // of how the rows are nested for display below
  const rolled = new Set();
  {
    let past = false;
    for (const f of doc.features) {
      if (past) rolled.add(f.id);
      if (doc.rollback === f.id) past = true;
    }
  }
  // Fusion grouping: a consumed sketch renders as a CHILD of the feature
  // that consumed it (Extrude1 ▸ sketch1), not as a sibling row — the tree
  // then reads as design history, not a flat op list
  const isSk = f => f.op === 'sketch' || f.op === 'sketch_on_face';
  const consumerOf = {};
  for (const f of doc.features)
    for (const d of f.inputs) {
      const src = doc.features.find(x => x.id === d);
      if (src && isSk(src) && !(d in consumerOf)) consumerOf[d] = f.id;
    }
  const makeNode = (f, child) => {
    const node = document.createElement('div');
    node.dataset.fid = f.id;
    const hasKids = Object.keys(f.params).length > 0 || f.volume != null;
    node.className = 'node' + (S.openNodes.has(f.id) ? ' open' : '')
      + (f.suppressed ? ' suppressed' : '')
      + (S.selected === f.id ? ' sel' : '')
      + (rolled.has(f.id) ? ' rolledback' : '')
      + (hasKids ? ' haskids' : '') + (child ? ' child' : '');
    node.appendChild(buildRow(doc, f));
    node.appendChild(buildBody(f));
    // '(after rollback bar)' is edit-isolation plumbing, not a user problem —
    // the dimmed row already says "not built right now"
    const probs = f.problems
      .filter(p => p !== '(suppressed)' && p !== '(after rollback bar)')
      .map(humanProblem);
    if (probs.length) {
      const pd = document.createElement('div'); pd.className = 'nproblems';
      pd.textContent = probs.join(' • '); node.appendChild(pd);
    }
    el.appendChild(node);
  };
  for (const f of doc.features) {
    if (consumerOf[f.id]) continue;          // renders with its consumer
    // creation order (user mandate R4): the sketch FIRST, its consumer below
    for (const d of f.inputs)
      if (consumerOf[d] === f.id)
        makeNode(doc.features.find(x => x.id === d), true);
    makeNode(f, false);
  }
  renderWarnings(doc, el);
  renderSpecRow(doc, el);
}
bus.on('doc-updated', renderDoc);
bus.on('settings-changed', () => { if (S.lastDoc) renderDoc(S.lastDoc); });

/* Failures speak (Fusion parity rule 7): the moment a feature NEWLY fails,
   say so in chat in human words — never just the little red dot. The extrude
   panel's live feature is excluded: that tool already explains and auto-
   repairs its own failures. */
let prevFailed = new Set();
bus.on('doc-updated', doc => {
  const failed = new Map();
  for (const f of doc.features)
    if (f.status === 'failed' && !f.problems.includes('(after rollback bar)'))
      failed.set(f.id, f);
  for (const [id, f] of failed)
    if (!prevFailed.has(id) && id !== activeExtrudeId())
      bus.emit('msg', 'bot', failMessage(f));
  prevFailed = new Set(failed.keys());
});

function humanProblem(p) {
  // backend raises carry good messages — unwrap them from the Python repr
  const m = p.match(/^(ValueError|KeyError|TypeError|RuntimeError)\((['"])([\s\S]*)\2\)$/);
  if (m) return m[1] === 'TypeError'
    ? 'bad parameters — ' + m[3] : m[3];
  if (/StdFail|Standard_|OCP\.|BRep|TopoDS|GeomAbs/.test(p))
    return 'the geometry kernel rejected this shape — try smaller values ' +
           'or a different face (' + p + ')';
  if (p.includes('is unavailable'))
    return p + ' — fix that upstream feature first';
  return p;
}

function failMessage(f) {
  const probs = f.problems.filter(p => p !== '(suppressed)').map(humanProblem);
  return `⚠ Feature "${f.id}" (${f.op}) failed to build: ` +
         `${probs.join('; ')} — click it in the tree to adjust it, or ✕ to ` +
         `delete it (whatever depends on it is reconnected).`;
}

function renderWarnings(doc, el) {
  if (!doc.warnings || !doc.warnings.length) return;
  // neutral info styling — multiple bodies are a normal modeling state, and
  // the old amber ⚠ box made every boss/pocket-in-progress read as an error
  const w = document.createElement('div');
  w.style.cssText = 'margin:8px 6px;padding:7px 9px;border:1px solid var(--line);' +
    'background:rgba(120,140,170,.07);color:var(--dim);border-radius:6px;' +
    'font-size:11.5px;line-height:1.45';
  w.innerHTML = doc.warnings.map(t => `<div>ℹ ${t}</div>`).join('');
  el.appendChild(w);
}

function buildRow(doc, f) {
  const row = document.createElement('div'); row.className = 'nrow';
  row.innerHTML = `
    <span class="twisty" title="expand">▶</span>
    <span class="nico">${OP_ICONS[f.op] || '□'}</span>
    <span class="nname">${f.id}</span>
    <span class="nop">${f.op}${f.inputs.length ? ' ← ' + f.inputs.join(', ') : ''}</span>
    <span class="nspacer"></span>`;
  row.querySelector('.twisty').onclick = e => {
    e.stopPropagation();
    S.openNodes.has(f.id) ? S.openNodes.delete(f.id) : S.openNodes.add(f.id);
    renderDoc(S.lastDoc);
  };

  // Fusion's browser rename: double-click the NAME itself (double-click
  // elsewhere on the row is Edit Feature)
  const nameEl = row.querySelector('.nname');
  nameEl.title = 'double-click to rename';
  nameEl.ondblclick = e => {
    e.stopPropagation();
    if (!modalGuard()) beginRename(nameEl, f);
  };

  const acts = document.createElement('span'); acts.className = 'nacts';
  if (f.op === 'sketch' || f.op === 'sketch_on_face') {
    addAct(acts, '✎', 'edit this sketch (reopens on its plane in the viewport)',
      () => bus.emit('edit-sketch', f));
  }
  if (f.op === 'sketch' || f.op === 'sketch_on_face') {
    addAct(acts, '⬆', 'extrude this sketch into a solid',
      () => openExtrude(f.id));
  }
  if (f.op === 'extrude' || f.op === 'extrude_face') {
    // Edit Feature (Fusion parity): reopen the tool that CREATED the feature
    addAct(acts, '✎', 'edit this extrude (reopens the Extrude tool with its ' +
      'arrow and live preview)', () => openExtrudeEdit(f.id));
  }
  // suppress + rollback actions removed from the UI (user mandate R5) — the
  // backend machinery stays: edit-sketch isolation is built on rollback
  addAct(acts, '✕', 'delete this feature (dependents are reconnected; ' +
    'anything that must go with it is listed first)',
    () => deleteFeature(f.id));

  const dot = document.createElement('span'); dot.className = 'ndot ' + f.status;
  row.append(acts, dot);
  row.onclick = () => selectFeature(f.id);
  // Fusion's gesture: double-click a feature = edit it with its own tool
  row.ondblclick = () => {
    if (modalGuard()) return;
    if (f.op === 'sketch' || f.op === 'sketch_on_face') bus.emit('edit-sketch', f);
    else if (f.op === 'extrude' || f.op === 'extrude_face') openExtrudeEdit(f.id);
  };
  return row;
}

/* Fusion's browser Delete. The backend REPAIRS the history around the node
   (dependents reconnect to its upstream body), so a mid-tree sketch or extrude
   is deletable — it used to be refused with "used by [...]", which made every
   feature but the last permanent in an AI-authored tree. Whatever has to go
   WITH it is shown before anything changes (rule 7: never a silent surprise),
   and the whole delete is one undo step. */
export async function deleteFeature(fid) {
  const dry = await postJSON('/api/feature/remove',
    { feature_id: fid, dry_run: true }, 'checking dependencies…');
  const plan = dry.remove_plan;
  if (!plan) return;                 // postJSON already showed the error
  if (plan.deleted.length > 1
      && !confirm(plan.summary + '\n\nDelete anyway?')) return;
  const doc = await postJSON('/api/feature/remove',
    { feature_id: fid }, 'deleting…');
  if (doc.error) return;
  if (S.selected === fid) { S.selected = null; clearHighlight(); }
  for (const id of plan.deleted) S.openNodes.delete(id);
  loadMesh();
  const applied = doc.remove_plan;
  if (applied && applied.deleted.length > 1)
    bus.emit('msg', 'bot', '\ud83d\uddd1 ' + applied.summary.replace(/^Delete /, 'Deleted ') +
      ' Undo (Ctrl+Z) puts it back.');
}

/* Del on the selected feature — the same gesture as Fusion's browser. Sketch
   mode owns Delete for sketch entities, so stay out of its way. */
let sketchOn = false;
bus.on('sketch-mode', ({ active }) => { sketchOn = active; });
window.addEventListener('keydown', e => {
  if (e.key !== 'Delete' || sketchOn || !S.selected) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (modalGuard()) return;
  e.preventDefault();
  deleteFeature(S.selected);
});

/* Reveal a feature the user did not click on: expand it, flash it, and scroll
   it into view. Used by provenance.js when a picked FACE is traced back to the
   feature that created it — on a 79-feature tree the row is usually far off
   screen, so highlighting without scrolling would highlight nothing the user
   can see.

   Deliberately does NOT touch S.selected: selection drives the tools (Modify ->
   Scale routes on the selected feature), and merely looking at a face must not
   re-aim them. */
export function revealFeature(fid, related = []) {
  const el = treeEl();
  if (!el) return null;
  for (const n of el.querySelectorAll('.node.fromface, .node.fromface-rel'))
    n.classList.remove('fromface', 'fromface-rel');
  if (!fid) return null;                    // null = just clear the marks
  const node = el.querySelector(`.node[data-fid="${CSS.escape(fid)}"]`);
  for (const rid of related) {
    if (rid === fid) continue;
    const rn = el.querySelector(`.node[data-fid="${CSS.escape(rid)}"]`);
    if (rn) rn.classList.add('fromface-rel');
  }
  if (!node) return null;
  node.classList.add('fromface');
  node.scrollIntoView({ block: 'center', behavior: 'smooth' });
  return node;
}

function addAct(parent, label, title, fn) {
  const b = document.createElement('button'); b.className = 'nact';
  b.textContent = label; b.title = title;
  b.onclick = e => { e.stopPropagation(); if (!modalGuard()) fn(); };
  parent.appendChild(b);
}

function buildBody(f) {
  const body = document.createElement('div'); body.className = 'nbody';
  for (const [k, v] of Object.entries(f.params)) {
    const pr = document.createElement('div'); pr.className = 'prow';
    pr.innerHTML = `<span class="pname">${k}</span>`;
    const val = document.createElement('span');
    if (typeof v === 'boolean') {          // real toggle — typing "false" into a
      val.className = 'pval';              // text edit reads as truthy in Python
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = v; cb.style.width = 'auto';
      cb.onclick = e => e.stopPropagation();
      cb.onchange = async () => {
        if (modalGuard()) { cb.checked = !cb.checked; return; }
        await postJSON('/api/edit', { feature_id: f.id, param: k, value: cb.checked });
        loadMesh();
      };
      val.appendChild(cb); pr.appendChild(val); body.appendChild(pr);
    } else if (typeof v === 'number' || typeof v === 'string') {
      val.className = 'pval'; val.textContent = v; val.title = 'click to edit';
      val.onclick = e => {
        e.stopPropagation();
        if (!modalGuard()) beginEdit(val, f.id, k, v);
      };
      pr.appendChild(val); body.appendChild(pr);
      // a pillar's outer/inner size reads as a DIAMETER on any drawing, so
      // offer Ø next to every radius and write back radius = Ø / 2
      if (typeof v === 'number' && isRadius(k))
        body.appendChild(diameterRow(f.id, k, v));
    } else if (k === 'entities' && Array.isArray(v)) {
      // NEVER dump raw entity JSON (user, 2026-08-25: "we dont need see to
      // entities, and all"). Each shape gets its own dimension rows instead.
      body.appendChild(shapeList(f, v));
    } else if (Array.isArray(v) && v.length && Array.isArray(v[0])) {
      body.appendChild(pr);                       // label row
      body.appendChild(pointsTable(f.id, k, v));  // editable table below
    } else {
      val.className = 'pro';
      val.textContent = Array.isArray(v) ? JSON.stringify(v) : v;
      pr.appendChild(val); body.appendChild(pr);
    }
  }
  if (f.volume != null) {
    const pr = document.createElement('div'); pr.className = 'prow';
    pr.innerHTML = `<span class="pname">volume</span>
                    <span class="pro">${fmtVol(f.volume)}</span>`;
    body.appendChild(pr);
  }
  return body;
}

/* ---------------- shapes inside a sketch ----------------
   A sketch's `entities` used to render as a raw JSON dump — unreadable, and
   un-editable. Now every shape lists the dimensions it is actually defined by
   (rectangle -> width/height, circle -> radius + Ø, slot -> length/height),
   editable in place, so a square can be resized without opening the sketch
   editor at all. Shapes defined by a coordinate list (traced paths, polygons)
   cannot be sensibly typed as numbers, so they show a summary and a button
   into the sketch editor. */

let SHAPES = null;                  // /api/sketch/kinds, fetched once
async function shapeCatalog() {
  if (!SHAPES) {
    try {
      const got = await getJSON('/api/sketch/kinds');
      SHAPES = got && got.fields ? { ...got, ok: true } : null;
    } catch (e) { /* fall through */ }
    // A server older than this page has no /api/sketch/kinds. That must NOT
    // leave the user with shape cards that are empty except a dropdown (it
    // did, and it reads as "the tree is broken"). Fall back to the entity's
    // OWN numeric fields, with raw key names, and say why.
    if (!SHAPES) SHAPES = { ok: false, fields: {}, common: [], diameter: {},
                            geometry: {} };
  }
  return SHAPES;
}
// warm it up at boot AND re-render once it lands: the first paint can happen
// before the fetch returns, and a shape card with no catalog has no rows
shapeCatalog().then(() => { if (S.lastDoc) renderDoc(S.lastDoc); });

const isRadius = k =>
  /(^|_)r$|radius/i.test(k) && !/pitch_circle/i.test(k);

function diameterRow(fid, param, radius) {
  const pr = document.createElement('div');
  pr.className = 'prow dia';
  pr.innerHTML = `<span class="pname">Ø ${param.replace(/radius/i, '')
    .replace(/[_ ]+$/, '') || 'dia'}</span>`;
  const val = document.createElement('span');
  val.className = 'pval';
  val.textContent = round4(radius * 2);
  val.title = 'diameter — click to edit (sets the radius to half of it)';
  val.onclick = e => {
    e.stopPropagation();
    if (modalGuard()) return;
    beginEditWith(val, radius * 2, async d => {
      await postJSON('/api/edit',
        { feature_id: fid, param, value: round4(d / 2) });
      loadMesh();
    });
  };
  pr.appendChild(val);
  return pr;
}

function round4(n) { return Math.round(n * 10000) / 10000; }

function shapeList(feat, entities) {
  const box = document.createElement('div');
  box.className = 'shapes';
  const cat = SHAPES || { fields: {}, common: [], diameter: {}, geometry: {} };

  entities.forEach((ent, i) => {
    const kind = ent.kind || '?';
    const card = document.createElement('div');
    card.className = 'shape';

    const head = document.createElement('div');
    head.className = 'shead';
    head.innerHTML = `<span class="sidx">${i + 1}</span>` +
      `<span class="skind">${kind.replace(/_/g, ' ')}</span>`;
    head.appendChild(modeToggle(feat, entities, i));
    card.appendChild(head);

    const known = cat.ok && cat.fields[kind];
    const dims = known ? cat.fields[kind] : genericFields(ent);
    for (const f of dims)
      if (ent[f.key] !== undefined)
        card.appendChild(entRow(feat, entities, i, f.key, f.label, f.unit));

    // Ø for round shapes, right under the radius
    const dkey = known ? (cat.diameter || {})[kind] : genericRadius(ent);
    if (dkey && typeof ent[dkey] === 'number')
      card.appendChild(entRow(feat, entities, i, dkey, 'Ø diameter', 'mm',
                              2));

    for (const f of (known ? (cat.common || []) : GENERIC_COMMON))
      if (ent[f.key] !== undefined)
        card.appendChild(entRow(feat, entities, i, f.key, f.label, f.unit));

    const gkey = known ? (cat.geometry || {})[kind] : genericGeometry(ent);
    if (gkey) card.appendChild(geometryNote(feat, ent, gkey));

    box.appendChild(card);
  });
  if (!entities.length) {
    const none = document.createElement('div');
    none.className = 'shempty';
    none.textContent = 'no shapes in this sketch';
    box.appendChild(none);
  } else if (cat.ok === false) {
    box.appendChild(staleCatalogNote());     // failures speak (rule 7)
  }
  return box;
}

/* ---- working without the catalog ----
   Everything above prefers /api/sketch/kinds (labels live next to the geometry
   that reads them). When that endpoint is missing — a server started before it
   existed — we still show every numeric field the shape actually has, under its
   raw key name, so dimensions stay editable instead of vanishing. */

const GENERIC_SKIP = new Set(['kind', 'mode', 'x', 'y', 'rotation']);
const GENERIC_COMMON = [{ key: 'x', label: 'x', unit: 'mm' },
                        { key: 'y', label: 'y', unit: 'mm' },
                        { key: 'rotation', label: 'angle', unit: 'deg' }];

function genericFields(ent) {
  return Object.keys(ent)
    .filter(k => !GENERIC_SKIP.has(k) && typeof ent[k] === 'number')
    .map(k => ({ key: k, label: k, unit: '' }));
}

function genericRadius(ent) {
  for (const k of ['r', 'radius'])
    if (typeof ent[k] === 'number') return k;
  return null;
}

function genericGeometry(ent) {
  for (const k of ['segments', 'points'])
    if (Array.isArray(ent[k])) return k;
  return null;
}

function staleCatalogNote() {
  const d = document.createElement('div');
  d.className = 'shstale';
  d.textContent = 'raw field names — restart the server (studio.py) for '
    + 'labelled dimensions like width / Ø diameter';
  return d;
}

/* one editable dimension of one shape. `factor` renders value*factor and
   divides on the way back (that is all a diameter is). */
function entRow(feat, entities, i, key, label, unit, factor = 1) {
  const pr = document.createElement('div');
  pr.className = 'prow' + (factor !== 1 ? ' dia' : '');
  pr.innerHTML = `<span class="pname">${label}</span>`;
  const raw = entities[i][key];
  const shown = typeof raw === 'number' ? round4(raw * factor) : raw;
  const val = document.createElement('span');
  val.className = 'pval';
  val.textContent = shown;
  val.title = `click to edit${unit && unit !== 'count' ? ' (' + unit + ')' : ''}`;
  val.onclick = e => {
    e.stopPropagation();
    if (modalGuard()) return;
    beginEditWith(val, shown, v => applyEntity(feat, entities, i, key,
                                               factor === 1 ? v : v / factor));
  };
  pr.appendChild(val);
  return pr;
}

/* add / subtract: does this shape ADD material to the profile, or cut into the
   shapes drawn before it. A dropdown, not a text box — "subtract" typed into a
   text field is how holes get lost.

   The FIRST shape cannot subtract: sketch._compose refuses a leading
   subtraction ("first entity cannot be a subtraction"), because there is
   nothing yet to cut into. Offering it there was a guaranteed red feature, so
   the first card shows a fixed 'add' badge that explains itself instead. */
const MODE_HELP =
  'add = this shape becomes material · subtract = it cuts into the shapes '
  + 'above it (a circle inside a rectangle makes a hole; a circle on its own '
  + 'is simply left out)';

function modeToggle(feat, entities, i) {
  if (i === 0) {
    const badge = document.createElement('span');
    badge.className = 'smode first';
    badge.textContent = 'add';
    badge.title = 'the first shape defines the profile, so it always adds — '
      + 'nothing exists yet for it to cut into. ' + MODE_HELP;
    return badge;
  }
  const sel = document.createElement('select');
  sel.className = 'smode';
  sel.title = MODE_HELP;
  for (const m of ['add', 'subtract']) {
    const o = document.createElement('option');
    o.value = m; o.textContent = m;
    if ((entities[i].mode || 'add') === m) o.selected = true;
    sel.appendChild(o);
  }
  sel.onclick = e => e.stopPropagation();
  sel.onchange = e => {
    e.stopPropagation();
    if (modalGuard()) { sel.value = entities[i].mode || 'add'; return; }
    applyEntity(feat, entities, i, 'mode', sel.value);
  };
  return sel;
}

function geometryNote(feat, ent, gkey) {
  const n = Array.isArray(ent[gkey]) ? ent[gkey].length : 0;
  const wrap = document.createElement('div');
  wrap.className = 'shgeom';
  const size = pathSize(ent, gkey);
  wrap.textContent = `${n} ${gkey}` + (size ? ` · ${size}` : '');
  const btn = document.createElement('button');
  btn.className = 'shbtn';
  btn.textContent = '✎ edit shape';
  btn.title = 'this outline is a coordinate list — reshape it in the sketch editor';
  btn.onclick = e => { e.stopPropagation(); if (!modalGuard()) bus.emit('edit-sketch', feat); };
  wrap.appendChild(btn);
  return wrap;
}

/* overall size of a coordinate-list shape, so the row says something useful
   about a traced outline instead of just "8 segments" */
function pathSize(ent, gkey) {
  const pts = [];
  if (Array.isArray(ent.start)) pts.push(ent.start);
  for (const seg of (ent[gkey] || [])) {
    if (Array.isArray(seg)) { pts.push(seg); continue; }
    if (seg && Array.isArray(seg.to)) pts.push(seg.to);
    if (seg && Array.isArray(seg.via)) pts.push(seg.via);
  }
  if (pts.length < 2) return '';
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const w = Math.max(...xs) - Math.min(...xs);
  const h = Math.max(...ys) - Math.min(...ys);
  return `${round4(w)} × ${round4(h)} mm`;
}

/* write ONE field of ONE shape back, as a whole-array param edit (the document
   engine edits a named param; `entities` is that param) */
async function applyEntity(feat, entities, i, key, value) {
  const next = entities.map(e => ({ ...e }));
  next[i][key] = value;
  await postJSON('/api/edit',
    { feature_id: feat.id, param: 'entities', value: next });
  loadMesh();
}

/* inline edit helper shared by the shape rows and the Ø rows */
function beginEditWith(el, oldVal, commit) {
  const input = document.createElement('input');
  input.value = oldVal;
  el.replaceChildren(input); input.focus(); input.select();
  let done = false;
  const finish = async ok => {
    if (done) return; done = true;
    const raw = input.value.trim();
    const num = Number(raw);
    if (!ok || raw === '' || (isNaN(num) && raw !== String(oldVal))) {
      el.textContent = oldVal; return;
    }
    if (isNaN(num) || num === Number(oldVal)) { el.textContent = oldVal; return; }
    await commit(num);
  };
  input.onclick = e => e.stopPropagation();
  input.onkeydown = e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(false);
}

function renderSpecRow(doc, el) {
  if (!doc.spec || !Object.keys(doc.spec).length) return;
  const sr = document.createElement('div'); sr.className = 'specrow';
  sr.innerHTML = `<b style="color:${doc.spec_problems.length
      ? 'var(--fail)' : 'var(--ok)'}">spec ${doc.spec_problems.length
      ? 'FAIL' : 'PASS'}</b><br>` +
    Object.entries(doc.spec).filter(([, v]) => v != null).map(([k, v]) =>
      `<span class="schip">${k}: ${JSON.stringify(v)}</span>`).join('') +
    doc.spec_problems.map(p => `<div class="sfail">! ${p}</div>`).join('');
  el.appendChild(sr);
}

function selectFeature(fid) {
  // toggle classes IN PLACE — a full re-render here replaces the row between
  // the two clicks of a double-click, and Chromium then never synthesizes
  // dblclick (rename / Edit Feature silently stopped working)
  const was = S.selected === fid;
  S.selected = was ? null : fid;
  if (was) clearHighlight(); else showFeatureOverlay(fid);
  for (const n of treeEl().querySelectorAll('.node.sel'))
    n.classList.remove('sel');
  if (!was) {
    const n = treeEl().querySelector(`.node[data-fid="${CSS.escape(fid)}"]`);
    if (n) n.classList.add('sel');
  }
}

function beginRename(el, f) {
  const input = document.createElement('input');
  input.value = f.id;
  el.replaceChildren(input); input.focus(); input.select();
  let done = false;                 // renderDoc may destroy the input mid-way
  const finish = async commit => {
    if (done) return; done = true;
    const v = input.value.trim();
    if (!commit || !v || v === f.id) { el.textContent = f.id; return; }
    const doc = await postJSON('/api/feature/rename',
      { feature_id: f.id, name: v });        // postJSON toasts doc.error itself
    if (doc.error) { el.textContent = f.id; return; }
    if (S.selected === f.id) S.selected = v;
    if (S.openNodes.has(f.id)) { S.openNodes.delete(f.id); S.openNodes.add(v); }
    loadMesh();                     // viewport body ids follow the new name
  };
  input.onclick = e => e.stopPropagation();
  input.ondblclick = e => e.stopPropagation();
  input.onkeydown = e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(false);
}

function beginEdit(el, fid, param, oldVal) {
  const input = document.createElement('input');
  input.value = oldVal; el.replaceChildren(input); input.focus(); input.select();
  const done = async commit => {
    const raw = input.value.trim();
    const parsed = raw !== '' && !isNaN(Number(raw)) ? Number(raw) : raw;
    if (commit && raw !== '' && parsed !== oldVal) {
      await postJSON('/api/edit', { feature_id: fid, param, value: parsed });
      loadMesh();
    } else { el.textContent = oldVal; }
  };
  input.onkeydown = e => {
    if (e.key === 'Enter') { e.preventDefault(); done(true); }
    if (e.key === 'Escape') done(false);
  };
  input.onblur = () => done(false);
}

function pointsTable(fid, param, pts) {
  const box = document.createElement('div'); box.className = 'pts';
  box.innerHTML = `<div class="pthead"><span>radius</span><span>z</span></div>`;
  const rows = pts.map(p => [...p]);
  const render = () => {
    box.querySelectorAll('.ptrow, .apply').forEach(el => el.remove());
    rows.forEach((p, i) => {
      const r = document.createElement('div'); r.className = 'ptrow';
      const ir = document.createElement('input'); ir.value = p[0];
      const iz = document.createElement('input'); iz.value = p[1];
      ir.oninput = () => rows[i][0] = Number(ir.value);
      iz.oninput = () => rows[i][1] = Number(iz.value);
      const add = document.createElement('button'); add.className = 'ptbtn';
      add.textContent = '＋'; add.title = 'insert point after';
      add.onclick = () => { rows.splice(i + 1, 0, [...rows[i]]); render(); };
      const del = document.createElement('button'); del.className = 'ptbtn';
      del.textContent = '✕'; del.title = 'remove point';
      del.onclick = () => { rows.splice(i, 1); render(); };
      r.append(ir, iz, add, del); box.appendChild(r);
    });
    const apply = document.createElement('button'); apply.className = 'apply';
    apply.textContent = 'Apply profile';
    apply.onclick = async () => {
      await postJSON('/api/edit', { feature_id: fid, param,
        value: rows.map(p => [Number(p[0]), Number(p[1])]) });
      loadMesh();
    };
    box.appendChild(apply);
  };
  render();
  return box;
}
