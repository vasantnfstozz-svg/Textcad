"""The ramped-plate residual: can the climb walk a RIDGE instead of stalling?

`_climb_to_the_deepest` steps away from the ONE nearest point on the staying
faces, which is the gradient of the distance field wherever that field is
smooth. It stops being smooth exactly on the medial axis, where the inscribed
sphere touches on two sides at once: stepping away from the first wall walks
into the second, the distance does not rise, the step halves and the seed dies
there. The ramped plate is that shape — the guard answers 12.2987 where a grid
oracle says 12.6900, and round one proved it is not a seeding fault (climbing
ALL 160 of its stations answers 12.2987 too).

The candidate fix costs no new machinery. When a step fails, the failed
candidate was still MEASURED, so its own nearest point is already in hand. If
that point sits on another wall, the two away-directions `u1` and `u2` are both
known, and `u1 + u2` rises against BOTH of them to first order (`(u1+u2).u1 =
1 + u1.u2 > 0` unless the walls are exactly opposite, which is a slab and has
no ridge to walk). So: try the bisector once before halving the step.

    python probes/shell_depth_ridge_climb_probe.py
    python probes/shell_depth_ridge_climb_probe.py --corpus

Nothing here is shipped until the answers are put to the KERNEL: a climb that
reads deeper ALLOWS more, and this guard's job is to refuse the bodies that
segfault OCCT.
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

SPENT = [0]


def ridge_climb(solid, measure, seen: list, best: tuple, tol: float) -> tuple:
    """`sketch._climb_to_the_deepest` with ONE change: the bisector try."""
    import sketch as sk
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(solid.wrapped)

    def outside(q) -> bool:
        cls.Perform(gp_Pnt(q.X, q.Y, q.Z), 1e-7)
        return cls.State() == TopAbs_State.TopAbs_OUT

    left = [sk._DEPTH_CLIMB_CALLS]

    def spend(q):
        if left[0] <= 0:
            return None, None
        left[0] -= 1
        SPENT[0] += 1
        return measure(q)

    seeds = sk._seeds_for_the_climb(seen, best[0], tol) or [best]
    for d0, q0 in seeds:
        if left[0] <= 0:
            break
        q, d = q0, d0
        step, near = max(d0, tol), None
        for _ in range(sk._DEPTH_CLIMB_STEPS):
            if left[0] <= 0:
                break
            if near is None:
                got = spend(q)
                if got[0] is None:
                    break
                d, near = got
            away = q - near
            reach = away.length
            if reach <= 1e-9:
                break
            cand = q + away * (step / reach)
            got = (None, None) if outside(cand) else spend(cand)
            if got[0] is not None and got[0] > d:
                q, d, near = cand, got[0], got[1]
                continue
            # ---- the change: the sphere touches on two sides, so walk the ridge
            took = False
            if got[0] is not None and got[1] is not None:
                u1 = away * (1.0 / reach)
                away2 = cand - got[1]
                if away2.length > 1e-9:
                    u2 = away2 * (1.0 / away2.length)
                    if u1.dot(u2) < 0.99:            # a different wall, not the same one
                        ridge = u1 + u2
                        if ridge.length > 1e-6:
                            alt = q + ridge * (step / ridge.length)
                            alt_got = (None, None) if outside(alt) else spend(alt)
                            if alt_got[0] is not None and alt_got[0] > d:
                                q, d, near = alt, alt_got[0], alt_got[1]
                                took = True
            if took:
                continue
            step *= 0.5
            if step <= tol * 0.25:
                break
        if d > best[0]:
            best = (d, q)
    return best


def answer(solid, patched: bool) -> tuple:
    import sketch as sk
    SPENT[0] = 0
    real = sk._climb_to_the_deepest
    counted = [0]

    def counting(s, measure, seen, best, tol):
        def m(q):
            counted[0] += 1
            return measure(q)
        return (ridge_climb if patched else real)(s, m, seen, best, tol)

    sk._climb_to_the_deepest = counting
    try:
        t0 = time.perf_counter()
        got = sk.deepest_material(solid, 1e9)
        return got[0], counted[0], time.perf_counter() - t0
    finally:
        sk._climb_to_the_deepest = real


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="store_true")
    a = ap.parse_args()
    from shell_depth_oracle_probe import oracle_depth
    from shell_depth_plateau_seeds_probe import BODIES
    cases = dict(BODIES)
    if a.corpus:
        import gauntlet
        for name, make in gauntlet.BODIES.items():
            cases[name] = make
    print(f"{'body':22s} {'today':>9s} {'ridge':>9s} {'oracle':>9s}  "
          f"{'calls now':>9s} {'calls new':>9s}   verdict")
    for name, make in cases.items():
        solid = make()
        now, c_now, _t1 = answer(solid, False)
        new, c_new, _t2 = answer(solid, True)
        truth, _at = oracle_depth(solid, coarse=20, refine=4)
        verdict = ("closed" if new >= truth - 1e-3 and now < truth - 1e-3 else
                   "same" if abs(new - now) < 1e-4 else
                   "PAST THE ORACLE" if new > truth + 1e-3 else "better")
        print(f"{name:22s} {now:9.4f} {new:9.4f} {truth:9.4f}  "
              f"{c_now:9d} {c_new:9d}   {verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
