# hang: autonomiq-sat-panel, seed 18886, step 18

add chamfer took 135 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j8_chamfer",
 "op": "chamfer",
 "params": {
  "length": 1.7,
  "edges": "all"
 },
 "inputs": [
  "autonomiq_sat_panel"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-213021-autonomiq-sat-panel-s18886-step18

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 18 (add chamfer) took 135307 ms


---

## Retired 2026-09-14 — NOT a product bug

This folder was filed by the journey runner's own clock, not by the product.
It was a 135 s `chamfer` that answered 200 — see above: under the app's own 900 s budget, not a finding.

Both defects are fixed in `751db79`: the runner reads
`QueryUnbiasedInterruptTime`, which stops at suspend, and its step limit is now
`kernelguard.DEFAULT_BUDGET` — the app's own — instead of a private 120 s.
Kept as the evidence those tests were written from (`tests/test_journeys.py`,
"the clock"); nothing here needs fixing in the product.
