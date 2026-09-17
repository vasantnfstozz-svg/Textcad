r"""Is `_wire_entity` the same answer when it asks `edges()` instead of
`order_edges()`?

`Wire.order_edges()` = `self.edges().sort_by(self)` + a flip pass.  Both halves
are already done for it:

  * build123d defines a WIRE parameter by walking `BRepTools_WireExplorer` and
    summing edge lengths (`Wire.param_at_point`), and `Wire.edges()` walks the
    SAME explorer — so sorting by that parameter cannot reorder the list;
  * `_wire_entity` flips each edge itself (`flipped = (cur - p0).length >
    (cur - p1).length`), so the flip pass is redundant too.

This compares the ENTITY DICT both ways on every wire shape Trim rebuilds,
including reversed wires and Text glyphs (which the user's designs lack).

    C:\Python314\python.exe probes/trim_wire_entity_identity.py
"""
from __future__ import annotations
import json
import math
import os
import sys
import time

import build123d as b3d
from OCP.TopoDS import TopoDS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sketch as sk          # noqa: E402
import sketch_trim as tr     # noqa: E402


def reverse_wire(w):
    return b3d.Wire.cast(TopoDS.Wire_s(w.wrapped.Reversed()))


def traced_poly(n=240, r=20.0):
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        rad = r + 0.07 * r * math.sin(7 * a)
        pts.append((round(rad * math.cos(a), 4), round(rad * math.sin(a), 4)))
    return b3d.Polygon(*pts)


def battery():
    plate = b3d.Rectangle(60, 30)
    yield "rect", plate.faces()[0].outer_wire()
    f = (plate - b3d.Pos(10, 0) * b3d.Circle(6)).faces()[0]
    ow = f.outer_wire()
    yield "rect+hole outer", ow
    for w in f.wires():
        if not w.is_same(ow):
            yield "rect+hole INNER", w
    yield "rect+hole outer REVERSED", reverse_wire(ow)
    yield "circle", b3d.Circle(9).faces()[0].outer_wire()
    yield "circle REVERSED", reverse_wire(b3d.Circle(9).faces()[0].outer_wire())
    yield "fused blobs", (b3d.Circle(10) +
                          b3d.Pos(14, 0) * b3d.Circle(10)).faces()[0].outer_wire()
    yield "ellipse", b3d.Ellipse(22, 9).faces()[0].outer_wire()
    sp = b3d.Spline([(0, 0), (6, 9), (14, -4), (22, 8), (30, 0), (24, -12),
                     (10, -14), (0, 0)])
    yield "closed spline", b3d.Wire(sp.edges())
    poly = traced_poly()
    yield "240-edge traced", poly.faces()[0].outer_wire()
    cut = (poly - b3d.Pos(18, 0) * b3d.Circle(9)).faces()[0]
    yield "240-edge traced - circle", cut.outer_wire()
    # a rectangle cut by a circle: chained line + arc, the classic trim result
    rc = (plate - b3d.Pos(30, 0) * b3d.Circle(8)).faces()[0]
    yield "rect bitten by a circle", rc.outer_wire()
    # every glyph wire of a word (BSPLINE + reversed, absent from designs/)
    for fi, gf in enumerate(sk._entity({"kind": "text", "mode": "add", "x": 0,
                                        "y": 0, "text": "AB8", "size": 18}
                                       ).faces()):
        o = gf.outer_wire()
        yield f"text glyph{fi} outer", o
        for wi, w in enumerate([x for x in gf.wires() if not x.is_same(o)]):
            yield f"text glyph{fi} hole{wi}", w


def main():
    original = b3d.Wire.order_edges
    bad = 0
    t_old = t_new = 0.0
    for name, w in battery():
        b3d.Wire.order_edges = original
        t = time.perf_counter()
        try:
            a = json.dumps(tr._wire_entity(w, "add"), sort_keys=True)
        except Exception as ex:                              # noqa: BLE001
            a = f"RAISED {type(ex).__name__}: {ex}"
        t_old += time.perf_counter() - t

        b3d.Wire.order_edges = lambda self: self.edges()
        t = time.perf_counter()
        try:
            b = json.dumps(tr._wire_entity(w, "add"), sort_keys=True)
        except Exception as ex:                              # noqa: BLE001
            b = f"RAISED {type(ex).__name__}: {ex}"
        t_new += time.perf_counter() - t
        b3d.Wire.order_edges = original

        if a == b:
            print(f"  ok  {name:28s} {len(w.edges()):4d} edges, "
                  f"{len(a):6d} chars")
        else:
            bad += 1
            print(f"  DIFFERS {name}")
            print(f"     order_edges: {a[:200]}")
            print(f"     edges()    : {b[:200]}")
    print(f"\n{bad} differences.  order_edges total {t_old:.2f} s, "
          f"edges() total {t_new:.2f} s "
          f"({t_old / max(t_new, 1e-9):.0f}x)")


if __name__ == "__main__":
    main()
