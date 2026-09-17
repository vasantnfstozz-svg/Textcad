"""WHERE the two touching hole loops come from — one contour split by
`_uncross`, or two different contours that meet after the simplify?

The fix depends on the answer. Reuses the two known bad traces of
probes/imgtrace_r3_pinch.py (round three's corpus, f73 at 90 mm and f122 at
12 mm) and reports, per source contour, how many loops `_uncross` returned
and how close the loops of ONE contour come to each other.

Run:  C:\\Python314\\python.exe probes/imgtrace_pinch_origin_probe.py
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
from imgtrace_r3_fuzz import corpus, png                    # noqa: E402

WANT = {"f73": 90.0, "f122": 12.0}


def closest_pts(a, b):
    pa, pb = np.asarray(a, float), np.asarray(b, float)
    return float(np.hypot(pa[:, None, 0] - pb[None, :, 0],
                          pa[:, None, 1] - pb[None, :, 1]).min())


def dissect(data, height_mm):
    """image_to_entities' geometry stage, opened up per contour."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    solid, min_area = imgtrace._traceable(imgtrace._mask_from_image(img),
                                          height_mm)
    cnts, hier = cv2.findContours(solid, cv2.RETR_CCOMP,
                                  cv2.CHAIN_APPROX_SIMPLE)
    x, y, w, h = cv2.boundingRect(np.vstack(list(cnts)))
    mm_px = float(height_mm) / h
    cx_px, cy_px = x + w / 2.0, y + h / 2.0
    eps = max(1.0, min(3.0, 0.15 / mm_px))
    cut_px = max(0.8, min(2.0, 0.4 / mm_px))
    hier = hier[0]
    print(f"  eps {eps:.3f} px = {eps * mm_px:.4f} mm, "
          f"chaikin cut {cut_px:.3f} px, min_area {min_area:.1f} px")
    out = []
    for i in range(len(cnts)):
        if cv2.contourArea(cnts[i]) < min_area:
            continue
        ap = cv2.approxPolyDP(cnts[i], eps, True).reshape(-1, 2).astype(float)
        if len(ap) < 3:
            continue
        ap = imgtrace._chaikin(ap, cut_px=cut_px)
        pts = [((px - cx_px) * mm_px, (cy_px - py) * mm_px) for px, py in ap]
        loops = [p for p in imgtrace._uncross(imgtrace._round_pts(pts))
                 if len(p) >= 3]
        kind = "outer" if hier[i][3] < 0 else "HOLE "
        note = ""
        if len(loops) > 1:
            gaps = [closest_pts(loops[a], loops[b])
                    for a in range(len(loops))
                    for b in range(a + 1, len(loops))]
            note = (f"  <-- SPLIT, its own loops come within "
                    f"{min(gaps):.6f} mm of each other")
        print(f"  contour {i:2d} {kind} area {cv2.contourArea(cnts[i]):9.1f} "
              f"px -> {len(loops)} loop(s){note}")
        out.append((i, kind, loops))
    return out


def main():
    for name, m in corpus(150):
        if name not in WANT:
            continue
        h_mm = WANT[name]
        print(f"\n=== {name} at {h_mm:g} mm ===")
        parts = dissect(png(m), h_mm)
        flat = [(i, k, lp) for i, k, lps in parts for lp in lps]
        worst = None
        for a in range(len(flat)):
            for b in range(a + 1, len(flat)):
                d = closest_pts(flat[a][2], flat[b][2])
                if worst is None or d < worst[0]:
                    worst = (d, flat[a][0], flat[b][0])
        print(f"  closest pair overall: {worst[0]:.6f} mm, between contour "
              f"{worst[1]} and contour {worst[2]}"
              + ("  (SAME contour)" if worst[1] == worst[2] else ""))


if __name__ == "__main__":
    main()
