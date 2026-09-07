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
| **Range** | `5ec2dc3..a2f9663` — TWO code commits from two work sessions on the same day: `bc5a7ca` (Mirror's deferred findings) and `a2f9663` (two panel fixes in the tool framework and the shared angle ring). `5ec2dc3` is the docs-only Mirror stamp |
| **Already reviewed** | everything up to `21429d8` (five rounds, 2026-09-06/07; every finding fixed or filed) |
| **Base of the whole Mirror change** | `023ca5d` (P4 Mirror as originally shipped) |
| **Effort** | high — `a2f9663` changes a branch every tool runs through (`tool.js applyOnce`); for `bc5a7ca` medium would do (it closes LOW-priority leftovers; the tool is stamped done) |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |

Review the two commits separately — they touch different code and were
merged with one one-line conflict in `tool.js applyOnce` (both add a `const`
after `spec.params`; both lines were kept). Frontend `ui v165`.

## A. `bc5a7ca` — Mirror's deferred findings (7 fixed, 4 closed by decision)

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

### Where A's risk is

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

## B. `a2f9663` — two panel fixes the user hit (frontend only, no `.py` outside tests)

- **`static/js/viewport.js` — the angle ring snaps.** `taperDrag` keeps the
  raw, unwrapped turn in `taperRing.raw` (clamped by the tool's `clampFn`) and
  shows `snapAngle()` of it: whole degrees, and within `SNAP_BAND` (3°) of a
  multiple of `SNAP_STEP` (45°) that multiple, clamped again so a mark past the
  limit is unreachable; `|| 0` keeps a `-0` out. `taperGrab` seeds `raw` from
  the shown value. Typed values never pass through it. Used by Extrude's taper
  ring, Revolve and Circular Pattern.
- **`static/js/tool.js` — honest zero with a preview up.** `applyOnce`: when
  the values are empty (`spec.isEmpty`), a feature exists, `st.plan` is set and
  no `hold` claims the state, a create-mode session removes its preview
  (`unbuild`: combiner then feature — the same two removes Cancel's `teardown`
  now delegates to, GONE-safe) and runs `afterApply` so the handles sit at 0;
  an edit session HOLDS with a sentence built from
  `spec.describe(st.lastGood, st)`. Before, the 0 was pushed, the kernel
  refused it (`Standard_ConstructionError` for extrude, the op's own sentence
  for revolve — probed) and `settle` reverted the box to the last good value —
  the user saw 12 come back into the box they had just emptied.
- **Tests:** `tests/e2e/test_edit_extrude.py` +2 (create: 12 → 0 → preview
  gone, box "0", 8 → built, OK; edit: 0 keeps 12 with the sentence, Cancel
  restores); `tests/e2e/test_revolve_tool.py` ring drag asserts 37.3 → "37" and
  92 → 90 exactly.
- **Docs:** fusion-parity skill (rule 4 corollary, gizmo snap rule),
  LAUNCH-PLAN §10 (a done row, a P3 follow-up, a data point on the flaky ring test).

### Where B's risk is — look hardest here

1. **The `st.plan` guard in `applyOnce`.** Five tools fold "no plan yet" into
   `isEmpty` (revolve, hole, mirror, both patterns), so the empty branch runs
   only once `st.plan` is set; otherwise the OLD push path runs. Is there a
   state with a feature built and `st.plan` null that lasts longer than the
   plan request — after `changeProfile`, after a refused `replan`, after the
   server-recovered path? If so the old revert bug is still reachable there.
2. **`unbuild` inside a running apply.** It posts two removes from inside
   `holdViewport`; `doc-updated` from the first remove can re-enter `apply()`
   (coalesced into the burst). Confirm the second `applyOnce` pass cannot find
   `st.featureId` half-cleared, and that `/api/feature/remove` of the preview
   extrude never cascades to its SKETCH (Cancel has used the same two calls
   since P2, so this should be proven — say so if it is).
3. **The hold in edit mode says "the feature keeps X"** — X is
   `spec.describe(st.lastGood, st)`. `lastGood` is the original at open and the
   last VERIFIED values after a push; is there a path where `lastGood` is null
   in edit mode (a settle that reverted sets `good = null` but leaves
   `st.lastGood` alone)? A `TypeError` here would be swallowed into the apply
   burst and the box would silently stop applying. Mirror's `describe` now
   reads `st.lastGoodPlan` (commit A) — for an edit that is the first plan.
4. **Snap + clamp ordering.** `raw` is clamped, then the snapped value is
   clamped again. Extrude's `clampTaper` has side effects (`ensureCollapse`,
   the one-time apex sentence) — check that two calls per pointer move cannot
   double-fire the sentence or re-request the collapse depths.
5. **`hold` before `empty`.** A tool's own `hold` sentence wins over the
   generic empty handling (Hole's "unchanged until it has a depth" keeps its
   preview; Pattern's count 1 removes it). Say if any tool's `isEmpty` state
   should have been a hold, or the reverse.

## Ground rules for this repo (they change what counts as a finding)

- Geometry claims are proven by measurement, not by reading. If a finding is
  geometric, say what to measure; the probes under `probes/` are the pattern.
- "A failed feature beats a corrupt body" — a refusal with a sentence is
  correct behaviour, not a bug. Silently returning an invalid or non-manifold
  solid is the bug.
- A saved design may never STOP rebuilding, except where the geometry is
  genuinely broken (see the accepted risk in BACKLOG.md).
- Never re-derive a backend fact in the frontend (LAUNCH-PLAN.md R1). The snap
  is a UI interaction rule, not a geometric fact; the clamp values still come
  from the plan.
- The fast tier is green on both trees (1149 on `bc5a7ca`; 1146 on
  `a2f9663` before the merge, which has no `.py` change of its own); the
  R1/R2/R3 grep test plus the Extrude and Revolve journeys were re-run on the
  merged tree, the 8 Mirror journeys on `bc5a7ca`, the taper-ring and
  Pattern-ring journeys on `a2f9663`'s final ring code. Do not report anything
  a test run would have caught.
- Documentation and comments ARE reviewable here: they are the contract the
  next change reads. But a wording preference is not a finding.

## Already known — do NOT re-report

Closed BY DECISION in A (LAUNCH-PLAN.md §10, specs/mirror.md decision 6):

- A body face wins a click over an origin quad behind it — the quads are glass
  through the model, sized past its silhouette; nearest-hit-wins was the
  earlier bug.
- The plan resolves a picked face through `pattern.plane_of` on purpose (the
  stored form must round-trip to what the op will build at rebuild).
- `delta()` runs once per plan and once per rebuild — a cache on the document
  is not worth its risk for one boolean.
- `snapshot`'s `?? null`, the shared `originPlanes` teardown (one owner at a
  time), `planeQuadInfo` echoing the handed frame.

Filed or decided with B:

- **Five tools hand-type "a value typed before the plan arrived waits for
  it"** (LAUNCH-PLAN §10, P3) — the reason the `st.plan` guard exists. A
  framework-level plan wait is the fix; not this commit.
- In edit mode a 0 leaves the OLD solid on screen while the box says 0 (the
  hold design shared with Hole and Pattern; the sentence says so).
- Draft tapers of 1–3° are not reachable by DRAG on the ring (the 0 mark
  holds them) — type them; a decision, not a bug.
- `test_revolve_tool.py::test_open_from_the_tree_row_and_drag_the_ring` is
  order-dependent (red after other tool journeys, green alone — §10 P1, with
  today's data point); B's commit ran it alone.

Older:

- The body-pattern health gate is retroactive (BACKLOG.md, accepted risk).
- 5 pre-existing red browser tests in `tests/e2e/test_tree_delete.py`
  (LAUNCH-PLAN.md §10 P1, someone else's work).
- Pattern's drag ghost (§10 P3, deferred by the user).

## After the review

Bring the findings back to the work chat. Each one gets reproduced by
measurement, then a test that is RED before the fix, then the fix — never a
fix applied straight from the review (`--fix` skips that discipline).
