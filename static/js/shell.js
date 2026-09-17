// shell.js — Fusion's Shell on the tool framework (tool.js) — LAUNCH-PLAN.md P4,
// specs/shell.md. ONE op (`shell`) that EATS its body: click the face that
// should be open, press Shell, drag the arrow into the material for the wall
// thickness; click more faces to open them, click an open face to close it.
// This file says only what makes a shell different: its panel, boxes <-> params,
// and its handles — the gold outlines of the open faces and the arrow that
// drags the thickness. Selection, the modal lock, the lazy verified preview,
// edit-in-isolation, Cancel/OK, Esc and the failure sentences are inherited.
//
// EVERY geometric fact is the plan's (R1): which faces are open and in what
// stored form, their outlines, where the arrow sits and which way it points
// (into the material for Inside, out of it for Outside). A click on the body
// while the panel is open is a TOGGLE the server decides (`face_toggle`, the
// rule Fillet's face clicks follow). There is no ghost: the cavity is inside
// an opaque body and cannot be drawn by growing an outline — the box follows
// the drag live and the real hollow, drawn by the kernel, appears on release.

import { tool, g, mm, len, say, setLen } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginEdgeGlow, endEdgeGlow } from './viewport.js';

const direction = () => g('shDirection').value;

/* the boxes -> the op's params. The face set is the plan's stored form; before
   the plan lands (OK pressed straight after an edit opens) the feature keeps
   its OWN set — the key is simply not sent, so a legacy `open_face` row still
   builds. Once the plan speaks, the list is the one form and open_face goes. */
function params(st) {
  const p = { thickness: Math.max(0, mm('shThickness')), direction: direction() };   // a wall is a length
  const src = (st && st.plan) || (st && st.original) || {};
  if (src.faces != null) { p.faces = src.faces; p.open_face = null; }
  return p;
}
/* {} = the honest default: nothing hollowed yet — thickness 0 */
function show(st, p) {
  setLen('shThickness', p.thickness || 0);
  g('shDirection').value = p.direction || 'inside';
}
/* every param the tool can write, normalized — Cancel-in-edit puts it back verbatim */
function snapshot(f) {
  const p = f.params || {};
  return { thickness: Number(p.thickness) || 0, direction: p.direction || 'inside',
           faces: p.faces == null ? null : p.faces,
           open_face: p.open_face == null ? null : p.open_face };
}
const openCount = p => Array.isArray(p.faces) ? p.faces.length
  : (p.open_face && p.open_face !== 'none' ? 1 : 0);
/* honest zero: no plan yet (its arrival applies), no thickness */
const isEmpty = (pr, st) => !st.plan || !(pr.thickness > 0);

const gizmos = {
  begin(st, plan) {
    beginEdgeGlow(plan.edges);                       // the open faces' outlines, gold
    beginExtrudeArrow(plan.origin, plan.axis, mm('shThickness'),
      v => setLen('shThickness', v, 1),              // dragging: the box follows
      async v => { setLen('shThickness', v, 1); await sh.apply(); },   // release: ONE verified rebuild
      v => Math.max(0, v));                          // a thickness has no sign
    if (plan.click_words) say(plan.click_words);     // what the click did (rule 7)
    // a thickness typed before the plan arrived waits for it
    if (!st.featureId && mm('shThickness') > 0) sh.apply();
  },
  end() { endEdgeGlow(); endExtrudeArrow(); },
};

const sh = tool({
  name: 'Shell', icon: '▢', tool: 'shell',
  panel: 'shellDialog', ids: 'sh',
  ops: { face: 'shell' },       // a body and its faces — no sketch profile
  eats: true,                   // the op returns the hollowed body: no Join / Cut row
  bodyRow: true,                // a body's tree row opens the tool with no face open
  repick: 'Click a flat face of the body to open or close it · drag the arrow for the wall · Esc cancels',
  /* every request carries the set the LAST plan settled (an empty list is a
     selection too — only a request without one is the opening click) and the
     panel's direction, so a click can never lose an earlier one and the arrow
     is planned for the side the box says */
  planExtra: st => ({ direction: direction(), ...(st && st.plan ? { faces: st.plan.faces } : {}) }),
  /* a click while the panel is open toggles that face — the server decides */
  onRepick: (st, data, replan) =>
    replan({ face_toggle: { center: data.center, normal: data.normal || null,
                            area: data.area ?? null } }),
  fields: { change: ['Direction'], typed: ['Thickness'] },
  show, params, snapshot, gizmos, isEmpty,
  /* Direction changed: the arrow's side is the plan's, so ask again */
  refresh: st => { if (st && st.plan) sh.replan(); },
  afterApply: () => setExtrudeArrowAmount(mm('shThickness')),
  nothing: 'Nothing hollowed — the thickness was 0. Open Shell again, then drag the arrow ' +
           'or type a wall thickness before OK.',
  split: () => 'the walls are too thin somewhere — use a thicker wall or open another face.',
  describe: p => `${len(p.thickness)} walls ${p.direction || 'inside'}, ` +
                 `${openCount(p)} face${openCount(p) === 1 ? '' : 's'} open`,
});

export const openShell = () => sh.open();
export const initShell = () => sh.init();
