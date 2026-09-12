# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review commit **`94eb47e`** — the fix pass for
> `REVIEW-QUEUE.md` section 8 (Import STL and STEP). Two P0-class findings
> were fixed, so the queue's step 8 calls for a second round, and this pass
> rewrote the inside of the voxel fill and added three refusals.
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

## What to review: `84e7c17..94eb47e` (one commit)

`meshrepair.py`, `blocks.py` (`_bbox_holds`, `_solids_from_shells`,
`_stl_bytes_to_solids`, `_stl_triangles`, `_resolve_step_path` only),
`studio.py` (the `repair_note` block in `import_stl_file` only).
+417 -37 lines. Fast tier 1623 -> 1634.

Section 8 had never been reviewed. 7 findings, all 7 fixed, 0 rejected, 0
deferred; each reproduced by measurement first (`probes/s8_a..m`) and each
locked by a test proven RED on the code as it stood.

## Where the risk is

This pass rewrote the **inside of the voxel fill** and added **three new
refusals**. On this project a fix pass's own new guard has been wrong more
often than not, and one of this pass's guards already refused correct
geometry once during the pass itself (see the third item).

1. **`voxel_remesh` now fills by WINDING NUMBER, not parity** (meshrepair.py).
   Every crossing carries `step = -1 if d > 0 else 1` and a cell is inside
   where the running winding is positive. Worth attacking: a surface exactly
   tangent in Z (`abs(d) < 1e-12` is skipped, so a vertical wall contributes
   nothing — is that still right when the winding has to balance?); two
   coincident crossings at the same z with opposite steps; a column left open
   (`wind > 0` at the top) now keeps what it accumulated instead of being
   dropped whole, which is a deliberate change of behaviour.
2. **`_solids_from_shells` decides what a VOID is by the sign of its solid's
   volume, and which body owns it by BOUNDING BOX containment, smallest
   first** (blocks.py). Bounding boxes are not containment: two bodies whose
   boxes nest but whose material does not (an L inside the box of a C) can
   hand a void to the wrong body, and a void touching its body's own box
   within 1e-6 is a tie. The same rule runs again, independently, over the
   MESH in `meshrepair._group_voids` — two copies of one rule.
3. **The remesh fidelity number** (`lost` out of `voxel_remesh`) compares the
   filled grid against the exact crossing integral over the SAME columns. The
   first version of this guard compared against the mesh's own signed volume
   and refused a CORRECT repair of two overlapping bodies as "25% wrong"
   (measured). The number it reports now only sees material that is thin in
   **Z** — a fin thin in X or Y is lost by the column sampling and shows up
   in neither term. It refuses over `REMESH_VOLUME_RTOL` (15%).
4. **`dedupe_walls_per_body` calls `split_components` a second time** on every
   dirty import, and decides "the whole body is a duplicate of itself" with
   `dup.all()`. What does that do to a body whose every triangle happens to
   be duplicated for some other reason?
5. **`component_shares`** changed what every multi-body import is decimated
   to. The cap is on the sum of the TARGETS; `decimate_guarded`'s ladder can
   still return up to 3x a share, or the undecimated component.
6. **`_stl_triangles`** now raises "cut short" where it used to say "not an
   STL file". Check the branch order against a genuinely empty binary STL
   (exactly 84 bytes), an ASCII file whose header does not start with `solid`,
   and the `MAX_INPUT_TRIANGLES` test's synthetic file.

## Measured, and not worth re-reporting

- The real 88,990-triangle Fusion assembly (`imports/liquid-piston-2-v1.stl`)
  imports to the **same geometry as before this commit** — 339,926.9 mm3, 3
  bodies, 21,552 triangles, health clean, drift 0.3% — checked against
  `84e7c17` in a throwaway worktree. The remesh path costs ~50% more wall
  clock there (23.4 s -> 35.9 s) for the winding fill; that is known and
  accepted, not a finding.
- **No saved design uses `import_stl` or `import_step`** (0 of the library),
  so nothing in `designs/` moves.
- The winding fill is identical to the parity fill on any mesh that does not
  overlap itself, by construction.
- Already checked and sound in the review, do not re-open: format detection
  (binary, ASCII LF and CRLF, a binary header that starts with `solid`);
  inverted and mixed winding (a sphere with 30% of its triangles flipped
  imports at the true volume); `-0.0`/`0.0` welding; the decimation ladder's
  volume guard (-0.01% on a 32,204-triangle sphere); import name collisions
  (byte comparison then a `-2` suffix); the upload filename cannot escape
  `imports/`; a multi-body import is not called "the part fell apart".

## The ground rules

Read the diff itself. One reviewer, no subagents. Reproduce by measurement
before reporting; a finding that does not reproduce is rejected with a line.
The shared rules of engagement and the output format are in `REVIEW-QUEUE.md`.

**If this round finds nothing**, set this file back to `Status: NOTHING
PENDING` and the next `code review` takes **REVIEW-QUEUE.md section 9, Trace
image** (it was scoped to share a chat with section 8 and did not).
