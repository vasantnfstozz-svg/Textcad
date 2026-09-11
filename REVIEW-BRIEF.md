# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review the **fix commit of the Move / Rotate round-one
> review** (base `9e04ff6`). A **P0 was found and fixed**, so the fix pass gets
> its own read, the way Shell, Primitives, Booleans and Measure each did.
> Round two.
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

## The range, one line per commit

- the fix commit — **5 findings, all 5 fixed, 0 rejected; 15 backend + 2
  browser tests; fast tier 1513; ui v188.** Touched:
  `blocks.py` (`resolve_face` — the picked normal is a GATE, not a nudge;
  `_measure_face_rows` rows gained a `planar` flag),
  `toolplan.py` (`_place_input` refuses a body another feature is built from;
  `plan_move` / `plan_rotate` key an EDIT on `feature_id`, never on the
  truthiness of the stored params; a stored rotate with no `angle_deg` reads
  the op's own default 90),
  `static/js/tool.js` (`openEdit` no longer assigns the Op select a value it
  has no option for; `cancelSession` writes nothing when the session never
  wrote — `push` sets `st.touched`),
  `static/js/move.js` (`rotate`'s snapshot keeps `pivot` verbatim),
  `static/js/viewport.js` (`beginMoveGhost` falls back to the feature's own
  `/api/feature-mesh` when its body is not drawn),
  `tests/test_move_review.py` (new, 15), `tests/e2e/test_move_tool.py` (+2),
  `probes/move_review_probe.py` (new), LAUNCH-PLAN §10 (2 rows).

## Where the risk is

1. **`blocks.resolve_face` is shared by five callers** — `sketch_on_face`,
   `extrude_face`, `hole`/the planner, the face-outline projection and the
   EDGE pick (two faces name an edge). The gate only drops a candidate that is
   PLANAR **and** points away from a stored normal; curved faces are untouched
   on purpose (a sphere has one face and `normal_at(center)` means nothing
   there — that is what broke the first attempt, two fast-tier tests). Proven
   inert on the library: 50 designs rebuilt twice in one process, old scoring
   vs new, **0 features moved**. Look for a caller that passes a normal it did
   NOT get from a pick.
2. **The new refusal raises where nothing raised before.** `resolve_face` used
   to always answer. Check every caller survives a `ValueError` as a sentence
   (`plan()` catches, `_eval` records it as a problem) — and that the branch is
   only reachable for a single-face shape, since a closed solid always has a
   face pointing any way you like.
3. **`_place_input`'s "already used by" refusal.** It excludes the feature
   being EDITED and suppressed consumers. Check a struck-out consumer, a
   feature whose `inputs` hold the body twice, and the command-then-select path
   where `_pick_body` FELL BACK to the newest solid (the body_id it returns is
   the one the check reads).
4. **`st.touched` now gates Cancel's restore.** `push` is the only writer in
   edit mode today — confirm no other path can write params during a session
   (`applyOp` returns early while editing; `unbuild` is create-mode only).
5. **The ghost's async fallback** (`ghostWait` / `ghostDelta`): a fetch that
   lands after the drag ended, two drags in a row, a Cancel mid-fetch, and the
   feature that 404s (a struck row) must all leave no stray ghost.
6. **The `planar` flag widened `_face_rows`' cached tuple from 3 to 4.** Every
   reader now indexes rather than unpacks; the probes take `r[1]`. Check
   nothing else unpacks a row.

## Do not re-report

- `rotate`'s DEFAULT still turns about the world origin: decided (§10 P2 row).
- World axes only, no Copy, no Point-to-Point: decided in the spec, §10.
- Multi-lump Move/Rotate: MEASURED clean in round one (two separated lumps and
  a concentric ring-and-post, all three axes, health + volume + the way back).
  The corpus GAP itself is the standing §10 P2 row.
- A stored pick landing on the wrong SAME-facing face of a stepped body after a
  rigid move: the new §10 P1 row — the residual round one deliberately left.
- `solids()` offering intermediate rows to Shell and the Target dropdown: the
  new §10 P3 row.
- A turned L-bracket's bounding-box centre moves although the pivot does not:
  measured; the gauntlet proves the pivot via the way back.

## Ground rules (unchanged)

- Reproduce by measurement or a red test before fixing; kernel probes go under
  `probes/`. The gauntlet is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push, restart
  the user's server if the backend changed. Then the paperwork.
