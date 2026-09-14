# kernel-crash: my-part-5, seed 18800, step 25

'j14_shell' (shell): shell: walls of 2.1 mm crashed the geometry kernel — nothing was changed and the app is unharmed. This body's faces cannot all be offset by 2.1 mm at once. The thicknesses that work are not one band, so a thinner AND a thicker wall are both worth trying, or open another face.

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j14_shell",
 "op": "shell",
 "params": {
  "thickness": 2.1,
  "open_face": "bottom"
 },
 "inputs": [
  "j2_mirror"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-193839-my-part-5-s18800-step25

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

---

## Fixed 2026-09-14 — there were TWO findings in this folder

**The segfault is real, and it stays a refusal.** `shell {thickness 2.1,
open_face "bottom"}` on this body kills OpenCASCADE, and so does every
thickness from 0.2 to 5 mm with the bottom open, and all but 0.2 with the top
open (`probes/shell_mirror_crash.py`). No bound fences that — the CLOSED
direction builds at some of the same thicknesses — so it belongs to the kernel
worker, which already survives it: a sentence, a red row, nothing changed. The
body is committed as `tests/fixtures/my_part_5_mirror_body.brep` and the
refusal is now a test (`tests/test_kernel_guard.py`, `KILLERS`
`shell_open_mirror`).

**The P0 was hiding beside it**, the way my-part-8's silent fillet hid behind
its crash. The same sweep found two CLOSED shells on this body that came back
"successful":

    t = 1.5   413262.875 -> 137707.973 mm3   watertight, but is_valid FALSE
    t = 3.0   413262.875 -> 413260.165 mm3   valid, watertight, health empty

The second is the body handed back as a hollow: 2.709 mm3 of 413262.875
removed, 0.00066 per cent, green in the tree and saveable. Every check that
existed asked about IDENTITY, and "nothing was hollowed" is
`abs(v_out - v_in) <= 1e-6`, which 2.709 clears by seven orders of magnitude.

Fixed: `sketch.assert_walls_could_be_a_skin` measures the walls against
`area * t` (an inward shell's walls lie within `t` of the surface they came
from, so they can never be a multiple of that), and `shell_after_guards` now
asks OpenCASCADE for its own verdict instead of only counting edges. The
ceiling is 2.0 against a measured ceiling of 1.056 over the gauntlet corpus
and the committed crash bodies at nine thicknesses
(`probes/shell_wall_bound_corpus.py`).
