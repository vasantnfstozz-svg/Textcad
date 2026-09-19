"""ROUND SIX — can a REAL picture make `_pull_apart` push a loop through
itself?

`probes/imgtrace_r6_self.py` shows the shape that does it: a piece of outline
whose own far side is within the 0.01 mm hair, with another loop within the
hair on the OTHER side. `_hair_cluster` only looks along the loop's index
order, so the far side — half an outline away — is invisible, and the vertex
walks through it.

In a picture that is: a fine comb or hatch, at a scale where one PIXEL is
under 0.01 mm (a 1600 px artwork traced 10 mm tall is 0.00625 mm/px), so the
teeth are hair-thin walls and the neighbouring loops `_uncross` makes out of
them are a hair apart.

Every trace is checked three ways:
  * `_first_crossing` on each entity as `sketch.py` receives it — `_uncross`
    promises None;
  * the same trace with `_pull_apart` turned off, to prove which pass made it;
  * `inspector.health` of the 2 mm extrusion.

Run:  C:/Python314/python.exe probes/imgtrace_r6_reach.py [n] [seed]
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
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402
from imgtrace_r5_mirror import png                          # noqa: E402

# 1 px must be under the 0.01 mm hair: 1600 px of artwork at these heights is
# 0.005-0.0125 mm/px
HEIGHTS = (6.0, 8.0, 10.0, 13.0, 16.0)


def comb(rng):
    """a solid bar with 1-2 px teeth — round one's own pathological outline,
    at a scale where a tooth is thinner than the hair"""
    m = np.zeros((1600, 1200), np.uint8)
    cv2.rectangle(m, (100, 1200), (1100, 1500), 1, -1)
    x = 120
    while x < 1090:
        w = int(rng.integers(1, 3))
        cv2.rectangle(m, (x, int(rng.integers(200, 1000))),
                      (x + w, 1210), 1, -1)
        x += w + int(rng.integers(1, 4))
    return m


def serpentine(rng):
    """a ribbon folded back on itself — 1-3 px runs with 1-3 px slots"""
    m = np.zeros((1600, 1200), np.uint8)
    y = 120
    left = True
    t = int(rng.integers(1, 4))
    while y < 1450:
        g = int(rng.integers(1, 4))
        cv2.rectangle(m, (120, y), (1080, y + t), 1, -1)
        cap = (1080 - t, 1080) if left else (120, 120 + t)
        cv2.rectangle(m, (cap[0], y), (cap[1], y + t + g), 1, -1)
        left = not left
        y += t + g
    cv2.rectangle(m, (60, 1460), (1140, 1540), 1, -1)   # a body to anchor it
    cv2.rectangle(m, (60, 1460), (140, 1540), 1, -1)
    return m


def hatch(rng):
    """cross hatching: 1-2 px lines both ways over a solid pad"""
    m = np.zeros((1600, 1200), np.uint8)
    cv2.rectangle(m, (80, 80), (1120, 1520), 1, -1)
    step = int(rng.integers(3, 7))
    w = int(rng.integers(1, 3))
    for x in range(140, 1080, step):
        cv2.rectangle(m, (x, 120), (x + w, 1480), 0, -1)
    for y in range(140, 1480, step * 2):
        cv2.rectangle(m, (120, y), (1080, y + w), 0, -1)
    return m


def spikes(rng):
    """a disc with hair-thin spokes — round four's pinch family at 4x the
    resolution"""
    m = np.zeros((1600, 1600), np.uint8)
    cv2.circle(m, (800, 800), int(rng.integers(500, 700)), 1, 120)
    for _ in range(int(rng.integers(6, 18))):
        a = float(rng.random() * 6.283)
        cv2.line(m, (800, 800),
                 (int(800 + 1400 * np.cos(a)), int(800 + 1400 * np.sin(a))),
                 1, int(rng.integers(1, 3)))
    return m


GENS = [("comb", comb), ("serp", serpentine), ("hatch", hatch),
        ("spikes", spikes)]


def no_push(data, h):
    real = imgtrace._pull_apart
    imgtrace._pull_apart = lambda loops, gap=imgtrace._HAIR_MM: loops
    try:
        return imgtrace.image_to_entities(data, height_mm=h)[0]
    finally:
        imgtrace._pull_apart = real


def crossings(ents):
    out = []
    for n, e in enumerate(ents):
        hit = imgtrace._first_crossing([tuple(p) for p in e["points"]])
        if hit is not None:
            out.append((n, hit[0], hit[1]))
    return out


def build(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:60]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 6
    seed = int(args[1]) if len(args) > 1 else 6_2026
    rng = np.random.default_rng(seed)
    traces = crossed = crossed_by_push = unhealthy = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data, height_mm=h_mm)
                except ValueError:
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k} h={h_mm:g}: "
                          f"{type(exc).__name__}: {str(exc)[:70]}")
                    continue
                traces += 1
                bad_ents = crossings(ents)
                if not bad_ents:
                    continue
                crossed += 1
                was = crossings(no_push(data, h_mm))
                by_push = not was
                crossed_by_push += by_push
                bad, vol = build(ents)
                if bad:
                    unhealthy += 1
                print(f"  {'PUSH-MADE ' if by_push else ''}SELF-CROSS "
                      f"{gname}{k} h={h_mm:g}: {len(ents)} loops, "
                      f"{len(bad_ents)} crossing {bad_ents[:3]} "
                      f"(without the push: {len(was)}) -> "
                      f"{bad or 'healthy'} vol {vol}")
                with open(os.path.join(HERE, f"_r6_cross_{gname}{k}.png"),
                          "wb") as fh:
                    fh.write(data)
    print(f"\n{traces} traces")
    print(f"  traces handing sketch.py a SELF-CROSSING polygon : {crossed}")
    print(f"  ...that were simple until `_pull_apart` ran      : "
          f"{crossed_by_push}")
    print(f"  unhealthy solids                                 : {unhealthy}")


if __name__ == "__main__":
    main()
