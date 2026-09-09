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

## Review this

| | |
|---|---|
| **Range** | `1301314..HEAD` - ONE code commit, `6e2cae9`: the fix pass for the SECOND review of the sketcher reorder |
| **Already reviewed** | everything up to `556a611`, twice. `556a611` was the fix pass for REVIEW-QUEUE section 1; `6e2cae9` fixes the eight findings of the re-review of THAT. Both prior reports are in `REVIEW-QUEUE.md`'s done log with their measured numbers |
| **Effort** | high - the same arithmetic as last time: which shape is a hole and in what order the kernel composes them, for every sketch in the library. The previous attempt at this exact code shipped a P0 |
| **Branch** | `master` (no pull request - do not try to comment on GitHub) |
| **Frontend** | `ui v176`, `css v40` (unchanged) |

---

## The one that matters: composition order, attempt two

`556a611` sorted a sketch's entities by nesting DEPTH. That was wrong in a way
one review did not catch: depth is a number, not an ordering constraint, so
the sort moved entities that no nesting relates. A top-level subtraction (one
that is inside nothing, depth 0) sorted to the very front, ahead of the adds
it was drawn after, and the guard "first entity cannot be a subtraction" then
refused the whole feature. `esp32-remote/logo_1_sketch` built at 4.37 mm2
before that commit and went red after it.

`6e2cae9` replaces the sort with `_compose_order` in `sketch.py`:

- **`_containment(shapes)`** - the measured matrix `inside[i][j]`, factored
  out of the old `_nesting_depth` (which is now its row sums). Mutual pairs
  (two copies of one shape, a mirror in place) are dropped, so duplicates
  cannot form a cycle.
- **`_compose_order(shapes)`** - a stable topological order: repeatedly take
  the lowest-numbered entity all of whose containing shapes are already
  composed. One edge per nested pair and nothing else, so an outer precedes
  what is nested inside it and everything else keeps the user's drawing order.
  If no entity is ever free (a containment cycle), it falls back to drawing
  order.
- **`_compose`** - a leading subtraction now WAITS in `waiting[]` for the
  first add and is applied immediately after it, instead of raising. The
  ValueError survives only for a sketch where every entity subtracts.
- **`_box_within`** replaces `BoundBox.is_inside` as the skip filter, X and Y
  only.

### Where to push hardest

1. **Is the topological order actually sufficient?** It constrains only nested
   pairs. Find an arrangement where two entities at the SAME level must be
   ordered relative to each other and drawing order gets it wrong - a chain of
   OVERLAPPING (not nested) subtracts, a bite that overlaps two outers, an add
   that overlaps a hole's rim.
2. **The deferral.** A subtraction held back to just after the first add is
   applied to that add *and nothing else yet*. Is there an arrangement where
   it used to cut more than that - two leading subtractions, or a leading
   subtraction that should have cut an add composed later?
3. **The cycle fallback.** `_containment` drops MUTUAL pairs, but a 3-cycle
   (A in B, B in C, C in A) is not dropped and lands in the `nxt is None`
   branch. Is that branch reachable with real shapes, and does it then compose
   sanely?
4. **Does it change a committed design?** That is the whole risk again. The
   library was swept: nothing raises, and exactly one area moves
   (`esp32-remote/logo_0_sketch` 277.16 -> 280.46 mm2, entity 8 an island
   inside the subtract 9). Find a second one, or a design whose shape changes
   at equal area.
5. **`_box_within`'s tolerance** is a flat `1e-7` mm, absolute, on a box test
   that only SKIPS. Is there a pair it wrongly skips - shapes sharing a
   boundary exactly, a shape whose box matches its container's to the micron?
6. **Cost.** Still O(n^2) measured booleans on the pairs the box lets through.
   `rocky-balboa/field_sketch` went 4128 -> 538 ms per rebuild, but 538 ms is
   not nothing. Is there a design where it is still felt?

## The arc translation (`_path_face`)

