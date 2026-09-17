"""Does the kernel worker's budget count the time the LAPTOP slept?

`kernelguard._Worker.answer` measures `DEFAULT_BUDGET` on `time.monotonic()`.
On Windows that clock is QueryPerformanceCounter and it keeps ticking through
a suspend, so shutting the lid mid-fillet spends the whole budget on sleep and
the user's sound feature comes back "was stopped after 15 minutes". The same
defect was fixed in the journey runner (tests/journeys.py, `awake_s`).

This probe answers three questions with numbers, none of them inferred:

  1. Is QueryUnbiasedInterruptTime readable here, and what does it say about
     this box (uptime vs awake)? That is the size of the bug.
  2. What is its resolution, next to `time.monotonic`? A budget clock that
     jumps 16 ms at a time is fine for a 900 s ceiling; one that jumps a
     second is not.
  3. Does `queue.Queue.get(timeout=X)` expire on the OS's BIASED timer? That
     is the trap the plan records: swapping the clock is not enough, because
     the wait itself still ends early after a suspend, so `queue.Empty` has to
     go back round the loop while the awake clock still has budget. It cannot
     be suspended here, so the wait is FAKED: a clock that stands still (the
     machine "asleep") against a real `queue.get` that really does return
     Empty, run against BOTH shapes of the loop.

    python probes/kernel_budget_awake_probe.py
"""
import queue
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kernelguard  # noqa: E402


def section(n: str) -> None:
    print(f"\n{n}\n" + "-" * len(n), flush=True)


def main() -> int:
    section("1. the two clocks on this box")
    awake = kernelguard._awake_s if hasattr(kernelguard, "_awake_s") else None
    if awake is None:
        print("kernelguard has no _awake_s yet -- reading the API directly")

        def awake():
            import ctypes
            import ctypes.wintypes as wt
            fn = ctypes.WinDLL("kernel32").QueryUnbiasedInterruptTime
            fn.argtypes = [ctypes.POINTER(wt.ULARGE_INTEGER)]
            fn.restype = wt.BOOL
            v = wt.ULARGE_INTEGER()
            return v.value / 1e7 if fn(ctypes.byref(v)) else time.monotonic()
    up, aw = time.monotonic(), awake()
    print(f"time.monotonic()          {up:12.3f} s  ({up / 3600:.2f} h)")
    print(f"awake (unbiased)          {aw:12.3f} s  ({aw / 3600:.2f} h)")
    print(f"the gap (slept)           {up - aw:12.3f} s  ({(up - aw) / 3600:.2f} h)")
    print("   -- every second of that gap is budget a suspended fillet would lose")

    section("2. resolution, over 2 s of real waiting")
    m0, a0 = time.monotonic(), awake()
    steps = []
    last = a0
    while time.monotonic() - m0 < 2.0:
        now = awake()
        if now != last:
            steps.append(now - last)
            last = now
    m1, a1 = time.monotonic(), awake()
    print(f"monotonic advanced {m1 - m0:.6f} s, awake advanced {a1 - a0:.6f} s "
          f"(disagree by {abs((m1 - m0) - (a1 - a0)) * 1000:.2f} ms)")
    if steps:
        print(f"awake ticks: {len(steps)} in 2 s, step {min(steps) * 1000:.3f}"
              f"-{max(steps) * 1000:.3f} ms")

    section("3. does a queue wait end on the BIASED timer? (the trap)")
    print("Faked, because this box cannot be suspended inside a probe: the awake")
    print("clock STANDS STILL (asleep) while the real queue.get really does end.")

    def frozen():
        return 100.0                      # the machine is asleep: no awake time passes

    def old_loop(q, budget):
        """what kernelguard.answer does today, with the clock swapped and the
        queue.Empty still fatal"""
        end = frozen() + budget
        while True:
            left = end - frozen()
            if left <= 0:
                return "TIMEOUT"
            try:
                return q.get(timeout=min(left, 0.05))
            except queue.Empty:
                return "TIMEOUT (queue.Empty ended it, awake budget untouched)"

    def new_loop(q, budget):
        """queue.Empty goes back round the loop; only the awake clock ends it"""
        end = frozen() + budget
        rounds = 0
        while True:
            left = end - frozen()
            if left <= 0:
                return f"TIMEOUT after {rounds} rounds"
            try:
                return q.get(timeout=min(left, 0.05))
            except queue.Empty:
                rounds += 1
                if rounds >= 3:           # the probe has to stop; the real one does not
                    return f"still waiting after {rounds} rounds -- budget intact"
                continue

    q: queue.Queue = queue.Queue()
    print(f"   today's shape : {old_loop(q, 900.0)}")
    print(f"   the fix       : {new_loop(q, 900.0)}")

    section("4. the answer a real worker gives, unchanged")
    print(f"DEFAULT_BUDGET = {kernelguard.DEFAULT_BUDGET} s, "
          f"_minutes -> {kernelguard._minutes(kernelguard.DEFAULT_BUDGET)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
