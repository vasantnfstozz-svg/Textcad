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
| **Range** | `f898bfe..HEAD` - ONE commit: the fix pass for the nine findings of the Sketcher review (REVIEW-QUEUE section 1) |
| **Already reviewed** | everything up to `c2390ac`. The Sketcher review itself found these nine; **review the FIXES, not the findings** - the findings are in `REVIEW-QUEUE.md`'s done log with their measured numbers |
| **Effort** | high - one fix changes the arithmetic of EVERY sketch in the library (which shape is a hole and in what order the kernel composes them), and one adds validation in front of the path tool |
| **Branch** | `master` (no pull request - do not try to comment on GitHub) |
| **Frontend** | `ui v175`, `css v40` (unchanged) |

---

## The one that matters: sketches now compose OUTERS BEFORE HOLES

Two P0s, one root cause. `_compose` is sequential, but an entity list arrives
in the order the user DREW in. Measured before the fix
(`probes/sketcher_review_probe.py`):

- bore drawn before its rim -> **2827.43 mm2**, a solid disc, where the editor
  had drawn a **2513.27** washer. Status `ok`, no warning. (`create()` in
  `sketcher.js` forced entity 0 back to `add` so the kernel would have
  something to cut FROM.)
- r10, r30, r20 in drawing order -> **1570.80 mm2**; the island was cut away
  again. The correct ring+island is **1884.96**.

The fix, in `sketch.py`:

- **`_nesting_depth(shapes)`** - how many other entity shapes each one sits
  inside. Containment is MEASURED (`abs((inner - outer).area) < 1e-7 *
  max(inner.area, 1)`); the bounding box only SKIPS a pair, it never decides
  one, because a circle straddling the rim passes the bbox test and fails the
  real one.
- **`_compose`** builds every shape first, then sorts indices by depth
  (stable, so ties keep drawing order) and composes in that order. It runs
  the depth pass ONLY when something actually subtracts.
- **`sketcher.js create()`** no longer flips entity 0's mode; the modes go up
  exactly as the editor drew them.
- **`assignModes`'s `containedIn`** tests every outline point instead of one
  in eight.

**The stored entity list is untouched** - it keeps drawing order, so the
tree's rows and every saved design read the same as before; only the
arithmetic is reordered.

### Where to push hardest

1. **Is depth a sufficient sort key?** Sorting by "how many shapes contain
   me" is not a topological sort. Find an arrangement where it composes
   wrongly - overlapping (not nested) subtracts, two shapes that contain each
   other (duplicates), a subtract at depth 0 that must run after a later add.
2. **Ties.** `order.sort(key=...)` is stable in CPython, so equal depths keep
   drawing order. Is there a case where two shapes at the SAME depth must be
   ordered relative to each other (a chain of overlapping bites)?
3. **Does the reorder change an existing design?** That is the whole risk of
   the commit. `test_reordering_never_changes_a_correctly_ordered_sketch`
   covers the simple case; is there a library design whose current (wrong but
   accepted) shape changes?
4. **Cost.** n^2 booleans, bbox-filtered, on every rebuild of a sketch that
   subtracts. Is there a real design where that is slow? (One face
   subtraction measured 0.73 ms.)
5. **`_nesting_depth`'s bare `except Exception: continue`.** A boolean that
   will not run leaves depth 0, which puts the shape FIRST. Is silently
   composing it first worse than failing?

## The path guards (`_validate_path`)

`_path_face` had none, so the kernel spoke: `Standard_TypeMismatch`,
`StdFail_NotDone`, and build123d's "Face can only be created with closed
wires" landed in `f.problems` and were shown in the tree and the chat. The
same three inputs 500'd `/api/sketch/trim/pieces`, which builds every
entity's face - the very tool a user reaches for to clean a crossing up.

Four named guards (zero-length segment, fewer than 3 distinct points, a
crossing between two STRAIGHT non-adjacent segments, zero shoelace area) plus
a catch-all around `make_face()`.

6. **False positives are the danger here.** The crossing test skips any pair
   involving an arc (a chord is not the arc) and skips adjacent pairs. Find a
   VALID profile it rejects - a path that touches itself at a point, a
   figure-that-doubles-back-but-closes, an arc-heavy crescent.
7. **The shoelace runs only when there is no arc in the path.** Is there an
   all-line path with real area that it calls zero, or an arc path with no
   area that now slips through to the catch-all?
8. **The distinct-point count** folds in arc `via` points. Two points plus a
   via = 3 = allowed. Is a degenerate via (on the chord) caught downstream?

## The rest (smaller, but each changed behaviour)

9. **`exitMode()` / `resetEditor()` clear `scaleDrag`.** Is there a path where
   a scale SHOULD survive - does `finishSketch()`'s `commitScale()` still run
   before `create()` reaches `exitMode()`, and does anything read `scaleDrag`
   after `exitMode()` in the same tick?
10. **Point-list rotation (`entToSketch`).** `outlinePts`, `pathOutline`,
    `entityHandles`, `collectSnapPoints` and `hitTest` now rotate a
    polygon/path's points; `applyResize` writes a dragged point back through
    `lx, ly`. Check the round trip is exact and that the UNROTATED case (every
    sketch the editor itself makes, rotation absent) is byte-identical.
11. **`POST /api/sketch/path-arcs` + the tree's async label.** The row renders
    "curve N R" and is patched when the answer lands. Check the cache key
    (`arcKindsSeen` per feature id), that a stale label cannot survive an edit
    that changes the arcs, and that `CSS.escape` covers the feature ids this
    repo makes.
12. **`askJSON` in `api.js`** - a read-only POST with no busy overlay and no
    `doc-updated`, failing silently. Is silence right for every future caller,
    or does it hide a server restart the user should hear about?
13. **`sketch_snap`: closed edges lose their seam "corner" and "midpoint".**
    `_is_closed` is `edge.is_closed` in a try/except. Is there a flat face
    whose real corner sat on a closed edge and is now gone?

## Ground rules

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. The fast proof is
  `C:\Python314\python.exe -m pytest tests/test_sketch_review.py
  tests/test_e2_sketch.py tests/test_sketch_snap.py tests/test_sketch_trim.py
  tests/test_sketch_corner.py -q` (113 tests); the whole fast tier is 1209.
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

- **The nine findings this commit fixes.** They are listed with their measured
  numbers in `REVIEW-QUEUE.md`'s done log. Report a fix that is WRONG or
  INCOMPLETE, never the original defect.
- **The one rejected finding:** the un-awaited `releaseIsolation()` in
  `exitMode()`. `postJSON` never rejects (`api.js:124`) and in the edit path
  the release is the last request in flight. Rejected with that reason.
- **A full circle still offers no QUADRANT snaps.** Deliberate: a new snap
  kind is a feature, not a review fix.
- **`blocks.resolve_face` picks by nearest centre**, so two coplanar faces
  sharing a centre resolve to the wrong twin. Queued, P1.
- **Pattern's `_axis_face` guards with the bounding box that B replaced**;
  Mirror's `_plane_face` is in the same family. Queued.
- Face MODE (`extrude_face`) still opens on Join regardless of direction.
  Known.
- Edit mode never rewires a combiner. Known.
- `feature_faces` answers nothing for a row whose whole body was MOVED after
  it. Pre-existing.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
