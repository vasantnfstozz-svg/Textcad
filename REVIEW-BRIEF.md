# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING** — Shell is CLOSED after three rounds
> (`fb0b8c8` built, `667ccc0` round one, `b99a24d` round two, `b5c6e70` round
> three). No P0 fell in round three, so the chain ends here.
>
> **The next `code review` goes to `REVIEW-QUEUE.md`** and takes the first
> status-board row marked TODO, which is **section 7 — Extrude as a whole
> module (with loft and sweep)**, priority medium.
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

## What closed, so the queue's section 11 does not re-derive it

Section 11 of `REVIEW-QUEUE.md` is **Tool framework core**, and the Shell chain
spent three rounds inside `tool.js`. When that row comes up, these are settled
and measured — do not re-report them, and do not re-measure them:

- **`replanNow`'s "keeps at least one edge" guard is gated on
  `st.input.kind === 'edges'`**, not on the key's name. That changes behaviour
  for Shell ALONE: only Fillet and Chamfer have kind `edges`, and only
  `plan_fillet` and `plan_shell` return an `edges` key at all.
- **`settle` restores `st.plan = st.lastGoodPlan`** so a param with no box of
  its own (Shell's face set, Mirror's plane) is not re-pushed from a stale
  plan. Without it, a refused face set looped revert → replan → refuse at a
  measured 50 rebuilds in 6 s.
- **`startPreview` clears `lastGood` and `lastGoodPlan`.** It has exactly two
  callers — `begin()` (both already null) and `changeProfile()` — and is a
  closure local, never exposed on `ctl`, so no spec hook can reach it. Edit
  mode goes straight to `setupTool` and is untouched.
- **`tree.js`'s `readable` / `namedParts` recursion has no depth cap and
  overflows the stack at depth ~5000.** REJECTED as a finding, measured:
  `JSON.stringify`, the branch it replaced, throws `RangeError` at EXACTLY the
  same depth, and threw a `TypeError` on a cycle where `readable` throws
  `RangeError`. Same failure through the same door; nothing was added. The
  longest row in the real library got SHORTER (my-part-8 `fillet1`: 567 chars
  against the old JSON's 607).

## What closed on the Shell op, for whoever touches `sketch.shell` next

Two guards now stand either side of the kernel, and they are siblings:

- `assert_every_lump_open` — BEFORE: on a body in several lumps, an opening on
  every lump or none at all. `offset(openings=[…])` shells only the lumps a
  listed face belongs to and hands back the raw offset solid for the rest.
- `assert_every_lump_hollowed` — AFTER, because only the kernel knows whether a
  wall fits: no result lump may be IDENTICAL to a lump that went in (same
  bounding box, same volume). Round two paired result lumps to input lumps by
  nearest bounding-box CENTRE and two CONCENTRIC lumps share a centre exactly,
  so it refused a shell the kernel had built perfectly. There is no pairing any
  more, and there should not be one.

Measured across the three rounds, so none of it needs re-deriving: an untouched
lump matches its input at d(volume) 0.0 and d(box) 0.0 (1.1e-13 at worst) while
a lump that really hollowed came no closer than 0.992 of its input, over 99
result lumps; no lump ever vanished over six extreme thicknesses; an OUTSIDE
shell never merged two lumps even at a 2 mm gap and t = 6;
`inspector.closed_shell` is effectively per-lump (an open-shell lump is caught
beside a healthy one exactly as it is alone); `.solids()`, `.volume` and
`.bounding_box()` never raise on a result and cost 5 ms for 24 calls against
the kernel's own 239 ms offset on a 12-lump body; the opening guard's
`_shape_key` match is exact through `linear_pattern`, `polar_pattern`,
`mirror`, a severed plate and an imported STEP.

The shared gauntlet corpus (`tests/gauntlet.py BODIES`) is **all one-lump
bodies** — that is how the same P0 got through two rounds. Shell's own gauntlet
now carries the multi-lump corner (four mixed pairs plus the concentric pair,
swept in both directions). **Any other op that eats a whole body deserves the
same corner**; there is a LAUNCH-PLAN §10 row for it.

## Ground rules (unchanged)

- Reproduce by measurement or a red test before fixing; kernel probes go under
  `probes/`. The gauntlet is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push, restart
  the user's server if the backend changed. Then the paperwork.
- Never `--fix`. One reviewer.

## Also open, and NOT the next review's job

`tests/e2e/test_tree_delete.py` is 5 red and was measured red at `667ccc0` in a
clean worktree, so it predates all of this. `tree.js deleteFeature` opens the
confirm only when `plan.deleted.length > 1` and the dialog never appears, so
the remove PLAN now takes ONE feature where it used to take the group. That is
the delete / strike-out workstream; LAUNCH-PLAN §10's browser-tier P1 row
carries it with the root cause narrowed.
