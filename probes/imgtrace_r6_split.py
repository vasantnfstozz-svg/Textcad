"""ROUND SIX — `_split_at_feet` on degenerate input.

Round two added it: `pts` with a vertex inserted wherever a vertex of `ring`
comes within `gap` of it, "at the point OF `pts` nearest that vertex, which
lies on the edge it splits, so not one shape changes". This probe attacks
that promise:

  1. a foot that lands ON an existing vertex
  2. a foot at an edge's exact END
  3. TWO feet on one edge (and two feet at the SAME point)
  4. a foot on a ZERO-LENGTH edge
  5. a triangle loop (three points, one inserted)
  6. does an insertion make the loop cross ITSELF?
  7. does an insertion make the NEXT round's room test (`_hair_cluster`)
     refuse a push it allowed before?

For each: the point count, the worst distance from an inserted point to the
edge it was supposed to lie on, and whether `_first_crossing` still says the
loop is simple.

Run:  C:/Python314/python.exe probes/imgtrace_r6_split.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402

GAP = imgtrace._HAIR_MM


def off_outline(before, after):
    """the worst distance from a point of `after` to the OUTLINE of `before` —
    0 means every inserted point really lies on the shape it split"""
    d, _f = imgtrace._nearest_on_ring(np.asarray(after, float),
                                      np.asarray(before, float))
    return float(d.max())


def area(p):
    return abs(imgtrace._area2([tuple(q) for q in p])) / 2.0


def case(name, pts, ring):
    a = np.asarray(pts, float)
    r = np.asarray(ring, float)
    out = imgtrace._split_at_feet(a, r, GAP)
    simple = imgtrace._first_crossing([tuple(p) for p in out]) is None
    print(f"  {name:<44} {len(a):>3} -> {len(out):<3} pts   "
          f"off-outline {off_outline(a, out):.9f}   area "
          f"{area(a):.9f} -> {area(out):.9f}   "
          f"{'simple' if simple else 'CROSSES ITSELF'}")
    return out


def main():
    bar = [(0.0, 0.0), (10.0, 0.0), (10.0, 2.0), (0.0, 2.0)]

    print("1 a foot that lands ON an existing vertex")
    case("ring vertex over the bar's corner", bar,
         [(10.0, 2.004), (12.0, 5.0), (8.0, 5.0)])

    print("\n2 a foot at an edge's exact END")
    case("ring vertex over (10, 0), the edge end", bar,
         [(10.0, -0.004), (12.0, -5.0), (8.0, -5.0)])

    print("\n3 TWO feet on one edge")
    case("two ring vertices over the top edge", bar,
         [(3.0, 2.004), (7.0, 2.004), (7.0, 6.0), (3.0, 6.0)])
    case("two ring vertices at the SAME point", bar,
         [(5.0, 2.004), (5.0, 2.004), (7.0, 6.0), (3.0, 6.0)])

    print("\n4 a foot on a ZERO-LENGTH edge")
    case("the bar with a doubled corner", bar[:2] + [(10.0, 0.0)] + bar[2:],
         [(10.0, -0.004), (12.0, -5.0), (8.0, -5.0)])

    print("\n5 a TRIANGLE loop")
    case("triangle, foot in the middle of its base",
         [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0)],
         [(5.0, -0.004), (8.0, -5.0), (2.0, -5.0)])

    print("\n6 a foot on a loop that already runs close to itself")
    hook = [(0.0, 0.0), (10.0, 0.0), (10.0, 0.004), (0.2, 0.004),
            (0.2, 2.0), (0.0, 2.0)]
    case("a 0.004 mm hook", hook,
         [(5.0, -0.004), (9.0, -5.0), (1.0, -5.0)])

    print("\n7 does the insertion change what the NEXT round may push?")
    # `_hair_cluster` refuses a push - returns None - only when EVERY edge of
    # the loop is shorter than the span. An insertion shortens the edge it
    # SPLITS; an edge long enough to stop the walk is still there unless every
    # long edge is split, and a foot is only put where the other loop really
    # comes within the hair. Measured on a small square with feet driven into
    # one, two, three and all four of its edges.
    side = 0.05
    sq = [(0.0, 0.0), (side, 0.0), (side, side), (0.0, side)]
    span = 4.0 * GAP
    far = [(-5.0, -5.0), (5.0, -5.0), (5.0, 5.0)]
    for k in range(5):
        feet = [f for f, want in (((side / 2, -0.004), k > 0),
                                  ((side + 0.004, side / 2), k > 1),
                                  ((side / 2, side + 0.004), k > 2),
                                  ((-0.004, side / 2), k > 3)) if want]
        out = imgtrace._split_at_feet(np.asarray(sq, float),
                                      np.array(feet + far, float), GAP)
        cl = imgtrace._hair_cluster(out, 0, span)
        edges = np.hypot(*(np.roll(out, -1, axis=0) - out).T)
        room = 'REFUSES' if cl is None else f'{len(cl)} pts'
        print(f'  {k} feet: {len(sq)} -> {len(out)} pts, shortest edge '
              f'{float(edges.min()):.6f} (span {span:.6f}), '
              f'_hair_cluster -> {room}')


if __name__ == '__main__':
    main()
