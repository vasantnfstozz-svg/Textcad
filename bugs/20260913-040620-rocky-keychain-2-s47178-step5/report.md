# hang: rocky-keychain-2, seed 47178, step 5

add fillet took 156 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j3_fillet",
 "op": "fillet",
 "params": {
  "radius": 2.2,
  "edges": "all"
 },
 "inputs": [
  "field_tool"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-040620-rocky-keychain-2-s47178-step5

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 5 (add fillet) took 156152 ms
