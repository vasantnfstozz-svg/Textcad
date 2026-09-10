# Shell — tool spec (P4, LAUNCH-PLAN.md §8 step 1)

> **Status: built 2026-09-10 (fb0b8c8, ui v184) — the fifth tool on the
> framework (`tool.js`); code review pending (REVIEW-BRIEF.md).** Fusion's Shell: pick the faces to remove, give a
> wall thickness, the body becomes walls of that thickness around a cavity.
> The op EATS its body like Hole (the result is the hollowed body — no Join /
> Cut row) and its input is a SET of faces on one body, toggled by clicking —
> the selection rule Fillet's faces already follow, decided by the SERVER.
>
> Decisions made here without the user (say so if any is wrong): Direction is
> **Inside** (the walls grow inward, the outside stays where it was) or
> **Outside** (the walls are added around the body, the old surface becomes the
> cavity) — Fusion's **Both**, with its second thickness, is not offered (§10);
> the cavity's corners are SHARP, as Fusion cuts them (build123d
> `Kind.INTERSECTION`; a fillet afterwards rounds them); only FLAT faces can be
> openings — the kernel refuses a cylinder's wall (`probes/shell_probe.py` §8);
> no tangent-chain box for faces; **no ghost**: the cavity is inside an opaque
> body and a hollow cannot be drawn by growing an outline — the thickness box
> follows the drag live and the real hollow, drawn by the kernel, appears on
> release (as Fillet). Autodesk's Shell reference (Faces/Body · Tangent Chain ·
> Inside Thickness · Direction · Outside Thickness) is the vocabulary.

## What you click, what you see

Click the face of a body that should be open — the top of a box that becomes
a tray — and press **Shell**: the face's outline glows gold, an arrow points
from its centre INTO the material, the Thickness box reads **0** — nothing has
been hollowed. Drag the arrow in and the box follows; release, and the body is
a tray with walls of that thickness after one verified rebuild. Type an exact
thickness or choose **Outside**, press **OK**. One `shell1` row appears in the
tree under the body; double-click it and the gold faces, the arrow and the
boxes come back at the stored values. While the panel is open, click another
flat face of the body and it opens too; click a gold face again and it closes.
With every face closed the body is a hollow closed shell, and the panel says
so.

## Inputs (rules 1, 2)

* **ONE body and 0…n of its FLAT faces.** Select-then-command: the face picked
  when Shell is pressed is the first opening; a body's row selected in the tree
  opens the tool on that body with no opening (a closed hollow) — the tree is a
  selection surface (`tool.js` `bodyRow`). With nothing picked the tool waits
  for a click on a face (command-then-select). A sketch, an edge and a curved
  face are refused with the framework's sentences.
