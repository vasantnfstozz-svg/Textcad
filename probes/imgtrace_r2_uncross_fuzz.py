"""REVIEW-QUEUE section 9 ROUND TWO — instrument _uncross and hunt for a
firing that costs real artwork.

_uncross is inert on clean shapes, so this drives it: it wraps the function,
records every call that actually changes the outline, and reports the WORST
area fraction discarded over a wide sweep (thin necks at every width, pinched
letters, whisker combs, random blobs, several target heights).

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_uncross_fuzz.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                                    # noqa: E402

FIRINGS = []


def _instrument():
    real = imgtrace._uncross

    def wrapped(pts):
        out = real(pts)
        kept = sum(len(o) for o in out)
        if kept != len(pts):
            a_in = abs(imgtrace._area2(pts)) / 2.0
            a_out = sum(abs(imgtrace._area2(o)) / 2.0 for o in out)
            FIRINGS.append((a_in, a_out, len(pts), kept))
        return out
    imgtrace._uncross = wrapped
    return real


def _rgba(mask):
    h, w = mask.shape
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def _necks():
    for neck in range(1, 13):
        for size in (200, 400):
            m = np.zeros((size * 2 + 60, size + 100), np.uint8)
            cv2.rectangle(m, (50, 20), (50 + size, 20 + size), 1, -1)
            cv2.rectangle(m, (50, 40 + size), (50 + size, 40 + 2 * size), 1, -1)
            c = (size + 100) // 2
            m[20 + size:40 + size, c - neck // 2:c - neck // 2 + neck] = 1
            yield f"neck{neck}px_{size}", m


def _combs():
    for tooth in (1, 2, 3):
        m = np.zeros((300, 300), np.uint8)
        cv2.rectangle(m, (40, 150), (260, 250), 1, -1)
        for i in range(20):
            m[60:150, 50 + i * 10:50 + i * 10 + tooth] = 1
        yield f"comb{tooth}px", m


def _random(n=120, seed=7):
    rng = np.random.default_rng(seed)
    for k in range(n):
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
        yield f"rand{k}", m


def main():
    _instrument()
    worst = []
    cases = 0
    for name, m in list(_necks()) + list(_combs()) + list(_random()):
        data = _rgba(m)
        for h_mm in (8.0, 40.0, 120.0):
            before = len(FIRINGS)
            try:
                imgtrace.image_to_entities(data, height_mm=h_mm)
            except Exception:                                  # noqa: BLE001
                continue
            cases += 1
            for a_in, a_out, n_in, n_out in FIRINGS[before:]:
                frac = (a_in - a_out) / a_in if a_in else 0.0
                worst.append((frac, name, h_mm, a_in, a_out, n_in, n_out))
    worst.sort(reverse=True)
    print(f"{cases} traces; _uncross changed an outline {len(worst)} times")
    print(f"{'lost%':>7s} {'shape':14s} {'h_mm':>6s} {'area in':>10s} "
          f"{'area out':>10s} {'pts':>9s}")
    for frac, name, h, a_in, a_out, n_in, n_out in worst[:20]:
        print(f"{100 * frac:7.3f} {name:14s} {h:6.1f} {a_in:10.4f} "
              f"{a_out:10.4f} {n_in:4d}->{n_out:<4d}")
    if worst:
        print(f"\nWORST single loss: {100 * worst[0][0]:.4f}% of one outline "
              f"({worst[0][1]} at {worst[0][2]:g} mm)")
    else:
        print("\n_uncross never fired")


if __name__ == "__main__":
    main()
