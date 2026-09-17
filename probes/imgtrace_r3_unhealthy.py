"""REVIEW-QUEUE section 9 round THREE — the two traces the round-three fuzz
built an UNHEALTHY solid from.  Round two's sweep reported zero; a different
corpus finds two in 450.  This prints exactly what is wrong with them.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_unhealthy.py
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
import _imgtrace_r1 as R1                                   # noqa: E402
import _imgtrace_old as OLD                                 # noqa: E402
from imgtrace_r3_fuzz import corpus, png, crossings         # noqa: E402

WANT = {"f73": 90.0, "f122": 12.0}


def dup_points(pts):
    n = len(pts)
    return sum(1 for i in range(n)
               if tuple(pts[i]) == tuple(pts[(i + 1) % n]))


def main():
    for name, m in corpus(150):
        if name not in WANT:
            continue
        h_mm = WANT[name]
        data = png(m)
        print(f"\n=== {name} at {h_mm:g} mm "
              f"({m.shape[1]}x{m.shape[0]} px, {int(m.sum())} ink px) ===")
        for tag, mod in (("old", OLD), ("r1", R1), ("r2", imgtrace)):
            try:
                ents, info = mod.image_to_entities(data, height_mm=h_mm)
            except Exception as exc:                        # noqa: BLE001
                print(f"  {tag:4s} REFUSED {type(exc).__name__}: {exc}")
                continue
            cr = sum(crossings(e["points"]) for e in ents)
            dups = sum(dup_points(e["points"]) for e in ents)
            tiny = [len(e["points"]) for e in ents]
            try:
                s = sk.make_sketch("XY", 0, ents)
                solid = sk.extrude_sketch(s, 2.0)
                bad = inspector.health(solid)
                print(f"  {tag:4s} {info['contours']}c/{info['holes']}h "
                      f"area {s.area:9.3f} mm2  crossings {cr}  dup-pts "
                      f"{dups}  pts {tiny}")
                print(f"       health: {bad}")
                areas = sorted(abs(imgtrace._area2(
                    [tuple(p) for p in e['points']])) / 2.0 for e in ents)
                print(f"       entity areas: "
                      + ", ".join(f"{a:.5f}" for a in areas))
            except Exception as exc:                        # noqa: BLE001
                print(f"  {tag:4s} SKETCH FAIL {type(exc).__name__}: "
                      f"{str(exc)[:90]}")


if __name__ == "__main__":
    main()
