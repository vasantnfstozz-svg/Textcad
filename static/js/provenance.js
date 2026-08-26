// provenance.js — "which feature made this face?"
//
// Fusion's Find in Timeline, and the missing half of TextCAD's navigation:
// selecting a feature already highlighted its geometry, but clicking geometry
// told you nothing about the tree. On an AI-authored design — 79 features the
// user did not write — that is the difference between a tree you can read and
// one you can only scroll.
//
// Pick a face -> the backend walks the per-feature solids and answers with the
// feature that CREATED that face, the sketch its profile came from, and the
// extrude/cut that applied it. We reveal that row in the tree and spell the
// chain out under the face info.

import { bus } from './bus.js';
import { S } from './state.js';
import { revealFeature } from './tree.js';
import { showFeatureOverlay } from './viewport.js';

let seq = 0;                 // only the newest pick may write to the panel

bus.on('face-picked', async info => {
  const mine = ++seq;
  if (info.clear || (info.face == null && !info.center)) {
    clear();                 // an edge/profile pick, or nothing pickable
    return;
  }
  let r;
  try {
    // NOT postJSON: this is a read-only lookup on every click. The busy
    // overlay would strobe over the viewport and postJSON would try to
    // broadcast a document that this endpoint deliberately does not return.
    const res = await fetch('/api/face-feature', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(info),
    });
    if (!res.ok) {
      // FAILURES SPEAK (Fusion parity rule 7). This exact case bit the user:
      // studio.py serves index.html and the JS from DISK on every request, but
      // Python code is only loaded at startup. A server started before this
      // feature existed therefore serves the NEW page against the OLD backend,
      // /api/face-feature 404s, and clicking a surface did nothing at all with
      // no explanation whatsoever.
      render(mine, { feature: null, reason: res.status === 404
        ? 'this needs a server restart — the page is newer than the running '
          + 'server (stop studio.py and start it again)'
        : `the lookup failed (HTTP ${res.status})` });
      return;
    }
    r = await res.json();
  } catch (e) {
    render(mine, { feature: null,
                   reason: 'could not reach the server for this lookup' });
    return;
  }
  render(mine, r);
});

/* a fresh document invalidates whatever the panel was saying */
bus.on('doc-updated', () => { seq++; });

function clear() {
  document.querySelectorAll('#pickInfo .provchain').forEach(el => el.remove());
  revealFeature(null);
}

function render(mine, r) {
  if (mine !== seq) return;    // the user has clicked something else since
  const host = document.getElementById('pickInfo');
  if (!host) return;
  host.querySelectorAll('.provchain').forEach(el => el.remove());
  const box = document.createElement('div');
  box.className = 'provchain';

  if (!r || !r.feature) {
    box.textContent = r && r.reason
      ? `Feature history: ${r.reason}`
      : 'Feature history: could not trace this face.';
    host.appendChild(box);
    return;
  }

  const chain = r.chain && r.chain.length
    ? r.chain
    : [{ id: r.feature, op: r.op, role: 'origin' }];
  const ROLE = { sketch: 'sketch', extrude: 'extrude', origin: 'created by',
                 applied: 'applied by' };
  box.innerHTML = '<b>Created by this feature</b>';
  for (const step of chain) {
    const row = document.createElement('div');
    row.className = 'provrow';
    const role = document.createElement('span');
    role.className = 'provrole';
    role.textContent = ROLE[step.role] || step.role;
    const link = document.createElement('a');
    link.className = 'provlink';
    link.textContent = step.id;
    link.title = `${step.op} — click to show it in the tree`;
    link.onclick = () => {
      revealFeature(step.id, chain.map(c => c.id));
      showFeatureOverlay(step.id);       // and light it up in the viewport
    };
    const op = document.createElement('span');
    op.style.cssText = 'color:var(--dim);font-size:10.5px';
    op.textContent = step.op;
    row.append(role, link, op);
    box.appendChild(row);
  }
  if (r.confidence && r.confidence !== 'high') {
    const note = document.createElement('div');
    note.style.cssText = 'margin-top:5px;color:var(--dim);font-size:10.5px';
    note.textContent = r.confidence === 'medium'
      ? 'Curved/lofted surface — traced by shape, so this is a best match.'
      : (r.reason || 'Low confidence.');
    box.appendChild(note);
  }
  host.appendChild(box);

  // the tree jumps to the feature that made it, with the rest of the chain
  // marked more faintly (sketch + tool + the boolean that applied it)
  revealFeature(r.feature, chain.map(c => c.id));
  S.lastFaceFeature = r;
}