* **Every click is a toggle the server decides** (`face_toggle`, the same rule
  as Fillet's face clicks): a face not yet open joins the set, an open face
  comes out. The plan hands back the set in STORED form and the browser sends
  that form with the next click, so two clicks in flight can never lose one
  (the plan chain `tool.js replan`).
* **The faces are stored as a list**, each a NAME (`"top"`, `"+x"` — the AI /
  legacy path) or a pick's `{center, normal}` resolved by geometry at every
  rebuild (`blocks.resolve_face`, the rule sketch_on_face and Hole use), so the
  opening rides an upstream dimension change. The legacy grammar
  `open_face: "top"|"bottom"|"none"` is still accepted by the op and read as
  one named face (or none); a stored `faces` list beats it.
* **The op eats its body.** `shell` is a modifier: input the body, output the
  hollowed body. No combiner, no `_cut` chip.

## The handle and the panel (rules 3, 4, 5)

* **Arrow** at the first opening's centre, pointing INTO the material for
  Inside and OUT of it for Outside (the plan's `axis` = ∓ the face's outward
  normal — the browser negates nothing); dragging it sets the thickness,
  negative clamps to 0. With no opening the arrow sits on the body's largest
  flat face. **Gold outlines** on every open face are the plan's `edges`
  (polylines, drawn by `beginEdgeGlow` — the fillet's glow, nothing new).
* **Panel** `shellDialog`, ids `sh…`: Faces (locked; the plan's words: "2 faces
  open of b" / "no face open — a closed hollow body") · Thickness (mm), starts
  at **0** · Direction: Inside / Outside · Cancel / OK. The Operation row is
  hidden: the op has no combiner.
* **Edit**: tree ✎ or double-click reopens on the stored faces and thickness;
  Cancel restores verbatim — inherited. Clicks toggle faces during an edit
  exactly as while creating (the request is the answer, the stored set the
  fallback — Hole's lesson).
* **Direction changed** → the plan is asked again (the arrow flips) and the
  feature rebuilds.

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | What is said |
|---|---|
| Thickness 0 on OK | "Nothing hollowed — the thickness was 0. Open Shell again, then drag the arrow or type a wall thickness before OK." |
| Thickness ≤ 0 / unknown direction / unknown legacy `open_face` | `shell: thickness must be positive (got 0) — drag the arrow or type a wall thickness` · `shell: direction must be "inside" or "outside" (got 'both')` · `shell: open_face must be "top", "bottom" or "none" (got 'left') — or give faces` |
| A curved face as an opening (AI path; the picker never offers one) | `shell: an opening must be a FLAT face — that face is CYLINDER (curved); pick a flat face` |
| A stored face the body no longer has a flat face for | the name's own sentence (`this solid has no flat face pointing 'top'`) |
| The walls meet in the middle: the offset "succeeds" and returns the body UNCHANGED (probed: t = 25 on a 50 × 50 × 30 box, top open, volume 75000 → 75000) | `shell: nothing was hollowed — walls of 25 mm meet in the middle of this body; use a thinner wall` |
| The walls swallow the body: an OPEN SHELL the kernel calls a success (probed: t = 40, volume 9000, not watertight) | `shell: walls of 40 mm leave a broken solid (an open shell, not watertight) — use a thinner wall` |
| The kernel refuses (a closed hollow at t ≥ half the body raises `RuntimeError: offset Error`; t = 24.9 raises a bare `ValueError: Null TopoDS_Shape object` — kernel wording in a Python class, so EVERYTHING is translated) | `shell: walls of 25 mm do not fit this body — the kernel could not offset its faces; use a thinner wall or open another face` |
| The result falls into pieces | the framework's pieces warning; the remedy: "the walls are too thin somewhere — use a thicker wall or open another face." |
| Curved face picked before pressing Shell | `Shell needs a FLAT face — the selected surface is CYLINDER (curved) …` (inherited) |

## Acceptance (LAUNCH-PLAN P4)

* `static/js/shell.js` in **≤ 120 lines**, **no geometry maths**: the glow, the
  arrow's origin and axis, the stored faces and the words all come from the
  plan.
* Backend: `sketch.shell` (the op, registered as the MODIFIER `shell`; the
  legacy `blocks.shell_out` body goes — `blocks.EXPORTS["shell"]` hands the
  script path the SAME op, one grammar), `toolplan.plan_shell`,
  `ToolPlanReq.faces` + `.direction`. `probes/shell_probe.py` records the
  kernel facts: `offset(openings=[…])` takes a list; Inside volumes match the
  formulas exactly; Outside with `Kind.INTERSECTION` too (ARC rounds the outer
  corners); the unchanged-body lie at t = half the width; the open-shell lie
  at t past it; the two exception classes; the cylinder wall refused; every
  corpus body takes a top opening at t = 2.
* **Tests**: `tests/test_shell_tool.py` (op volumes against formulas for one,
  two and no openings, Inside and Outside; the legacy grammar; every refusal
  as a sentence; the catalogue; riding an upstream change; plan: the opening
  click → faces / origin / axis / edges / words, toggle off → closed words,
  a second face, Outside flips the axis, edit reads the stored set, a `faces`
  list beats the opening click, the plan agrees with the op) and
  `tests/test_shell_gauntlet.py` (every corpus body, every flat face as the one
  opening, Inside and Outside, a closed hollow, top + each other face — a
  healthy solid or a sentence, never a raw kernel error; every face of the
  box must build).
* **3 browser journeys**: click the top + press Shell + type + OK (volume and
  one row, no chip); drag the arrow, click a side face (2 open), click it again
  (1 open), Cancel removes everything; edit → Outside → volume, Cancel restores.
