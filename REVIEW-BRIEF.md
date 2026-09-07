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
| **Range** | `16ade36..HEAD` — THREE code commits from two work sessions: `753c24c` (A: the STEP export handed over one body of a multi-body design) and `4f15f66` + `9bed191` (B: Fillet picking — inside corners, lost clicks, and the Select-mode path). The rest are review handoffs |
| **Already reviewed** | everything up to `a2f9663` (Mirror, five rounds + the deferred findings, and the two panel fixes) |
| **Effort** | high — A is a P0 silent-wrong-geometry class: the artifact the user MACHINES FROM was wrong, and the change also moves the spec-verification target; B changes the picker every tool and Measure go through |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |
| **Frontend** | `ui v167` |

Review A and B separately — they touch different code (A: `document.py`,
`studio.py /api/export`, `mcp_server.py`, `dialogs.js`; B: `viewport.js`
picking, `tool.js replan`, `blocks.resolve_edge`, `studio._tagged_mesh`,
`toolplan.plan_fillet`). B was built on a branch and rebased onto A with no
code conflict.

## A. `753c24c` — the STEP export held one body of a multi-body design

### The bug, as reported and as measured

The user exported a design to STEP, opened it in another program, and "can
see only half part of design and rest of them are missing".

A Document legitimately has SEVERAL unconsumed leaf bodies —
`leaf_solid_ids()` returns all of them and `/api/model` renders all of them,
so the viewport showed the whole design. `to_step()` exported
`Document.result()`, which is ONE body: the tree's tail.

Measured on the user's own library (all 50 designs swept, 4 affected):

| design | bodies | old export | whole design | shipped |
|---|---|---|---|---|
| `my-part-6` | 4 | 585.6 mm³ | 424 161.3 mm³ | **0.1 %** |
| `esp32-remote` | 2 | 249.1 mm³ | 107 733.9 mm³ | **0.2 %** |
| `my-part-2` | 2 | 1 297 968.1 mm³ | 1 357 248.8 mm³ | 95.6 % |
| `my-part-5` | 3 | 413 262.9 mm³ | 414 625.4 mm³ | 99.7 % |

The `my-part-6` file was a 22×10×15 mm nub in place of a 200×143×88 mm part.

### What changed

**`document.py`**

- **`result_bodies()`** (new) — `leaf_solid_ids()` turned into parts. The one
  authority on "what is the design", so the viewport and the exporter cannot
  disagree. `result()` is the LAST of these and keeps its old meaning.
- **`result_shape()`** (new) — the whole design as one shape: a bare part when
  there is one body, a `b3d.Compound` when there are several. **Not fused** —
  bodies the user has not joined are not joined. Exporting and measuring share
  this so a file can never hold something other than what was reported.
- **`_export_blockers()`** — rewritten. Was: walk BACKWARDS from the tail,
  `break` at the first built solid. So (a) a failed branch sitting earlier than
  the tail was never seen, and (b) the test was `part is None` only, so a body
  that BUILT but failed its health check (empty solid, open shell) sailed
  through. Now: a forward pass over every unconsumed, active, non-sketch
  feature, blocking on a missing part OR `status != "ok"`.
- **`to_step()`** — exports `result_shape()`.
- **the spec check in `rebuild()`** — now `inspector.verify(self.result_shape())`
  instead of `self.result()`, and the spec cache signature spans EVERY leaf's
  signature instead of only the tail's.

**`studio.py`** `/api/export` also returns `is_valid`, `is_manifold` and
`bodies`, measured from the written file.

**`mcp_server.py`** `_report` measures `result_shape()`, adds `bodies`.

**`static/js/dialogs.js`** the export line says how many separate bodies are in
the file and warns if the kernel calls the geometry unsound. Every number is a
field on the response — nothing is recomputed in JS (R1).

### Where A's risk is

