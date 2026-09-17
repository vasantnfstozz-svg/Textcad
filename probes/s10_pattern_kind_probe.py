"""probes/s10_pattern_kind_probe.py — what a pattern actually DOES when it is
fed something that is not a solid body, measured before the gate is written.

The §10 P3 row names `linear_pattern` / `polar_pattern`. `mirror` is the third
member of pattern.SEEDED_OPS, so it is measured here too: a gate that takes
away something that works today would be worse than the wrong sentence.

Run:  C:\\Python314\\python.exe probes\\s10_pattern_kind_probe.py
"""
import sys

sys.path.insert(0, ".")

import document                                           # noqa: E402
from document import Document, n_solids                   # noqa: E402
import sketch as sk                                       # noqa: E402

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
TWO = [{"kind": "circle", "x": -15, "y": 0, "r": 5, "mode": "add"},
       {"kind": "circle", "x": 15, "y": 0, "r": 5, "mode": "add"}]

CASES = [
    ("linear_pattern", {"count": 3, "dx": 20}),
    ("polar_pattern", {"count": 4, "axis": "+z", "radius": 20}),
    ("polar_pattern", {"count": 4}),
    ("mirror", {"plane": "YZ"}),
    ("fillet", {"radius": 1, "edges": "all"}),
    ("shell", {"thickness": 1}),
    ("scale", {"factor": 2}),
    ("rotate", {"axis": "Z", "angle_deg": 45}),
]

for entities, label in ((ONE, "one circle"), (TWO, "two circles (a Compound)")):
    print("\n" + "=" * 72)
    print(f"sketch: {label}")
    print("=" * 72)
    probe = Document(name="k")
    probe.add("s1", "sketch", {"entities": entities, "plane": "XY", "offset": 0.0}, [])
    probe.rebuild()
    part = probe._parts["s1"]
    print(f"  type={type(part).__name__}  is_sketch={sk.is_sketch(part)}  "
          f"n_solids={n_solids(part)}  area={getattr(part, 'area', None)}")
    for op, params in CASES:
        d = Document(name="k")
        d.add("s1", "sketch", {"entities": entities, "plane": "XY", "offset": 0.0}, [])
        d.add("p1", op, params, ["s1"])
        d.rebuild()
        f = d.get("p1")
        vol = f.volume
        print(f"  {op:16s} {str(params)[:34]:36s} -> {f.status:7s} vol={vol}")
        for pr in (f.problems or []):
            print(f"      {pr}")

print("\n" + "=" * 72)
print("a SOLID still patterns (the behaviour a gate must not take away)")
print("=" * 72)
for op, params in (("linear_pattern", {"count": 3, "dx": 20}),
                   ("polar_pattern", {"count": 4, "axis": "+z"}),
                   ("mirror", {"plane": "YZ"})):
    d = Document(name="s")
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.add("p1", op, params, ["b1"])
    d.rebuild()
    f = d.get("p1")
    print(f"  {op:16s} -> {f.status:7s} vol={f.volume} pieces={f.pieces} {f.problems}")

print("\n" + "=" * 72)
print("n_solids of every SKETCH_PRODUCER's output (the gate's test)")
print("=" * 72)
print(" ", sorted(sk.SKETCH_PRODUCERS))
print("  pattern.SEEDED_OPS", document.pattern.SEEDED_OPS)
print("  pattern.PATTERN_OPS", document.pattern.PATTERN_OPS)
