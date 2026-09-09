# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **In a fresh chat on Opus (`/model claude-opus-5`), type exactly this:**
>
> ```
> /code-review high - read REVIEW-BRIEF.md first: it names the commit range, the base, and what not to re-report
> ```
>
> That line never changes. Everything specific to this review is below.

---

## ONE reviewer, not a fleet

The fourth round was run as ten parallel lenses with a three-judge panel per
finding: about 46 Opus agents at xhigh before the user stopped it, 40-100x the
cost of a single review, and against this repo's own token rules ("no agent
fan-outs", LAUNCH-PLAN section 9). It did find a P0 that three cheaper rounds
had missed, so the shape is not banned - but it is for a P0 in code that has
already failed repeatedly, and only with the agent count quoted to the user
first. **This round is ONE reviewer at medium.** If it finds nothing, the
sketcher section is done.

---

## Review this

| | |
|---|---|
| **Range** | `5f65a7a..HEAD` - ONE code commit, `13da90c`: the fix pass for the FOURTH review of sketch composition |
| **Already reviewed** | everything up to `5f65a7a`, four times. Each round fixed the previous round's fix: 556a611, 6e2cae9, 5f65a7a, now 13da90c. All four reports are in `REVIEW-QUEUE.md`'s done log with their measured numbers |
| **Effort** | **medium.** The rule gained a constraint rather than changing shape, the library composes bit-identically, and composition is now measurably independent of drawing order. Read `_compose_order`, `_overlaps` and `_order_from` closely; treat the rest as confirmation |
| **Branch** | `master` (no pull request - do not try to comment on GitHub) |
| **Frontend** | `ui v178`, `css v40` (unchanged) |

---

## What changed

Round three made a cut that ends up FIRST in the composition order remove
nothing. That is right only if a leading cut genuinely meets nothing - and an
entity waits only for the shapes it is NESTED INSIDE, so a cut could be
ordered ahead of material it overlaps because that material sat inside a
DIFFERENT cut and was waiting itself. Measured: a boss with a bar across it
composed 22.3648 mm2; adding a pocket around them gave 78.5398 - the whole
boss, as if the bar had never been drawn, status `ok`, no warning.

`13da90c` makes the constraint two-part:

- an outer before anything nested inside it (unchanged);
- **material before a cut that overlaps it without containing it** - an edge
  added only while the order still STARTS with a cut, after which the order
  is recomputed, up to n passes.
- `_order_from(needs)` is the old topological walk, now over a general edge
  matrix; `_overlaps` / `_boxes_meet` measure the overlap with the bounding
  box only skipping.
- The emptiness reset fires only after a CUT now (after an add it was failing
  a single tiny entity that used to build).
- `_seg_point` names a segment with no `to`, or a `via` of one number.
- `sketch_corner._chain` refuses a start-less path instead of fabricating the
  origin - which `set_arc_radius` was writing back into the design.
- `scaleEntity` leaves a malformed path or an empty polygon alone instead of
  repairing it.
- Suppressed and rolled-back features drop their notes.

### Where to push hardest

1. **Is the two-part constraint sufficient, or is there a third case?** Look
   for an arrangement where two entities must be ordered relative to each
   other and NEITHER nesting nor add-cut overlap relates them: two cuts that
   overlap each other over shared material, an add overlapping an add that a
   cut then bites, a cut that meets material only through a third shape.
   Measure the area and compare with what the editor paints (add fills GREEN,
   cut fills RED, per entity, no even-odd canvas fill).
2. **Cycles.** The overlap pass adds edges to a matrix that already carries
   containment, and skips a pair when the reverse edge exists - but a longer
   cycle (A before B before C before A) can still form. Construct one and
   check the fallback branch composes sanely rather than silently badly.
3. **Termination.** The pass loops up to n times, recomputing the order each
   time. Can it oscillate, or add an edge every pass without ever freeing the
   lead, and exit quietly with a bad order?
