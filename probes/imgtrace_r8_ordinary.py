"""ROUND EIGHT — the SAME question at the ordinary door, and one more.

`probes/imgtrace_r8_meet.py` shows that at the `settle` door a pair measuring
zero apart is an interior OVERLAP 16 times in 30, and all 16 build healthy.
`image_to_entities` carries the same `tight <= _MEET_MM` refusal, on traces
nobody rescaled. Round seven measured its cost as "one ordinary trace in 500,
which builds healthy at 608.568 mm3". This measures the rate AND the kind.

While the corpus is running it also asks the question `image_to_entities`
never asks: **does a polygon reach `sketch.py` crossing itself?**

`settle` re-proves simplicity after `_pull_apart` and says why: "the push is
not only a move: it inserts a vertex at each contact (`_split_at_feet`) and
rounds it onto the 0.001 mm grid, up to 0.0007 mm off the edge it split ...
and a loop `_uncross` had just proved simple came back crossing".
`image_to_entities` calls the same `_pull_apart` as its LAST geometric act and
then goes straight to `_poly_entity`. Nothing re-asks there.

MEASURED 2026-09-19 at 37eb290, two seeds of 600 ordinary traces each:

    seed 82026: 600 traces — 0 self-crossing polygons out, 0 MEET refusals
    seed 5150 : 600 traces — 0 self-crossing polygons out, 0 MEET refusals

So at the ORDINARY door the new refusal is rarer than round seven's "1 in
500" — 0 in 1200 here — and `image_to_entities` not re-proving simplicity
after its own `_pull_apart` cost nothing over 1200 traces. The cost of the
refusal is paid at the FIT door, where `settle` runs: see
`probes/imgtrace_r8_meet.py`.

Run:  C:/Python314/python.exe probes/imgtrace_r8_ordinary.py [n] [seed]
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
from imgtrace_r8_meet import zero_pairs                     # noqa: E402
from imgtrace_r8_settle import build                        # noqa: E402

CAUGHT: dict = {}
_REAL = imgtrace._worst_residual


def _spy(loops, stuck):
    CAUGHT["loops"] = loops
    CAUGHT["stuck"] = stuck
    return _REAL(loops, stuck)


imgtrace._worst_residual = _spy


def entities_anyway(data, height_mm):
    """image_to_entities, with its MEET refusal turned into a return value."""
    real = imgtrace._MEET_MM
    try:
        imgtrace._MEET_MM = -1.0          # nothing can be <= -1
        ents, info = imgtrace.image_to_entities(data, height_mm=height_mm)
    finally:
        imgtrace._MEET_MM = real
    return ents, info


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 20
    seed = int(args[1]) if len(args) > 1 else 8_2026
    rng = np.random.default_rng(seed)

    traces = refused = escaped = 0
    grid: dict = {}
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                CAUGHT.clear()
                try:
                    ents, info = entities_anyway(data, h_mm)
                except ValueError:
                    continue
                traces += 1
                # (a) did a self-crossing polygon get out?
                for e in ents:
                    if imgtrace._first_crossing(
                            [tuple(p) for p in e["points"]]) is not None:
                        escaped += 1
                        print(f"  ESCAPED self-crossing: {gname}{k} "
                              f"h={h_mm:g}  ({len(ents)} entities)")
                        break
                # (b) would the shipped MEET refusal have fired here?
                tight = _REAL(CAUGHT.get("loops", []), CAUGHT.get("stuck", []))
                if tight is None or tight > 1e-12:
                    continue
                refused += 1
                hits = zero_pairs(CAUGHT["loops"], CAUGHT["stuck"])
                kinds = {h[3] for h in hits}
                label = ("tangent" if "tangent" in kinds
                         else "cross" if kinds else "none")
                bad, vol = build(ents)
                grid[(label, bad is None)] = grid.get(
                    (label, bad is None), 0) + 1
                print(f"  REFUSED {gname}{k} h={h_mm:g}: {len(hits)} zero "
                      f"pair(s) {sorted(kinds) or ['-']} -> "
                      + (f"HEALTHY {vol:.3f} mm3" if bad is None
                         else str(bad)[:58]))

    print(f"\n{traces} ordinary traces, seed {seed}")
    print(f"  polygons that reached sketch.py CROSSING themselves : {escaped}")
    print(f"  traces the shipped MEET refusal turns away          : {refused}"
          + (f"  (1 in {traces // refused})" if refused else ""))
    for label in ("tangent", "cross", "none"):
        h = grid.get((label, True), 0)
        b = grid.get((label, False), 0)
        if h or b:
            print(f"    {label:8s}: healthy {h:3d}   broken {b:3d}")


if __name__ == "__main__":
    main()
