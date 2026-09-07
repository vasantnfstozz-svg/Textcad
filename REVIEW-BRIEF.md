# REVIEW-BRIEF.md — what the next code review should look at

> **How this file works.** It is written fresh at the end of every work
> session, right after the code commit, and it is always about ONE review. It
> is not a log: the previous contents are REPLACED, so the file stays short
> and the review chat pays for one small read instead of re-deriving three
> commits of context. Ship-check step 6 refreshes it.
>
> **In the review chat, type exactly this and nothing else:**
>
> ```
> /code-review high — read REVIEW-BRIEF.md first: it names the commit range, the base, and what not to re-report
> ```
>
> That line never changes. Everything specific to today is below, which is
> why the line can stay the same forever.

---

## Review this

| | |
|---|---|
| **Range** | `85821be..072aa95` — only the newest commit is UNREVIEWED |
| **Already reviewed** | `9644b6d`, `c4d5961`, `85821be` (reviewed 2026-09-07; both findings dealt with — one fixed in `072aa95`, one filed in BACKLOG.md) |
| **Base of the whole Mirror change** | `023ca5d` (P4 Mirror as originally shipped) |
| **Effort** | high |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |

`072aa95` is a fix TO the reviewed work, so review it against `85821be` and do
not re-open what the last review already passed.

## What changed, in one line each

- **9644b6d** — the 5 findings of the first review of Mirror: the clicked
  plane is matched by PLANE not nearest centre, the revert records what the
  kernel VERIFIED, `image & removed` got its own guard, the re-pick knows
  `planes`, the blank Plane option cannot read "no plane" over a built mirror.
- **c4d5961** — the 4 P0 silent-wrong-geometry findings of the big review: a
  PLACEMENT op (rotate / scale / legacy copy-only mirror) folds to a BODY
  seed instead of a whole-body "delta"; `join` is planned only for a body
  seed; `_body_pattern` gained the `inspector.health` gate; a body seed is not
  offered its own mid-planes, and the AI prompt + catalogue were corrected.
- **85821be** — the 2 follow-ups: `pattern.delta` and `plane_of`'s face
  reading carry error barriers so no raw kernel exception reaches the tree,
  and `toolplan._axis_face` bounds a pattern's axis click.
- **072aa95 (the one to review)** — the P0 the last review found: on an EDIT
  the stored `join` is honoured only while the stored params and the plan
  agree about whether there IS a seed. When they disagree the stored seed has
  stopped resolving, so `join: False` means nothing and the plan fell back to
  the legacy COPY form, relocating the body 80 mm with zero overlap.

## Where the risk actually is — look hardest here

1. `toolplan.plan_mirror`'s `join` decision and `_seed_plan`'s seed
   resolution. Every P0 so far has been in the gap between what the tree
   STORED and what the plan DERIVED. Ask of any new combination: if the seed
   stops resolving, does the plan turn a feature mirror into something that
   moves or deletes the body?
2. `document.delta_features`. It is the one folding rule three tools share, so
   a wrong answer there is wrong geometry in all of them.
3. Anything that can refuse at REBUILD. A refusal that fires on a design saved
   by an older build breaks a file the user already owns.

## Ground rules for this repo (they change what counts as a finding)

- Geometry claims are proven by measurement, not by reading. If a finding is
  geometric, say what to measure; the probes under `probes/` are the pattern.
- "A failed feature beats a corrupt body" — a refusal with a sentence is
  correct behaviour, not a bug. Silently returning an invalid or non-manifold
  solid is the bug.
- A saved design may never STOP rebuilding, except where the geometry is
  genuinely broken (see the accepted risk in BACKLOG.md).
- Never re-derive a backend fact in the frontend (LAUNCH-PLAN.md R1).
- The fast tier is green and the browser tier for Mirror, Pattern and Hole is
  green, so do not report anything a test run would have caught.

## Already known — do NOT re-report

Filed and deliberately deferred until after Mirror is stamped:

- `blocks.EXPORTS` still maps `mirror` to `mirror_copy`, so the AI's script
  path has the old copy-only grammar while the feature tree has the new one.
- An unknown plane NAME sent to `plan_mirror` is ignored in silence.
- The origin-plane quads are built once when the pick starts and never
  rebuilt, so they keep the old size and centre after the body changes.
- A body face wins a click over an origin quad behind it, so a quad the part
  covers cannot be clicked.
- `tree.js` renders an object-shaped plane as `[object Object]`.
- `mirror.js` derives the plane words in JS instead of using the plan's
  `plane_words` (an R1 violation).
- A boss whose mirror plane runs through it gets the cut branch's remedy
  ("adds nothing") instead of "is the seed itself".
- The perf / R10 cleanups: the picked face is resolved three times per click,
  `delta()` is computed in both the plan and the rebuild, a fourth
  world-axis table.
- The body-pattern health gate is retroactive with no grandfathering
  (BACKLOG.md, accepted risk, measured clean against every live design).
- 5 pre-existing red browser tests in `tests/e2e/test_tree_delete.py`
  (LAUNCH-PLAN.md §10 P1, someone else's work).

## After the review

Bring the findings back to the work chat. Each one gets reproduced by
measurement, then a test that is RED before the fix, then the fix — never a
fix applied straight from the review (`--fix` skips that discipline).
