"""REVIEW-QUEUE section 9 ROUND TWO — the residuals the sweep still shows.

The sweep leaves the SAME one self-crossing, one unhealthy solid and one
61% shortfall in round one's code and round two's. This names them, so they
are either explained or filed rather than left as a number.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_residual.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                                   # noqa: E402
import inspector                                                  # noqa: E402
import sketch as sk                                               # noqa: E402

from imgtrace_r2_sweep import _crossings, _png, corpus            # noqa: E402


def main():
    for name, m in corpus():
        data = _png(m)
        ys, _ = np.where(m)
        for h_mm in (12.0, 40.0, 90.0):
            mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
            truth = float(m.sum()) * mm_px * mm_px
            try:
                ents, info = imgtrace.image_to_entities(data, height_mm=h_mm)
            except Exception:                                  # noqa: BLE001
                continue
            cross = sum(_crossings(e["points"]) for e in ents)
            try:
                s = sk.make_sketch("XY", 0, ents)
                bad = inspector.health(sk.extrude_sketch(s, 2.0))
                short = (truth - s.area) / truth
            except Exception as e:                             # noqa: BLE001
                print(f"{name} @ {h_mm:g}: sketch {type(e).__name__}: {e}")
                continue
            if cross or bad or short > 0.25:
                # how much of the ink survives the 0.25 mm speckle floor?
                solid, min_area = imgtrace._traceable(
                    imgtrace._mask_from_image(
                        cv2.imdecode(np.frombuffer(data, np.uint8),
                                     cv2.IMREAD_UNCHANGED)), h_mm)
                kept = float(solid.sum()) * mm_px * mm_px
                print(f"{name} @ {h_mm:g} mm: crossings {cross}, "
                      f"health {bad or 'ok'}, traced "
                      f"{100 * (1 - short):.1f}% of the ink; the floor "
                      f"({min_area:.0f} px) already leaves "
                      f"{100 * kept / truth:.1f}% "
                      f"({info['contours']}c/{info['holes']}h)")


if __name__ == "__main__":
    main()
