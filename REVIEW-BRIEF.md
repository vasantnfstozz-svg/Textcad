# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review commit `c9b2e92` (section 4's fix pass). One
> of its nine findings was silent wrong geometry that would have been SAVED,
> and the fixes sit inside `rebuild` itself, so the house rule sends a second
> chat over the fix commit.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range below; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes. Everything specific to this review is below.

---

## The range

```
c9b2e92        (one commit, base e335a4f)
```

`git show c9b2e92 --stat` — `document.py`, `toolplan.py`, `blocks.py`,
`author.py`, `tests/test_boolean_review.py` (new, 26 tests),
`probes/boolean_review_probe.py` (new). Production code +157 / -26.

## What it did

Section 4 of `REVIEW-QUEUE.md` (Booleans and transforms, never reviewed):
9 findings, all 9 fixed, 0 rejected. The full record is that file's done log.
The five that changed behaviour every design goes through:

- **`_check_combiner_inputs`** (new, `document.py` ~line 103) — a KIND gate on
  every combiner, run in `_eval` BEFORE the kernel. It exists because
  `loft(sketch, solid)` **segfaults** OpenCASCADE (exit 139 standalone), which
  no `except` can catch, and because `intersect(body, sketch)` returned a 2D
  Sketch that CONSUMED the body and left the design with no bodies at all
  while every row stayed green.
- **the spec verdict** (`rebuild`, ~line 1006) — no leaf bodies used to mean
  "nothing to check", so a design with NOTHING built verified against a spec.
  It is a failure now.
- **`_check_idle_cuts`** (new) — names a cut that removed no material.
- **`_check_pieces`** — a pattern's copy form no longer reports N pieces.
- **`_heal_stranding_cuts`** — leaves a tool another cut shares alone. This is
  the P0-class one: measured, the other cut lost 3600 mm3 more than its own
  parameters ask for, unasked and unmentioned.
- **`_live_source`** (new) — one copy of the struck-node pass-through walk,
  replacing the private copies in `consumed_ids` and `_check_pieces`. Behaviour
  was identical in all three; confirm that.

## Where the risk is

1. **`_live_source` replaced two working walks.** `consumed_ids` is what the
   viewport and the exporter filter on. If the shared version differs from
   either original by a hair, bodies appear or vanish.
2. **The new spec failure is a new way for `rebuild` to return False.**
   Anything that treats `ok` as "the geometry is fine" now also sees "there is
   no geometry". Check the callers, especially the export path and the MCP.
3. **The kind gate refuses input combinations that used to build.** The 50
   library designs were checked (none uses a boolean on a sketch or a loft on
   a solid, zero volume drift), but a hand-written or AI-authored tree could.
   A design that no longer OPENS would be the bad outcome — `from_data` runs
   through `add`, not `_eval`, so it should still open and show a failed row.
4. **`_check_idle_cuts` compares 2dp-rounded volumes with a 0.01 tolerance.**
   A legitimate cut that removes a whisker would be called idle.
5. **`_pick_body` now raises** where it used to fall back. Three callers
   (extrude, revolve, hole face modes).

## Ground rules

Read the diff yourself, ONE reviewer, no subagents. Measure before claiming —
`probes/boolean_review_probe.py` reproduces all nine originals (§3's
sketch+solid case is behind `--crash` because it kills the process). The fast
tier is 1314 passing (1288 + the 26 new); run the files the diff touches plus
`tests/test_launch_rules.py`.

## Do not report (already known, or settled)

- **A suppressed final boolean promotes its TOOL to the result**
  (`_result_feature`, `document.py:1283`). Open P1 in LAUNCH-PLAN section 10.
  Section 4 located it and recorded two notes for it in the done log; it was
  deliberately not fixed here.
- **Rotate and Scale do not share a pivot.** Measured and documented, and the
  behaviour was deliberately left alone — changing it would move geometry in
  saved designs. Now a P2 row in LAUNCH-PLAN section 10.
- **The Add Feature dialog collects combiner inputs in TREE ORDER**, so a Cut
  cannot target a body that precedes its tool. Its own note says so ("First
  input MINUS the rest (by tree order). Keep body first."), and the tool panel
  path orders them correctly. Judged documented, not a defect.
- The open P1/P2/P3 rows in LAUNCH-PLAN section 10; the pre-existing red
  browser tests (`tests/e2e/test_tree_delete.py`, five; the order-dependent
  revolve ring test); `-m library` not collecting; two requests reaching the
  kernel at once; lint-class output.
- Comments naming what the user saw on which date are history, not clutter.
