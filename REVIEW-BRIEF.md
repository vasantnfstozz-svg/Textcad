# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `b17d626..751db79` - one commit, the journey
> runner's clock and its step limit.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range named here; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes.

---

## The range

    b17d626..751db79        (base b17d626, the paperwork for the kernel-worker review)

One commit:

- `751db79` - the journey runner stops timing the hours the laptop slept, and
  asks the kernel's own budget what a hang is; 4 new tests.

Touched: `tests/journeys.py` (+92/-10), `tests/test_journeys.py` (+122/-1),
`probes/awake_clock.py` (new), one `LAUNCH-PLAN.md` section 10 row.
No product code, no frontend, no `static/`, so ui stays v200.
Fast tier 1749 -> 1753, ruff zero.

## What it changes

**1. A clock that does not count machine sleep.** `journeys.awake_s()` reads
Windows' `QueryUnbiasedInterruptTime` (100-ns units) instead of
`time.monotonic()`, falling back to `time.monotonic` off Windows and whenever
the call cannot be made. `awake_elapsed(perf0, awake0)` returns
`(how long it really ran, how much of it was sleep)`: it keeps
`perf_counter`'s 100 ns resolution for ordinary steps and only subtracts a gap
bigger than `SLEPT_FLOOR_S` (1.0 s). Three call sites move onto it - the
child's per-request timer in `Journey.call`, the parent's stall watchdog in
`wait_or_kill_a_stalled_child`, and the per-journey total in `spawn`.

**2. The step limit is `kernelguard.DEFAULT_BUDGET`**, not the runner's own
120 s, and `STALL_KILL_S` is `DEFAULT_BUDGET + READY_SECONDS` (1080 s), which
is deliberately ABOVE it.

## Where the risk is

- **The subtraction could hide a real hang.** `awake_elapsed` takes time OFF a
  measurement. If the awake clock could ever lag the perf clock for a reason
  that is not a suspend - a VM's timer, a frequency change, the 9 ms
  resolution against a 100 ns one - the runner would shorten a genuine
  runaway. The floor is 1.0 s and the two agreed within 6 ms over 2 s on this
  box; that is one box.
- **A 7.5x looser step limit.** Anything that used to be caught between 120 s
  and 900 s is now only a note in `notes`. That is the intent, but it is the
  change most likely to be wrong: is the budget really the right line for a
  request that makes SEVERAL guarded calls (a rebuild re-running three
  fillets), or for one that makes none at all (a tab switch)?
- **The stall ceiling now outlives the budget by 180 s.** If the guard fails to
  stop a call, an overnight run loses 18 minutes to it instead of 10.
- **`import kernelguard` at `tests/journeys.py` module level.** It is only read
  for two constants, and it has no import-time side effects today (checked);
  it is still the test runner importing product code at import time.
- **A function attribute as a cache** (`awake_s._fn`).

## Cleared by measurement, not by argument

- `time.monotonic()` on this Python IS the uptime clock: 119554.9 s against
  `GetTickCount64`'s 119554.8 s. So it counts suspend, and the 8 h 16 m undo
  reading was the laptop sleeping, not work.
- `QueryUnbiasedInterruptTime` resolution is about 9 ms, and it tracks
  `perf_counter` to within 6 ms over a 2 s sleep (`probes/awake_clock.py`).
- All four new tests are RED against `b17d626` and green after. The clock test
  is red with a message naming the gap ("the runner is 12954 s out: it is back
  on a clock that counts the 216 min this box slept") when `awake_s` is
  swapped back to `time.monotonic`, so it cannot rot quietly.
- One real journey (`bit-tray`, seed 4242, 11 steps, `--library`) ran clean
  with step times from 7 ms to 2555 ms: the awake clock did not coarsen the
  readings.

## Do not re-report

- **The four `bugs/fixed/` folders from the night of 2026-09-13 that this
  commit reclassifies** (the 405 s shell, the 164 s pattern, the 135 s
  chamfer, the 8 h 16 m undo). They were the runner's own clock and limit, not
  the product; each carries a "Retired 2026-09-14 - NOT a product bug" note
  saying which of the two defects filed it. `bugs/` itself is down to the two
  real ones: `20260913-193839-my-part-5` (a shell segfault) and
  `20260913-212515-autonomiq-panel` (killed at 600 s; it would now be allowed
  the guard's own 900 s and answer in words).
- **`kernelguard`'s own budget counting machine sleep.** Found, measured, and
  deliberately NOT fixed here: it is product code and its `queue.get(timeout=)`
  expires on the OS's biased timer too, so it needs its own pass. It is a
  `LAUNCH-PLAN.md` section 10 P2 row.
- **`--hours` still being wall-clock.** An overnight deadline is when the user
  wants the run to stop, not how much work it got through; left on purpose.
- The reviewer may of course say any of these three calls was wrong.
