"""ROUND EIGHT — what `settle` costs, and what asking "is this pair an
OVERLAP?" would cost on top of it.

`settle` runs `_uncross` and `_pull_apart` up to three times, on art that has
just been shrunk — which splits loops and so makes MORE pairs. Round six
measured `_pull_apart` at 86 s on pathological art (200 loops of 400 points),
and round seven put `min_channel_mm` behind a bound precisely because one
trace held a server thread for 119.56 s. Nothing has measured `settle`.

The overlap test is the fix `probes/imgtrace_r8_meet.py` argues for: a pair
measuring zero apart is refused today whether it is a PINCH or an ordinary
interior OVERLAP, and 16 of 30 refusals are overlaps that all build healthy.
The test has to be cheap enough to run inside `_worst_residual`, which on the
worst corpus case is asked about 161 pairs.

MEASURED 2026-09-19 at 37eb290, `imgtrace_r8_cost.py 5 82026`:

    360 settle runs
      slowest settle         : 22.408 s  (rings1 h=9.5 s=0.02, 16 entities)
      most pairs given up on : 301       (rings2 h=9.5 s=0.02)
      slowest overlap pass   : 0.122 s   (that same trace, 301 stuck pairs)

The overlap test is cheap enough to live inside `_worst_residual` — an eighth
of a second on the worst trace in the corpus, and it is asked only of pairs
that would otherwise trip the refusal. `settle` ITSELF is the expensive thing:
22.4 s of a server thread for one fitted trace, on art shrunk to a fiftieth.
Not a defect, but the number to beat if the fit ever traces at the final size
instead of tracing big and shrinking.

Run:  C:/Python314/python.exe probes/imgtrace_r8_cost.py [n] [seed]
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402
from imgtrace_r7_rescale import rescale                     # noqa: E402
from imgtrace_r8_meet import overlaps                       # noqa: E402

SCALES = (0.5, 0.1, 0.02)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 6
    seed = int(args[1]) if len(args) > 1 else 8_2026
    rng = np.random.default_rng(seed)

    worst_settle = (0.0, "")
    worst_pairs = (0, "")
    worst_ov = (0.0, "")
    runs = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data, height_mm=h_mm)
                except ValueError:
                    continue
                if len(ents) < 2:
                    continue
                for s in SCALES:
                    sc = rescale(ents, s)
                    t0 = time.perf_counter()
                    try:
                        imgtrace.settle(sc)
                    except ValueError:
                        pass
                    dt = time.perf_counter() - t0
                    runs += 1
                    tag = f"{gname}{k} h={h_mm:g} s={s:g} ({len(sc)} ents)"
                    if dt > worst_settle[0]:
                        worst_settle = (dt, tag)
                    # ...and the cost of asking every pair `_pull_apart` gave
                    # up on whether it is an overlap
                    flat = [imgtrace._round_pts(
                        [(float(e["x"] + px), float(e["y"] + py))
                         for px, py in e["points"]]) for e in sc]
                    split = []
                    for pts in flat:
                        split += [p for p in imgtrace._uncross(pts)
                                  if len(p) >= 3
                                  and abs(imgtrace._area2(p)) > 1e-9]
                    st: list = []
                    apart = imgtrace._pull_apart(split, report=st)
                    if len(st) > worst_pairs[0]:
                        worst_pairs = (len(st), tag)
                    rings = {}
                    t0 = time.perf_counter()
                    for i, j, _d in st:
                        for q in (i, j):
                            if q not in rings:
                                rings[q] = np.asarray(
                                    imgtrace._round_pts(apart[q]), float)
                        a, b = rings[i], rings[j]
                        if len(a) >= 3 and len(b) >= 3:
                            overlaps(a, b) or overlaps(b, a)
                    dt = time.perf_counter() - t0
                    if dt > worst_ov[0]:
                        worst_ov = (dt, f"{tag}, {len(st)} stuck pairs")
    print(f"{runs} settle runs, seed {seed}")
    print(f"  slowest settle          : {worst_settle[0]:.3f} s  "
          f"({worst_settle[1]})")
    print(f"  most pairs given up on  : {worst_pairs[0]}  ({worst_pairs[1]})")
    print(f"  slowest overlap pass    : {worst_ov[0]:.3f} s  ({worst_ov[1]})")


if __name__ == "__main__":
    main()
