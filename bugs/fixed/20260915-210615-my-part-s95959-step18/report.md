# kernel-crash: my-part, seed 95959, step 18

'j8_shell' (shell): shell: walls of 1.1 mm crashed the geometry kernel — nothing was changed and the app is unharmed. This body's faces cannot all be offset by 1.1 mm at once. The thicknesses that work are not one band, so a thinner AND a thicker wall are both worth trying, or open another face.

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j8_shell",
 "op": "shell",
 "params": {
  "thickness": 1.1,
  "open_face": "top"
 },
 "inputs": [
  "j5_shell"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260915-210615-my-part-s95959-step18

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.


## Triage 2026-09-16 (fixing chat)

Measured with `probes/shell_thin_wall_probe.py`: the crash boundary on this body
is exactly half its 1.3 mm wall (0.64 builds, 0.66 segfaults). A 1.1 mm shell
with the top open is a legitimate 0.2 mm recess in the lid (the lid is 1.3 mm
from the cavity ceiling), so no pre-kernel rule refuses it without refusing
correct geometry; the kernel crashes on legitimate input there and the kernel
worker turns that into a sentence — which is what this folder recorded. The
crash is locked in as `tests/test_kernel_guard.py` KILLERS `shell_twice`.

What the finding DID lead to: `sketch.assert_something_would_be_hollowed`, a
pre-kernel refusal for any body that is thin EVERYWHERE relative to the wall
(closed, this body is refused from 0.66 mm up; with the top open from 1.3 mm),
validated over the corpus with zero false refusals
(`probes/shell_thin_wall_corpus.py`). Retired to `bugs/fixed/`.
