# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** The sketch-plane review is CLOSED in two
> rounds. Round one read `1c77d9f..bc136be` (Sketch plane offset `ee102b1` +
> Move Plane `bc136be`) and fixed 2 in `cdc833a`; round two read `cdc833a`
> — the fix itself, because it changed what every Finish Sketch writes —
> and fixed 2 more in `a1e3483`. The next `code review` takes the first TODO
> row of `REVIEW-QUEUE.md`.

## Round two, in one paragraph

Reviewed on Opus 5 (1M) 2026-09-22, one reviewer, no subagents. Round one's
fix was right about what to write; round two found that it decided WHEN to
write it one step too early, and that the box it trusts does not always give
back the number it was handed. Both findings are the same shape as the P1
round one fixed — a formula silently replaced by the number it happened to
resolve to — reached by two doors round one did not open: a move the server
REFUSED, and a display unit that is not millimetres. Both reproduced in a
real browser before the fix, both red-then-green. 4 new browser tests (2 for
the findings, 2 for round trips nobody had driven) and one probe that lifts the
three functions straight out of `sketcher.js`; fast tier **2610 green**, the
sketch-plane browser file 16 green, ruff and eslint zero; ui v231. No design file touched.

## What round two found (both fixed)

- **P2 — a move the server REFUSED still ate the formula.**
  `setSketchPlaneOffset` gave up `skOffsetRaw` at the TOP of the function,
  before the `/api/face-outline` (or plane-frame) call that can fail. When
  that call does not land the sketch stays exactly where it was and says so
  ("⚠ Could not move the sketch plane"), but the formula had already been
  dropped: the next Finish Sketch wrote `-4` where `"-wall"` had been.
  Measured on the plate + boss with the call aborted: volume identical to
  1e-9, `offset` `"-wall"` -> `-4`, nothing said. The plane is now given up
  only after the frame has arrived.
- **P2 — in inches, OK without touching anything was a move.** The Offset box
  speaks the DISPLAY unit; the offset is millimetres. `setLen` renders -4 mm
  as `-0.1575` in (4 dp) and `mm()` reads that back as **-4.0005 mm**, so the
  guard round one added ("the box opens at that number, so OK without
  touching it is a no-op") was false in any unit but mm: pressing OK moved the
  sketch plane 0.0005 mm, rebuilt everything under it, and wrote `-4.0005`
  over the formula. `ok()` now passes the offset the step OPENED with whenever
  the box still reads the exact string `open()` filled it with.

## Cleared by MEASUREMENT (do not re-report)

- **The `offsetParam` table holds — all nine rows.**
  `probes/sketch_offset_table.py` lifts `offsetParam`, `stableJson` and
  `sameSketch` VERBATIM out of `sketcher.js` and runs every shape an `offset`
  can have through them: a number, a numeric STRING, `-0`, `20.0`, a formula,
  a formula that does NOT resolve, **no `offset` key at all**, `offset: null`,
  and a feature with no `resolved`. Every row writes back what was saved and
  every row calls an untouched Finish no change at all. The two that mattered
  were also driven in a real browser: a sketch with no `offset` key — which is
  all 47 of the user's designs, 310 sketches — writes nothing, not even the 0
  the editor drew at; and a **plane** sketch's formula (`offset: "lift"`)
  survives, volume identical, where round one only ever drove the face half.
- **`modalGuard()` in `stageSketchPlane` refuses nothing legitimate.** Every
  ribbon button is already guarded (`ribbon.js renderRibbon`), and
  `planePickAt` calls `endPlanePick()` BEFORE the callback, so a pick cannot
  land while the step it would replace is open. The only door it closes is the
  one round one found (Measure holding the lock over a pending pick).
- **No design is affected by either finding.** 47 designs, 310 sketches with
  an `offset`: zero formulas, and the only three offsets with more than two
  decimals (8.899999999999999 twice, 10.700000000000001) are generator float
  arithmetic, not an inch round trip.

## Also do not report (known, decided or recorded)

- Everything on round one's list: no tilted planes / construction planes, no
  arrow on tree re-edit, the face-pick panel's own button opens at 0,
  `sketch_on_face`'s docstring, the drag's 0.1 mm rounding, `author.py`
  refusing an absolute-offset plane sketch, and the node harness's stubs — all
  still true, all plan §10 P3 or `specs/sketch-plane.md`.
- **Move Plane replaces a formula only when the NUMBER changed**, so dragging
  away and back to the same value keeps the literal the first drag wrote.
  Round one's deliberate choice, unchanged.
- **The same unit round trip is in `tool.js` for every OTHER tool panel, for
  NUMBERS.** Measured in the same browser: Extrude's edit panel in inches,
  OK pressed untouched, `amount` 12 -> **11.99896** and the solid 7200 ->
  7199.38 mm3. A FORMULA is safe there (`"h"` came back `"h"` — a formula
  cannot seed a number box, so it seeds 0 and an untouched OK writes
  nothing), which is why round one's "the sibling door is sound" still
  stands. Deferred as a plan §10 P2 row: it is `okSession` doing what its own
  comment says on purpose, so it is a framework pass, not this step's.

**Ground rules** (as always): reproduce by measurement or a red test before
fixing; smallest fix; tests with it; commit; restart the user's server if
`sketch.py` / `studio.py` changed; then this file -> `Status: NOTHING
PENDING`, a plan §10 row for anything deferred, memory. Never `--fix`.
