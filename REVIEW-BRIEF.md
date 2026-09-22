# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review the range `e551a3d..HEAD` — **Offset Plane**,
> Fusion's construction plane as a feature (`specs/offset-plane.md`). ONE
> commit on top of `e551a3d`. Built on Fable 2026-09-22, no review yet.

## What was built, in one paragraph

The user tried the 2026-09-21 sketch-plane design (Create Sketch's Offset step
+ the SKETCH tab's Move Plane, reviewed and closed in `cdc833a` / `a1e3483`)
and found it the wrong tool: moving the plane took the drawn circle with it
(Fusion's *Redefine Sketch Plane*). What they meant is Fusion's **Construct >
Offset Plane**, and that is what this commit builds — and it DELETES the old
design: the Offset step, Move Plane, `setSketchPlaneOffset` /
`currentSketchPlane` / `pauseSketchInput` / `setSketchPointerPaused`, the 16
browser tests and 3 node tests that pinned them. `offset_plane` is a feature of
a **third kind, `plane`** (neither creator nor modifier; result a build123d
`Plane`), from a principal plane or a flat face of a body (a REFERENCE input,
never consumed). A sketch names the plane in `plane` (`REF_PARAMS["sketch"]`),
so the plane's offset rebuilds every sketch on it and deleting it cascades.
Create Sketch right after Offset Plane lands on the new plane
(select-then-command); any later Create Sketch clicks the orange quad. Line
delta **+1069 / −1175**; fast tier **2621 green**, the offset-plane
browser file 8 green, ruff and eslint zero; ui v232. No design file touched
(the sketch's own `offset` param stays, 310 saved offsets untouched).

## Where the risk is (ranked — start at the top)

1. **A third kind of part flowing through code written for two.** Every site
   that sorted `_parts` into sketch | solid was touched (`document.py`:
   rebuild loop, `leaf_solid_ids`, `_result_feature`, the blockers,
   `_kind_of`, `_check_modifier_input`, `_check_combiner_inputs`;
   `provenance.py` twice; `studio.py` `/api/model` goes through
   `leaf_solid_ids`). The question for the review: **is there a site I did
   not find?** Candidates: `document.py:2261` (pieces warnings — skipped by
   the COMBINERS/MODIFIERS filter), `consumed_ids` (a plane is in
   `FACE_REFERENCE_OPS`, so its body input is not consumed), the delete plan's
   `_passthrough` (kind "plane" never matches, so dependents cascade — is
   that the right answer when the BODY under a face-based plane is deleted?),
   export (`exported_bodies`), the spec checker, journeys, the MCP doorbell's
   op list. Measured: `tests/test_offset_plane.py` covers the first six sites.
2. **`REF_PARAMS["sketch"] = ("plane",)` changes `param_refs` for EVERY
   sketch.** The principal names are filtered out, so an ordinary sketch's
   refs stay `[]` and its cache signature does not move — but `param_refs`
   feeds the delete plan (1356/1388/1415/1478), `_signature` and the
   "rides a move" rule at 597. A sketch on an offset plane now answers "does
   not ride" there. Check what that means for `move` of a body whose face the
   plane is measured from (the plane rebuilds from the moved face anyway).
3. **The formula door.** `numeric_params` had to learn the op (the browser
   test found `"-wall"` refused as "a value it cannot use"). The same lookup
   pattern (`CREATORS.get(op) or MODIFIERS.get(op)`) exists in `op_params`
   (fixed), `numeric_params` (fixed) — and possibly elsewhere: `_params_dict`,
   `required_params`, `author._annotate`, the Add Feature dialog's catalog
   consumer. One grep, please.
4. **`plane_of` builds a throwaway `Feature("?")` to reuse `_plane_part`'s
   sentences.** Cheap but ugly; a sentence from the plan reads "sketch: plane
   must be …" — fine for the sketch plan, wrong wording if any other caller
   arrives.
5. **The viewport draws planes on `doc-updated` AND re-draws inside
   `loadModel` (sized with the model).** `fitRadius` at the first draw is the
   previous model's; the redraw fixes the size. A plane that did not build has
   `plane_frame: null` and is simply not drawn — the tree row says why.
6. **The pick: a plane quad is only pickable OUTSIDE the body's silhouette**
   (the origin-quad rule: a body face under the cursor wins). A plane sitting
   inside the part's outline from the current view is reachable only through
   its row. Documented as plan §10 P3 (c), not fixed.
7. **Select-then-command through a bus event.** `select-feature` → tree
   `selectFeature` (which also `clearPick`s and shows the overlay); `null`
   clears. `startSketch` consumes a selected plane only when its status is
   `ok`. Check that a plane selected minutes ago does not silently hijack a
   Create Sketch the user meant for a face — that is exactly the
   fusion-parity rule 2 caveat (the tree row ranks last for tools; here it
   ranks FIRST, on purpose, because Create Sketch has no other selection).
8. **The `/api/doc` payload grew** by one key per feature (`plane_frame`,
   null for all but planes). `_doc_json` runs on every request.

## Do not report

- The sketch's own `offset` parameter and the offset method (rule 11) are
  unchanged on purpose: the AI author and 310 saved offsets use them.
- `into_sign` is measured per face (+y: positive goes in) — reviewed twice.
- The tool.js inch round-trip on an untouched OK (Extrude 12 → 11.99896) is
  plan §10 P2, not this range; the plane panel handles it with the `shown`
  string compare, tested in mm and inches.
- A plane off another plane, an angled plane, a midplane, hiding a plane —
  plan §10 P3, listed in the spec's "Not built".
- The "body disappeared" report of 2026-09-22 was not a bug: the user's
  active tab held one sketch and no body (7 tabs named my-part-6).

## Ground rules for the reviewer

One reviewer, no subagents. Reproduce by measurement or a red test before
fixing; smallest fix; tests beside the code; commit, push, restart the user's
server (the backend changed). Then this file → `Status: NOTHING PENDING`, a
plan §10 row for anything deferred, memory. Never `--fix`.
