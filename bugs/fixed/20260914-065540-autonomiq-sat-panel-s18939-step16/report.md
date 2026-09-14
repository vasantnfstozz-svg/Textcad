# hang: autonomiq-sat-panel, seed 18939, step 16

undo  took 29781 s (the limit is 120 s) and answered 200

## The step that broke it

`POST /api/undo`

```json
null
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260914-065540-autonomiq-sat-panel-s18939-step16

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 16 (undo ) took 29781465 ms


---

## Retired 2026-09-14 — NOT a product bug

This folder was filed by the journey runner's own clock, not by the product.
It was an `/api/undo` "lasting" 8 h 16 m. It lasted seconds: THE LAPTOP SLEPT. The steps either side took 23 ms and 3598 ms, the working set never moved off 512 MB, and bugs/journeys.log shows the previous journey ending 22:37:56 and this one filed 06:55:40 — the gap IS the sleep. Windows' monotonic clock is QueryPerformanceCounter and it keeps ticking through a suspend (this box: 33.08 h of uptime against 29.48 h awake).

Both defects are fixed in `751db79`: the runner reads
`QueryUnbiasedInterruptTime`, which stops at suspend, and its step limit is now
`kernelguard.DEFAULT_BUDGET` — the app's own — instead of a private 120 s.
Kept as the evidence those tests were written from (`tests/test_journeys.py`,
"the clock"); nothing here needs fixing in the product.
