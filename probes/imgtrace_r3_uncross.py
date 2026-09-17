"""REVIEW-QUEUE section 9 round THREE — `_uncross` now KEEPS a same-turning
loop as a polygon of its own.  That is geometry the tracer never emitted
before, so it is put three questions, by measurement:

  1. can a KEPT loop OVERLAP the piece it was cut from?  Two `add` polygons
     that overlap in one sketch is a composition question this project has
     been bitten by before.  Split at the FIRST crossing only: if the same
     two arcs cross TWICE, the second crossing is never looked at again,
     because after the split those edges live in different polygons.
  2. can it INVENT a piece — a whisker that merely turns the same way?
  3. do the kept loops get the right mode and the right place in the order?

Overlap is measured by rasterising each loop at 20 px/mm and intersecting.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_uncross.py
"""
from __future__ import annotations

import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402

PPMM = 20.0


def raster(pts, origin, size):
    m = np.zeros(size, np.uint8)
    q = np.array([[(x - origin[0]) * PPMM, (y - origin[1]) * PPMM]
                  for x, y in pts], np.int32)
    cv2.fillPoly(m, [q], 1)
    return m


def overlaps(loops):
    """pairwise overlap area in mm2 between the loops of one contour"""
    allp = [p for lp in loops for p in lp]
    if not allp:
        return []
    x0 = min(p[0] for p in allp) - 1
    y0 = min(p[1] for p in allp) - 1
    w = int((max(p[0] for p in allp) - x0 + 2) * PPMM) + 2
    h = int((max(p[1] for p in allp) - y0 + 2) * PPMM) + 2
    ms = [raster(lp, (x0, y0), (h, w)) for lp in loops]
    out = []
    for i in range(len(ms)):
        for j in range(i + 1, len(ms)):
            inter = int((ms[i] & ms[j]).sum()) / (PPMM * PPMM)
            if inter > 1e-6:
                ai = int(ms[i].sum()) / (PPMM * PPMM)
                aj = int(ms[j].sum()) / (PPMM * PPMM)
                out.append((i, j, inter, ai, aj))
    return out


def report(name, pts):
    loops = imgtrace._uncross(imgtrace._round_pts(pts))
    areas = [abs(imgtrace._area2(lp)) / 2.0 for lp in loops]
    ov = overlaps(loops)
    print(f"{name:34s} {len(loops)} loop(s), areas "
          + ", ".join(f"{a:.2f}" for a in areas))
    for i, j, inter, ai, aj in ov:
        frac = 100.0 * inter / min(ai, aj)
        print(f"    OVERLAP loops {i} and {j}: {inter:.2f} mm2 "
              f"= {frac:.1f}% of the smaller ({ai:.2f} / {aj:.2f} mm2)")
    if not ov:
        print("    no overlap between the kept loops")
    return loops, ov


# --------------------------------------------------------------------------
# 1. constructed outlines
# --------------------------------------------------------------------------
def pentagram(r=10.0):
    """a five-point star drawn as a closed polyline: 5 self-crossings, and
    the SAME pair of arcs crosses more than once"""
    return [(r * math.cos(math.radians(90 + 144 * k)),
             r * math.sin(math.radians(90 + 144 * k))) for k in range(5)]


def double_cross():
    """a closed outline whose two arcs cross TWICE — a strip folded back
    through itself and out again, which is what a traced ribbon with two
    hairline touches looks like after Douglas-Peucker"""
    return [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (-2.0, 6.0),
            (-2.0, 4.0), (12.0, 4.0), (12.0, 2.0), (-2.0, 2.0),
            (-2.0, -1.0), (0.0, -1.0)]


def whisker(same_turn):
    """a square with a one-pixel-wide spike walked out and back; `same_turn`
    makes the fold-back turn the SAME way as the body"""
    body = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    if same_turn:
        spike = [(4.9, 10.0), (4.9, 16.0), (5.2, 16.0), (5.1, 10.0),
                 (5.0, 15.9), (4.8, 10.0)]
    else:
        spike = [(4.9, 10.0), (5.05, 16.0), (5.15, 16.0), (5.0, 10.0)]
    return body[:3] + spike + body[3:]


def main():
    print("1. CONSTRUCTED OUTLINES\n")
    report("pentagram (5 crossings)", pentagram())
    report("two arcs crossing TWICE", double_cross())
    report("whisker, fold-back turns back", whisker(False))
    report("whisker, fold-back turns SAME", whisker(True))

    print("\n2. THE SAME OUTLINES THROUGH THE WHOLE TRACER\n")
    # a ribbon that folds through itself twice, rendered as a picture
    m = np.zeros((300, 400), np.uint8)
    cv2.rectangle(m, (40, 40), (360, 120), 1, -1)
    cv2.rectangle(m, (40, 122), (360, 200), 1, -1)
    m[120:122, 190:192] = 1                   # a two-pixel join
    img = np.zeros(m.shape + (4,), np.uint8)
    img[:, :, 3] = m * 255
    ok, buf = cv2.imencode(".png", img)
    ents, info = imgtrace.image_to_entities(buf.tobytes(), height_mm=40)
    print(f"two bars joined by a 2 px bridge -> {info}")
    for k, e in enumerate(ents):
        a = abs(imgtrace._area2([tuple(p) for p in e["points"]])) / 2.0
        print(f"    ent {k}: mode {e['mode']:9s} area {a:8.2f} mm2 "
              f"at ({e['x']:.2f}, {e['y']:.2f})")


if __name__ == "__main__":
    main()
