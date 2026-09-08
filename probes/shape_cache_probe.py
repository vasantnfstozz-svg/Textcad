"""probes/shape_cache_probe.py — where may a per-body cache live? (2026-09-08)

blocks._face_rows / _edge_topo remember a body's faces, centres and edge
adjacency so a plan on a 48-edge selection costs 0.4 s instead of 34 s. The
first version stored them as ATTRIBUTES on the Part. This probe asks what
build123d does with such an attribute when the body is copied or moved, and
what a safe key looks like.

§1 does Shape.__deepcopy__ carry instance attributes over? (moved() / Pos * part
   go through it) — if so a moved copy inherits its parent's face centres
§2 can a build123d Part be a weakref / WeakKeyDictionary key, and what are its
   __hash__ / __eq__ — does a moved copy compare equal to its original?
§3 TopoDS_Shape.IsEqual: does it tell a copy, and an in-place move, apart?
"""
import copy
import sys
import weakref

sys.path.insert(0, ".")
from build123d import Location, Pos   # noqa: E402

import blocks                          # noqa: E402

p = blocks.plate(40, 30, 20)
p._probe_attr = {"faces": p.faces(), "n": 6}

print("== §1 deepcopy / moved carry attributes?")
q = copy.deepcopy(p)
print("  deepcopy has attr:", hasattr(q, "_probe_attr"),
      "| same list object:", getattr(q, "_probe_attr", {}).get("faces") is p._probe_attr["faces"])
m = p.moved(Location((100, 0, 0)))
print("  moved() has attr:", hasattr(m, "_probe_attr"))
if hasattr(m, "_probe_attr"):
    f0 = m._probe_attr["faces"][0]
    print("  moved copy's cached face 0 centre:", [round(v, 2) for v in tuple(f0.center())],
          "| its real face 0 centre:", [round(v, 2) for v in tuple(m.faces()[0].center())])
pm = Pos(0, 50, 0) * p
print("  Pos * part has attr:", hasattr(pm, "_probe_attr"))

print("\n== §2 weakref / hash / eq")
try:
    weakref.ref(p)
    print("  weakref.ref(part): ok")
except TypeError as e:
    print("  weakref.ref(part): REFUSED", e)
try:
    d = weakref.WeakKeyDictionary()
    d[p] = "rows"
    print("  WeakKeyDictionary[part]: ok; lookup:", d.get(p), "| moved copy finds parent's entry:", d.get(m))
    print("  hash(p) == hash(m):", hash(p) == hash(m), "| p == m:", p == m, "| p == deepcopy:", p == q)
except Exception as e:
    print("  WeakKeyDictionary: REFUSED", type(e).__name__, e)
print("  hash(p.wrapped) == hash(q.wrapped) (deepcopy):", hash(p.wrapped) == hash(q.wrapped))
print("  hash(p.wrapped) == hash(m.wrapped) (moved):", hash(p.wrapped) == hash(m.wrapped))

print("\n== §3 TopoDS_Shape.IsEqual")
w = p.wrapped
print("  p vs itself:", w.IsEqual(p.wrapped), "| p vs deepcopy:", w.IsEqual(q.wrapped),
      "| p vs moved:", w.IsEqual(m.wrapped))
r = copy.deepcopy(p)
r.move(Location((0, 0, 5)))          # IN PLACE
print("  in-place move: same object:", r is r, "| wrapped IsEqual before/after:",
      w.IsEqual(r.wrapped), "| top face z now:",
      round(max(f.center().Z for f in r.faces()), 2))
print("  in-place move keeps the attr:", hasattr(r, "_probe_attr"))
