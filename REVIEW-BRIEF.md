# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
> **A rewrite must carry over every PENDING range it did not review** - this
> brief exists because one did not.
>
> **Status: PENDING** - review `fbc3a50..e96ceb7` (three commits, all built
> on 2026-09-24 in one chat at the user's request). Nothing else is pending:
> `1294f7a` was reviewed and fixed at `23a7b4c`, and `REVIEW-QUEUE.md` is
> empty.

## The commits (base `fbc3a50`)

- `3b26057` Quieter screen. The face pick box shows "Face N" and its size
  rows only (area only when a face has no other size); an edge shows its
  diameter and length; a profile its name. The status bar keeps only
  "Report a bug" and "ui vN". Sketch mode lost its mouse legend, every
  per-tool click hint, the chat tip on entering, and "Esc cancel / Del
  delete". Frontend only, +68 -163.
- `a3f5427` Face sketches no longer DRAW the model's snap points (corners,
  edge midpoints, arc and hole centres, design and sketch centre); they
  still snap. Every remaining sketch marker is sized from `snapTol3d`
  (12 px in plane mm) with no millimetre floor, so none grows on zoom-in.
  +9 -26.
- `e96ceb7` Deleted the Flange / Impeller / Compressor examples: samples.py,
  meanline.py, impeller.py, `/api/sample/{name}`, MCP `design_compressor`,
  the `curved_blade` op, and their tests. Turn profile, Sphere, Cone and
  Polygon lost their ribbon buttons; their ops still build. +129 -2885.

## Where the risk is

- **A deleted op or route still named somewhere.** The sweep at commit time
  found none in code; the author prompt, `document.CREATORS`,
  `blocks.EXPORTS`, the self-test, icons and the ribbon were all edited.
  Check `author.op_catalog` and the AI's validation gates list nothing
  that no longer exists.
- **Old session files.** A tab restored with source `sample:<name>` is now
  treated like an untitled design (`studio._dirty`: dirty while it holds
  features). `test_a_restored_tab_from_a_retired_sample_reads_dirty` holds
  it. Is there any other reader of a `sample:` source?
- **Saved designs.** None of the 47 `designs/*.tcad.json`, their
  `.history/` versions or `tests/fixtures/` uses `curved_blade` (grepped).
  `revolve_profile` is used by thread-case, bottle_cap_28mm and
  water_bottle_750ml and was KEPT.
- **Snap without dots.** `sketcher.draw3D` no longer pushes `modelSnaps`,
  face hole centres or the sketch centre into `dots`; `collectSnapPoints`
  and `smartSnap` are unchanged. The orange cross is the only sign of a
  model snap now.
- **`sketcher.updateHint`** (commit 1) is tiny: the edge-on warning (kept,
  because clicks are refused while `edgeOnView`) and the path tool's
  Line/Arc switch.
- `settings.js` lost `paintUnit`; `paintUnitLabels` runs at init and on
  `settings-changed`.

## Ground rules

- The user chose what each box and bar shows and what to delete; do not
  report a removed row, button or example as a lost feature. Something
  that was load-bearing (a test, a debugging recipe, a failure that must
  speak, a design that no longer opens) is a real finding.
- Proven by the fast tier (see the commit), the browser tests of the
  changed UI (`test_camera_zup`, `test_bodies_visible`,
  `test_tool_panel_units`, `test_new_panel_units`, `test_user_workflow`,
  `test_face_to_feature`, `test_small_face_and_fold`, `test_tool_panel_dock`,
  `test_zoom_limits`, `test_doorbell`, `test_examples_tab`,
  `test_face_sketch_in_viewport`, `test_model_snap`) and one headless
  screenshot pass.

## Do not re-report

- The "Sketch on this face" button stays in the pick box (an action, not
  information).
- The other tools' pick prompts (Extrude, Fillet, Create Sketch's "Select a
  plane...", placement) and the chat's welcome message still speak; the
  user kept the welcome text when asked.
- `plOffset` joining `LENGTH_BOXES` in `test_new_panel_units.py`: that test
  was red before commit 1 (Offset Plane added the box without listing it).
- `placement.js` keeps an empty-in-practice `COUNTS` set on purpose, so a
  count param added later is not read through the length unit.
- `blocks._numbers` stays: `scale` uses it too.
- The pick box staying open when a sketch starts is older than this range.

**How the review starts.** The user opens a fresh chat on Opus
(`/model claude-opus-5-5[1m]`) and types only `code review`. CLAUDE.md's
section "The review chat" tells that chat to read this status line: PENDING
means review the range named here; NOTHING PENDING means go to the queue.
