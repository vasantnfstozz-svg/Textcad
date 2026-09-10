# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review commit `e35450d` (section 5's fix pass). A
> P0-class finding was fixed there, so the house rule sends a second chat over
> the fix itself before the queue moves on to section 6.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range below; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes. Everything specific to this review is below.

---

## The range

```
e35450d   Primitives review, section 5: 8 of 8 findings fixed, 0 rejected; 55 new tests
```

Base: `7ea7eea`. One commit. `git show e35450d` is the whole diff.

Files touched: `blocks.py` (+138/-11), `document.py` (+64/-4), `author.py`
(+4/-2), `studio.py` (+4), `static/js/tree.js` (+17/-6),
`static/js/placement.js` (+29/-8), `static/css/studio.css` (+2),
`static/index.html` (ui v182, css v41), and two new files —
`tests/test_primitive_guards.py` (55 tests) and
`probes/primitives_review_probe.py`.

## What it does

Section 5 of `REVIEW-QUEUE.md` (primitives, the tree's shape editors,
click-to-place). Eight findings, all fixed. The full record is in the queue's
done log; the short version:

- **The P0.** `polygon_plate` and `hex_plate` span Z 0..thickness, while every
  primitive the AI's positioning rule calls "CENTERED at the origin" spans
  -t/2..+t/2. The rule listed all five together, so every `move` the AI
  computed for a hex body was half a thickness out. **The prompt was corrected,
  not the geometry** — two saved designs are built on the solid as it stands.
- New value guards on every primitive, a number-vs-word guard at the edit
  gate, and `Document.rebuild` now translating its failure through
  `blocks.plain_cause` instead of `repr(e)`.
- `with_center_hole` / `with_bolt_circle` refuse when they would drill nothing.
- `spec_checked` on the doc response, so a parked rollback bar no longer reads
  as "spec FAIL".
- Placement popup: one debounce timer per destination; a blank field no longer
  posts 0.

## Where the risk is

1. **The new refusals are the whole risk.** Every guard turns something that
   used to build (or used to fail differently) into a refusal. All 50 saved
   designs were rebuilt and none has a failed feature, but the corpora that
   were NOT run are the gauntlets. Look hardest at `blocks._positive` and at
   `_drilled`: `_drilled` compares `before.volume` to `after.volume` with a
   `1e-6` floor, and a legitimate but tiny hole in a very large body is the
   case to think about.
2. **`Document.numeric_params`** decides what the edit gate type-checks, from
   the type ANNOTATION on each op's function. It was written narrow on purpose
   (a bare `float` or `int` only), but it now sits in front of every edit in
   the app. An op whose numeric parameter is annotated some other way is
   unguarded; an op whose WORD parameter is somehow annotated `float` would be
   refused wrongly. The test covers `edges`, `open_face`; the rest is by
   inspection.
3. **`plain_cause` is now the last barrier for every feature failure**, not
   just fillet and chamfer. Its multi-line / over-200-character collapse is
   new. A build123d refusal that is genuinely useful and happens to be long
   would now be replaced by "the geometry kernel rejected the shape it would
   produce" — check whether that trade is right, and whether any op's own
   plain ValueError is long enough to be caught by it.
4. **`spec_checked` defaults to `True`** on the dataclass. A `Document` that
   is never rebuilt therefore claims the spec was checked. Follow whether any
   caller reads it before a rebuild.
5. **`polygon_plate` now accepts `sides=6.0`** where it used to raise
   (`sides != int(sides)` passes a whole float). That is a widening, not a
   narrowing — confirm it cannot let anything else through.

## Ground rules

`REVIEW-QUEUE.md`'s "Shared rules of engagement" and output format apply.
Read-only during the review; the fix pass follows in the same chat.

## Do not re-report

- **The Z convention itself.** That polygon/hex plates are not centred is now
  DELIBERATE and documented in three places. Whether they SHOULD be re-centred
  is a LAUNCH-PLAN section 10 row (P2) awaiting the user's decision, not a
  finding.
- **The `DEFAULTS` table in `placement.js` duplicating dimensions the backend
  has no defaults for.** Deliberate, and mirrored by
  `tests/test_placement_defaults.py`.
- **`placement.js` calling `loadMesh()` itself** — the known P3 already
  exempted for `sketcher.js` and `measure.js`.
- Everything in the queue's section 5 "Checked and found sound" list:
  `isRadius`/`diameterRow`, the Ø round-trip, `circumR`, the
  missing-catalogue fallback, `api_summary`/`_signature`.
- The nine items on the queue header's global "Never report" list.
