"""Round two's attack on the `order_edges()` removal in `_wire_entity`.

Round one removed `wire.order_edges()` from `_wire_entity` on a STRUCTURAL
argument (build123d defines a wire's parameter by walking
`BRepTools_WireExplorer`, `Wire.edges()` walks the same explorer, so
`sort_by(self)` cannot reorder it; and `_wire_entity` flips each edge
itself). That argument is only as good as the wires it meets.

`_wire_entity` writes the outline BACK into the user's sketch, so a wrong
order is silent wrong geometry saved. The test that decides it is not
"same order" but "is the list a connected traversal chain": `_wire_entity`
walks the list once, flipping each edge to meet the previous one's end, so
it produces a correct closed outline IFF consecutive edges touch.

So for every wire below this measures, for BOTH lists:

  * the largest gap between edge k's traversal end and edge k+1's start,
  * whether the loop closes (last end == first start),
  * the `_wire_entity` dict itself, compared field by field,
  * the AREA of the face the resulting entity builds against the area of
    the face the wire came from — the number a garbled outline destroys.

Hunting grounds the brief named: a wire assembled from edges added out of
order, a wire from a boolean, a wire from an imported STEP/STL, a wire from
Sweep/Loft/Text, a closed wire whose seam sits mid-list, plus a
self-touching wire (where `sort_by`'s closest-point key is known to be able
to answer with the wrong edge).

Read only.
"""
from __future__ import annotations
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d
from OCP.TopoDS import TopoDS
import sketch as sk
import sketch_trim as tr

TOLC = 1e-6


def reversed_wire(w):
    """The same wire with TopAbs orientation REVERSED (build123d 0.11.1 has
    no `Wire.reversed()`)."""
    return b3d.Wire(TopoDS.Wire_s(w.wrapped.Reversed()))


def face_area(w):
    """Area of the face this single wire encloses — what `_wire_entity`
    must preserve. None when the wire cannot make a face."""
    try:
        return float(b3d.Face(w).area)
    except Exception:                                  # noqa: BLE001
        return None


def chain_gaps(edges):
    """Largest joint gap walking the list the way `_wire_entity` does."""
    worst, cur, start = 0.0, None, None
    for e in edges:
        p0, p1 = e @ 0, e @ 1
        if cur is None:
            start = p0
            cur = p1
            continue
        d0, d1 = (cur - p0).length, (cur - p1).length
        worst = max(worst, min(d0, d1))
        cur = p1 if d0 <= d1 else p0
    close = (cur - start).length if start is not None else 0.0
    return worst, close


def ent_area(ent):
    try:
        return float(sk._entity(ent).area)
    except Exception as ex:                            # noqa: BLE001
        return f"BUILD FAILED: {str(ex)[:60]}"


def compare(name, wire, true_area=None):
    try:
        a = wire.edges()
    except Exception as ex:                            # noqa: BLE001
        print(f"  {name:<44} edges() raised {ex}")
        return
    try:
        b = wire.order_edges()
    except Exception as ex:                            # noqa: BLE001
        b = None
        ob_err = str(ex)[:50]
    ga, ca = chain_gaps(a)
    if b is None:
        print(f"  {name:<44} n={len(a):<4} edges() gap={ga:.2e} close={ca:.2e}"
              f"   order_edges() RAISED {ob_err}")
        return
    gb, cb = chain_gaps(b)
    same_len = len(a) == len(b)
    # same geometric sequence? compare midpoints in list order
    seq_same = same_len and all(
        ((a[i] @ 0.5) - (b[i] @ 0.5)).length < 1e-9 for i in range(len(a)))
    try:
        ea = tr._wire_entity(wire, "add")
    except Exception as ex:                            # noqa: BLE001
        ea = {"ERR": str(ex)[:60]}
    orig = tr._ordered_edges
    tr._ordered_edges = lambda w: w.order_edges()
    try:
        eb = tr._wire_entity(wire, "add")
    except Exception as ex:                            # noqa: BLE001
        eb = {"ERR": str(ex)[:60]}
    finally:
        tr._ordered_edges = orig
    ident = ea == eb
    aa, ab = ent_area(ea), ent_area(eb)
    flag = "" if (ident and gb <= max(ga, 1e-9)) else "   <<<< DIFFERS"
    print(f"  {name:<44} n={len(a):<4} edges(): gap={ga:.2e} close={ca:.2e} | "
          f"order_edges(): n={len(b):<4} gap={gb:.2e} close={cb:.2e} | "
          f"seq_same={seq_same} entity_same={ident}{flag}")
    if not ident or (isinstance(aa, float) and isinstance(ab, float)
                     and abs(aa - ab) > 1e-6):
        print(f"      area edges()={aa}  order_edges()={ab}  true={true_area}")
    if true_area is not None and isinstance(aa, float) \
            and abs(aa - true_area) > 1e-4:
        print(f"      !! edges() outline area {aa} vs true {true_area}")


