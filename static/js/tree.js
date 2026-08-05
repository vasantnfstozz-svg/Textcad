// tree.js — the feature tree panel: Fusion-style rows, inline editing,
// suppress/delete/rollback actions, the spec verdict, and the status bar.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh, showFeatureOverlay, clearHighlight } from './viewport.js';
import { openFeatDialog } from './dialogs.js';
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
         `${probs.join('; ')} — click it in the tree to adjust or delete it.`;
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
  nameEl.ondblclick = e => { e.stopPropagation(); beginRename(nameEl, f); };

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
  addAct(acts, '✕', 'delete feature',
    () => postJSON('/api/feature/remove', { feature_id: f.id })
            .then(() => loadMesh()));

  const dot = document.createElement('span'); dot.className = 'ndot ' + f.status;
  row.append(acts, dot);
  row.onclick = () => selectFeature(f.id);
  // Fusion's gesture: double-click a feature = edit it with its own tool
  row.ondblclick = () => {
    if (f.op === 'sketch' || f.op === 'sketch_on_face') bus.emit('edit-sketch', f);
    else if (f.op === 'extrude' || f.op === 'extrude_face') openExtrudeEdit(f.id);
  };
  return row;
}

function addAct(parent, label, title, fn) {
  const b = document.createElement('button'); b.className = 'nact';
  b.textContent = label; b.title = title;
  b.onclick = e => { e.stopPropagation(); fn(); };
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
        await postJSON('/api/edit', { feature_id: f.id, param: k, value: cb.checked });
        loadMesh();
      };
      val.appendChild(cb); pr.appendChild(val); body.appendChild(pr);
    } else if (typeof v === 'number' || typeof v === 'string') {
      val.className = 'pval'; val.textContent = v; val.title = 'click to edit';
      val.onclick = e => { e.stopPropagation(); beginEdit(val, f.id, k, v); };
      pr.appendChild(val); body.appendChild(pr);
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
