"""REVIEW-QUEUE section 9 ROUND FIVE — what the hair-cluster walk costs when
a picture puts MANY vertices inside the hair at once.

Round four's fix moves a vertex together with the run of neighbours joined to
it by edges shorter than the push (`_hair_cluster`). That walk is O(n) in the
loop's own point count, and it is run once PER NEAR VERTEX, per pair, per
round (four rounds). So the cost is quadratic in the number of points that
are inside the hair together.

A hair is 0.01 mm. A raster's two nearest contours are two pixels apart, so
they are inside the hair as soon as mm/px < 0.005 — a 3000 px scan traced
12 mm tall, which is exactly what "trace this logo onto a small face" does.

This probe times the guard on detailed art at shrinking target heights and
prints how many loops, points and near vertices each one has.

Run:  C:/Python314/python.exe probes/imgtrace_r5_cluster_cost.py
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402


def png(m):
    img = np.zeros(m.shape + (4,), np.uint8)
    img[:, :, 3] = (m > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def hatched_plate(h=3000, w=2400, pitch=14, bar=7):
    """a filled plate combed by fine slots — ordinary hatched/engraved art,
    and a picture whose contours run alongside each other for their whole
    length"""
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (60, 60), (w - 61, h - 61), 1, -1)
    for y in range(200, h - 200, pitch):
        m[y:y + bar, 200:w - 200] = 0
    return m


def wavy_slots(h=3000, w=2400, pitch=26, bar=13, amp=5, freq=0.35):
    """the same comb, but every slot edge WAVES — Douglas-Peucker then has to
    keep a point every few pixels, so the loops carry thousands of points AND
    run alongside each other inside the hair"""
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (60, 60), (w - 61, h - 61), 1, -1)
    xs = np.arange(200, w - 200)
    wave = (amp * np.sin(freq * xs)).astype(np.int32)
    for y in range(200, h - 200, pitch):
        for k, x in enumerate(xs):
            m[y + wave[k]:y + wave[k] + bar, x] = 0
    return m


def main():
    real = imgtrace._pull_apart
    calls = {"n": 0, "t": 0.0, "loops": 0, "pts": 0}

    def timed(loops, gap=imgtrace._HAIR_MM):
        t0 = time.perf_counter()
        out = real(loops, gap)
        calls["t"] += time.perf_counter() - t0
        calls["n"] += 1
        calls["loops"] = len(loops)
        calls["pts"] = sum(len(p) for p in loops)
        return out

    imgtrace._pull_apart = timed
    try:
        print(f"{'height':>8s} {'mm/px':>9s} {'loops':>6s} {'points':>7s} "
              f"{'_pull_apart':>12s} {'whole trace':>12s}")
        pics = [("comb", png(hatched_plate())), ("wavy", png(wavy_slots()))]
        for pname, data in pics:
          print(f"-- {pname}")
          for height in (60.0, 30.0, 18.0, 12.0, 8.0, 5.0, 3.0):
            calls["t"] = 0.0
            t0 = time.perf_counter()
            try:
                _e, info = imgtrace.image_to_entities(data, height_mm=height)
            except ValueError as exc:
                print(f"{height:8.1f}  refused: {str(exc)[:60]}")
                continue
            whole = time.perf_counter() - t0
            print(f"{height:8.1f} {height / 3000:9.5f} {calls['loops']:6d} "
                  f"{calls['pts']:7d} {calls['t']:11.2f}s {whole:11.2f}s   "
                  f"({info['contours']} pieces, {info['holes']} holes)")
    finally:
        imgtrace._pull_apart = real


if __name__ == "__main__":
    main()
