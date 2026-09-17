"""Attack `sketch_trim._sample_wire`'s identity claim (review of 916a731).

The commit says `_sample_wire(w, n)` is bit-for-bit `[w.position_at(i/n)]` and
proves it on 7 entity kinds and the 324 sketches of the user's 40 designs.
Those designs predate the Text entity (d3c8c85) and contain no wire that is
REVERSED, self-touching, disconnected, zero-length or imported.  This probe
builds each of those by hand and compares the two samplers byte for byte.

Run:  C:\\Python314\\python.exe probes/trim_sample_identity_attack.py
"""
from __future__ import annotations
import os
import sys
import numpy as np
import build123d as b3d
from OCP.TopoDS import TopoDS


def reverse_wire(w):
    """A genuinely REVERSED Wire — `b3d.Wire(w.wrapped.Reversed())` silently
    yields an EMPTY wrapper (measured), so cast the TopoDS back explicitly."""
    return b3d.Wire.cast(TopoDS.Wire_s(w.wrapped.Reversed()))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sketch as sk          # noqa: E402
import sketch_trim as tr     # noqa: E402


def stock(wire, n):
    """`_outline`'s loop exactly as it stood at HEAD~ (337f947)."""
    pts = np.empty((n, 2))
    for i in range(n):
        p = wire.position_at(i / n)
        pts[i] = (p.X, p.Y)
    return pts


NS = (1, 2, 3, 5, 64, 96, 166, 384)


def compare(name, wire, ns=NS):
    for n in ns:
        try:
            a = stock(wire, n)
        except Exception as ex:                      # noqa: BLE001
            try:
                tr._sample_wire(wire, n)
                print(f"  DIVERGE {name} n={n}: stock raised {type(ex).__name__}"
                      f" but _sample_wire returned")
            except Exception as ex2:                 # noqa: BLE001
                if type(ex) is not type(ex2):
                    print(f"  DIVERGE {name} n={n}: stock {type(ex).__name__} "
                          f"vs new {type(ex2).__name__}")
            continue
        try:
            b = tr._sample_wire(wire, n)
        except Exception as ex:                      # noqa: BLE001
            print(f"  DIVERGE {name} n={n}: new raised {type(ex).__name__}: {ex}")
            continue
        if a.tobytes() != b.tobytes():
            d = np.abs(a - b)
            print(f"  DIVERGE {name} n={n}: max |delta| = {d.max():.3e} "
                  f"at sample {int(np.unravel_index(d.argmax(), d.shape)[0])}")
            return False
    edges = wire.edges()
    print(f"  ok  {name:44s} edges={len(edges):4d} fwd={wire.is_forward} "
          f"len={wire.length:.6f} sum_edges={sum(e.length for e in edges):.6f}")
    return True


def ent_wire(e):
    return tr._entity_face(e, 0).outer_wire()


