"""REVIEW-QUEUE section 9 ROUND TWO — the one artwork that still reaches
OpenCASCADE with a crossed outline.

_uncross exists so that sketch.py is never handed a polygon that crosses
itself, and round one measured "240 random artworks: zero crossings, zero
unhealthy builds". A 426-trace sweep finds one that still does, in round
one's code and round two's alike. This pins down WHERE the crossing is
introduced.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_rand76.py
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

from imgtrace_r2_sweep import _crossings, _png                    # noqa: E402


def rand76():
    rng = np.random.default_rng(7)
    out = {}
    for k in range(120):
        m = np.zeros((300, 300), np.uint8)
        for _ in range(int(rng.integers(3, 9))):
            kind = int(rng.integers(0, 3))
            p = tuple(int(v) for v in rng.integers(40, 260, 2))
            if kind == 0:
                cv2.circle(m, p, int(rng.integers(10, 70)), 1, -1)
            elif kind == 1:
                q = tuple(int(v) for v in rng.integers(40, 260, 2))
                cv2.rectangle(m, p, q, 1, -1)
            else:
                q = tuple(int(v) for v in rng.integers(20, 280, 2))
                cv2.line(m, p, q, 1, int(rng.integers(1, 5)))
        if m.sum() >= 400:
            out[k] = m
    return out[76]


def main():
    seen = []
    real = imgtrace._uncross

    def spy(pts):
        out = real(pts)
        seen.append(([tuple(p) for p in pts], [list(map(tuple, o))
                                               for o in out]))
        return out
    imgtrace._uncross = spy
    try:
        ents, info = imgtrace.image_to_entities(_png(rand76()), height_mm=40.0)
    finally:
        imgtrace._uncross = real

    print(f"{info}")
    for k, (src, outs) in enumerate(seen):
        print(f"  contour {k}: in {len(src)} pts, "
              f"{_crossings(src)} crossings -> loops "
              f"{[len(o) for o in outs]}, crossings "
              f"{[_crossings(o) for o in outs]}")
    for k, e in enumerate(ents):
        c = _crossings(e["points"])
        print(f"  entity {k} ({e['mode']}, {len(e['points'])} pts): "
              f"{c} crossings")
        if c:
            pts = [tuple(p) for p in e["points"]]
            hit = imgtrace._first_crossing(pts)
            print(f"      _first_crossing says {hit}")
            # was this list clean BEFORE _poly_entity re-centred it?
            for src, outs in seen:
                for o in outs:
                    if len(o) == len(pts):
                        print(f"      matching loop before centring: "
                              f"{_crossings(o)} crossings, "
                              f"first {imgtrace._first_crossing(o)}")
    s = sk.make_sketch("XY", 0, ents)
    print(f"  area {s.area:.3f}, "
          f"health {inspector.health(sk.extrude_sketch(s, 2.0))}")


if __name__ == "__main__":
    main()
