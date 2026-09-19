"""Round three, attack 3: is `_DEPTH_CLIMB_CALLS = 200` enough on a body
NOBODY has built yet?

Round two measured five bodies that want 166 to 516 calls unstopped and answer
identically at 200 and at 10,000, and measured that running out moves the
answer DOWN. Down is round one's P1 class — a guard refusing walls the kernel
builds — so "200 is binding but harmless" is a claim about the five bodies it
was measured on. The dimension that corpus held constant is the SHAPE of the
early seeds: on all five, the three DEEPEST seeds die quickly (a plateau seed
walks into the opposite wall, the bisector is the zero vector, the step halves
and it is over in about ten calls), so the budget still reaches the `room` and
`both` rankings where those bodies keep their answer.

Vary it: put the ridge-WALKING shape where the deepest seeds are, and the real
maximum where only a later ranking finds it. A seed that walks a ridge spends
two calls a step for all forty steps, so three of them cost 240 and nothing is
left.

    C:\\Python314\\python.exe probes/shell_r3_budget_starve_probe.py
    C:\\Python314\\python.exe probes/shell_r3_budget_starve_probe.py --body ramp_and_wedge

No offset, no boolean: this is BRepExtrema and the classifier only.
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import build123d as b3d  # noqa: E402

import sketch as sk  # noqa: E402


def ramped_plate():
    """the round-two body: inscribed radius 12.713, found only by the ridge"""
    return b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-60, 0), (60, 0), (60, 8), (10, 26), (-60, 8), close=True)), 50)


def ramp_and_wedge():
    """the ramped plate (deep, and a RIDGE that the climb now walks for its
    whole forty steps) with the wedge-in-a-slab fused beside it (the real
    maximum, and one the deepest ranking never seeds)."""
    ramp = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-60, 0), (60, 0), (60, 8), (10, 26), (-60, 8), close=True)), 50)
    w = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-40, 0), (40, 0), (40, 34), (-40, 2), close=True)), 40)
    return b3d.Part() + (ramp + b3d.Pos(150, 20, 0) * w)


def ramp_pair():
    """two ramped plates, the second half again as deep: three ridge-walking
    seeds on the small one, the answer on the big one"""
    small = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-60, 0), (60, 0), (60, 8), (10, 26), (-60, 8), close=True)), 120)
    big = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-45, 0), (45, 0), (45, 6), (8, 39), (-45, 6), close=True)), 30)
    return b3d.Part() + (small + b3d.Pos(0, 140, 0) * big)


def double_ramp():
    """one ramped plate twice the size: the ridge is twice as long to walk"""
    return b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-120, 0), (120, 0), (120, 16), (20, 52), (-120, 16),
                     close=True)), 100)


def wedge_and_ramp():
    """the wedge in a slab, with the ramped plate fused on: the slab's plateau
    and the ramp's ridge both come before the wedge's own seed"""
    w = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-40, 0), (40, 0), (40, 30), (-40, 2), close=True)), 40)
    slab = b3d.Pos(0, -30.0, 12.0) * b3d.Box(80, 80, 24)
    ramp = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-60, 0), (60, 0), (60, 8), (10, 26), (-60, 8), close=True)), 50)
    return b3d.Part() + (w + slab + b3d.Pos(0, 110, 0) * ramp)


def starve_wedge():
    """The shape the budget cannot survive, by construction:

      * a RAMP scaled so its stations read about 15.4 and its ridge walk
        reaches about 15.9 — the three DEEPEST seeds, and each one walks the
        ridge for its whole forty steps at two calls a step;
      * a WEDGE scaled 1.6x, whose true maximum is about 19.9 but whose best
        station measures about 3.9 — so it is seeded by the ROOM ranking,
        which is the FOURTH seed and only runs if the budget lasts;
      * a plain slab under the wedge, so the wedge is fused into something and
        the body is one solid.
    """
    ramp = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-75, 0), (75, 0), (75, 10), (12.5, 32.5), (-75, 10),
                     close=True)), 62.5)
    w = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-64, 0), (64, 0), (64, 48), (-64, 3.2), close=True)), 64)
    slab = b3d.Pos(0, -48.0, 19.2) * b3d.Box(128, 128, 38.4)
    return b3d.Part() + (ramp + b3d.Pos(0, 200, 0) * (w + slab))


def starve_wedge_far():
    """the same, with the ramp made deeper still so it owns every deep seed"""
    ramp = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-90, 0), (90, 0), (90, 12), (15, 39), (-90, 12),
                     close=True)), 75)
    w = b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-80, 0), (80, 0), (80, 60), (-80, 4), close=True)), 80)
    slab = b3d.Pos(0, -60.0, 24.0) * b3d.Box(160, 160, 48)
    return b3d.Part() + (ramp + b3d.Pos(0, 250, 0) * (w + slab))


BODIES = {"ramped_plate": ramped_plate, "ramp_and_wedge": ramp_and_wedge,
          "ramp_pair": ramp_pair, "double_ramp": double_ramp,
          "wedge_and_ramp": wedge_and_ramp, "starve_wedge": starve_wedge,
          "starve_wedge_far": starve_wedge_far}


def answer_at(solid, budget: int) -> tuple:
    """(depth, calls spent) with `_DEPTH_CLIMB_CALLS` set to `budget`."""
    keep = sk._DEPTH_CLIMB_CALLS
    counted = [0]
    real = sk._climb_to_the_deepest

    def counting(s, measure, seen, best, tol):
        def m(q):
            counted[0] += 1
            return measure(q)
        return real(s, m, seen, best, tol)

    sk._DEPTH_CLIMB_CALLS = budget
    sk._climb_to_the_deepest = counting
    try:
        t0 = time.perf_counter()
        got = sk.deepest_material(solid, 1e9)
        return got[0], counted[0], time.perf_counter() - t0
    finally:
        sk._DEPTH_CLIMB_CALLS = keep
        sk._climb_to_the_deepest = real


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", default=None)
    ap.add_argument("--oracle", action="store_true", default=True)
    a = ap.parse_args()
    from shell_depth_oracle_probe import oracle_depth
    names = [a.body] if a.body else list(BODIES)
    print(f"shipped budget = {sk._DEPTH_CLIMB_CALLS}\n")
    print(f"{'body':<18} {'faces':>5} {'@200':>9} {'@10000':>9} {'unstopped':>9} "
          f"{'wants':>6} {'oracle':>9}   verdict")
    for name in names:
        solid = BODIES[name]()
        at200, c200, _ = answer_at(solid, 200)
        big, cbig, _ = answer_at(solid, 10_000)
        free, cfree, _ = answer_at(solid, 10_000_000)
        truth, _at = oracle_depth(solid, coarse=20, refine=4)
        verdict = ("SHORT BY BUDGET" if big > at200 + 1e-4 else
                   "same" if abs(big - at200) <= 1e-4 else "?")
        print(f"{name:<18} {len(solid.faces()):>5} {at200:>9.4f} {big:>9.4f} "
              f"{free:>9.4f} {cfree:>6d} {truth:>9.4f}   {verdict}"
              + (f"   (oracle is {truth - at200:+.4f} over the shipped answer)"
                 if truth > at200 + 1e-3 else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
