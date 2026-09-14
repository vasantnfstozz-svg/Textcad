"""Probe: a clock that does NOT count the time the machine was asleep.

Why. tests/journeys.py timed one `undo` at 29 781 465 ms (8 h 16 m) on the
2026-09-13 overnight run (bugs/fixed/20260914-065540-autonomiq-sat-panel-s18939-step16)
with a FLAT 512 MB working set and neighbouring steps at 23-3598 ms. Nothing
ran for eight hours: the laptop slept in the middle of the request and both
`time.perf_counter()` (the child's step clock) and `time.monotonic()` (the
parent's stall watchdog) counted the suspend.

What this measures: whether kernel32's QueryUnbiasedInterruptTime is reachable
from this Python, what resolution it has, and that it tracks perf_counter while
the box is awake (the two may only DIFFER across a suspend, which is the point).
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

k32 = ctypes.WinDLL("kernel32")
k32.QueryUnbiasedInterruptTime.argtypes = [ctypes.POINTER(wt.ULARGE_INTEGER)]
k32.QueryUnbiasedInterruptTime.restype = wt.BOOL


def unbiased() -> float:
    v = wt.ULARGE_INTEGER()
    if not k32.QueryUnbiasedInterruptTime(ctypes.byref(v)):
        raise OSError("QueryUnbiasedInterruptTime failed")
    return v.value / 1e7                      # 100-ns units -> seconds


print("python", sys.version.split()[0], "platform", sys.platform)
a = unbiased()
print("reads:", a, "s since boot, awake  (=%.2f hours)" % (a / 3600))

# resolution: how small a gap can it see?
ticks = []
last = unbiased()
while len(ticks) < 5:
    now = unbiased()
    if now != last:
        ticks.append(now - last)
        last = now
print("resolution: %.4f s between changes (%s)" % (sum(ticks) / len(ticks), [round(t, 5) for t in ticks]))

# does it advance like the other two while the box is awake?
for secs in (0.25, 1.0, 2.0):
    u0, p0, m0 = unbiased(), time.perf_counter(), time.monotonic()
    time.sleep(secs)
    print("slept %.2f s -> unbiased %.3f  perf_counter %.3f  monotonic %.3f"
          % (secs, unbiased() - u0, time.perf_counter() - p0, time.monotonic() - m0))

# and: is monotonic() really GetTickCount64 (biased) on this build?
print("time.get_clock_info('monotonic'):", time.get_clock_info("monotonic"))
print("time.get_clock_info('perf_counter'):", time.get_clock_info("perf_counter"))
print("uptime biased (GetTickCount64): %.2f hours" % (k32.GetTickCount64() / 3.6e6)
      if hasattr(k32, "GetTickCount64") else "no GetTickCount64")
