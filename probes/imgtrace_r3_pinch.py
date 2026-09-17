"""REVIEW-QUEUE section 9 round THREE — WHY those two traces build an
unhealthy solid.  `_uncross` guarantees no ONE polygon crosses itself; it
says nothing about two DIFFERENT polygons of the same sketch touching, and a
hole that touches its outer ring pinches the face.

Prints, per trace, the closest approach between every pair of entities and
what OpenCASCADE says about the solid.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_pinch.py
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
from imgtrace_r3_fuzz import corpus, png                    # noqa: E402

WANT = {"f73": 90.0, "f122": 12.0}


def seg_dist(a, b, c, d):
    """minimum distance between segment ab and segment cd"""
    def pt_seg(p, q, r):
        v = r - q
        t = 0.0 if not v.dot(v) else np.clip((p - q).dot(v) / v.dot(v), 0, 1)
        return float(np.linalg.norm(p - (q + t * v)))
    return min(pt_seg(a, c, d), pt_seg(b, c, d),
               pt_seg(c, a, b), pt_seg(d, a, b))


def closest(e1, e2):
    p = np.array([[e1["x"] + x, e1["y"] + y] for x, y in e1["points"]])
    q = np.array([[e2["x"] + x, e2["y"] + y] for x, y in e2["points"]])
    best = 1e9
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        for j in range(len(q)):
            best = min(best, seg_dist(a, b, q[j], q[(j + 1) % len(q)]))
    return best


def main():
    for name, m in corpus(150):
        if name not in WANT:
            continue
        h_mm = WANT[name]
        ents, info = imgtrace.image_to_entities(png(m), height_mm=h_mm)
        print(f"\n=== {name} at {h_mm:g} mm: {info} ===")
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                d = closest(ents[i], ents[j])
                if d < 0.05:
                    print(f"  ents {i} ({ents[i]['mode']}) and {j} "
                          f"({ents[j]['mode']}) come within {d:.6f} mm")
        s = sk.make_sketch("XY", 0, ents)
        solid = sk.extrude_sketch(s, 2.0)
        print(f"  sketch area {s.area:.4f} mm2, faces {len(s.faces())}")
        print(f"  solid volume {solid.volume:.4f}, is_valid "
              f"{solid.is_valid}, solids {len(solid.solids())}")
        print(f"  health: {inspector.health(solid)}")


if __name__ == "__main__":
    main()
