# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
> **A rewrite must carry over every PENDING range it did not review** - this
> brief exists because one did not.
>
> **Status: PENDING** - review `fbc3a50..2b71fff`: FIVE code commits in two
> groups. Group A (`3b26057`, `a3f5427`, `e96ceb7`, `58ab54f`, all built on
> 2026-09-24) is CARRIED OVER unreviewed from the previous brief. Group B is
> `2b71fff` (2026-09-29, the done-checklist judge). `ca4a635` and `85f31e7`
> in the range are brief rewrites. Nothing else is pending: `1294f7a` was
> reviewed and fixed at `23a7b4c`, and `REVIEW-QUEUE.md` is empty.

## Group B - `2b71fff` the done-checklist (base `85f31e7`)

New: `judge.py` (fail-open client for TypeSafe's Jev "system one" API),
`tests/test_judge.py` (13 tests), `probes/openjev_laya.py` (the measured
numbers). Changed: `author.py` +138 -7 - the step protocol's first reply may
carry `"plan": [...]`; `_plan_items`, `_feature_words`, `_tree_words`,
`_checklist_missing`; `author_steps` reads "done" against the plan BEFORE
`_apply_step`, refuses it at most `CHECKLIST_CAP`=2 times, only while
`steps_left >= 2`, never as a counted failure (`soft`), and past the cap
appends "Checklist could not confirm: ..." to the done line. The judge is
OpenRouter's hosted Jev when `OPENROUTER_API_KEY` exists (the key the design
model already uses), else `127.0.0.1:8080`; `TEXTCAD_JUDGE=0` disables it.

Two live jobs ran through `/api/chat`: the first reached "done" and the
checklist refused it (rightly wired, wrongly judged - see the commit: the
plan item carried a size the summary did not show; fixed and reproduced
through the judge at 0.37 -> 0.97). The second gave up on `linear_pattern`
after three kernel refusals and never reached "done".

### Where the risk is (group B)

- **A guess must never cost a verified design.** Check the three guards:
  `soft` refusals do not touch `fails`; `checks < CHECKLIST_CAP`; and the
  gate is skipped when `steps_left < 2`. Is there any path where a checklist
  refusal, combined with the model's own refusals, gives up an "add" job
  (which restores the snapshot) that would otherwise have finished?
- **The gate runs before `_apply_step`**, so a refused "done" never wrote a
  spec and never rebuilt - confirm nothing in `_apply_step`'s done branch
  was relied on for the refusal text, and that a done step carrying an
  "add" as well (the two-acts case) is still refused by `_apply_step`, not
  passed by the gate.
- **`_tree_words` is what the judge sees.** Sketch entity sizes now ride
  along (rectangle w×h, circle r, slot length); a plan element the model
  phrases in words the tree does not use (an id like `cut3`) will read
  "missing" and cost two soft refusals. Is the prompt's "no sizes" rule and
  the "(exact sizes do not matter)" question enough, or should ids be
  required to be descriptive?
- **judge.py fails open on `URLError`, `OSError`, `ValueError`, `TypeError`,
  `KeyError`** and goes quiet for 30 s after one failure. A non-JSON 200
  body is a `ValueError` (caught). An HTTP 401/429 from OpenRouter is an
  `HTTPError` (a `URLError`, caught) - the checklist silently vanishes for
  30 s at a time. Should a bad key be surfaced once in the job log?
- **The key lookup copies `studio._user_env`** (registry read at import).
  `judge.URL` and `judge.KEY` are module constants: a key set after the
  server started is not seen until restart - same as the design model's.
- **Cost and privacy.** ~500 input tokens a call at $0.042 per million, one
  or two calls per job. The tree summary (ids, ops, faces, sizes, the
  request) goes to OpenRouter - the same service that receives the full
  tree JSON on every chat message via `chat_intent`. No geometry, no files.
- **R10 delta.** This commit ADDS: author.py +138 -7, plus 461 new lines
  of client, tests and probe. Nothing was deleted. Recorded, not hidden.

### Ground rules (group B)

- The judge is a text judge by design; "it cannot tell the camera opening
  is in the wrong place" is the documented limit, not a finding. A finding
  is a way the judge's guess changes the geometry the user gets, loses
  work, loops, or hides a failure.
- The free OpenJev models (Laya, Verdict) measured unfit on this laptop
  and are NOT the default; that is measured in the probe, not a gap.
- Proven by the fast tier before the smoke fixes (2570 passed), the six
  test files that read the author's text after them, and two live jobs.

### Do not re-report (group B)

- `judge.alive()` returns False against OpenRouter (no `/health`); nothing
  calls it in the product, it is for a local server and the probe.
- The plan is read on the FIRST reply whatever the tree (`first`), unlike
  `name`, which is read only while the tree is empty - on purpose, so an
  "add" job gets a checklist too.
- The OpenJev install under `C:\Users\VasanSeenivasan\openjev` (own venv)
  is outside the repo and nothing starts it; the memory topic file names
  it. The memory update for this commit could not be written (a tool
  permission denial), so the memory index still says "first spike =
  done-checklist" as a plan, not as shipped.

## Group A - carried over (base `fbc3a50`)

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
- `58ab54f` Sketch chat says no how-to: the face-sketch "Draw your
  profile, Finish Sketch, then Extrude" line is gone and "Sketch created"
  no longer adds "Use Create > Extrude". Status and warning lines stay.
  +4 -8.

### Where the risk is (group A)

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

### Ground rules (group A)

- The user chose what each box and bar shows and what to delete; do not
  report a removed row, button or example as a lost feature. Something
  that was load-bearing (a test, a debugging recipe, a failure that must
  speak, a design that no longer opens) is a real finding.
- Proven by the fast tier (see the commits), the browser tests of the
  changed UI (`test_camera_zup`, `test_bodies_visible`,
  `test_tool_panel_units`, `test_new_panel_units`, `test_user_workflow`,
  `test_face_to_feature`, `test_small_face_and_fold`, `test_tool_panel_dock`,
  `test_zoom_limits`, `test_doorbell`, `test_examples_tab`,
  `test_face_sketch_in_viewport`, `test_model_snap`) and one headless
  screenshot pass.

### Do not re-report (group A)

- The "Sketch on this face" button stays in the pick box (an action, not
  information).
- The other tools' pick prompts (Extrude, Fillet, Create Sketch's "Select a
  plane...", placement) and the chat's welcome message still speak; the
  user kept the welcome text when asked, and the one-line pick prompts were
  kept on purpose (they say what a tool is waiting for). Sketch Scale's
  chat how-to ("GRAB one of the amber arrows...") is also still there.
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
