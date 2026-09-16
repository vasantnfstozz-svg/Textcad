"""REVIEW-QUEUE section 9 ROUND TWO — the two artworks _uncross mutilates.

The fuzz (probes/imgtrace_r2_uncross_fuzz.py) found _uncross discarding 48.9%
and 23.4% of ONE outline. This pins those two down end to end: true pixel
area against traced area with _uncross as shipped and with it disabled, plus
what the discarded loop actually was.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_uncross_case.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                                    # noqa: E402
import inspector                                                   # noqa: E402
import sketch as sk                                                # noqa: E402


def _random_case(k, seed=7, n=120):
    rng = np.random.default_rng(seed)
    for idx in range(n):
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
        if m.sum() < 400:
            continue
        if idx == k:
            return m
    raise SystemExit(f"case {k} not reached")


def _png(mask):
    h, w = mask.shape
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def _trace(data, h_mm, uncross):
    saved = imgtrace._uncross
    if not uncross:
        imgtrace._uncross = lambda p: [p]      # no splitting at all
    try:
        ents, info = imgtrace.image_to_entities(data, height_mm=h_mm)
        try:
            s = sk.make_sketch("XY", 0, ents)
            area, health = s.area, ""
            solid = sk.extrude_sketch(s, 2.0)
            health = "; ".join(inspector.health(solid)) or "healthy"
        except Exception as e:                                # noqa: BLE001
            return None, f"{type(e).__name__}: {e}", info
        return area, health, info
    finally:
        imgtrace._uncross = saved


def main():
    for k in (81, 23, 58):
        m = _random_case(k)
        data = _png(m)
        h_mm = 40.0
        ys, _ = np.where(m)
        mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
        truth = float(m.sum()) * mm_px * mm_px
        a_on, h_on, i_on = _trace(data, h_mm, True)
        a_off, h_off, i_off = _trace(data, h_mm, False)
        print(f"--- rand{k}: {m.shape[1]}x{m.shape[0]} px, "
              f"{int(m.sum())} ink px -> a true {truth:.2f} mm2")
        print(f"    shipped (_uncross on) : {a_on!r:>12} mm2  "
              f"{i_on['contours']}c/{i_on['holes']}h/{i_on['points']}p  {h_on}")
        print(f"    _uncross disabled     : {a_off!r:>12} mm2  "
              f"{i_off['contours']}c/{i_off['holes']}h/{i_off['points']}p  "
              f"{h_off}")
        if isinstance(a_on, float) and isinstance(a_off, float):
            print(f"    difference vs truth   : shipped "
                  f"{100 * (a_on - truth) / truth:+.2f}%, "
                  f"off {100 * (a_off - truth) / truth:+.2f}%")
        print()


if __name__ == "__main__":
    main()
