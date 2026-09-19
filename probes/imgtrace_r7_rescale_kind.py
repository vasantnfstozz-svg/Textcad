"""ROUND SEVEN — WHAT the fit's rescale breaks: a duplicate point, or a real
crossing, or a pinch between two loops.

`probes/imgtrace_r7_rescale.py` counts 129 of 288 traces ending pinched or
self-crossing after `studio._trace_fitted`'s residual rescale. This says which
of the three it is, case by case, because they are not the same finding:

  * a DUPLICATE point (two grid points merged into one) leaves a zero-length
    edge — `_round_pts` drops it, but studio never calls `_round_pts` after
    its rescale, so the polygon reaches `sketch.py` carrying it;
  * a REAL crossing is the state `_uncross` exists to forbid;
  * a PINCH (two loops at exactly 0.000000000 mm) is the open-shell failure
    of rounds one and five.

Run:  C:/Python314/python.exe probes/imgtrace_r7_rescale_kind.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import GENS, png                    # noqa: E402
from imgtrace_r7_rescale import SCALES, closest, rescale    # noqa: E402

HEIGHTS = (9.5, 12.0, 17.3, 25.0, 33.7, 40.0)


def kind_of(e):
    """'clean', 'duplicate' (the crossing goes away with _round_pts) or
    'crossing' (it does not)"""
    pts = [tuple(p) for p in e["points"]]
    if imgtrace._first_crossing(pts) is None:
        return "clean"
    r = imgtrace._round_pts(pts)
    if len(r) < 3 or imgtrace._first_crossing(r) is not None:
        return "crossing"
    return "duplicate"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 12
    seed = int(args[1]) if len(args) > 1 else 7_2026
    rng = np.random.default_rng(seed)
    tally = {"duplicate": 0, "crossing": 0}
    pinch = {s: 0 for s in SCALES}
    seen = {s: 0 for s in SCALES}
    refused = {s: 0 for s in SCALES}
    worst_s_pinch = 0.0
    worst_s_cross = 0.0
    traces = 0
    for k in range(n):
        for _g, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data,
                                                          height_mm=h_mm)
                except ValueError:
                    continue
                except Exception:                           # noqa: BLE001
                    continue
                traces += 1
                if len(ents) < 2:
                    continue
                for s in SCALES:
                    seen[s] += 1
                    sc = rescale(ents, s)
                    if "--settled" in sys.argv:
                        try:
                            sc, _n = imgtrace.settle(sc)
                        except ValueError:
                            refused[s] = refused.get(s, 0) + 1
                            continue
                    kinds = [kind_of(e) for e in sc]
                    if closest(sc) <= 0.0:
                        pinch[s] += 1
                        worst_s_pinch = max(worst_s_pinch, s)
                    for kk in kinds:
                        if kk != "clean":
                            tally[kk] += 1
                            if kk == "crossing":
                                worst_s_cross = max(worst_s_cross, s)
    print(f"\n{traces} traces, each rescaled at {SCALES}")
    print(f"  polygons carrying a DUPLICATE point : {tally['duplicate']}")
    print(f"  polygons that really CROSS          : {tally['crossing']}")
    print(f"  biggest s that still makes a crossing: {worst_s_cross:g}")
    print(f"  biggest s that still makes a PINCH   : {worst_s_pinch:g}")
    for s in SCALES:
        print(f"    s={s:<5g} pinched {pinch[s]:4d} of {seen[s]}, "
              f"refused {refused[s]}")


if __name__ == "__main__":
    main()
