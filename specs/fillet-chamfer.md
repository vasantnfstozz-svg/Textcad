# Fillet / Chamfer on picked edges — tool spec (P4, LAUNCH-PLAN.md §8 step 1)

> **Status: DRAFT for the user's approval, 2026-09-04.** The third tool on the
> framework (`tool.js`) and the first that needs a NEW input kind: edges. The
> edge picker it brings is the piece Hole (points on edges), face-profile
> Revolve (P3b: an edge as the axis) and Shell reuse.

## What you click, what you see

Press **Fillet** (or **Chamfer**) and click the edges of a body in the
viewport: each edge you hover lights up, each edge you click turns **gold** and
stays selected; clicking a gold edge releases it. A **ball** sits at the middle
of the first picked edge, the radius box reads **0** — nothing has changed yet.
Drag the ball into the body and the box follows; release, and every selected
edge is rounded (bevelled) by that value after one verified rebuild. Type an
exact figure, press **OK**. One `fillet1` (`chamfer1`) row appears in the tree
under the body; double-click it and the same edges light up again with the ball
at the stored value.

## Inputs (rules 1, 2)

* **One or more EDGES of one body**, picked in the viewport. Select-then-command
  works: edges already gold when you press the tool are its input; with nothing
  picked the tool waits for clicks (command-then-select). Faces and sketches are
  refused with a sentence. A selection can only grow on the body the first edge
  belongs to; clicking another body's edge says so.
* **Tangent chain** (Fusion default ON): clicking one edge of a rounded rim
  selects the whole smoothly connected loop. The server works the chain out and
  hands the edges back; a checkbox in the panel turns it off.
* **Edges are stored by GEOMETRY, never by index** (same rule as
  `resolve_face`): each edge as **the two faces it separates**, plus its
  midpoint, direction and type. At build time the op finds the edge those two
  faces still share, so a fillet survives a change to the box's height
  upstream — and when they no longer meet (or both resolve to the same face,
  because a nearest-match never fails) it says the edge is gone instead of
  quietly rounding a different one. Param stays backward compatible: the AI's
  `edges: "all"|"top"|…` groups keep working.
* **The tangent chain is a picking aid, not a stored property.** It is ON for
  fresh picking (Fusion) and OFF for a selection that came from the tree: the
  stored edges are already the answer, and re-expanding them could only add
  edges the user never picked. The panel's checkbox shows the server's answer;
  ticking it grows the selection visibly, before OK.

## The handle and the panel (rules 3, 4, 5)

* **Ball** at the midpoint of the first edge, dragging along the bisector of the
  two faces that meet there, INTO the material; ball position, drag axis and
  the px-per-mm reference come from `POST /api/tool/plan {tool:"fillet", body,
  edge_centers}` — no vector maths in JS (R1). The value is the distance
  dragged; negative is clamped to 0 (a fillet has no sign).
* **Preview**: the value box follows the drag live, the selected edges stay
  gold, and the real solid appears on release (one verified rebuild) — no fake
  ghost: a rounded corner is drawn only by the kernel. Typed values apply after
  the usual pause.
* **Panel** `filletDialog`, ids `fl…` (Chamfer reuses the same declaration with
  its own name, op and label): Edges (count + body) · Radius (mm) box — starts
  at **0** · Tangent chain ☑ · Cancel / OK. Chamfer: **Distance** (mm), equal
  on both faces; two distances and distance-plus-angle are P4b.
* **Edit**: tree ✎ or double-click reopens the tool in isolation with the edges
  gold and the ball at the stored value; Cancel restores verbatim — inherited.
* **Framework extensions this tool forces** (§8 step 5, Extrude and Revolve get
  them too): a third selection kind `edges` (multi-pick, toggle, one body);
  `viewport.beginEdgePick` with hover highlight; **Esc cancels any open tool
  panel** (backlog item, "inherit it once when the second tool lands").

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | What is said |
|---|---|
| Radius too big for the neighbouring faces (kernel refuses, or returns a broken solid — probed: a round bigger than the corner round next to it comes back not watertight) | the op says what actually went wrong — "fillet: radius 8 mm does not fit on 2 edges — the kernel could not build it there" — and the framework puts back the last value that built. **The tool does NOT search for the largest value that would fit** (the approved spec said it would; the P4 review killed it): searching means filleting at radii the user never typed, and on esp32-remote a refused radius 4 made it try 2.0 and OCCT **segfaulted**, taking the server and every unsaved tab with it (reproduced 2026-09-04, exit 139). Nothing speculative is ever handed to the kernel. |
| Radius 0 on OK | "Nothing rounded — the radius was 0. Open Fillet again, then drag the ball or type a radius before OK." |
| An edge is gone after an upstream change | "The edge at (10, 0, 20) is no longer on the body (nearest edge is 7 mm away) — re-pick the edges of `fillet1`." (the feature fails, the body stays whole) |
| Click on a face / sketch / another body's edge | "Fillet works on the edges of ONE body — click an edge of `box1`, not a face." |
| Result invalid or in pieces | never accepted: the framework backstop reverts to the last radius that built and says so |
| AI path passes both `edges` and `edge_centers`, or an empty list | `ValueError` sentence from `blocks.fillet_edges`; the repair loop reads it |

## Acceptance (LAUNCH-PLAN P4)

* `static/js/fillet.js` in **100–200 lines** declaring BOTH tools (Fillet,
  Chamfer) from one function; **no geometry maths**; the ball and highlight
  live in `viewport.js`, the edge selection kind in `tool.js`.
* Backend: `fillet` / `chamfer` accept `edge_centers` (list of
  `{center, dir, type}`) resolved by nearest midpoint with a tolerance that
  refuses with a sentence; `toolplan.plan_fillet` returns resolved edges,
  tangent chains, the ball frame and `limits.max_radius` per edge (probed:
  `probes/fillet_limits_probe.py` — what the kernel throws, and on which
  radius, for a box, a tube rim and a chain).
* **40+ plan tests** (body × picked edges × chain on/off → plan) and
  `tests/test_fillet_gauntlet.py`: every corpus body in `tests/gauntlet.py`,
  every edge picked one at a time at a small radius — valid solid or a
  sentence, never a raw OCP error; edge resolution stable after the body's
  height changes.
* **3–6 browser journeys**: pick two top edges + drag; tangent chain on a
  rounded rim; edit-and-cancel restores; too-large radius keeps the last good
  one and speaks; Chamfer on four vertical edges; Esc cancels the panel.
* R10: line delta recorded in the commit; the profile picker and the new edge
  picker share one `beginPick`, so the viewport's pick code shrinks as the tool
  lands.

## The user's five-step checklist (R9)

1. Build a 40 × 30 × 20 box. Press **Fillet** with nothing selected: the hint
   asks for edges, hovering an edge lights it, clicking a top edge turns it
   gold and a ball appears at its middle; box reads 0, the body is unchanged.
2. Drag the ball into the box to about 3: the box follows; release and the
   edge is rounded. Type 5: the round grows to exactly 5.
3. Click the other three top edges (all four gold), then click one again to
   release it: three are rounded on release. OK: one `fillet1` in the tree.
   Double-click it: the three edges relight, the ball reads 5; Cancel changes
   nothing.
4. Press **Chamfer**, click the four vertical edges, type 2, OK. Now edit the
   box's extrude to 30 high: the chamfers ride along on the taller box.
5. Open `fillet1` and type 50: the chat says 50 does not fit and why, and the
   body keeps the radius that did build (the box goes back to it). Esc closes
   the panel — once, even if you hold the key down.
