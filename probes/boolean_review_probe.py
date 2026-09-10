"""Section 4 review (booleans and transforms) — the measurements, 2026-09-10.

Every finding of that review was reproduced here BEFORE it was fixed. Run it
against the fixed tree and the refusals are sentences instead of kernel text;
run it against the commit before and §3 kills the process.

    C:\\Python314\\python.exe probes/boolean_review_probe.py

§1  transform pivots      — rotate is about the WORLD ORIGIN, scale about the
                            SHAPE CENTRE (the docstring claimed the origin)
§2  booleans that miss    — disjoint fuse/cut/intersect, and an edge-touching
                            fuse (health catches the last two, not the cut)
§3  loft, wrong inputs    — SEGFAULTS on sketch+solid; raw OCCT text otherwise
§4  a 2D combiner result  — intersect(body, sketch) ate the body, stayed green
§5  the spec with no body — reported "meets spec" with nothing built
§6  the default target    — a New-body boss became the panel's "current state"
§7  pattern piece noise   — 24 rows in 13 library designs called broken
§8  the stranding heal    — ticked `through` on a SHARED tool, and the other
                            cut silently lost 3600 mm3 more than it asks for
§9  the FOLLOW-UP read of c9b2e92 — two holes in §3's own guard, and a body
                            behind the rollback bar called broken
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d                                          # noqa: E402

import blocks                                                    # noqa: E402
import document                                                  # noqa: E402
import inspector                                                 # noqa: E402
import sketch as sk                                              # noqa: E402
import toolplan                                                  # noqa: E402
from document import Document                                    # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
RECT60 = [{"kind": "rectangle", "x": 0, "y": 0, "w": 60, "h": 60, "mode": "add"}]


def bb(part) -> str:
    b = part.bounding_box()
    return (f"x[{b.min.X:.1f},{b.max.X:.1f}] y[{b.min.Y:.1f},{b.max.Y:.1f}] "
            f"z[{b.min.Z:.1f},{b.max.Z:.1f}]")


def head(n, title):
    print(f"\n{'=' * 70}\n\u00a7{n}  {title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
head(1, "transform pivots: rotate = world origin, scale = shape centre")
plate = b3d.Pos(100, 0, 0) * blocks.plate(20, 20, 10)
print("  a plate moved to x=100 :", bb(plate))
print("  rotate(Z, 90)          :", bb(blocks.rotate(plate, "Z", 90.0)),
      "  <- it MOVED: about the world origin")
print("  scale(2)               :", bb(blocks.scale_uniform(plate, 2.0)),
      "  <- centre still x=100: about the SHAPE CENTRE")

# ---------------------------------------------------------------------------
head(2, "booleans on bodies that do not overlap")
a = blocks.plate(10, 10, 10)
far = b3d.Pos(50, 0, 0) * blocks.plate(10, 10, 10)
for name, fn in (("fuse", document._fuse), ("cut", document._cut),
                 ("intersect", document._intersect)):
    try:
        out = fn([a, far])
        print(f"  {name:10s} vol={out.volume:>9.1f} solids={document.n_solids(out)} "
              f"health={inspector.health(out, check_valid=False)}")
    except Exception as e:                                       # noqa: BLE001
        print(f"  {name:10s} RAISED {type(e).__name__}: {e}")
print("  -> the CUT is the silent one: it returns its input unchanged and")
print("     health has nothing to say, so a tool that misses reads as success")
touching = document._fuse([blocks.plate(10, 10, 10),
                           b3d.Pos(10, 10, 0) * blocks.plate(10, 10, 10)])
print("  edge-touching fuse:", inspector.health(touching, check_valid=False))

# ---------------------------------------------------------------------------
head(3, "loft with the wrong inputs (DANGER: one of these segfaults)")
s1 = sk.make_sketch(entities=CIRC, plane="XY", offset=0.0)
s2 = sk.make_sketch(entities=RECT60, plane="XY", offset=20.0)
flat = sk.make_sketch(entities=RECT60, plane="XY", offset=0.0)
solid = blocks.plate(20, 20, 5)
cases = [("two solids", [solid, blocks.disc(5, 5)]),
         ("the same sketch twice", [s1, s1]),
         ("coplanar profiles", [s1, flat]),
         ("a real loft", [s1, s2])]
if "--crash" in sys.argv:
    cases.insert(1, ("sketch + solid  (SEGFAULT)", [s1, solid]))
else:
    print("  [sketch + solid is SKIPPED - it kills the process. --crash to run it]")
for label, parts in cases:
    try:
        out = document._loft(parts)
        print(f"  {label:28s} vol={out.volume:.1f}")
    except Exception as e:                                       # noqa: BLE001
        print(f"  {label:28s} {type(e).__name__}: {e}")
# The KIND gate lives in Document._eval, before the kernel is reached at all —
# which is the only thing that can stop the segfault. Calling _loft directly,
# as above, skips it; through the document the message names the feature:
d = Document(name="lf")
d.add("p1", "plate", {"width": 20, "depth": 20, "thickness": 5})
d.add("p2", "disc", {"radius": 5, "thickness": 5})
d.add("lf", "loft", {}, ["p1", "p2"])
d.rebuild()
print("  via the document           ", d.get("lf").problems[0])

# ---------------------------------------------------------------------------
head(4, "a combiner whose result is 2D eats the body and stays green")
d = Document(name="ix")
d.add("p1", "plate", {"width": 20, "depth": 20, "thickness": 10})
d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0})
d.add("ix", "intersect", {}, ["p1", "s1"])
print("  rebuild ok     =", d.rebuild())
print("  statuses       =", {f.id: f.status for f in d.features})
print("  leaf bodies    =", d.leaf_solid_ids(), " result_shape:", d.result_shape())
print("  warnings       =", d.warnings)
print("  -> before the fix: every row ok, no bodies, no warning at all")

# ---------------------------------------------------------------------------
head(5, "the spec verdict when the design has no bodies")
d = Document(name="z", spec={"n_solids": 1, "size": [20, 20, 10], "tol": 0.5})
d.add("p1", "plate", {"width": 20, "depth": 20, "thickness": 10})
print(f"  body live   : ok={d.rebuild()} spec_problems={d.spec_problems}")
d.get("p1").suppressed = True
d._mark_stale()
print(f"  body struck : ok={d.rebuild()} spec_problems={d.spec_problems}")
print("  -> before the fix the second line was ok=True, spec_problems=[]")

# ---------------------------------------------------------------------------
head(6, "the Join/Cut default target after a New-body face boss")
d = Document(name="dt")
d.add("panel", "plate", {"width": 80, "depth": 40, "thickness": 10})
d.rebuild()
top = max(d._parts["panel"].faces(), key=lambda f: f.center().Z)
fc = [top.center().X, top.center().Y, top.center().Z]
d.add("boss", "extrude_face", {"face_center": fc, "amount": 5.0}, ["panel"])
d.add("sk2", "sketch_on_face",
      {"face_center": fc, "offset": 0.0, "entities": CIRC}, ["panel"])
d._mark_stale()
d.rebuild()
print("  _latest_descendant('panel') =", toolplan._latest_descendant(d, "panel"))
print("  plan target_body            =",
      toolplan.plan_extrude(d, {"sketch_id": "sk2"})["target_body"])
print("  -> before the fix both said 'boss', so the next Cut cut the PRISM")

# ---------------------------------------------------------------------------
head(7, "a pattern of copies reported as a part that fell apart")
d = Document(name="pat")
d.add("peg", "disc", {"radius": 3, "thickness": 5})
d.add("row", "linear_pattern", {"count": 4, "dx": 20}, ["peg"])
d.rebuild()
print("  row.pieces =", d.get("row").pieces)
print("  warnings   =", d.warnings or "(none)")
print("  -> before the fix: 24 such rows in 13 library designs were each told")
print("     'something in it no longer touches the rest'")

# ---------------------------------------------------------------------------
head(8, "the stranding heal on a tool two cuts share")


def strand(shared: bool):
    d = Document(name="strand")
    d.add("base", "plate", {"width": 40, "depth": 40, "thickness": 20})
    d.add("bandsk", "sketch_on_face",
          {"face": "top", "offset": -6.0, "entities": RECT60}, ["base"])
    d.add("band", "extrude", {"amount": 2.0}, ["bandsk"])
    d.add("slice", "cut", {}, ["base", "band"])
    if shared:
        d.add("base2", "plate", {"width": 30, "depth": 30, "thickness": 20})
        d.add("slice2", "cut", {}, ["base2", "band"])
    d.rebuild()
    return d


d = strand(shared=False)
print(f"  tool of its own : through={d.get('band').params.get('through', 'ABSENT')} "
      f"slice.pieces={d.get('slice').pieces}  (the heal SHOULD fire)")
d = strand(shared=True)
print(f"  tool shared     : through={d.get('band').params.get('through', 'ABSENT')} "
      f"slice2.vol={d.get('slice2').volume}")
print("  -> before the fix: through=True and slice2 was 12600.0, i.e. 3600 mm3")
print("     more removed than its own parameters ask for (16200.0), unasked")
print("     and unmentioned. designs/cam-cover-plaque shares a tool this way.")

# ---------------------------------------------------------------------------
head(9, "the FOLLOW-UP read of c9b2e92: two holes in the loft guard")
print("  getattr(obj, 'volume', 0) does NOT swallow a raising property —")


class _Boom:
    @property
    def volume(self):
        raise RuntimeError("kernel says no")


try:
    getattr(_Boom(), "volume", 0)
    print("     ...swallowed (so the first guard was fine)")
except Exception as e:                                           # noqa: BLE001
    print(f"     ...it PROPAGATES: {type(e).__name__}. inspector._try does not:",
          inspector._try(lambda: _Boom().volume))
print("  and build123d raises its OWN bare ValueError with kernel wording:")
try:
    sk.loft_sketches([sk.make_sketch(entities=CIRC, plane="XY", offset=0.0),
                      b3d.Part()])
except Exception as e:                                           # noqa: BLE001
    print(f"     {type(e).__name__}: {e}")
print("  -> `except ValueError: raise` let that out as 'already a sentence'.")
print("     _loft now translates EVERYTHING and reads the volume through _try.")
print()
print("  and a body behind a parked rollback bar was called broken:")
d = Document(name="rb")
d.add("base", "plate", {"width": 40, "depth": 40, "thickness": 10})
d.add("boss", "disc", {"radius": 8, "thickness": 6})
d.rebuild()
print(f"     boss builds at {d.get('boss').volume} mm3 with no bar")
d.rollback = "base"
d._mark_stale()
d.rebuild()
try:
    toolplan._pick_body(d, "boss", "drill")
except ValueError as e:
    print(f"     with the bar parked: {e}")
