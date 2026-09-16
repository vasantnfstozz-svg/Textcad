# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** `6586579..e642756` - the three parallel
> worktree streams - was reviewed on 2026-09-16 and its findings are fixed and
> pushed (`f538a76`, `2287157`). The next `code review` goes to
> `REVIEW-QUEUE.md` and takes the first status-board row marked TODO:
> **section 9, Trace image.**
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

## What the last review found (2026-09-16, range `6586579..e642756`)

Two findings, both in code the range itself had just added.

**1. The carried face pick crossed ops that place geometry against the
WORLD (P1, silent wrong geometry).** `31684d1` taught `Document.edit` to add
a `move`'s own delta to every stored `face_center` on a body the move
carries, and called a feature rigid when the move reaches it and all of its
inputs are rigid. That is the right question about the body a feature READS
and the wrong one about the body it HANDS ON. `mirror`, `rotate` about the
world origin and `polar_pattern` do not travel with their input - every face
centre of a mirror moves by MINUS the delta - so the carry pushed those picks
the wrong way. On a plate with two bosses, moved then mirrored, a pick on a
mirrored boss top was carried 6 mm the wrong way and landed on the plate top:
**720 mm3 became 7560 mm3 with every tree row `ok` and the solid valid, where
leaving the pick where it was had been RIGHT.** Fixed by splitting the two
questions (`document._hands_on_the_move`): a mirror still gets its own plane
pick carried, nothing below it does, and a `rotate` about the body's own
centre plus an unseeded `linear_pattern` were measured to travel with the move
and still carry. 8 new tests, 4 of them measured red first.

**2. The doorbell's browser half (P3).** `noteArrival` sat inside main.js's
`docSig(d) !== docSig(S.lastDoc)` branch, so an MCP redelivery of a design
whose bytes did not change - the reused-tab path, which does not rebuild -
left every field of that signature unchanged, the banner was never spoken and
the marker sat owed for ten minutes. `tests/test_mcp_arrival.py` proved the
server marker, not the banner. The call moved out of the branch; 3 e2e
journeys now drive a real page, the redelivery one measured red first.
ui v202.

## What was verified

Fast tier **1808 passed** (from 1800). Library tier **101 passed** - all 50
live designs rebuilt. `tests/e2e/test_doorbell.py` 3 passed. Ruff zero,
ESLint zero. The user's server restarted and serving `main.js?v=202`, exactly
one listener on 8123, `three.module.js` served locally (200, 1,326,016 bytes).
**The user's saved designs were never exposed to finding 1**: a scan of all 50
found 58 `move` features and not one face pick downstream of a world-placed op
that a move reaches.

## What was cleared, and must not be re-reported

- Everything on the previous brief's "cleared by measurement" list still
  stands: the scaled-body shell segfault is fenced, the my-part-9 stall is
  open on purpose, the PARAMETER half of the face-pick bug needs a body-frame
  pick (plan section 10 P1), the `resolve_face` shared-centre tie is a P2 for
  the pickers, and the favicon 404 is pre-existing.
- **The tool panels' hard-wired `(mm)`** is known and filed (plan section 10
  P2, "The tool panels ignore the display unit"). The units label is half a
  feature on purpose.
- **`_result_feature`'s spine walk was read and left alone.** Its callers
  (`_measured`, `_doc_json`, `measure`, `provenance`, `_check_dangling`, the
  viewport's `result_id`) all take the id and the part from the same call, so
  they stay consistent; the deliberate change to `tests/test_rebuild_cache.py`
  carries its reason in the test.
- **`static/vendor/three/`**: the two add-ons import nothing but `three`, no
  CDN reference is left anywhere in served code, and the import map matches
  what `viewport.js` asks for.
- **`run-textcad.cmd`** reads soundly. One nit, deliberately not changed: its
  `import build123d` readiness check costs a cold kernel import (10-30 s) on
  every launch, before `studio.py` pays it again.
