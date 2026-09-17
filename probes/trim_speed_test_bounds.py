"""How much slack do the three RED count tests of 916a731 actually carry?

`tests/test_trim_speed.py` asserts `seen["n"] <= 4` for one outline and
`<= 4 * len(ents)` for a whole sketch.  The commit says the old code scored
166 and 544.  This prints the TRUE counts so the bounds can be judged, and
checks that the counter cannot be satisfied by a change that stops sampling
altogether.

Run:  C:\\Python314\\python.exe probes/trim_speed_test_bounds.py
"""
from __future__ import annotations
import os
import sys
import math
from contextlib import contextmanager

import build123d as b3d
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sketch_trim as tr     # noqa: E402


@contextmanager
def counting_wire_walks():
    seen = {"n": 0}
    original = b3d.Wire.edges

    def edges(self):
        seen["n"] += 1
        return original(self)

    b3d.Wire.edges = edges
    try:
        yield seen
    finally:
        b3d.Wire.edges = original


@contextmanager
def counting_edge_adaptors():
    """Per-POINT cost that survived the fix: one geom_adaptor + one Length_s
    per sample, inside Edge.position_at."""
    seen = {"n": 0}
    original = b3d.Edge.geom_adaptor

    def adaptor(self):
        seen["n"] += 1
        return original(self)

    b3d.Edge.geom_adaptor = adaptor
    try:
        yield seen
    finally:
        b3d.Edge.geom_adaptor = original


def traced(points, r, x=0.0, y=0.0, mode="add"):
    pts = []
    for k in range(points):
        a = 2 * math.pi * k / points
        rad = r + 0.07 * r * math.sin(7 * a)
        pts.append([round(rad * math.cos(a), 4), round(rad * math.sin(a), 4)])
    return {"kind": "polygon", "mode": mode, "x": x, "y": y, "points": pts}


RECT = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 40, "h": 20}


def main():
    ent = traced(240, 20.0)
    with counting_wire_walks() as seen:
        outline = tr._outline(ent, 0)
    print(f"test 1  _outline on a 240-edge polygon: {len(outline['pts'])} "
          f"samples, wire walks = {seen['n']}   (bound is <= 4)")

    ents = [traced(120, 18.0, x=-30), traced(120, 18.0, x=30),
            traced(90, 10.0, mode="subtract"), dict(RECT)]
    with counting_wire_walks() as seen:
        tr.trim_pieces(ents)
    print(f"test 3  trim_pieces on {len(ents)} entities: wire walks = "
          f"{seen['n']}   (bound is <= {4 * len(ents)})")

    # what the OLD sampler scored on the same two cases
    original = tr._sample_wire

    def stock(wire, n):
        pts = np.empty((n, 2))
        for i in range(n):
            p = wire.position_at(i / n)
            pts[i] = (p.X, p.Y)
        return pts

    tr._sample_wire = stock
    try:
        with counting_wire_walks() as seen:
            tr._outline(ent, 0)
        print(f"        old sampler, same outline: {seen['n']} walks")
        with counting_wire_walks() as seen:
            tr.trim_pieces(ents)
        print(f"        old sampler, same sketch : {seen['n']} walks")
    finally:
        tr._sample_wire = original

    # the per-point cost that is LEFT
    wire = tr._entity_face(ent, 0).outer_wire()
    for n in (10, 100, 400):
        with counting_edge_adaptors() as seen:
            tr._sample_wire(wire, n)
        print(f"        Edge.geom_adaptor calls for n={n:4d}: {seen['n']}")

    # can a wholly different sampler satisfy the walk bound? (mesh/discretize)
    with counting_wire_walks() as seen:
        wire.edges()                       # a single table build
    print(f"\n        one wire.edges() call scores {seen['n']} — so any "
          f"implementation that builds the table once passes the bound,\n"
          f"        including ones that do not sample by arc length at all; "
          f"the identity tests are what stops those.")


if __name__ == "__main__":
    main()
