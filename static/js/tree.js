// tree.js — the feature tree panel: Fusion-style rows, inline editing,
// suppress/delete/rollback actions, the spec verdict, and the status bar.

import { bus } from './bus.js';
import { S } from './state.js';
import { postJSON } from './api.js';
import { OP_ICONS } from './icons.js';
import { loadMesh, showFeatureOverlay, clearHighlight } from './viewport.js';
import { openFeatDialog } from './dialogs.js';

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
    last && last.volume != null ? 'volume ' + last.volume + ' mm³' : '';
  document.getElementById('sRebuild').textContent =
    doc.rebuild_ms != null ? 'rebuild ' + doc.rebuild_ms + ' ms' : '';

  const badge = document.getElementById('verifyBadge');
  const nWarn = (doc.warnings || []).length;
  if (!doc.features.length) { badge.className = 'none'; badge.textContent = 'empty'; }
  else if (doc.ok && nWarn) {
    badge.className = 'ok';
    badge.textContent = `✓ verified — ⚠ ${nWarn} stray bod${nWarn > 1 ? 'ies' : 'y'}`;
    badge.title = doc.warnings.join('\n');
  }
  else if (doc.ok) { badge.className = 'ok'; badge.textContent = '✓ verified'; badge.title = ''; }
  else { badge.className = 'fail'; badge.textContent = '✗ check failed'; badge.title = ''; }

  const el = treeEl();
  el.innerHTML = '';
  let pastBar = false;
  for (const f of doc.features) {
    const node = document.createElement('div');
    const hasKids = Object.keys(f.params).length > 0 || f.volume != null;
    node.className = 'node' + (S.openNodes.has(f.id) ? ' open' : '')
      + (f.suppressed ? ' suppressed' : '')
      + (S.selected === f.id ? ' sel' : '')
      + (pastBar ? ' rolledback' : '') + (hasKids ? ' haskids' : '');
    node.appendChild(buildRow(doc, f));
    node.appendChild(buildBody(f));
    const probs = f.problems.filter(p => p !== '(suppressed)');
    if (probs.length) {
      const pd = document.createElement('div'); pd.className = 'nproblems';
      pd.textContent = probs.join(' • '); node.appendChild(pd);
    }
    el.appendChild(node);
    if (doc.rollback === f.id) {
      const bar = document.createElement('div'); bar.className = 'rollbar';
      bar.title = 'rollback bar — features below are not built';
      el.appendChild(bar);
      pastBar = true;
    }
  }
  renderWarnings(doc, el);
  renderSpecRow(doc, el);
}
bus.on('doc-updated', renderDoc);

function renderWarnings(doc, el) {
  if (!doc.warnings || !doc.warnings.length) return;
  const w = document.createElement('div');
  w.style.cssText = 'margin:8px 6px;padding:7px 9px;border:1px solid #8a6a2a;' +
    'background:rgba(217,162,60,.08);color:#d9a23c;border-radius:6px;' +
    'font-size:11.5px;line-height:1.45';
  w.innerHTML = doc.warnings.map(t => `<div>⚠ ${t}</div>`).join('');
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

  const acts = document.createElement('span'); acts.className = 'nacts';
  if (f.op === 'sketch' || f.op === 'sketch_on_face') {
    addAct(acts, '⬆', 'make solid — extrude / revolve this sketch',
      () => openFeatDialog('extrude', [f.id]));
  }
  const isBar = doc.rollback === f.id;
  addAct(acts, isBar ? '⤓' : '⤒',
    isBar ? 'release rollback bar (build everything)'
          : 'roll back to here (build only up to this feature)',
    () => postJSON('/api/rollback', { feature_id: isBar ? null : f.id })
            .then(() => loadMesh()));
  addAct(acts, f.suppressed ? '▶' : '⏸',
    f.suppressed ? 'unsuppress' : 'suppress',
    () => postJSON('/api/feature/suppress',
      { feature_id: f.id, suppressed: !f.suppressed }).then(() => loadMesh()));
  addAct(acts, '✕', 'delete feature',
    () => postJSON('/api/feature/remove', { feature_id: f.id })
            .then(() => loadMesh()));

  const dot = document.createElement('span'); dot.className = 'ndot ' + f.status;
  row.append(acts, dot);
  row.onclick = () => selectFeature(f.id);
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
                    <span class="pro">${f.volume} mm³</span>`;
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
  if (S.selected === fid) {          // click again = deselect
    S.selected = null; clearHighlight(); renderDoc(S.lastDoc); return;
  }
  S.selected = fid; renderDoc(S.lastDoc);
  showFeatureOverlay(fid);
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
