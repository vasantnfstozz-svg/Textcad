# Press Pull — tool spec (P4, LAUNCH-PLAN.md §8 step 1)

> **Status: built 2026-09-11 — the last Tier-1 tool of §4, the row the plan
> called "Push/Pull naming".** The plan's own note was "Extrude in face mode
> already does this; expose the name", and that is all this is: no new op, no
> new panel, no backend change, no kernel call — so no probe. Fusion's name is
> **Press Pull** (Modify tab, shortcut Q), and the button carries that name.
>
> Decisions made here without the user (say so if any is wrong):
> * **Press Pull is a ROUTER, the way Fusion's is.** Fusion's Press Pull does
>   not have a dialog of its own: it reads what is selected and starts the
>   command that fits — a sketch profile or a planar face starts **Extrude**, an
>   edge starts **Fillet**, a curved face starts Offset Face. TextCAD does the
>   first two and says plainly that it cannot do the third yet. The plan's row
>   named only "flat face of a body"; the profile and edge routes cost eleven
>   lines and are what the Fusion user's finger expects.
> * **The panel and the tree row are Extrude's (or Fillet's).** Fusion's
>   timeline shows an Extrude after a Press Pull, never a "Press Pull" feature.
>   So the header reads Extrude, the row reads Extrude face, and the tool
>   re-opens from the tree exactly as before. `press_pull` is a ribbon key
>   only: it is in `icons.js` for the button's icon and name, and it is NOT an
>   op — the document, the author and the MCP never see the word.
> * **Nothing selected: Extrude asks.** Press Pull with an empty selection
>   behaves as the Extrude button does — "click a sketch profile or a flat
>   face in the viewport". An edge clicked at that prompt is not taken (the
>   prompt is Extrude's, and it takes faces and profiles); click the edge
>   first, then press the button.

## What you click, what you see

**A flat face.** Click a flat face of a body, press **Press Pull** (Modify
tab, first button). The Extrude panel opens in face mode — Profile reads
"(selected face)", Operation is Join, the distance is 0 and nothing has been
built. The arrow stands on the face; drag it out and the face is pulled out
with a white ghost, drag it in and the body is cut. Release, and one verified
rebuild replaces the ghost. OK keeps the Extrude-face row; Cancel removes it.
This is exactly what pressing Extrude with that face selected does.

**A sketch.** Select a sketch — its row in the tree or its outline in the
viewport — and press Press Pull: Extrude opens on that profile.

**An edge.** Click an edge and press Press Pull: the chat says "Press Pull on
an edge is Fillet — drag the ball for the radius" and the Fillet panel opens
with that edge gold.

**A curved face.** The chat says "Press Pull on a curved face would offset it
(Fusion's Offset Face), which TextCAD does not have yet. Click a FLAT face to
pull it, a sketch to extrude it, or an edge to fillet it." No panel opens,
nothing is built.

## Where it lives

- `static/js/extrude.js` `openPressPull()` — reads the selection's kind once
  (`tool.js selectionKind`, the same answer `open()` reads a moment later) and
  routes; three sentences, no geometry.
- `static/js/ribbon.js` — `press_pull` in `TOOLS` and first in Modify →
  Features, as in Fusion.
- `static/js/icons.js` — `⇕` and "Press Pull", marked as not an op.

## Tests

`tests/e2e/test_press_pull.py` — four journeys with real clicks: a face pick
opens Extrude in face mode and a typed 5 mm pull grows the plate by exactly
60 × 40 × 5 mm³ with one body left; a selected sketch row opens Extrude on that
profile; an edge pick opens Fillet; a curved face gets the sentence and no
panel. The fast tier is untouched (no backend change).
