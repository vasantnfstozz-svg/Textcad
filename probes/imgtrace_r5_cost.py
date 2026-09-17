"""REVIEW-QUEUE section 9 ROUND FIVE — what the MIRROR pass costs.

`_split_at_feet` is the half of the question `_pull_apart` never asked: a
vertex of the bigger loop on the middle of a smaller loop's edge. It inserts
a vertex ON that edge (no shape change) and lets the existing push open the
hair. This probe measures what that costs the user's art, A/B in one process:
the module as it ships, against the same module with the mirror pass turned
off.

Per picture it reports traces that come out byte-identical, the worst point
move, the worst area change, and the health of both solids.

Run:  C:/Python314/python.exe probes/imgtrace_r5_cost.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402


def both_ways(data, height_mm):
    with_pass = imgtrace.image_to_entities(data, height_mm=height_mm)[0]
    real = imgtrace._split_at_feet
    imgtrace._split_at_feet = lambda pts, ring, gap: pts
    try:
        without = imgtrace.image_to_entities(data, height_mm=height_mm)[0]
    finally:
        imgtrace._split_at_feet = real
    return with_pass, without


def area_of(ents):
    tot = 0.0
    for e in ents:
        pts = [(e["x"] + x, e["y"] + y) for x, y in e["points"]]
        a = abs(imgtrace._area2(pts)) / 2.0
        tot += a if e["mode"] == "add" else -a
    return tot


def worst_move(a, b):
    """the biggest distance from a point of `b` to the outline of `a` — the
    honest deformation when the point COUNTS differ"""
    worst = 0.0
    for ea, eb in zip(a, b):
        ra = np.array([[ea["x"] + x, ea["y"] + y] for x, y in ea["points"]])
        rb = np.array([[eb["x"] + x, eb["y"] + y] for x, y in eb["points"]])
        d, _f = imgtrace._nearest_on_ring(rb, ra)
        worst = max(worst, float(d.max()))
    return worst


def true_gap(ents):
    """the honest closest approach of any two loops, both directions"""
    rs = [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]], float)
          for e in ents]
    best = float("inf")
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            d1, _f = imgtrace._nearest_on_ring(rs[i], rs[j])
            d2, _f = imgtrace._nearest_on_ring(rs[j], rs[i])
            best = min(best, float(d1.min()), float(d2.min()))
    return best


def health_of(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"FAIL {type(exc).__name__}"
    bad = inspector.health(solid)
    return bad[0] if bad else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 40
    seed = int(args[1]) if len(args) > 1 else 5_2026
    rng = np.random.default_rng(seed)
    traces = same = diff = 0
    worst_pt = worst_area = 0.0
    bad_new = bad_old = 0
    tight_new = tight_old = touch_new = touch_old = 0
    closest_new = closest_old = float("inf")
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h in HEIGHTS:
                try:
                    new, old = both_ways(data, h)
                except ValueError:
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: {type(exc).__name__}: "
                          f"{str(exc)[:60]}")
                    continue
                traces += 1
                if len(new) > 1:
                    gn, go = true_gap(new), true_gap(old)
                    tight_new += gn < 0.002
                    tight_old += go < 0.002
                    touch_new += gn < 1e-6
                    touch_old += go < 1e-6
                    closest_new = min(closest_new, gn)
                    closest_old = min(closest_old, go)
                if new == old:
                    same += 1
                    continue
                diff += 1
                an, ao = area_of(new), area_of(old)
                da = abs(an - ao) / max(abs(ao), 1e-9) * 100.0
                worst_area = max(worst_area, da)
                if len(new) == len(old):
                    worst_pt = max(worst_pt, worst_move(old, new))
                hn, ho = health_of(new), health_of(old)
                bad_new += bool(hn)
                bad_old += bool(ho)
                print(f"  {gname}{k} h={h:g}: {len(old)}->{len(new)} loops, "
                      f"points {sum(len(e['points']) for e in old)}->"
                      f"{sum(len(e['points']) for e in new)}, area "
                      f"{ao:.3f}->{an:.3f} mm2 ({da:+.3f}%), health "
                      f"{ho or 'ok'} -> {hn or 'ok'}")
    print(f"\n{traces} traces")
    print(f"  byte-identical with the mirror pass on: {same} "
          f"({100 * same / max(traces, 1):.1f}%)")
    print(f"  changed                               : {diff}")
    print(f"  worst point move                      : {worst_pt:.6f} mm")
    print(f"  worst area change                     : {worst_area:.4f} %")
    print(f"  unhealthy solids  without / with      : {bad_old} / {bad_new}")
    print(f"  traces with a TRUE pair under 0.002 mm: {tight_old} -> "
          f"{tight_new}")
    print(f"  traces with a TRUE pair under 1e-6 mm : {touch_old} -> "
          f"{touch_new}")
    print(f"  closest true pair anywhere            : {closest_old:.9f} -> "
          f"{closest_new:.9f} mm")


if __name__ == "__main__":
    main()
