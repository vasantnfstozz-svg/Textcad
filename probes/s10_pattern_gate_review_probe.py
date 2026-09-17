"""Review probe for the pattern kind gate (eed6a33): put REAL bodies to it.

Asks four things the commit's own tests do not:
  §1 what `mirror join=true` (NOT gated) says when it is fed a sketch — the
     same family, the same confusing sentence?
  §2 a COMPOUND of separate solids still patterns (the gate must not fire).
  §3 a body whose `area` RAISES, and one with no solids but area (a bare
     face) — which branch each takes.
  §4 what the two pattern ops did with a sketch BEFORE the gate, so the gate
     is measured against doing nothing.

Run:  C:\\Python314\\python.exe probes/s10_pattern_gate_review_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build123d as b3d                       # noqa: E402
import document                               # noqa: E402
import inspector                              # noqa: E402
from document import Document, n_solids       # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def hdr(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def sketch_doc():
    d = Document(name="k")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    return d


# --- §1 mirror join=true on a sketch -----------------------------------------
hdr("§1 mirror with join=true, fed a SKETCH (not in SOLID_REPEATING_MODIFIERS)")
d = sketch_doc()
d.add("m1", "mirror", {"plane": "YZ", "join": True}, ["s1"])
d.rebuild()
f = d.get("m1")
print("status:", f.status)
print("problems:", f.problems)

hdr("§1b mirror with join=false, fed a SKETCH (the case the tests cover)")
d = sketch_doc()
d.add("m2", "mirror", {"plane": "YZ"}, ["s1"])
d.rebuild()
print("status:", d.get("m2").status, "problems:", d.get("m2").problems)

hdr("§1c mirror with a SEED, fed a sketch")
d = sketch_doc()
d.add("m3", "mirror", {"plane": "YZ", "seed": "s1"}, ["s1"])
d.rebuild()
print("status:", d.get("m3").status, "problems:", d.get("m3").problems)


# --- §2 a compound of separate solids ----------------------------------------
hdr("§2 a body that is TWO separate solids — the gate must not fire")
d = Document(name="c")
d.add("b1", "plate", {"width": 10, "depth": 10, "thickness": 5}, [])
d.add("p1", "linear_pattern", {"count": 2, "dx": 40}, ["b1"])        # two lumps
d.add("p2", "linear_pattern", {"count": 2, "dy": 40}, ["p1"])        # pattern the compound
ok = d.rebuild()
print("rebuild ok:", ok)
for fid in ("p1", "p2"):
    ff = d.get(fid)
    print(f"  {fid}: status={ff.status} vol={ff.volume} pieces={ff.pieces} {ff.problems}")


# --- §3 the two measurements the gate makes ----------------------------------
hdr("§3 n_solids / area on the shapes the gate can meet")
plate = b3d.Box(10, 10, 5)
face = b3d.Face(b3d.Rectangle(10, 10).wire())
comp_empty = b3d.Compound(children=[])
for name, shp in (("Box", plate), ("bare Face", face), ("empty Compound", comp_empty)):
    ns = n_solids(shp)
    area = inspector._try(lambda s=shp: s.area)
    print(f"  {name:16s} n_solids={ns}  area={area}")


class _AngryArea:
    wrapped = plate.wrapped

    @property
    def area(self):
        raise RuntimeError("area exploded")


ang = _AngryArea()
print("  area-raises      n_solids=", n_solids(ang),
      " area=", inspector._try(lambda: ang.area))


# --- §4 what happened BEFORE the gate ----------------------------------------
hdr("§4 the two pattern ops fed a sketch, with the gate bypassed")
import pattern                                 # noqa: E402
import sketch as sk                            # noqa: E402

sk_obj = sk.make_sketch("XY", 0.0, CIRC)
for op, fn, kw in (("linear_pattern", pattern.linear_pattern, dict(count=3, dx=20)),
                   ("polar_pattern", pattern.polar_pattern, dict(count=4)),
                   ("mirror join", pattern.mirror, dict(plane="YZ", join=True))):
    try:
        out = fn(sk_obj, **kw)
        print(f"  {op:16s} BUILT: solids={n_solids(out)} "
              f"area={inspector._try(lambda: out.area)} "
              f"vol={inspector._try(lambda: out.volume)}")
    except Exception as e:
        print(f"  {op:16s} refused: {type(e).__name__}: {e}")

print("\ndocument.SOLID_REPEATING_MODIFIERS =", document.SOLID_REPEATING_MODIFIERS)
