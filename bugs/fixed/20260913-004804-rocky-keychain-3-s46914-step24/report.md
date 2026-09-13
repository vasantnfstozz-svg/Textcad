# hang: rocky-keychain-3, seed 46914, step 24

edit  took 124 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/edit`

```json
{
 "feature_id": "j8_fillet",
 "param": "radius",
 "value": 2.75
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-004804-rocky-keychain-3-s46914-step24

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 20 (edit ) took 109633 ms
- step 24 (edit ) took 124363 ms
