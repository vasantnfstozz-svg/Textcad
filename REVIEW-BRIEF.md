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
| **Range** | `bdca16b..HEAD` - ONE code commit, `5f65a7a`: the fix pass for the THIRD review of sketch composition |
| **Already reviewed** | everything up to `6e2cae9`, three times. `556a611` fixed REVIEW-QUEUE section 1; `6e2cae9` fixed the re-review of that; `5f65a7a` fixes the re-review of THAT. All three reports are in `REVIEW-QUEUE.md`'s done log with their measured numbers |
| **Effort** | **medium** - the P0 rule says a P0 fix earns another round, and this is the third P0 in the same twenty lines. But the surface is now SMALLER than last time: the deferral is gone rather than replaced, so there is less new logic to get wrong. Read `_compose` and `_area_of` closely; treat the rest as confirmation |
| **Branch** | `master` (no pull request - do not try to comment on GitHub) |
| **Frontend** | `ui v177`, `css v40` (unchanged) |

---

## What changed, and why the last two attempts failed

Round one sorted a sketch's entities by nesting DEPTH; a depth is not an
ordering constraint, so it moved entities no nesting related and a live design
went red. Round two replaced the sort with `_compose_order`, a real
topological order, and then DEFERRED a leading subtraction to just after the
first add so the design would keep the area it had. Those two cancel:
`_compose_order` hoists a subtraction in FRONT of the add nested inside it
*precisely so that add survives as an island*, and the deferral subtracted it
from exactly that add. Measured: `[r20 subtract, r10 add]` built area **0.0**
and reported `ok`; three identical bars inside one subtract blob built 144.0
instead of 216.0, with the FIRST bar missing.

`5f65a7a`:

- **`_compose`** - a leading subtraction removes NOTHING (nothing is composed
  yet, so there is nothing to cut) and calls `_note` so it is not silent.
  `waiting[]` is gone.
- **`_area_of(shape)`** - `.area`, or 0.0 for anything that cannot answer. A
  step that empties the profile resets `result` to `None`, so the next add
  starts it again and the kernel is never handed an empty shape to subtract
  from. A sketch that ends empty raises one of two sentences: "the cuts
  removed everything that was drawn", or "every entity is a cut" when there
  was never an add at all.
- **`_path_face`** - a missing `start` is refused instead of defaulting to the
  origin; `via` is read outside the arc translator's `try`.
- **`tree.js loadArcKinds`** - captures the design before its await and bails
  if it changed; an in-flight key dedupes the N calls one render makes.
- **`sketcher.js scaleEntity`** - `|| []` / `|| [0, 0]` guards.

### Where to push hardest

1. **Is "a leading subtraction removes nothing" right for a subtraction that
   OVERLAPS rather than contains?** `_compose_order` only orders nested pairs,
   so a red shape that merely overlaps a later green one keeps drawing order
   and its cut is now dropped. Find an arrangement a user can actually draw
   (or the AI can author) where that loses a cut they wanted. Note the mode
   rule this rests on: `assignModes()` (sketcher.js:1441) assigns `subtract`
   ONLY by odd containment depth, so two overlapping shapes are both `add`.
2. **The `_area_of` reset.** `result = None` mid-loop means a later add starts
   a fresh profile. Is there an arrangement where an add after an emptying cut
   should still have been cut by something already applied - or where the
   reset hides a genuine "this sketch is nonsense" that used to fail?
3. **`_area_of` swallowing.** It returns 0.0 for any exception. Can a
   legitimate part-composed profile fail to answer `.area` and be treated as
   empty, silently dropping everything composed so far?
4. **Does it change a committed design?** Swept: only
   `esp32-remote/logo_1_sketch`'s arithmetic moves (4.3671 -> 7.6656), and all
   six of that design's `logo_*` features are suppressed, so no built geometry
   changes. Find a second design that moves, or one whose shape changes at
   equal area.
5. **The refusal in H6.** A `path` with no `start` now fails the feature. No
   design in `designs/` has one (swept) and author.py:333 documents `start`,
   but check the OTHER producers - trace-image, import, trim/pieces, the
   sketch API endpoints - for a path entity built without one.
6. **The note.** `_note` from `_compose` lands in `f.notes` via
   `document.rebuild`'s drain. Check an endpoint that composes WITHOUT
   draining (`/api/sketch/trim/pieces`, `/api/sketch/path-arcs`) cannot leave
   a note that later attaches to an unrelated feature.
7. **`loadArcKinds`.** The in-flight key is `feat.id + " " + JSON`; the doc
   guard compares `arcKindsDoc`, which is keyed by `doc.name`. Two tabs of the
   SAME design share that name - can a reply still cross between them?
8. **Cost.** `_containment` is unchanged and still O(n^2) measured booleans on
   the pairs the box lets through (735 ms on `rocky-balboa/field_sketch`,
   23 entities). Known, not a finding.

## Ground rules

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. The fast proof is
  `C:\Python314\python.exe -m pytest tests/test_sketch_review3.py
  tests/test_sketch_review2.py tests/test_sketch_review.py
  tests/test_e2_sketch.py tests/test_sketch_snap.py tests/test_sketch_trim.py
  tests/test_sketch_corner.py -q`; the whole fast tier is 1239.
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

- **The eight findings this commit fixes**, listed as H1-H8 in
  `REVIEW-QUEUE.md`'s done log under "Section 1, round three", with their
  measured numbers. Report a fix that is WRONG or INCOMPLETE, never the
  original defect.
- **Four tests from the previous round were corrected in place** because they
  asserted the defective contract (the eaten island as the expected area, a
  start-less path as legal, two message regexes). That is deliberate and
  recorded; a test whose NEW assertion is wrong is a finding.
- **The nine findings of the first review** (556a611) and its one rejection,
  the un-awaited `releaseIsolation()` in `exitMode()`; **the eight of the
  second** (6e2cae9).
- **The first card in the sketch tree shows a fixed `add` badge.** A leading
  subtraction is composable now, so the badge is stricter than the backend
  needs. Relaxing it is a feature.
- **A full circle still offers no QUADRANT snaps.** Deliberate.
- **`blocks.resolve_face` picks by nearest centre**, so two coplanar faces
  sharing a centre resolve to the wrong twin. Queued, P1.
- **Pattern's `_axis_face` guards with the bounding box that B replaced**;
  Mirror's `_plane_face` is in the same family. Queued.
- **`-m library` cannot collect** (duplicate basenames against `tests/e2e`).
  That is why all three P0s in this code reached a live design uncaught; it is
  a tracked test-infrastructure item, not a finding about this commit.
- Face MODE (`extrude_face`) still opens on Join regardless of direction.
  Known. Edit mode never rewires a combiner. Known.
- `feature_faces` answers nothing for a row whose whole body was MOVED after
  it. Pre-existing.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
