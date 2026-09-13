# hang: autonomiq-panel, seed 46927, step 16

add shell took 1195 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j8_shell",
 "op": "shell",
 "params": {
  "thickness": 2.2,
  "open_face": "top"
 },
 "inputs": [
  "j4_linear_pattern"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-011500-autonomiq-panel-s46927-step16

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 16 (add shell) took 1195472 ms
