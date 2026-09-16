# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `6586579..e642756` - three parallel worktree
> branches merged into master: the face-pick carry and the struck-boolean
> result, the launch-prep batch (doorbell, vendored three.js, notices, units
> label), and the shell triage that changed no product code.
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

## The range, and how it was built

Base `6586579`, head `e642756`. **This range was built by three agents working
in parallel worktrees, not by one session in sequence** - the first time that
has happened on this project. Each stream was fenced to its own files and each
ran only its own targeted test files; **no stream ran the full tier, and no
stream saw the other two's code.** The fast tier was run ONCE, by the parent
session, after the merge: **1800 passed** (from 1762), Ruff zero, ESLint zero.

That is the structural risk in this range, and it is where a reviewer should
look first: **a defect that only shows where two streams meet cannot have been
caught by anyone who worked on it.** The merge itself had one conflict, in the
`LAUNCH-PLAN.md` §10 table, resolved by hand.

## One line per commit

| Commit | Stream | What it does |
|---|---|---|
| `f0224fe` | shell | Proves the scaled-body segfault already fenced at HEAD and the my-part-9 stall still open; 1 test, 3 probes. **No product code.** |
| `37afa42` | shell | Line-ending tidy on the triage note. |
| `31684d1` | picks | Face picks follow a rigid `move`; `_result_feature` follows the tail's own spine; 19 tests. |
| `6b4c494` | launch | Doorbell arrival marker moves to the server; three.js vendored; `THIRD-PARTY-NOTICES.md`; units label; `run-textcad.cmd`; 8 tests. |
| `15e38b1` | launch | Paperwork: four backlog rows closed, two new rows. |

## Where the risk is

1. **`document.py` `_carry_face_picks` / `_shift_face_picks` is the sharp
   edge.** It mutates stored `face_center` values on an edit, which is a write
   to the user's saved design data. The rigidity rule ("a feature is rigid when
   the move reaches it and every one of its inputs is rigid too") is new and
   hand-written. Ask it the questions that have caught this class four times
   before: what does it do with a STRUCK feature in the chain, with a pick
   nested in a Pattern axis or Mirror plane dict, with a shared tool feeding
   two bodies, and with a `move` whose delta is zero. The same class of guard
   has twice shipped refusing correct geometry.
2. **`_result_feature` changed what "the result" means.** The status-bar
   volume, `measure`, the spec check and `_check_dangling` all read it.
   `tests/test_rebuild_cache.py` pinned the OLD answer and was deliberately
   changed. Check the new spine walk on a design whose tail is struck AND whose
   `input[0]` is itself struck.
3. **The doorbell is a server-side singleton.** One module-level `ARRIVAL` in
   `studio.py`, with a ten-minute staleness and a `POST /api/arrival/ack` that
   consumes it. Two tabs, two browsers, and a reload racing an ack are the
   cases to press. FastAPI runs sync endpoints in a threadpool, so this marker
   is shared mutable state across threads.
4. **`static/vendor/three/`** is 1.3 MB of third-party code now in the repo and
   on the import map. Confirm the add-ons import nothing but `three`, and that
   no code path still expects the CDN.
5. **The units label is half a feature by design.** §10 carries a new P2: the
   tool panels have `(mm)` hard-wired and read their boxes with no conversion,
   so switching to inches converts the readouts and not the inputs. That is
   known and filed - see the do-not-report list.

## Cleared by measurement - do not re-report

- **The scaled-body shell segfault is fenced, and the guard was proved to be
  what fences it.** At the filed t = 1.8 the wall guard refuses in 0.00 s with
  the kernel never asked; with `assert_wall_fits_every_lump` stubbed out, the
  same call kills the process with 0xC0000005 in 4 s. The §10 row is `done`.
  A test pins the kernel being untouched, not merely the wording.
- **The my-part-9 shell stall is open on purpose, and its leading candidate is
  rejected with numbers.** The stall band is not an interval in thickness
  (1.5 refuses, 1.6 stalls, 1.7 refuses, 2.5 stalls), so no bound monotone in
  `t` can fence it. The "refuse when a narrow face's offset vanishes" rule was
  built and measured out: a plain 60 x 40 x 12 plate with the same 0.6 mm rim
  chamfer shells soundly at the same 2.5 mm, so that rule would refuse correct
  work. The folder stays in `bugs/`.
- **The parameter half of the face-pick bug is not fixable at the resolver.**
  Thickening the plate from 10 to 14 mm flips the pick exactly as a move does
  (22800.0 mm3 where 18810.62 was asked). From a stored `(centre, normal)` the
  move case and the thicken case are arithmetically identical - candidates 1 mm
  and 4 mm away, one right, one wrong, and nothing stored says which body frame
  the pick was taken in. It needs the pick stored in the body's frame, which
  touches the viewport pick payload and every saved design. §10 carries it.
- **The `resolve_face` shared-centre tie refusal was built, then backed out.**
  A round pocket with a flush round pad gives two +Z faces whose centroids are
  both (0, 0, 10), so one pick describes both. The refusal broke
  `test_concentric_lumps_a_post_inside_a_ring_still_shell` - a shell the kernel
  builds perfectly, because Shell asks `resolve_face` once per lump and
  concentric lumps tie exactly. It is also not silent. Filed P2 for the
  pickers to close by saying which face they mean; a test pins the tie.
- **The user's 50 live designs are clean, and this was swept, not reasoned.**
  The three parallel streams were forbidden heavy runs, so the parent session
  ran `-m library` once after the merge: **101 passed**, every live design
  rebuilt. Beyond that sweep: the pick carry fires only when a `move` feature's
  x/y/z is edited, never on load, rebuild or save, and `resolve_face` itself
  changed by docstring only.
- **The favicon 404 in the browser console is pre-existing** and unrelated to
  this range.

## What was verified after the merge

Fast tier 1800 passed, library tier 101 passed. Ruff zero. ESLint zero. Server restarted and the page
loaded in a real browser at `ui v201`: the body draws (so the local three.js
works), the status bar ends in a dim `mm` chip, `/api/doc` carries
`arrival: null` so no phantom banner, and **zero network requests left the
machine** - the offline claim is measured, not assumed.
