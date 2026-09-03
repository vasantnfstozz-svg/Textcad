"""PROBE (LAUNCH-PLAN.md rule 1 / CLAUDE.md "probe before you build"):
the facts behind sketch.APEX_FRACTION and sketch.collapse_offset.

Run:  C:\\Python314\\python.exe probes\\taper_apex_probe.py

Establishes, on THIS build123d/OCCT:
  1. a narrowing taper builds a watertight solid at 99.9% of the height where
     the walls meet, and the kernel refuses the exact (100%) tip;
  2. the kernel's wire-to-wire distance is exact where point sampling is not
     (a 200x200 plate with an r5 hole 2 mm from the edge: 2.000 vs 2.111);
  3. per-face results combine into the same Part type extrude() returns.
Re-run before changing APEX_FRACTION or collapse_offset.
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import inspector                       # noqa: E402
import sketch as sk                    # noqa: E402
from build123d import Part             # noqa: E402


def healthy(s):
    return not inspector.health(s)


def main():
    print("build123d", __import__("build123d").__version__)
    # 1. the apex fraction
    r, h = 35.39, 37.13                # a cone the user drew (2026-09-03)
    circ = sk.make_sketch(plane="XY", entities=[{"kind": "circle", "r": r}])
    meet = math.degrees(math.atan(r / h))
    for frac in (0.99, 0.999, 0.9999, 1.0):
        # ask for a taper whose walls meet at frac * h  (Fusion sign: negative narrows)
        t = -math.degrees(math.atan(r / (frac * h)))
        try:
            s = sk._tapered_extrude(circ, h, -t) if False else sk.extrude_sketch(circ, h, taper=t)
            print(f"  fraction {frac}: taper {t:.3f} -> top z {s.bounding_box().max.Z:.4f} "
                  f"healthy={healthy(s)}")
        except Exception as e:
            print(f"  fraction {frac}: REFUSED {str(e)[:90]}")
    print(f"  (walls meet at {meet:.2f} deg; APEX_FRACTION = {sk.APEX_FRACTION})")

    # 2. exact hole-wall distance vs sampling
    plate = sk.make_sketch(plane="XY", entities=[
        {"kind": "rectangle", "w": 200, "h": 200},
        {"kind": "circle", "r": 5, "x": 93, "y": 6, "mode": "subtract"}]).faces()[0]
    outer, hole = plate.outer_wire(), plate.inner_wires()[0]
    pts = lambda w: [w @ (i / 64) for i in range(64)]
    sampled = min((p - q).length for p in pts(hole) for q in pts(outer))
    t0 = time.time(); exact = hole.distance_to(outer); dt = (time.time() - t0) * 1000
    print(f"  hole->outer wall: exact {exact:.4f} mm ({dt:.1f} ms), 64-point sampling {sampled:.4f} mm, truth 2.0")
    print(f"  collapse_offset(plate) = {sk.collapse_offset(plate):.4f} (truth 1.0 = half the wall)")

    # 3. per-face combine
    a = sk.extrude_sketch(sk.make_sketch(plane="XY", entities=[{"kind": "circle", "r": 5}]), 3)
    b = sk.extrude_sketch(sk.make_sketch(plane="XY", entities=[{"kind": "circle", "r": 20, "x": 40}]), 3)
    both = Part(children=[a, b])
    print(f"  Part(children=[a, b]) -> {type(both).__name__} with {len(both.solids())} solids")


if __name__ == "__main__":
    main()
