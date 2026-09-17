// loft.js — Fusion-style Loft ON the tool framework (tool.js), the second
// Tier 2 tool (LAUNCH-PLAN.md §4, specs/loft.md) and the framework's first
// MULTI-INPUT tool. This file declares only what makes Loft different: its
// panel, the SECTIONS — the sketch profiles the loft blends, in order — how a
// tree row or a viewport pick adds and removes one while the panel is open,
// the Ruled box, and its one gizmo: the ghost skinning the sections' outlines
// (Fusion's Loft has no drag handle — it is a selection tool). Selection, the
// modal lock, the lazy verified preview, Join/Cut, edit-in-isolation,
// Cancel/OK and the failure sentences are inherited.
//
// EVERYTHING GEOMETRIC IS THE PLAN'S (R1): the server judges the sections
// exactly as the op will (sketch.loft_geometry — one verdict), puts them in
// the order they lie along the loft when the picks came out of order (and
// says so), lists what could still be added, and hands back one outline ring
// per section for the ghost. `loft` stays a COMBINER: the feature's inputs
// ARE the sections, so nothing about the tree changes.

import { S } from './state.js';
import { tool, g, say } from './tool.js';
import { beginLoftGhost, hideLoftGhost, endLoftGhost } from './viewport.js';

const feats = () => (S.lastDoc && S.lastDoc.features) || [];

/* the sections this session holds, in pick order; the plan's `order` is what
   the feature stores */
const sections = st => (st && st.sections) || [];

/* ---------------- the panel <-> params ---------------- */
function params(st) {
  return { ruled: g('lfRuled').checked };
}
/* the sections are the FEATURE'S INPUTS, never a parameter: an edit reads
   them off the feature (the framework's restore posts params only — a first
   draft put them in the snapshot and Cancel was refused as "no parameter
   'sections'"); a new session starts from its first profile */
function show(st, p) {
  g('lfRuled').checked = !!p.ruled;
  if (st && !st.sections) {
    const f = st.editing && feats().find(x => x.id === st.featureId);
    st.sections = f ? [...(f.inputs || [])] : [st.input.id];
  }
  renderList(st);
}
function snapshot(f) { return { ruled: !!(f.params || {}).ruled }; }
/* the sections as a list with ✕, locked in an edit (the framework never
   rewires a combiner's inputs mid-edit) */
function renderList(st) {
  const box = g('lfList');
  box.innerHTML = '';
  const locked = !!(st && st.editing);
  for (const id of sections(st)) {
    const row = document.createElement('div');
    row.className = 'lfrow';
    const name = document.createElement('span');
    name.textContent = id;
    row.appendChild(name);
    if (!locked) {
      const x = document.createElement('button');
      x.type = 'button'; x.className = 'exbtn'; x.textContent = '✕';
      x.title = 'take this profile out of the loft';
      x.onclick = () => remove(st, id);
      row.appendChild(x);
    }
    box.appendChild(row);
  }
  g('lfAddRow').style.display = locked ? 'none' : '';
  g('lfHint').textContent = sections(st).length < 2
    ? 'Pick a second profile: click a sketch in the viewport, its row in the tree, or the list.'
    : `${sections(st).length} profiles — they blend in the order they lie along the loft.`;
}
function setCandidates(plan) {
  const sel = g('lfAdd');
  sel.innerHTML = '';
  sel.add(new Option('Add profile…', ''));
  for (const c of plan.candidates || []) sel.add(new Option(c.label, c.id));
  sel.value = '';
}

/* ---------------- adding and removing sections ---------------- */
function add(st, id, replan) {
  if (!st || st.editing) return;
  if (id === st.featureId) { say('⚠ that row is this loft\'s own result — click another sketch.'); return; }
  if (sections(st).includes(id)) { remove(st, id, replan); return; }   // a second click takes it out
  st.sections = [...sections(st), id];
  renderList(st);
  replan();
}
function remove(st, id, replan) {
  if (!st || st.editing) return;
  if (sections(st).length <= 1) { say('⚠ Loft keeps its first profile — Cancel closes the tool.'); return; }
  st.sections = sections(st).filter(s => s !== id);
  if (id === st.input.id) st.input = { kind: 'profile', id: st.sections[0] };
  renderList(st);
  (replan || lf.replan)();
}
/* a tree row clicked while the panel is open: the server says whether it is
   a profile a loft can take (the plan refuses anything else with a sentence) */
function onRow(st, fid, replan) { add(st, fid, replan); }
/* a sketch clicked in the viewport while the panel is open */
function onRepick(st, data, replan) {
  if (data && data.profile) add(st, data.profile, replan);
}

/* ---------------- the ghost ---------------- */
const gizmos = {
  begin(st, plan) {
    setCandidates(plan);
    if (plan.reordered) {
      st.sections = [...plan.order];            // the stored order is the plan's
      renderList(st);
      if (plan.note && st.saidNote !== plan.note) { st.saidNote = plan.note; say(`Loft: ${plan.note}.`); }
    } else {
      renderList(st);
    }
    beginLoftGhost((plan.sections || []).map(s => s.ring));
    if (st.featureId) hideLoftGhost();          // the real solid is on screen
  },
  end() { endLoftGhost(); },
};
function afterApply(st) { if (st && st.featureId) hideLoftGhost(); }
/* the Add list: a choice adds that profile */
function refresh(st) {
  const id = g('lfAdd').value;
  if (!id) return;
  g('lfAdd').value = '';
  add(st, id, lf.replan);
}

const lf = tool({
  name: 'Loft', icon: '⏢', tool: 'loft',
  panel: 'loftDialog', ids: 'lf',
  ops: { profile: 'loft' },
  fields: { change: ['Ruled', 'Add'] },
  show, params, snapshot, gizmos, afterApply, refresh, onRow, onRepick,
  repick: 'click another sketch profile to add it to the loft · Esc cancels',
  planExtra: st => ({ sketch_ids: sections(st) }),
  inputs: st => [...sections(st)],
  isEmpty: (pr, st) => sections(st).length < 2,
  nothing: 'Nothing lofted — a loft needs at least two profiles. Open Loft on one ' +
           'sketch, then click a second one before OK.',
  split: () => 'the lofted cut leaves material on both sides — move a profile, or ' +
               'loft fewer of them.',
  describe: (p, st) => `${sections(st).length} profiles${p.ruled ? ', ruled' : ''}`,
});

export const openLoft = profileId => lf.open(profileId);
export function initLoft() { lf.init(); }
