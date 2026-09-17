"""What `_pull_apart` COSTS: how far it moves the user's traced art, and what
it does to art whose pieces touch BY DESIGN.

Two questions the shipped guard's docstring answers by argument, not by
measurement:

  * how far does a vertex actually move, over a real corpus, and how much
    area does that cost?  (the guard opens a 0.01 mm hair and refuses a push
    bigger than a quarter of the vertex's own shorter edge);
  * a figure-8, a bowtie, two letters that kiss: `_uncross` splits the pinched
    contour into two loops, and the guard then pushes them 0.01 mm apart. Does
    one connected piece of art become two disconnected solids?

Run:  C:/Python314/python.exe probes/imgtrace_pull_apart_cost.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402


def _png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def both_ways(data, height_mm):
    """(entities with the guard, entities without it)"""
    real = imgtrace._pull_apart
    with_guard = imgtrace.image_to_entities(data, height_mm=height_mm)[0]
    imgtrace._pull_apart = lambda loops, gap=0.01: loops
    try:
        without = imgtrace.image_to_entities(data, height_mm=height_mm)[0]
    finally:
        imgtrace._pull_apart = real
    return with_guard, without


def displacement(a, b):
    """the biggest point-to-point move between two traces of one picture, and
    the area they differ by (mm2 and %)"""
    if len(a) != len(b):
        return None
    worst = 0.0
    for ea, eb in zip(a, b):
        if len(ea["points"]) != len(eb["points"]):
            return None
        for pa, pb in zip(ea["points"], eb["points"]):
            worst = max(worst, float(np.hypot(ea["x"] + pa[0] - eb["x"] - pb[0],
                                              ea["y"] + pa[1] - eb["y"] - pb[1])))

    def area(ents):
        tot = 0.0
        for e in ents:
            pts = [(e["x"] + p[0], e["y"] + p[1]) for p in e["points"]]
            tot += (1 if e["mode"] == "add" else -1) * abs(
                imgtrace._area2(pts)) / 2.0
        return tot
    aa, ab = area(a), area(b)
    return worst, aa - ab, (100.0 * (aa - ab) / ab if ab else 0.0)


def figure_eight(bar=1, r=150, size=700):
    """two discs joined by a `bar`-pixel neck — art that touches BY DESIGN"""
    m = np.zeros((size, size), np.uint8)
    cv2.circle(m, (size // 2, 200), r, 1, -1)
    cv2.circle(m, (size // 2, 500), r, 1, -1)
    if bar:
        cv2.line(m, (size // 2, 200), (size // 2, 500), 1, bar)
    return m


def kissing_squares(size=700, half=140):
    """two squares meeting at ONE corner — the classic pinch"""
    m = np.zeros((size, size), np.uint8)
    c = size // 2
    m[c - half:c, c - half:c] = 1
    m[c:c + half, c:c + half] = 1
    return m


def main():
    print("=== how far the guard moves the art (round-four fuzz) ===")
    from imgtrace_r4_fuzz import corpus
    worst_move = (0.0, "")
    worst_area = (0.0, "")
    n = same = 0
    for name, img, _art, _cls, _drew in corpus(60):
        ok, buf = cv2.imencode(".png", img)
        assert ok
        for h_mm in (15.0, 45.0):
            try:
                a, b = both_ways(buf.tobytes(), h_mm)
            except ValueError:
                continue
            n += 1
            d = displacement(a, b)
            if d is None:
                print(f"  {name} at {h_mm:g}: the guard changed the POINT "
                      f"COUNT ({len(a)} vs {len(b)} entities)")
                continue
            move, darea, dpct = d
            if move <= 1e-12:
                same += 1
            if move > worst_move[0]:
                worst_move = (move, f"{name} at {h_mm:g} mm")
            if abs(dpct) > abs(worst_area[0]):
                worst_area = (dpct, f"{name} at {h_mm:g} mm ({darea:+.5f} mm2)")
    print(f"  {n} traces; {same} left byte-identical")
    print(f"  worst vertex move : {worst_move[0]:.6f} mm  ({worst_move[1]})")
    print(f"  worst area change : {worst_area[0]:+.4f} %  ({worst_area[1]})")

    print("\n=== art that touches BY DESIGN ===")
    for label, mask, h_mm in [("figure-8, 1 px neck", figure_eight(1), 40.0),
                              ("figure-8, 3 px neck", figure_eight(3), 40.0),
                              ("two squares kissing at a corner",
                               kissing_squares(), 40.0)]:
        data = _png(mask)
        for tag, ents in zip(("guard on ", "guard off"),
                             both_ways(data, h_mm)):
            s = sk.make_sketch("XY", 0, ents)
            solid = sk.extrude_sketch(s, 2.0)
            print(f"  {label:34s} {tag}: {len(ents)} loops, "
                  f"{len(solid.solids())} solid(s), {solid.volume:9.3f} mm3, "
                  f"health {inspector.health(solid) or 'ok'}")


if __name__ == "__main__":
    main()