4. **Cost.** It fires only while the order starts with a cut. Confirm that,
   and that no design in `designs/` newly pays for it. Measured before:
   `rocky-balboa/field_sketch` 1207 ms with the pass against 1506 ms without
   (same order - the pass never fires there).
5. **`_overlaps` returns False on an exception**, like `_area_of` returning
   0.0: a pair whose boolean will not run is treated as apart, which drops
   the edge and so can drop the cut. Find a pair where `&` throws.
6. **The refusals.** `sketch_corner` and `_path_face` refuse a start-less
   path, and `_seg_point` refuses a malformed segment. Check every producer
   again for one that can emit either - trace-image, import, trim/pieces,
   author.py, MCP, the sketch endpoints - and check the failure reaches the
   user as a sentence in the tree, never a 500.
7. **The frontend early-outs.** `scaleEntity` returns the entity untouched for
   a malformed path or an empty polygon. Does Scale still behave for the GOOD
   entities in the same drag ("scale all")? Does anything downstream depend
   on every entity having been scaled?

## Ground rules

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. The fast proof is
  `C:\Python314\python.exe -m pytest tests/test_sketch_review4.py
  tests/test_sketch_review3.py tests/test_sketch_review2.py
  tests/test_sketch_review.py tests/test_e2_sketch.py tests/test_sketch_snap.py
  tests/test_sketch_trim.py tests/test_sketch_corner.py -q`; the whole fast
  tier is 1258.
- **A finding is a concrete input on which the code does the wrong thing**,
  with the exact click or data that triggers it. Order: P0 wrong geometry or
  data loss, P1 blocks the action, P2 daily annoyance, P3 polish.
- **The frontend must not re-derive backend facts** (rule R1).
- **Two banned failures:** a kernel exception reaching the user (OCP errors
  derive from `Exception`), and a "successful" invalid or empty solid.
- **Comments naming a date record a past bug**; do not report them as noise.
- **No fixes, no style remarks**; both linters run at zero.

## Output format

```
### F1 - P<0-3> - <one line>
- File: <path>:<line>
- Trigger: <the exact click or input>
- Expected / Actual: <one line each>
- Confidence: high | medium | low - <why>
- Evidence: <1-3 quoted lines>
```
then `### Checked and found OK` (up to 8) and `### Could not judge without
running the app` (up to 5). At most 15 findings; say so if fewer than 5 are
high or medium confidence.

## Already known - do NOT report

- **The eight findings this commit fixes**, J1-J8 in `REVIEW-QUEUE.md`'s done
  log under "Section 1, round four", with their measured numbers. Report a fix
  that is WRONG or INCOMPLETE, never the original defect.
- **"The note is never rendered, so a dropped cut is still silent" is REFUTED
  and measured.** Only `extrude.js` reads `f.notes`, but `Document.warnings`
  republishes every note (document.py:1211) and `tree.js renderWarnings`
  shows them in its info box.
- **The three findings deferred on purpose**, now rows in LAUNCH-PLAN section
  10: `sketch_trim.py`'s own copy of the composition rule (P1); a
  self-crossing polygon building an invalid face that reports ok (P2); the
  arc-label doc guard keyed by design NAME (P3).
- **The findings of rounds one, two and three** and their two rejections (the
  un-awaited `releaseIsolation()`; the note-rendering claim above).
- **The first card in the sketch tree shows a fixed `add` badge.** A leading
  cut is composable now, so the badge is stricter than the backend needs.
- **A full circle still offers no QUADRANT snaps.** Deliberate.
- **`blocks.resolve_face` picks by nearest centre**, so two coplanar faces
  sharing a centre resolve to the wrong twin. Queued, P1.
- **Pattern's `_axis_face` guards with the bounding box `_face_of` dropped.**
  Queued.
- **`-m library` cannot collect** (duplicate basenames against `tests/e2e`).
  A tracked test-infrastructure item.
- Face MODE (`extrude_face`) still opens on Join regardless of direction, and
  Edit mode never rewires a combiner. Known.
- `feature_faces` answers nothing for a row whose whole body was MOVED after
  it. Pre-existing.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
