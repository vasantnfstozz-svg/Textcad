# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
> **A rewrite must carry over every PENDING range it did not review** - this
> brief exists because one did not.
>
> **Status: PENDING** - `e6c291c..1294f7a`, ONE commit, frontend only.
> Nothing else is carried over: the Tier 2 tools were all reviewed and fixed
> on 2026-09-23, and `REVIEW-QUEUE.md` is empty.

## The range (base `e6c291c`)

- `1294f7a` Create Sketch opens on one fixed, framed view; offset planes hide
  once the pick is over; 4 new browser tests. Built on Opus 5.5 at the user's
  request (2026-09-24).

## What changed, and why

The user: Create Sketch's plane pick "is different sometimes, not aligned; it
has to go to a proper fixed position, a correct zoomed mid position, every
time". And an offset plane stayed in the background after its sketch was
finished; it should be gone, since it is in the tree.

1. `viewport.framePlanePick` (called by `beginPlanePick`, and again from
   `loadModel` if a load lands while the pick is open): the camera flies to
   the home iso direction, aimed at the box centre of every quad corner plus
   the bodies' box, at the distance where each point satisfies
   `|sideways| <= depth * tan(half-fov) * 0.88`. A 350 ms `flyTo` tween;
   `endPlanePick` and `setView` stop it (`endViewTween`).
2. `loadModel`: the fit volume (`fitCenter` / `fitRadius`) is the CURRENT
   document's always. With no body and no sketch it resets to the origin,
   radius 100. Before, it was only updated when a body existed (or when a
   fit was asked for with sketches), so an empty design kept the previous
   design's centre. `fitToObjects` is folded in and deleted.
3. Construction planes (`drawConstructionPlanes`) are created with
   `visible = !!planePickCb`; `showConstructionPlanes` flips them in
   `beginPlanePick` / `endPlanePick`. The tree-row glow
   (`showFeatureOverlay`) still reads the hidden quad's geometry and matrix.

## Where the risk is

- **The fit reset reaches every reader of `fitRadius`.** Arrow length, the
  ground grid, the zoom floor on the next fit, sketch3d's plate size, label
  size. On a sketch-only design `fitRadius` is now the sketches' (it was the
  last body design's, or 100). Is anything sized from it now too small?
- **The tween holds `controls.enabled = false`.** It gates the wheel and is
  also the e2e "tween done" signal. Can anything end the pick without
  `endPlanePick` (and so leave navigation off)? The `doc-updated` handler,
  Esc and a pick answer all go through it. An exception inside
  `framePlanePick` during `loadModel` is swallowed by that function's `catch`.
- **Raycasts ignore `visible`.** Hidden construction planes are still hit by
  a raycast. Only `pickableQuads` includes them, and it is only raycast during
  a plane pick, when they are shown. Is there another path?
- **Offset Plane's own pick** (`openOffsetPlane`) goes through
  `beginPlanePick`, so it frames too. That was deliberate, for consistency.
- `framePlanePick` may raise `camera.far` / `controls.maxDistance` when the
  fit distance exceeds them. It never lowers them.

## Ground rules

- Frontend only. No backend or document change, and no design file touched.
- Proof: the 4 new tests (`tests/e2e/test_create_sketch_view.py` x3,
  `test_offset_plane.py::test_the_plane_is_on_screen_only_while_a_pick_waits_for_it`)
  were run red against HEAD's `viewport.js` and are green now.

## Do not re-report

- `test_adaptive_grid.py::test_zoom_subdivides_and_stops_at_the_floor` is red
  on HEAD `e6c291c` too (plan s10 P3 row).
- The "plane1" / "XZ" label overlap in the pick view is pre-existing (plan
  s10 P3 row).
- `test_sketch_scale`'s `_entities` now accepts `sketch_on_face`. Measured:
  the fixture's click missed the top face from the old camera and sketched on
  XZ. That was the test's bug, not a new one.
- The pick moving the camera at all diverges from Fusion. The user asked for
  it (fusion-parity rule 14).

**How the review starts.** The user opens a fresh chat on Opus
(`/model claude-opus-5-5[1m]`) and types only `code review`. CLAUDE.md's
section "The review chat" tells that chat to read this status line: PENDING
means review the range named here; NOTHING PENDING means go to the queue.
