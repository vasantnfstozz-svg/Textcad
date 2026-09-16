"""probes/imgtrace_fuzz_probe.py - REVIEW-QUEUE section 9.

Random artwork through image_to_entities at many target heights, auditing
every entity for what sketch.py would refuse: <3 points, duplicate points,
self-intersection, sub-0.1mm edges - and then BUILDING the sketch to see
whether the kernel agrees.

Run: C:\\Python314\\python.exe probes/imgtrace_fuzz_probe.py [n]
"""
from __future__ import annotations

import os
import random
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import imgtrace  # noqa: E402
import inspector  # noqa: E402
import sketch as sk  # noqa: E402


def crossings(p, touch_tol=0.0):
    """proper crossings AND touches (a vertex landing on a far segment)"""
    import itertools
    n = len(p)
    hits = []
    for i, j in itertools.combinations(range(n), 2):
        if j == i + 1 or (i == 0 and j == n - 1):
            continue
        a, b = np.array(p[i], float), np.array(p[(i + 1) % n], float)
        c, d = np.array(p[j], float), np.array(p[(j + 1) % n], float)
        r, s = b - a, d - c
        den = r[0] * s[1] - r[1] * s[0]
        if abs(den) < 1e-15:
            continue
        t = ((c - a)[0] * s[1] - (c - a)[1] * s[0]) / den
        u = ((c - a)[0] * r[1] - (c - a)[1] * r[0]) / den
        if -touch_tol <= t <= 1 + touch_tol and -touch_tol <= u <= 1 + touch_tol:
            hits.append((i, j, tuple(np.round(a + t * r, 4))))
    return hits


def audit(ents):
    out = []
    for k, e in enumerate(ents):
        p = [tuple(q) for q in e["points"]]
        n = len(p)
        if n < 3:
            out.append(("few", k, n))
            continue
        if any(p[i] == p[(i + 1) % n] for i in range(n)):
            out.append(("dup", k, 0))
        if len(set(p)) != n:
            out.append(("pinch", k, n - len(set(p))))
        mn = min(np.hypot(p[(i + 1) % n][0] - p[i][0],
                          p[(i + 1) % n][1] - p[i][1]) for i in range(n))
        if mn < 0.1:
            out.append(("short", k, round(mn, 4)))
        hits = len(crossings(p))
        if hits:
            out.append(("cross", k, hits))
    return out


def random_art(rng, size=700):
    img = np.zeros((size, size, 4), np.uint8)
    for _ in range(rng.randint(1, 5)):
        kind = rng.choice(["poly", "circ", "rect", "star", "text"])
        col = (0, 0, 0, 255)
        if kind == "poly":
            n = rng.randint(3, 9)
            pts = [[rng.randint(40, size - 40), rng.randint(40, size - 40)]
                   for _ in range(n)]
            cv2.fillPoly(img, [np.array(pts, np.int32)], col)
        elif kind == "circ":
            cv2.circle(img, (rng.randint(80, size - 80), rng.randint(80, size - 80)),
                       rng.randint(20, 220), col, -1)
        elif kind == "rect":
            x0, y0 = rng.randint(20, size - 120), rng.randint(20, size - 120)
            cv2.rectangle(img, (x0, y0), (x0 + rng.randint(10, 300),
                                          y0 + rng.randint(10, 300)), col, -1)
        elif kind == "star":
            cx, cy = rng.randint(150, size - 150), rng.randint(150, size - 150)
            k = rng.randint(4, 9)
            sp = []
            for i in range(2 * k):
                r = rng.randint(90, 160) if i % 2 == 0 else rng.randint(8, 50)
                a = i * np.pi / k
                sp.append([cx + r * np.cos(a), cy + r * np.sin(a)])
            cv2.fillPoly(img, [np.array(sp, np.int32)], col)
        else:
            cv2.putText(img, rng.choice(["Rocky", "AQ", "Bg8", "W@"]),
                        (rng.randint(20, 200), rng.randint(200, size - 40)),
                        cv2.FONT_HERSHEY_SIMPLEX, rng.uniform(2, 7), col,
                        rng.randint(3, 22))
    for _ in range(rng.randint(0, 3)):      # punch holes
        cv2.circle(img, (rng.randint(80, size - 80), rng.randint(80, size - 80)),
                   rng.randint(10, 90), (0, 0, 0, 0), -1)
    ok, b = cv2.imencode(".png", img)
    return b.tobytes()


def main(n=60):
    rng = random.Random(7)
    tally = {}
    crashes, builds = [], 0
    for i in range(n):
        data = random_art(rng)
        h = rng.choice([2.0, 3.0, 5.0, 12.0, 25.0, 50.0, 120.0])
        try:
            ents, info = imgtrace.image_to_entities(data, height_mm=h)
        except ValueError as e:
            tally.setdefault("refused: " + str(e)[:44], 0)
            tally["refused: " + str(e)[:44]] += 1
            continue
        except Exception as e:                       # noqa: BLE001
            crashes.append((i, h, type(e).__name__, str(e)[:120]))
            continue
        for kind, k, v in audit(ents):
            tally.setdefault(kind, 0)
            tally[kind] += 1
            if kind in ("cross", "dup", "few", "pinch"):
                print(f"  #{i} h={h} {kind} ent{k} {v}  {info}")
        try:
            face = sk.make_sketch("XY", 0, ents)
            solid = sk.extrude_sketch(face, 2.0)
            hp = inspector.health(solid)
            builds += 1
            if hp:
                print(f"  #{i} h={h} BUILT UNHEALTHY {hp}  {info}")
        except Exception as e:                       # noqa: BLE001
            print(f"  #{i} h={h} BUILD FAILED {type(e).__name__}: {str(e)[:110]}")
    print("tally:", tally)
    print("crashes (non-ValueError):", crashes)
    print(f"built {builds}/{n}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