Each segment's `ThreePointArc` / `Line` is now individually wrapped and the
kernel's failure re-raised as a sentence naming the arc number. There is
deliberately NO collinearity threshold of our own: OCCT accepts a middle
point 1e-6 off a 100 mm chord (probed), so any threshold we picked would
reject real profiles.

7. **Does the per-segment wrapper swallow something it should not?** It
   catches bare `Exception` around a build123d builder call that mutates the
   enclosing `BuildLine` context. Is there a failure mode where the raise
   leaves the context in a state that breaks the NEXT sketch, or where a
   KeyError from a malformed `s["to"]` now reads as a geometry message?
8. **The message names `arc N` counting from 1** over `segs`. Does that match
   what the tree's row for that curve calls it?

## The rest (smaller, each changed behaviour)

9. **`sketch_snap`: `centred = geom_type == ELLIPSE`** now also yields
   `arc_center`. A closed BSPLINE (an elliptical pocket's TOP rim, probed) is
   deliberately still left with no point at all. Is that the right line, and
   is `arc_center` trustworthy for a PARTIAL ellipse arc as well as a closed
   one?
10. **`tree.js`: both arc-label maps are cleared when `doc.name` changes**
    (`arcKindsFor`, called at the top of `renderDoc`). Check that a rename, a
    tab switch back and forth, and two tabs of the SAME design behave; and
    that clearing mid-flight cannot let a resolved `loadArcKinds` write a
    label belonging to the previous design.
11. **`api.js askJSON` now returns `{error, status}` on `!r.ok`.** It has one
    caller today. Does `res.error` shadow a legitimate response field for any
    plausible future caller?
12. **`sketcher.js entSamplePts`** got `|| []` / `|| [0, 0]` guards. Are its
    siblings (`outlinePts`, `entityHandles`, `hitTest`, `collectSnapPoints`)
    equally safe on the same malformed path entity, or does the crash just
    move one function along?

## Ground rules

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. The fast proof is
  `C:\Python314\python.exe -m pytest tests/test_sketch_review2.py
  tests/test_sketch_review.py tests/test_e2_sketch.py tests/test_sketch_snap.py
  tests/test_sketch_trim.py tests/test_sketch_corner.py -q`; the whole fast
  tier is 1225.
- **A finding is a concrete input on which the code does the wrong thing**,
  with the exact click or data that triggers it. Order: P0 wrong geometry or
  data loss, P1 blocks the action, P2 daily annoyance, P3 polish.
- **The frontend must not re-derive backend facts** (rule R1).
- **Two banned failures:** a kernel exception reaching the user (OCP errors
  derive from `Exception`), and a "successful" invalid solid.
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

- **The eight findings this commit fixes**, listed with their measured numbers
  in `REVIEW-QUEUE.md`'s done log under "Section 1 again". Report a fix that
  is WRONG or INCOMPLETE, never the original defect.
- **`esp32-remote/logo_0_sketch` 277.16 -> 280.46 mm2 is accepted**: entity 8
  sits inside the subtract 9, so the island survives - the reorder rule
  working as designed. Report a DIFFERENT design that changes.
- **The nine findings of the first review** (556a611) and its one rejection,
  the un-awaited `releaseIsolation()` in `exitMode()`.
- **The first card in the sketch tree shows a fixed `add` badge.** With the
  deferral, a leading subtraction is now composable, so the badge is stricter
  than the backend needs. Relaxing it is a feature, not a review fix.
- **A full circle still offers no QUADRANT snaps.** Deliberate.
- **`blocks.resolve_face` picks by nearest centre**, so two coplanar faces
  sharing a centre resolve to the wrong twin. Queued, P1.
- **Pattern's `_axis_face` guards with the bounding box that B replaced**;
  Mirror's `_plane_face` is in the same family. Queued.
- **`-m library` cannot collect** (duplicate basenames against `tests/e2e`).
  That is why both P0s in this code reached a live design uncaught; it is a
  tracked test-infrastructure item, not a finding about this commit.
- Face MODE (`extrude_face`) still opens on Join regardless of direction.
  Known. Edit mode never rewires a combiner. Known.
- `feature_faces` answers nothing for a row whose whole body was MOVED after
  it. Pre-existing.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
