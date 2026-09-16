"""REVIEW-QUEUE section 9 ROUND TWO — a DETERMINISTIC artwork that _uncross
mutilates, small enough to be a test.

The fuzz found it on random blobs; this sweeps plain two-lobe artworks (a
bar-joined dumbbell, an hourglass, a bent neck) at every neck width and a few
heights, and prints the ones where the traced area falls short of the ink.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_pinch.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                                    # noqa: E402
import sketch as sk                                                # noqa: E402


def _png(mask):
    h, w = mask.shape
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def _area(data, h_mm):
    try:
        ents, _ = imgtrace.image_to_entities(data, height_mm=h_mm)
        return sk.make_sketch("XY", 0, ents).area
    except Exception:                                          # noqa: BLE001
        return None


def dumbbell(neck, ang=0):
    m = np.zeros((420, 820), np.uint8)
    cv2.circle(m, (170, 210), 130, 1, -1)
    cv2.circle(m, (650, 210), 130, 1, -1)
    cv2.line(m, (170, 210), (650, 210 + ang), 1, neck)
    return m


def bowtie(neck):
    m = np.zeros((520, 520), np.uint8)
    cv2.fillPoly(m, [np.array([(30, 30), (250 - neck, 250), (30, 470)])], 1)
    cv2.fillPoly(m, [np.array([(490, 30), (250 + neck, 250), (490, 470)])], 1)
    m[250 - neck:250 + neck, 250 - neck:250 + neck] = 1
    return m


def bent(neck):
    m = np.zeros((520, 520), np.uint8)
    cv2.circle(m, (140, 140), 110, 1, -1)
    cv2.circle(m, (380, 380), 110, 1, -1)
    cv2.line(m, (140, 140), (380, 380), 1, neck)
    return m


def main():
    print(f"{'shape':16s} {'neck':>5s} {'h_mm':>6s} {'true mm2':>10s} "
          f"{'traced':>10s} {'lost%':>7s}")
    worst = None
    for name, fn, args in (("dumbbell", dumbbell, range(1, 10)),
                           ("dumbbell_tilt", lambda n: dumbbell(n, 60),
                            range(1, 10)),
                           ("bowtie", bowtie, range(1, 8)),
                           ("bent", bent, range(1, 10))):
        for neck in args:
            m = fn(neck)
            data = _png(m)
            for h_mm in (20.0, 40.0, 90.0):
                ys, _ = np.where(m)
                mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
                truth = float(m.sum()) * mm_px * mm_px
                got = _area(data, h_mm)
                if got is None:
                    continue
                lost = 100.0 * (truth - got) / truth
                if lost > 5.0:
                    print(f"{name:16s} {neck:5d} {h_mm:6.1f} {truth:10.2f} "
                          f"{got:10.2f} {lost:7.2f}")
                    if worst is None or lost > worst[0]:
                        worst = (lost, name, neck, h_mm, truth, got)
    if worst:
        print(f"\nWORST: {worst[1]} neck {worst[2]} px at {worst[3]:g} mm — "
              f"traced {worst[5]:.2f} of a true {worst[4]:.2f} mm2 "
              f"({worst[0]:.1f}% lost)")
    else:
        print("\nnothing lost more than 5%")


if __name__ == "__main__":
    main()