def wires_of(shape):
    out = []
    for f in shape.faces():
        ow = f.outer_wire()
        out.append(("outer", ow, face_area(ow)))
        for w in f.wires():
            if not w.is_same(ow):
                out.append(("hole", w, face_area(w)))
    return out


def main():
    print("=" * 110)
    print("A. wires a TRIM boolean really produces (the production source)")
    print("=" * 110)
    cases = {
        "rect + circle overlap": (
            b3d.Rectangle(40, 20) + b3d.Pos(20, 0) * b3d.Circle(8)),
        "rect - circle bite": (
            b3d.Rectangle(40, 20) - b3d.Pos(20, 0) * b3d.Circle(8)),
        "plate with 2 holes": (
            b3d.Rectangle(40, 30) - b3d.Pos(-10, 0) * b3d.Circle(5)
            - b3d.Pos(10, 0) * b3d.Circle(5)),
        "two discs joined by a thin neck": (
            b3d.Pos(-9, 0) * b3d.Circle(10) + b3d.Pos(9, 0) * b3d.Circle(10)),
        "ring (annulus)": b3d.Circle(20) - b3d.Circle(12),
        "L from two rects": (
            b3d.Rectangle(40, 10) + b3d.Pos(-15, 10) * b3d.Rectangle(10, 10)),
        "star of 5 overlapping rects": None,
    }
    star = b3d.Rectangle(30, 6)
    for k in range(1, 5):
        star = star + b3d.Rectangle(30, 6).rotate(b3d.Axis.Z, 36 * k)
    cases["star of 5 overlapping rects"] = star
    for name, shape in cases.items():
        for tag, w, area in wires_of(shape):
            compare(f"{name} [{tag}]", w, area)

    print()
    print("=" * 110)
    print("B. wires ASSEMBLED FROM EDGES ADDED OUT OF ORDER")
    print("=" * 110)
    sq = [b3d.Edge.make_line((0, 0, 0), (10, 0, 0)),
          b3d.Edge.make_line((10, 0, 0), (10, 10, 0)),
          b3d.Edge.make_line((10, 10, 0), (0, 10, 0)),
          b3d.Edge.make_line((0, 10, 0), (0, 0, 0))]
    for label, order in [("in order", [0, 1, 2, 3]),
                         ("shuffled 2,0,3,1", [2, 0, 3, 1]),
                         ("reversed list", [3, 2, 1, 0]),
                         ("seam mid-list 1,2,3,0", [1, 2, 3, 0])]:
        picked = [sq[i] for i in order]
        for maker in ("Wire(...)", "Wire.combine"):
            try:
                if maker == "Wire(...)":
                    w = b3d.Wire(picked)
                else:
                    w = b3d.Wire.combine(picked)[0]
            except Exception as ex:                    # noqa: BLE001
                print(f"  square {label:<22} {maker:<14} build raised "
                      f"{str(ex)[:50]}")
                continue
            compare(f"square {label} [{maker}]", w, 100.0)
    # some edges handed in REVERSED as well as out of order
    mixed = [sq[2].reversed(), sq[0], sq[3].reversed(), sq[1]]
    try:
        compare("square shuffled AND 2 edges reversed",
                b3d.Wire(mixed), 100.0)
    except Exception as ex:                            # noqa: BLE001
        print("  shuffled+reversed build raised", str(ex)[:70])

    print()
    print("=" * 110)
    print("C. REVERSED wires, and a wire holding a whole circle edge")
    print("=" * 110)
    rect = b3d.Rectangle(40, 20)
    ow = rect.face().outer_wire()
    compare("rectangle outer wire", ow, 800.0)
    compare("rectangle outer wire REVERSED", reversed_wire(ow), 800.0)
    disc = b3d.Circle(9).face()
    compare("full circle wire", disc.outer_wire(), float(disc.area))
    compare("full circle wire REVERSED", reversed_wire(disc.outer_wire()),
            float(disc.area))
    star2 = b3d.Rectangle(30, 6) + b3d.Rectangle(30, 6).rotate(b3d.Axis.Z, 40)
    sw = star2.faces()[0].outer_wire()
    compare("30-edge boolean outline REVERSED", reversed_wire(sw),
            face_area(sw))
    # a circle edge chained with lines: circle fully inside a rect makes a
    # separate hole wire, so build the chain by hand instead
    key = (b3d.Rectangle(30, 10) + b3d.Pos(20, 0) * b3d.Circle(8))
    for tag, w, area in wires_of(key):
        compare(f"rect+circle keyhole [{tag}]", w, area)

    print()
    print("=" * 110)
    print("D. SELF-TOUCHING and nearly self-touching wires")
    print("=" * 110)
    # a C whose tips nearly meet: the closest point to a tip's midpoint is
    # on the OTHER tip
    c_ring = b3d.Circle(20) - b3d.Circle(14) - \
        b3d.Pos(19, 0) * b3d.Rectangle(14, 1.0)
    for tag, w, area in wires_of(c_ring):
        compare(f"C ring, 1.0mm gap [{tag}]", w, area)
    c_ring2 = b3d.Circle(20) - b3d.Circle(14) - \
        b3d.Pos(19, 0) * b3d.Rectangle(14, 0.05)
    for tag, w, area in wires_of(c_ring2):
        compare(f"C ring, 0.05mm gap [{tag}]", w, area)
    # a spiral-ish comb: many long thin fingers close together
    comb = b3d.Rectangle(40, 4)
    for k in range(8):
        comb = comb + b3d.Pos(-18 + k * 5, 14) * b3d.Rectangle(2.0, 24)
    for tag, w, area in wires_of(comb):
        compare(f"8-finger comb [{tag}]", w, area)

    print()
    print("=" * 110)
    print("E. TEXT glyph wires (the 8th entity kind, added after the corpus)")
    print("=" * 110)
    for word in ["O", "B", "8", "A", "S", "g", "Q"]:
        s = sk._entity({"kind": "text", "text": word, "size": 12.0,
                        "x": 0, "y": 0})
        for tag, w, area in wires_of(s):
            compare(f"text {word!r} [{tag}]", w, area)
            compare(f"text {word!r} [{tag}] REVERSED", reversed_wire(w), area)

    print()
    print("=" * 110)
    print("F. SWEEP / LOFT faces, and an offset (BSPLINE) outline")
    print("=" * 110)
    try:
        prof = b3d.Rectangle(6, 2)
        path = b3d.Edge.make_spline([(0, 0, 0), (20, 10, 0), (40, -6, 0)])
        swept = b3d.sweep(b3d.Plane(origin=(0, 0, 0), z_dir=(0, 0, 1)) * prof,
                          path)
        for tag, w, area in wires_of(swept):
            compare(f"sweep face [{tag}]", w, area)
    except Exception as ex:                            # noqa: BLE001
        print("  sweep case skipped:", str(ex)[:80])
    try:
        off = b3d.offset(b3d.Rectangle(30, 12).face(), 3.0,
                         kind=b3d.Kind.ARC)
        for tag, w, area in wires_of(off):
            compare(f"offset ARC face [{tag}]", w, area)
    except Exception as ex:                            # noqa: BLE001
        print("  offset case skipped:", str(ex)[:80])
    try:
        ell = b3d.Ellipse(18, 7).face()
        compare("ellipse wire", ell.outer_wire(), float(ell.area))
        sl = b3d.SlotOverall(30, 10).face()
        compare("slot wire", sl.outer_wire(), float(sl.area))
    except Exception as ex:                            # noqa: BLE001
        print("  ellipse/slot skipped:", str(ex)[:80])

    print()
    print("=" * 110)
    print("G. IMPORTED STEP outline (exact BREP, edges OCCT wrote itself)")
    print("=" * 110)
    import tempfile
    try:
        solid = b3d.extrude(
            (b3d.Rectangle(30, 18) - b3d.Pos(6, 0) * b3d.Circle(4)).face(),
            amount=5)
        fn = os.path.join(tempfile.gettempdir(), "_trim_order_probe.step")
        b3d.export_step(solid, fn)
        back = b3d.import_step(fn)
        flat = [f for f in back.faces()
                if abs(f.center().Z) < 1e-6 and f.area > 1]
        for f in flat:
            ow = f.outer_wire()
            compare("STEP re-import flat face [outer]", ow, float(f.area))
            for w in f.wires():
                if not w.is_same(ow):
                    compare("STEP re-import flat face [hole]", w)
        os.remove(fn)
    except Exception:                                  # noqa: BLE001
        traceback.print_exc()


if __name__ == "__main__":
    main()
