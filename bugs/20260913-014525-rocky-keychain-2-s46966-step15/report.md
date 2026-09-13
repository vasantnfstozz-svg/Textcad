# hang: rocky-keychain-2, seed 46966, step 15

add chamfer took 630 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j5_chamfer",
 "op": "chamfer",
 "params": {
  "length": 2.5,
  "edges": "all"
 },
 "inputs": [
  "j3_mirror"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-014525-rocky-keychain-2-s46966-step15

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 15 (add chamfer) took 629507 ms
