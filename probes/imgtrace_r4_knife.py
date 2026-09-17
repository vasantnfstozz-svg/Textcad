"""REVIEW-QUEUE section 9 ROUND FOUR — the FIRST carried item, verified.

Round three carried "the 5%-of-the-picture threshold is a knife edge (13 px
scan edge right, 16 px wrong)" and said removing it would break inverse-video
art with a counter. Both halves are checked here by measurement:

  1. sweep the scan edge one pixel at a time and print where the answer
     turns, on three picture sizes, so the edge is a number and not a claim;
  2. re-score ALL FOUR corpora with the 5% test deleted (every dark shell
     read past, however fat) and print exactly which pictures that breaks.

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_knife.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import imgtrace_r4_corpus as C4                             # noqa: E402
import imgtrace_r3_corpus as C3                             # noqa: E402


def scan_sheet(size, band, n=5):
    """paper with a dark platen edge and a row of dark letters on it"""
    img = np.full((size, size, 3), 255, np.uint8)
    w, step = size // 12, size // 7
    for i in range(n):
        cv2.rectangle(img, (size // 8 + i * step, size * 2 // 5),
                      (size // 8 + i * step + w, size * 3 // 5),
                      (0, 0, 0), -1)
    img[:band] = img[-band:] = 0
    img[:, :band] = img[:, -band:] = 0
    return img


def side(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    got = imgtrace._mask_from_image(img)
    return "bright" if int((got == m).sum()) == m.size else "dark"


def shell_thickness(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    sh = imgtrace._edge_shell(m, 0, np.ones(m.shape, np.uint8))
    if sh is None:
        return -1.0
    return float(cv2.distanceTransform(sh, cv2.DIST_L2, 3).max())


def sweep():
    print("=== 1. where the 5% threshold actually turns ===")
    print("    (truth is 'dark' everywhere: dark letters on paper)")
    for size in (400, 800, 2400):
        lim = 0.05 * size
        row = []
        turn = None
        for band in range(1, int(lim * 1.4) + 6):
            s = side(scan_sheet(size, band))
            row.append((band, s, shell_thickness(scan_sheet(size, band))))
            if s != "dark" and turn is None:
                turn = band
        print(f"\n  {size} px picture: 5% of min(shape) = {lim:.1f} px")
        print(f"    last band read RIGHT : {turn - 1 if turn else 'all'} px"
              f"  (shell thickness {row[turn - 2][2]:.2f})" if turn
              else "    every band read RIGHT")
        if turn:
            print(f"    first band read WRONG: {turn} px"
                  f"  (shell thickness {row[turn - 1][2]:.2f})")
            print(f"    = {100.0 * turn / size:.2f}% of the picture; "
                  f"the corner of a t px band is t*sqrt(2) thick, so the "
                  f"effective pad limit is 5%/sqrt(2) = "
                  f"{lim / np.sqrt(2):.1f} px")


def no_5pct(m):
    """`_border_bright` with the 5% thinness test DELETED"""
    valid = np.ones(m.shape, np.uint8)
    ring = imgtrace._ring_mean(m, valid)
    if ring > 0.4:
        return ring
    shell = imgtrace._edge_shell(m, 0, valid)
    if shell is None:
        return ring
    rest = (1 - shell).astype(np.uint8)
    inside = m[rest.astype(bool)]
    lit = int(inside.sum())
    if min(lit, int(inside.size) - lit) < 64:
        return ring
    return imgtrace._ring_mean(m, rest)


def rescore():
    print("\n\n=== 2. what deleting the 5% test costs, over all four corpora "
          "===")
    orig = imgtrace._border_bright
    cases = list(C3.r1_cases()) + list(C3.r2_cases()) + \
        list(C3.r3_cases()) + list(C4.r4_cases())
    ship = {}
    for name, im, truth, _d in cases:
        if truth is None:
            continue
        ship[name] = (C4.side_of(im, imgtrace._mask_from_image(im)), truth)
    imgtrace._border_bright = no_5pct
    broke, healed, n_ship, n_no = [], [], 0, 0
    for name, im, truth, _d in cases:
        if truth is None:
            continue
        got = C4.side_of(im, imgtrace._mask_from_image(im))
        was, _t = ship[name]
        n_ship += was == truth
        n_no += got == truth
        if was == truth and got != truth:
            broke.append(name)
        if was != truth and got == truth:
            healed.append(name)
    imgtrace._border_bright = orig
    print(f"  shipped (5% test in place): {n_ship} of {len(ship)}")
    print(f"  5% test deleted           : {n_no} of {len(ship)}")
    print(f"  BROKEN by deleting it ({len(broke)}): {', '.join(broke)}")
    print(f"  HEALED by deleting it ({len(healed)}): {', '.join(healed)}")


if __name__ == "__main__":
    sweep()
    rescore()
