# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — the FIX COMMIT `cdc833a` of the sketch-plane review, on master.
> Round one read `1c77d9f..bc136be` (Sketch plane offset `ee102b1` + Move
> Plane `bc136be`), found **2**, fixed both, and one of them changes what
> **Finish Sketch writes for every sketch in the app** — the door this
> project has been wrong at more often than anywhere else. So the brief is
> deliberately set PENDING on the fix, exactly as section 7 of the queue was.
> Strike this when round two is done.

## Round one, in one paragraph

Reviewed on Opus 5 (1M) 2026-09-22, one reviewer, no subagents. The feature
itself held up: the two risks the build's own brief ranked first and second
were **cleared by measurement, not by reading** (below). The two findings were
in the seams either side of it — what an EDIT writes back, and who is allowed
to open the step. 3 new browser tests for the findings, 4 more for the flows
the build never drove, 1 new node assertion; fast tier and both linters green;
no design file touched.

## The fix commit — where the risk is, ranked

1. **`sketcher.js` now writes a DIFFERENT `offset` than before, on every
   Finish.** `skOffsetRaw` holds the offset *as written* (a formula string
   when it names a parameter), `offNum` the number the editor draws at, and
   `offsetParam()` chooses between them. Check the table: a numeric offset, a
   formula, a formula that does not resolve (`resolved.offset` is **null**,
   which `??` does NOT stop at), a missing key, `offset: null`, a feature
   object with no `resolved` at all. The claim to attack is that a legacy face
   sketch opened and closed still writes **nothing**.
2. **`sameSketch` compares the offset as WRITTEN now** (`stableJson`), not as
   a number. `-25` and `-25.0` must still be one sketch; `"-wall"` and `-4`
   must not. If this is too strict anywhere, a no-op Finish starts rebuilding
   the tree again — the thing the function exists to prevent.
3. **Move Plane replaces a formula only when the NUMBER changed.** The test is
   the number, not the gesture, so a user who drags away and back to the same
   value keeps the literal the first drag wrote. Deliberate; argue it if you
   disagree.
4. **`stageSketchPlane` now calls `modalGuard()`.** It runs on a viewport
   CLICK, so the ribbon's guard never saw it. Verify nothing legitimate is now
   refused: `startSketch` clears the lock (`cancelTool` + `cancelMeasure`)
   before the pick, so the guard should be dormant in the normal flow.
5. The node harness gained a `dialogs.js` stub (`modalGuard` reading
   `S.modalTool`). A stub that answers differently from the real one is a test
   that proves nothing.

## What round one found (both fixed)

- **P1, latent, silent wrong geometry + lost work.** A sketch whose `offset`
  is a named-parameter formula (`"-wall"`): opening it from the tree and
  pressing Finish Sketch **without touching anything** replaced the formula
  with `0`, moved the sketch plane, and rebuilt everything downstream on it.
  Measured on a plate + boss: **48,226.19 mm3 -> 48,678.58 mm3**, both green,
  nothing said. The cause was one expression, `Number(feature.params.offset)
  || 0`, in two places: it collapses a formula to 0 *and* the collapsed number
  is what gets written back. `sameSketch` did not stop it either — it compared
  `Number("-wall")`, which is NaN, so even a no-op Finish counted as a change.
  The number to draw at is now the server's own `resolved` value (R1) and the
  formula is what is written back. **The plane-sketch half of this was
  PRE-EXISTING** (that branch already sent `offset: skPlaneOffset`); the face
  half arrived with `bc136be`. No saved design is affected: 47 designs, 0 use
  named parameters yet.
- **P3, the one-command lock.** Create Sketch leaves a plane PICK pending, and
  Measure is the one tool that takes the modal lock without ending a pending
  pick (`openMeasure` does not call `endPending`, and the viewport routes a
  click to `planePickAt` before its own picking). The pick then landed in the
  Offset step, which **took the lock off Measure and later handed it back as
  null** — two panels open, no lock. The face path had always asked
  (`openSketchOnFace`'s own `modalGuard`); the plane path now asks too.

## Cleared by MEASUREMENT (do not re-report)

- **`into_sign` is right** — 51 flat faces of 8 bodies (box, tube, L-shape,
  20 deg and 40 deg tapers, plate+boss, pocket, a plate on its side), each
  stepped 0.25 mm off the face along `into_sign * frame.z` and put to OCCT's
  solid classifier: **51 right, 0 wrong**, including the two ring faces whose
  centre of mass lies in the hole (`normal_at(center())` does not raise there,
  and the sign is still right). The build's brief ranked this first.
- **No left-handed frame exists.** `x cross y - z` over 31 faces of 6 bodies
  including rotated and tapered ones: **max 0.0**. The ghost's `makeBasis`
  cannot mirror the face outline. Ranked second.
- **The sibling door is sound.** A TOOL PANEL edit (Extrude, `amount: "h*2"`,
  opened and OK'd unchanged) keeps its formula — the P1 above is the sketch
  editor's alone, not the tool framework's.
- **Escape is safe.** The step's capture listener on `window` runs before
  `tool.js`'s, `sketcher.js`'s and `measure.js`'s bubble listeners and stops
  them; `section.js`'s capture listener defers on `S.modalTool`.
- Flows now driven in a real browser and green: Move Plane on a NEW face
  sketch, Move Plane twice in one sketch, Section view getting its arrow back
  after Esc, the arrow DRAGGED with a real pointer and its value stored.

## Also do not report (known, decided or recorded)

- No tilted planes / construction-plane feature; no arrow on tree re-edit; the
  pick panel's own button opens at 0 — plan section 10 P3, `specs/sketch-plane.md`.
- `sketch_on_face`'s docstring says "+y face offset < 0 INTO"; for +y that is
  wrong (frame z points -Y). `into_sign` is the measured truth and the
  six-face test locks it; the docstring is text.
- The Offset box rounds a DRAG to 0.1 mm and the arrow keeps the unrounded
  amount — cosmetic, the box is what OK reads.
- `author.py` refuses an absolute-offset plane sketch once a body exists and
  the panel lets the user make one silently — deliberate, plan section 10 P3.
- The node tests stub `viewport.js`, `sketcher.js`, `api.js` and `dialogs.js`
  and run the real `tool.js`; the key-listener count subtracts `tool.js`'s own
  Esc listener.

**Ground rules** (as always): reproduce by measurement or a red test before
fixing; smallest fix; tests with it; commit; restart the user's server if
`sketch.py` / `studio.py` changed; then this file -> `Status: NOTHING PENDING`,
a plan section 10 row for anything deferred, memory. Never `--fix`.
