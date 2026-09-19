"""ROUND EIGHT — what a pair at ZERO really is: a pinch, or an OVERLAP?

Round seven made a dormant refusal live. `_worst_residual` <= `_MEET_MM`
(1e-12 mm) now refuses the trace, at both doors — `image_to_entities` and the
new `settle`. The case for it: rounds one, three and five each measured two
loops sharing a point building a watertight-looking OPEN SHELL, the banned
failure. The cost round seven measured: one ordinary trace in 500.

`probes/imgtrace_r8_settle.py` measures the cost at the OTHER door and it is
not one in 500: 30 of 864 rescaled traces are refused and **26 of the 30 build
HEALTHY**. This probe asks why.

`_worst_residual` measures a DISTANCE, and two loops measure zero apart in two
completely different situations:

  * they TOUCH at a point, interiors disjoint — the pinch, an open shell;
  * their interiors OVERLAP — the boundaries cross transversally, which is an
    ordinary union the kernel is happy with. Round seven's own
    `_split_at_feet` docstring says so: "either cross transversally — which is
    an overlap, and an overlap is a union the kernel is happy with".

Round seven cleared overlaps as a pre-existing state ("`_uncross` returned 0
interior-overlapping pairs in 600 traces") — on traces at their OWN size. The
rescale is what makes them: two loops 0.0004 mm apart, multiplied by s = 0.02
and re-rounded onto the 0.001 mm grid, land ON each other.

So this classifies every stuck pair with `imgtrace_r5_mirror.contact_kind`
(tangent vs cross), and puts every trace to the kernel, to see whether that
classification PREDICTS the health. If it does, the refusal has a rule that
costs nothing.

MEASURED 2026-09-19 at 37eb290, two seeds, 1728 settle runs in all:

    seed 82026 (30 refusals)      seed 5150 (37 refusals)
      tangent: healthy 10 broken 4   tangent: healthy 10 broken 5
      cross  : healthy 16 broken 0   cross  : healthy 21 broken 0

    TOTAL   tangent (a real point contact): 20 healthy, 9 BROKEN
            cross   (the interiors OVERLAP): 37 healthy, 0 broken

**Every one of the 37 overlap-only refusals builds a healthy solid, and every
one of the 9 open shells carries a real point contact.** The contact kind
predicts the kernel; the DISTANCE does not. So the refusal as shipped turns
away 37 traces for a state that is an ordinary union, and the rule that costs
nothing is: refuse a TANGENT contact, allow an OVERLAP.

Run:  C:/Python314/python.exe probes/imgtrace_r8_meet.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import cv2                                                  # noqa: E402
import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402
from imgtrace_r7_rescale import rescale                     # noqa: E402
from imgtrace_r8_settle import build, settle_open            # noqa: E402

SCALES = (0.9, 0.5, 0.25, 0.1, 0.05, 0.02)


def overlaps(a, b) -> bool:
    """True when the interiors of two simple loops really overlap — some
    MIDPOINT of a's edges is strictly inside b and some is strictly outside,
    so the two boundaries cross transversally.

    Midpoints, not vertices: a contact puts a VERTEX of one loop exactly on
    the other's outline, where `pointPolygonTest` answers 0 and says nothing.
    Nesting (every midpoint inside) is NOT an overlap for this question — a
    hole tangent to the inside of its outer is a pinch like any other.
    """
    poly = np.asarray(b, np.float32)
    mid = (np.asarray(a, float) + np.roll(np.asarray(a, float), -1, 0)) / 2.0
    ins = out = False
    for p in mid:
        v = cv2.pointPolygonTest(poly, (float(p[0]), float(p[1])), False)
        if v > 0:
            ins = True
        elif v < 0:
            out = True
        if ins and out:
            return True
    return False


def zero_pairs(loops, stuck):
    """the pairs `_worst_residual` reads as at-or-under `_MEET_MM`, with the
    contact classified"""
    rings: dict = {}
    hits = []
    for i, j, _d in stuck:
        for k in (i, j):
            if k not in rings:
                p = imgtrace._round_pts(loops[k])
                rings[k] = np.asarray(p, float) if len(p) >= 3 else None
        a, b = rings[i], rings[j]
        if a is None or b is None:
            continue
        d1, _f = imgtrace._nearest_on_ring(a, b)
        d2, _f = imgtrace._nearest_on_ring(b, a)
        g = min(float(d1.min()), float(d2.min()))
        if g <= imgtrace._MEET_MM:
            hits.append((i, j, g, "cross" if (overlaps(a, b) or overlaps(b, a))
                         else "tangent"))
    return hits


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 6
    seed = int(args[1]) if len(args) > 1 else 8_2026
    rng = np.random.default_rng(seed)

    rows = []
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
                    out, why, _u, tight = settle_open(sc)
                    if why != "MEET" or out is None:
                        continue
                    # re-derive the stuck pairs on the same coordinates
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
                    hits = zero_pairs(apart, st)
                    kinds = {h[3] for h in hits}
                    bad, vol = build(out)
                    rows.append((gname, k, h_mm, s, tight, hits, kinds,
                                 bad, vol))

    print(f"{len(rows)} MEET refusals, seed {seed}\n")
    grid: dict = {}
    for gname, k, h_mm, s, tight, hits, kinds, bad, vol in rows:
        label = ("tangent" if "tangent" in kinds else
                 "cross" if kinds else "none")
        ok = bad is None
        grid[(label, ok)] = grid.get((label, ok), 0) + 1
        print(f"  {gname}{k} h={h_mm:g} s={s:g}: {len(hits)} zero pair(s) "
              f"{sorted(kinds) or ['-']}  -> "
              + ("HEALTHY " + (f"{vol:.3f} mm3" if vol else "")
                 if ok else str(bad)[:58]))
    print("\n  contact kind  x  what the kernel says")
    for label in ("tangent", "cross", "none"):
        h = grid.get((label, True), 0)
        b = grid.get((label, False), 0)
        if h or b:
            print(f"    {label:8s}: healthy {h:3d}   broken {b:3d}")


if __name__ == "__main__":
    main()
