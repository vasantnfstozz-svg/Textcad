"""The largest axis-aligned rectangle inside a face outline, probed before it
is written into studio.py.

Two APIs checked rather than remembered: cv2.fillPoly / cv2.erode on an int32
point array, and cv2.pointPolygonTest as the independent oracle. The answer
is checked against geometry that has a known one: a circle of radius r holds
a square of side r*sqrt(2), and a rectangle must come back as ITSELF.

Run:  C:\\Python314\\python.exe probes/imgtrace_inscribed_algo_probe.py
"""
from __future__ import annotations

import math

import cv2
import numpy as np

CELLS = 240


def _biggest_run(mask):
    """(area, i0, i1, j0, j1) of the largest all-true axis-aligned block of a
    2D bool array — the classic histogram sweep, one stack pass per row."""
    gh, gw = mask.shape
    heights = np.zeros(gw + 1, np.int32)
    best = (0, 0, -1, 0, -1)
    for j in range(gh):
        heights[:gw] = np.where(mask[j], heights[:gw] + 1, 0)
        stack = []
        for i in range(gw + 1):
            start = i
            while stack and stack[-1][1] >= heights[i]:
                s, hgt = stack.pop()
                if hgt * (i - s) > best[0]:
                    best = (hgt * (i - s), s, i - 1, j - hgt + 1, j)
                start = s
            stack.append((start, int(heights[i])))
    return best


def inscribed_box(outer, cells=CELLS):
    """(w, h, cx, cy) of the biggest axis-aligned rectangle inside the ring
    `outer` ([[x, y], ...] in the face's own 2D)."""
    xs = [float(p[0]) for p in outer]
    ys = [float(p[1]) for p in outer]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    box = (bw, bh, (x0 + x1) / 2, (y0 + y1) / 2)
    if bw <= 0 or bh <= 0:
        return box
    cell = max(bw, bh) / float(cells)
    gw, gh = max(1, round(bw / cell)), max(1, round(bh / cell))
    pts = np.array([[[round((x - x0) / cell), round((y - y0) / cell)]
                     for x, y in zip(xs, ys)]], np.int32)
    grid = np.zeros((gh + 1, gw + 1), np.uint8)
    cv2.fillPoly(grid, pts, 1)
    if int(grid.sum()) == grid.size:
        return box                      # the face IS its bounding box
    inside = cv2.erode(grid, np.ones((3, 3), np.uint8),
                       borderType=cv2.BORDER_CONSTANT, borderValue=0)
    area, i0, i1, j0, j1 = _biggest_run(inside.astype(bool))
    if area <= 0:
        return box
    ax0, ax1 = x0 + i0 * cell, x0 + i1 * cell
    ay0, ay1 = y0 + j0 * cell, y0 + j1 * cell
    if ax1 - ax0 <= 0 or ay1 - ay0 <= 0:
        return box
    return (ax1 - ax0, ay1 - ay0, (ax0 + ax1) / 2, (ay0 + ay1) / 2)


def corners(b):
    w, h, cx, cy = b
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
            (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def clearance(poly, b):
    """the worst (most negative = outside) signed distance of the box's
    perimeter to the ring, sampled densely"""
    w, h, cx, cy = b
    pts = []
    for t in np.linspace(0, 1, 200):
        pts += [(cx - w / 2 + t * w, cy - h / 2),
                (cx - w / 2 + t * w, cy + h / 2),
                (cx - w / 2, cy - h / 2 + t * h),
                (cx + w / 2, cy - h / 2 + t * h)]
    ring = np.array(poly, np.float32)
    return min(cv2.pointPolygonTest(ring, (float(x), float(y)), True)
               for x, y in pts)


def circle(r=30.0, n=256):
    return [[r * math.cos(2 * math.pi * i / n),
             r * math.sin(2 * math.pi * i / n)] for i in range(n)]


def main():
    cases = [
        ("rectangle 60 x 40",
         [[-30, -20], [30, -20], [30, 20], [-30, 20]], (60.0, 40.0)),
        ("circle r = 30", circle(30.0),
         (30.0 * math.sqrt(2), 30.0 * math.sqrt(2))),
        ("L 60x60 less a 30x30 bite",
         [[-30, -30], [30, -30], [30, 0], [0, 0], [0, 30], [-30, 30]],
         None),
        ("plus/cross", [[-10, -30], [10, -30], [10, -10], [30, -10],
                        [30, 10], [10, 10], [10, 30], [-10, 30],
                        [-10, 10], [-30, 10], [-30, -10], [-10, -10]], None),
        ("ellipse 80 x 30", [[40 * math.cos(t), 15 * math.sin(t)]
                             for t in np.linspace(0, 2 * math.pi, 256,
                                                  endpoint=False)], None),
    ]
    print(f"{'face':30s} {'bbox':>16s} {'inscribed':>16s} "
          f"{'clear mm':>9s} {'expected':>16s}")
    for name, poly, want in cases:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        bb = (max(xs) - min(xs), max(ys) - min(ys))
        b = inscribed_box(poly)
        c = clearance(poly, b)
        exp = f"{want[0]:7.2f}x{want[1]:7.2f}" if want else " " * 16
        print(f"{name:30s} {bb[0]:7.2f}x{bb[1]:7.2f} "
              f"{b[0]:7.2f}x{b[1]:7.2f} {c:9.3f} {exp}")
        assert c >= -1e-6, f"{name}: the box leaves the face by {-c:.3f} mm"
        if want:
            assert abs(b[0] - want[0]) < 1.0 and abs(b[1] - want[1]) < 1.0

    import time
    t = time.perf_counter()
    for _ in range(20):
        inscribed_box(circle(30.0))
    print(f"\ncost: {(time.perf_counter() - t) / 20 * 1000:.1f} ms per call "
          f"at {CELLS} cells")


if __name__ == "__main__":
    main()
