"""REVIEW-QUEUE section 9 ROUND FIVE — is there a fit-box rule that serves
BOTH the washer and the bolted plate?

`studio._inscribed_box` deliberately ignores holes, so on a washer the box
lands on the hole and most of the traced art is over air. Round four measured
the obvious fix — punch the holes out of the grid — and rejected it: it costs
little on a plate with a few bolt holes and collapses a plate with 24 of them
to a strip.

This probe measures three rules on the same faces, so the decision is made on
numbers rather than on either anecdote:

  ignore  — what ships: the biggest rectangle inside the OUTER outline
  punch   — round four's rejected fix: the biggest rectangle inside the outer
            outline that touches no hole
  material— the rectangle inside the outer outline with the most MATERIAL in
            it (holes allowed, but they count against it) — a rule with no
            threshold to calibrate

Run:  C:/Python314/python.exe probes/imgtrace_r5_fitbox_holes.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import studio                                               # noqa: E402

CELLS = 160


def ring(cx, cy, r, n=64):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return [(cx + r * np.cos(t), cy + r * np.sin(t)) for t in a]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


FACES = {
    "washer 60 od / 40 id": (ring(0, 0, 30), [ring(0, 0, 20)]),
    "plate 120x80, 4 bolt holes d6": (
        rect(-60, -40, 60, 40),
        [ring(sx * 50, sy * 30, 3) for sx in (-1, 1) for sy in (-1, 1)]),
    "plate 120x80, 24 bolt holes d5": (
        rect(-60, -40, 60, 40),
        [ring(-55 + 10 * k, sy * 33, 2.5)
         for k in range(12) for sy in (-1, 1)]),
    "plate 120x80, 90x55 pocket": (
        rect(-60, -40, 60, 40), [rect(-45, -27.5, 45, 27.5)]),
    "cover 100x100, d30 centre bore": (
        rect(-50, -50, 50, 50), [ring(0, 0, 15)]),
    "disc r30, no holes": (ring(0, 0, 30), []),
    "rectangle 120x80": (rect(-60, -40, 60, 40), []),
}


def grids(outer, holes, cells=CELLS):
    xs = [p[0] for p in outer]
    ys = [p[1] for p in outer]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    cell = max(bw, bh) / float(cells)
    gh = max(1, round(bh / cell)) + 1
    gw = max(1, round(bw / cell)) + 1

    def raster(loop):
        pts = np.array([[[round((x - x0) / cell), round((y - y0) / cell)]
                         for x, y in loop]], np.int32)
        g = np.zeros((gh, gw), np.uint8)
        cv2.fillPoly(g, pts, 1)
        return g

    face = raster(outer)
    air = np.zeros_like(face)
    for h in holes:
        air |= raster(h)
    return face, air, cell, x0, y0


def box_from(block, cell, x0, y0):
    area, i0, i1, j0, j1 = block
    if area <= 0 or i1 <= i0 or j1 <= j0:
        return None
    return (x0 + i0 * cell, x0 + i1 * cell, y0 + j0 * cell, y0 + j1 * cell)


def best_material(mask, material):
    """the rectangle of all-true `mask` cells with the most `material` cells
    in it — a maximum-sum submatrix (Kadane over every row band)"""
    gh, gw = mask.shape
    val = np.where(mask, np.where(material, 1, 0), -10 ** 6).astype(np.int64)
    best = (0, 0, -1, 0, -1)
    for j0 in range(gh):
        acc = np.zeros(gw, np.int64)
        for j1 in range(j0, gh):
            acc += val[j1]
            run, start = 0, 0
            for i in range(gw):
                if run <= 0:
                    run, start = acc[i], i
                else:
                    run += acc[i]
                if run > best[0]:
                    best = (int(run), start, i, j0, j1)
    return best


def measure(name, outer, holes):
    face, air, cell, x0, y0 = grids(outer, holes)
    k3 = np.ones((3, 3), np.uint8)
    inside = cv2.erode(face, k3, borderType=cv2.BORDER_CONSTANT,
                       borderValue=0).astype(bool)
    material = inside & ~cv2.dilate(air, k3).astype(bool)
    rules = {
        "ignore": box_from(studio._biggest_all_true_block(inside),
                           cell, x0, y0),
        "punch": box_from(studio._biggest_all_true_block(material),
                          cell, x0, y0),
        "material": box_from(best_material(inside, material), cell, x0, y0),
    }
    print(f"\n{name}")
    for rname, b in rules.items():
        if b is None:
            print(f"  {rname:9s}  (none)")
            continue
        ax0, ax1, ay0, ay1 = b
        i0, i1 = int(round((ax0 - x0) / cell)), int(round((ax1 - x0) / cell))
        j0, j1 = int(round((ay0 - y0) / cell)), int(round((ay1 - y0) / cell))
        win = material[j0:j1 + 1, i0:i1 + 1]
        on = float(win.mean()) if win.size else 0.0
        w, h = ax1 - ax0, ay1 - ay0
        print(f"  {rname:9s} {w:7.2f} x {h:7.2f} mm = {w * h:9.1f} mm2, "
              f"{100 * on:5.1f}% on material, "
              f"{w * h * on:9.1f} mm2 of it")


def main():
    for name, (outer, holes) in FACES.items():
        measure(name, outer, holes)


if __name__ == "__main__":
    main()
