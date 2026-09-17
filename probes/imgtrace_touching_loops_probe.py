"""LAUNCH-PLAN s10 P2: two traced HOLES that touch pinch the face — the solid
is valid and the volume is right, and `inspector.health` says it is not
watertight.

`_uncross` splits a self-crossing outline at the crossing POINT and, when
both halves are artwork (a pinch, not a whisker), keeps them BOTH — carrying
the identical crossing point into each. So the two polygons handed to
sketch.py meet at exactly 0.000000 mm, and the face they cut has a pinch.

This probe (a) shows the shared point in the entities the tracer emits,
(b) measures the solid, and (c) sweeps the gap a fix would have to open to
find how far apart OpenCASCADE actually needs them.

Run:  C:\\Python314\\python.exe probes/imgtrace_touching_loops_probe.py
"""
from __future__ import annotations

import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402


def _png(img):
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def pinched_hole(size=1200, bar=1):
    """A solid plate whose HOLE is two discs joined by a `bar`-pixel neck."""
    img = np.zeros((size, size, 4), np.uint8)
    cv2.rectangle(img, (80, 80), (size - 80, size - 80), (10, 10, 10, 255), -1)
    hole = np.zeros((size, size), np.uint8)
    cv2.circle(hole, (size // 2, 420), 190, 1, -1)
    cv2.circle(hole, (size // 2, 780), 190, 1, -1)
    cv2.line(hole, (size // 2, 420), (size // 2, 780), 1, bar)
    img[hole.astype(bool)] = (0, 0, 0, 0)
    return _png(img)


def shared_points(ents, tol=1e-9):
    """(n_pairs, closest_mm) over every pair of DIFFERENT entities."""
    world = [[(e["x"] + px, e["y"] + py) for px, py in e["points"]]
             for e in ents]
    pairs, closest = 0, float("inf")
    for a in range(len(world)):
        for b in range(a + 1, len(world)):
            pa = np.asarray(world[a])
            pb = np.asarray(world[b])
            d = np.hypot(pa[:, None, 0] - pb[None, :, 0],
                         pa[:, None, 1] - pb[None, :, 1]).min()
            closest = min(closest, float(d))
            if d <= tol:
                pairs += 1
    return pairs, closest


def measure(ents, label):
    n_pairs, closest = shared_points(ents)
    add = sum(1 for e in ents if e["mode"] == "add")
    sub = len(ents) - add
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 3.0)
        vol = solid.volume
        health = inspector.health(solid)
        valid = inspector._try(lambda: solid.is_valid())
    except Exception as e:                       # noqa: BLE001 — report it
        print(f"{label:22s} REFUSED: {type(e).__name__}: {e}")
        return
    print(f"{label:22s} {add} add + {sub} holes, closest pair "
          f"{closest:.6f} mm ({n_pairs} touching), vol {vol:.2f} mm3, "
          f"valid {valid}, health {health}")


def main():
    data = pinched_hole()
    for h in (40.0, 60.0):
        ents, info = imgtrace.image_to_entities(data, height_mm=h)
        measure(ents, f"traced at {h:g} mm")
        print(f"                       info {info}")

    print("\nhow far apart does OCCT need two hole loops? "
          "(two 6 mm squares in a 60 mm plate)")
    for gap in (0.0, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.05, 0.2):
        ents = [{"kind": "polygon", "mode": "add", "x": 0, "y": 0,
                 "points": [[-30, -30], [30, -30], [30, 30], [-30, 30]]}]
        for sgn in (-1, 1):
            cx = sgn * (3.0 + gap / 2.0)
            ents.append({"kind": "polygon", "mode": "subtract",
                         "x": round(cx, 4), "y": 0.0,
                         "points": [[-3, -3], [3, -3], [3, 3], [-3, 3]]})
        measure(ents, f"gap {gap:.4f} mm")

    print("\nthe same, meeting at a POINT rather than along an edge "
          "(two squares corner to corner)")
    for gap in (0.0, 0.002, 0.005, 0.01, 0.05):
        d = (3.0 + gap / 2.0) * math.sqrt(2)
        ents = [{"kind": "polygon", "mode": "add", "x": 0, "y": 0,
                 "points": [[-30, -30], [30, -30], [30, 30], [-30, 30]]}]
        for sgn in (-1, 1):
            ents.append({"kind": "polygon", "mode": "subtract",
                         "x": round(sgn * d / math.sqrt(2) * 1.0, 4),
                         "y": round(sgn * d / math.sqrt(2) * 1.0, 4),
                         "points": [[-3, -3], [3, -3], [3, 3], [-3, 3]]})
        measure(ents, f"corner gap {gap:.4f}")


if __name__ == "__main__":
    main()
