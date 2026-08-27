// measure.js — the Measure tool: how wide, how far, how thick.
//
// User request (2026-08-27): "we dont have proper scale to measure distance
// between two point … if i am clicking a line of circle, it should show the
// diameter, and i want to see the distance between two faces".
//
// Fusion parity:
//   rule 2  select-then-command — whatever is already picked becomes A
//   rule 9  one command at a time — sets S.modalTool while the panel is open
//   rule 7  failures speak — a measurement that cannot be made says why
//
// Read-only. /api/measure never mutates the document, so clicking around to
// read numbers cannot touch the design or its version history. Editing the
// numbers is P1 (see MEASURE-PLAN.md); the panel already leaves room for it.

import { bus } from './bus.js';
import { postJSON } from './api.js';
import { S } from './state.js';
import { showDimension, clearDimension, loadMesh } from './viewport.js';

// the two selections, in click order
let A = null, B = null;
let busy = false;
let last = null;          // the last measurement (carries .driver)
let mine = false;         // true while OUR OWN edit is rebuilding the document

const el = id => document.getElementById(id);
const panel = () => el('measureDialog');

function label(sel) {
  if (!sel) return '—';
  const t = sel.info && sel.info.type ? ` · ${sel.info.type}` : '';
  const kind = sel.kind === 'face' ? 'Face' : 'Edge';
  return `${kind} ${sel.id}${t}`;
}

/* ------------------------------------------------------------- open/close */

export function isMeasuring() { return S.modalTool === 'Measure'; }

export function openMeasure() {
  A = null; B = null;
  // select-then-command (rule 2): a face already picked in the viewport IS the
  // first selection — retyping a click the user already made is the kind of
  // friction Fusion does not have.
  if (S.pickedFace && S.pickedFace.id != null) {
    A = { kind: 'face', id: S.pickedFace.id, body: S.pickedFace.body,
          info: S.pickedFace };
  } else if (S.pickedCurved && S.pickedCurved.id != null) {
    A = { kind: 'face', id: S.pickedCurved.id, body: S.pickedCurved.body,
          info: S.pickedCurved };
  }
  panel().style.display = 'block';
  S.modalTool = 'Measure';
  S.modalToolPanel = 'measureDialog';
  render();
  if (A) run();
}

export function cancelMeasure() {
  if (S.modalTool === 'Measure') { S.modalTool = null; S.modalToolPanel = null; }
  A = null; B = null;
  clearDimension();
  if (panel()) panel().style.display = 'none';
}

/* ------------------------------------------------------------- selecting */

export function initMeasure() {
  bus.on('pick', p => {
    if (!isMeasuring() || !p || p.clear) return;
    if (p.kind !== 'face' && p.kind !== 'edge') {
      // a sketch profile is not a measurable solid feature — say so rather
      // than silently ignoring the click (rule 7)
      note('A sketch profile has no 3D dimension to read — click a face or an edge.');
      return;
    }
    const sel = { kind: p.kind, id: p.id, body: p.body, info: p.info };
    // Two slots, filled in click order, then it cycles: the third click
    // becomes the new A and clears B, so the user can keep walking a chain of
    // dimensions without pressing Reset between every pair.
    if (!A) A = sel;
    else if (!B) {
      if (same(A, sel)) { note('That is the same thing — pick a different one.'); return; }
      B = sel;
    } else { A = sel; B = null; }
    render();
    run();
  });
  // A rebuild invalidates face/edge indices (they are array positions), so a
  // stale pair must be dropped rather than re-measured against new geometry.
  // EXCEPT after our own Set: the backend already re-measured this very
  // selection and reported what it became, so dropping it here would blank the
  // panel the instant the user's edit succeeded.
  bus.on('doc-updated', () => {
    if (!isMeasuring() || mine) return;
    A = null; B = null; clearDimension(); render();
  });
  el('meCancel').onclick = cancelMeasure;
  el('meReset').onclick = () => {
    A = null; B = null; clearDimension(); render();
  };
  el('meApply').onclick = applyEdit;
  el('meInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); applyEdit(); }
    // Esc in the box reverts the box, it does not close the tool — losing a
    // whole selection to a stray Esc while typing is infuriating
    if (e.key === 'Escape') { e.stopPropagation(); showEdit(last); }
  });
  el('meSwap').onclick = () => {
    if (!B) return;
    const t = A; A = B; B = t;
    render(); run();
  };
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape' && isMeasuring()) { e.preventDefault(); cancelMeasure(); }
  });
}

function same(x, y) {
  return x && y && x.kind === y.kind && x.id === y.id && x.body === y.body;
}

/* ------------------------------------------------------------- measuring */

