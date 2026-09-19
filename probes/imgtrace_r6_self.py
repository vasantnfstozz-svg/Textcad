"""ROUND SIX — the question no round has asked: does the push make a loop
cross ITSELF?

`_uncross` proves every loop simple. `_pull_apart` then MOVES points, by up to
a hair, and nothing re-asks. Its only room test, `_hair_cluster`, looks at the
edges JOINED to the vertex — it says nothing about a part of the SAME outline
that lies a few microns away with half the loop in between.

A ribbon folded back on itself is exactly that: the slot between two runs of
the ribbon is bounded by two NON-adjacent edges, and a vertex on the outside
of a run has the slot on its other side. Push that vertex away from a
neighbouring loop and it walks straight through the ribbon's own far wall —
the state `_uncross` exists to forbid, handed to `sketch.py`.

Run:  C:/Python314/python.exe probes/imgtrace_r6_self.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402
from imgtrace_r6_truth import self_min                      # noqa: E402


def serpentine(t=0.005, gap=0.005):
    """a ribbon `t` thick folded back on itself with a `gap` slot between the
    two runs — one simple polygon, 8 points"""
    y1, y2, y3 = t, t + gap, t + gap + t
    return [(0.0, 0.0), (1.0, 0.0), (1.0, y3), (0.05, y3), (0.05, y2),
            (0.995, y2), (0.995, y1), (0.0, y1)]


def below(d=0.0045):
    """a BIGGER loop a hair under the ribbon's bottom edge"""
    return [(0.2, -5.0), (5.0, -5.0), (5.0, -d), (0.2, -d)]


def slotted(slot=0.004):
    """a square with a slot cut in from its RIGHT edge — the rejected shape:
    both mouth vertices are within the hair of the same neighbour, so they
    move TOGETHER and the slot survives"""
    return [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0 - slot / 2),
            (0.5, 1.0 - slot / 2), (0.5, 1.0 + slot / 2),
            (2.0, 1.0 + slot / 2), (2.0, 2.0), (0.0, 2.0)]


def beside(dx=0.001):
    return [(2.0 + dx, -5.0), (10.0, -5.0), (10.0, 1.0 - 0.0045),
            (2.0 + dx, 1.0 - 0.0045)]


def build(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:70]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def report(name, a, b):
    print(f"\n=== {name}")
    print(f"  before: loop A self-min "
          f"{self_min(np.asarray(a, float)):.9f} mm, {len(a)} pts")
    out = imgtrace._pull_apart([a, b])
    sm = self_min(np.asarray(out[0], float))
    print(f"  after : loop A self-min {sm:.9f} mm, {len(out[0])} pts "
          f"-> {'CROSSES ITSELF' if sm <= 0.0 else 'still simple'}")
    print(f"  _first_crossing on the rounded loop: "
          f"{imgtrace._first_crossing(imgtrace._round_pts(out[0]))}")
    pushed = [imgtrace._poly_entity(imgtrace._round_pts(out[0]), "add"),
              imgtrace._poly_entity(imgtrace._round_pts(out[1]), "subtract")]
    clean = [imgtrace._poly_entity(imgtrace._round_pts(a), "add"),
             imgtrace._poly_entity(imgtrace._round_pts(b), "subtract")]
    b1, v1 = build(clean)
    b2, v2 = build(pushed)
    print(f"  as traced  : {b1 or 'healthy'}  volume {v1}")
    print(f"  after push : {b2 or 'healthy'}  volume {v2}")
    return sm


def main():
    report("a ribbon folded back on itself, 0.005 mm slot",
           serpentine(), below())
    print("\n  slot width sweep (ribbon 0.005 mm thick, neighbour 0.0045 mm "
          "away)")
    for slot in (0.002, 0.004, 0.005, 0.006, 0.008, 0.010, 0.014):
        out = imgtrace._pull_apart([serpentine(0.005, slot), below()])
        sm = self_min(np.asarray(out[0], float))
        print(f"    slot {slot:.3f} mm -> self-min {sm:>12.9f} "
              f"{'CROSSES' if sm <= 0.0 else ''}")
    report("REJECTED: a slot whose two mouth vertices share one neighbour",
           slotted(0.004), beside(0.001))


if __name__ == "__main__":
    main()
