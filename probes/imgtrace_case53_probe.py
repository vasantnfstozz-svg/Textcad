"""probes/imgtrace_case53_probe.py - the one fuzz case that BUILT an invalid
solid (imgtrace_fuzz_probe #53). Isolates whether imgtrace produced a bad
entity or sketch.py composed good ones badly.
"""
from __future__ import annotations

import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imgtrace  # noqa: E402
import inspector  # noqa: E402
import sketch as sk  # noqa: E402
from imgtrace_fuzz_probe import audit, random_art  # noqa: E402


def case(n):
    rng = random.Random(7)
    for i in range(n + 1):
        data = random_art(rng)
        h = rng.choice([2.0, 3.0, 5.0, 12.0, 25.0, 50.0, 120.0])
    return data, h


def main():
    data, h = case(53)
    ents, info = imgtrace.image_to_entities(data, height_mm=h)
    print("info", info, "h", h)
    print("audit", audit(ents))
    print("modes", [e["mode"] for e in ents])
    for k, e in enumerate(ents):
        p = e["points"]
        xs = [q[0] + e["x"] for q in p]
        ys = [q[1] + e["y"] for q in p]
        a2 = sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                 for i in range(len(p))) / 2
        print(f"  ent{k} {e['mode']:9s} n={len(p):3d} area={a2:9.3f} "
              f"x {min(xs):8.3f}..{max(xs):8.3f}  y {min(ys):8.3f}..{max(ys):8.3f}")
    face = sk.make_sketch("XY", 0, ents)
    print("face area", face.area, "faces", len(face.faces()))
    solid = sk.extrude_sketch(face, 2.0)
    print("health", inspector.health(solid))
    print("measure", {k: v for k, v in inspector.measure(solid).items()
                      if k in ("volume", "n_solids", "n_faces")})
    # do any two entity outlines TOUCH / overlap boundaries?
    import itertools
    for a, b in itertools.combinations(range(len(ents)), 2):
        pa = np.array([[q[0] + ents[a]["x"], q[1] + ents[a]["y"]]
                       for q in ents[a]["points"]])
        pb = np.array([[q[0] + ents[b]["x"], q[1] + ents[b]["y"]]
                       for q in ents[b]["points"]])
        d = np.hypot(*(pa[:, None, :] - pb[None, :, :]).transpose(2, 0, 1)).min()
        if d < 0.15:
            print(f"  outlines {a} and {b} come within {d:.4f} mm "
                  f"({ents[a]['mode']} vs {ents[b]['mode']})")


if __name__ == "__main__":
    main()
