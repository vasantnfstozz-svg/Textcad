"""ROUND SEVEN — the fit's own rescale, AFTER every guarantee imgtrace makes.

`imgtrace.image_to_entities` ends with two promises, both bought with P0s:
every polygon is simple, and no two loops of the sketch come within 0.01 mm
of each other. Round six went to the trouble of putting the art-centring
shift ON the 0.001 mm grid precisely because re-rounding points onto a
SHIFTED grid can merge two of them and put a crossing back.

`studio._trace_fitted` then does this, outside imgtrace entirely:

    e["points"] = [[round(px * s, 3), round(py * s, 3)] for px, py in ...]

An arbitrary `s`, and a re-round onto the 0.001 mm grid. Every clearance the
push opened is multiplied by `s` — the hair is 0.01 mm, so at s = 0.05 it is
0.0005 mm and the grid closes it — and every point lands on a grid the loops
were never proved simple on.

`s` is called a "residual exact-fit rescale", but `_trace_fit_height`'s own
docstring says otherwise: when nothing tried fits, "one of them has to be
traced and then SHRUNK by `_trace_fitted`'s residual rescale".

This probe sweeps `s` over the entities of traces that really carry hair-wide
pairs, and measures, on the coordinates the sketch is handed:
  * the closest pair, before and after;
  * whether any polygon now crosses itself;
  * (with --health) what the kernel says about the 2 mm extrusion.

Run:  C:/Python314/python.exe probes/imgtrace_r7_rescale.py [n] [seed] [--health]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402

SCALES = (0.9, 0.5, 0.25, 0.1, 0.05, 0.02)


def rescale(ents, s):
    """exactly what studio._trace_fitted does with its residual `s`"""
    out = []
    for e in ents:
        out.append({**e, "x": round(e["x"] * s, 3),
                    "y": round(e["y"] * s, 3),
                    "points": [[round(px * s, 3), round(py * s, 3)]
                               for px, py in e["points"]]})
    return out


def rings_of(ents):
    return [np.asarray([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                       float) for e in ents]


def closest(ents):
    rs = rings_of(ents)
    best = float("inf")
    for i in range(len(rs)):
        if len(rs[i]) < 2:
            return 0.0
        for j in range(i + 1, len(rs)):
            d1, _f = imgtrace._nearest_on_ring(rs[i], rs[j])
            d2, _f = imgtrace._nearest_on_ring(rs[j], rs[i])
            best = min(best, float(d1.min()), float(d2.min()))
    return best


def crosses(ents):
    return sum(1 for e in ents
               if imgtrace._first_crossing([tuple(p) for p in e["points"]])
               is not None)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 12
    seed = int(args[1]) if len(args) > 1 else 7_2026
    want_health = "--health" in sys.argv
    build = None
    if want_health:
        import inspector
        import sketch as sk

        def build(ents):
            try:
                solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
            except Exception as exc:                        # noqa: BLE001
                return f"SKETCH FAIL {type(exc).__name__}", None
            bad = inspector.health(solid)
            return (bad[0] if bad else None), float(solid.volume)

    rng = np.random.default_rng(seed)
    traces = hit = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data,
                                                          height_mm=h_mm)
                except ValueError:
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: "
                          f"{type(exc).__name__}: {str(exc)[:60]}")
                    continue
                traces += 1
                if len(ents) < 2:
                    continue
                g0, x0 = closest(ents), crosses(ents)
                for s in SCALES:
                    sc = rescale(ents, s)
                    g, x = closest(sc), crosses(sc)
                    if g > 0 and not x:
                        continue
                    hit += 1
                    line = (f"  {gname}{k} h={h_mm:g} s={s:g}: closest "
                            f"{g0:.6f} -> {g:.9f} mm, self-crossing "
                            f"{x0} -> {x} of {len(ents)}")
                    if build:
                        bad0, vol0 = build(ents)
                        bad, vol = build(sc)
                        line += (f"  |  {bad0 or 'healthy'} {vol0} -> "
                                 f"{bad or 'healthy'} {vol}")
                    print(line)
                    break
    print(f"\n{traces} traces, {hit} of them pinched or self-crossing after "
          f"a rescale in {SCALES}")


if __name__ == "__main__":
    main()
