# hang: fan-disk, seed 18895, step 29

add linear_pattern took 164 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j14_linear_pattern",
 "op": "linear_pattern",
 "params": {
  "count": 4,
  "dx": 1.7,
  "dy": 8.0,
  "dz": 0
 },
 "inputs": [
  "j11_move"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-214727-fan-disk-s18895-step29

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 29 (add linear_pattern) took 164069 ms


---

## Retired 2026-09-14 — NOT a product bug

This folder was filed by the journey runner's own clock, not by the product.
It was a 164 s `linear_pattern` that answered 200 — see above: under the app's own 900 s budget, not a finding.

Both defects are fixed in `751db79`: the runner reads
`QueryUnbiasedInterruptTime`, which stops at suspend, and its step limit is now
`kernelguard.DEFAULT_BUDGET` — the app's own — instead of a private 120 s.
Kept as the evidence those tests were written from (`tests/test_journeys.py`,
"the clock"); nothing here needs fixing in the product.
