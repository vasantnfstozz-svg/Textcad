# REVIEW-QUEUE.md - the from-scratch code review of the OLD tools

> **How this file works.** The tools shipped since 2026-09-03 were each reviewed
> right after their commit and the reviews found real bugs every time (Taper 14,
> P2 Extrude 28, Revolve 40, Hole 25, Pattern 7, Mirror ~20, Fillet 7+6). The
> older modules never had that pass. This file is the ordered queue of those
> modules, one section each, with everything a reviewer needs so that no
> section has to be re-derived in a chat.
>
> **One module per chat, on Opus, and the user types only `code review`.**
> The user opens a FRESH chat, types `/model claude-opus-5-5[1m]`, then `code
> review`. CLAUDE.md's section "The review chat" sends that chat here
> whenever `REVIEW-BRIEF.md` says `Status: NOTHING PENDING`: it takes the
> first status-board row marked TODO, reads that section's files itself as
> ONE reviewer (no `/code-review` command, no subagents), puts the report in
> the chat, and then runs the fix pass under "After the review" without being
> asked. The next module waits for the next chat.
>
> Each section still carries its old paste line: it names the files and the
> effort, which is the scope the reviewer reads. The user does not paste it.
>
> `REVIEW-BRIEF.md` keeps its job for per-commit reviews of NEW code; its
> `Status: PENDING` wins over this queue. This file is for the backlog of old code.

---

## Shared rules of engagement (every section)

1. **Read-only during the review.** No edits, no server start (the user's
   server is on port 8123; a second listener there is a known trap), nothing
   under `tests/e2e/` (those write into the design library). You MAY run the
   fast test files a section names, with `C:\Python314\python.exe -m pytest <file> -q`.
2. **Stay in scope.** Read the section's files; follow a call out of them only
   when a finding depends on it. Every other module has its own section.
3. **Comments are history, not clutter.** A comment naming what the user saw
   on which date records a real past bug. Never report a comment as noise.
4. **The frontend must not re-derive backend facts** (LAUNCH-PLAN rule R1).
   Plane frames, axes, normals, origins, safe ranges, target bodies come from
   a server response, never from JS maths. JS that computes such a fact itself
   is a finding; name the line.
5. **Two failures are banned by design:** a kernel exception reaching the
   user (OpenCASCADE errors derive from `Exception`, not `RuntimeError`), and
   a "successful" invalid, empty or non-manifold solid. A degenerate value that
   reaches build123d unchecked is a finding.
6. **The viewport follows the document** (rule R3): a tool that refreshes the
   scene itself is a finding unless the section lists it as known.
7. **No fixes, no style.** One clause of a hint is fine; a patch is not. No
   naming, formatting or refactoring remarks; Ruff and ESLint run at zero.
8. **Findings are concrete.** A finding is an input on which the code does the
   wrong thing, with the exact user action or data that triggers it. "Could be
   fragile" is not a finding.

**Never report** (already known, tracked in LAUNCH-PLAN.md section 10): the
open P1/P2/P3 rows there; the pre-existing red browser tests
(`tests/e2e/test_tree_delete.py`, five; the order-dependent revolve ring
test); two requests reaching the kernel at once (FastAPI threadpool, P2);
the browser replaying a POST on a dead keep-alive socket (P2); the
`enterMode()` race when a sketch opens (P3); `sketcher.js` and `measure.js`
calling `loadMesh()` after their own changes (P3); five tools hand-typing
"a value typed before the plan arrived waits for it" (P3); lint-class output
(unused names, two statements on a line, single-letter geometry variables).
A section may add its own known items.

---

## Output format - exactly this, nothing else

Order by severity: **P0** wrong geometry saved or data lost; **P1** blocks a
basic action; **P2** hurts daily use; **P3** polish. At most 15 findings. If
fewer than 5 have high or medium confidence, say so; do not pad the list.

```
### F1 - P<0-3> - <one line: what goes wrong>
- File: <path>:<line>  (and a second path:line if two places interact)
- Trigger: <the exact user action or the exact input data>
- Expected: <one line>
- Actual: <one line>
- Confidence: high | medium | low - <why: read the whole path / a test contradicts it / could not follow one branch>
- Evidence: <1-3 quoted lines from the file, verbatim>
```

Then two closing sections:

```
### Checked and found OK
<up to 8 one-liners: areas read fully and found sound, so they are not re-checked>

### Could not judge without running the app
<up to 5 one-liners>
```

---

## Status board

