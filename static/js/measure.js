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
import { showDimension, clearDimension, loadMesh,
         showSelectionOverlay, clearSelectionOverlay,
         setPickHighlightEnabled, setDimProbe, clearDimProbe,
         setDimProbeFrozen }
  from './viewport.js';

// the two selections, in click order
let A = null, B = null;
let busy = false;
let last = null;          // the last measurement (carries .driver)
let mine = false;         // true while OUR OWN edit is rebuilding the document
let probeOn = null;       // 'a'|'b': which selection the drag probe rides
let probeBusy = false, probePending = null;
let lastAcross = null;    // last ACROSS response — held when the ray misses
let probeFrozen = false;  // clamped at the curve's limit
let chosenSide = null;    // 'a'/'b' when the user overrode which side moves

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
  setPickHighlightEnabled(false);   // we paint A and B ourselves
  render();
  if (A) run();
}

export function cancelMeasure() {
  if (S.modalTool === 'Measure') { S.modalTool = null; S.modalToolPanel = null; }
  A = null; B = null; chosenSide = null;
  probeOn = null; clearDimProbe();
  clearDimension();
  clearSelectionOverlay();
  setPickHighlightEnabled(true);    // hand the normal highlight back
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
    chosenSide = null;      // a new pair re-asks which side should move
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
    A = null; B = null;
    probeOn = null; clearDimProbe();
    clearDimension(); render();
  });
  el('meCancel').onclick = cancelMeasure;
  el('meReset').onclick = () => {
    A = null; B = null; chosenSide = null;
    probeOn = null; clearDimProbe();
    clearDimension(); render();
  };
  el('meApply').onclick = applyEdit;
  for (const inp of document.getElementsByName('meSideR'))
    inp.onchange = () => { chosenSide = inp.value; };
  el('meInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); applyEdit(); }
    // Esc in the box reverts the box, it does not close the tool — losing a
    // whole selection to a stray Esc while typing is infuriating
    if (e.key === 'Escape') { e.stopPropagation(); showEdit(last); }
  });
  el('meSwap').onclick = () => {
    if (!B) return;
    const t = A; A = B; B = t;
    // Swapping renames the slots, so a remembered "move B" would now point at
    // the face that used to be A — exactly the move-the-wrong-thing surprise
    // this tool must not spring. Drop the override and re-ask.
    chosenSide = null;
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

function paintPicks() {
  showSelectionOverlay([
    A ? { tag: 'A', kind: A.kind, id: A.id, body: A.body } : null,
    B ? { tag: 'B', kind: B.kind, id: B.id, body: B.body } : null,
  ].filter(Boolean));
}

function render() {
  paintPicks();
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
  armProbe(r);
}

/* ---------------------------------------------------- the draggable line ----
   The witness pair is ONE sample: between a slanted wall and a boss, or around
   a cylinder, the distance varies along the geometry (user request 2026-08-31:
   "i dont know the closest distance and longest distance ... i can see the
   live value in the box"). With two picks and at least one FACE, the value
   label becomes a grab handle — dragging it slides the sample point across
   that face and every position asks the kernel for the exact local distance.
   One request in flight, latest drag position wins: same throttle discipline
   as the extrude preview. */

function armProbe(r) {
  probeOn = null;
  lastAcross = null;
  probeFrozen = false;
  clearDimProbe();
  if (!r || !A || !B || !r.from || !r.to) return;
  const on = A.kind === 'face' ? 'a' : (B.kind === 'face' ? 'b' : null);
  if (!on) return;                       // two edges: nothing to slide across
  const src = on === 'a' ? A : B;
  if (setDimProbe({ body: src.body, id: src.id }, sendProbe)) {
    probeOn = on;
    el('meHint').textContent =
      'Drag the value label to slide the measurement along the face.';
  }
}

function paintProbe(r, kindText) {
  el('meValue').textContent = r.label;
  el('meKind').textContent = kindText;
  const rows = el('meRows');
  rows.innerHTML = '';
  if (r.mode === 'across' && r.nearest != null
      && Math.abs(r.nearest - r.value) > 5e-3) {
    const d = document.createElement('div');
    d.className = 'merow';
    d.innerHTML = '<span class="k"></span><span class="v"></span>';
    d.querySelector('.k').textContent = 'nearest anywhere';
    d.querySelector('.v').textContent = r.nearest.toFixed(2) + ' mm';
    rows.appendChild(d);
  }
  showDimension(r.from, r.to, r.label);
}

async function sendProbe(pt) {
  if (!probeOn || !A || !B) return;
  if (probeBusy) { probePending = pt; return; }
  probeBusy = true;
  try {
    const res = await fetch('/api/measure/probe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ a: strip(A), b: strip(B),
                             point: pt, on: probeOn }),
    });
    const r = await res.json();
    if (!r.error && r.from && r.to) {
      // Two modes, named honestly: ACROSS runs along the source face's normal
      // and stretches to meet the other surface. Past the curve's extreme the
      // ray misses — and flipping to nearest there made the far dot TELEPORT
      // between the tangent region and the closest point on every micro-move
      // (user report 2026-08-31: "the line is dancing or vibrating"). So once
      // across has been seen, a miss CLAMPS the line at its last real
      // crossing — "that is the limit … after that no need to move" — and it
      // unfreezes the moment the cursor comes back into range.
      if (r.mode === 'across') {
        lastAcross = r;
        if (probeFrozen) { probeFrozen = false; setDimProbeFrozen(false); }
        paintProbe(r, 'across the gap at this spot');
      } else if (lastAcross) {
        if (!probeFrozen) {
          probeFrozen = true;
          setDimProbeFrozen(true);
          paintProbe(lastAcross, "across the gap — at the curve's limit");
        }
        // while frozen: ignore nearest updates entirely; the line holds
      } else {
        paintProbe(r, 'nearest from this spot');
      }
    }
  } catch (e) { /* mid-drag hiccup: the next move retries */ } finally {
    probeBusy = false;
    if (probePending) {
      const q = probePending;
      probePending = null;
      sendProbe(q);
    }
  }
}

