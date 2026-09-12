# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review commit **`d94518c`** — round TWO's fix pass for
> `REVIEW-QUEUE.md` section 8 (Import STL and STEP). Round two fixed a
> P0-class gap and two regressions round one had introduced, and it replaced
> the shell-grouping rule outright, so the queue's step 8 calls for a third
> read of THIS commit before section 9.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range named here; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes.

---

## What to review: `94eb47e..d94518c` (one commit)

`blocks.py` (`_outward`, `_shell_inside`, `_solids_from_shells`,
`_stl_triangles`, `_resolve_step_path` only) and `meshrepair.py`
(`winding_is_consistent`, `voxel_remesh`, `repair_stl_mesh`; `_group_voids`
deleted). +207 -81 lines. Fast tier 1634 -> 1639.

Round two (run on Fable 5.1 at the user's call, 2026-09-12) re-read `94eb47e`:
4 findings, all 4 fixed, 0 rejected — two of them REGRESSIONS round one had
introduced, one the round-one P0 still open through another door, one a wrong
diagnosis round one wrote. Each measured on `94eb47e` first
(`probes/s8r2_a..f`), each locked by a test proven RED there.

## Where the risk is

1. **`_solids_from_shells` now decides void-or-body by NESTING DEPTH, with
   OCCT's `BRepClass3d_SolidClassifier` on ONE vertex of each shell against
   every other shell's outward solid.** One vertex is enough for a shell that
   is wholly inside or wholly outside; a shell that TOUCHES another (a vertex
   `ON`) reads as not inside. Worth attacking: a void whose vertex lands
   exactly on the outer wall (a zero-thickness spot — an invalid solid either
   way, but what does the row say?); the `1e-7` classifier tolerance on
   float32 mesh coordinates; a file with dozens of shells (n² classifier
   calls, bbox-prefiltered — is it still seconds?). The depth rule assumes a
   nesting TREE: two shells that cross each other (overlapping bodies in the
   CLEAN path, which never sees the remesh) each get depth 0 — two bodies,
   as before. Confirm nothing else changed for that case.
2. **Orientation is FORCED from the role** (`_outward`, then
   `TopoDS.Shell_s(...Reversed())` for a void). Probed: an outward void gives
   1064 mm3 and `is_valid False`; the classifier answers OUT against an
   inward solid. Both traps are now documented in the code — check the code
   never takes either path.
3. **`voxel_remesh` has TWO fills again**: winding when
   `winding_is_consistent(faces)`, parity otherwise. The consistency test
   judges only edges shared by exactly two triangles. A mesh that is
   inconsistent AND overlaps itself is wrong either way (as before `94eb47e`,
   by parity). Attack the test itself: a consistent mesh it calls
   inconsistent (a component with a pinch AND a legitimately doubled edge?)
   would silently lose the overlap fix; an inconsistent one it calls
   consistent would take the winding fill and lose material.
4. **`repair_stl_mesh` writes ONE STL piece** and lets blocks sort the
   shells. Confirmed on the real assembly (same three volumes, 25.1 s). The
   report's `bodies` now counts COMPONENTS (voids included) until
   `_read_stl_solids` overwrites it with the kernel's count — a caller that
   read `repair_stl_mesh`'s report directly would see the component count.
   The only such caller is the module's own self-test.
5. **`_stl_triangles`** strips a BOM with `data[:83].removeprefix(...)` and
   bounds the "cut short" claim at 50,000,000 triangles. Check the
   `test_input_triangle_cap` fixture (500,001 declared, exact size) still
   takes the binary branch.

## Measured, and not worth re-reporting

- `imports/liquid-piston-2-v1.stl` (88,990 triangles): **339,926.9 mm3, 3
  bodies, 21,552 triangles, health clean** on `84e7c17`, `94eb47e` AND
  `d94518c`; 23.4 s / 35.9 s / 25.1 s.
- **No saved design uses `import_stl` or `import_step`.**
- Round one's cases all still measure right on `d94518c`: hollow 936/1 body;
  hollow + plain body 1936/2; hollow through the repair path 2936/2;
  duplicated body 2000/2; welded overlap 11,998; thin plate 5,531.75 with
  `remesh_drift_pct` 8.3 reported; disjoint pinched cubes 15,998.
- Round two's cases on `d94518c`: inverted hollow **936/1** (was 1064/2);
  inverted hollow + plain **1936/2** (was 2064/3); pinched cavity **62,976.1**
  (was refused "empty volume"); pinched cubes with a flipped face **15,998**
  (was 7,998.8); BOM ASCII imports at 1000 (was "cut short, 824,211,557
  triangles"); a body sealed inside a cavity (depth 2) is its own body,
  6,336/2.
- The viewport mesh of a solid carrying a void: signed volume 936.0 = the
  solid's volume (`studio._tagged_mesh`, `probes/s8r2_d_classifier_bom.py`).
- Do not re-open the round-one "checked" list (format detection, winding on
  clean meshes, `-0.0` welding, the decimation ladder, name collisions, the
  upload path, `_check_pieces`).

## The ground rules

Read the diff itself. One reviewer, no subagents. Reproduce by measurement
before reporting; a finding that does not reproduce is rejected with a line.
The shared rules of engagement and the output format are in `REVIEW-QUEUE.md`.

**If this round finds nothing**, set this file back to `Status: NOTHING
PENDING` and the next `code review` takes **REVIEW-QUEUE.md section 9, Trace
image**.
