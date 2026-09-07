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
| **Range** | `6e6f3fe..HEAD` — ONE code commit: the six findings of the review of `16ade36..6e6f3fe` (A the STEP export, B fillet picking, C the edge-group chips), each reproduced first and each with a test that was RED before the fix |
| **Already reviewed** | everything up to `6e6f3fe`. The four code commits in it were reviewed and this commit is the answer — **do not re-review them** |
| **Effort** | high — two of the six change code every tool goes through (`tool.js replan`, `viewport.js` picking) and one changes what `rebuild()` calls a failure |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |
| **Frontend** | `ui v169` (css unchanged at v39) |

This commit is a review answer, so the useful question is not "is there a bug
in the old code" — that review already happened. It is **"is each fix the
right fix, and does it break something the old behaviour was holding up?"**

## The six, and where each one's risk is

### 1. `tool.js replan` — the session is bound at click time

`replan()` now captures `st` when the click happens and passes it to
`replanNow(extra, mine)`, which returns early if `st !== mine`. Before, `mine`
was bound after the queue wait.

**Look at:** every caller of `replan` (`fillet.js` chain box + 6 chips,
`pattern.js` axis re-pick + Along box, `mirror.js` plane pick / box / refresh,
`tool.js` onEdgePick and line 600). Is there a caller that *relies* on a
queued plan running against a session opened later? I could not find one — a
plan describes the session it was made in — but that is the regression this
change could cause, and it would show as "the panel stopped updating".

**Proof:** `tests/e2e/test_fillet_tool.py::test_a_queued_chip_click_belongs_to_the_session_it_was_made_in`.
Red before: 4 gold edges appeared in a session that picked nothing. The test
delays `/api/tool/plan` **in the browser** (a `window.fetch` wrapper) rather
than in the driver, so the driver stays free to click while one is in flight —
that is the only way to queue a second request on purpose. If you think that
is fragile, say so.

### 2. `document.to_step` / `studio.py /api/export` — `Document.exported_bodies`

`to_step` records `len(result_bodies())` **inside** the try, while the rollback
bar is released, and resets it to 0 on entry. `/api/export` echoes that instead
of counting after the call.

**Look at:** a new mutable field on `Document` (`exported_bodies`). It is reset
at the top of `to_step` so a failed export cannot leave a stale count, and
`/api/export` returns `{"error": …}` on failure before reading it. Is there a
path that reads it without an export having happened (it would read 0)? Should
it have been the file's own `n_solids` instead — one number, measured, no
state? I kept them separate on purpose: `n_solids` is solids in the FILE,
`bodies` is bodies of the DESIGN, and the sentence offers "join them with
Extrude's Join", which is advice about features.

### 3. `toolplan._toggle_set` — compares the chain-expanded picks

Now takes `chain` and calls `_expand(part, [r], chain)` per ref; the chain
default moved ABOVE the chip block in `plan_fillet` (it does not depend on
anything in between). Removal drops any pick whose chain reaches into the set,
and reports the number of EDGES released.

**Look hardest here.** Two things: (a) **cost** — the add path is one `_expand`
over all refs (as before), but the remove path is one per ref, and
`blocks.tangent_chain` rebuilds an end-point map over every edge of the body on
every call. On esp32-remote (609 edges) with a dozen picks that could be slow;
I did not measure it. (b) does dropping a whole pick whose chain merely
*touches* the group release edges outside the group? Yes, deliberately — it is
the rule a single click already follows (`_toggle_pick`), and the browser says
"the click released N edges". Is that the right call for a chip?

### 4. `blocks.edge_side` / `edge_direction` / `edge_groups` — guarded per edge

All the geometry in `edge_side` is inside the try now (was: the normals only),
`edge_direction` returns `"other"` on a refusal, and the `edge_groups` loop
skips an edge whose classification raises — including `_shape_key`.

**Look at:** three bare `except Exception` blocks that swallow silently. The
alternative is a panel that will not open, which is worse, but nothing is
reported anywhere. Should a skipped edge leave a note? Also: `_edge_faces` is
NOT guarded — it was in the path before the chips, so its exposure is
unchanged, but say so if you disagree.

### 5. `viewport.ownFaceHit` — the bound is 2× the reach, not 4×

