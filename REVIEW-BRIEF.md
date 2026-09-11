# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review commit **`3b230b7`** (base `9992748`), the fix
> for LAUNCH-PLAN section 10's P1 "sketch_trim keeps its own copy of the
> sketch composition rule" - plus a P0 it uncovered in `sketch.py` itself.
> Range: `git diff 9992748..3b230b7`. Files: `sketch.py`, `sketch_trim.py`,
> `tests/test_trim_composition.py`.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range named here; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes.

---

## What this commit did

**Two rules became one, and the one that survived was wrong in a fourth case.**

- **`sketch_trim.py` kept its own composition rule** - a sequential
  add/subtract loop in DRAWING order - while `sketch.py` orders outers before
  what nests inside them and material before a cut that overlaps it. On
  `[boss r5 add, bar 80x6 cut, pocket 40x20 cut]` the builder composes
  **22.3648 mm2** and trim composed **0.0**, so every Trim click on that
  cluster answered "the result would have no area left". Its pointwise
  material test called `(0, +-4)` empty where the builder leaves boss, so a
  click offered to dissolve what is really the profile's own edge.
- **Two guards refused work the builder accepts.** `sketch_trim` l.372/l.424
  rejected any entity list whose FIRST shape is a cut. Deleting one bar from
  `[pocket cut, bar, bar, bar]` builds 144.0 mm2; Trim said "delete the cut
  shapes first".
- **The P0 in `sketch.py`.** The fourth review's "material before a cut that
  overlaps it" pass ran only *while the order STARTED with a cut*. One
  unrelated shape drawn first switched it off:
  `[boss, bar, pocket]` = 22.3648 (correct), `[far circle, boss, bar, pocket]`
  = **157.0796** - the boss built SOLID, the bar's 56.17 mm2 of red paint lost,
  green and silent. The honest answer is 100.9046.

**The shape of the fix:** `sketch.compose(entities, note=False)` and
`sketch.compose_order(entities)` are public; `sketch_trim` asks them (R1).
`_cluster` returns its members in the builder's order, so `_material_at` and
`_compose_faces` inherit it. The two guards are replaced by
`_refuse_if_the_trim_broke_it`, which asks whether the BUILDER can still
compose the result and never blames the click for a sketch that was already
broken. `_compose_order`'s overlap pass runs for every cut, not just a leading
one, so where a shape was drawn cannot change the solid.

## Where the risk is - read these four first

1. **`_compose_order` now adds an ordering edge for EVERY (cut, material)
   overlapping pair**, not only for cuts that lead. This is the widest blast
   radius in the commit: it runs for every sketch in every design that has a
   subtract. Two questions worth attacking - does it change a sketch whose
   old answer was the one the user wanted, and can the extra edges make a
   CYCLE that `_order_from` then breaks by falling back to drawing order?
2. **`_cluster` returns composition order, not sorted order.** Every caller
   that indexed `cl[0]` had to become `min(cl)`; the splice in `trim_apply`
   was the one found. Look for another positional assumption about `cl`.
3. **`_refuse_if_the_trim_broke_it` composes the WHOLE entity list**, twice on
   the refusal path. Cost on a 24-entity sketch, and whether a legitimate trim
   can now be refused because of an unrelated broken entity (it composes the
   BEFORE list too, precisely to avoid that - is that escape hatch tight?).
4. **`note=False`.** `compose` publishes "entity N removes nothing" into
   `sketch._NOTES`, which `Document.warnings` drains. A hover or a click must
   not leave a sentence about entity N of a CLUSTER in the next feature's
   warnings. One test covers it; look for an uncovered path.

## What was measured (do not re-measure unless you doubt the method)

- **50 live designs rebuilt under both the old and the new rule: ZERO volume
  drift**, zero warning changes, none newly broken. Total rebuild time
  133.2s -> 127.3s (the old code re-ran the topological sort in a loop).
  Probe: `probes/library_drift_compose.py old|new`.
- **18,500 grid points across 8 sketches**: `_material_at`, fed the cluster in
  the new order, agrees with the BUILT profile at every point, for every
  cluster seed. Probe: `probes/trim_material_grid.py`.
- All 24 drawing orders of `[far, boss, bar, pocket]` give one area.
- Fast tier **1554 passed**, ruff clean, live `/api/sketch/trim/apply` smoke
  test green on the restarted server. No frontend change, so no cache bump.

## Do not re-report

- `_entity_face` taking `faces()[0]`. It was probed: every entity kind builds
  exactly one face today, and the multi-face shapes that could exist (a
  self-crossing polygon) are refused by `_entity` before they get here. The
  self-crossing-polygon item is already queued on LAUNCH-PLAN section 10.
- The `note` parameter defaulting to True. Every existing caller is the
  builder, which wants the notes.
- Everything on LAUNCH-PLAN.md section 10's open list, and the pre-existing
  red `tests/e2e/test_tree_delete.py` (five, measured at 667ccc0).
