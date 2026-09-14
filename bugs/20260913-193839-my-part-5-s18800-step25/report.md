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
