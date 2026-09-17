"""REVIEW-QUEUE section 9 round THREE — two blobs that meet at a POINT.

`_uncross` splits at the first crossing into `a` (the cut loop) and `b` (the
rest).  When EITHER comes back with fewer than three points it takes the
"whisker's fold-back" branch and keeps the bigger of the two — but `b` there
is the original outline with the crossing stitched shut, and for a corner
touch that stitch is a straight line across real artwork, not a whisker.

Two squares meeting at one corner, a bow tie, an X of two triangles: all
ordinary silhouettes.  Measured as traced area against the picture's own ink
and as the rastered symmetric difference, which an area comparison alone
cannot see.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_corner.py
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
import _imgtrace_old as OLD                                 # noqa: E402
import _imgtrace_r1 as R1                                   # noqa: E402

MODS = [("old", OLD), ("r1", R1), ("r2", imgtrace)]


def png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def two_squares(s=120, gap=0):
    m = np.zeros((2 * s + 40, 2 * s + 40), np.uint8)
    m[20:20 + s, 20:20 + s] = 1
    m[20 + s + gap:20 + 2 * s + gap, 20 + s + gap:20 + 2 * s + gap] = 1
    return m


def bowtie(s=140):
    m = np.zeros((2 * s, 2 * s), np.uint8)
    cv2.fillPoly(m, [np.array([[10, 10], [10, 2 * s - 10], [s, s]],
                              np.int32)], 1)
    cv2.fillPoly(m, [np.array([[2 * s - 10, 10], [2 * s - 10, 2 * s - 10],
                               [s, s]], np.int32)], 1)
    return m


def chain(s=110):
    """three discs in a row, each touching the next at one pixel"""
    m = np.zeros((3 * s, 7 * s, ), np.uint8)
    for k in range(3):
        cv2.circle(m, (s + 2 * k * s, int(1.5 * s)), s - 1, 1, -1)
    return m


def diff_mask(ents, shape, mm_px, cx, cy):
    """rasterise the traced entities back onto the picture's own grid"""
    out = np.zeros(shape, np.uint8)
    for e in ents:
        q = np.array([[(e["x"] + x) / mm_px + cx, cy - (e["y"] + y) / mm_px]
                      for x, y in e["points"]], np.int32)
        cv2.fillPoly(out, [q], 1 if e["mode"] == "add" else 0)
    return out


def report(name, m, h_mm=40.0):
    data = png(m)
    ys, xs = np.where(m)
    mm_px0 = h_mm / (int(ys.max()) - int(ys.min()) + 1)
    ink = float(m.sum()) * mm_px0 * mm_px0
    print(f"\n=== {name}: {int(m.sum())} ink px, {ink:.2f} mm2 at "
          f"{h_mm:g} mm tall ===")
    for tag, mod in MODS:
        try:
            ents, info = mod.image_to_entities(data, height_mm=h_mm)
        except Exception as exc:                            # noqa: BLE001
            print(f"  {tag:4s} REFUSED {type(exc).__name__}: {exc}")
            continue
        s = sk.make_sketch("XY", 0, ents)
        bad = inspector.health(sk.extrude_sketch(s, 2.0))
        # rasterise back: bbox centre of the traced art in picture pixels
        x0, y0 = int(xs.min()), int(ys.min())
        w = int(xs.max()) - x0 + 1
        h = int(ys.max()) - y0 + 1
        mmpx = h_mm / h
        got = diff_mask(ents, m.shape, mmpx, x0 + w / 2.0, y0 + h / 2.0)
        lost = int(((m > 0) & (got == 0)).sum())
        gained = int(((m == 0) & (got > 0)).sum())
        print(f"  {tag:4s} {info['contours']}c/{info['holes']}h "
              f"area {s.area:9.2f} mm2 ({100 * s.area / ink:5.1f}% of the ink)"
              f"  px lost {lost:6d}  px INVENTED {gained:6d}"
              f"  health {'ok' if not bad else bad}")


def main():
    report("two squares meeting at ONE corner", two_squares())
    report("two squares with a one-pixel gap", two_squares(gap=2))
    report("a bow tie (two triangles at a point)", bowtie())
    report("three discs in a chain", chain())


if __name__ == "__main__":
    main()
