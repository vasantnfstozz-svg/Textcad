# hang: cam-cover-plaque, seed 18784, step 8

add shell took 405 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j4_shell",
 "op": "shell",
 "params": {
  "thickness": 2.7,
  "open_face": "bottom"
 },
 "inputs": [
  "cam_cover_plaque"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260913-192027-cam-cover-plaque-s18784-step8

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 8 (add shell) took 404941 ms


---

## Retired 2026-09-14 — NOT a product bug

This folder was filed by the journey runner's own clock, not by the product.
It was a 405 s `shell` that answered 200. The app's own kernel guard allows one guarded call 900 s before IT calls it a hang; the runner was using a private 120 s, so this was correct behaviour filed as a bug.

Both defects are fixed in `751db79`: the runner reads
`QueryUnbiasedInterruptTime`, which stops at suspend, and its step limit is now
`kernelguard.DEFAULT_BUDGET` — the app's own — instead of a private 120 s.
Kept as the evidence those tests were written from (`tests/test_journeys.py`,
"the clock"); nothing here needs fixing in the product.