| # | Module | Effort | Status |
|---|---|---|---|
| 1 | Sketcher | high | four rounds, each fixing the last: 556a611 (9/9, 1 rejected), 6e2cae9 (8/8, the fix pass had a P0), 5f65a7a (8/8, so did that one), **13da90c** (8/9, 1 rejected - the ordering RULE was incomplete), and **round five, ONE reviewer at medium**, which CLEARED the two-part ordering rule (no arrangement makes it worse, termination bounded) and fixed 5 gaps in the fix pass itself. Composition is measurably order-independent, all 324 library sketches build, the whole library composes unchanged. **Section 1 is done unless the sixth read finds something** |
| 2 | Document core and feature tree | high | **reviewed and fixed 6ea5546**, ONE reviewer at medium: 5 findings, **4 fixed, 1 rejected** (refusing to open a file with an unknown op IS the settled answer - the fast tier proved it). 7 new tests; the P2s were a struck row keeping its piece count (and silencing the warning below it), a struck row highlighting the whole upstream body, and an intended sever re-probing the healer on every rebuild |
| 3 | Version tree and session persistence | high | **reviewed and fixed f63ba5a** (3 findings, all 3 fixed, 9 tests): a P0 (a save could overwrite ANOTHER design's file and graft itself onto its version tree), a P1 (after a restart a tab with unsaved edits could read clean, so closing it discarded them silently) and a P2 (the only recovery for a lost index named a Python method - it is a button now). A P0 was fixed, so **round two re-reviewed the FIX COMMIT: fafe983**, 4 findings, **all 4 fixed**, 8 new tests - the same P0 was still reachable through TWO other doors (a second tab taking over an open design's file; a slug whose `.history/` outlived its deleted `.tcad.json`), and the new repair button could overwrite a NEWER build's index. **Section 3 is done unless a third read finds something** |
| 4 | Booleans and transforms | high | **reviewed and fixed c9b2e92**, ONE reviewer: 9 findings, **all 9 fixed**, 26 new tests, 50/50 library designs rebuild with ZERO volume drift. The one that mattered most: **`loft` of a sketch AND a solid SEGFAULTS OpenCASCADE** (exit 139, no `except` can catch it) and the Add Feature dialog offers every feature as a checkbox — so combiners now get a KIND gate BEFORE the kernel, which also closes the silent twin (an `intersect` of a body and a sketch ate the body and left the design with no bodies, all rows green). Plus: no bodies + a spec reported "meets spec"; the Join/Cut default target followed FACE-REFERENCE ops (a New-body boss became the panel's current state, parity rule 6); the stranding heal ticked `through` on a tool ANOTHER cut shares (that cut lost 3600 mm3 unasked); a cut whose tool misses reported success silently; a pattern's copy form called "a part that fell apart" (24 rows in 13 designs). A P0-class finding was fixed, so **round two re-reviewed the FIX COMMIT: 33b2f49**, 2 findings, **both fixed**, 4 tests — two holes in the guard round one had just built (`getattr` does not swallow a raising property; build123d raises its OWN bare `ValueError` with kernel wording), plus the new refusal calling a body behind the rollback bar broken. The brief's four other named risks CLEARED by measurement, `_live_source` included (52 files, 15 struck features, zero mismatches). **Section 4 is done unless a third read finds something** |
| 5 | Primitives and shape editing | high | **reviewed and fixed e35450d**, ONE reviewer: 8 findings, **all 8 fixed**, 0 rejected, 55 new tests, all 50 saved designs rebuild with no failed feature. The one that mattered: **`polygon_plate` and `hex_plate` span Z 0..thickness, and the AI's positioning rule listed them with disc and plate as CENTERED** — so every `move` it computed for a hex body was half a thickness out (designs/planetary-assembly: four bolt heads seated 1.4 mm high, 0.5 mm of shank overlap where 1.9 mm was intended). The PROMPT was corrected, not the solid: two saved designs are built on the geometry as it stands. Plus: a degenerate dimension put raw kernel text in the feature row (`Standard_DomainError('')` for a zero thickness — the same empty diagnosis for all three of a plate's dimensions; twelve lines of pybind11 constructor overloads for the string "8mm"); `with_center_hole`/`with_bolt_circle` reported success after drilling NOTHING (radius 0, or a PCD that puts the holes off the part — volume unchanged, row green), and a PCD of 0 silently drilled one hole instead of six; the tree painted a red "spec FAIL" whenever the rollback bar was parked, on **42 of the 50 designs** that carry a spec; the placement popup's one shared debounce timer discarded a dimension typed just before touching x/y/z. A P0-class finding was fixed, so **round two re-reviewed the FIX COMMIT: 2d2e8a9**, 2 findings, **both fixed**, 4 tests — the fix pass's own `cone` guard had taken away a legitimate shape (a funnel standing POINT-DOWN: `cone(0, 10, h)` builds at 2094.40 mm3, exactly the flipped cone's volume), and `spec_checked` defaulted True so a never-rebuilt document claimed a green "spec PASS". The brief's other four named risks CLEARED by measurement: `_drilled`'s 1e-6 floor has six orders of magnitude of headroom (a 0.05 mm hole in a 100-million-mm3 plate measures to 8 significant figures), `numeric_params` misses no numeric parameter (pattern's unannotated `count` already refuses plainly in `pattern.py`), `plain_cause`'s new collapse cannot swallow a ValueError because that branch returns first, and `sides=6.0` is a non-event (no file holds one). **Section 5 is done unless a third read finds something** |
| 6 | Measure and drive | high | **reviewed and fixed 3ce97a3**, ONE reviewer: 8 findings, **all 8 fixed**, 0 rejected, 10 new tests. The P0 was silent wrong geometry through a door nobody had opened: over 400 faces the mesh switches to a cheaper path that handed the viewport one edge id PER ADJACENT FACE in face order, while `measure.resolve` indexes `part.edges()` — so on **12 of the 50 saved designs** every edge click measured a DIFFERENT edge and never said so (esp32-remote: 7176 ids for 3588 edges, 6517 wrong), and on isogrid-panel a straight 210 mm edge read ⌀4.50 mm AND opened an edit box driving another hole's circle. Plus: the verification re-read the face INDEX the pick was made on, so a rebuild that renumbered the faces REVERTED a correct edit (x-frame's ⌀8 pad hole really became 8.5 and the tool said it had not — 7 of 81 editable diameters, and the move path too); an imported STL answered "face -1 is not on this body any more — click it again" for ever; a tilted face's extents came from the WORLD bbox (a 45° chamfer read 6.00 where it is 8.49, and the pick panel said 8.49); every dimension typed to more than 3 decimals was written perfectly and then reverted (5/16" = 7.9375); a bore's "centre" was an arbitrary point along its axis. The revert safety net was ACCIDENTAL (it fired on renumbering) and is now explicit: a dimension that stops a feature building is put back. **A P0 was fixed, so round two re-read the FIX COMMIT: b8a956f**, 2 findings, **both fixed**, 2 tests — both in the fix pass's own new code and NEITHER live for the user (a fallback that shared a `try` with the thing it falls back from, so it could never run; and `picks` still describing the post-write body after a revert put the previous one back). The brief's first-named risk CLEARED by measurement: **322 driven edits across 9 designs — 92 diameters, 58 moves, 172 deliberately destructive — against an independent inline oracle, zero false passes and zero false fails**; plus no outlines lost by the mesh fix (identical distinct edge sets), `_shape_key` collision-free across located copies, and BSPLINE flat walls handled. **Section 6 is CLOSED** |
| 7 | Extrude as a whole module (with loft and sweep) | medium | **reviewed and fixed `dfcb73f`**, ONE reviewer: 6 findings, **all 6 fixed**, 0 rejected, 11 unit tests + 2 browser journeys, all 50 saved designs rebuild unchanged. The two that mattered were in the ops nobody had ever reviewed: a **loft blends ONE profile per sketch** — build123d chains every section's faces into a single loft, so two sketches of two circles each came back as ONE snaking solid of 1570.8 mm3 (the honest tubes are 3141.6) reaching outside BOTH sketch planes, status ok, no warning — and **`sweep` fed a solid BODY sweeps it face by face**: a 24 000 mm3 plate became a 178 000 mm3 six-lump blob, green and silent, with the plate consumed, one click from the Create ribbon (the Add Feature dialog pre-ticks the newest feature). Plus: a picked face pulled INTO the body kept the default Join and fused a prism already inside it (plate 24 000, prism 9 600, join 24 000 — three green rows, nothing said; the drag-direction rule was written `!isFace(st)`); Through all threw the taper away while the box and the ring still showed the angle (a -10° through cut built 20 x 30 x 2000 mm, dead straight); a typed negative "Distance 2" was dropped; and Through all's into-the-body seeding was missing from Two sides, so the 2 m side ran into the air. No P0, so the queue's step 8 called for no second round — but the brief was deliberately set **PENDING on the fix commit `dfcb73f`** anyway: the pass added two REFUSALS (one of them in `_eval`, which runs for every modifier feature on every rebuild) and changed what Extrude does by default, and on this project a fix pass's OWN new guard has been wrong more often than not. Round two read that diff only and is **done at `a8e96d9`**: 2 findings, both fixed, 3 more browser journeys — the loft refusal quoted ONE profile count for SEVERAL sections, and OK said "Extrude created" over an EMPTY viewport (the inward pull is a Cut by itself now, so "deeper than the body" is one gesture away: the extrude stays green at 72 000 mm3 while the CUT it made fails and no body is left — the OK sentence only ever looked at the tool's OWN feature, never at the combiner it had just added). **Section 7 is CLOSED** |
| 8 | Import STL and STEP | medium | **reviewed and fixed `94eb47e`**, ONE reviewer: 7 findings, **all 7 fixed**, 0 rejected, 11 new tests, fast tier 1623 → 1634. The two that mattered were both silent wrong geometry, both green: a **hollow STL imported with its cavity FILLED plus a phantom body inside it** (936 mm3 came in as TWO bodies totalling 1064 — lib3mf had already read the file correctly as one Solid of 936, but the guard meant to take that as-is called `shp.is_valid()`, and `is_valid` is a **property**, so it raised TypeError into a bare `except` and every shape was exploded shell by shell; the as-is path alone is not enough either, since lib3mf returns ONE Solid holding every shell in the file and two disjoint bodies make it invalid, so the shells are regrouped by winding + containment, and `split_components` gave the cavity its own STL piece on the repair path too); and **the parity voxel fill XORed overlapping material away** — two interpenetrating bodies welded along a shared edge, the Fusion assembly export this module exists for, came back **7,998 mm3 of a true 12,000**, a void punched straight through the overlap, health [] and status ok. Plus: a body exported TWICE at the same place was **deleted outright** (2000 mm3 imported as 1000, announced as "merged 24 coincident wall triangles"); the remesh moved every surface of a body with nothing measuring or reporting it (a 0.6 mm plate came back 8.7% light, silently); `MIN_COMPONENT_BUDGET` is a floor per BODY with no cap on the sum (40 bodies = 60,000 triangles of an 18,000 budget); a file that is not STEP at all was diagnosed "surfaces or curves alone cannot be used here" (OCCT does not raise — it returns an empty shape); a truncated STL said "not an STL file". The real 88,990-triangle assembly imports to the SAME geometry as before (339,926.9 mm3, 3 bodies, checked against `84e7c17` in a worktree) and **no saved design uses either op**. Two P0s were fixed, so **round two re-read the fix commit `94eb47e`: `d94518c`** (on Fable 5.1 at the user's call), 4 findings, **all 4 fixed**, 5 tests, fast tier 1639 — the round-one P0 was still open through the INVERSION door (a hollow part wound inside-out came in as 1064 mm3 in two bodies because void-or-body was decided by the SIGN of each shell's volume; it is decided by NESTING DEPTH now, with OCCT's point classifier, and each shell is WOUND to fit its role), and round one had introduced two REGRESSIONS: a pinched CAVITY surface was refused as "an empty volume" (the winding fill enters where the winding says in, and on an inward surface that is nowhere), and the winding fill broke the parity fill's documented indifference to inconsistent winding (two pinched cubes with one face flipped came back 7,998.8 of 16,000, green) — a component whose triangles disagree falls back to parity. The duplicate bbox grouping rule in meshrepair is DELETED: one STL piece, one exact rule in blocks. A P0-class gap was fixed again, so **round three re-read `d94518c`: `8fdfa5b`**, 1 finding, **fixed**, 2 tests, fast tier 1641 — round two's nesting rule judged "B is inside A" from ONE vertex of B, so a bracket overlapping the notch of a C-shaped frame (box inside the frame's box, one corner inside its material) came in as ONE body of 20,360 mm3, the 640 mm3 bracket made a VOID of the frame, valid and green; "wholly inside" is a spread SAMPLE of up to 400 vertices and 400 face centres now (TopExp.MapShapes in C++, one loaded classifier, 0.25 s per nested pair), and the face centres catch a pin whose ends sit in two walls while its middle spans the gap. Cleared: an OUTWARD-wound cavity (MeshLab re-orient) — lib3mf marks it invalid, the regroup gives 936. **Round four re-read `8fdfa5b`: `8241115`**, 1 finding (P1), **fixed**, 2 tests, fast tier 1643 — round three's 400 + 400 point survey put each point to OCCT's classifier, which is LINEAR in the container's faces (173 ms a point against a 32k-face body; the 55 us figure had been measured against a 12-face box), so a real faceted hollow part beside another body made 800 calls, ~140 s. Now: one confirming point; an INWARD-wound shell that sits inside a body is the cavity the file says it is; an OUTWARD-wound one (MeshLab re-orient, or an embedded body) gets a survey sized to the container (`_nest_cap`, a 100,000 face-evaluation budget per kind). Cleared: thin walls to 0.005 mm, 40 parts in a tray and 40 islands in a housing (~1 s), `_spread` edges, `BRepExtrema_ShapeProximity` (dead end in OCP). No P0 in round four, so **Section 8 is CLOSED** — 4 rounds, 13 findings, all fixed, 20 tests, 1623 → 1643 |
| 9 | Trace image | medium | **FOUR rounds** (`4c9ea32`, `4b3af6a`, `f5d9a17`, round four empty): 18 findings, **11 fixed, 4 rejected, 5 carried**, 22 new tests. **Five P0s, all the same one: artwork traced as its own NEGATIVE.** Round one found it in the original majority rule - a 40 mm disc cropped to its ink (78% ink) traced its four CORNERS, 343.5 mm2 of a true 1256.6 - and **the user's `esp32-remote` `logo_0_sketch` IS that bug in the library**: one 533.34 mm2 slab with six letter-shaped holes, the negative of "autonomIQ" (both logo features suppressed, so it was never machined). Rounds two and three then found the same P0 twice more inside the replacement rules - a thin dark edge (a scan's platen edge, a 1 px export frame) and a thin LIGHT pad (a plate with bolt holes: 440.1 mm2 of a true 1258.0). **The lesson of this section is measurement discipline**: round one scored itself 9 vs 7, round two 12 vs 11, each on ITS OWN corpus - and an outside corpus showed round one was a net REGRESSION and round two merely a TIE with the original. Over all four corpora (74 pictures) the final tally is original 55, round one 42, round two 54, **shipped 58**; round four's was the first self-assessment here to survive an outside corpus. Also fixed: `_uncross` DISCARDING real artwork (two discs joined by a 1 px bar traced as one - 1237 of a true 2498 mm2, valid and silent); a 2x2 speck deciding the fit height AND the 90-degree auto-rotate (a logo stood up at 7.2 x 36 mm instead of 107.9 x 21.6, a ninth of the area); outlines handed to `sketch.py` that cross themselves (1 trace in 60 built a body OpenCASCADE calls invalid); and a numpy traceback reaching the chat. The health number that settles the pass: over 450 traces the ORIGINAL module hands `sketch.py` **720 self-crossing edges and 30 unhealthy solids**; the shipped one, **0 and 2**. **Section 9 is CLOSED** |
| 10 | Viewport, picking and face provenance | high | **reviewed and fixed `8aa30a2`**, ONE reviewer: 5 findings, **all 5 fixed**, 0 rejected, 9 new tests. The P1 was in the face-pick SIZE GATE committed hours earlier (`1a8d28f`): a pick whose face GROWS past its recorded area falls through to a same-sized face elsewhere, and when the two host faces of an edge no longer share one the feature goes RED - measured on a plate with two 200 mm2 pads, widening one 20 -> 24 mm killed its own chamfer though the rim had moved 2 mm. `resolve_edge` tries stored sizes first and sizeless second, so a refusal is earned by both rules. Plus: the Sketch tool's plane picker decided FLAT from the surface TYPE, so no tapered, lofted or swept wall could be sketched on though `sketch_on_face` and the pick panel's own button accept it (all four walls of a 12-degree tapered box are BSPLINE and planar); `attribute_face`'s stale-index fall-back never consulted the area it was handed, so a flush pad in a pocket was attributed to the plate with 'high' confidence; a 'Created by' link revealed the tree row and lit nothing; an imported mesh body's face click blamed a document change that never happened. **Round two re-read the fix commit: `9f1b421`, 0 findings** - round one's work was put to the kernel, not to a reading (the sizeless fall-back is DORMANT over the 9 gauntlet bodies' 135 edges, RIGHT at all twelve widths when it does run, and newly answers in 1 of 752 cross-body resolutions; 6 of round one's 9 tests go red on revert, the 3 that do not are documented guard tests). Round two's own extra measurement found a defect in `toolplan._face_of` instead - see the done log. **Section 10 is CLOSED** |
| 11 | Tool framework core | medium | **reviewed and fixed `a3d6b03`**, ONE reviewer: 6 findings, **all 6 fixed**, 0 rejected, 18 tests. **P0: a tool panel open on design A wrote its edit into design B** - the document tab bar was the one control not behind `modalGuard` (every ribbon button already is) and `uid()` hands out the same feature names in every design, so B's `extrude1` went 9 mm -> 30 mm / 1017.88 -> 3392.92 mm3 from a panel opened on A. Plus a mistyped holes box deleting a requirement and calling it a pass; a selected sketch row outranking a curved-face pick so Extrude silently extruded the sketch; a missing bracket adding nothing and saying nothing; any non-200 plan answering 'cannot start: undefined'; and the extrude arrow sitting on the average of the SAMPLED boundary points (3.727 mm off on an L profile, 12.404 mm on two islands). **Round two `217d289`: 3 more, the P0 STILL OPEN through the door round one's own commit message named** - a panel does not need a tab CLICK to lose its design; a design ARRIVING from outside (MCP, the doorbell, a second window) takes the active tab, measured 9 -> 30 mm again; and the spec dialog deleted a requirement through the six boxes round one did not look at (typing `two` into n_solids made a red spec a GREEN `{}`). Cleared by measurement, not reading: the tab guard does NOT lock the user in, and the centroid change really is gizmo-only (the whole plan dict byte-identical over ten profiles but `origin`/`outer_radius`). **Round three `931f747`: round two holds (0 findings, the shipped tool.js run in node - a rename does NOT fire the let-go), and the P0 section 10 handed over is CLOSED** - while Fillet is open the click carries the PREVIEW's area, so a face the preview TRIMMED resolved on the input body by its trimmed area and `plan_fillet` rounded every edge of a pad 50 mm away, silently. Section 10's proposed `OnFace` gate was evaluated and REJECTED by measurement (an annulus's centroid lies in its hole), so stored-size-then-sizeless is used with `OnFace` only as the chooser: **284 clicks on real preview bodies, 0 moved, 0 newly refused**. **Section 11 is CLOSED** (three rounds, 10 findings, 39 tests) |
| 12 | Server layer | medium | **SEVEN rounds** (`b88d870`, `29bc967`, `8feb30f`, `4a6c667`, `66d80c1`, `8f242c6`, round seven empty): 19 findings, **17 fixed, 1 rejected, 1 carried**, 60 new tests. The spine of it was ONE defect found four times over: **a request read "which tab am I about?" more than once, and the MCP doorbell moves the active tab from another thread between the reads.** Round three measured `/api/export` writing design A's 2000 mm3 solid into design B's `.step` (B is 3600 mm3), status 200, "Exported". Round four found that repair covered two endpoints while **25 others had the same seam** - measured with a real race and nothing patched: `/api/trace-png` put a traced logo into a saved design the user never opened, whose undo depth was 0, so Ctrl+Z there does nothing; `/api/chat` read the active tab **25 times in one request**. Round five found the per-request pin protected one request while the ANSWER gave the next away (`_doc_json` labelled a reply about tab A with the tab a doorbell had just made active, and the browser hands that label back) and that **nine `fetch(` sites bypass `api.js`** - File > Export wrote the arriving design's solid. Round six found the new fetch door was string-only while three.js sends `Request` objects, so the viewport could be drawn another design's mesh. Round seven: **0 findings** - 26 URL shapes, 46 tab-sensitive endpoints in three header states (140 asks, all correct), the one-writer guard right in all 16 cells, `designs/` byte-identical over 397 files. Earlier rounds also closed: a restart throwing away the tab you were LOOKING at (`[:MAX_TABS]` keeps the oldest), `/api/export` overwriting another design's `.step` and refusing two of the user's own designs, `/api/spec` poisoning a document with one wrong value, the fast tier writing `t-washer` into the user's library and ringing their live app, and five refusals answering 200. **Section 12 is CLOSED** |
| 13 | AI author, MCP and chat | medium | **reviewed and fixed `6b7198d`**, ONE reviewer: 10 findings, **8 fixed, 0 rejected, 2 deferred**, 20 tests (the section had NO MCP test at all). **P0: the MCP doors overwrite a design in the user's library and graft the AI's part onto its version tree** - `build_design` with no name is called `untitled`, which is a real design with a real `.history/`, and `Document.save` is a plain overwrite; measured, the user's design DESTROYED. **P1: the AI's first CORRECT step was refused on 27 of the 50 saved designs**, for a rule about features the USER drew - three refusals, give-up, snapshot restored, 'I did NOT change your design'. Plus `done` judged on the whole tree; the catalogue advertising three `polar_pattern` axis values the op refuses by name; `list_operations` handing a calling AI the step-loop prompt as `build_design`'s conventions; **`verify_step` answering `matches_spec: true` for requirements it never checked** (an unknown key dropped silently, `size: [40, 30]` never comparing Z) while its docstring calls an empty mismatch list a proof; `design_compressor` answering a degenerate duty with a ZeroDivisionError. **Round two `0cc2faa`: round one opened the ADD door and left the EDIT door shut** - an AI edit to a user's feature was still refused for that feature's own pre-existing problem, 27 of 50 again; `lint_tree(only=)` is deleted and replaced by a BASELINE (what the tree already broke at job start; only what is new or worse is reported), 27 -> 0. Also `_MINE` was a promise made once and never re-checked, so the AI overwrote the user's edits to its own design. **Round three `d369595`: the replaced mechanism was put to the kernel rule by rule, and the ONE rule whose key could not carry its question was wrong** - the blob rule lost its owner test, so the AI refused to extrude a sketch the USER drew by hand (5+ shapes), gave up, and said 'I did NOT change your design' a third time. Verified: the baseline cannot MASK a fault the AI introduces (every other key carries the feature id, `Document.add` refuses duplicates, the baseline is the first statement of the job; every masking attempt refused), `AUTHOR_PROMPT` is byte-identical to before the split, 0 of 50 designs carry a spec key the new `checked_spec` refuses. **Section 13 is CLOSED** (three rounds, 16 findings, 32 tests) |

Skipped on purpose: **Shell** (rebuilt on the framework next; reviewed then),
**the crash supervisor** (`supervise.py`, reviewed 517f2f6), the prototype
leftovers `assembly.py`, `impeller.py`, `engine.py`, `check.py`, `generate.py`
(not reached by Studio or the MCP server).

---

## Section 1 - Sketcher

Paste line:
```
/code-review high sketch.py sketch_trim.py sketch_snap.py sketch_corner.py static/js/sketcher.js static/js/sketch3d.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 1 and the output format
```

The 2D editor the user draws profiles with before extruding, revolving or
cutting them. Never reviewed as a whole.

| File | Lines | Role |
|---|---|---|
| `static/js/sketcher.js` | 2082 | tools (line, rectangle, circle, polygon, path with arcs, image trace), snapping (`smartSnap`, `collectSnapPoints`, `sketchSnap`), drag handles and resize (`entityHandles`, `resizeGrab`, `applyResize`, `pointerDown/Move/Up`), the scale gizmo (`scaleSel` ... `commitScale`), modify ops (`mirrorEntity`, `duplicateEntity`, `offsetEntity`), trim (`fetchTrimPieces`, `trimClick`), dimension editing (`buildDimEditor`, `drawDimFields`, `routeDigitToDrawBox`, `commitDrawDims`), enter/exit/finish/cancel and the did-anything-change test (`sameSketch`, `stableJson`, `finishEmpty`), sketching on a body face (`openSketchOnFace`, `fetchFaceOutline`) |
| `static/js/sketch3d.js` | 439 | the sketch plane inside the 3D viewport: frame, grid, flat-on view, orbit-up, screen-to-plane pointer mapping |
| `sketch.py` | 1-698 | **in scope:** `entity_schema`, `_validate_dims`, `_entity`, `_compose`, `_path_face`, `make_sketch`, `sketch_plane`, `named_face`, `face_plane`, `face_sketch_plane`, `_face_frame`, `face_outline_2d`, `pick_face`, `sketch_on_face`, `_signed_area`. **Out:** `collapse_offset` and everything below (extrude, taper, revolve, hole, loft, sweep - section 7 and the reviewed tools) |
| `sketch_trim.py` | 429 | `trim_pieces` splits entities at intersections, `trim_apply` rebuilds entities from the kept faces; `_pick_face`, `_face_contains` |
| `sketch_snap.py` | 176 | the model-snap backend of `/api/sketch/snap`: `plane_of`, `plane_of_frame`, `snap_geometry` (body edges projected into the sketch plane) |
| `sketch_corner.py` | 252 | the tree's editable path arc radius: `path_arcs`, `set_arc_radius`, `_corner_solve`, `circumradius` (a corner arc re-filleted tangent) |
| `studio.py` | - | the sketch endpoints only: `/api/sketch-mesh/{feature_id}` (l.1592), `/api/face-outline` (1638), `/api/sketch/snap` (1671), `/api/sketch/trim/pieces` (1686), `/api/sketch/arc-radius` (1697), `/api/sketch/trim/apply` (1710), `/api/sketch/kinds` (2633) |
| `toolplan.py` | - | `plan_sketch` (l.538) only: the plane frame the sketcher draws on |

Tests for orientation (fast): `tests/test_e2_sketch.py`, `test_e5_sketch_on_face.py`,
`test_sketch_corner.py`, `test_sketch_snap.py`, `test_sketch_trim.py`,
`test_face_outline.py`. Browser (read, do not run):
`tests/e2e/test_face_sketch_in_viewport.py`, `test_sketch_empty_exit.py`,
`test_sketch_scale.py`, `test_model_snap.py`.

Finding classes, in order of harm:
- **The saved sketch differs from what was drawn** - coordinates, arc
  via-points, path closure, entity `mode` (add/cut), the `x, y` offsets that
  some entities carry and others do not.
- **A change silently dropped or silently applied** - `sameSketch` /
  `stableJson` decide whether an edit rebuilds; a false "same" loses an edit.
  Typed values (`commitDrawDims`, `routeDigitToDrawBox`) versus dragged ones.
- **Snapping moves a point the user did not intend** - a stale model point
  after the body changed, a point on another plane, past the 0.1 mm grid
  floor; exact circle centres and design-centre snaps are meant to be exact.
- **A pointer state machine that gets stuck** - draw, resize, scale, trim,
  path and image trace share one canvas and one `pointerDown/Move/Up`; a
  tool switch, Escape, double-click or lost `pointerup` that leaves a flag set.
- **Async races** - `openSketchOnFace`, `fetchFaceOutline`, `fetchPlaneFrame`,
  `fetchTrimPieces` are awaited while the user can still click. The
  `enterMode` race is known; report a *different, concrete* one only.
- **Trim** - pieces computed from one sketch state and applied to another;
  `_pick_face` / `_face_contains` tolerances; entities returning from
  `trim_apply` with a different kind or orientation.
- **Corner arcs** - `set_arc_radius` on a corner whose neighbours are too
  short for the radius, on a closed path's first/last corner, or on a path
  whose arc list and point list disagree in length.
- **Face sketches** - the outline and frame come from the server; any JS that
  derives a normal, an axis or an "up" itself (rule R1).
- **Validation gaps in `sketch.py`** - zero radius, zero-length line,
  self-intersecting or open path, a polygon with two identical points, NaN or
  string numbers from the JSON, reaching build123d unchecked.

Where to look hardest: `pointerDown/Move/Up` and what `setTool` /
`cancelSketch` reset; `commitDrawDims` and `applyResize` (two writers of the
same fields); `sameSketch` / `stableJson`; `openSketchOnFace` -> `enterMode`
when the plan or outline arrives after the user moved on;
`sketch_trim._pick_face`; `sketch_corner._corner_solve`.

Section-specific known items: `face_sketch_plane` snaps a face tilted under
25 degrees to the nearest principal plane (deliberately parked, section 10
P2); the five `loadMesh()` calls (P3).

---

## Section 2 - Document core and feature tree

Paste line:
```
/code-review high document.py static/js/tree.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 2 and the output format
```

The feature tree and the document that rebuilds it. Every tool sits on this;
a wrong body after an edit, rename, delete or strike is the P0 class. Only
single fixes were reviewed (36584e1: tree wipe on delete, refusals as 400,
clockwise polygons), never the module.

| File | Lines | Role |
|---|---|---|
| `document.py` | 1481 | `Feature` (l.291), `Document` (l.319): `add`, `edit`, `edit_many`, `check_params`, `param_names`, `param_refs`, `rename`, `remove`, `remove_plan`, `_delete_plan`, `_orphan_sweep`, `_passthrough`, `strike`, `unstrike`, `rebuild`, `_eval`, `_signature`, `_cache_get/_put`, `_mark_stale`, `_heal_stranding_cuts`, `_check_pieces`, `_check_dangling`, `_result_feature`, `result*`, `consumed_ids`, `leaf_solid_ids`, `to_data`, `from_data`, `save`, `load`. Module helpers `op_params`, `_min_inputs`, `_kind_of`, `_deep_valid`, `n_solids`, `_canon_number`, `_delete_summary`, `SEEDED_OPS`, `REF_PARAMS`. **Out:** the boolean semantics of `_fuse/_cut/_intersect/_loft` themselves (section 4) |
| `static/js/tree.js` | 1006 | `renderDoc`, `buildRow`, `buildBody`, `selectFeature`, `beginEdit` / `beginEditWith` / `applyEntity`, `beginRename`, `strikeFeature` / `restoreFeature`, `deleteFeature`, `revealFeature`, the parameter editors (`genericFields`, `genericRadius`, `genericGeometry`, `pointsTable`, `pathArcRows`, `entRow`, `modeToggle`), `renderWarnings` / `failMessage`, `applyTreeFilter` / `initTreeFind`. **Out:** the shape catalogue editors (`shapeCatalog`, `diameterRow`, `shapeList`, section 5) |
| `studio.py` | - | `/api/doc` (987), `/api/edit` (1625), `/api/feature/params` (1719), `/api/feature/add` (1734), `/api/feature/remove` (2128), `/rename` (2153), `/suppress` (2168), `/strike` (2182), `/api/undo` (2216), `/redo` (2241), `/rollback` (2268) |

Tests for orientation (fast): `test_tree.py` 23, `test_delete_repair.py` 20,
`test_strike.py` 6, `test_strike_visibility.py` 3, `test_p0_fixes.py` 13,
`test_p1_fixes.py` 12, `test_rebuild_cache.py` 13, `test_core.py` 16,
`test_pieces_warning.py` 7, `test_polygon_winding.py` 7, `test_api.py` 25.
Browser (read only): `tests/e2e/test_tree_delete.py` (five red, known),
`test_tree_history.py`, `test_tree_shape_edit.py`.

Finding classes:
- **A rebuild serves a stale body** - `_signature` / `_cache_get` /
  `_mark_stale` after a param edit, rename, strike, suppress or reorder; a
  cache key that ignores a field the op reads.
- **Delete and strike take too much or too little** - `_delete_plan`,
  `_orphan_sweep`, `_passthrough`, `_heal_stranding_cuts`: a healed or
  re-pointed cut is a changed result the user did not ask for; the
  2026-08-31 tree wipe is the class.
- **References not walked** - `REF_PARAMS` / `SEEDED_OPS`: rename, delete,
  strike, unstrike must reach every seed, target, face and sketch reference;
  a dangling reference that resolves to *something else* instead of failing.
- **The edit guard** - `op_params` / `check_params`: a key the op cannot take
  accepted, a legal one refused, a number arriving as a string or with a
  unit; `edit_many` applying half a batch.
- **File round trip** - `from_data` on an older file changing meaning (legacy
  forms of axis, plane, seed), `to_data` dropping a field, `load` of a file
  with an unknown op.
- **Health verdicts** - `_deep_valid`, `n_solids`, `_check_pieces`,
  `_check_dangling`: a multi-solid or invalid result reported as one healthy
  body, or a healthy one refused.
- **tree.js editors** - `applyEntity` and the generic editors writing into the
  wrong field, the wrong entity index, or with a string type; a struck or
  suppressed row that still accepts an edit; `renderDoc` losing the selection
  or the open editor on a doc event.
- **Undo / redo / rollback** - a snapshot restored into the wrong tab, or a
  refused step leaving the redo line inconsistent (`_unsnapshot`).

Where to look hardest: `_delete_plan` with `_orphan_sweep`; `_signature` and
what it omits; `strike` / `unstrike` with struck ancestors and the folded
combiner that has no tree node; `applyEntity`; the `suppress` endpoint's
effect on a final boolean.

Section-specific known items: a suppressed final boolean promotes its TOOL to
the result (section 10, P1) - report it only if you name the line that does it.

---

## Section 3 - Version tree and session persistence

Paste line:
```
/code-review high history.py backfill.py static/js/versions.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 3 and the output format
```

Per-design version history in `designs/<name>.history/`, the version panel,
and the tab session that survives a server restart. Data loss is the P0 class
here. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `history.py` | 807 | `History` (l.221): `_load`, `_save`, `_write_atomic`, `snapshot`, `append`, `set_current`, `star`, `relabel`, `amend`, `delete_after`, `delete`, `rename`, `protected`, `prune`, `repair`, the tree queries (`children`, `roots`, `ancestors`, `leaves`, `branch_points`, `depths`, `tree_lines`); `diff_snapshots`, `content_hash`, `_change_note` |
| `backfill.py` | 254 | migration of pre-history designs into `.history/` |
| `static/js/versions.js` | 414 | `paint`, `row`, `descendantsOf`, `removeAfter`, `remove`, `toggleDiff`, `rename`, `restore`, `refresh`; the dirty dot and the three-way close prompt |
| `studio.py` | - | the tab model and session: `_new_tab` (140), `_find_tab` (163), `_tabs_json` (231), `_persist_session` (263), `_restore_session` (278), `/api/tabs` (996), `/switch` (1001), `/close` (1015), `/api/new` (1028), `/api/open/{file}` (2570), `/api/designs` (2556); the versions API: `/api/save` (2283), `/api/versions` (2298), `/diff` (2317), `/restore` (2341), `/star` (2409), `/amend` (2426), `/delete_after` (2456), `/delete` (2474), `/label` (2493) |

Tests for orientation (fast): `test_history.py` 73, `test_version_api.py` 60,
`test_session_restore.py` 5, `test_tab_reuse.py` 13, `test_backfill.py` 21.
Browser (read only): `tests/e2e/test_version_panel.py`, `test_tree_history.py`,
`test_recovery.py`. Design notes: `VERSION-TREE-PLAN.md`.

Finding classes:
- **A version is not what was saved** - `content_hash` vs the snapshot
  written, `amend` (update vN in place) vs `append` (push vN+1) choosing wrong,
  the dirty flag lying in either direction.
- **A version or the current pointer is lost** - `delete`, `delete_after`
  (renumbers), `prune`, `repair`, `protected`; restore of a version whose
  snapshot file is missing or unreadable; `_write_atomic` on Windows when the
  target exists or is open in another tab.
- **Two tabs, one design** - the same design open twice, or the same
  `.history/` written by two tabs; `_find_tab` reuse rules.
- **Session restore** - a tab restored on the wrong design or version, unsaved
  edits dropped or duplicated after a restart, the per-port session file, the
  supervisor's `TEXTCAD_RECOVERED` / `TEXTCAD_SAFE_RESTORE` path read here.
- **Open and save** - a design written under another name (the path
  sanitising itself is known P2; a *wrong file written* is a finding),
  `/api/new` colliding with an existing name.
- **versions.js** - the row acted on differs from the row shown
  (`descendantsOf`, `removeAfter`, `restore` after a `refresh`), the close
  prompt discarding when it said keep, `toggleDiff` on a stale pair.
- **backfill** - a migrated design whose v1 differs from the file it came
  from.

Where to look hardest: `delete_after` and `repair`; `_persist_session` when
the server is mid-request; `restore_version` (studio.py 2342) and what it
does to the tab's dirty state; `versions.js` `remove` / `removeAfter`.

---

## Section 4 - Booleans and transforms

Paste line:
```
/code-review high document.py blocks.py toolplan.py - read REVIEW-QUEUE.md first: the header, the shared rules, section 4 and the output format; in these three files review ONLY the functions section 4 names
```

Join, Cut, Intersect, Loft as combiners; Move, Rotate, Scale as transforms;
the default cut target. These change bodies silently, which is why they rank
here. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `document.py` | 60-110 | the ops table, `_fuse`, `_cut`, `_intersect`, `_loft`, `COMBINERS`, `_kind_of`, `_min_inputs`; the combiner folding (a combiner that has no tree node), `_result_feature`, `consumed_ids`, `leaf_solid_ids`, `_check_pieces`, `_heal_stranding_cuts` as they apply to booleans |
| `blocks.py` | 196-222 | `rotate`, `scale_uniform`, the `move` entry of the ops table (l.933); `mirror_copy` (204) is the legacy form now owned by Mirror, reviewed - read for context only |
| `toolplan.py` | 149-207 | `_latest_descendant`, `_default_target`, `_pick_face`, `_flat_or_raise`, `_pick_body`: which body a cut or a face pick lands on when several exist |

Tests for orientation (fast): `test_s3_bodies.py` 6, `test_e1_ops.py` 10,
`test_core.py` 16, `test_delete_repair.py` 20 (cuts self-heal),
`test_pieces_warning.py` 7, `test_export_guard.py` 18 (multi-body), and the
corpus in `tests/gauntlet.py` (read it; do not run every gauntlet).

Finding classes:
- **A boolean result that is several solids reported as one body**
  (`n_solids`, `_check_pieces`), or the TOOL body surviving as the result.
- **Touching, not overlapping** - fuse or cut of bodies that share a face or
  an edge producing a non-manifold or invalid "success" (rule 5); an
  intersect with no overlap returning an empty solid as OK.
- **Transforms about the wrong point** - `rotate` / `scale_uniform` about the
  world origin when the body sits off-origin, or about a centre that moves
  with an earlier edit; a transform of a body that carries a sketch plane
  (the Mirror lesson: `Shape.mirror` copied the sketch's plane along).
- **The default target** - `_default_target` / `_pick_body` choosing a body
  other than the one under the sketch when several exist, or a struck one.
- **Input order after a delete or strike** - a cut whose tool and target
  swap, or a fuse that loses one input silently.
- **Loft** - profiles on the same plane, mismatched vertex counts, a loft of
  a single profile, reaching the kernel unchecked.

Where to look hardest: `_cut` and `_heal_stranding_cuts` together;
`_default_target`; `_check_pieces` thresholds; `scale_uniform`'s centre.

Section-specific known items: a suppressed final boolean promotes its tool
(P1) - name the line if you find it; `blocks.py` calling `is_valid()` as a
method inside a bare except (section 10 P2, line has shifted since) belongs to
section 5.

---

## Section 5 - Primitives and shape editing

Paste line:
```
/code-review high blocks.py static/js/tree.js static/js/placement.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 5 and the output format; in blocks.py and tree.js review ONLY the functions section 5 names
```

The primitives (Box, Cylinder, Sphere, Cone, Pipe, Hex, Polygon, Turn
profile, Blade, Centre bore, Bolt circle), the shape editors in the tree, and
placing a new primitive in the viewport. The AI's main building path; a
dimension landing in the wrong parameter is the P0 class. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `blocks.py` | 52-183, 599-668, 945-1012 | `plate`, `disc`, `ball`, `cone`, `tube`, `polygon_plate`, `hex_plate`, `revolve_profile`, `curved_blade`, `_tall_cutter`, `with_center_hole`, `with_bolt_circle`; the legacy `polar_pattern` (183) and `linear_pattern` (222) that the AI may still emit; `_plain_cause`, `_finish` (the health check every op returns through), `api_summary`, `_signature`, the ops table (933). **Out:** the fillet/chamfer, edge and face resolvers (reviewed), import (section 8), `shell_out` (rebuilt next) |
| `static/js/tree.js` | - | `shapeCatalog`, `shapeList`, `diameterRow`, `genericFields`, `genericRadius`, `genericGeometry`, `staleCatalogNote`, `renderSpecRow`, `round`, `circumR` |
| `static/js/placement.js` | 115 | `PLACEABLE`, `startPlacement`, `closePlacePopup`; with `viewport.beginPlacement` / `cancelPlacement` (viewport.js 472-480) |
| `studio.py` | - | `/api/ops` (2640), `/api/feature/add` (1734) for blocks |

Tests for orientation (fast): `test_shape_params.py` 9,
`test_placement_defaults.py` 2, `test_e1_ops.py` 10, `test_core.py` 16,
`test_api.py` 25. Browser (read only): `tests/e2e/test_tree_shape_edit.py`,
`test_washer_resize.py`, `test_bodies_visible.py`.

Finding classes:
- **A tree edit lands in the wrong parameter or unit** - `diameterRow` is
  exactly the radius/diameter seam; `round` and `circumR` (hex and polygon
  size conventions); a field shown for one op and written to another.
- **Degenerate parameters reaching the kernel** - zero or negative height,
  `tube` inner >= outer, `cone` top >= bottom, a bolt circle whose holes
  overlap the bore or each other, a blade with zero chord: rule 5 both ways.
- **Placement re-deriving the frame** - `placement.js` computing where the
  primitive lands from viewport maths instead of the plan (rule R1); a
  placed primitive whose stored origin differs from the ghost shown.
- **`_finish` and `_plain_cause`** - a kernel message reaching the user
  verbatim, a wrong sentence, or an invalid result passing `_finish`; the
  `is_valid()` method-vs-property fast path (say what it does now).
- **The legacy patterns** - `polar_pattern` / `linear_pattern` in blocks.py
  versus the Pattern tool's `pattern.py`: a design file naming the legacy op
  rebuilding differently.
- **`api_summary` / `_signature`** - the catalogue the AI and the tree read
  disagreeing with what the op accepts.

Where to look hardest: `diameterRow` and `genericFields`; `_finish`;
`with_bolt_circle`; `startPlacement`.

---

## Section 6 - Measure and drive

Paste line:
```
/code-review high measure.py static/js/measure.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 6 and the output format
```

The measure tool and type-a-dimension drive. A driven dimension REWRITES a
feature parameter, so a wrong resolver is silent wrong geometry. The rule is
driven-vs-derived (`MEASURE-PLAN.md`). Never reviewed.

| File | Lines | Role |
|---|---|---|
| `measure.py` | 1340 | `resolve`, `_measure_one`, `_measure_two`, `_full_circles`, `_min_distance`, `_closest_on_axis`, `_plane_cache` / `_plane_sig` / `_sketch_plane` / `_build_plane`, `_face_index_for`, `_hole_driver`, `_diameter_driver`, `resolve_driver`, `_face_role`, `_entity_dim_for_direction`, `resolve_pair_driver`, `resolve_move`, `plan_move`, `plan_set`, `_to_param`, `write`, `probe`, `measure` |
| `static/js/measure.js` | 460 | `openMeasure`, `cancelMeasure`, `run`, `paintPicks`, `armProbe` / `paintProbe` / `sendProbe`, `showEdit` / `applyEdit` / `readOnlyReason` |
| `static/js/viewport.js` | 1995-2114, ~2190 | `showDimension`, `clearDimension`, `setDimProbe`, `setDimProbeFrozen`, `clearDimProbe`, `initDimDrag`, `nudgeDimFrom`, `paintDimLabel`, `dimEnd` |
| `studio.py` | - | `/api/measure` (2010), `/api/measure/probe` (2047), `/api/measure/set` (2061) |

Tests for orientation (fast): `test_measure.py` 32, `test_measure_api.py` 10,
`test_measure_drive.py` 23, `test_measure_move.py` 11. Browser (read only):
`tests/e2e/test_measure_picks.py`, `test_measure_probe.py`, `test_dim_box.py`.

Finding classes:
- **A typed value writes the wrong parameter** - `resolve_driver`,
  `resolve_pair_driver`, `_to_param`, `write`: wrong feature, wrong key, wrong
  sign or offset (a distance to a face vs a sketch offset), a diameter written
  as a radius.
- **Derived offered as driven** - `readOnlyReason` and `_face_role`: a
  dimension that depends on two features editable as if it drove one.
- **The number is wrong** - curved-to-curved minimum distance, axis offsets,
  a full circle vs an arc (`_full_circles`), `_plane_cache` serving a plane
  from before a rebuild (`_plane_sig`).
- **Move** - `resolve_move` / `plan_move` moving a different feature or by a
  vector in the wrong frame (rule R1 applies on the JS side too).
- **Stale picks** - a pick on a body id from before a rename or rebuild
  answering on another body.
- **The probe** - `probe` and `sendProbe` disagreeing on units or frame; a
  frozen probe surviving a doc change.

Where to look hardest: `resolve_driver` and `_diameter_driver`; `_to_param`;
`_plane_cache`; `applyEdit`.

Section-specific known items: `measure.js`'s one awaited `loadMesh()` (P3);
MEASURE-PLAN P3/P4 (pinned dimensions, named parameters) are not built, so
their absence is not a finding.

---

## Section 7 - Extrude as a whole module (with loft and sweep)

Paste line:
```
/code-review medium sketch.py toolplan.py static/js/extrude.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 7 and the output format; in sketch.py and toolplan.py review ONLY the functions section 7 names
```

Extrude was reviewed three times as a DIFF (taper dae2c5f, the framework
rebuild 6cc526a, direction/panel fixes) but never as one module, and loft and
sweep (AI-only ops, no tool UI) were never reviewed at all. Fresh eyes go to
the cut and through paths, `_shapefix`, `collapse_offset`, loft and sweep.

| File | Lines | Role |
|---|---|---|
| `sketch.py` | 699-1122, 1478-1510, 1631-1668 | `collapse_offset`, `_apex_cap`, `_taper_offset_problem`, `_tapered_extrude`, `_tapered_extrude_face`, `_same_side`, `_taper_loft`, `_shapefix`, `extrude_face`, `_fusion_taper`, `extrude_sketch`, `face_profile`; `through_reach`, `material_depth` (shared with Hole); `loft_sketches`, `sweep_sketch`, `is_sketch` |
| `toolplan.py` | 207-340 | `plan_extrude`, `_edit_input`, `_sketch_part`, `_profile`, `_coincides`, with `_limits` / `_collapse` (93-135) |
| `static/js/extrude.js` | 266 | the tool declaration: `openExtrude`, `initExtrude` |
| `static/js/viewport.js` | 978-1250, 1449-1491 | the arrow, second arrow, ghost and taper ring (`beginExtrudeArrow` ... `secondArrowAxisScreen`, `projectAmount`, `arrowGrab/Drag/Release`) |
| `studio.py` | - | `/api/face-feature` (1994): extrude_face from a picked face |

Tests for orientation (fast): `test_extrude_v1.py` 15, `test_through_cut.py` 18,
`test_taper_apex.py`, `test_taper_direction.py`, `test_face_workflow.py` 6,
`test_offset_method.py`, `test_toolplan.py` 15. Gauntlet: `test_taper_gauntlet.py`
(read; run only if a fix touches taper). Browser (read only):
`tests/e2e/test_edit_extrude.py`, `test_extrude_cut_target.py`,
`test_extrude_direction.py`, `test_extrude_ok_commits.py`, `test_modal_taper.py`,
`test_face_to_feature.py`, `test_small_face_and_fold.py`.

Finding classes:
- **A through cut that does not go through** - `through_reach` /
  `material_depth` measured on a body that a later feature extends; a cut that
  stops a hair short and leaves a skin.
- **The wrong target** - when several bodies exist (also section 4's
  `_default_target`), or a cut that finds nothing and reports success.
- **Extents** - Two sides / Symmetric measured or signed wrong; an amount of
  0 or a negative amount reaching the kernel.
- **`_shapefix`** - a repaired solid is a DIFFERENT solid; repair that
  changes volume beyond tolerance without a note (rule 5, quietly).
- **`collapse_offset`** - a face sketch's offset folded into the extrude on the
  wrong side, or twice.
- **Loft and sweep** - profiles on one plane, mismatched vertex counts, one
  profile, a self-intersecting path, reaching build123d unchecked; a sweep
  along a path that is not planar.
- **The arrow** - `projectAmount` vs the plan's axis (rule R1); the arrow's
  amount and the box disagreeing after a drag ends off-canvas.

Section-specific known items: the taper ring can start off-canvas (P3); the
25-degree face snap (P2); "a value typed before the plan arrived" (P3).

---

## Section 8 - Import STL and STEP

Paste line:
```
/code-review medium meshrepair.py blocks.py static/js/dialogs.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 8 and the output format; in blocks.py and dialogs.js review ONLY the functions section 8 names
```

An external STL becomes a solid through a repair pipeline; a STEP becomes an
exact body. The invalid-solid class (rule 5) is the risk. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `meshrepair.py` | 359 | `parse_binary_stl`, `to_binary_stl`, `edge_counts`, `duplicate_triangles`, `signed_volume`, `is_clean`, `drop_duplicate_walls`, `split_components`, `collapse_repair`, `voxel_remesh`, `decimate_guarded`, `repair_stl_mesh` |
| `blocks.py` | 696-943 | `_stl_triangles`, `_ascii_stl_to_binary`, `_stl_bytes_to_solids`, `_read_stl_solids`, `_resolve_stl_path`, `import_stl`, `_resolve_step_path`, `import_step`, `import_stl_report` |
| `static/js/dialogs.js` | 80-128 | `actionImportStl` (one button, routed by extension) |
| `studio.py` | - | `/api/import-stl` (1932, `import_stl_file`), `/api/import-step` (1885, `import_step_file`) |

Tests for orientation (fast): `test_import_stl.py` 19, `test_import_step.py` 8,
`test_mesh_pipeline.py` 9.

Finding classes:
- **A wrong solid reported as OK** - inverted normals (`signed_volume` sign),
  `is_clean` thresholds, a multi-shell STL imported as one body or the
  largest shell only without saying so.
- **Repair that changes the part silently** - `voxel_remesh`,
  `decimate_guarded`, `collapse_repair`: how far did the surface move, and is
  that in the report (`import_stl_report`)?
- **Format detection** - a binary STL whose header starts with `solid`; an
  ASCII STL with Windows line endings; a STEP with several solids or a
  compound; a zero-triangle file.
- **Paths** - `_resolve_stl_path` / `_resolve_step_path` escaping `imports/`,
  name collisions overwriting an earlier import (the 48 leftover files are
  known, section 10 P2; the collision is not).
- **The body in the tree** - a `Part` wrapping a compound with volume 0
  (recorded gotcha), body ids after import, the forced mesh reload.
- **Cost** - only if quadratic in triangles (`edge_counts`,
  `duplicate_triangles`).

---

## Section 9 - Trace image

Paste line:
```
/code-review medium imgtrace.py static/js/sketcher.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 9 and the output format; in sketcher.js review ONLY the image-trace functions section 9 names
```

"Trace Image" in the sketch ribbon: a PNG/JPG/SVG becomes polygon entities
in the open sketch, auto-fitted to a face sketch including a 90-degree
auto-rotate. Small; may share a chat with section 8. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `imgtrace.py` | 216 | `_mask_from_image`, `artwork_aspect`, `_bridge_pieces`, `_chaikin`, `_round_pts`, `_poly_entity`, `image_to_entities` |
| `static/js/sketcher.js` | - | the trace tool only (grep `trace`): rasterising SVG/JPG in the browser, the fit to the face outline, the auto-rotate, the insert into the sketch |
| `studio.py` | - | `/api/trace-png` (1832) |

Tests for orientation (fast): `test_trace.py` 9.

Finding classes:
- **Entities that section 1 would refuse** - self-intersecting polygons,
  duplicate consecutive points, fewer than 3 points, produced here and handed
  to `sketch.py`.
- **Orientation** - image y-down vs sketch y-up; the auto-rotate applied
  twice, or not at all, on a face sketch; mirror-image artwork.
- **Scale and fit** - `artwork_aspect` vs the face outline; a fit that
  overflows the face; sub-0.1 mm points after `_round_pts`.
- **Holes in the artwork** - nested contours: inner loops as `cut`, outer as
  `add`, and the nesting depth beyond two.
- **Input limits** - a huge image, an image with alpha only, a JPG with no
  dark pixels: a sentence, not a stack trace.

---

## Section 10 - Viewport, picking and face provenance

Paste line:
```
/code-review high static/js/viewport.js provenance.py static/js/provenance.js static/js/grid3d.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 10 and the output format; in viewport.js skip the per-tool gizmos section 10 lists as out of scope
```

The three.js scene, face/edge/body picking, the model loading that follows the
document (R3), and the face-to-feature attribution behind a click. The fillet
picking half was reviewed (4f15f66, 9bed191, e5ffb8d); the rest never.

| File | Lines | Role |
|---|---|---|
| `static/js/viewport.js` | 2443 | **picking first:** `pickAt`, `selectProfile`, `selectFace`, `selectEdge`, `faceGeometry`, `showPick`, `answerPick`, `profilePickAt`, `edgeHitAt`, `faceInfoAt`, `ndcFrom`, `planePickAt` / `planePickHover`, `buildOriginPlanes` / `clearOriginPlanes`, `hoverFaceAt`, `pickWhat`, `beginProfilePick` / `cancelProfilePick`, `beginEdgePick` / `endEdgePick`, `beginPlanePick` / `cancelPlanePick`. **Then the model side:** `loadMesh` (1752), `loadModel`, `addBodies` / `bodyMeshes`, `addSketches` / `sketchMeshes`, `disposeModel` / `disposeParts`, `follow`, `fitToObjects`, `clearMesh`, `showFeatureOverlay`, `showSelectionOverlay` / `clearSelectionOverlay`, `setView` (1596), `holdViewport` (1729), `buildControls`, `setOrbitUp`, `zoomFloor` / `wheelNotches` / `onWheelZoom`, `placeGround` / `groundFootprint` / `updateGroundGrid`, `modelExtent`. **Out:** the per-tool gizmos - extrude arrow and ghost, taper ring, axis line, plane quad, hole marker, revolve ghost, the dimension probe (sections 6, 7 and the reviewed tools); `visibleEdgeHit` / `ownFaceHit` (reviewed; re-check only how the two pickers share them) |
| `provenance.py` | 658 | which feature made this face: `topo_faces`, `surface_key`, `interior_point`, `OnFace`, `picked_faces`, `feature_index`, `edge_feature`, `attribute_face`, `_chain`, `_explain`, `_hosts`, `_sketch_behind`, `_extrude_behind`; `feature_faces` (369) was reviewed in e5ffb8d - read for context |
| `static/js/provenance.js` | 145 | `render`, `clear`: the face-to-feature answer shown to the user |
| `static/js/grid3d.js` | 140 | `gridStepFor`, `planeHalfFor`, `buildGridLines`, `viewFootprintOn`, `patchFor` |
| `studio.py` | - | `/api/mesh.stl` (1061), `/api/model` (1515), `/api/feature-mesh/{id}.stl` (1606), `/api/face-feature` (1994) |

Tests for orientation (fast): `test_face_provenance.py` 17,
`test_face_workflow.py` 6, `test_mesh_pipeline.py` 9. Browser (read only):
`tests/e2e/test_camera_zup.py`, `test_adaptive_grid.py`, `test_zoom_limits.py`,
`test_origin_planes.py`, `test_bodies_visible.py`, `test_model_snap.py`.

Finding classes:
- **The click lands on something else** - depth-only rules where topology is
  needed (the fillet lesson), the ground plane or a sketch mesh eating a
  click, a hidden face selected, `ndcFrom` off by the canvas offset after a
  resize.
- **Stale ids** - body ids after a rename or rebuild (`geom_version`), a
  highlight or overlay on the wrong body, `follow` skipping a doc event.
- **Attribution** - `attribute_face` naming the wrong feature:
  `surface_key` tolerances, `interior_point` on coplanar faces, a trimmed
  survivor after a later cut, a face two features could claim.
- **Rule R1** - any frame, normal, axis or origin derived in JS from mesh
  geometry instead of a plan or doc field.
- **Rule R3** - the scene refreshed by a tool, or refreshed twice for one
  doc event, or not at all for an event kind.
- **Camera** - orbit-up flip, `zoomFloor` trapping the user on a small part,
  `fitToObjects` on an empty scene.
- **Disposal** - geometries and materials not disposed per rebuild (only if
  it grows per rebuild).

Section-specific known items: a tree row click's own STL highlight racing a
face click's plan on the kernel (P2); the R3 `loadMesh` calls in sketcher and
measure (P3); the `enterMode` race (P3).

---

## Section 11 - Tool framework core

Paste line:
```
/code-review medium static/js/tool.js toolplan.py static/js/dialogs.js static/js/api.js static/js/ask.js static/js/ribbon.js static/js/main.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 11 and the output format; in toolplan.py review ONLY the shared helpers and plan() that section 11 names
```

The framework every tool declares itself on, the plan request path, the
dialogs and the API layer. Reviewed only piecemeal, tool by tool.

| File | Lines | Role |
|---|---|---|
| `static/js/tool.js` | 1028 | `tool()`, `fill`, `currentSelection`, `waitForRow` / `dropRowWait`, `boolOf`, `isolateFor` / `releaseIso`, `pickedBody`, `activeToolFeature`, `toolSessionOpen`, `canEdit`, `editFeature`, `cancelTool`, `humanProblem`, `setBox`, `num`, `say`; the one-way Cancel/OK guard and Esc |
| `toolplan.py` | 51-207, 1242 | `_vec`, `_frame`, `_axis_name`, `_project_wire`, `_loops`, `_limits`, `_collapse`, `_world`, `_feature`, `_solids`, `_latest_descendant`, `_default_target`, `_pick_face`, `_flat_or_raise`, `_pick_body`, `plan()`; with the `ToolPlanReq` model and `/api/tool/plan` (studio.py 1660) |
| `static/js/dialogs.js` | 423 | `modalGuard`, `actionNew` / `Save` / `Open` / `Export` / `Undo` / `Redo` / `Examples`, `loadSample`, `openFeatDialog`, `initDialogs`, `actionSpec` |
| `static/js/api.js` | 135 | `setBusy` / `clearBusy` / `isBusy`, `getJSON`, `postJSON`, `planRequest` (the queue), `waitForServer`, `noteRecovery` |
| `static/js/ask.js` | 125 | `askText`, `askConfirm`, `askThree`, `askNumber` (no native dialogs) |
| `static/js/ribbon.js`, `main.js`, `bus.js`, `state.js`, `icons.js` | 225, 108, 10, 15 | the tabs and buttons, boot order, the event bus, shared state `S` |

Tests for orientation (fast): `test_toolplan.py` 15, `test_launch_rules.py` 5,
`test_api.py` 25. Browser (read only): `tests/e2e/test_user_workflow.py`,
`test_extrude_ok_commits.py`, `test_recovery.py`.

Finding classes:
- **Cancel / OK / Esc** - a preview feature removed twice or left behind, an
  OK that commits after a Cancel, Esc during an awaited plan.
- **The plan queue** - `planRequest`: a stale plan answering a newer click,
  a busy flag stuck after a failed request, two tools' plans interleaved.
- **Edit** - `editFeature` reverting to the wrong params on Cancel, or the
  select following a default instead of the stored value (known for five
  tools as P3; report only a NEW instance).
- **`ToolPlanReq`** - a field a tool sends that pydantic drops (the `own_id`
  lesson); a field typed wrong (string for a number).
- **Dialogs** - `modalGuard` letting two dialogs stack, `askNumber` returning
  a string, a dialog action running on the wrong tab.
- **Recovery** - `noteRecovery` and `waitForServer` after a supervisor
  relaunch: a stale tab list, a request replayed.
- **Ribbon** - a button reaching a tool in the wrong mode; an op missing from
  `icons.js` so it is invisible in the tree.

Section-specific known items: five tools hand-type the plan wait (P3); tool
panels cover the chat column (P2); the one-way Cancel/OK guard and Esc were
done in P4 (recheck, do not re-report the design).

---

## Section 12 - Server layer

Paste line:
```
/code-review medium studio.py - read REVIEW-QUEUE.md first: the header, the shared rules, section 12 and the output format; skip the endpoints other sections own
```

The FastAPI app minus the endpoints owned by other sections: setup, error
handling, refusals, the remaining endpoints, export, static serving. The STEP
export was reviewed (753c24c); recheck only the guard's blind spots.

| File | Lines | Role |
|---|---|---|
| `studio.py` | 2797 | app setup and middleware, `_user_env()` (API keys from the registry), the refusal path (`_refused`, every refusal answers 400), exception handlers; `/` (982), `/api/spec` (2200), `/api/examples` (2507), `/api/design-preview/{file}` (2545), `/api/sample/{name}` (2613), `/api/ops` (2640), `/api/export` (2646, `export_step`, `_export_blockers`), `/api/chat` (2688, the HTTP side only; the author is section 13), the supervisor handshake (`TEXTCAD_SERVER_CHILD`, `TEXTCAD_RECOVERED`, `TEXTCAD_SAFE_RESTORE`, the checkpoint), static file serving and cache-busting |
| `supervise.py` | 224 | reviewed (517f2f6) - read for context only |

Tests for orientation (fast): `test_api.py` 25, `test_export_guard.py` 18,
`test_tab_reuse.py` 13, `test_examples_gallery.py` 10, `test_supervisor.py`.
Browser (read only): `tests/e2e/test_examples_tab.py`, `test_recovery.py`.

Finding classes:
- **A wrong status** - 200 with `ok: false`, a 500 carrying a kernel message,
  a refusal as 200 (rule 5 at the HTTP layer).
- **Paths** - `/api/design-preview`, `/api/sample`, `/api/examples` building
  file paths from request data (open and export are known P2; the others are
  new).
- **Export** - `_export_blockers` missing a case (the multi-body lesson: 4 of
  50 designs once exported as little as 0.1%), a file name collision, the
  export of a struck or suppressed tree.
- **Concurrency** - a request mutating a tab another request reads (the
  kernel race itself is known; a *lock that is missing on a specific path* is
  new).
- **Secrets** - an API key in a log line, a response or an error page.
- **Binding** - the server reachable from outside the machine.

---

## Section 13 - AI author, MCP and chat

Paste line:
```
/code-review medium author.py mcp_server.py meanline.py static/js/chat.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 13 and the output format
```

The front door for the founding rule ("AI mistakes must never reach the
user"): the catalogue the AI reads, the parser of what it returns, the lint,
the MCP tools an outside AI calls, and the chat column. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `author.py` | 518 | `op_catalog`, `_catalog_text`, `_annotate`, `_parse`, `lint_tree`, `_to_document`, `author_design` |
| `mcp_server.py` | 227 | `_safe_name`, `_notify_studio` (the doorbell), `_report`, `list_operations`, `build_design`, `design_part`, `measure_step`, `verify_step`, `design_compressor` |
| `meanline.py` | 237 | the compressor design the MCP tool builds from (`design`, `to_spec`, `build_from_design`) |
| `static/js/chat.js` | - | the chat column: sending, applying the answer, showing warnings (recorded: chat warnings go unread) |
| `studio.py` | - | `/api/chat` (2688) |

Tests for orientation (fast): the author is exercised through `test_api.py`,
`test_offset_method.py`, `test_p1_fixes.py`, `test_tree.py`,
`test_extrude_v1.py`, `test_export_guard.py` (grep `author`); there is no
dedicated MCP test.

Finding classes:
- **Catalogue vs op** - `op_catalog` advertising a key the op refuses, or
  omitting one it needs; `document.op_params` is meant to be the single
  source (8b37426) - check the author reads it and nothing else.
- **The parser** - `_parse` accepting malformed or partial JSON and building
  something other than what the model said; a numeric string kept as a string.
- **Two entries, one guard** - `_to_document` and `build_design` bypassing the
  strict add that `/api/feature/add` enforces (unknown keys refused, health
  gate), so an AI tree lands unchecked.
- **The lint** - `lint_tree` letting through what it is meant to refuse
  (absolute-offset sketches once a body exists), or refusing a legal tree.
- **MCP** - `_safe_name` and path traversal on design names, `build_design`
  overwriting an existing design, the doorbell re-firing on every page load
  (known P1, section 10 - name the line if you find the cause).
- **Chat** - the model's answer applied to the tree without the health gate;
  a missing API key producing a stack trace instead of a sentence; a warning
  shown where the user does not look.
- **Claims** - `measure_step` / `verify_step` reporting a number or verdict
  that `inspector` would not give.

---

## After the review - the fix pass, in the SAME Opus chat

The same chat goes straight on to this once the report is in the chat. The
user types nothing (decided 2026-09-10).

1. Load the `textcad-dev` skill; `fusion-parity` too if the module is a
   modeling tool. Read CLAUDE.md's environment facts (two Pythons, detached
   server, hooks).
2. Take the findings in severity order. **Reproduce each by measurement
   first**: a probe under `probes/` or a test that shows the wrong number,
   the wrong body, the lost edit. A finding that does not reproduce is
   REJECTED with a one-line reason; it is not fixed "just in case".
3. For each confirmed finding: a test that is RED before the fix, then the
   smallest fix. Never `/code-review --fix`.
4. Run the section's fast test files plus `tests/test_launch_rules.py`. Run an
   op's gauntlet file only when the fix touches that op. `python -m ruff check .`
   on the changed Python; the edit hook runs `node --check` on JS. If anything
   under `static/` changed, bump `main.js?v=` (and `studio.css?v=` for CSS) in
   `static/index.html` after reading the current value.
5. One commit: `<Module> review fixes: N of M findings fixed, K rejected (<why, in a few words>); T new tests` with the project author flags, then push to
   the private backup. Record the line delta in the message.
6. If the backend changed, restart the user's server detached per CLAUDE.md
   and let it open the browser.
7. Update THIS file: the status board row (`reviewed <hash>, fixed <hash>,
   N/M`), and a "Done log" entry below with the rejected findings and their
   reasons. Add a LAUNCH-PLAN.md section 10 row only for a finding that was
   deferred rather than fixed or rejected.
8. A second review round happens only if a P0 was fixed: rewrite
   `REVIEW-BRIEF.md` for the fix commit with `Status: PENDING`, so the next
   `code review` picks the fix commit up first. Otherwise tell the user in
   one line, in plain words: what was found, what was fixed, whether their
   designs are affected, and that the next section waits for `code review`
   in a fresh Opus chat. There is no user checklist (retired 2026-09-10).

Token rules apply (LAUNCH-PLAN section 9): targeted test files, no gauntlet
sweeps, no screenshot loops, browser tests only if a fix changed a journey.

## Done log

### Section 1 - Sketcher (reviewed and fixed 2026-09-09, commit 556a611)

9 findings, all reproduced by measurement first
(`probes/sketcher_review_probe.py`). **9 fixed, 1 rejected**, and 2 of the
review's 5 "could not judge without running the app" items turned out to be
real and were fixed with them.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P0 | a hole drawn BEFORE its outer became solid material - `create()` forced entity 0 back to `add`. Measured 2827.43 mm2 where the editor drew a 2513.27 washer | the flip is gone; modes go up exactly as drawn |
| F2 | P0 | even-odd modes were right but the entities were never reordered; `_compose` is sequential, so an island drawn last was cut away. Measured 1570.80 vs 1884.96 mm2 | `_compose` composes OUTERS BEFORE THE HOLES INSIDE THEM, by measured containment (`_nesting_depth`) |
| F3 | P1 | an interactive Scale survived Cancel Sketch and owned the next sketch's keyboard; Escape wrote the DISCARDED entities into it | `scaleDrag` cleared in `exitMode()` and `resetEditor()` |
| F4 | P1 | `_path_face` had no validation: `Standard_TypeMismatch('TopoDS::Face')`, `StdFail_NotDone` and "Face can only be created with closed wires" reached the tree verbatim | `_validate_path` names the four real mistakes; a catch-all around `make_face()` keeps any other OCCT text out |
| F5 | P2 | Modify -> Offset grew a slot's height only, and at Offset 12 Finish blamed the slot | both dimensions grow, floored at `height + 0.5` |
| F6 | P3 | `rotation` on a polygon/path was built but never drawn: outline, handles, hit-test and snap read the raw points while `entSamplePts` rotated | one `entToSketch` helper; `applyResize` writes back through the local frame it already computes |
| F7 | P3 | the tree re-derived corner-vs-arc and got a CLOSED path wrong, promising a tangent round `set_arc_radius` does not give (R1) | new `POST /api/sketch/path-arcs` serves `path_arcs`, the same function the edit acts on; the row says "curve" until it answers |
| F8 | P3 | a bore's parameter seam was offered as a model "corner" and its antipode as a "midpoint" | closed edges give their centre only; arcs keep their real ends |
| F9 | P3 | reopening a path/polygon-only sketch framed the world origin | `entSamplePts`, not `[e.x, e.y]` |

**Promoted from "could not judge" to fixed:**

- the 8-sample `containedIn` walk really can call a mostly-nested shape (a
  traced outline with a spike) contained and turn it into a hole - it now
  tests every point, which is free at 48-96 points on an edit;
- an OCCT error really can escape `/api/sketch/trim/pieces` (it builds every
  entity's face and catches only `KeyError`/`ValueError`) - and it is the
  LIKELY case, since a crossing path is what a user reaches for Trim to
  clean up. F4's `ValueError` closes it; locked in by a test.

**Settled by reading, no change needed:**

- `commitScale()`'s stale readout is NOT hidden by `placeFloat`'s pane clamp -
  it goes to the chat via `bus.emit('msg', 'bot', ...)`, so it was plainly
  visible. Folded into F3.
- `sketch_on_face`'s docstring contradicted `face_sketch_plane` on the offset
  SIGN: it still promised "offset < 0 INTO the material ... on every face",
  a rule abandoned on 2026-08-27 because it silently mirrored the esp32
  cavity. Docstring corrected to the rule the code follows.

**REJECTED (1):**

- *the un-awaited `releaseIsolation()` in `exitMode()` leaving the viewport
  rolled back*. `postJSON` never rejects - it catches a dead server and
  returns `{error}` (`api.js:124`) - and in the edit path the release is the
  LAST request in flight, so its response is what sets the viewport. The only
  overlap needs a click during `cancelSketch`, which is the already-tracked
  "two requests reaching the kernel at once" item.

**Not done, deliberately:** a full circle still offers no QUADRANT snaps.
Fusion has them; adding one would need a new snap kind in the frontend's
rank table and dot rendering, which is a feature, not this review's business.

### Section 1 again - the FIX PASS re-reviewed (2026-09-09, commit 6e2cae9)

A P0 fix earns a second review; this one found a P0 of its own. 8 findings,
8 fixed, all measured against `designs/` before and after.

| # | P | What it was | Fix |
|---|---|---|---|
| G1 | P0 | F2's reorder iterated in SORTED order but still refused a subtraction as the first entity of THAT order. `esp32-remote/logo_1_sketch` built at 4.37 mm2 before the fix pass and raised `ValueError` after it - red sketch, red everything downstream, and `-m library` cannot collect so nothing caught it | a sort by DEPTH is not an ordering constraint. `_compose_order`: a stable topological order over measured containment - an outer before what is nested inside it, drawing order everywhere else. A leading subtraction (it may CONTAIN an add) waits for the first add |
| G2 | P1 | F4's catch-all wrapped only `make_face()`, so `StdFail_NotDone: GC_MakeArcOfCircle` came straight out of `ThreePointArc` - kernel text in the tree, 500 from `/api/sketch/trim/pieces`. The very failure F4 existed to close | translated per segment, naming the arc. No threshold of ours: OCCT accepts a via 1e-6 off a 100 mm chord (probed), so the kernel judges and we translate |
| G3 | P1 | `_nesting_depth`'s bbox skip NEVER fired - `BoundBox.is_inside` is `not(STRICTLY inside)` and a sketch box is flat in Z, so always True. Every pair ran a full boolean: +4128 ms per rebuild of `rocky-balboa/field_sketch` | `_box_within`, X and Y only. 4128 -> 538 ms; `rocky-keychain/words_sketch` 1513 ms -> out of the top six |
| G4 | P1 | `entSamplePts` read `e.start[0]` / `e.points` unguarded; a path with no `start` is legal on the backend, so Edit on one threw `TypeError` in an unawaited handler before `enterMode()` - sketch mode silently never opened | `|| []` / `|| [0, 0]` like every sibling reader |
| G5 | P3 | `arcKindsSeen` was keyed before the await, so one failed fetch pinned a row at "curve N R"; both label maps were keyed by bare feature id (unique only within a document) and never shrank | key stored after the answer arrives; both maps dropped when the design on screen changes |
| G6 | P3 | `askJSON` ignored `r.ok`, so a 422 body read as a successful "no arcs" | `!r.ok` returns an `error`; still silent to the user, never to the caller |
| G7 | P3 | a closed ELLIPSE edge (an elliptical pocket's floor rim) got no snap point at all - F8 suppressed the seam and the centre was added only under `if circle` | `arc_center` for ellipses too (probed: the true centre, where `center()` answers a sampled centroid and lies). A closed BSPLINE has no defined centre and is still left alone |

**Accepted, not a defect:** `esp32-remote/logo_0_sketch` 277.16 -> 280.46 mm2.
Entity 8 sits inside the subtract 9, so the island survives - F2's rule
working as designed, and the only area in the library that changes.

### Section 1, round three - the DEFERRAL re-reviewed (2026-09-09, commit 5f65a7a)

The second round's P0 fix earned a third review, and it found a P0 of its own -
in the same few lines, for the third time. 8 findings, 8 fixed, 0 rejected,
every one reproduced first in `probes/sketcher_review3_probe.py`.

The lesson worth keeping: **the two mechanisms cancelled each other.**
`_compose_order` hoists a subtraction in FRONT of the add nested inside it
*precisely so that add survives as an island*. The deferral then held that
subtraction back to just after the first add and subtracted it from exactly
the add the order existed to save. Each half was defensible alone; together
they restored the drawing-order answer the whole reorder was built to replace,
and the round-two goal that produced them ("it cuts exactly what it cut
before") was itself the bug - preserving a live design's number was treated as
the target when the number was wrong.

**Ground truth, settled by reading the renderer** (worth not re-deriving): the
sketcher paints every entity on its own - `add` fills GREEN, `subtract` fills
RED (`sketcher.js:1611`). There is NO even-odd canvas fill; `assignModes()`
only assigns the modes, and only when the user edits. So "what the editor
shows" means: a green region is material and must be in the built profile.

| # | P | What it was | Fix |
|---|---|---|---|
| H1 | P0 | the deferral, above. `[r20 subtract, r10 add]` built area **0.0** and reported `ok` - a successful empty sketch, banned failure 2. Three identical bars inside one subtract blob built 144.0 instead of 216.0, the FIRST bar silently missing and the other two there. `esp32-remote/logo_1_sketch` built 4.3671 where the editor paints 7.6656 | a leading subtraction removes NOTHING - nothing is composed yet, so there is nothing to cut - and a note in the feature says so instead of the cut vanishing silently |
| H2 | P1 | a profile cut away to nothing reached `_as_sketch` as an empty Compound; `pl * <empty>` is a plain `list`, so the tree showed `AttributeError: 'list' object has no attribute 'faces'`. The right message (`"sketch is empty"`, document.py:868) was unreachable | `_area_of` after every step: empty is not failed, so the next add starts the profile again, and a sketch that ENDS empty says "the cuts removed everything that was drawn" |
| H3 | P2 | a cut applied to an already-empty result raised build123d's `ValueError: Dimensions of objects to subtract from are inconsistent` verbatim (rule 5) | same fix as H2 - the kernel is never handed an empty shape to subtract from |
| H4 | P2 | `tree.js loadArcKinds` never re-checked the document after its `await`: a reply that landed after a design switch repainted the NEW design's rows, because the selector matches feature id alone and ids like `sketch1` are unique only within one document. A free curve got a `corner` label and the tangency promise the backend will not keep | the design is captured before the await and compared after |
| H5 | P2 | `sketcher.js scaleEntity` still read `e.start[0]` and iterated `e.segments` unguarded - round two's `entSamplePts` fix made that path reachable, so Scale on a start-less path threw TypeError mid-drag, in an unawaited handler | the same `\|\| []` / `\|\| [0, 0]` guards as its siblings |
| H6 | P2 | a `path` entity with no `start` was built from the origin, while `outlinePts`, `hitTest`, `entityHandles` and `collectSnapPoints` all guard `&& e.start` and drew NOTHING - invisible, unclickable, and saved anyway | refused, in a sentence. Defaulting is inventing geometry nobody drew; the AI author's own schema (author.py:333) documents `start` as part of a path |
| H7 | P3 | `pathArcRows` calls `loadArcKinds` once per path entity, and round two moved the dedupe key after the await, so N path entities fired N identical POSTs per render, each carrying the whole entity list | an in-flight key, dropped again the moment the answer or the failure lands - dedupe restored without pinning a row on a failed fetch |
| H8 | P3 | an arc segment with no `via` at all reported "the middle point lies on the straight line between its ends" - a sentence about a point that is not there. `_validate_path` cannot catch it either: it guards with `s.get("via")` | `via` is read OUTSIDE the translator's try, and a missing one is named |

**Nothing rejected.** All eight reproduced.

**Four tests from round two asserted the defective contract** and were
corrected in place, each recording why in its docstring - they are the reason
the P0 survived a review:

- `LOGO_1_AREA = 2 * math.pi * 9  # the two clear adds; the nested one is eaten`
  wrote the eaten island down as the expected area;
- `test_the_deferred_subtraction_still_subtracts` asserted the island was gone
  (now `test_the_leading_subtraction_keeps_the_island_it_contains`);
- `test_a_path_entity_without_a_start_is_legal` asserted the opposite of H6;
- two message regexes ("first entity cannot be a subtraction") named a mistake
  that is no longer a mistake.

**The library, measured:** exactly one sketch's arithmetic moves -
`esp32-remote/logo_1_sketch` 4.3671 -> 7.6656 - and all six of that design's
`logo_*` features are SUPPRESSED, so no built geometry in `designs/` changes
at all. (Round two's accepted `logo_0_sketch` 277.16 -> 280.46 was suppressed
too, so that never reached the part either.) All 81 features rebuild `ok`.
1239 fast tests pass, ruff and eslint at zero, ui v177.

### Section 1, round four - the ORDERING RULE re-reviewed (2026-09-09, commit 13da90c)

Ten independent reviewers, one lens each, with a three-judge panel (refute /
reproduce-by-measurement / severity) on every finding they raised: 35 raised,
10 killed by the panel, and the survivors deduplicated by hand. **It cost
about 46 Opus agents at xhigh before it was stopped, which is 40-100x a single
review and against this repo's own token rules - see [[usage-conscious-testing]].
Do not repeat the shape without quoting the price first.** It did earn its
money once: it found the P0 below, which three cheaper rounds had missed.

**The lesson: this time the rule was INCOMPLETE, not inverted.** An entity
waits only for the shapes it is NESTED INSIDE. So a cut can be ordered ahead
of material it overlaps for a reason that has nothing to do with that
material - because the material sits inside a DIFFERENT cut and is waiting
itself - and round three's "a leading cut removes nothing" then threw it away.
Measured: a boss with a bar across it composed 22.3648 mm2; adding a pocket
around them gave 78.5398, the whole boss, as if the bar had never been drawn.
56.17 mm2 of red paint built solid, status `ok`. The constraint is in two
parts, and one of them was missing:

- an outer before anything nested inside it (a hole needs its material; an
  island survives its hole);
- **material before a cut that OVERLAPS it without containing it.**

A cut that still leads after both genuinely meets nothing, and only that one
is dropped. `_overlaps` / `_boxes_meet` measure it, the bbox only skipping;
the pass runs ONLY while the order starts with a cut, so the ordinary sketch
pays nothing (`rocky-balboa/field_sketch`: 1207 ms with the pass against
1506 ms without, same order - it never fires there).

| # | P | What it was | Fix |
|---|---|---|---|
| J1 | P0 | the dropped overlapping cut, above. The built solid also DEPENDED ON THE DRAWING ORDER: the same three shapes gave different areas depending on which was drawn first | the overlap edge. All six permutations now give 22.3648 |
| J2 | P2 | the emptiness reset fired after an ADD too, so one entity of area <= 1e-9 (a radius typed as 0.00001, area 3.1e-10) raised "the cuts removed everything that was drawn" for a sketch with NO cut in it - and failed where it used to build | narrowed to cuts, which is the only case it was written for |
| J3 | P2 | `sketch_corner._chain` fabricated a start at the origin, and `set_arc_radius` WRITES that start back (sketch_corner.py:240) - a radius edit on a start-less path SAVED a vertex the user never drew, turning the sketch the backend refuses green | refused, same sentence as `_path_face`; a segment with no `to` is named there too |
| J4 | P2 | `scaleEntity`'s round-three guards defaulted a missing start to [0, 0] and then WROTE it back - the same fabrication, from the frontend | a malformed path (or a polygon with no `points`) is left ALONE, like every sibling reader |
| J5 | P2 | `to` was read outside the arc translator's try and never wrapped: a segment with no destination reached the tree as `KeyError('to')`, a `via` of one number as `IndexError` | `_seg_point` names both, in `_validate_path` and `_path_face` |
| J6 | P2 | a SUPPRESSED feature kept its notes, and `Document.warnings` republishes every note (document.py:1211), so the info box went on stating a fact about geometry no longer in the model | notes cleared for suppressed and rolled-back features |
| J7 | P3 | the dropped-cut note said "nothing in this sketch is drawn beneath it" even when material HAD been drawn there and an earlier cut removed it | the note says which of the two it is |
| J8 | P3 | a raw NUL byte in `tree.js`, written by round three's in-flight key. Valid JS, but every tool treats the file as binary (grep reported it so, which is how it was found) | an explicit `\u0000` escape |

**REJECTED (1), and worth recording because it read convincingly:** *the note
is never rendered, so a dropped cut is still silent.* Only `extrude.js` reads
`f.notes` in the frontend - but `Document.warnings` republishes each note as
`'<feature>': <note>` (document.py:1211) and `tree.js renderWarnings` shows
those in its info box. Measured: the note appears. Two of the ten lenses drew
opposite conclusions about this, which is what a lens panel is for.

**DEFERRED, all real, all measured, none fixed here** (they are other
modules, and one commit that changes the composition rule should not also
rewrite Trim) - see LAUNCH-PLAN section 10:

- **`sketch_trim.py` keeps its OWN copy of the composition rule**
  (`_compose_faces`, l.223-229, drawing order) and its own leading-cut
  refusal (l.372, l.424). So Trim computes a different profile from the
  builder, and refuses entity lists `_compose` now accepts. P1.
- a **polygon whose outline crosses itself** builds a sketch that reports `ok`
  with an invalid face; the extrude two nodes later takes the blame. P2,
  pre-existing (the shoelace guard catches zero area, not crossing).
- **`tree.js`'s doc guard compares design NAMES**, and `freeDesignName` can
  offer one name to two unsaved tabs, so an arc label can still cross between
  two tabs of the same name. P3.

**The library, measured:** all 25 subtracting sketches in `designs/` compose
to exactly the same area as before this commit. esp32-remote (81 features),
rocky-balboa and wing-rib all rebuild `ok`. 1258 fast tests, ruff and eslint
zero, ui v178.

### Section 1, round five - ONE reviewer, medium (2026-09-09, commit c489839)

The cheap shape, as the round-four lesson demanded: a single reviewer at
medium instead of ten lenses and a panel. It **cleared the two-part ordering
rule** - the part that had failed three rounds running:

- for every (add, cut) pair the order now carries an edge one way or the
  other (`needs[j][i]` when the add is nested inside the cut, so the island
  survives; `needs[i][j]` when they merely overlap, so the material goes
  first), and no arrangement it could construct made a result worse;
- **termination is bounded** by `range(n)` and by `grew`, and `_order_from`
  degrades to drawing order rather than looping. A cycle would need an add
  ordered before a cut while being transitively nested inside it, which the
  `inside[i][j] or inside[j][i]` skip and `_containment`'s mutual-pair drop
  rule out;
- an adversarial 24-entity sketch (8 leading cuts, 8 islands, 8 crossing
  bars) orders in 0.11 s and composes in 0.27 s.

It then found five gaps in the fix pass itself. All five reproduced.

| # | P | What it was | Fix |
|---|---|---|---|
| K1 | P1 | `_overlaps` answered **False** when the boolean would not run - and False leaves the cut LEADING, where `_compose` drops it. One unmeasurable pair and round four's P0 is back: measured 78.5398 mm2 instead of 22.3648, plus a note that is false about the user's sketch | fails **open** now. True only orders the material first, and subtracting a shape that turns out not to overlap removes nothing anyway. This is the opposite of the safe direction elsewhere in the file, and the comment says why |
| K2 | P2 | the `start` read was never routed through the new `_seg_point`, so `start: [5]` still reached the tree as `IndexError('tuple index out of range')` and `["a","b"]` as a raw `float()` message | one `_xy` validator, used for the start and both segment points |
| K3 | P2 | `sketch_corner._chain` checked that `start`/`to` EXIST but not that they hold two numbers, and `path_arcs` / `set_arc_radius` read `s["via"]` raw. The IndexError is not in studio.py's catch list: `/api/sketch/path-arcs` 500s and EVERY radius row in the sketch disappears | `_pt` validates the start, every `to` and every arc's `via`, once, in `_chain` - the funnel both readers go through |
| K4 | P2 | round four's `scaleEntity` early-outs came AFTER the `!inPlace` `e.x`/`e.y` line, so a "scale all" drag still wrote coordinates into a malformed entity and committed it back through `skEnts[idx] = scaleEntity(...)` | a `scalable(e)` guard at the TOP of the function; the in-branch returns are gone |
| K5 | P3 | the rolled-back branch cleared `notes` and `volume` but left `pieces`, and `_check_pieces` filters only `suppressed`. Measured: park the bar before a severing cut - the part is WHOLE and the panel still says "leaves the part in 2 separate pieces" | `f.notes, f.pieces = [], None` |

**Nothing rejected.** One cosmetic note accepted and fixed: a mangled
continuation line (`if is_arc                     else None`) left by the
previous pass's patch script - ruff-clean, but it read like a bad patch.

**The library, measured:** all 324 sketches in `designs/` still build, and
every subtracting one composes to the same area as before - the tightened
point validation rejects nothing real (the reviewer swept the live library
and `tests/fixtures/` for path points that are not exactly two numbers: zero
hits).

---

### Section 2 - Document core and feature tree (reviewed and fixed 2026-09-10, commit 6ea5546)

ONE reviewer at medium, read-only, no server started. `document.py` (1481) +
`static/js/tree.js` (1006) + the studio endpoints the section lists. **5
findings, 4 fixed, 1 rejected**, each reproduced by measurement before it was
touched. 7 new tests; fast tier 1264 -> 1271, all green.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P2 | a STRUCK feature kept its last `pieces`. Its row went on saying "pieces 2" about geometry that is gone, and `_check_pieces` took that stale count as the BASELINE for the feature below it: strike one severing cut and the SECOND one's warning vanished while the bar was measurably still in two pieces (`n_solids(result) == 2`, `doc.warnings == []`). Same class the fourth sketcher review fixed for `notes` and `volume`; `pieces` was missed, and the past-bar branch two lines up does clear it | the suppressed branch clears `pieces` too, and `_check_pieces` resolves a struck input through its pass-through to the body it really carries |
| F2 | P2 | clicking a struck-out row lit up the WHOLE upstream body. A suppressed node's slot in `_parts` holds its first input's solid (rebuild needs that), and `/api/feature-mesh` served it - the 2026-08-26 "the whole body is being selected" complaint back through the struck rows | the endpoint 404s for a suppressed feature; `viewport.js` already treats 404 here as "not built (suppressed / rolled back)" |
| F3 | P2 | a cut that legitimately severs re-probed the healer on EVERY rebuild. The probe is a full extrude plus a boolean, it can never pass for an intended sever, and only a `through` key already on the tool skipped it - 204 such cut tools across 26 of the 50 designs. Measured 13.0 ms against 0.1 ms on a four-feature design where every feature is a cache hit | a failed probe is memoised on the cut's own content signature (`_heal_tried`, capped like the other caches), so an edit still asks. `tests/test_through_cut.py` 104 s -> 81 s |
| F4 | P3 | the status bar's volume was JS's own rule, "the last non-suppressed feature" (R1). On `designs/spiderman-logo` that is a sketch, so the readout was blank; where the last row is a separate tool body it reported that body's volume as the design's | `_doc_json` sends `result_volume` from `Document._result_feature()`; the tree renders it |

**Rejected:** F5, "a design file naming an op this build does not know should
still open". It should not. A version restore of such a file answers "cannot
open it - it is still in the history" and a restored session tab holding one
is dropped while every other tab lives; both are deliberate and both are
tested (`test_version_api.py`, `test_session_restore.py`), and the fast tier
failed the attempt. `op_params` tolerating an unknown op is about walking the
CATALOGUE without raising, not about loading. Pinned by
`test_an_unknown_op_is_refused_at_every_door` so the sixth reader does not
re-open it.

**Checked and found sound** (do not re-derive): the content signature is
complete for every op - a seeded pattern's `_before`/`_after` are always
ancestors of its own input body, enforced by `_seed_parts`; `strike` /
`unstrike` agree with `remove` in every arrangement traced, including the
input dedup and the type-refusal branch; `_orphan_sweep`'s face-reference
skip holds (deleting a face-sketch pocket takes three nodes and leaves the
body); `rename` walks inputs, `REF_PARAMS`, the bar, `_parts`, `_sigs` and
re-stamps - and no param anywhere in the 50-design library holds a feature id
outside `seed`; the spec round-trip is safe (`to_data` stringifies hole-radius
keys, `spec_from_dict` casts them back). The tree's folded-boolean rule and
`delta_features`' folding rule are two copies of one rule and no arrangement
was found where they disagree - worth collapsing one day, not a defect today.

**Left alone deliberately:** a struck row's dimension rows stay editable while
its ✎ is withheld. ✎ reopens a live tool with a preview, which cannot work
with the geometry gone; a typed number is harmless and applies when the row
comes back.

---

### Section 3 - Version tree and session persistence (reviewed and fixed 2026-09-10, commit f63ba5a)

ONE reviewer, read-only, no server started. `history.py` (807) + `backfill.py`
(254) + `static/js/versions.js` (414) + the tab/session and versions endpoints
in `studio.py`. Data loss is the P0 class here and the module had never been
reviewed. **3 findings, all 3 fixed**, each reproduced by measurement first.
9 new tests; fast tier 1271 -> 1280, all green.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | **P0** | a save could land on SOMEONE ELSE'S design. File > New accepts any name and the slug rule collapses a natural one onto an existing file with no exact typing (`cam cover plaque` -> `cam-cover-plaque`; this filesystem is case-insensitive, so `Cam Cover Plaque` hits it too - probed). Measured on a temp library: tab A saved 1 feature as v1; a second tab of the same name saved 0 features as v2, `designs/<slug>.tcad.json` went to 0 features, the new content was appended to the OTHER design's tree as a child of its latest version, `current` moved to it, and BOTH tabs ended up with `source: file:<slug>` so two tabs wrote one file and one history. 48 of the 50 designs would survive it as their previous version; `esp32-remote-live-t2` and `-t3` have no `.history/` at all | `/api/save` refuses and names the way out. Two saves stay allowed: the tab already bound to that file, and a save whose content is exactly what the file already holds (that is how a sample tab writes itself into the library, and nothing can be lost) |
| F2 | P1 | after a restart a tab holding unsaved edits could read CLEAN, so closing it threw them away with no prompt. The baseline block takes the design's current VERSION on purpose - "otherwise a dirty tab would read clean after every restart and the close prompt would let those edits vanish silently" - but both fallbacks were open: a design with no (or a broken) `.history/` never entered the `if cur:` branch, and a `sample:` source never entered the block at all, so the baseline stayed the ALREADY-EDITED restored content. Measured with three restored tabs all holding radius 99: True / False / False | `_restored_baseline()` falls back to the design FILE on disk, then to the pristine sample; an unknown baseline reads DIRTY (a needless dot costs one click, a wrong "clean" costs the work) |
| F3 | P2 | the only recovery for a lost version index named a Python method the user cannot run. With `index.json` gone the panel said "History.repair() rebuilds an index from them"; `repair()` had callers only in `tests/` | `History.can_repair()` is true in the one state repair is for (index unusable, snapshots present), `/api/versions` carries it, `POST /api/versions/repair` runs it and refuses a healthy history (repair guesses a linear chain and drops labels and the star), and the panel offers "Rebuild the version list". Both problem sentences now point at the panel |

**Checked and found sound** (do not re-derive): `delete_after` handing back an
id a single `delete()` retired is DELIBERATE and pinned by
`test_delete_after_resets_the_numbering` - the trim is the explicit "this tail
never happened" gesture; the crash-checkpoint machinery (a locked in-flight
set that names the OLDEST request, and no checkpoint taken while any POST is
still running, so a half-applied edit can never reach the session file);
`append`'s no-op rule, the snapshot-before-index ordering and `_write_atomic`;
all four branches of `restore_version` (hash fast path, missing/corrupt
snapshot, older-build refusal, undo push); `backfill.py`'s no-`--follow`
decision, sha dedup and skip-live rule; `postJSON`'s `if (doc.features)` guard,
which is why the version endpoints that answer without a document cannot blank
the tree; `versions.js` showing a parentless version as a root rather than
dropping it (better than the backend's `depths()`, which omits it).

**Not ranked, still true:** restore v3 and then re-open the design from the
library without saving, and the tree gains a version duplicating content it
already holds - the file was never rewritten by the restore. Deterministic on
paper, odd enough in practice that it was left alone.

### Section 3, round two - the FIX PASS re-reviewed (2026-09-10, commit fafe983)

A P0 was fixed in `f63ba5a`, so the house rule sent a second chat over the fix
commit itself. **4 findings, all 4 fixed, 8 new tests**, fast tier 1288 green,
ruff clean, no frontend change. Every one was reproduced by measurement first:
`probes/version_review_probe.py` (A-D, each printing PASS/FAIL).

Two of the four were the SAME P0 through another door - a save landing on a
design's version tree that was not its own. That is why the round earned its
tokens.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P1 | `/api/save`'s identical-content escape hatch bound a SECOND tab to a file another tab already owned. From then on either tab's save silently overwrote the other's and hung its version off the other's latest - measured `bore.radius` 11 -> 44, with v3 parented to a v2 it never came out of. Exactly the state F1's own test asserts (`sources.count == 1`), and untested | `_file_owner(slug)` (case-INSENSITIVE, because the filesystem is) refuses the save with "already open in another tab". The escape hatch stays for the case it was written for - a tab writing content into a library file NO tab owns |
| F2 | P1 | `can_repair()` was `not exists() and any(glob)`, so it said YES for an index written to a schema this build does not understand - the one state `_load` refuses to interpret "rather than risk mangling it". The new panel button then replaced it with a linear "(recovered)" chain under a **brand-new design_id**, guessing away the parents, labels and star the branch exists to protect | `History._foreign` is set on the schema branch; `can_repair()` and `repair()` both refuse it. `/api/versions/repair` no longer answers such a case with "your version list is readable" (the opposite of the truth) - it reports `repair()`'s own refusal |
| F3 | P2 | The design FILE was the only thing the guard checked. There is no in-app delete, so a design removed in Explorer leaves `<slug>.history/` behind - and an unrelated design of the same name appended itself to that tree as a child of its last version, under its `design_id` and its `name`. Measured: a 1-feature disc became v3 of a 3-feature flange | `_saved_versions_exist(slug)` is the third door: the refusal names `designs/<slug>.history/` and says either rename this design or delete that folder |
| F4 | P2 | A cloud-sync or merge conflict copy (`v3 (2).json.gz`, `v.json.gz`) matched `repair()`'s glob but not `_VID`, so the sort key ran `int(_VID.match(...).group(1))` over it and took the rebuild down with an `AttributeError` whose text went straight to the user - a banned failure | `History.snapshot_files()` returns only exact `v<N>.json.gz` names, as `(number, path)`, and is the one place both `can_repair()` and `repair()` read. The stray file is left on disk untouched. A snapshot whose `stat()` fails is now "left out" like an unreadable one instead of escaping |

**Line delta:** +493 / -26 across `history.py`, `studio.py`, two test files and
the new probe (the probe and its tests are most of it: production code is
+118 / -20).

**Checked and found sound:** `_restored_baseline`'s three fallbacks, including
the `file:` source whose design was deleted (returns None, which `_dirty`
reads as DIRTY - the safe direction) and the unknown `sample:` key; the
current-version-before-file ordering, which matches what the dirty dot means;
`/api/versions` staying 200 for a broken index (`next_id`, `tree_lines` and
`problems` all tolerate `_data is None`); `postJSON` surfacing a 200-with-
`error` body in the chat, so the repair button's failures are not silent;
`content_hash` sorting keys, so the raw-file comparison in the save guard is
not defeated by key order or indentation.

**Not ranked, still true:** the versions routes answer refusals with HTTP 200
plus an `error` key rather than through `_refused`, which `_refused`'s own
docstring argues against. It is the convention across that entire group of
routes and the frontend handles it; changing one route would be worse than
leaving all of them. Noted in the brief's do-not-report list.

### Section 4 - Booleans and transforms (reviewed and fixed 2026-09-10, commit c9b2e92)

Never reviewed before. 9 findings, **all 9 fixed, 0 rejected**, 26 new tests,
measured first in `probes/boolean_review_probe.py`. The whole 50-design
library rebuilds afterwards with **zero volume drift** and no newly failing
row (the saved files record each feature's volume, so that is a real
before/after, not a claim).

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P1 | **A combiner given a SKETCH.** `intersect(body, sketch)` returned a 2D `Sketch`, CONSUMED the body, and left the design with `leaf_solid_ids() == []`, `result_shape() None`, an empty viewport - and all three rows green with no warning. `_eval` checked only the input COUNT | `_check_combiner_inputs`, a KIND gate that names the offending feature, run BEFORE the kernel |
| F2 | P1 | **No bodies + a spec reported "meets spec."** `if ok and self.spec and leaves:` read "no leaves" as "nothing to check", so a design with NOTHING in it verified against a spec demanding one 20x20x10 solid. Two doors: F1's combiner, and simply striking the only body out | no bodies is a spec FAILURE, with that sentence |
| F3 | P1 | **The Join/Cut default target followed FACE-REFERENCE ops.** `extrude_face` only points AT a face (`consumed_ids` already knew), but `_latest_descendant` counted it as a consumer, so a New-body boss became the panel's "current state" and the next face sketch's Cut landed on the PRISM. Fusion parity rule 6. With Join the later `fuse` hid it, because `reversed` found that first | the walk skips `sk.FACE_REFERENCE_OPS` |
| F4 | P1 | **Loft reached the kernel unchecked** - and `loft(sketch, solid)` **SEGFAULTS** OpenCASCADE (access violation in `BRepOffsetAPI_ThruSections`, exit 139 in its own process). Otherwise `Standard_NoSuchObject('NCollection_DataMap::Find')` and `StdFail_NotDone('BRep_API: command not done')` reached the tree verbatim (rule 5). A coplanar loft built a zero-volume "solid" that only said "empty solid" | F1's gate stops the crash case before the kernel; a translator for the rest; a coplanar loft names the plane |
| F5 | P1 | **The stranding heal ticked `through` on a tool ANOTHER cut shares.** The proof it relies on is computed for one cut only; measured, the second cut went 16200.0 -> 12600.0 mm3, i.e. 3600 mm3 more removed than its own parameters ask for, unasked and unmentioned. `designs/cam-cover-plaque` already shares a tool prism between two combiners | a tool with more than one live consumer is left alone |
| F6 | P2 | **A cut whose tool MISSES reported success and changed nothing** (volume 4000.0 against its input's 4000.0, warnings []) - and the tool is consumed either way, so it vanished from the viewport while the body sat untouched | `_check_idle_cuts` names the cut and its tool |
| F7 | P2 | **A pattern's COPY form was called a part that fell apart.** `linear_pattern`/`polar_pattern` without a seed exist to make `count` separate bodies, but they are MODIFIERS and so were not in the extrude/revolve exclusion: 24 rows across 13 library designs were each told "something in it no longer touches the rest" - the exact buried-signal failure that exclusion exists to prevent | the copy form is excluded; the seeded form keeps the check. The 2 genuine `fuse` multi-body reports survive |
| F8 | P2 | **The two Transform buttons do not share a pivot** and one docstring said the wrong one: measured, `rotate` turns about the WORLD ORIGIN (a plate at x[90,110] lands at y[90,110]) and `scale` about the SHAPE CENTRE (x[80,120], centre unmoved), while `scale_uniform` claimed "about the origin" | both docstrings state the measured pivot; `scale` gains the `OP_NOTES` entry it never had, so the dialog and the AI both see it |
| F9 | P3 | **`_pick_body` paired one body's geometry with another body's id**: a named feature that had FAILED fell back to `doc.result()`'s geometry while keeping the requested id, so the face was resolved on one body and recorded against another | refused by name. An id that names nothing at all still falls through, so an empty document keeps answering "build a body first" (that sentence is asserted by `test_revolve_p3b`) |

**Deliberately NOT changed:** the transform PIVOTS themselves (F8). Making
`rotate` turn in place would move geometry in every saved design that uses it,
which is a migration decision for the user, not a review fix. Recorded as a
LAUNCH-PLAN section 10 row.

**Line delta:** +655 / -26 across `document.py`, `toolplan.py`, `blocks.py`,
`author.py`, the new test file and the new probe. Production code is
+157 / -26, and that includes removing two duplicated copies of the
struck-node pass-through walk (`Document._live_source` now serves
`consumed_ids`, `_check_pieces` and `_check_idle_cuts`).

**Checked and found sound:** empty boolean results are NOT reported as success
(`health` catches "non-positive volume" and "no solid present" - an intersect
with no overlap and a cut that removes everything both fail); an edge-touching
fuse is caught as non-manifold, so rule 5 holds for touching-not-overlapping;
`suppressed` IS part of `_signature`, so striking a feature cannot hand a
downstream node a stale cached part; `remove_plan` keeps the positional order
of surviving inputs and cascades a cut whose first input cannot heal, so
target and tool cannot swap on a delete; `_passthrough` refuses a type change;
`_export_blockers` refuses on both doors and `to_step` refused the F1 blackout
outright, so no corrupt STEP file was ever written; `_latest_descendant`
terminates by construction; the heal's volume guard correctly refuses the
"drills clean through" case its comment describes.

**Named as the section asked, not counted as a finding:** a suppressed final
boolean promotes its TOOL to the result - `_result_feature`,
`document.py:1283`, which walks back past the struck row without filtering
consumed ids. Already an open P1 in LAUNCH-PLAN section 10, so it was not
re-reported. Two things worth recording for whoever takes it: the tree's X
does NOT reach it (`strike` runs the orphan sweep, which suppresses the tool
prism too), only `/api/feature/suppress`, which no frontend calls; and its
worse door is `_export_blockers`, which would then treat the cutter as a body
of the design and write it into the STEP file.

### Section 4 again - the FIX PASS re-reviewed (2026-09-10, commit 33b2f49)

`c9b2e92` fixed a P0-class finding, so the house rule sent a second read over
the fix commit itself. **2 findings, both fixed, 0 rejected**, 4 new tests
(fast tier 1314 -> 1318). Both are the same shape as section 1's G2, where
F4's catch-all wrapped only `make_face()` and `StdFail_NotDone` came out of
`ThreePointArc` instead: **a translator built one commit ago, with holes.**

| # | P | What it was | Fix |
|---|---|---|---|
| G1 | P2 | **`_loft`'s new guard leaked two ways.** (a) `getattr(out, "volume", 0)` does NOT swallow an exception raised by the property - the default only covers `AttributeError` (measured: a property raising `RuntimeError` propagates straight through `getattr`) - so a degenerate loft escaped as raw kernel text, the exact failure the guard exists to stop. (b) `except ValueError: raise` treated every `ValueError` as one of OUR sentences, but build123d raises its own bare ones with kernel wording (measured: `loft_sketches([sketch, Part()])` -> `ValueError('More than one wire is required')`) | the volume is read through `inspector._try`, the idiom that already existed for this; `_loft` now translates EVERY exception, because the count check is in `_eval` and the kind check in `_check_combiner_inputs` and both run first, so nothing above that line produces a sentence worth keeping |
| G2 | P3 | **The new `_pick_body` refusal called a HEALTHY body broken.** A feature behind a parked rollback bar has no part, so a face-mode plan answered "'boss' has not built - fix that feature first" about a body that builds at 1206.37 mm3 the moment the bar comes down. The sketch and extrude editors park the bar for isolation, so an ordinary edit could produce that sentence - and it tells a non-engineer to repair something that is not broken | the two reasons are two sentences; the parked-bar one says to move the bar. The distinction `_export_blockers`' docstring already draws ("the build raised, or it is stale behind a rollback bar") |

**Honest reachability:** neither G1 door could be driven through the app. An
empty sketch raises inside `make_sketch`, so its part is `None` and a loft of
it never evaluates; an empty combiner result is a `Compound`, which the new
kind gate refuses first. They are holes in a rule-5 barrier rather than live
bugs, and they were fixed because the fix is three lines and the barrier's
whole job is that nothing leaks. G2 reproduces in four lines.

**The brief named five risks; four cleared BY MEASUREMENT, not by reading:**

- **`_live_source` is behaviour-identical to both walks it replaced** - the
  biggest risk, since `consumed_ids` is what the viewport and the exporter
  filter on. Re-implemented both originals verbatim and compared over 52
  design and fixture files with 15 struck features exercised: **zero
  mismatches**, plus hand-built chains of one and two consecutive struck
  nodes.
- **The new spec failure reaches three `rebuild()` callers and none of them
  refuses a user action:** `studio.py` only reports `ok`, `mcp_server` gates
  the export on it (correct - there is nothing to export), `author.py` hands
  `spec_problems` to the model as something to fix (correct - a tree with no
  bodies should be told so).
- **A parked rollback bar cannot trigger the false "no bodies" verdict:** the
  rollback branch returns before the new one.
- **The kind gate's 2D test holds on every path that makes a 2D part.** This
  was the one I expected to be wrong, because `rebuild` itself deliberately
  classifies by OP as well as type ("disjoint entities compose into a Compound
  that is not a Sketch instance"). Measured: `make_sketch` normalises even
  DISJOINT entities to a `Sketch`, and `move`, `rotate`, `scale` and
  `sketch_on_face` all keep `is_sketch` True - so a legitimate loft of a
  sketch plus a moved copy of it still builds (1570.8 mm3). No false refusal.

**Considered and rejected as findings:** a pattern SEEDED on a healed tool is
not the shared-tool bug through another door (that bug was a second cut on a
DIFFERENT body silently changed; a pattern of the same feature following its
fix is coherent, so the guard rightly ignores `param_refs`);
`_check_idle_cuts`' 0.01 mm3 absolute tolerance is negligible at the scale
these parts are built at; the pattern exclusion reads a falsy `seed` as the
copy form, matching what `_eval` itself does.

**Line delta:** +130 / -8. The library still rebuilds with zero volume drift.

### Section 5 - Primitives and shape editing (reviewed and fixed 2026-09-10, commit e35450d)

8 findings, all reproduced by measurement first
(`probes/primitives_review_probe.py`). **8 fixed, 0 rejected**, 55 new tests
(`tests/test_primitive_guards.py`), fast tier 1373 green.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P0 | `polygon_plate` and `hex_plate` span Z 0..thickness; `author.AUTHOR_PROMPT` listed them with disc/plate/tube as "CENTERED at the origin - they span Z from -thickness/2 to +thickness/2". Measured: the other five span -4..+4 at thickness 8, these two 0..8. Every `move` the AI computed for a hex body was half a thickness out | the PROMPT now says which five are centred and that these two stand on Z=0. A test measures all seven spans AND checks the prompt names exactly the centred set |
| F2 | P1 | a degenerate or mistyped dimension put raw kernel text in the feature row: `Standard_DomainError('')` (empty, and identical for all three of a plate's dimensions), `StdFail_NotDone('BRep_API: command not done')`, and for the string "8mm" twelve lines of pybind11 constructor overloads | `blocks._positive` checks every dimension before the kernel and names the bad one; `check_params` refuses a non-number in a number param, read from the type ANNOTATION; `rebuild` translates through `blocks.plain_cause` instead of `repr(e)` |
| F3 | P2 | `with_center_hole(radius=0)` and a bolt circle whose PCD puts the holes off the part handed back the UNDRILLED body - volume unchanged at 78539.82, row green | positive-value guards, plus `_drilled()`: a drill that removes no volume raises, naming why |
| F4 | P2 | `with_bolt_circle(pitch_circle_dia=0)` put all `count` locations on the origin, so six holes became ONE at the centre and the row stayed green (78037.16 = exactly one hole) | refused, with the smallest PCD that would fit named, and `with_center_hole` suggested for one central hole |
| F5 | P2 | the tree painted a red **"spec FAIL"** whenever the rollback bar was parked - `spec_problems` held `["(spec not checked while rolled back)"]` and `renderSpecRow` colours any non-empty list as a failure. **42 of the 50 saved designs carry a spec**, so it appeared the moment any editor opened | `spec_checked` is a field on the response and the row has three states. The browser does not read it out of a problem line's wording (R1) |
| F6 | P2 | the placement popup shared ONE debounce timer between its dimension and position grids, so a dimension typed within 250 ms of touching x/y/z was silently discarded while the popup went on showing it | one timer per destination |
| F7 | P3 | `Number(v) \|\| 0` in the placement popup turned a cleared field (and the lone `-` of a negative number) into 0, which then failed as a zero dimension | an unparseable box waits for the rest of the number |
| F8 | P3 | `revolve_profile` has promised radii >= 0 in its docstring since it existed and never checked; a negative radius gave `StdFail_NotDone` | the point number and its radius are named |

**Why the prompt and not the geometry (F1).** Both sides were wrong together,
so either could have moved. `designs/hex-nut-M16` and
`designs/planetary-assembly` hold five of these features between them, and
re-centring would have shifted a nut that the user has already looked at and
may have cut. Moving a shipped part to fix a sentence is the wrong trade; the
sentence was the thing telling the AI to place bodies wrongly. **Whether the
two should be re-centred for consistency is a product decision, not a review
fix** - it is a LAUNCH-PLAN section 10 row (P2), and it carries the related
question that click-to-place currently drops five primitives half below the
ground grid and these two on top of it.

**Checked and found sound, so not re-checked:** `isRadius`/`diameterRow` -
enumerated every op parameter, all 12 diameter rows are true radii and all
four already-diameter params (`hole.diameter`, `cbore_diameter`,
`csink_diameter`, `pitch_circle_dia`) are correctly excluded; the Ø row cannot
drift the stored radius, because `beginEditWith` returns early on an unchanged
number; `circumR` is the standard `abc/(4·Area)` formula, correctly written;
the missing-catalogue fallback (`genericFields`/`genericRadius`/
`genericGeometry`/`staleCatalogNote`) really does keep every numeric field
editable; the sketch-entity catalogue is already drift-guarded both ways by
`test_shape_params.py`; `api_summary`/`_signature` are no longer the catalogue
the AI reads (`author.op_catalog` derives from `document.op_params`, one source
shared with the edit guard), so that drift risk is already closed.

**Not reported, on purpose:** `placement.js` calling `loadMesh()` itself is the
known P3 already exempted for `sketcher.js` and `measure.js`, and the fit flag
it passes is computed correctly.

**Line delta:** +237 / -25 over 8 files, plus 340 lines of tests and the probe.
Geometry is untouched - every fix either refuses or changes wording - and all
50 saved designs rebuild with no failed feature.

### Section 5, ROUND TWO - the fix pass re-read (2026-09-10, commit 2d2e8a9)

`e35450d` closed a P0-class finding (the AI was told polygon/hex plates were
centred when they are not), so the house rule sent a second read over the fix
itself. **2 findings, both fixed**, 4 new tests, fast tier 1377 green.

| # | P | What it was | Fix |
|---|---|---|---|
| R1 | P1 | the fix pass's own `cone` guard required a POSITIVE `bottom_radius`, which refused a funnel standing point-down. Measured: OCCT builds `cone(0, 10, 20)` at 2094.40 mm3 - **exactly the volume of `cone(10, 0, 20)`**, which was still allowed. A capability the fix pass took away | both radii only have to be >= 0; the both-zero case is still caught by the equal-radii check ("that is a cylinder, use disc") |
| R2 | P3 | `spec_checked` defaulted to `True`, so a document that had never been rebuilt reported `spec_checked=True, spec_problems=[]` - which the tree paints as a green **spec PASS** for geometry nothing has verified | defaults False; `rebuild` sets it. Not reachable through today's endpoints (`/api/tabs/switch` rebuilds a never-built tab first, and the active tab is rebuilt at restore), which is why it is a P3 and not worse |

**The brief named five risks; four CLEARED by measurement, not by reading:**

- **`_drilled`'s 1e-6 volume floor has six orders of magnitude of headroom.**
  A 0.05 mm-radius hole through a 1000x1000x100 plate (100 million mm3) gives
  `gone=0.785398170` against a true 0.785398163 - eight significant figures.
  The floor cannot falsely refuse a real hole at any scale this system builds.
- **`numeric_params` misses no numeric parameter.** Enumerated every
  parameter of every op: the only numeric-looking one outside the gate is
  `revolve_profile.points`, a list, which is checked point-by-point inside the
  function. `polar_pattern`/`linear_pattern`'s unannotated `count` already has
  its own plain refusal in `pattern.py` ("count must be a whole number >= 1"),
  measured rather than assumed.
- **`plain_cause`'s new collapse cannot swallow a useful refusal.** The
  `isinstance(e, ValueError)` branch returns the message verbatim BEFORE the
  multi-line / 200-character test, so every op's own plain sentence passes
  through intact; only an untranslated non-ValueError can be collapsed.
- **`polygon_plate` accepting `sides=6.0` is a non-event.** No design or
  fixture file holds a whole-float `sides`/`count` or a numeric string, so the
  widening changes nothing that exists.

Also checked: the stranding-heal early return at `document.py:1059` does not
skip the new flag (it returns the value the recursive inner `rebuild()` set),
and `renderSpecRow`'s `!== false` fallback keeps the row's old behaviour
against a server that does not send the field.

**Considered and NOT reported:** `numeric_params` doing an uncached
`inspect.signature` walk on every edit (~100 us against a 20 ms rebuild -
`op_params` is cached, but this is not a bug and padding the list is against
the rules); `tube(20, 0, 6)` newly refusing where it used to build a plain
disc silently (that is the same "removed nothing" class as F3 and the refusal
is the honest answer, not a regression).

**Line delta:** +21 / -8. All 50 saved designs rebuild with no failed feature.

**The deferred half of F1 is now SETTLED, by the user:** asked whether
polygon/hex plates should be re-centred to match the other five, they said the
hex nut is not even needed - "just delete it or leave it". The geometry stays
as it is, the LAUNCH-PLAN section 10 row records the decision, and it is not
scheduled.

### Section 6 - Measure and drive (reviewed and fixed 2026-09-10, commit 3ce97a3)

8 findings, every one reproduced by measurement first
(`probes/measure_review_probe.py`). **8 fixed, 0 rejected**, 10 new tests,
fast tier 1387 green, all 48 buildable designs clean.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P0 | over 400 faces, `_tagged_mesh` handed out one edge id PER ADJACENT FACE in face order while `measure.resolve` indexes `part.edges()`. Twelve of the 50 saved designs are over 400 faces: esp32-remote advertised 7176 ids for 3588 edges, 6517 resolving elsewhere. On isogrid-panel a straight 210 mm edge read ⌀4.50 mm AND opened an edit box driving `corner_hole_sketch`'s circle, so typing there resized a hole the user never clicked | mesh mode filters `part.edges()` down to the rich faces' edges under their TRUE index; the once-per-face duplicates go with it, and meshing got FASTER (esp32-remote 3828 → 2725 ms) |
| F2 | P1 | the verification re-read the face INDEX the pick was made on, and a rebuild renumbers those, so a CORRECT edit was reverted. x-frame: a ⌀8 pad hole really became 8.5 (volume 116961.184 → 116896.388) and the tool said "the model came out at 8 mm — nothing was changed". 7 of 81 editable diameters across eight designs; the move path too (the wall had moved by exactly the 1.0 mm asked for, at a new index) | `measure.remeasure()` re-finds each pick by geometry — a round face by its AXIS LINE, a flat face by its NORMAL and its position ACROSS it (both a move and a width edit slide a wall along its own normal and nowhere else), unique-or-nothing, radius breaking the bore/counterbore tie. 81 of 81 land; `picks` hands the panel the relocated ids |
| F3 | P1 | every face click on an imported STL answered "face -1 is not on this body any more — click it again". A mesh body carries ONE pseudo-face, id -1, so clicking again gives -1 again: a loop with no exit, and a false reason | `resolve` names what the body is. Measuring a mesh body's surface is still not possible — LAUNCH-PLAN §10 P3 |
| F4 | P2 | a tilted face's `extents` came from the WORLD bounding box, whose third dimension is only ~0 when the face is axis aligned. A 6 mm 45° chamfer read 60.00 × 6.00; it is 8.49 across, which is what the PICK panel said for the same face | projected into the face's own frame with `face_plane().to_local_coords()`, as `_tagged_mesh` already did |
| F5 | P2 | the readout is rounded to 3 dp and the verification compared it against the RAW request, so every dimension with more than three decimals was written perfectly and then reverted: 5/16" = 7.9375, 7/16" = 11.1125, both refused | the request is rounded the same way before comparing |
| F6 | P3 | a bore's "centre" row was `axis_of_rotation.position`, an arbitrary point ALONG the axis — the mouth of a 5 mm pocket (z=6), not its middle (z=3.5). The pick panel calls the same number `axis_at` | pinned to the face's own middle |
| F7 | P3 | `sendProbe` checked `probeOn`/`A`/`B` only BEFORE its await, so a reply landing after Esc repainted a dimension line into a closed tool | re-checked after the await |
| F8 | P3 | `openMeasure` read `S.pickedFace`/`S.pickedCurved` but not `S.pickedEdge`, so clicking a bore's rim and pressing Measure opened an empty panel asking for the click just made (parity rule 2) | an edge pick becomes A too |

**The revert safety net is now EXPLICIT rather than accidental.** It used to
fire only because a wrecked part also renumbered the faces — which `remeasure`
sees through — so `measure_set` asks the real question: did a feature that
built a moment ago stop building? A ⌀8 hole grown to ⌀38 leaves its 2 mm rim
fillet nowhere to sit, and that reverts with "it would stop fl from building".
`test_a_move_that_wrecks_the_part_reverts_itself` was REVISED for the same
reason: its 5.0 mm case lands the asked-for step exactly (the cavity slides to
y=-45 and the step really is 5.00 mm), so the old revert message was a lie;
the wreck is now asserted at 120 mm, where the cavity leaves the plate.

**Checked and found sound, so not re-checked:** `_plane_cache`/`_plane_sig`
(the signature covers every `sketch_on_face` argument that moves a plane, and
the base-Part identity check makes a rebuild a guaranteed miss); the probe's
caliper maths (wall↔pillar 24.000 at the facing minimum, 24.804 at t=3 against
the closed form 24.803847, clamped at 30.0 past the flank); units and frames
end to end (body meshes are added untransformed); `_to_param` against
`ENTITY_DIAMETER` (both mapped keys really store radii); `plan_move`'s sign
rule (26 of 27 driven moves across 7 designs landed, the miss being F2); and
"never raises" — 1294 single measurements plus 1320 random pairs across 11
designs, with `plan_set` on every one that offered an edit, zero raises.

**Line delta:** +782 / -37 (code +308 / -37, tests +295, probe +179).

**A P0 was fixed, so `REVIEW-BRIEF.md` is PENDING on `3ce97a3`** and the next
`code review` re-reads this fix pass before taking section 7.

**Note for future probes:** `/api/open/<design>` PUSHES a version into the
real `.history/` index. Load a design read-only with `Document.from_data`
instead. One `opened gear-case` version was created and reverted during this
review; its orphaned `designs/gear-case.history/v41.json.gz` is unreferenced
and can be deleted by the user.

### Section 6, ROUND TWO - the fix pass re-read (2026-09-10, commit b8a956f)

`3ce97a3` closed a P0-class finding, so the house rule sent a second read over
the fix commit. **2 findings, both fixed**, 2 new tests, fast tier 1389 green.
Both were in the fix pass's own new code — where the brief predicted — and
**neither is live for the user**.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P3 | `_measure_one`'s world-bbox fallback for `extents` sat inside the SAME `try` as the in-frame projection it is a fallback for, so an exception in the projection abandoned both and the row vanished. Forced in a probe (no real face reaches it): the panel showed only type/area/centre/normal where it would have shown "50.00 × 40.00 mm" | the fallback has its own `try` |
| F2 | P3 | a REVERTED edit still handed back `picks`. Those ids are computed against the post-write body and `_revert_last()` then restores the previous one: a ⌀8 bore whose ⌀38 edit was reverted came back as `picks.a` id 6, which in the restored body is a 6.28 mm² face, while the user's own id 27 is still the bore. `measure.js` ignores `picks` unless the edit verified, so nothing misbehaved — it was one guard away | `picks` is sent only when the edit stands |

**What the re-read CLEARED by measurement** (so the next reader need not
re-derive it):

- **No false passes — the brief's first-named risk.** 322 driven edits
  through `/api/measure/set` across 9 saved designs: 92 diameters, 58 moves,
  and 172 deliberately destructive ones (tripling each bore, then shrinking
  it to a sliver), each checked against an INDEPENDENT oracle written inline
  — axis collinearity for bores, plane offsets along the normal for moves.
  Zero false passes, zero false fails.
- `_shape_key` does not collide across located copies, so mesh mode's `keep`
  set is sound: 70 IDENTICAL boxes gave 840 distinct keys for 840 edges.
- **The mesh fix loses no outlines.** The distinct edge set drawn is
  identical on esp32-remote (3588), isogrid-panel (927) and
  planetary-assembly (1464); only duplicates and wrong ids are gone.
- The mixed-body cost is real but small: an imported STL that has then been
  CUT (16663 faces, 1132 rich) meshes in 11.3 s against 10.5 s before — +7%
  on a path already dominated by the mesh, emitting 2100 fewer duplicates.
- Dead-flat BSPLINE walls take the new in-frame extents path correctly: a
  10° tapered 40×30 extrude reads 47.05 × 20.31, the trapezoid's true size.
- An edge pick drives end to end: clicking a rim and setting ⌀20 lands.
- Face order is deterministic across two identical rebuilds (196/196 by area
  on x-frame), so the signature approach rests on something stable.

**Line delta:** +64 / -22. **SECTION 6 IS CLOSED**; the brief goes back to
`NOTHING PENDING` and the next `code review` takes section 7 (Extrude as a
whole module, with loft and sweep).

### Section 7 - Extrude as a whole module, with loft and sweep (reviewed and fixed 2026-09-11, commit `dfcb73f`)

ONE reviewer on Opus, `medium` effort as the queue says. **6 findings, all 6
fixed, 0 rejected, 0 deferred**; 11 new unit tests (`tests/test_extrude_review.py`)
and 2 new browser journeys (`tests/e2e/test_extrude_face_pocket.py`). The fast
tier is 1533 green, Ruff and ESLint zero, and all 50 saved designs rebuild with
no failed feature and no new warning. No P0, so there is no second round.

**F1 (P1) - a loft blends ONE profile per sketch, and did not say so.**
build123d flattens every section's faces into a single chain
(`for face in s.faces(): loft_sections.append(face.outer_wire())`), so two
sketches holding two circles each blended A1 -> A2 -> B1 -> B2: ONE snaking
solid of **1570.8 mm3** where the two honest tubes are 3141.6, spanning
z -3.92..23.92 — outside BOTH sketch planes — with status ok and not one
warning. Which profile pairs with which was kernel face order. `loft` now
refuses a multi-profile section in `_check_combiner_inputs`, where the kind
gate from section 4 already lives. The user's six live lofts (autonomiq-panel,
autonomiq-sat-panel) are all single-profile and untouched.

**F2 (P1) - a profile op fed a solid BODY.** `sweep` was the silent one:
build123d takes `sections.faces()`, so a BODY is swept FACE BY FACE. A
24 000 mm3 plate came back as a **178 000 mm3 six-lump blob** — status ok,
`problems []`, `warnings []` — and the plate itself was consumed, because a
modifier's input is. The "falls into pieces" check exempts extrude/revolve/
loft/sweep by name (a sketch of 8 pilot circles is 8 prisms by design), so
nothing spoke at all. `extrude` and `revolve` do fail there, but on health, in
wording that names nothing to change. All three are one click from the Create
ribbon: the Add Feature dialog pre-ticks the NEWEST feature. `_eval` now gates
the sketch-consuming MODIFIERS the way section 4 gated the combiners. The test
is SOLIDS, never `is_sketch`: a sketch of disjoint islands composes into a
Compound that is not a Sketch instance, and a test on the type would have taken
those designs away (covered by its own test).

**F3 (P1) - pushing a picked face INTO the body did nothing, quietly.** Face
mode defaults to Join, and the Join/Cut rule that reads the drag direction was
written `!isFace(st)` — for face SKETCHES only — so an inward pull fused a
prism that was already inside the body: **plate 24 000, prism 9 600, join
24 000 mm3**, three green rows, an unchanged body, nothing said. Fusion's
parity rule 6 is "dragging INTO the body + Cut = pocket" and the plan already
ships `into_sign` for a face pick, so the rule now runs in face mode too
(browser journey: red as `- cut / + join` before the fix). The silence had a
second door — an explicit Join, the AI, the MCP path — so `_check_idle_cuts`
became `_check_idle_booleans` and names a join that added nothing, exactly as
it has named a cut that removed nothing since section 4. Zero of the 50 saved
designs trip it.

**F4 (P2) - Through all threw the taper away while the panel still showed it.**
A 2 m tapered prism collapses, so `extrude_sketch` zeroes the taper — but a
-10° through cut built **20 x 30 x 2000 mm, dead straight**, while the taper box
and the dashed ring went on reading -10°. The handle and the solid may not
disagree: the op now leaves a note (so the AI, MCP and API hear it, R7) and
`sync()` disables and zeroes the box and parks the ring while Through all is
ticked. The same `sync()` pass hides the Through row in FACE mode, where
`extrude_face` has no `through` param at all and ticking it was obeyed by
nobody.

**F5 (P3) - a typed negative "Distance 2" was dropped without a word.**
`amount 8 + amount2 -5` built 4800 mm3, the first side alone (`if amt2 > 0`).
`amount2` IS "the other way", so its sign carries nothing: it is taken as a
magnitude now, and the two-sided solid spans -5..8 whichever sign is typed.

**F6 (P3) - Through all's into-the-body seeding was missing from Two sides.**
Parity rule 4's corollary ("THROUGH ALL with an untouched 0 seeds direction
INTO the body") lived inside the `dir === 'one'` branch of `params()`, so in
Two sides the 2 m side ran +Z into the AIR on a top face and only the blind
second side cut anything. The seeding belongs to the through cut, not to one
Direction entry.

**Cleared by measurement (so the next read need not re-derive it):**

- The taper direction chain is sound. `_straighten_face` does NOT flip the
  rebuilt face's normal anywhere in the gauntlet corpus (dot = +1.000 on all
  four faces it rebuilds), so `_apex_cap` and `_taper_loft` read the same frame
  as the captured `outward`; on the fused tapered body of `test_taper_gauntlet`
  a -5 / 0 / +5 deg taper measures 11 405 / 13 290 / 15 359 mm3 — the lean
  follows the sign.
- `collapse_offset` is exact on thin, L-shaped, holed and multi-island
  profiles (an L with 20 mm arms returns exactly 10.0).
- Symmetric extrude fuses its two halves and both of them narrow
  (4644 = 2 x 2322); `_shapefix` accepts a repair only at equal volume and only
  if it then passes health.
- Degenerate amounts speak plainly: 0 mm, with or without a taper, is refused
  as "the geometry kernel rejected the shape it would produce", never kernel
  text.
- **Known and not a finding:** the symmetric branch (`both=True`) skips
  `_taper_offset_problem`, the pre-check that exists because a degenerate 2D
  offset can access-violate OCCT rather than raise. No profile could be
  constructed that reaches it — `_apex_cap` caps every case tried — so it is
  an asymmetry, not a bug. Worth knowing if a taper ever takes the server down.

**Line delta:** +116 / -29 across `document.py`, `sketch.py`, `extrude.js` and
the cache-buster — the two guards, the join check and their comments — plus 264
lines of new tests (`test_extrude_review.py`, `test_extrude_face_pocket.py`). **SECTION 7 IS CLOSED**; the brief goes back to `NOTHING PENDING`
and the next `code review` takes section 8 (Import STL and STEP).

### Section 7, ROUND TWO - the fix commit re-read (2026-09-11, commit `a8e96d9`)

Not required by the queue's step 8 (no P0 was fixed in round one) and run
anyway, at the user's word, because the fix pass had added two REFUSALS - one
of them in `document._eval`, which runs for EVERY modifier feature on EVERY
rebuild - and had changed what Extrude's face mode does by default. **2
findings, both fixed**, 3 new browser journeys.

**R1 (P3) - the new loft refusal quoted ONE count for SEVERAL sections**:
"a and b hold 2" where `a` held 2 and `b` held 3. Each section names its own
count now ("a (2 profiles) and b (3 profiles)").

**R2 (P3) - OK reported success over an EMPTY viewport.** Since round one an
inward face pull becomes a Cut by itself, so "deeper than the body" is ONE
gesture away: push a 20 mm plate's top face in by 30 and `extrude_face` is
perfectly green at 72 000 mm3 while the cut it created FAILS and the design has
no bodies at all - and OK said "Extrude created - editable in the feature tree".
`okSession` only ever looked at `st.featureId`, never at the combiner the same
session had just added. Pre-existing in the framework (section 11's module),
one gesture away because of round one, so fixed here: OK names the red row and
which boolean it is. Nothing was ever SILENT - the tree's own failure toast said
what failed - but OK contradicted it.

**Cleared by measurement:**

- The two new refusals take away nothing that used to build: mirrored sketches
  (single AND disjoint), scaled sketches, disjoint-island sketches, a ring with
  a hole, `sketch_on_face` profiles, three-section lofts and ring-to-ring lofts
  all still build. `n_solids` is exception-safe and returns 0 for None, so the
  gate cannot throw on a rebuild.
- The new through-all note cannot LEAK. The stranding healer calls
  `extrude_sketch(through=True)` as a probe OUTSIDE the per-feature drain: on
  the esp32-remote fixture with a tapered trim tool, `_NOTES` is empty after the
  rebuild and the note sits on the right feature, over two rebuilds.
- The auto-cut lands on the body whose FACE WAS PICKED, not the newest one, so
  the 2026-08-24 wrong-target class does not return (two-body journey; the other
  body untouched at 18 000 mm3). `st.opUser` guards the user's own choice.
- A pull deeper than the body fails LOUDLY (empty solid) instead of saving a
  corrupt one.
- F6's fix measured at the backend: the old form ran +2000 mm into the AIR
  (z -5..2000) and the seeded one runs -2000 into the material (z -2000..5).

**Out of scope, recorded in LAUNCH-PLAN.md section 10 instead:** a
`linear_pattern` / `polar_pattern` fed a SKETCH still answers with a diagnosis
about a shape the user never asked for - the same wrong-KIND family in the
opposite direction, in `pattern.py`.

**Test-run note:** `test_supervisor.py::test_a_kernel_crash_costs_one_step_not_the_session`
FAILED twice at ~370 s while the 34-minute browser tier was running against it
(its waits are 90 s timeouts) and PASSES in 21.7 s on an idle machine. Three
browser journeys - `test_measure_probe`, `test_small_face_and_fold`,
`test_tree_history` - fail identically at `1b645b7`, BEFORE this review started:
pre-existing, not this work.

**Honest limitation:** this round ran in the SAME chat as the fix, so it was not
a fresh pair of eyes. It attacked the diff by measurement rather than by reading,
which is why the two findings it did turn up are both in the new code itself.

**Line delta:** +163 / -9 (two sentences and a framework check, plus 3 journeys).
**SECTION 7 IS CLOSED**; the brief goes back to `NOTHING PENDING` and the next
`code review` takes section 8 (Import STL and STEP).

### Section 8 - Import STL and STEP (reviewed and fixed 2026-09-12, commit `94eb47e`)

Never reviewed before. 7 findings, **all 7 fixed, 0 rejected, 0 deferred**,
11 new tests (fast tier 1623 -> 1634), +417 -37 lines. Every finding was
reproduced by measurement first (`probes/s8_a_weld.py` .. `s8_m_realfile.py`)
and every fix is locked by a test proven RED on the code as it stood.

**F1 (P0) - a hollow STL imported with its cavity FILLED, plus a phantom body
inside it.** A 10 mm cube holding a sealed 4 mm void (936 mm3) came in as TWO
bodies totalling **1064 mm3**: the outer shell closed into a solid with the
cavity filled (1000), plus a phantom 64 mm3 block sitting inside it. health
[], status ok, the chat said "as 2 bodies". lib3mf had already read the file
correctly - `Solid volume=936.000 shells=2 is_valid=True` - and the guard that
exists to take exactly that as-is called `shp.is_valid()`. **`is_valid` is a
PROPERTY** in build123d 0.11.1, so the call raised `TypeError: 'bool' object
is not callable` into the bare `except Exception: pass` beneath it, and the
as-is path could never run: every shape was exploded shell by shell, which is
what the code's own comment says must not happen. Fixing the call alone is not
enough - lib3mf returns ONE Solid holding every shell in the file, so two
disjoint bodies make that solid invalid and the shells must still be
regrouped. `_solids_from_shells` now reads an INWARD-wound closed shell as a
sealed void and `MakeSolid(...).Add(...)`s it to the smallest body whose box
contains it. The same wrong answer had a second door: `split_components`
separates by shared vertices, so a cavity is always its own component and the
repair path wrote it as its own STL piece (`_group_voids`).

**F2 (P0) - the parity voxel fill XORed overlapping material away.** Two
bodies that INTERPENETRATE and are welded along a shared edge - the Fusion
assembly export this module exists for, and one overshared edge is all it
takes to reach the remesh - came back **7,998.4 mm3 of a true 12,000**, a void
punched straight through where the two bodies overlap, health [] and status
ok, the only note "auto-repaired: remeshed 1 defective body". The fill paired
the crossings as (enter A, enter B), (exit A, exit B). Crossings now carry the
direction the surface faces (`step = -1 if d > 0 else 1`) and a cell is inside
where the running **winding number** is positive. A column left open at the
top keeps what it accumulated instead of being dropped whole.

**F3 (P1) - the remesh moved every surface of a body and nothing measured or
reported it.** `ref` was taken AFTER the remesh, so even the decimation guard
below it could not see the remesh's own error; only decimation had a volume
rule. A 0.6 mm plate 100 mm across, pinched at one edge, came back **8.7%
light**, green, with no number anywhere. `voxel_remesh` now also returns how
much material was thinner than one grid cell, reported as `remesh_drift_pct`
and said to the user, and refused over `REMESH_VOLUME_RTOL` (15%). **The first
version of that guard was wrong and the pass caught it**: comparing the result
against the mesh's own `signed_volume` calls a CORRECT repair of two
overlapping bodies 25% wrong, because a signed volume double-counts material
where two surfaces overlap. The number reported now compares the filled grid
against the exact crossing integral over the SAME columns, so overlap cancels
and what is left is the z-quantisation. It sees only material that is thin in
Z; a fin thin in X or Y is lost by the column sampling and shows in neither
term.

**F4 (P1) - a body exported TWICE at the same place was deleted outright.**
`drop_duplicate_walls` removes ALL copies of a duplicated triangle - right for
the interface wall between two touching bodies, that is what merges them, and
fatal when the duplicate IS the whole body. A doubled 10 mm cube beside a
plain one imported as **one body of 1000 mm3 out of 2000**, announced as
"auto-repaired: merged 24 coincident wall triangles"; a file holding nothing
but the doubled body was refused with "no solid found in the mesh".
`dedupe_walls_per_body` decides per connected component now (duplicates share
their vertices, so they always live in one), and a component that would vanish
keeps one copy.

**F5 (P2) - `MIN_COMPONENT_BUDGET` blew the budget the module exists to
keep.** The floor is per BODY and nothing capped the sum: 40 bodies of 5,000
triangles got 1,500 apiece = **60,000 triangles out of an 18,000 budget**,
3.3x what the kernel read and the viewer mesh were budgeted for, and the
ladder's last rung accepts 3x that again. `component_shares` caps the sum of
the targets at `MAX_OUTPUT_MULT` (2x).

**F6 (P2) - a file that is not STEP at all was diagnosed "surfaces or curves
alone cannot be used here"**, sending the user to look for surfaces in a file
that was never STEP. OCCT's reader does not raise on one: it prints
`**** ERR StepFile : Undefined Parsing ...` to the server console and hands
back an EMPTY shape, so the `except` around the read never fired. Checked
against the `ISO-10303` header now.

**F7 (P3) - two more invented diagnoses on the STL side.** A truncated or
part-downloaded binary STL read "not an STL file (neither binary nor ascii
STL)"; it is named as cut short now, with both triangle counts.

**Checked by measurement and left alone** (in the review, so the next round
need not re-open them): format detection - binary, ASCII with LF and with
CRLF, and a BINARY file whose 80-byte header starts with `solid`, all at
exactly 1000 mm3; winding - a fully inverted cube and a 32,204-triangle sphere
with 5% and then 30% of its triangles flipped all import at the true volume,
so `is_clean` being winding-blind costs nothing; `-0.0` against `0.0` welds
(`np.unique(axis=0)`); the decimation ladder's volume guard drifts -0.01% on
that sphere; the voxel remesh itself is accurate on thick non-overlapping
geometry (+0.01% at res=100, -0.01% at res=200, ~5 s); import name collisions
compare BYTES then suffix `-2` so a different file never overwrites an earlier
import; the upload filename is built from the sanitised `feature_id` and
cannot escape `imports/`; a multi-body import is not mislabelled "the part
fell apart" (`_check_pieces` only inspects combiners and modifiers).

**The real file, both ways.** `imports/liquid-piston-2-v1.stl`, the 88,990-
triangle Fusion assembly this pipeline was built against, imports to the
**same geometry as before the fix** - 339,926.9 mm3, 3 bodies, 21,552
triangles, health clean, `remesh_drift_pct` 0.3 - measured against `84e7c17`
in a throwaway worktree. The remesh path costs ~50% more wall clock there
(23.4 s -> 35.9 s) for the winding fill: known and accepted. **No saved design
uses `import_stl` or `import_step`**, so nothing in `designs/` moves.

Two P0s were fixed, so the brief is **PENDING on `94eb47e`** and the next
`code review` re-reads this fix commit before section 9.

### Section 8, ROUND TWO - the fix commit `94eb47e` re-read (2026-09-12, commit `d94518c`, on Fable 5.1 at the user's call)

4 findings, **all 4 fixed, 0 rejected**, 5 new tests (fast tier 1634 -> 1639),
+207 -81 lines. Each measured on `94eb47e` first (`probes/s8r2_a..f.py`),
each locked by a test proven RED there. Two were regressions round one had
introduced; one was round one's P0 still open through another door.

**F1 (P0-class) - the P0 through the INVERSION door.** A hollow part whose
whole file is wound inside-out (a known exporter bug; the plain inverted case
has had a test since import shipped) still imported as **1064 mm3 in TWO
bodies** on `94eb47e`; with a plain body beside it, 2064 in three. Round one
decided void-or-body by the SIGN of each shell's volume, so the inverted outer
shell read as a "void" - orphaned, flipped into a body - and the cavity as a
"body". `_solids_from_shells` decides by **nesting depth** now: OCCT's
`BRepClass3d_SolidClassifier` on one vertex of each shell against every other
shell's outward solid (bounding boxes pre-filter); depth 0 a body, odd a void
of its immediate container, even a body again (a loose part sealed inside a
cavity is its own body - tested). Each shell is then WOUND to fit its role,
whatever the file said: `MakeSolid.Add` needs the void inward (outward, the
same void gave 1064 and `is_valid False`), and the classifier answers OUT
against an inward solid for a point that is inside - both probed
(`probes/s8r2_e_orient.py`).

**F2 (P1, REGRESSION) - a pinched cavity was refused.** A hollow part whose
cavity surface has an overshared edge sent an inward-wound component through
the winding fill, which enters where the winding says "in" - nowhere, on an
inward surface - and raised "voxel remesh produced an empty volume". The
parity fill before `94eb47e` did not care. The component is turned outward
before the fill; a 40 mm cube with a pinched two-cube cavity imports at
62,976.1 of 62,976.

**F3 (P0-class, REGRESSION) - the winding fill broke a documented property.**
`voxel_remesh`'s docstring promised "whatever the input's sins (pinches,
self-touches, inconsistent winding)", and the parity fill kept that promise
because it never looked at direction. The winding fill does: two pinched
20 mm cubes with cube A's top face flipped - a scanner or sculpt-tool export -
came back **7,998.8 of 16,000**, `remesh_drift_pct` 0.0, health [], green.
`winding_is_consistent` judges the edges shared by exactly two triangles (an
edge shared by four carries each direction twice even when every body is
wound perfectly, so a pinch must not count); a component that fails it takes
the parity fill, so no component is worse off than before `94eb47e`. A mesh
that is inconsistent AND overlaps itself is wrong either way, as it always
was.

**F4 (P2) - the new "cut short" diagnosis misfired on a BOM.** A UTF-8
byte-order mark in front of `solid` (a Windows text editor) made
`_stl_triangles` read the text as a binary header: "cut short - its header
says 824,211,557 triangles but only 22 are in the file". The BOM is stripped
and the claim is bounded to a plausible count (50,000,000).

**Structure.** `repair_stl_mesh` writes ONE STL piece with every component in
it; lib3mf reads that as one Solid holding every shell and blocks sorts them.
The round-two brief's "two copies of one rule" - bounding-box nesting in
`meshrepair._group_voids` AND in blocks - is one exact rule now;
`_group_voids` is deleted. Also fixed on the way: the STEP header read held
the file open past the caller's `unlink` on failure (Windows) - a `with`.

**Measured and left alone.** The real 88,990-triangle assembly imports to the
SAME geometry on all three commits (339,926.9 mm3, 3 bodies, 21,552
triangles); 25.1 s on `d94518c` against round one's 35.9 s - the one-piece
read is cheaper. The viewport mesh of a solid carrying a void has the solid's
own signed volume (936.0). No saved design uses either op.

A P0-class gap was fixed, so the brief is **PENDING on `d94518c`** for a third
read before section 9.

### Section 8, ROUND THREE - the round-two commit `d94518c` re-read (2026-09-12, commit `8fdfa5b`, on Fable 5.1 at the user's call)

1 finding, **fixed**; 1 attack cleared; 2 new tests (fast tier 1639 -> 1641),
+122 -12 lines. Measured on `d94518c` first (`probes/s8r3_a..d.py`).

**F1 (P0-class, REGRESSION of round two) - one vertex decided "inside".**
Round two's nesting-depth rule classified ONE vertex of shell B against shell
A's solid. A bracket sitting in the notch of a C-shaped frame, overlapping
the frame's wall by 2 mm - its box inside the frame's box, one corner inside
the frame's material - came in as **ONE body of 20,360 mm3**: the 640 mm3
bracket had been made a VOID of the 21,000 mm3 frame, `is_valid True`,
health [], green. On `94eb47e` and on `84e7c17` it was two bodies. Two bodies
that overlap are two bodies (section 4's documented decision: never fuse).
`_shell_inside` now requires EVERY sampled point of B to classify IN - up to
400 of its unique vertices AND as many face centres, spread over the shell
(`_spread`). The face centres are what catch the nastier cousin, also tested:
a pin whose ends are embedded in the two walls of a U-shaped housing while
its middle spans the gap - every vertex inside wall material, not one face.
A body that pokes out by less than one sampled point in 400 still reads as a
void, and `MakeSolid.Add` then builds an INVALID solid, which the deep
validity pass paints red: wrong, but never silent. Cost (probes/
s8r3_c, s8r3_d): `TopExp.MapShapes` walks a 32k-triangle shell in C++ in
0.075 s where build123d's `.vertices()` took 1.8 s and a Python explorer
3.8 s; 800 points sample in 0.073 s and classify in 0.10 s with ONE loaded
`BRepClass3d_SolidClassifier` (55 us a point; constructing one per point is
the same speed but was the wrong habit). Each shell's sample is built once,
lazily, and reused across candidate containers.

**Cleared** (`probes/s8r3_b_outward_void.py`): a hollow STL whose cavity is
wound OUTWARD - what MeshLab's "re-orient all faces coherently" produces per
connected component - reaches lib3mf as a Solid of 1064 mm3 that OCCT marks
`is_valid False`, so the as-is fast path declines it and the regroup gives
936 / 1 body; with a plain body beside it, 1936 / 2.

The real 88,990-triangle assembly: same geometry on all four commits, 25.2 s.
No saved design uses either op. A P0-class regression was fixed, so the brief
is **PENDING on `8fdfa5b`** for a fourth read - one function family - before
section 9.

### Section 8, ROUND FOUR - the round-three commit `8fdfa5b` re-read (2026-09-12, commit `8241115`, on Fable 5.1 at the user's call) - SECTION CLOSED

1 finding (P1, cost), **fixed**; 4 attacks cleared; 2 new tests (fast tier
1641 -> 1643), +121 -20 lines. Measured on `8fdfa5b` first
(`probes/s8r4_a..f.py`).

**F1 (P1, REGRESSION of round three) - the right answer at an unusable
price.** Round three's "wholly inside" put up to 400 vertices and 400 face
centres of shell B to `BRepClass3d_SolidClassifier` on body A. That
classifier is LINEAR in A's faces: ~5 us a face, **173 ms a point against a
32k-face body** (`probes/s8r4_b_bigcontainer.py`); round three's 55 us/point
had been measured against a 12-face box. A true cavity must have every point
tested, so a real faceted hollow part beside another body in the same file -
lib3mf's one Solid is then invalid and the regroup runs; a hollow part ALONE
is valid and never reaches it - made **800 classifier calls**, ~140 s against
a 32k-face housing, for the P0's own motivating case. Fix: the file's winding
is the primary signal again, but only as a hint geometry confirms. One point
of B (two calls) says whether it sits inside A at all; if it does and the
file wound B INWARD, B is the cavity the file says it is; if the file wound
B OUTWARD - a cavity MeshLab re-oriented, or a body embedded in / overlapping
A - only B's surface can tell, and that survey is sized to what A costs to
ask (`_nest_cap`: a budget of 100,000 face-evaluations per kind - 8 + 8
points against 32k faces, 100 + 100 against 1k, the full 400 + 400 below
250). Face counts and samples are cached per shell. The cliff scenario
(`probes/s8r4_e_cliff_timing.py`, 32k-face housing + 8k-face cavity + a
body) imports in 20-21 s wound either way - all of it the lib3mf read of 40k
triangles. Locked by a test that COUNTS classifier calls (a monkeypatched
classifier), not by timing: <= 8 for a properly wound cavity beside another
body (was 800), <= 2 + 2 * `_nest_cap` for a re-oriented one.

**Cleared** (`probes/s8r4_a, c, d, f`): thin-walled hollow parts down to a
0.005 mm wall import as one body at the exact volume (build123d's bounding
box is not padded, so `_bbox_holds` never loses a void); 40 parts in an OPEN
tray (one shell) and 40 islands sealed in a CLOSED housing both import as 41
bodies in ~1 s (a part in an open cavity is OUT of the tray's shell after
one point; a sealed island is depth 2); `_spread` is 1-based, distinct and
in range at n = 0, 1, cap, cap + 1 and 16103; `BRepExtrema_ShapeProximity`
as a BVH crossing test is a dead end in OCP - lib3mf faces carry no
triangulation (meshing two shells took 6.9 s) and its result map is an
unregistered type; a -0.009% volume gap on a 32k-face faceted sphere is the
decimation ladder's guarded drift (the file is over the 20k clean-path cap
and comes back at 18,000 faces), not the reader.

**Residuals, documented in the code, none silent:** a body embedded in
another by all but less than one sampled point in `_nest_cap` reads as a
void, and `MakeSolid.Add` then builds an INVALID solid - a red row; an
inside-out body that also overlaps another is trusted as a cavity (two
exporter bugs at once) - invalid, red; a mesh whose winding is inconsistent
AND overlaps itself takes the parity fill and loses the overlap, as it did
before any of this.

**Section 8 is CLOSED**: four rounds, 13 findings, all fixed, 0 rejected, 20
tests, fast tier 1623 -> 1643. The real 88,990-triangle assembly imports to
the same geometry on all five commits. No saved design uses either op. Brief
is NOTHING PENDING; the next `code review` takes section 9, Trace image.

### Section 10 - Viewport, picking and face provenance (reviewed and fixed 2026-09-16, commit `8aa30a2`; round two `9f1b421`)

ONE reviewer, high effort. 5 findings, **all 5 fixed, 0 rejected**, 9 new
tests. The scope was widened on purpose to include `blocks.resolve_face` and
the face-pick size gate of `1a8d28f`, which was hours old and had never been
read by anyone but its author.

- **F1 (P1) - the size gate could refuse an edge that is still on the body.**
  A stored pick whose face GROWS past its recorded area falls through to a
  same-sized face elsewhere; the two host faces of the picked edge then share
  no edge and the feature goes red with "the picked edge is no longer on the
  body - re-pick the edges of this feature". Measured on a plate with two
  200 mm2 pads (20x10 and 25x8): widening the filleted pad 20 -> 24 mm killed
  its own chamfer, though the rim had moved 2 mm. Fixed with `_shared_edges`
  and a two-pass loop - stored sizes first, sizeless second, a refusal earned
  by both.
- **F2 (P2) - no tapered, lofted or swept wall could be sketched on.** The
  Sketch tool's plane picker decided FLAT from the surface TYPE while
  `selectFace`'s own button read `planar`; all four walls of a 12-degree
  tapered box are BSPLINE and planar, and `face_outline_2d` returns 56 points
  for them. One `isFlatFace` helper now serves all four doors.
- **F3 (P2) - `attribute_face` named the wrong feature with "high" confidence.**
  Its stale-index fall-back never consulted the area it was handed, and the
  browser rounds the centre to 2 decimals, so a flush pad in a round pocket
  (113.10 mm2) tied exactly with the pocket top (2343.36 mm2) and the kernel's
  face order decided. `_area_matches` narrows the candidates when something
  matches and fails open when nothing does.
- **F4 (P2)** a link in the "Created by" chain revealed the tree row and lit
  nothing (`S.selected` is never written on that path). **F5 (P3)** an
  imported mesh body's face click blamed a document change that never
  happened, for ever.

**Round two (`9f1b421`) found 0 findings in round one's own code** and proved
it by measurement rather than by reading: the sizeless fall-back never runs on
any of the 9 gauntlet bodies' 135 edges; when forced to run it names the right
rim at all twelve widths, never the pad 50 mm away; and over 752 resolutions
of every corpus edge against every other corpus body it newly answers in
exactly one. `isFlatFace` admits no wall `selectFace` did not already admit
(the diff's pre-image proves it). `_area_matches` falls open on a pick with no
area at all - every design saved before 2026-09-16.

**The one thing round two did find is NOT in section 10's files.** A live face
click carries the area of the mesh ON SCREEN, and while Fillet/Chamfer is open
that mesh is the tool's PREVIEW body - so a face the preview TRIMMED resolves
on the input body by its trimmed area. Measured: a bracket whose pad Q top is
180 mm2, exactly what an r2 fillet leaves of pad P's 200 mm2 top; clicking pad
P's top resolves pad Q's, 50 mm away, and `toolplan._face_of` does not refuse
because `surface_gap` ignores trimming on purpose and both tops are coplanar
+Z. `plan_fillet` would then round every edge of the wrong pad, silently. It
needs the area coincidence - a sweep of 64 planar preview faces at four radii
found none - but it is silent wrong geometry when it happens. Carried out of
the section because `toolplan.py` belongs to section 11.

**Section 10 is CLOSED** (two rounds, 5 findings, all fixed, 10 tests).

### Section 11 - Tool framework core (reviewed and fixed 2026-09-16/17, `a3d6b03`; rounds two `217d289`, three `931f747`)

Three rounds, 10 findings, all fixed, 0 rejected, 39 new tests. **Two P0s, and
they were the SAME P0 through two doors.**

- **Round one's P0** - a tool panel open on design A, a click on design B's
  document tab, OK: the edit lands on B. The tab bar was the one control not
  behind `modalGuard`, and `uid()` hands out the same feature names in every
  design. Measured: B's `extrude1` 9 -> 30 mm.
- **Round two found it still open**, through the door round one's own commit
  message had named: a panel never listens for `doc-updated`, and a design
  ARRIVING from outside (an AI over MCP, the doorbell, a second browser
  window) takes the active tab with no tab-bar click at all. The session now
  records the tab it was opened on and lets go, writing nothing, with a
  sentence. Its residual - the let-go fires only when the browser HEARS - was
  closed later by the tab header (section 12 round four plus the browser half).
- **Round three re-read that let-go in node** and cleared it: it compares
  `doc.active_tab`, the server's tab id, never the design NAME, so a rebuild,
  an Undo, a version restore and a **rename** all leave the panel open.
- **The carried P0 from section 10 was closed here**: while Fillet or Chamfer
  is open the click carries the PREVIEW body's area, so a face the preview had
  TRIMMED resolved on the input body by its trimmed area - pad Q's top at
  180 mm2 is exactly what an r1 blend leaves of pad P's 200 - and
  `plan_fillet` rounded every edge of the wrong pad, silently. Section 10's
  proposed `OnFace` gate was **evaluated and rejected by measurement** (an
  annulus's own centroid lies in its hole, so a good pick would be refused);
  the rule `resolve_edge` already uses was used instead. **284 clicks on real
  preview bodies: 0 moved, 0 newly refused.**
- Also fixed: a mistyped spec box deleting a requirement and reporting a pass
  (round one for `holes`, round two for the other six); a selected sketch row
  outranking a curved-face pick so Extrude silently extruded the sketch; a
  missing bracket adding nothing and saying nothing; a non-200 plan answering
  "cannot start: undefined", then "the server said 400", before finally
  speaking the server's own sentence; and the extrude arrow and taper ring
  sitting on the average of the sampled boundary points (12.404 mm off on two
  islands) instead of the area centroid.

Cleared by measurement rather than reading: the new tab guard does **not** lock
the user in (every exit releases the modal), and the centroid change is gizmo
placement only (the whole plan dict byte-identical over ten profiles apart from
`origin` and `outer_radius`, which reach only the arrow and the ring).

**Section 11 is CLOSED.**

### Section 13 - AI author, MCP and chat (reviewed and fixed 2026-09-17, `6b7198d`; rounds two `0cc2faa`, three `d369595`)

Three rounds, 16 findings, 14 fixed, 0 rejected, 2 deferred, 32 new tests. The
section had **no MCP test at all** before this pass.

- **P0 - the MCP doors overwrite a design in the user's library** and graft the
  AI's part onto its version tree. `build_design` with no `name` is called
  `untitled`, and `designs/untitled.tcad.json` is a real design with a real
  `.history/`; `Document.save` is a plain overwrite with no owner check, and
  the doorbell then pushes a version into that design's history. Measured: the
  user's design destroyed. A name this server wrote is re-used (so the
  regenerate-and-look loop still lands in one file); anything else gets the
  first free `-2`. Round two tightened it further: a name is ours only while
  the file is still the one we wrote, because the user may have edited it.
- **P1, three rounds to close - the AI could not touch 27 of the 50 saved
  designs.** The authoring lint judged the WHOLE tree, so "add a boss to this"
  on `esp32-remote` was refused for a sketch the user had drawn at an absolute
  Z. Round one scoped the ADD door (28 blocked -> 1). Round two found the EDIT
  door still shut - it linted `authored | {the edited feature}`, and the edited
  feature is always the user's - and replaced scoping with a BASELINE: what the
  tree already broke when the job started, reporting only what is new or worse
  (27 -> 0). Round three found the baseline had dropped the owner test on the
  **blob** rule, the one key with no feature id, so the AI refused to extrude a
  sketch the user drew by hand. Each time, the failure ended in the same
  sentence: *"I did NOT change your design."*
- **`verify_step` gave a verdict on requirements it never checked** - an
  unknown key is dropped silently by `spec_from_dict`, and `size: [40, 30]`
  zips against a measured triple so Z is never compared - while its own
  docstring calls an empty mismatch list a proof. `checked_spec` refuses an
  unmeasurable key by name now, at the chat's `done` door and the MCP door
  alike. `measure_step` was cleared: it never invents a number.
- Also fixed: the catalogue advertised three `polar_pattern` axis values the op
  refuses by name (the AI reads this, and so does the Add Feature dropdown);
  `list_operations` handed a calling AI the step-loop prompt as `build_design`'s
  conventions, so a reply in the shape it asks for is rejected; `done` was
  judged on the whole tree; `design_compressor` answered a degenerate duty with
  a ZeroDivisionError, and its first guard was wider than its own equation.

Verified rather than assumed: the baseline **cannot mask a fault the AI
introduces** (every other key carries the feature id; `Document.add` and
`from_data` both refuse a duplicate id; the baseline is the first statement of
`author_steps`; every masking attempt measured was refused); `AUTHOR_PROMPT` is
byte-identical to before the prompt split (15529 chars, compared out of git);
0 of the 50 saved designs carry a spec key the new rule refuses.

**Deferred** (rows owed in LAUNCH-PLAN section 10): `op_params` cannot
distinguish "no default" from "default is None", so the catalogue cannot mark a
required parameter and a missing one reaches the feature row as a raw
`TypeError`; the 10-entity sketch limit never looks at `sketch_on_face`, the
only sketch kind the offset method uses, while the same prompt teaches putting
a whole bolt grid in one - a product decision; and `meanline.design` answers
geometrically impossible duties (rpm 1 gives a 4,221,135 mm tip radius; a
negative radius reaches OCCT).

**Section 13 is CLOSED.**

### Section 12 - Server layer (reviewed 2026-09-16/17; seven rounds, `b88d870` -> round seven empty)

19 findings, 17 fixed, 1 rejected, 1 carried, 60 new tests. **Four P0s, and
three of them were the same defect found again after it had been "fixed".**

**The spine: a request that asks twice which tab it is about.** `_doc()`,
`_entry()`, `_slug_of_active()` and their helpers each went to
`STATE["active"]` independently, and the MCP doorbell
(`/api/open/<slug>?external=1`) moves that from its own thread - both
endpoints are sync `def`s, so FastAPI runs them side by side in the threadpool.

- **Round three** measured `/api/export` writing design A's **2000 mm3** solid
  into design B's `.step` (B is 3600 mm3), status 200, "Exported", no warning;
  `/api/save` had the same seam and worse, because the mis-binding PERSISTS.
- **Round four** found that was a point repair: **25 other routes had the same
  seam.** Measured with a real race, nothing patched - `/api/trace-png` put a
  traced logo into a saved library design the user never opened, and that
  design's undo depth was **0**, so Ctrl+Z on it does nothing (104 ms window).
  `/api/chat` read the active tab **25 times in one request**, so the AI could
  build in a design the user never asked about with "one Undo takes it all
  back" false. Fixed with ONE mechanism - a request resolves its tab once,
  carried in a context var armed by a middleware - not 25 repairs.
- **Round five** found the pin protected exactly one request and the ANSWER
  gave the next away: `_doc_json` labels every reply with the LIVE active tab,
  so a poll carrying tab A's tree came back labelled the arriving tab and the
  browser handed that label back as its next header - the next edit set the
  ARRIVING design's `base.thickness` to 41 while the design on screen kept 5.
  It also found **nine `fetch(` sites bypass `api.js`**, so File > Export wrote
  the arriving design's solid and reported it as the export just asked for.
- **Round six** found the page-wide fetch door was STRING-ONLY while three.js
  r160's `FileLoader` calls `fetch(new Request(...))`: `/api/feature-mesh` went
  out bare and the viewport could be drawn another design's mesh (bbox
  [20,20,5] with the header, [60,60,30] without). Wrong picture, not wrong
  edit, so P1.
- **Round seven found nothing**, and proved it: 26 URL shapes through a real
  loopback server, 46 tab-sensitive endpoints x 3 header states = 140 asks all
  correct, the one-writer guard right in all 16 cells (including failing OPEN
  when the guard itself raises), no fast-tier test ringing port 8123, and
  `designs/` byte-identical over 397 files.

**Also closed, from the earlier rounds:**

- **A restart threw away the tab you were looking at.** The session checkpoint
  slices `[:MAX_TABS]`, which keeps the OLDEST twelve; measured with 13 open,
  the 13th - active, holding unsaved work - did not come back and nothing said
  so. Every tab is restored now (40 heavy tabs in 176 ms, only the active one
  rebuilt).
- **`/api/export` overwrote another design's `.step`** under a name neither the
  save nor the MCP uses - then round one's cure **refused Export outright on
  `esp32-remote-live-t2` and `-t3`** (both carry the NAME `esp32-remote`) and
  moved two more designs off their own file. Round one had claimed all 50
  designs have `name == slug`; four do not. Export takes the stem of the FILE
  the tab is bound to now: 0 of 50 refused, 0 of 50 moved.
- **`/api/spec` stored a value of any type and poisoned the document**: 200
  carrying a `TypeError`, the value KEPT, every later `/api/edit` repeating it,
  and `/api/save` writing it into the `.tcad.json`. Round two found the same
  failure still reachable through `10**400` (`OverflowError`).
- **The fast tier designed a washer into the user's library and rang their live
  app** - `designs/t-washer.*` plus `POST /api/open/t-washer?external=1` to
  port 8123, which takes the active tab and puts a banner over their work. A
  library-wide `DESIGNS` fixture is NOT safe (the `-m library` tier and two
  gallery tests read the real folder on purpose), so the guards are
  file-scoped.
- **Five refusals answered 200**, and `/api/export` made four OCCT calls under
  no kernel lock. The deadlock question the lock raised was settled by
  measurement: `_KERNEL_LOCK` is an `RLock`, pinned by a test that goes red if
  anyone makes it a plain `Lock`.

**Rejected:** `n_solids`/`symmetry` accepting any int - measured not to poison
anything (`/api/edit` stays 200, the document stays saveable, `verify` answers
with a failed requirement, and `symmetry=10**9` is bounded at 0.02 s).

**Carried:** `doc = e["doc"]` can still go stale if `/api/open` reloads that
same tab mid-request (needs a per-tab lock) - a lost update between the user's
own two actions, no cross-design loss.

**A product change the user should know about:** two browser windows now hold
INDEPENDENT tabs - window one no longer follows window two's switch. That is
what addressing a request to a tab means, and save, export and the viewport all
follow the window's own tab now.

**Section 12 is CLOSED.**

### Section 9 - Trace image (reviewed 2026-09-17; four rounds, `4c9ea32` -> round four empty)

18 findings, 11 fixed, 4 rejected, 5 carried, 22 new tests. Never reviewed
before. **Five P0s, and every one of them is the same failure: artwork traced
as its own NEGATIVE.**

- **Round one** found it in the original rule, which called the *minority* half
  the ink: any logo cropped to its own ink traces its background. A 40 mm disc
  at 78% ink traced its four corners (343.5 mm2 of 1256.6), inverse-video art
  failed identically, and **the user's `esp32-remote` `logo_0_sketch` is this
  bug sitting in the library** - one 533.34 mm2 slab with six letter-shaped
  holes, the negative of "autonomIQ". Both its logo features are suppressed, so
  it was never machined.
- **Round two** found round one's replacement (the outermost 1 px ring) had
  **re-opened the same P0**: a thin dark edge - a scan's platen edge, a printed
  rule box, the 1 px frame an exporter leaves - made five letters trace as ONE
  contour with five letter-shaped holes.
- **Round three** found round two's replacement had re-opened it twice more: a
  thin LIGHT pad was stripped as a "frame", so a plate with nine bolt holes
  traced 440.1 mm2 of a true 1258.0 (10 contours / 1 hole instead of 1 / 9);
  and round two's own headline case was still open for art under 1% of a sheet
  (the paper traced as a slab with a logo-shaped hole, 1587.8 of a true 102.1).
- **Round four found nothing** and closed it.

**The transferable lesson is about measurement, not tracing.** Round one scored
its rule 9-vs-7 and round two 12-vs-11 - each on a corpus it had chosen itself.
An outside corpus showed round one was a net REGRESSION (29 of 74) and round
two merely a TIE with the original (54 against 55). Only by the fourth round,
scoring four real modules on four independent corpora, did a number hold up:

| corpus | n | original | round 1 | round 2 | shipped |
|---|---|---|---|---|---|
| round one's | 10 | 7 | 9 | 9 | 9 |
| round two's | 15 | 11 | 10 | 12 | 12 |
| round three's | 21 | 17 | 10 | 14 | 16 |
| round four's | 28 | 20 | 13 | 19 | 21 |
| **all four** | **74** | **55** | **42** | **54** | **58** |

Reported the other way too, because it matters: on round three's own corpus the
original edges the shipped rule 17-16, and on a 458-picture random generator
round two edges it 331-324. What settles it is health, not polarity - over the
same 450 traces the ORIGINAL module hands `sketch.py` **720 self-crossing edges
and builds 30 unhealthy solids**, the shipped module **0 and 2**.

**Also fixed:**

- **`_uncross` discarded real artwork.** Round two's own fix for self-crossing
  outlines cut the smaller loop off at every crossing; its claimed bound (the
  loop is `eps` wide) did not hold. Two discs joined by a 1 px bar traced
  **1237.16 mm2 of a true 2498.45** - one disc - valid, healthy, no warning, at
  every size. A loop that turns the same way as the piece it came from is kept
  as its own polygon now; worst area loss across a 441-trace fuzz: 0.000%.
- **A 2x2 speck decided the fit height and the 90-degree auto-rotate**, because
  `artwork_aspect` read the RAW mask while the tracer speckle-cleans it: the
  same logo landed on a 120x40 face at 7.2 x 36.0 mm standing up instead of
  107.9 x 21.6 lying along it - a ninth of the area, and exactly the "vertical
  position, its no use" the rotate exists to prevent. Later, five pieces 9.7 mm
  across were REFUSED outright for one speck, and the 1.66 mm dot of an "i"
  vanished silently.
- **Outlines that cross themselves reached `sketch.py`** - OpenCV walks out and
  back along a 1 px whisker and Douglas-Peucker turns the touch into a
  crossing; a comb had 26 crossings in one outline and 1 trace in 60 built a
  body OpenCASCADE calls invalid. Also, the crossing test was decided in the
  last bits, so an outline `_uncross` had just certified came out of
  `_poly_entity` crossing again.
- **A numpy traceback reached the chat** ("zero-size array to reduction
  operation minimum") for art that would be under 0.25 mm at the fitted height.

**Rejected by measurement** (round four): a light shell round a dark region is
a coin flip by geometry alone - a margin round a *plate* and a margin round a
*card* are identical, three discriminators were built and all three measured
wrong - so the rule picks the side this product's input is on (all five traced
designs are dark-on-light); the 64 px floor's one remaining window is
unreachable except by a picture built to hit it, and closing it re-opens round
two's P0; the fat-mount failure is the documented one (the corner of a *t* px
band is *t*root2 thick); and `_first_crossing`'s new tolerance cannot call a
legitimate touch a crossing (168 outlines, six constructed touching shapes).

**Cleared:** nested holes never come out filled (ring-hole-island-hole gives
add/subtract/add/subtract at 98.9% of the ideal area); traced art is not
mirrored on a plane sketch and the auto-rotate is a proper rotation applied
once; all 346 polygon entities across the 50 saved designs have no
self-crossings, no duplicate points and none under 3 points; 14 degenerate
inputs all answer with a sentence. The five traced designs re-derive unchanged
except `esp32-remote`'s logo, which goes from the 6-contour slab to **9
contours and 4 holes** - nine glyphs and four counters, which is what
"autonomIQ" in Impact has. Wrong to right.

**Carried** (rows in LAUNCH-PLAN section 10): the fit path measuring its aspect
at the default 50 mm and tracing at another height (P1, needs `studio.py`); art
on a down-facing face reading mirrored (P1, needs `sketch.py` and a product
decision, since flipping the frame would mirror every existing face sketch);
the auto-fit box being the face bbox so art overflows a round face (P2); the
5% threshold's knife edge (P2); two traced holes touching at exactly 0.000000
mm pinching the face (P2, pre-existing and far worse before this pass); the
traced bbox including contours `min_area` drops (P3); and `_bridge_pieces`
giving up after 16 welds (P3, API-only, left on purpose).

**Section 9 is CLOSED.**