1. **`_export_blockers` is now stricter in two directions at once.** A design
   that used to export can now be REFUSED — by design ("a failed feature beats
   a corrupt body"), with the escape hatch being to strike the feature out.
   Worth checking: is there a legitimate document shape that this now refuses
   wrongly? The `sk.is_sketch(part)` skip is the guard for sketch-valued
   modifiers (a moved profile); a feature with NO part cannot be classified
   that way and is treated as a body. Is that the right call?
2. **The spec check moved target.** For a multi-body design the spec now
   describes the whole design, not the tail. On `esp32-remote` this replaced
   three bogus size errors with the one true complaint. No design in the
   library flips from fail to pass. But it IS a semantic change to the
   anti-hallucination guarantee — read `test_spec_is_checked_against_every_body`
   and `test_spec_cache_notices_a_change_to_a_body_that_is_not_the_tail` and
   say whether the cache key is now complete.
3. **`Compound(bodies)` vs fusing.** Proven in
   `probes/multibody_step_probe.py`: §2 the file reads back as N solids with
   the summed volume, §3 one body writes identically wrapped or bare, §4 the
   bodies stay exact BREP (all `PLANE` faces, no `BSPLINE`) through a
   round-trip, §5 touching bodies are NOT fused by the writer. Overlapping
   separate bodies double-count in the volume readback — judged pathological
   (the user would see two overlapping bodies in the viewport) and left alone.
4. **The deep `is_valid` pass in `rebuild()` still only sees the tail**
   (`document.py`, the `rf_deep` block). Deliberate: it costs ~270 ms per body
   on every rebuild, and the export readback now validates every body at export
   time instead. Say if you disagree — the trade is editing speed against
   catching an invalid non-tail body earlier than the export.

### A: do not re-report

- **`/api/mesh.stl` / `_ensure_mesh_file` use `result()`.** No caller anywhere
  in the tree; the viewport uses `/api/model`, which is per-body. Dead path.
- **`_doc_json`'s `result_pieces` is the tail feature's lump count.** Verified
  as guarded by checks that are live during a drag.
- **`mcp_server.build_design` / `design_part` export one body.** Both call
  `to_step`; they carry no export logic of their own and are fixed by it.
- **`mcp_server.py:212` (the compressor) exports `build.part`.** Not a
  Document — single-part path, unaffected.
- **`measure.py`, `provenance.py`, `toolplan.py` use `result()`.** Not audited
  as part of this change; they are tool-target concerns, not export. Out of
  scope on purpose, not an oversight — flag them as new findings if you think
  they carry the same defect.
- **`test_export_lands_in_designs_and_is_measured` asserts `n_solids == 1`.**
  Correct: `sample_flange()` is a linear chain with exactly one leaf.

### A: proof

- Fast tier green (1157 passed before the last two commits' worth of changes;
  re-run at ship).
- 10 new tests in `tests/test_export_guard.py` — every one of them written RED
  first and confirmed to fail for the right reason (`n_solids == 1`).
- `probes/multibody_step_probe.py` — 7 sections, all measured, incl. §6 which
  exports the user's real `my-part-6` whole.
- Live server smoke test through the real HTTP API: `POST /api/open/my-part-6`
  then `POST /api/export` returns `n_solids 4, volume 424161.33,
  size [200.625, 143.442, 88.284], is_valid true, is_manifold true`.
- Line delta: +370 / −38 across 6 files (of which +235 is tests), plus a
  130-line probe. This one ADDS more than it deletes — a bug fix, not a phase.

## B. `4f15f66` + `9bed191` — Fillet picking: inside corners, lost clicks, Select mode

Two user-reported bugs (2026-09-07, an isogrid panel: a grid of triangular
pockets), and a third the user found while testing the fix.

1. **No inside-corner edge could be picked.** `viewport.edgeHitAt` refused an
   edge whenever ANY face was a hair nearer than the line. The two walls that
   meet at an inside corner always are, from every viewing angle, so every
   concave edge was unpickable. Now: the server names the faces each edge
   bounds (`studio._tagged_mesh`, `edges[i].faces`, read off the ancestor map
   `_edge_polylines` already builds — a separate `face.edges()` pass cost 10%
   of the esp32 mesh, `probes/tagged_mesh_hosts_timing_probe.py`), and a face
   in front does not hide an edge when it is one of that edge's own faces AND
   was hit within 4 pick-widths of the line (`viewport.ownFaceHit`).
2. **A click sometimes did not select.** `tool.replan` requests could overlap;
   each carries the picks the previous ANSWER settled, so the later request
   went out without the earlier click and, landing last, won. Now one plan
   request at a time (`planChain`); the rebuild a plan triggers is no longer
   awaited inside `replanNow` (apply() already coalesces bursts).
3. **A raw pick resolves by "lies on the edge"**, not nearest midpoint
   (`blocks._edge_under` / `_edge_distance`: Extrema_ExtPC bounded by the
   ends, `probes/edge_point_distance_probe.py`, 75 µs a pair). While the
   preview is up the lines on screen are the ROUNDED body's: its trimmed
   neighbours lie exactly on their parents; its own new rims lie on no edge of
   the input body and are now refused with a sentence. Before, a rim click
   resolved to the edge it replaced and silently un-picked it.
4. **The plan says whether a click added or removed** (`click`), and the tool
   says it in the chat when a click RELEASED edges (with Chain on, one click
   on a picked smooth rim releases the whole rim, which looked like a refusal).
5. **`9bed191` — Select mode had its own copy of the old rule** (`pickAt`), so
   after 1. an inside upright edge still selected the WALL when clicked outside
   the Fillet panel — and select-then-command never saw the edge. Both pickers
   now share `viewport.visibleEdgeHit`, which also takes the first VISIBLE edge
   hit rather than the nearest one.

Tests: `tests/test_fillet_tool.py` +3, `tests/test_mesh_pipeline.py` +1 (all
four measured RED with `blocks.py` / `studio.py` / `toolplan.py` stashed),
`tests/e2e/test_fillet_tool.py` +2 (a pocket's floor rim and an upright corner
picked and rounded — the volume GROWS, the kernel's number; an inside edge
selected in Select mode enters Fillet as its first click). `click_edge` in that
file now waits for the plan's answer (the gold count changing, up to 3 s)
instead of a fixed 700 ms.

### Where B's risk is — look hardest here

1. **`ownFaceHit`'s two conditions.** "Own face" alone would let a cylinder's
   hidden BACK seam be picked through its front (own face, far behind), hence
   the `<= 4 * reach` distance guard. Is there a real view where a legitimate
   inside corner fails it (a wall seen at a grazing angle: the face hit runs
   away along the wall), or where a hidden edge passes it (a wall thinner than
   4 pick-widths at a zoomed-out view)? A finding here must name the view and
   the geometry; both are judgement calls, and the old rule was wrong for the
   entire concave half of every solid.
2. **`visibleEdgeHit` takes the first VISIBLE hit, not the nearest.** In
   `pickAt` the sketch-profile tie test still compares against `eHits[0]` (the
   nearest edge, visible or not). Can a hidden nearer edge now steal a tie from
   a coplanar profile, or the other way round?
3. **`_edge_under`'s tolerance** (`PICK_ON_EDGE_TOL = 0.05` mm). A round with
   a radius under 0.05 mm would have its rims resolve onto the edge again. Is
   there any OTHER producer of raw `points` picks whose points do NOT lie on
   the input body's edges within 0.05 — e.g. a body shown in mesh mode
   (imported STL: `faces` is `[]` and the points are triangle edges)? The
   fillet op does not apply to those, but the resolver is shared: check
   `blocks.edges_for` callers.
4. **`replanNow` no longer awaits `apply()`.** Every caller of `replan` was
   checked for awaiting its result (`fillet.js` chain box, `mirror.js`
   `refresh` / `onRepick`, `pattern.js` `onRepick`, `tool.js` 559 / 567 / 570):
   none does. But look at `okSession` / `cancelSession` — a click's plan still
   in the chain when OK or Cancel runs adopts its plan after `hide()` nulled
   `st`; the `st !== mine` guard is what stops it. Is there a path where the
   guard is not enough (e.g. `adoptPlan` on a session that was re-opened)?
   And: `applyOnce` (a2f9663) runs `unbuild` for an empty state — with the
   un-awaited `apply()` from a click's plan, can a click and an emptied box
   interleave so that `unbuild` removes a feature the click's plan is about?
5. **Performance of the resolver.** `_edge_under` walks every edge of the
   input body per click (600 edges: ~45–135 ms measured, with the type filter
   and the early exit). `_tagged_mesh` gained the `faces` field at ~0 cost
   (the ancestor map was already built; the rejected separate pass was 10%).
   `_edge_polylines` now returns a tuple; its only caller is `_tagged_mesh`; a
   seam edge's face is listed once (`dict.fromkeys`).

### B: proof

- Fast tier 1150 green before the rebase (the rebase had no code conflict;
  the fillet, mesh, model and Mirror unit tests were re-run on the rebased tree).
- Browser: fillet 8/8, measure picks 3/3 (Measure uses `pickAt`), hole,
  mirror, extrude-direction and edit-extrude green.
  `tests/e2e/test_pattern_tool.py::test_edit_reopens_on_the_stored_values_and_cancel_restores`
  failed ONCE in a 5-file run and passed 3/3 alone — its last assertion reads
  the modal lock right after the server shows the restored volume, while the
  browser still awaits `releaseIso()` before `releaseModal()` (a pre-existing
  race, not on B's path).
- Line delta (B, source): +140 / −20; tests +160 / −2. A fix — nothing to delete.

## Ground rules for this repo (they change what counts as a finding)

- Geometry claims are proven by measurement, not by reading. If a finding is
  geometric, say what to measure; the probes under `probes/` are the pattern.
- "A failed feature beats a corrupt body" — a refusal with a sentence is
  correct behaviour, not a bug. Silently returning an invalid or non-manifold
  solid is the bug.
- A saved design may never STOP rebuilding, except where the geometry is
  genuinely broken (see the accepted risk in BACKLOG.md).
- Never re-derive a backend fact in the frontend (LAUNCH-PLAN.md R1). The
  picker's occlusion test is viewport hit-testing; the TOPOLOGY it uses (which
  faces an edge bounds) comes from the server. Every export number is a field
  on the response.
- Do not report anything a test run would have caught.
- Documentation and comments ARE reviewable here: they are the contract the
  next change reads. But a wording preference is not a finding.

## Already known — do NOT re-report

- A's list above; the pattern edit/cancel race above (a `wait_for_function` on
  the modal lock would fix the test).
- Picking on a mesh-mode (imported STL) body keeps the OLD occlusion rule
  (`faces` is empty there): those bodies cannot be filleted anyway.
- Five tools hand-type "a value typed before the plan arrived waits for it"
  (LAUNCH-PLAN §10, P3); `test_revolve_tool.py::test_open_from_the_tree_row_and_drag_the_ring`
  is order-dependent (§10 P1).
- The body-pattern health gate is retroactive (BACKLOG.md, accepted risk).
- 5 pre-existing red browser tests in `tests/e2e/test_tree_delete.py`
  (LAUNCH-PLAN.md §10 P1, someone else's work).
- Pattern's drag ghost (§10 P3, deferred by the user).

## After the review

Bring the findings back to the work chat. Each one gets reproduced by
measurement, then a test that is RED before the fix, then the fix — never a
fix applied straight from the review (`--fix` skips that discipline).