/* ---------------------------------------------------- the editable half ----
   A dimension is typeable ONLY when the backend resolved a driver: one param
   that this number IS. Anything derived — the gap between two independent
   features — stays read-only and says why, rather than the tool guessing which
   side of the gap should move (MEASURE-PLAN.md). A missing box is a small
   disappointment; a box that silently moves the wrong wall is not. */

function showEdit(r) {
  const row = el('meEdit'), who = el('meDriver'), sideRow = el('meSide');
  const d = r && r.driver;
  // A derived distance has no param to write, but a parallel pair can still be
  // changed by MOVING one side. The backend says which sides are movable; if
  // none are, it says why and the readout stays read-only.
  const mv = r && r.move && !r.move.error ? r.move : null;
  if (!d && !mv) {
    row.style.display = 'none';
    sideRow.style.display = 'none';
    // FAILURES SPEAK (rule 7). A number with no box and no reason reads as a
    // broken tool — the user is left wondering why they cannot type here. The
    // backend gives a specific reason for a distance it cannot move; for
    // everything else say what kind of read-only this is.
    const why = (r && r.move && r.move.error) ? r.move.error
                                              : readOnlyReason(r);
    who.style.display = why ? 'block' : 'none';
    who.textContent = why;
    return;
  }
  row.style.display = 'flex';
  el('meInput').value = r.value;
  who.style.display = 'block';
  who.textContent = d ? `drives ${d.label}` : `moves ${mv.label}`;
  // Only offer the A/B choice when BOTH sides could move; with one candidate
  // there is nothing to choose and a disabled radio is just noise.
  if (mv && (mv.movable || []).length > 1) {
    sideRow.style.display = 'flex';
    for (const inp of document.getElementsByName('meSideR'))
      inp.checked = inp.value === (chosenSide || mv.side);
  } else {
    sideRow.style.display = 'none';
  }
}

async function applyEdit() {
  // Editable means EITHER a driver (one param to write) or a movable side.
  // This guard used to demand a driver, so pressing Set on a movable gap
  // returned silently — the number stayed put with no explanation, which is
  // the one thing rule 7 forbids (caught in UI verification).
  const editable = last && (last.driver
                            || (last.move && !last.move.error));
  if (!editable || busy) return;
  const v = parseFloat(el('meInput').value);
  if (!isFinite(v)) { note('Type a number first.'); return; }
  let failed = null, warn = null;
  busy = true;
  try {
    const body = { a: strip(A), value: v };
    if (B) body.b = strip(B);
    if (chosenSide) body.side = chosenSide;
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
  // WAIT FOR THE VIEWPORT. The scene follows the document by itself (R3);
  // this joins that load so the overlay below is rebuilt from the NEW bodies.
  // Without the wait the readout said 30 mm and the
  // status bar showed the new volume while the part on screen still drew the
  // old hole, until the 3 s watcher happened to fire (caught in UI
  // verification). It also clears the now-stale pick overlay, which was
  // contradicting the readout with the pre-edit radius.
  await loadMesh();
  // loadMesh disposes every body, and the A/B overlay was built from the OLD
  // ones — so re-light the same two picks against the new geometry. Without
  // this the panel still listed A and B while the model showed neither, which
  // is the same "my selection vanished" confusion the highlight fix removed.
  paintPicks();
  // Repaint from the REBUILT geometry rather than assuming the write landed
  // where it was asked to (house rule 3). The backend verified it too; this is
  // what the user actually sees.
  await run();
  if (warn) note('⚠ ' + warn);         // after run(), which clears the note
  setTimeout(() => { mine = false; }, 0);
}

/* Why a measurement cannot be typed into, per kind. Never left blank. */
const READ_ONLY = {
  angle: 'read-only — an angle follows the faces that form it',
  centres: 'read-only — set each hole’s position in its sketch',
  clearance: 'read-only — set each feature’s position in its sketch',
  length: 'read-only — an edge length follows the profile behind it',
  area: 'read-only — a face area follows the profile behind it',
  distance: 'read-only — these two picks are not a parallel pair',
  diameter: 'read-only — no sketch circle drives this bore '
            + '(a primitive, or an imported body)',
};

function readOnlyReason(r) {
  if (!r || !r.kind) return '';
  return READ_ONLY[r.kind] || 'read-only — no single parameter drives this';
}

const KIND_NAMES = {
  diameter: 'diameter', length: 'edge length', area: 'face area',
  thickness: 'material thickness', gap: 'open gap', step: 'step / depth',
  distance: 'minimum distance', centres: 'centre to centre',
  clearance: 'surface to surface', angle: 'angle',
};
