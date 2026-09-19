"""Is the climb's budget of 200 enough on a body with MORE stations than any
body it was measured on — and which way does the answer move when it is not?

`_DEPTH_CLIMB_CALLS` rose from 120 to 200 on 2026-09-17 because 120 starved the
two seed rankings that commit added. The number came from the unstopped SPEND
over the plateau bodies, the gauntlet corpus, the committed crash fixtures and
drilled plates up to 330 faces: 3 to 172, never near the theoretical 369. This
probe pushes past that: a 19 x 19 drilled plate is 367 faces and about three
times as many stations as anything in that set.

Two numbers are the finding: what the climb SPENDS when nothing stops it, and
what the answer becomes at budgets below that. The second is the one that
matters — a starved climb must read LOWER (a safer refusal), never deeper,
because a deeper reading lets a body the wall does not fit reach a kernel that
segfaults on it.

    python probes/memcap.py --gb 6 --timeout 1800 -- \
        C:\\Python314\\python.exe probes/shell_depth_budget_headroom_probe.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def drilled(L, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, L, H)) - cut


def main() -> int:
    import sketch as sk
    t0 = time.perf_counter()
    solid = drilled(90.0, 24.0, 19, 0.5, 4.0)
    print(f"{len(solid.faces())} faces, {solid.volume:,.3f} mm3 "
          f"[{time.perf_counter() - t0:.0f}s build]", flush=True)

    stations, spent = [0], [0]
    real = sk._climb_to_the_deepest

    def counting(s, measure, seen, best, tol):
        stations[0] = len(seen)

        def m(q):
            spent[0] += 1
            return measure(q)
        return real(s, m, seen, best, tol)

    sk._climb_to_the_deepest = counting
    try:
        for budget in (10_000, 200, 120, 30, 0):
            spent[0] = 0
            sk._DEPTH_CLIMB_CALLS = budget
            t1 = time.perf_counter()
            got = sk.deepest_material(solid, 1e9)
            print(f"  budget {budget:>6} -> depth {got[0]:9.4f}   spent "
                  f"{spent[0]:>5}   stations measured {stations[0]:>5}   "
                  f"[{time.perf_counter() - t1:.0f}s]", flush=True)
    finally:
        sk._climb_to_the_deepest = real
        sk._DEPTH_CLIMB_CALLS = 200
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
