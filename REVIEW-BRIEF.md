# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** LAUNCH-PLAN section 10's P1 "sketch_trim keeps
> its own copy of the sketch composition rule" is CLOSED at `3b230b7`, and the
> review of it ran FIVE rounds (`1d6c2d8`, `0ef49e5`, `c54b4d8`, `cfd0485`,
> `df21052`) — 6 findings fixed, 0 rejected. The next `code review` therefore
> goes to `REVIEW-QUEUE.md` and takes the first TODO row of the status board:
> **section 8, Import STL and STEP** (which may share its chat with section 9,
> Trace image, as the queue note says).
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

## What the last review did (the Trim composition P1, five rounds)

**6 findings, 6 fixed, 0 rejected. One P0 and one P1 among them. No live
design moved: all 50 rebuild to identical volumes with identical warnings, at
every round.**

- **`sketch_trim.py` kept its own composition rule** and disagreed with the
  builder. On `[boss r5 add, bar 80x6 cut, pocket 40x20 cut]` the builder
  composes 22.3648 mm2 and trim composed 0.0, so every Trim click on that
  cluster answered "the result would have no area left"; its pointwise
  material test called `(0, +-4)` empty where the builder leaves boss; and two
  guards refused work the builder accepts (deleting one bar from
  `[pocket cut, bar, bar, bar]`, which builds 144.0 mm2). `sketch.compose` and
  `sketch.compose_order` are public now and trim asks them (R1).
- **P0 in `sketch.py` itself**, found because the Trim fix inherits the
  builder's order. The "material before a cut that overlaps it" pass ran only
  while the order STARTED with a cut, so one unrelated shape drawn first
  switched it off: `[far circle, boss, bar, pocket]` built **157.0796** — the
  boss SOLID, the bar's 56.17 mm2 of red paint lost, green and silent — where
  the honest answer is 100.9046. The pass runs for every cut now.
- **P1, in the fix's own new code:** the new builder check made one Trim click
  cost 43.9 s on `rocky-balboa/field_sketch` (23 entities) against 15.6 s
  without it. It is off the rebuild branch now — where it could tell us
  nothing anyway — and measured over 176 real rebuild trims in the library,
  not one leaves a list the builder refuses.
- **P2:** a sketch can ask for an order that does not exist (two cuts
  overlapping, each containing an add that pokes into the other). The builder
  has always broken such a knot by falling back to the drawing order and said
  nothing — 210.0 mm2 where the paint says 180.0. It says so now, names every
  shape in the knot and nothing else, and the note reaches `Document.warnings`.
- Two P3 rounds spent getting that sentence to name the right shapes.

## Do not re-report

- `_entity_face` taking `faces()[0]`: probed, every entity kind builds exactly
  one face today and the multi-face cases are refused by `_entity` first.
- `_knot_note`'s singular branch being unreachable: known, correct, tested.
- `_compose_order`'s `modes=None` branch: no production caller, kept so the
  older `probes/sketcher_review3_probe.py` still runs.
- Trim's speed on a big sketch (6.1 s to HOVER a 23-entity sketch). Measured,
  PRE-EXISTING, and now a P2 row on LAUNCH-PLAN section 10 with the cause
  (`_pieces_raw` sampling and pair-intersecting every outline).
- Everything else on LAUNCH-PLAN.md section 10's open list, and the
  pre-existing red `tests/e2e/test_tree_delete.py` (five, measured at 667ccc0).
