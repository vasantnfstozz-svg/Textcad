// fillet.js — Fusion-style Fillet AND Chamfer on picked edges, on the tool
// framework (tool.js) — LAUNCH-PLAN.md P4, specs/fillet-chamfer.md. One
// declaration serves both: they differ in a name, an op and the word for the
// value. This file says only what makes an edge tool different: its panel, its
// op, boxes <-> params, and its handles — the gold edges and the arrow that
// drags the value into the material. Selection (edges, toggled by clicking —
// the SERVER decides add-or-remove, it knows the tangent chains), the modal
// lock, the lazy verified preview, edit-in-isolation, Cancel/OK, Esc and the
// failure sentences are inherited.
//
// EVERY geometric fact is the plan's (R1): which edges a click means, the
// chain it grows into, the stored form the op receives (`edges_param`), where
// the handle sits and which way it drags (`ball`). This file draws what it is
// told. There is no ghost: a rounded corner is drawn only by the kernel — the
// value box follows the drag live and the real solid appears on release.

import { tool, g, num, say, setBox } from './tool.js';
import { beginExtrudeArrow, endExtrudeArrow, setExtrudeArrowAmount,
         beginEdgeGlow, endEdgeGlow } from './viewport.js';

function edgeTool(o) {                 // o = {name, icon, op, ids, param, unit, verb}
  const P = o.ids;
  const box = P + 'Value';
  const chainOn = () => g(P + 'Chain').checked;
  const hasEdges = e => Array.isArray(e) ? e.length > 0 : !!e;   // a legacy group is a string

  const ctl = tool({
    name: o.name, icon: o.icon, tool: o.op,
    panel: P + 'Dialog', ids: P,
    ops: { edges: o.op },
    fields: { typed: ['Value'] },
    /* the op gets the plan's stored edges — never an index, never JS geometry */
    /* the op gets the plan's stored edges — never an index, never JS geometry.
       Before the plan lands (OK pressed straight after an edit opens) the
       feature's OWN edges stand in, so a rebuild is never asked for none. */
    params: st => ({ [o.param]: Math.max(0, num(box)),
                     edges: (st && st.plan && st.plan.edges_param)
                       || (st && st.original && st.original.edges) || [] }),
    /* THE CHAIN DEFAULT IS THE SERVER'S (R1). The first plan of a session asks
       without one, so the answer can depend on the geometry — a chain-off
       fillet reopened, or an AI group with tangent neighbours, must not be
       grown; the checkbox then shows what came back and speaks from there on. */
    planExtra: st => (st && st.plan ? { chain: chainOn() } : {}),
    show(st, p) {
      g(box).value = p[o.param] || 0;
      // a NEW session starts at the honest default; the plan's answer follows
      if (!st || !st.editing) g(P + 'Chain').checked = true;
    },
    snapshot(f) {
      const p = f.params || {};
      return { [o.param]: Number(p[o.param]) || 0, edges: p.edges == null ? 'all' : p.edges };
    },
    isEmpty: pr => !(pr[o.param] > 0) || !hasEdges(pr.edges),
    nothing: `Nothing ${o.verb} — the ${o.unit.toLowerCase()} was 0. Open ${o.name} again, ` +
             `click the edges, then drag the arrow or type a value before OK.`,
    describe: p => `${o.unit.toLowerCase()} ${p[o.param]} mm`,
    gizmos: {
      begin(st, plan) {
        if (plan.chain != null) g(P + 'Chain').checked = !!plan.chain;
        beginEdgeGlow(plan.edges);
        if (!plan.ball) return;                    // nothing picked yet: the hint is up
        beginExtrudeArrow(plan.ball.origin, plan.ball.dir, num(box),
          v => setBox(box, v),                     // dragging: the box follows
          async v => { setBox(box, v); await ctl.apply(); },   // release: ONE verified rebuild
          v => Math.max(0, v));                    // a radius has no sign
        if (!st.featureId && num(box) > 0) ctl.apply();   // a value typed before the plan arrived
      },
      end() { endEdgeGlow(); endExtrudeArrow(); },
    },
    afterApply() { setExtrudeArrowAmount(num(box)); },
    /* No `settle`: there is no safe way to ASK the kernel what would have fit.
       Searching means filleting at radii the user never typed, and one of those
       segfaulted OCCT on a real design (see blocks._finish). The framework puts
       back the last value that built and says so — the op has already said why. */
  });

  g(P + 'Chain').onchange = () => ctl.replan();   // the box now speaks: planExtra sends it
  return ctl;
}

let fl = null, ch = null;
export function initFillet() {
  fl = edgeTool({ name: 'Fillet', icon: '◠', op: 'fillet', ids: 'fl',
                  param: 'radius', unit: 'Radius', verb: 'rounded' });
  ch = edgeTool({ name: 'Chamfer', icon: '◣', op: 'chamfer', ids: 'ch',
                  param: 'length', unit: 'Distance', verb: 'bevelled' });
  fl.init(); ch.init();
}
export const openFillet = () => fl.open();
export const openChamfer = () => ch.open();
