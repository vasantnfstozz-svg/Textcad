"""The point the guard already found, still IN the body it just hollowed.

`assert_something_would_be_hollowed` measures, before the kernel, one point of
material at distance `d >= t` from every face that stays — it has the exact
number and the exact point, and it throws both away. But that point is a
THEOREM about the result: an inward shell keeps exactly the material within `t`
of the staying faces, so a point at distance `d > t` from all of them is inside
the CAVITY and cannot be in the walls. If it comes back inside the result, the
kernel did not hollow what it was asked to hollow — no corpus, no constant, no
calibration.

This probe measures whether that test fires on the two results round two found
the shipped `area*t`-AND-`coarea` gate accepting, and what margin (`d - t`) it
has to work with.

    python probes/memcap.py --gb 6 --timeout 900 -- \
        C:\\Python314\\python.exe probes/shell_deep_point_survives_probe.py

One case per run: two OpenCASCADE workloads at once is how this box dies.
"""
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

# (name, L, W, H, n, r, p, t, what the truth is)
CASES = [
    ("flat100 t=2.5", 60.0, 60.0, 10.0, 10, 1.0, 6.0, 2.5, 31886.6),
    ("flat100 t=3.0", 60.0, 60.0, 10.0, 10, 1.0, 6.0, 3.0, 32781.0),
    ("flat100 t=1.6", 60.0, 60.0, 10.0, 10, 1.0, 6.0, 1.6, 24357.5),   # SOUND
    ("merge64 t=1.7", 36.4, 36.4, 40.0, 8, 0.8, 4.0, 1.7, 45608.9),
]


def drilled(L, W, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def state(shape, q):
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(shape.wrapped)
    cls.Perform(gp_Pnt(*q), 1e-7)
    s = cls.State()
    return {TopAbs_State.TopAbs_IN: "IN", TopAbs_State.TopAbs_OUT: "OUT",
            TopAbs_State.TopAbs_ON: "ON"}.get(s, str(s))


def main() -> int:
    import build123d as b3d

    import sketch
    for name, L, W, H, n, r, p, t, truth in CASES:
        t0 = time.perf_counter()
        solid = drilled(L, W, H, n, r, p)
        v_in = float(solid.volume)
        found = sketch.deepest_material(solid, t, ())
        if found is None:
            print(f"{name}: deepest_material measured NOTHING")
            continue
        depth, at, tol = found
        try:
            off = b3d.offset(solid, amount=-t, kind=b3d.Kind.INTERSECTION)
            out = solid - off
        except Exception as e:                                # noqa: BLE001
            print(f"{name}: the kernel refused ({type(e).__name__})  {str(e)[:60]}")
            continue
        v_out = float(out.volume)
        print(f"{name}: body {v_in:,.3f} -> walls {v_out:,.3f} (truth {truth:,.1f}, "
              f"{(v_out - truth) / truth * 100:+.3f}%)\n"
              f"    deepest_material: depth {depth:.4f} at "
              f"({at[0]:.4f}, {at[1]:.4f}, {at[2]:.4f}), tol {tol:.2e}, "
              f"margin d-t = {depth - t:+.4f}\n"
              f"    that point is {state(solid, at)} the body and "
              f"{state(out, at)} the walls  -> "
              f"{'CAUGHT' if state(out, at) == 'IN' else 'not caught'}"
              f"   [{time.perf_counter() - t0:.0f}s]", flush=True)
        # what the theorem allows: a ball of radius d-t around the point is all
        # cavity, so the cavity can never be smaller than that
        ball = 4.0 / 3.0 * math.pi * max(0.0, depth - t) ** 3
        print(f"    cavity {v_in - v_out:,.3f} mm3; the ball bound alone needs "
              f"{ball:,.3f} mm3 (truth {v_in - truth:,.1f})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
