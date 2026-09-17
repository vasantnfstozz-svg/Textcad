"""REVIEW-QUEUE section 9 ROUND FOUR — the SECOND carried item, verified the
way the round-four brief asks: run the ORIGINAL module over the SAME 450
traces round three fuzzed and count what it leaves behind.

Round three carried "two HOLES touching at exactly 0.000000 mm pinch the face
- 2 of 450 traces, pre-existing under all three rules". `imgtrace_r3_unhealthy`
only re-ran the TWO traces it already knew about; this runs the whole corpus
through one module at a time, so "pre-existing" is a count and not a sample.

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_pre_existing.py <old|r1|r2|ship>
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
import _imgtrace_old as OLD                                 # noqa: E402
import _imgtrace_r1 as R1                                   # noqa: E402
import _imgtrace_r2 as R2                                   # noqa: E402
from imgtrace_r3_fuzz import corpus, png, crossings         # noqa: E402

MODS = {"old": OLD, "r1": R1, "r2": R2, "ship": imgtrace}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "old"
    mod = MODS[tag]
    tot = cross_tot = bad_tot = refused = 0
    bad_names, cross_names = [], []
    worst_short = (0.0, "")
    for name, m in corpus(150):
        data = png(m)
        for h_mm in (12.0, 40.0, 90.0):
            try:
                ents, _info = mod.image_to_entities(data, height_mm=h_mm)
            except Exception:                               # noqa: BLE001
                refused += 1
                continue
            tot += 1
            c = sum(crossings(e["points"]) for e in ents)
            if c:
                cross_tot += c
                cross_names.append(f"{name}@{h_mm:g}({c})")
            try:
                solid, _ma = imgtrace._traceable(
                    imgtrace._mask_from_image(
                        __import__("cv2").imdecode(
                            np.frombuffer(data, np.uint8), -1)), h_mm)
                sy, _sx = np.where(solid)
                mm_px = h_mm / (int(sy.max()) - int(sy.min()) + 1)
                ink = float(solid.sum()) * mm_px * mm_px
                s = sk.make_sketch("XY", 0, ents)
                area = s.area
                if inspector.health(sk.extrude_sketch(s, 2.0)):
                    bad_tot += 1
                    bad_names.append(f"{name}@{h_mm:g}")
                short = (ink - area) / ink
                if short > worst_short[0]:
                    worst_short = (short, f"{name}@{h_mm:g}")
            except Exception as exc:                        # noqa: BLE001
                bad_tot += 1
                bad_names.append(f"{name}@{h_mm:g}:{type(exc).__name__}")
    print(f"\n[{tag}] {tot} traces ({refused} refused)")
    print(f"  self-crossing edges handed to sketch.py: {cross_tot} "
          f"{cross_names[:12]}")
    print(f"  invalid / unhealthy solids: {bad_tot} {bad_names[:12]}")
    print(f"  worst shortfall vs the ink: {100 * worst_short[0]:.2f}% "
          f"({worst_short[1]})")


if __name__ == "__main__":
    main()
