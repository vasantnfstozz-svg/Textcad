"""The five traces the pull-apart audit leaves at EXACTLY 0.000000 mm.

`_pull_apart` opens a 0.01 mm hair between loops of one sketch. The audit
(probes/imgtrace_pull_apart_audit.py) finds 25 of 480 traces still closer
than 0.002 mm and 5 at exactly 0.000000 mm. This probe opens one of them up:
which loops, what modes, where they meet, and what OpenCASCADE makes of the
face — so the residual is a number and a verdict, not a worry.

Run:  C:/Python314/python.exe probes/imgtrace_zero_gap_case.py
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
from imgtrace_r4_fuzz import corpus                         # noqa: E402

WANT = {"p4": 15.0, "p88": 15.0, "p102": 45.0, "p116": 15.0}


def main():
    for name, img, _art, _cls, _drew in corpus(120):
        if name not in WANT:
            continue
        ok, buf = cv2.imencode(".png", img)
        assert ok
        h_mm = WANT[name]
        ents, info = imgtrace.image_to_entities(buf.tobytes(), height_mm=h_mm)
        print(f"\n=== {name} at {h_mm:g} mm: {info} ===")
        rings = [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                          float) for e in ents]
        for i in range(len(rings)):
            for j in range(i + 1, len(rings)):
                d1, f1 = imgtrace._nearest_on_ring(rings[i], rings[j])
                d2, _f = imgtrace._nearest_on_ring(rings[j], rings[i])
                g = min(float(d1.min()), float(d2.min()))
                if g >= 0.002:
                    continue
                v = int(d1.argmin())
                print(f"  loop {i} ({ents[i]['mode']}, "
                      f"{abs(imgtrace._area2(rings[i])) / 2:.4f} mm2) and "
                      f"loop {j} ({ents[j]['mode']}, "
                      f"{abs(imgtrace._area2(rings[j])) / 2:.4f} mm2) "
                      f"meet at {g:.6f} mm, near {tuple(rings[i][v])}")
                # is loop j inside loop i, or beside it?
                poly = rings[i].astype(np.float32)
                inside = sum(
                    1 for p in rings[j]
                    if cv2.pointPolygonTest(poly, (float(p[0]), float(p[1])),
                                            False) > 0)
                print(f"      {inside} of {len(rings[j])} points of loop {j} "
                      f"are INSIDE loop {i}")
        s = sk.make_sketch("XY", 0, ents)
        solid = sk.extrude_sketch(s, 2.0)
        print(f"  sketch area {s.area:.4f} mm2, faces {len(s.faces())}; "
              f"solid {solid.volume:.4f} mm3, solids "
              f"{len(solid.solids())}, health {inspector.health(solid)}")


if __name__ == "__main__":
    main()
