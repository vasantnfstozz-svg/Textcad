# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING** — `33b2f49` fixed two findings and neither was a
> P0 (a P2 hardening gap and a P3 wrong sentence), so there is no third round
> to run. The next `code review` goes to the queue.
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

## Just done: section 4's FIX PASS, re-reviewed (33b2f49)

`c9b2e92` closed a P0-class finding — the stranding heal ticked `through` on a
tool another cut shared, and that cut lost 3600 mm3 unasked — so the house rule
sent a second chat over the fix commit. It found **two findings, both fixed**,
4 new tests, fast tier 1318 green. Full record in `REVIEW-QUEUE.md`'s done
log, section 4, round two.

Both were **holes in the guard round one had just built** — the same shape as
section 1's G2, where F4's catch-all wrapped only `make_face()` and
`StdFail_NotDone` came out of `ThreePointArc` instead:

- `getattr(out, "volume", 0)` does **not** swallow an exception raised by the
  property (the default only covers `AttributeError`), so a degenerate loft
  escaped `_loft` as raw kernel text — the exact failure the guard exists to
  stop. It reads through `inspector._try` now.
- `except ValueError: raise` assumed every `ValueError` is one of our
  sentences, but build123d raises its own bare ones with kernel wording
  (`ValueError('More than one wire is required')`). `_loft` translates
  everything now; the count and kind checks both run before it.
- and the new `_pick_body` refusal called a **healthy** body broken: behind a
  parked rollback bar a feature has no part, so a face-mode plan said "'boss'
  has not built — fix that feature first" about a body that builds at
  1206.37 mm3 the moment the bar comes down.

Neither loft door could be driven through the app; they were fixed because the
barrier's whole job is that nothing leaks. That is stated plainly in the done
log rather than dressed up as a live bug.

**Four of the five risks the previous brief named cleared by measurement**,
including the biggest: `_live_source` is behaviour-identical to both walks it
replaced (52 files, 15 struck features, zero mismatches, plus hand-built
struck chains). The kind gate's 2D test also held on every 2D-producing path,
which I had expected to be the weak one.

## What the next review takes

`REVIEW-QUEUE.md`'s status board, first row marked TODO: **section 5,
Primitives and shape editing**. Sections 1-4 are closed.

## Do not report (already known, or settled)

- **A suppressed final boolean promotes its TOOL to the result**
  (`_result_feature`, `document.py:1283`). Open P1 in LAUNCH-PLAN section 10.
  Section 4 located it and recorded two notes for it in the done log.
- **Rotate and Scale do not share a pivot.** Measured, documented in both
  docstrings and `OP_NOTES`, and deliberately left alone — changing it would
  move geometry in saved designs. The user was asked on 2026-09-10 and said
  not now. P2 row in LAUNCH-PLAN section 10.
- **The Add Feature dialog collects combiner inputs in TREE ORDER**, so a Cut
  cannot target a body that precedes its tool. Its own note says so, and the
  tool-panel path orders them correctly. Judged documented, not a defect.
- The open P1/P2/P3 rows in LAUNCH-PLAN section 10; the pre-existing red
  browser tests (`tests/e2e/test_tree_delete.py`, five; the order-dependent
  revolve ring test); `-m library` not collecting; two requests reaching the
  kernel at once; lint-class output.
- Comments naming what the user saw on which date are history, not clutter.
