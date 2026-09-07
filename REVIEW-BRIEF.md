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
| **Range** | `5ec2dc3..bc5a7ca` — ONE code commit, `bc5a7ca` |
| **Already reviewed** | everything up to `21429d8` (five rounds, 2026-09-06/07; every finding fixed or filed). `5ec2dc3` is the docs-only stamp |
| **Base of the whole Mirror change** | `023ca5d` (P4 Mirror as originally shipped) |
| **Effort** | medium is enough — this commit closes the LOW-priority leftovers of the earlier reviews; the tool is stamped done |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |

`bc5a7ca` closes the ~9 findings the earlier reviews deferred until after the
stamp: 7 fixed, the rest closed by decision (listed below — do not re-open
them, the reasons are in LAUNCH-PLAN.md §10 and specs/mirror.md decision 6).

## What changed, in one line each

- **pattern.py `_repeat`** — the fuse branch gained the cut branch's second
  sentence: an image that adds exactly 0.0 AND overlaps the seed "is the seed
  itself", otherwise "lies inside the body" (`probes/mirror_boss_seed_probe.py`).
- **toolplan.py `plan_mirror`** — a plane NAME that is none of the alternatives
  is refused with the names that exist; `"face"` / `"stored"` keep the current
  plane (they are the names the panel gives it when it is none of the
  alternatives — inserted AFTER this check, which is why they need the carve-out).
- **blocks.py `mirror_copy`** — `EXPORTS["mirror"]` delegates to
  `pattern.mirror(part, plane, join=join)` (lazy import: pattern → sketch →
  blocks); `_PLANES` and the b3d `mirror` import deleted.
- **viewport.js `loadModel`** — `if (originPlanes.length) buildOriginPlanes()`
  after the fit update, so the origin quads follow the body.
- **tree.js `buildBody`** — an object-valued param renders as `k v · k v`.
- **tool.js** — `st.lastGoodPlan` (set with `lastGood` from the plan captured
  at the start of `applyOnce`; for an edit, from the first plan while
  `lastGood` is the original), `spec.describe(params, st)`, and `okSession`
  reports a NEW feature that ended `failed` as NOT built with its first problem.
- **mirror.js** — `planeWords` deleted; `describe` reads `lastGoodPlan.plane_words`.
- **Tests** — 3 unit tests, 1 browser journey (first plane refused → OK says
  NOT built), 4 assertions in existing journeys (quad size grows after the
  body doubles — proven RED with the viewport line reverted; the tree shows
  `mid X`; the revert sentence carries the plan's words); one existing
  assertion flipped from "an unknown name changes nothing" to the refusal.

## Where the risk actually is — look hardest here

1. **`okSession`'s `failed` read.** It reads the feature from `feats()`
   (`S.lastDoc`) right after `await apply()`. If `S.lastDoc` can lag the
   response that carried the failure (a debounced apply, `applyRun`), the
   sentence could say "created" over a red row again, or "NOT built" over a
   green one. The journey covers the plain path only.
2. **`lastGoodPlan` and the race the comment above it names.** The plan is
   captured at the START of `applyOnce`, so it matches `pr`; but after a
   `settle` that typed milder values, `good = spec.params(st)` is re-read from
   the CURRENT plan while `lastGoodPlan` is the captured one. Mirror has no
   settle; say whether any tool with one (Fillet) can now describe a revert
   in the wrong plan's words. Cosmetic at worst — the params stay right.
3. **`_repeat`'s new branch.** `_overlaps(image, added)` runs only when the fuse
   added < 1e-9 mm³. Is there a fused image that overlaps the seed's material
   AND lies inside the body without being the seed itself? (A boss image
   overlapping half the boss adds material — so no; but say if you find one.)
4. **`mirror_copy`'s delegation.** Every older script called
   `mirror(part, "YZ")` positionally and got the copy; the sentences for a bad
   name now come from `pattern.plane_of` (still `ValueError`). Check nothing in
   `generate.py` / the Layer-1 prompt quoted the old sentence.
5. **`buildOriginPlanes` on every load.** It also fires for the SKETCH tool's
   plane pick (same `originPlanes`), and it resets hover opacity. Intended;
   say if a load can happen while `planePickCb` is set and break that pick.

## Ground rules for this repo (they change what counts as a finding)

- Geometry claims are proven by measurement, not by reading. If a finding is
  geometric, say what to measure; the probes under `probes/` are the pattern.
- "A failed feature beats a corrupt body" — a refusal with a sentence is
  correct behaviour, not a bug. Silently returning an invalid or non-manifold
  solid is the bug.
- A saved design may never STOP rebuilding, except where the geometry is
  genuinely broken (see the accepted risk in BACKLOG.md).
- Never re-derive a backend fact in the frontend (LAUNCH-PLAN.md R1).
- The fast tier is green (1149 passed) and the 8 Mirror browser journeys
  are green, so do not report anything a test run would have caught.
- Documentation and comments ARE reviewable here: they are the contract the
  next change reads. But a wording preference is not a finding.

## Already known — do NOT re-report

Closed BY DECISION in this round (LAUNCH-PLAN.md §10, specs/mirror.md decision 6):

- A body face wins a click over an origin quad behind it — the quads are glass
  through the model, sized past its silhouette; nearest-hit-wins was the
  earlier bug.
- The plan resolves a picked face through `pattern.plane_of` on purpose (the
  stored form must round-trip to what the op will build at rebuild).
- `delta()` runs once per plan and once per rebuild — a cache on the document
  is not worth its risk for one boolean.
- `snapshot`'s `?? null`, the shared `originPlanes` teardown (one owner at a
  time), `planeQuadInfo` echoing the handed frame.
- The body-pattern health gate is retroactive (BACKLOG.md, accepted risk).
- 5 pre-existing red browser tests in `tests/e2e/test_tree_delete.py`
  (LAUNCH-PLAN.md §10 P1, someone else's work).
- Pattern's drag ghost (§10 P3, deferred by the user).

## After the review

Bring the findings back to the work chat. Each one gets reproduced by
measurement, then a test that is RED before the fix, then the fix — never a
fix applied straight from the review (`--fix` skips that discipline).
