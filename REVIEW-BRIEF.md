# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — THREE code commits wait, oldest first: **Sweep
> `36ee69c`** (range `6b9fa0e..36ee69c`, merged into master at `97a6aea`),
> **Loft `ec45cf1`** (range `97a6aea..ec45cf1`, merged at `559c342`, section 2)
> and **Text entity `d3c8c85`** (range `559c342..d3c8c85`, section 3). All
> built on Fable by the scheduled Tier 2 build of 2026-09-17 with **no review
> yet** — the user asked for the tools to be built one by one and the reviews
> to wait for their own `code review` chats (LAUNCH-PLAN §11, 2026-09-17).
> Sweep and Loft share `tool.js` and suit one chat; Text is the sketcher and
> stands alone. Strike a section here when it is done.

## 1. Sweep tool — `36ee69c` (`specs/sweep.md`)

**What it is.** The first Tier 2 tool: a profile (sketch or flat face) swept
along a PATH sketch. New concepts: an OPEN `path` entity (`closed: false`,
drawn by the sketch ribbon's new Path tool), a PATH SKETCH (a Sketch of edges,
area 0, carrying its wires on `_tc_paths`), and a `path` parameter that is a
REFERENCE (`document.REF_PARAMS`, like a pattern's seed).

**Where the risk is, ranked:**

1. **`sketch._place_sketch` now sits under EVERY sketch and sketch_on_face.**
   Measured: all 47 live designs (50 leaf bodies) rebuild to identical volumes
   and warnings against master (`probes/sweep_library_drift.py`, two runs, diff
   ignores timings). But `compose()` now filters open paths and raises a new
   sentence for an all-open list; `_as_sketch(pl * compose(...))` is unchanged
   for the closed case. A Sketch built as `Sketch(children=[*faces, *edges])`
   (closed shapes AND an open path in one sketch) is a new kernel shape: probe
   6 showed extrude ignores the loose edges; revolve, hole, trim
   (`/api/sketch/trim/pieces`), the tree's entity editor and `cornerlib` were
   NOT measured with one. Worth one probe each.
2. **`sweep_geometry`'s bend and mitre guards refuse BEFORE the kernel.** The
   rule this project keeps relearning: a guard that refuses correct geometry
   is a bug. The bend rule (arc radius ≤ profile reach → refuse) is exact for a
   profile centred on the path; a profile OFFSET from the path (the path
   starts off-centre but on the plane) is judged by the same reach from the
   centre, which over-refuses on the outer side and — check this — may
   UNDER-refuse on the inner side, because the kernel moves the path to the
   centre anyway (probe 4), so the geometry it sweeps IS centred. The mitre
   rule (`leg < reach·tan(turn/2)`) was measured on 90° corners only (legs 1,
   2, 3 invalid; 4+ fine with reach 3). Obtuse and acute turns: a probe.
3. **The Pappus check** (`|V − A·L| > 2 %` refuses) runs for ONE-face profiles
   whose start slant ≤ 2°. Could a correct sweep fail it? A closed LOOP path
   (probe 2: exact), an arc path (exact), a spline path — `path_points` with
   `smooth` — was NOT measured against A·L (probe 1's spline was slanted at
   the start, so it was excluded by the angle). A legacy smooth `path_points`
   tree that starts perpendicular and whose volume is honestly ≠ A·L would be
   refused; no design in `designs/` uses `sweep` at all.
4. **The frontend `onRow` hook** (tool.js): `waitForRow` is armed in `begin()`
   and `openEdit()`; `dropRowWait` runs in `hide()`. Pattern's edges/feature
   modes already had their own waiters — check no tool ends up with TWO waiters
   (waitForRow drops the previous one, so the last armed wins; is that ever the
   wrong one?).
5. **`_check_modifier_input`'s new branch** calls `part.faces()` on any
   `is_sketch(part)` for extrude/revolve/sweep — a Compound of disjoint islands
   is not a Sketch instance and takes the old path; fine. A sketch with faces
   AND paths passes (faces non-empty). A sketch of paths only fed to `sweep` as
   the PROFILE: the gate says "path sketch … needs a closed profile" before the
   op's own sentence — two sentences for one case, the gate's wins.
6. **The kernel placement rule** (probe 3/4): the swept solid starts at the
   profile's CENTRE OF MASS. A profile with holes (a ring) — is `Sketch.center()`
   the mass centre of the face-with-hole (yes for one face) — and does the
   kernel use the same point? Measured on a circle and an off-centre rectangle
   only.
7. **`_reverse_wire`** rebuilds `Wire([e.reversed() for e in reversed(edges)])`
   — measured on lines and one arc. A reversed wire's `tangent_at(0)` is the
   old end's tangent negated; the code reads it after reversal, fine.

**Ground rules for the review:** one reviewer, medium effort, read the diff of
`36ee69c` and probe; fix in the same chat; browser tier only
`tests/e2e/test_sweep_tool.py`; never the full suite "to see".

**Do not re-report** (known, deliberate, in LAUNCH-PLAN §10 P3 "Sweep's
loose ends"): the Add Feature dialog's `path` text box; the arrow sliding
along the local tangent during a drag; no Pappus check for multi-face
profiles; the corner-radius editor untested on open paths; no
orientation/taper/twist. Also deliberate: `SWEEP_SLANT_DEG = 2` is a NOTE
threshold, not a refusal (8° costs 1 % of the volume — measured on the
gauntlet's tapered wall); the in-plane refusal starts at 80°.

## 2. Loft tool — `ec45cf1` (`specs/loft.md`)

**What it is.** The second Tier 2 tool and the framework's FIRST MULTI-INPUT
tool. `loft` stays a combiner (inputs = the sections, in order) and gains its
first parameter, `ruled`. New: `sketch.loft_geometry` (the one verdict),
`toolplan.plan_loft`, `static/js/loft.js`, three small `tool.js` changes
(`spec.inputs(st)`; a profile tool with `onRepick` takes sketch picks while
open; a multi-input tool's preview is UNBUILT and re-created when its input
list changes), `viewport.beginLoftGhost`.

**Where the risk is, ranked:**

1. **The order guard refuses BEFORE the kernel** (`loft_geometry`: the
   sections' centroids must step one way along the mean normal). Measured on
   parallel XY planes and one perpendicular pair. Could a CORRECT loft fail
   it? Sections whose normals differ a lot (a 90° fan of planes) project onto
   the mean normal in an order that may not be the loft's — the kernel builds
   such lofts (probe: XY + YZ planes, 785 mm3, valid). Sections whose
   centroids are laterally far apart but at the same height along the axis
   (a horizontal loft between two vertical profiles — the planes are
   parallel, so the mean normal is horizontal and the stations are fine; but
   two profiles on PERPENDICULAR planes with centroids at equal projection
   would be called coplanar). Worth a probe on tilted planes: `LOFT_STEP_TOL`
   is 1e-3 mm absolute.
2. **The plan REORDERS silently-ish**: the tool puts out-of-order picks in
   axis order and says so once in chat; the stored feature has the sorted
   order. A user who WANTS a fold-back (they never do — the kernel's result is
   self-intersecting) cannot get one. The AI path gets the refusal sentence
   instead. Two behaviours for one rule: intended, but check the sentence
   names the order the plan actually stored.
3. **`tool.js` applyOnce now UNBUILDS a built preview** when
   `JSON.stringify(spec.inputs(st)) !== st.inputsPushed` — only when
   `spec.inputs` exists, so every other tool is untouched (Sweep's four and
   Revolve's journeys were re-run: green, except one Revolve ring-drag flake
   also seen on master — see below). Check: `unbuild` inside `applyOnce`
   inside `holdViewport` — the combiner (`st.opId`) goes with it and
   `applyOp` re-adds it; `st.lastGood` is kept from the previous feature and
   `settle` would push it into the NEW feature — same params shape, fine, but
   worth a look.
4. **`document._eval` now passes `**params` for loft only** (`_loft(ins,
   ids=..., ruled=...)`). `op_params("loft")` returns `(("ruled", False),)`
   and `check_params` accepts it; an OLD saved loft with no params still
   builds (six in autonomiq-panel / autonomiq-sat-panel — drift zero). A
   design saved by a NEWER build with an unknown loft param would refuse at
   `check_params` on edit, not on load — the existing rule.
5. **`loft_sketches` health uses `check_valid=False`** (the rebuild's policy),
   so a self-intersecting loft in a CORRECT order (a twisted pair of squares
   beyond some angle?) would pass health and only the deep check at the end
   of rebuild flags the body. The 45° twist measured valid; 90° is the same
   square. Probe 60°–80°.
6. **Candidates exclude consumed sketches** — but a sketch consumed by THIS
   loft's own preview is in `taken`, so it stays listed as a section; a
   sketch consumed by a struck-out feature is offered (suppressed consumers
   are skipped), matching the framework's profile list.

**Do not re-report** (LAUNCH-PLAN §10 P3 "Loft's loose ends"): no face
sections, no rails / end conditions / seam control, no viewport highlight of
picked profiles, smooth-vs-ruled volume difference, ghost seam twist. Also
deliberate: the sections list is locked in an edit (the framework never
rewires a combiner mid-edit); a single-profile OK says "Nothing lofted".

**A timing flake, not this range's:** `tests/e2e/test_revolve_tool.py::
test_open_from_the_tree_row_and_drag_the_ring` read the angle box as 0 at the
37.3° drag step once, when run in one process after the four Sweep journeys.
Re-run alone twice on this branch and twice on master: four passes. The ring
drag's 40 ms move steps are the likely edge; not touched here.

## 3. Text sketch entity — `d3c8c85` (`specs/text-entity.md`)

**What it is.** A new entity kind, `text`: a word as build123d `Text` faces,
centred on x / y, composing like any shape. New: `sketch._text_faces`,
`ENTITY_STRINGS`, `entity_outlines`, `POST /api/sketch/outline`, the
sketcher's Text tool (one click + a text field in the draw-time box), the
server-outline render cache, `tree.entTextRow`.

**Where the risk is, ranked:**

1. **`entity_schema()` gained two keys** (`strings`, `server_outline`) and the
   tree reads `cat.strings[kind]`. An OLD page against this server is fine
   (extra keys); THIS page against an old server (no `strings`) renders no
   word row — the fallback path (`cat.ok === false`) shows generic numeric
   fields only, so a text entity's word would be uneditable there. Deliberate
   (the server and page ship together) but worth one look at `shapeList`.
2. **`_text_faces` returns a Sketch of several faces** — `compose()` treats it
   as ONE shape: `_containment` / `_overlaps` / `_area_of` run on the whole
   word. A word drawn OVER the edge of a rectangle (half in, half out) with
   mode add: measured nothing. The even-odd rule in the sketcher uses the
   word's BOX; the kernel composes the real glyphs. A letter straddling a hole
   edge is the shape to probe (`compose` with a subtract word partly outside
   the plate: does the outside part vanish silently, as any subtract does?).
3. **The sketcher draws nothing for a word until the server answers**, and
   caches `[]` on an error — after an error the word never draws again in
   that session (the cache key has no retry). The error IS said in chat. A
   word whose glyphs fail (an emoji, say) would sit invisible but present in
   `skEnts`; the tree shows it. Probe an emoji / a non-Latin word: the kernel
   may shape it with Arial's fallback glyphs or produce nothing.
4. **The draw-time box now holds a TEXT input** and `routeDigitToDrawBox`
   focuses the FIRST input when a digit is typed anywhere in sketch mode —
   for the Text tool that first input IS the word field (a digit typed
   before the box exists goes nowhere; after it exists the field is already
   focused). Escape in the word field calls `updateDrawDimBox` which
   re-focuses it (`!el.contains(document.activeElement)` is false while
   focused, so no loop) — check Escape still leaves the tool as it does for
   other shapes.
5. **`_validate_dims` runs on `size` only**; `text` and `font` are validated
   in `_text_faces` (empty, non-string). A `text` that is a NUMBER (the AI
   writing `"text": 2026`) is refused as "needs a word" — arguably it should
   be shaped as "2026". Deliberate? No: a cheap improvement (str() a number).
6. **Extrude of a word gives N solids** and `_check_pieces` exempts extrude by
   name, but a **Cut** made of the word's prisms is judged too: the engraving
   journey (plate − 'AB' prisms) passed with no pieces warning because the
   RESULT is one body. A word cut THROUGH a thin plate would split it — the
   existing "falls into pieces" warning covers that.

**Do not re-report** (LAUNCH-PLAN §10 P3 "Text entity's loose ends"): the
silent Arial fallback for an unknown font; no bold / italic / spacing / text
on a curve; the font row shown only when present; the brief invisible moment
before the loops arrive; box-based hit-test and mode rule; no resize handles.

**Merge note.** The build session merges the branch into master only if the
main checkout has no modified tracked files at that moment (the user's Opus
bug-fix chat shares the checkout). If the bottom of this file says a branch
is unmerged, review it on the branch: `git log master..worktree-<name>`.

**How the review starts.** The user opens a fresh chat on Opus
(`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
"The review chat" tells that chat to read this status line: PENDING means
review the range named here; NOTHING PENDING means go to the queue (which is
empty since 2026-09-17).
