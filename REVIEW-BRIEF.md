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
| **Range** | `072aa95..21429d8` — only the newest commit is UNREVIEWED |
| **Already reviewed** | `9644b6d`, `c4d5961`, `85821be`, `072aa95` (all reviewed 2026-09-07; every finding dealt with — fixed in `072aa95` and `21429d8`, or filed in BACKLOG.md) |
| **Base of the whole Mirror change** | `023ca5d` (P4 Mirror as originally shipped) |
| **Effort** | high |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |

`21429d8` closes the three findings of the review OF `072aa95`, so review it
against `072aa95` and do not re-open what the earlier reviews passed.

**It changes no runtime behaviour.** The only `.py` edit outside tests and
probes is a docstring; there is no new branch, no new call, no changed
condition. So the useful questions are narrow — see below.

## What changed, in one line each

- **c4d5961 / 85821be / 072aa95** (reviewed) — the P0 silent-wrong-geometry
  work on Mirror: a PLACEMENT op folds to a BODY seed, `join` is planned only
  for a body seed, `_body_pattern` gained the health gate, error barriers on
  `pattern.delta` / `plane_of`, a bounded axis click, and finally: on an EDIT
  the stored `join` is honoured only while the stored params and the plan
  AGREE about whether there is a seed.
- **21429d8 (the one to review)** — the three findings of that last review,
  all "the contract does not match the code":
  1. `toolplan.plan_mirror`'s docstring stated the OLD `join` rule; it now
     states the real one (a NEW mirror joins only with no seed; an EDIT keeps
     the stored value only while stored params and plan agree there is a seed).
  2. `specs/mirror.md`'s **Edit** bullet promised the stored `join` is carried
     unconditionally; it is now conditional, with the measured cost of getting
     it wrong. Its **Tests** bullet names the guard too.
  3. `tests/test_mirror_tool.py`'s collapsed-seed test named TWO collapse
     paths and exercised one. The PLACEMENT path — a stored seed naming a
     `rotate` / `scale` / legacy copy-only mirror row, which folds to a BODY
     seed — is now guarded.
  New: `probes/mirror_seed_collapse_probe.py` (2 sections) measures both
  paths: of a 76460 mm³ plate the legacy COPY form left 0 mm³ and 5940 mm³
  where the body actually was; the JOIN form leaves all of it.

## Where the risk actually is — look hardest here

1. **Do the words now match the code?** Read `plan_mirror`'s docstring and the
   spec's Edit bullet against lines 1091–1093 of `toolplan.py` (the
   `stored_seed` / `keep_stored` / `join` triple). A contract
   that is subtly still wrong is the whole point of this commit; that is a
   finding, and "the docstring is fine" is a valid answer.
2. **Does the new guard actually guard?** It was measured RED with the
   `keep_stored` line reverted to `bool(s.fid)` and green with it. If the new
   block would still pass with the fix reverted, say so — a green regression
   test is worse than none.
3. **Is the new scenario's tree honest?** It stores `seed: "rot"` with
   `join: false` on a row whose input is that same `rotate`. If that
   combination cannot arise from any real path — the tool, the AI, an older
   saved design, a tree edit that re-folds a seed — the guard is pinning a
   fiction, and the REAL collapse path is unguarded. This is the finding worth
   the most here.
4. The collapse rule itself (`plan_mirror`'s `join`) and `_seed_plan`'s seed
   resolution remain the highest-risk code in Mirror: every P0 so far has been
   in the gap between what the tree STORED and what the plan DERIVED.

## Ground rules for this repo (they change what counts as a finding)

- Geometry claims are proven by measurement, not by reading. If a finding is
  geometric, say what to measure; the probes under `probes/` are the pattern.
- "A failed feature beats a corrupt body" — a refusal with a sentence is
  correct behaviour, not a bug. Silently returning an invalid or non-manifold
  solid is the bug.
- A saved design may never STOP rebuilding, except where the geometry is
  genuinely broken (see the accepted risk in BACKLOG.md).
- Never re-derive a backend fact in the frontend (LAUNCH-PLAN.md R1).
- The fast tier is green (1146 passed) and the browser tier for Mirror,
  Pattern and Hole is green, so do not report anything a test run would have
  caught.
- Documentation and comments ARE reviewable here: they are the contract the
  next change reads. But a wording preference is not a finding.

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
