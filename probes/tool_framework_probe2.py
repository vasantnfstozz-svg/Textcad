"""Section 11 probe, part 2: _loops / _limits against real ring profiles."""
import os
import sys

os.environ.setdefault("TEXTCAD_NO_BROWSER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sketch as sk                                # noqa: E402
import toolplan                                    # noqa: E402
from document import Document                      # noqa: E402


def build(*feats):
    d = Document(name="probe")
    for fid, op, params, inputs in feats:
        d.add(fid, op, params, inputs)
    d.rebuild()
    return d


print("=" * 72)
print("A ring sketch (r15 outer, r5 hole) — does _loops see the hole?")
print("=" * 72)
d = build(("s", "sketch", {"plane": "XY", "entities": [
    {"kind": "circle", "r": 15},
    {"kind": "circle", "r": 5, "mode": "subtract"}]}, []))
f = d.features[0]
print("  status:", f.status, "problems:", f.problems)
prof = d._parts["s"]
pl = sk.sketch_plane("XY", 0)
faces = list(prof.faces())
print(f"  faces: {len(faces)}")
for i, fc in enumerate(faces):
    print(f"   face {i}: area={fc.area:.4f}  wires={len(fc.wires())} "
          f"lengths={[round(w.length, 6) for w in fc.wires()]}")
loops = toolplan._loops(faces, pl)
lim, centre = toolplan._limits(loops)
print(f"  _loops -> {len(loops)} loop(s), holes per loop: "
      f"{[len(L['holes']) for L in loops]}")
print(f"  has_holes = {lim['has_holes']}   (true ring area = "
      f"{3.14159265*(225-25):.2f})")
print(f"  centre={centre}  outer_radius={lim['outer_radius']}")

print()
print("=" * 72)
print("Plate with a bore (sketch_on_face ring) via the extrude plan")
print("=" * 72)
d2 = build(
    ("b", "plate", {"width": 60, "depth": 40, "thickness": 20}, []),
    ("s", "sketch_on_face", {"face": "top", "entities": [
        {"kind": "circle", "r": 15},
        {"kind": "circle", "r": 5, "mode": "subtract"}]}, ["b"]),
)
p = toolplan.plan(d2, {"tool": "extrude", "sketch_id": "s"})
print("  ok:", p.get("ok"), "error:", p.get("error"))
if p.get("ok"):
    print("  has_holes:", p["limits"]["has_holes"],
          " loops:", [(len(L["outer"]), len(L["holes"])) for L in p["loops"]])
    print("  origin:", p["origin"], " outer_radius:", p["limits"]["outer_radius"])

print()
print("=" * 72)
print("A face WITH a real hole: extrude_face on an annular top face")
print("=" * 72)
d3 = build(("t", "tube", {"outer_radius": 30, "inner_radius": 10, "height": 20}, []))
part = d3._parts["t"]
top = None
for fc in part.faces():
    pln = sk.face_plane(fc)
    if pln is not None and abs(pln.z_dir.Z - 1) < 1e-6:
        top = fc
        break
print(f"  top face: area={top.area:.4f}  wires={len(top.wires())} "
      f"lengths={[round(w.length, 6) for w in top.wires()]}")
fp = sk.face_plane(top)
loops = toolplan._loops([top], fp)
lim, _c = toolplan._limits(loops)
print(f"  _loops holes: {[len(L['holes']) for L in loops]}   "
      f"has_holes={lim['has_holes']}  (expect 1 / True)")
print(f"  outer poly points: {len(loops[0]['outer'])}")
