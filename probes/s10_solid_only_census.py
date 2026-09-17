"""probes/s10_solid_only_census.py — round TWO of the review of 15eff19..9de0dc2.

Two questions, measured before a line of the gate is written:

  §1  EVERY modifier fed a SKETCH: what does the user actually read? The
      §10 row named `fillet` and `shell`; the rule says census the whole
      family, and every op the gate would newly refuse must first be shown
      to be genuinely solid-only.
  §2  the same ops fed a real SOLID, so the gate can be proven not to take
      away work that is correct today.
  §3  a numeric parameter that is null or "" in a LOADED file.

Run:  C:\\Python314\\python.exe probes\\s10_solid_only_census.py
"""
import sys

sys.path.insert(0, ".")

from document import Document, n_solids            # noqa: E402
import sketch as sk                                # noqa: E402
import inspector                                   # noqa: E402

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
TWO = [{"kind": "circle", "x": -15, "y": 0, "r": 5, "mode": "add"},
       {"kind": "circle", "x": 15, "y": 0, "r": 5, "mode": "add"}]

# every MODIFIER with params that are sensible for its own job
CASES = [
    ("with_center_hole", {"radius": 2}),
    ("with_bolt_circle", {"count": 4, "bolt_radius": 1, "pitch_circle_dia": 14}),
    ("fillet", {"radius": 1, "edges": "all"}),
    ("chamfer", {"length": 1, "edges": "all"}),
    ("shell", {"thickness": 1}),
    ("hole", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
              "diameter": 3, "depth": 2}),
    ("extrude_face", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                      "amount": 3}),
    ("revolve_face", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                      "angle": 90}),
    ("sketch_on_face", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                        "entities": ONE}),
    ("scale", {"factor": 2}),
    ("rotate", {"axis": "Z", "angle_deg": 45}),
    ("mirror", {"plane": "YZ"}),
]


def sketch_doc(entities):
    d = Document(name="k")
    d.add("s1", "sketch", {"entities": entities, "plane": "XY", "offset": 0.0}, [])
    return d


print("=" * 78)
print("§1  every modifier fed a SKETCH")
print("=" * 78)
for entities, label in ((ONE, "one circle"), (TWO, "two circles (a Compound)")):
    probe = sketch_doc(entities)
    probe.rebuild()
    part = probe._parts["s1"]
    print(f"\n-- sketch: {label}  type={type(part).__name__} "
          f"is_sketch={sk.is_sketch(part)} n_solids={n_solids(part)} "
          f"area={inspector._try(lambda: part.area)}")
    for op, params in CASES:
        d = sketch_doc(entities)
        d.add("p1", op, params, ["s1"])
        d.rebuild()
        f = d.get("p1")
        print(f"  {op:18s} -> {f.status:7s} vol={f.volume}")
        for pr in (f.problems or []):
            print(f"        {pr}")

print()
print("=" * 78)
print("§2  the same ops fed a real SOLID (20x20x5 plate) — must all still work")
print("=" * 78)
for op, params in CASES:
    d = Document(name="s")
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.add("p1", op, params, ["b1"])
    d.rebuild()
    f = d.get("p1")
    print(f"  {op:18s} -> {f.status:7s} vol={f.volume} pieces={f.pieces} "
          f"{f.problems or ''}")

print()
print("=" * 78)
print("§3  a numeric parameter that is null or \"\" in a LOADED file")
print("=" * 78)
for op, params, ins in (
        ("extrude", {"amount": None}, "sketch"),
        ("extrude", {"amount": ""}, "sketch"),
        ("extrude", {"amount": 4, "taper": None}, "sketch"),
        ("fillet", {"radius": None, "edges": "all"}, "solid"),
        ("fillet", {"radius": ""}, "solid"),
        ("scale", {"factor": None}, "solid"),
        ("rotate", {"angle_deg": None}, "solid"),
        ("linear_pattern", {"count": None, "dx": 10}, "solid"),
        ("polar_pattern", {"count": ""}, "solid"),
        ("shell", {"thickness": None}, "solid"),
        ("chamfer", {"length": None}, "solid"),
        ("with_center_hole", {"radius": None}, "solid"),
        ("hole", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                  "diameter": None}, "solid"),
):
    if ins == "sketch":
        d = sketch_doc(ONE)
        src = "s1"
    else:
        d = Document(name="s")
        d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
        src = "b1"
    d.add("p1", op, params, [src])
    d.rebuild()
    f = d.get("p1")
    print(f"  {op:16s} {str(params)[:44]:46s} -> {f.status}")
    for pr in (f.problems or []):
        print(f"        {pr}")
