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
| **Range** | `16ade36..HEAD` — ONE code commit: the STEP export handed over one body of a multi-body design |
| **Already reviewed** | everything up to `a2f9663` (Mirror, five rounds + the deferred findings, and the two panel fixes) |
| **Effort** | high — this is a P0 silent-wrong-geometry class: the artifact the user MACHINES FROM was wrong, and the change also moves the spec-verification target |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |
| **Frontend** | `ui v166` |

## The bug, as reported and as measured

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

## What changed

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

## Where the risk is

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

## Do not re-report

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

## Proof

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
