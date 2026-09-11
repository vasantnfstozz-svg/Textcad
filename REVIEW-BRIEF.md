# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review commit **`9e04ff6`** (base `9af39d9`): the
> Move and Rotate tools, LAUNCH-PLAN.md P4's sixth and seventh, built
> 2026-09-11 from `specs/move-rotate.md`. Round one.
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

- `9e04ff6` — Move and Rotate: `blocks.rotate` grew `pivot` (+
  `body_centre`, `_rotate_pivot`); `document._move_offsets` (sentences for a
  bad offset) and `move` joins `PLACEMENT`; `toolplan.plan_move` /
  `plan_rotate`; `author.OP_NOTES["rotate"]`; `static/js/move.js` (new, both
  tools); `viewport.js` `beginArrows` / `endArrows` / `arrowAxisScreen` /
  `arrowsDragging` (N arrows, a colour each) and the body ghost
  (`beginMoveGhost` / `setMoveGhost` / `endMoveGhost` / `moveGhostInfo`);
  `tool.js` open() takes a CURVED pick as its body for `anyFace` + `bodyRow`
  tools and awaitPick offers every face to them; two panels in `index.html`
  (ui v187); ribbon + main wiring. Tests: `tests/test_move_tool.py` (36),
  `tests/test_move_gauntlet.py` (16 over the corpus), `tests/e2e/test_move_tool.py`
  (3 journeys). Probe: `probes/move_rotate_probe.py`.

## Where the risk is

1. **The pivot's three spellings and the legacy default.** `rotate(pivot=None)`
   and `"origin"` must be byte-identical to the old op (planetary-assembly
   carries a rotate); `plan_rotate` for an EDIT must hand back the STORED pivot
   (absent → `None`, and the JS `?? null` must not turn it into `"center"` on
   the first push — that would move a saved body). Check the JS `stored()` /
   `rtParams` path with `st.plan` absent AND present.
2. **The triad's placement is JS arithmetic** (`move.js along()`): centre +
   Σ box·axis from the plan's `origin` / `axes`. Spec allows exactly this and
   nothing more — check nothing else geometric crept in.
3. **The ghost's delta is `box − st.shown`.** `st.shown` is seeded in
   gizmos.begin from the boxes (an edit's stored values, a new session's zeros)
   and set again in afterApply; a revert restores the boxes first, so shown =
   lastGood. Look for a path where shown is stale: the Axis box changed and a
   drag starts before the rebuild lands (shown's angle is about the OLD axis);
   a typed value inside the debounce window followed by a drag.
4. **`bodyObjs.find` in `beginMoveGhost`** takes the first of
   `[featureId, inputBody]` present; with several bodies visible, the body
   found must be THIS one.
5. **`tool.js` open()'s new curved branch** sits before the curved refusal:
   any tool with `anyFace` + `bodyRow` gets it — today only Move / Rotate set
   both (Pattern: anyFace only; Shell: bodyRow only). Confirm nothing else.
6. **Rotate about a pivot of a body in several lumps** — `body_centre` is the
   whole compound's box; fine for a turn, but the Shell lesson says probe it.

## Do not re-report

- `rotate`'s DEFAULT still turns about the world origin: decided (§10 P2 row,
  user said not now on 2026-09-10; the tool sends `"center"` explicitly).
- World axes only, no Copy, no Point-to-Point: decided in the spec, §10.
- `move` is special-cased in `document._eval` rather than a MODIFIER: it
  predates this work and passes a SKETCH through too (`_kinds`).
- A turned L-bracket's bounding-box centre moves although the pivot does not:
  measured, the gauntlet proves the pivot via the way back.

## Ground rules (unchanged)

- Reproduce by measurement or a red test before fixing; kernel probes go under
  `probes/`. The gauntlet is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push, restart
  the user's server if the backend changed. Then the paperwork.
- Never `--fix`. One reviewer.

## Also open, and NOT the next review's job

`tests/e2e/test_tree_delete.py` is 5 red and was measured red at `667ccc0` in a
clean worktree, so it predates all of this (LAUNCH-PLAN §10's browser-tier P1
row carries it). REVIEW-QUEUE section 7 (Extrude) waits until this brief reads
NOTHING PENDING.
