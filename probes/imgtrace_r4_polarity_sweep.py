"""REVIEW-QUEUE section 9 ROUND FOUR — the polarity rule scored on 230 random
OPAQUE pictures whose answer is known by construction, for all four rules.

The four corpora are hand-built pictures, 74 of them. This is the same
question asked of a generator instead of a reviewer: draw the art, remember
which side it was drawn on, and ask each rule. No solids are built, so it is
cheap enough to run every rule over every picture.

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_polarity_sweep.py [n]
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import _imgtrace_old as OLD                                 # noqa: E402
import _imgtrace_r1 as R1                                   # noqa: E402
import _imgtrace_r2 as R2                                   # noqa: E402
from imgtrace_r4_fuzz import corpus                         # noqa: E402

RULES = [("old", OLD), ("r1", R1), ("r2", R2), ("ship", imgtrace)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 230
    tot = 0
    hit = {t: 0 for t, _ in RULES}
    by_cls = defaultdict(lambda: {t: 0 for t, _ in RULES})
    by_n = defaultdict(int)
    for _name, img, art, cls, drew in corpus(n):
        ok, buf = cv2.imencode(".png", img)
        assert ok
        data = buf.tobytes()
        dec = cv2.imdecode(np.frombuffer(data, np.uint8),
                           cv2.IMREAD_UNCHANGED)
        tot += 1
        by_n[(cls, drew)] += 1
        for tag, mod in RULES:
            got = mod._mask_from_image(dec)
            right = int((got == art).sum()) / art.size > 0.98
            hit[tag] += right
            by_cls[(cls, drew)][tag] += right
    print(f"\n{tot} opaque pictures, the side each rule picked:\n")
    print(f"  {'class':16s} {'drawn':11s} {'n':>4s}  "
          + "  ".join(f"{t:>5s}" for t, _ in RULES))
    print("  " + "-" * 56)
    for key in sorted(by_cls):
        row = by_cls[key]
        print(f"  {key[0]:16s} {key[1]:11s} {by_n[key]:4d}  "
              + "  ".join(f"{row[t]:5d}" for t, _ in RULES))
    print("  " + "-" * 56)
    print(f"  {'TOTAL':16s} {'':11s} {tot:4d}  "
          + "  ".join(f"{hit[t]:5d}" for t, _ in RULES))
    print("\n  " + ",  ".join(f"{t} {100.0 * hit[t] / tot:.1f}%"
                              for t, _ in RULES))


if __name__ == "__main__":
    main()
