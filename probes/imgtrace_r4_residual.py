"""REVIEW-QUEUE section 9 ROUND FOUR — what the pictures the SHIPPED rule
still reads wrong actually trace to, in mm2, under all four rules.

A corpus table says "bright" or "dark"; it does not say whether the user
would notice. This traces each residual picture and prints the composed
sketch area against the area of the ink the picture really carries, so the
cost of each remaining failure is a number.

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_residual.py
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
import _imgtrace_r2 as R2                                   # noqa: E402
import imgtrace_r4_corpus as C4                             # noqa: E402

MODS = [("old", OLD), ("r1", R1), ("r2", R2), ("ship", imgtrace)]

# the pictures the shipped rule reads WRONG in round four's own corpus, plus
# the two that every rule reads wrong (so the residual is not blamed on this
# round's fix) and one baseline that must stay right
WANT = ["a3_inverse_keyline_1px_big", "a4_inverse_keyline_1px_small",
        "a5_inverse_video_white_margin", "a6_inverse_art_touches_all_edges",
        "b2_plate_holes_no_pad", "c7_dark_shell_ink_majority_three_sides",
        "d5_sheet4000_shell_20px_is_under_5pct", "b1_plate_holes_pad_2px",
        "b3_scan_edge_and_paper_pad"]


def true_ink(img, truth, h_mm):
    """area in mm2 of the side the picture was DRAWN with, at the scale the
    module would use for that side"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    art = m if truth == "bright" else (1 - m)
    art = art.astype(np.uint8)
    ys, _xs = np.where(art)
    mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
    return float(art.sum()) * mm_px * mm_px


def main():
    h_mm = 40.0
    cases = {n: (im, t, d) for n, im, t, d in C4.r4_cases()}
    for name in WANT:
        im, truth, desc = cases[name]
        ok, buf = cv2.imencode(".png", im)
        assert ok
        data = buf.tobytes()
        ink = true_ink(im, truth, h_mm)
        print(f"\n=== {name}  ({desc})")
        print(f"    truth {truth}; the ink it carries is {ink:.1f} mm2 "
              f"at {h_mm:g} mm tall")
        for tag, mod in MODS:
            try:
                ents, info = mod.image_to_entities(data, height_mm=h_mm)
            except Exception as exc:                        # noqa: BLE001
                print(f"    {tag:5s} REFUSED {type(exc).__name__}: "
                      f"{str(exc)[:50]}")
                continue
            try:
                s = sk.make_sketch("XY", 0, ents)
                bad = inspector.health(sk.extrude_sketch(s, 2.0))
                print(f"    {tag:5s} {info['contours']:2d}c/{info['holes']:2d}h"
                      f"  {s.area:9.1f} mm2  ({100 * s.area / ink:6.1f}% of "
                      f"the ink)  health {bad or 'ok'}")
            except Exception as exc:                        # noqa: BLE001
                print(f"    {tag:5s} SKETCH FAIL {type(exc).__name__}: "
                      f"{str(exc)[:50]}")


if __name__ == "__main__":
    main()