**This one contradicts the last review, and it was settled by measurement.**
The previous review called `4 * reach` a pixel/world unit mix-up and proposed
comparing in pixels. `probes/own_face_reach_probe.py` (new, 853 samples on a
pocketed box: 3 zooms × 3 directions × 6 click offsets, through
`__vp.edgeHitReport`) found:

- a **pixel** bound guards nothing: every own-face hit is inside the 5 px pick
  threshold by construction (max 4.02 px of 853), because both points sit on
  the click ray. The proposed fix would have made the escape unconditional.
- the world bound is right in KIND (the click tolerance really is a world
  length that grows with zoom) and 4× too loose: a legitimate click's face hit
  lands within 1.1× the reach (p90), 1.5× at worst, while 4× at a 400 mm view
  is 11.5 mm — and a **dead-centre** click was measured selecting an edge whose
  line is 10.0 mm behind the face in front of it.

**Look at:** is 2× enough margin? The measured worst legitimate case is 1.5×
(a 4 px offset at a 60 mm view). Everything I sampled was a pocketed box; a
large curved body could differ. And `__vp.edgeHitReport` is new production
code that exists only for the probe and the test — the same kind of hook as
`edgeScreen` / `pickAtWorld`, but say if it should not ship.

**Proof:** `test_a_face_hit_far_from_the_line_is_not_beside_it` drives the real
rule (`beside` comes from `ownFaceHit` itself, not a copy of it) and asserts
nothing 6 mm from the line is "beside" it. All 11 fillet journeys pass,
including both inside-corner ones the user hand-tested.

### 6. `document.rebuild` — every body is deep-checked, verdict cached

Was: OCCT validity on `_result_feature()` (the tail) only. Now: on every
`leaf_solid_ids()` body, memoised in `_valid_cache` keyed on the same content
signature the part cache uses, bounded by `CACHE_MAX`. `_deep_valid` is a new
module-level function so a test can stand in for it.

**Look at:** (a) the cache — the signature is the same one `_cache` uses, so a
different body cannot collide, but check that reasoning. (b) this can turn a
body that was green RED, which then blocks the export. I swept the user's whole
library: **51 designs, 0 with a body OCCT calls invalid**, and second rebuilds
~0.0 s. (c) `_valid_cache` is per-Document while `_cache` is shared across
documents — deliberate (it is small and per-design), or an inconsistency?

## Ground rules for this repo (they change what counts as a finding)

- **Never re-derive a backend fact in the frontend.** Axis, origin, frame, safe
  range, target body, edge groups: a field on a server response, never JS math.
- **A failed feature beats a corrupt body.** A kernel exception reaching the
  user and a "successful" invalid solid are both banned. OCP errors derive
  from `Exception`, not `RuntimeError`.
- **Geometry claims are measured, not reasoned about.** If you think a number
  is wrong, say what to measure. A finding that rests on reading the code
  alone, in a place where a probe exists, will be measured before it is fixed.
- Comments carry the user's own words and the date a bug was seen; they are
  the repo's memory, not clutter.

## Already known — do NOT re-report

- Everything in `16ade36..6e6f3fe` that this commit does not touch: that review
  is closed. In particular the picking-on-mesh-mode-bodies note, the pattern
  edit/cancel race, and the retroactive body-pattern health gate.
- The proposed pixel-space fix for `ownFaceHit` (finding 5) — measured and
  rejected, with the numbers above. Re-propose it only with a measurement.
- Five tools hand-type "a value typed before the plan arrived waits for it"
  (LAUNCH-PLAN §10, P3).
- `test_revolve_tool.py::test_open_from_the_tree_row_and_drag_the_ring` is
  order-dependent (§10 P1): it passes in its own file, fails after its
  neighbours. Pre-existing.
- 5 pre-existing red browser tests in `tests/e2e/test_tree_delete.py` (§10 P1,
  someone else's work).
- Pattern's drag ghost (§10 P3, deferred by the user).
- `designs/esp32-remote` reports a spec mismatch (36 solids vs `n_solids: 1`).
  That is 753c24c's spec-target change and an improvement on what it replaced;
  the spec is the user's to update, not the code's.

## After the review

Bring the findings back to the work chat. Each one gets reproduced by
measurement, then a test that is RED before the fix, then the fix — never a
fix applied straight from the review (`--fix` skips that discipline).
