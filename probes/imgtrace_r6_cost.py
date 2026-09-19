"""ROUND SIX — what round six costs, on ordinary art and on the worst case.

Round five left one cost to judge: on a deliberately extreme 2400 x 3000
hatched picture the guard goes ~18 s to ~51 s, while ordinary art is
0.06-0.15 s. Round six adds three things to the same loop — a snap of the
move onto the 0.001 mm grid, `_walks_through_itself` per move, and the
give-up report — so the question is asked again, against the module as it was
at a chosen commit.

Run:  C:/Python314/python.exe probes/imgtrace_r6_cost.py [before.py]
      (default: probes/_imgtrace_r6_before.py)
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import png                          # noqa: E402


def load(path):
    spec = importlib.util.spec_from_file_location("imgtrace_before", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hatched(w=2400, h=3000, step=7, bar=2):
    """the extreme: a hatched plate with a hundred holes"""
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (60, 60), (w - 60, h - 60), 1, -1)
    for x in range(120, w - 120, step):
        cv2.rectangle(m, (x, 120), (x + bar, h - 120), 0, -1)
    for y in range(120, h - 120, step * 3):
        cv2.rectangle(m, (120, y), (w - 120, y + bar), 0, -1)
    for k in range(100):
        cv2.circle(m, (200 + (k % 10) * 220, 200 + (k // 10) * 280), 40, 0, -1)
    return m


def logo(w=900, h=600):
    """ordinary art: a word-shaped blob with a few holes"""
    m = np.zeros((h, w), np.uint8)
    for k in range(5):
        cv2.circle(m, (140 + k * 150, 300), 90, 1, -1)
        cv2.circle(m, (140 + k * 150, 300), 40, 0, -1)
    return m


def ring(w=420, h=320):
    m = np.zeros((h, w), np.uint8)
    cv2.circle(m, (210, 160), 130, 1, 30)
    for a in (0.3, 1.9, 3.4, 5.1):
        cv2.line(m, (210, 160),
                 (int(210 + 300 * np.cos(a)), int(160 + 300 * np.sin(a))),
                 1, 1)
    return m


CASES = [("ordinary logo 900x600 @ 40 mm", logo, 40.0),
         ("ring with hairline spokes @ 12 mm", ring, 12.0),
         ("HATCHED 2400x3000, 100 holes @ 8 mm", hatched, 8.0)]


def timed(mod, data, h):
    t0 = time.perf_counter()
    ents, info = mod.image_to_entities(data, height_mm=h)
    return time.perf_counter() - t0, len(ents), info["points"]


def loop_field(n_loops, n_pts, touch=True):
    """`n_loops` rings of `n_pts` points in a grid, each one a hair from its
    neighbours when `touch` — the shape of the pair scan's worst case"""
    out = []
    side = int(np.ceil(np.sqrt(n_loops)))
    pitch = 1.0 if touch else 3.0
    for k in range(n_loops):
        cx, cy = (k % side) * pitch, (k // side) * pitch
        ang = np.linspace(0, 2 * np.pi, n_pts, endpoint=False)
        r = 0.4995 if touch else 0.4
        out.append([(round(cx + r * np.cos(t), 3),
                     round(cy + r * np.sin(t), 3)) for t in ang])
    return out


def guard_cost(old):
    print(f"\n{'_pull_apart alone':<42}{'before':>10}{'after':>10}")
    for n_loops, n_pts, touch in ((50, 60, True), (200, 60, True),
                                  (400, 60, True), (200, 400, True),
                                  (400, 60, False)):
        loops = loop_field(n_loops, n_pts, touch)
        t0 = time.perf_counter()
        a = old._pull_apart([list(p) for p in loops])
        ta = time.perf_counter() - t0
        t0 = time.perf_counter()
        b = imgtrace._pull_apart([list(p) for p in loops])
        tb = time.perf_counter() - t0
        same = all(len(x) == len(y) for x, y in zip(a, b))
        tag = (f"{n_loops} loops x {n_pts} pts"
               + ("" if touch else ", clear of each other")
               + ("" if same else "  [POINT COUNTS CHANGED]"))
        print(f"{tag:<42}{ta:>9.2f}s{tb:>9.2f}s")


def main():
    path = (sys.argv[1] if len(sys.argv) > 1
            else os.path.join(HERE, "_imgtrace_r6_before.py"))
    before = load(path)
    print(f"before = {os.path.basename(path)}\n")
    print(f"{'case':<38}{'before':>10}{'after':>10}{'loops':>8}{'points':>9}")
    for name, gen, h in CASES:
        data = png(gen())
        t0, n0, p0 = timed(before, data, h)
        t1, n1, p1 = timed(imgtrace, data, h)
        print(f"{name:<38}{t0:>9.2f}s{t1:>9.2f}s{n1:>8}{p1:>9}"
              + ("" if (n0, p0) == (n1, p1) else f"   (was {n0}/{p0})"))
    guard_cost(before)


if __name__ == "__main__":
    main()
