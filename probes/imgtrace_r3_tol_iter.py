"""REVIEW-QUEUE section 9 round THREE — two of round two's smaller changes,
measured rather than read.

  3. `_first_crossing`'s new one-billionth tolerance.  A touch was ALREADY a
     hit before round two (the test was t,u in [0,1] closed), so the change
     only widens the band by 1e-9 of a segment's own length.  Does that band
     ever catch an outline round one called clean — a figure-eight, a pinched
     annulus, two shapes sharing a vertex, a Chaikin corner grazing an edge?

  4. `_traceable`'s monotone fixed point.  Does it converge, in how many
     rounds worst case, and does the `min_area` it returns match the mask it
     returns when the 8-round cap bites?

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_tol_iter.py
"""
from __future__ import annotations

import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import _imgtrace_r1 as R1                                   # noqa: E402
from imgtrace_r3_fuzz import corpus, png                    # noqa: E402


# --------------------------------------------------------------------------
# 3. the tolerance
# --------------------------------------------------------------------------
def fig8():
    return [(0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0)]


def touch_at_vertex():
    """two squares meeting at one corner, as ONE outline"""
    return [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0),
            (5.0, 5.0), (10.0, 5.0), (10.0, 10.0), (5.0, 10.0)]


def pinched_annulus(gap=0.0):
    """a ring whose two sides meet (or nearly meet) at one point"""
    pts = []
    for k in range(40):
        a = 2 * math.pi * k / 40
        pts.append((10 * math.cos(a), 10 * math.sin(a)))
    for k in range(40):
        a = -2 * math.pi * k / 40
        r = 10.0 - gap if k == 0 else 4.0
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def grazing_chaikin():
    """a spike whose Chaikin-cut corner lands exactly on another edge"""
    pts = np.array([(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (5.0, 6.0),
                    (5.0, 0.0), (4.0, 6.0), (0.0, 6.0)])
    return [tuple(float(v) for v in p) for p in imgtrace._chaikin(pts, 0.5)]


def tolerance_cases():
    print("3. THE ONE-BILLIONTH TOLERANCE\n")
    cases = [("figure eight", fig8()),
             ("two squares sharing one vertex", touch_at_vertex()),
             ("pinched annulus (exact touch)", pinched_annulus(0.0)),
             ("pinched annulus (1e-4 mm gap)", pinched_annulus(1e-4)),
             ("pinched annulus (1e-9 mm gap)", pinched_annulus(1e-9)),
             ("Chaikin corner grazing an edge", grazing_chaikin())]
    for name, pts in cases:
        p = imgtrace._round_pts(pts)
        a = R1._first_crossing(p)
        b = imgtrace._first_crossing(p)
        same = (a is None) == (b is None)
        n_r1 = len(R1._uncross(p)) if isinstance(R1._uncross(p), list) else 1
        n_r2 = len(imgtrace._uncross(p))
        print(f"  {name:34s} r1 {'cross' if a else 'clean':5s}  "
              f"r2 {'cross' if b else 'clean':5s}  "
              f"{'' if same else '<-- DIFFERENT'}   "
              f"loops: r1 {n_r1}, r2 {n_r2}")
    print("\n  over the round-three fuzz corpus, outline by outline:")
    diff = tot = 0
    for name, m in corpus(80):
        try:
            ents, _ = imgtrace.image_to_entities(png(m), height_mm=40)
        except Exception:                                   # noqa: BLE001
            continue
        for e in ents:
            p = [(e["x"] + x, e["y"] + y) for x, y in e["points"]]
            tot += 1
            if (R1._first_crossing(p) is None) != \
                    (imgtrace._first_crossing(p) is None):
                diff += 1
                print(f"    {name}: r1 and r2 disagree on this outline")
    print(f"    {tot} finished outlines, {diff} where the tolerance "
          f"changes the verdict")


# --------------------------------------------------------------------------
# 4. the fixed point
# --------------------------------------------------------------------------
def count_rounds(mask, h_mm):
    """re-run _traceable's loop, counting the rounds it needs"""
    n_comp, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    comp_areas = stats[1:, 4]
    keep = [i + 1 for i, a in enumerate(comp_areas) if a >= 9]
    rounds = 0
    for _ in range(64):
        rounds += 1
        ys, _xs = np.where(np.isin(labels, keep))
        h_all = int(ys.max()) - int(ys.min()) + 1
        min_area = max(9.0, (0.25 * h_all / float(h_mm)) ** 2)
        smaller = [i for i in keep if comp_areas[i - 1] >= min_area]
        if not smaller:
            return rounds, None, "refused"
        if smaller == keep:
            return rounds, min_area, "converged"
        keep = smaller
    return rounds, min_area, "did NOT converge in 64"


def graded_ladder(n):
    """n pieces of graded size stacked down the picture, so each round of
    the fixed point can only drop the outermost one"""
    m = np.zeros((2000, 600), np.uint8)
    for i in range(n):
        s = 3 + i * 2
        y = 1980 - i * 100
        m[y - s:y, 20:20 + s] = 1
    m[0:260, 300:560] = 1                       # the real artwork, big
    return m


def fixed_point():
    print("\n\n4. _traceable's FIXED POINT\n")
    worst = (0, "")
    for name, m in corpus(80):
        mask = imgtrace._mask_from_image(
            cv2.imdecode(np.frombuffer(png(m), np.uint8),
                         cv2.IMREAD_UNCHANGED))
        for h in (12.0, 40.0, 90.0):
            try:
                r, _ma, how = count_rounds(mask, h)
            except Exception:                               # noqa: BLE001
                continue
            if r > worst[0]:
                worst = (r, f"{name} at {h:g} mm ({how})")
    print(f"  fuzz corpus: worst round count {worst[0]} ({worst[1]})")

    for n in (4, 8, 16, 30):
        m = graded_ladder(n)
        r, ma, how = count_rounds(m, 10.0)
        capped, ma_mod = None, None
        try:
            solid, ma_mod = imgtrace._traceable(m, 10.0)
            capped = int(cv2.connectedComponents(solid, 8)[0] - 1)
        except ValueError as exc:
            how = f"module refused: {str(exc)[:40]}"
        print(f"  graded ladder of {n:2d} specks: {r:2d} rounds, {how}; "
              f"module keeps {capped} pieces, min_area {ma_mod} "
              f"(true fixed point {ma})")

    print("\n  cost on a big picture:")
    for side in (1000, 2000, 4000):
        m = np.zeros((side, side), np.uint8)
        cv2.circle(m, (side // 2, side // 2), side // 3, 1, -1)
        for i in range(40):
            m[10 + i * 5:12 + i * 5, 10:12] = 1
        t0 = time.perf_counter()
        imgtrace._traceable(m, 40.0)
        print(f"    {side}x{side} px: {1000 * (time.perf_counter() - t0):.0f} ms")


if __name__ == "__main__":
    tolerance_cases()
    fixed_point()
