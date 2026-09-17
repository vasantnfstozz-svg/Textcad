"""REVIEW-QUEUE section 9 ROUND FIVE — does the guard keep its OWN promise,
and is the fit height's measurement budget really five?

Two counts, both cheap, both over the corpora the earlier rounds used.

1. `_pull_apart` runs at most four rounds and stops. If a round ran out with
   work still to do — or if `_hair_cluster` refused a vertex because the whole
   loop is sub-hair — the guard returns loops that are still inside the hair
   BY ITS OWN one-way test. This counts those.

2. `studio._trace_fit_height` claims "a choice over a finite set" of at most
   `rounds` heights. This counts the `artwork_aspect` calls it really makes,
   on art built to walk downhill for ever.

Run:  C:/Python314/python.exe probes/imgtrace_r5_contract.py [n]
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
import studio                                               # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402


def one_way_min(loops):
    """the smallest distance the guard's OWN test measures, after it ran"""
    arr = [np.asarray(p, float) for p in loops]
    size = [abs(imgtrace._area2(p)) for p in loops]
    best = float("inf")
    for i in range(len(arr)):
        for j in range(len(arr)):
            if i == j or size[j] < size[i]:
                continue
            d, _f = imgtrace._nearest_on_ring(arr[i], arr[j])
            best = min(best, float(d.min()))
    return best


def contract(n, seed):
    real = imgtrace._pull_apart
    stats = {"calls": 0, "left": 0, "worst": float("inf")}

    def watched(loops, gap=imgtrace._HAIR_MM):
        out = real(loops, gap)
        if len(out) > 1:
            stats["calls"] += 1
            m = one_way_min(out)
            if m < gap * (1 - 1e-9):
                stats["left"] += 1
                stats["worst"] = min(stats["worst"], m)
        return out

    imgtrace._pull_apart = watched
    rng = np.random.default_rng(seed)
    try:
        for _k in range(n):
            for _gname, gen in GENS:
                data = png(gen(rng))
                for h_mm in HEIGHTS:
                    try:
                        imgtrace.image_to_entities(data, height_mm=h_mm)
                    except ValueError:
                        pass
                    except Exception as exc:                # noqa: BLE001
                        print(f"  TRACEBACK {type(exc).__name__}: "
                              f"{str(exc)[:60]}")
    finally:
        imgtrace._pull_apart = real
    print(f"{stats['calls']} traces with 2+ loops")
    print(f"  still inside the hair by the guard's OWN test: {stats['left']}")
    if stats["left"]:
        print(f"  worst one-way gap left: {stats['worst']:.9f} mm")


def downhill(step=0.62, n=9):
    """a bar with a ladder of ornaments above it, each smaller than the last:
    every height the fit tries drops the next rung, so the aspect keeps
    changing and the iteration never settles"""
    m = np.zeros((1400, 1200), np.uint8)
    cv2.rectangle(m, (60, 1200), (1139, 1339), 1, -1)
    y, size = 1100, 150.0
    for _ in range(n):
        s = max(2, int(size))
        cv2.rectangle(m, (600 - s // 2, y - s), (600 + s // 2, y), 1, -1)
        y -= s + 12
        size *= step
    return m


def budget():
    real = imgtrace.artwork_aspect
    seen = {"n": 0, "h": []}

    def counted(data, height_mm=50.0):
        seen["n"] += 1
        seen["h"].append(round(float(height_mm), 4))
        return real(data, height_mm)

    imgtrace.artwork_aspect = counted
    try:
        data = png(downhill())
        for m_w, m_h in ((12.0, 14.0), (14.0, 12.0), (6.0, 90.0),
                         (90.0, 6.0), (3.0, 3.0), (400.0, 400.0),
                         (1.0, 2000.0)):
            seen["n"], seen["h"] = 0, []
            h, rot = studio._trace_fit_height(data, m_w, m_h)
            print(f"  box {m_w:7.1f} x {m_h:7.1f} -> h={h:8.3f} "
                  f"rot={str(rot):5s}  {seen['n']} aspect calls at "
                  f"{seen['h']}")
    finally:
        imgtrace.artwork_aspect = real


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 60
    print("--- 2. the fit height's measurement budget ---")
    budget()
    print("\n--- 1. the guard's own contract, after it ran ---")
    contract(n, 5_2026)


if __name__ == "__main__":
    main()
