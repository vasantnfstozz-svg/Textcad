r"""Lead 2 of the 916a731 brief: `Wire.order_edges()` inside `_wire_entity`.

`order_edges()` is `self.edges().sort_by(self)` plus a flip pass, and
`sort_by(Wire)` costs one `param_at_point` per edge.  But `Wire.edges()`
ALREADY walks the wire with `BRepTools_WireExplorer`, which returns the edges
in CONNECTION order with their orientation composed — so the sort may be
re-deriving an order that is already there.

The decisive question is not "is it faster" but "is it the SAME list".  This
compares, on the wires Trim actually rebuilds:

  * the order of the edges (by geometric midpoint, so the two wrappers of one
    TopoDS edge compare equal),
  * the direction each edge runs in (start point),
  * and the time each costs.

    C:\Python314\python.exe probes/trim_order_edges_lead.py
"""
from __future__ import annotations
import os
import sys
import time

import build123d as b3d

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sketch_trim as tr     # noqa: E402


def key(e):
    a, b = e @ 0, e @ 1
    return (round(a.X, 6), round(a.Y, 6), round(b.X, 6), round(b.Y, 6))


def wires_to_test():
    plate = b3d.Rectangle(60, 30)
    yield "rect - circle (outer)", (plate - b3d.Circle(8)).faces()[0].outer_wire()
    f = (plate - b3d.Pos(10, 0) * b3d.Circle(6)).faces()[0]
    ow = f.outer_wire()
    yield "rect with hole (outer)", ow
    for w in f.wires():
        if not w.is_same(ow):
            yield "rect with hole (INNER)", w
    yield "fused blobs", (b3d.Circle(10) +
                          b3d.Pos(14, 0) * b3d.Circle(10)).faces()[0].outer_wire()
    yield "circle", b3d.Circle(9).faces()[0].outer_wire()
    # the expensive kind: a traced polygon cut by a circle
    import math
    pts = []
    for k in range(240):
        a = 2 * math.pi * k / 240
        r = 20 + 1.4 * math.sin(7 * a)
        pts.append((round(r * math.cos(a), 4), round(r * math.sin(a), 4)))
    poly = b3d.Polygon(*pts)
    yield "240-edge traced polygon", poly.faces()[0].outer_wire()
    yield "240-edge polygon - circle", (poly - b3d.Pos(18, 0) *
                                        b3d.Circle(9)).faces()[0].outer_wire()


def main():
    print(f"{'wire':30s} {'edges':>6s} {'order_edges':>12s} {'edges()':>10s} "
          f"{'same order?':>12s} {'same dirs?':>11s}")
    for name, w in wires_to_test():
        t = time.perf_counter()
        oe = w.order_edges()
        t_oe = time.perf_counter() - t
        t = time.perf_counter()
        ee = w.edges()
        t_ee = time.perf_counter() - t
        ko, ke = [key(e) for e in oe], [key(e) for e in ee]
        same_order = [k[:2] for k in ko] == [k[:2] for k in ke] or \
                     sorted(ko) == sorted(ke) and ko == ke
        print(f"{name:30s} {len(ee):6d} {t_oe * 1000:10.1f}ms "
              f"{t_ee * 1000:8.1f}ms {str(ko == ke):>12s} "
              f"{str([k[:2] for k in ko] == [k[:2] for k in ke]):>11s}")
        if ko != ke:
            # where do they part company?
            for i, (a, b) in enumerate(zip(ko, ke)):
                if a != b:
                    print(f"      first difference at {i}: order_edges "
                          f"{a[:2]}->{a[2:]}   edges() {b[:2]}->{b[2:]}")
                    break
            rot = next((r for r in range(len(ke))
                        if ke[r:] + ke[:r] == ko), None)
            print(f"      edges() is order_edges rotated by "
                  f"{rot if rot is not None else 'NOT a rotation'}")


if __name__ == "__main__":
    main()
