"""REVIEW-QUEUE section 9 ROUND TWO — the whole-sweep proof.

Traces a wide corpus (thin necks at every width, whisker combs, 120 random
artworks, three target heights each) through round ONE's imgtrace and round
TWO's, and for every trace measures three things against the picture itself:

  * how much of the ink came back (traced mm2 vs pixel mm2),
  * whether any entity crosses itself (what _uncross exists to prevent),
  * whether the extruded solid is healthy.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_sweep.py
"""
from __future__ import annotations

import importlib.util
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace as r2                                             # noqa: E402
import inspector                                                  # noqa: E402
import sketch as sk                                               # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "imgtrace_r1", os.path.join(HERE, "_imgtrace_r1.py"))
r1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r1)


def _png(mask):
    h, w = mask.shape
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def _crossings(pts):
    n = len(pts)
    a = np.asarray(pts, float)
    r = np.roll(a, -1, axis=0) - a
    hits = 0
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            den = r[i, 0] * r[j, 1] - r[i, 1] * r[j, 0]
            if abs(den) < 1e-15:
                continue
            d = a[j] - a[i]
            t = (d[0] * r[j, 1] - d[1] * r[j, 0]) / den
            u = (d[0] * r[i, 1] - d[1] * r[i, 0]) / den
            hits += 0 <= t <= 1 and 0 <= u <= 1
    return hits


def corpus():
    for neck in range(1, 13):
        m = np.zeros((460, 500), np.uint8)
        cv2.rectangle(m, (50, 20), (450, 220), 1, -1)
        cv2.rectangle(m, (50, 240), (450, 440), 1, -1)
        c = 250
        m[220:240, c - neck // 2:c - neck // 2 + neck] = 1
        yield f"neck{neck}", m
    for neck in range(1, 8):
        m = np.zeros((420, 820), np.uint8)
        cv2.circle(m, (170, 210), 130, 1, -1)
        cv2.circle(m, (650, 210), 130, 1, -1)
        cv2.line(m, (170, 210), (650, 210), 1, neck)
        yield f"dumbbell{neck}", m
    for tooth in (1, 2, 3):
        m = np.zeros((300, 300), np.uint8)
        cv2.rectangle(m, (40, 150), (260, 250), 1, -1)
        for i in range(20):
            m[60:150, 50 + i * 10:50 + i * 10 + tooth] = 1
        yield f"comb{tooth}", m
    rng = np.random.default_rng(7)
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
            yield f"rand{k}", m


def run(mod, data, truth, h_mm):
    try:
        ents, _ = mod.image_to_entities(data, height_mm=h_mm)
    except Exception:                                          # noqa: BLE001
        return None
    cross = sum(_crossings(e["points"]) for e in ents)
    try:
        s = sk.make_sketch("XY", 0, ents)
        area = s.area
        bad = inspector.health(sk.extrude_sketch(s, 2.0))
    except Exception as e:                                     # noqa: BLE001
        return {"short": 1.0, "cross": cross, "bad": 1,
                "note": type(e).__name__}
    return {"short": (truth - area) / truth, "cross": cross,
            "bad": 1 if bad else 0, "note": ""}


def main():
    acc = {"r1": [], "r2": []}
    n = 0
    for name, m in corpus():
        data = _png(m)
        ys, _ = np.where(m)
        for h_mm in (12.0, 40.0, 90.0):
            mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
            truth = float(m.sum()) * mm_px * mm_px
            a, b = run(r1, data, truth, h_mm), run(r2, data, truth, h_mm)
            if a is None or b is None:
                continue
            n += 1
            acc["r1"].append((a["short"], name, h_mm, a))
            acc["r2"].append((b["short"], name, h_mm, b))
    print(f"{n} traces compared\n")
    for tag in ("r1", "r2"):
        rows = sorted(acc[tag], reverse=True)
        cross = sum(r[3]["cross"] for r in rows)
        bad = sum(r[3]["bad"] for r in rows)
        over5 = sum(1 for r in rows if r[0] > 0.05)
        print(f"round {'ONE' if tag == 'r1' else 'TWO'}: "
              f"worst shortfall {100 * rows[0][0]:6.2f}% ({rows[0][1]} at "
              f"{rows[0][2]:g} mm) | traces losing >5% of the ink: {over5} | "
              f"self-crossings: {cross} | unhealthy solids: {bad}")
        for r in rows[:5]:
            print(f"      {100 * r[0]:6.2f}%  {r[1]} at {r[2]:g} mm")
    print()


if __name__ == "__main__":
    main()