def main():
    print("=== A. wires the user's 324 sketches do not contain ===")

    # 1. a reversed wire (inner wires of a boolean result are REVERSED)
    plate = b3d.Rectangle(40, 20)
    hole = b3d.Circle(6)
    face = (plate - hole).faces()[0]
    ow = face.outer_wire()
    inner = [w for w in face.wires() if not w.is_same(ow)]
    compare("boolean outer wire", ow)
    for k, w in enumerate(inner):
        compare(f"boolean INNER wire {k} (is_forward={w.is_forward})", w)

    # 2. explicitly reversed circle wire
    circ = b3d.Circle(9).faces()[0].outer_wire()
    compare("circle wire", circ)
    rev = reverse_wire(circ)
    compare("circle wire REVERSED", rev)

    poly = ent_wire({"kind": "regular_polygon", "mode": "add", "x": 0, "y": 0,
                     "radius": 10, "sides": 7})
    compare("regular_polygon 7", poly)
    compare("regular_polygon 7 REVERSED", reverse_wire(poly))
    compare("boolean outer wire REVERSED", reverse_wire(ow))

    # 3. a wire whose edges run against their natural direction
    pts = [(0, 0), (20, 0), (20, 10), (0, 10)]
    fwd_edges = [b3d.Edge.make_line(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    back = [b3d.Edge(e.wrapped.Reversed()) for e in fwd_edges]
    compare("square, every edge REVERSED", b3d.Wire(back))

    # 4. a single-edge OPEN wire, and a 2-edge open wire
    compare("single open line edge", b3d.Wire([b3d.Edge.make_line((0, 0), (10, 0))]))
    compare("two open line edges", b3d.Wire(
        [b3d.Edge.make_line((0, 0), (10, 0)),
         b3d.Edge.make_line((10, 0), (10, 7))]))

    # 5. a zero-length edge inside the table
    try:
        zero = b3d.Edge.make_line((10, 0), (10, 0))
        w = b3d.Wire([b3d.Edge.make_line((0, 0), (10, 0)), zero,
                      b3d.Edge.make_line((10, 0), (10, 7))])
        compare("wire with a ZERO-LENGTH edge", w)
    except Exception as ex:                          # noqa: BLE001
        print(f"  (zero-length edge could not be built: {ex})")

    # 6. a spline with many poles
    sp = b3d.Spline([(0, 0), (6, 9), (14, -4), (22, 8), (30, 0), (24, -12),
                     (10, -14), (0, 0)])
    compare("closed spline, 8 poles", b3d.Wire(sp.edges()))

    # 7. the NEW Text entity — the corpus predates it
    for word in ("O", "AB", "Bo8"):
        try:
            faces = sk._entity({"kind": "text", "mode": "add", "x": 0, "y": 0,
                                "text": word, "size": 20}).faces()
            print(f"  text {word!r}: {len(faces)} face(s)")
            for fi, f in enumerate(faces):
                compare(f"text {word!r} face{fi} outer", f.outer_wire())
                o = f.outer_wire()
                for wi, w in enumerate([x for x in f.wires()
                                        if not x.is_same(o)]):
                    compare(f"text {word!r} face{fi} hole{wi}", w)
        except Exception as ex:                      # noqa: BLE001
            print(f"  (text {word!r} failed: {ex})")

    # 8. a self-touching outline: two blobs joined by a hair-thin neck
    neck = (b3d.Circle(10) + b3d.Pos(19, 0) * b3d.Circle(10))
    compare("two circles fused at a tangent-ish neck",
            neck.faces()[0].outer_wire())

    # 9. a path entity with arcs (exercises CIRCLE edges mid-chain)
    compare("path with two arcs", ent_wire(
        {"kind": "path", "mode": "add", "x": 0, "y": 0, "start": [0, 0],
         "segments": [{"type": "line", "to": [20, 0]},
                      {"type": "arc", "via": [26, 6], "to": [20, 12]},
                      {"type": "line", "to": [0, 12]},
                      {"type": "arc", "via": [-5, 6], "to": [0, 0]}]}))

    # 10. an ellipse (one closed BSPLINE/ELLIPSE edge) and a tiny wire
    compare("ellipse", ent_wire({"kind": "ellipse", "mode": "add", "x": 0,
                                 "y": 0, "rx": 22, "ry": 9, "rotation": 31}))
    compare("tiny 0.2 mm circle", ent_wire({"kind": "circle", "mode": "add",
                                            "x": 0, "y": 0, "r": 0.1}))

    # 11. a wire whose edge table is DISCONNECTED (WireExplorer stops early)
    try:
        d = b3d.Wire([b3d.Edge.make_line((0, 0), (10, 0)),
                      b3d.Edge.make_line((50, 50), (60, 50))])
        compare("DISCONNECTED two-edge wire", d)
    except Exception as ex:                          # noqa: BLE001
        print(f"  (disconnected wire could not be built: {ex})")

    print("\n=== B. the parameter ends, on every wire kind above ===")
    for name, w in (("circle", circ), ("reversed circle", rev),
                    ("boolean outer", ow), ("poly7", poly)):
        for pos in (0.0, 1.0, 0.5, 1e-18, 1 - 1e-16):
            a = w.position_at(pos)
            # what _sample_wire computes for that same fraction
            b = tr._sample_wire(w, 1) if pos == 0.0 else None
            if b is not None and (float(a.X), float(a.Y)) != tuple(b[0]):
                print(f"  DIVERGE {name} at position {pos}: "
                      f"{a.X},{a.Y} vs {b[0]}")
        print(f"  ok  ends {name}")


if __name__ == "__main__":
    main()
