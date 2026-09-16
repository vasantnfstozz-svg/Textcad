"""probes/imgtrace_spike_probe.py - REVIEW-QUEUE section 9.

Where does the zero-width SPIKE in a traced outline come from: the source
contour, approxPolyDP, or _chaikin? And does the outline actually CROSS
itself (which sketch.py would build as a silently wrong area)?
"""
from __future__ import annotations

import itertools
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imgtrace  # noqa: E402
from imgtrace_case53_probe import case  # noqa: E402
from imgtrace_fuzz_probe import crossings  # noqa: E402

assert itertools


def stage_report(name, pts):
    p = [tuple(map(float, q)) for q in pts]
    x = crossings(p)
    n = len(p)
    spikes = 0
    for i in range(n):
        a = np.array(p[(i - 1) % n]) - np.array(p[i])
        b = np.array(p[(i + 1) % n]) - np.array(p[i])
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na > 1e-12 and nb > 1e-12:
            cosang = float(np.dot(a, b) / (na * nb))
            if cosang > 0.9999:          # < ~0.8 deg included angle: a spike
                spikes += 1
    print(f"  {name}: {n} pts, {len(x)} self-crossings, {spikes} needle corners")
    if x[:4]:
        print("    first crossings:", x[:4])
    return x


def main():
    data, h = case(53)
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    mask = imgtrace._mask_from_image(img)
    n_comp, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    comp_areas = stats[1:, 4]
    ys, xs = np.where(mask)
    h_all = int(ys.max()) - int(ys.min()) + 1
    mm_px = h / h_all
    min_area = max(9.0, (0.25 / mm_px) ** 2)
    keep = {i + 1 for i, a in enumerate(comp_areas) if a >= min_area}
    solid = np.isin(labels, list(keep)).astype(np.uint8)
    cnts, hier = cv2.findContours(solid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    x0, y0, w, hh = cv2.boundingRect(np.vstack([c for c in cnts]))
    mm_px = h / hh
    eps = max(1.0, min(3.0, 0.15 / mm_px))
    cut_px = max(0.8, min(2.0, 0.4 / mm_px))
    print(f"mm_px={mm_px:.5f} eps={eps:.3f}px cut_px={cut_px:.3f}px")
    big = max(range(len(cnts)), key=lambda i: cv2.contourArea(cnts[i]))
    raw = cnts[big].reshape(-1, 2).astype(float)
    stage_report("raw contour", raw)
    ap = cv2.approxPolyDP(cnts[big], eps, True).reshape(-1, 2).astype(float)
    stage_report("after approxPolyDP", ap)
    ch = imgtrace._chaikin(ap, cut_px=cut_px)
    stage_report("after _chaikin", ch)
    mm = [((px - (x0 + w / 2)) * mm_px, ((y0 + hh / 2) - py) * mm_px)
          for px, py in ch]
    stage_report("after scale to mm", mm)
    rounded = imgtrace._round_pts(mm)
    stage_report("after _round_pts", rounded)
    stage_report("after _uncross (the fix)", imgtrace._uncross(rounded))


if __name__ == "__main__":
    main()