async function run() {
  if (!A || busy) return;
  busy = true;
  try {
    const body = { a: strip(A) };
    if (B) body.b = strip(B);
    // plain fetch, not postJSON: read-only on every click, so the busy overlay
    // must not strobe and no document broadcast is expected (same reasoning as
    // provenance.js's face lookup)
    const res = await fetch('/api/measure', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      // studio.py serves the JS from disk but Python only at startup, so a
      // server older than this page 404s here and the panel would just sit
      // blank — the same trap provenance.js documents.
      show(null, res.status === 404
        ? 'this needs a server restart — the page is newer than the running '
          + 'server (stop studio.py and start it again)'
        : `the measurement failed (HTTP ${res.status})`);
      return;
    }
    const r = await res.json();
    if (r.error) { show(null, r.error); return; }
    show(r, null);
  } catch (e) {
    show(null, 'could not reach the server for this measurement');
  } finally {
    busy = false;
  }
}

function strip(sel) {
  return { body: sel.body ?? null, kind: sel.kind, id: sel.id };
}

/* ------------------------------------------------------------- rendering */

function render() {
  el('meSelA').textContent = label(A);
  el('meSelB').textContent = label(B);
  el('meSelA').classList.toggle('empty', !A);
  el('meSelB').classList.toggle('empty', !B);
  el('meSwap').disabled = !B;
  el('meHint').textContent = !A
    ? 'Click a face or an edge in the viewport.'
    : (!B ? 'Click a second face or edge for a distance — or read the first one below.'
          : 'Click anything else to start a new pair.');
  if (!A) show(null, null);
}

function note(msg) {
  el('meNote').textContent = msg;
  el('meNote').style.display = 'block';
}

function show(r, error) {
  last = error ? null : r;
  el('meNote').style.display = 'none';
  const val = el('meValue'), rows = el('meRows');
  rows.innerHTML = '';
  if (error) {
    val.textContent = '—';
    val.classList.add('bad');
    note(error);
    showEdit(null);
    clearDimension();
    return;
  }
  val.classList.remove('bad');
  if (!r) {
    val.textContent = '—';
    el('meKind').textContent = '';
    showEdit(null);
    clearDimension();
    return;
  }
  val.textContent = r.label || '—';
  el('meKind').textContent = KIND_NAMES[r.kind] || r.kind || '';
  showEdit(r);
  for (const [k, v] of (r.rows || [])) {
    const d = document.createElement('div');
    d.className = 'merow';
    d.innerHTML = `<span class="k"></span><span class="v"></span>`;
    d.querySelector('.k').textContent = k;
    d.querySelector('.v').textContent = v;
    rows.appendChild(d);
  }
  // draw what was actually measured (see viewport.showDimension)
  if (r.from && r.to) showDimension(r.from, r.to, r.label);
  else clearDimension();
}

/* ---------------------------------------------------- the editable half ----
   A dimension is typeable ONLY when the backend resolved a driver: one param
   that this number IS. Anything derived — the gap between two independent
   features — stays read-only and says why, rather than the tool guessing which
   side of the gap should move (MEASURE-PLAN.md). A missing box is a small
   disappointment; a box that silently moves the wrong wall is not. */

function showEdit(r) {
  const row = el('meEdit'), who = el('meDriver');
  const d = r && r.driver;
  if (!d) {
    row.style.display = 'none';
    who.style.display = 'none';
    return;
  }
  row.style.display = 'flex';
  el('meInput').value = r.value;
  who.style.display = 'block';
  who.textContent = `drives ${d.label}`;
}

async function applyEdit() {
  if (!last || !last.driver || busy) return;
  const v = parseFloat(el('meInput').value);
  if (!isFinite(v)) { note('Type a number first.'); return; }
  let failed = null, warn = null;
  busy = true;
  try {
    const body = { a: strip(A), value: v };
    if (B) body.b = strip(B);
    // postJSON (unlike the read path): this DOES mutate the document, so the
    // busy overlay and the doc-updated broadcast are both wanted
    mine = true;                       // this doc-updated is ours; keep A/B
    const r = await postJSON('/api/measure/set', body);
    if (r.error) failed = r.error;
    else if (r.warning) warn = r.warning;
  } catch (e) {
    failed = 'could not apply that change';
  } finally {
    // Release BEFORE repainting. run() early-returns while `busy` is set, so
    // re-reading inside this window silently did nothing and the panel kept
    // showing the OLD dimension after a successful edit — the model had
    // changed and the readout had not (caught in UI verification).
    busy = false;
  }
  if (failed) { note(failed); mine = false; return; }
  // RELOAD THE VIEWPORT. postJSON only broadcasts the document; every mutating
  // tool reloads the mesh itself. Without this the readout said 30 mm and the
  // status bar showed the new volume while the part on screen still drew the
  // old hole, until the 3 s watcher happened to fire (caught in UI
  // verification). It also clears the now-stale pick overlay, which was
  // contradicting the readout with the pre-edit radius.
  await loadMesh();
  // Repaint from the REBUILT geometry rather than assuming the write landed
  // where it was asked to (house rule 3). The backend verified it too; this is
  // what the user actually sees.
  await run();
  if (warn) note('⚠ ' + warn);         // after run(), which clears the note
  setTimeout(() => { mine = false; }, 0);
}

const KIND_NAMES = {
  diameter: 'diameter', length: 'edge length', area: 'face area',
  thickness: 'material thickness', gap: 'open gap', step: 'step / depth',
  distance: 'minimum distance', centres: 'centre to centre', angle: 'angle',
};
