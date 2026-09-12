"""Gate ideas for is_rotationally_symmetric, measured on the bottle cap that ate the box.
Read-only on designs/ (Document.from_data, never /api/open)."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import build123d as b3d
import document, inspector

data = json.loads((ROOT / "designs/bottle_cap_28mm.tcad.json").read_text(encoding="utf-8"))
doc = document.Document.from_data(data)
doc.spec = None
doc.rebuild()
cap = doc.result_shape()
print("cap:", type(cap).__name__, len(cap.solids()), "solids", len(cap.vertices()), "vertices", round(cap.volume, 2))
print("SkipClean:", hasattr(b3d, "SkipClean"))

def gates(shape, n, tol=1e-3):
    t0 = time.perf_counter()
    rot = shape.rotate(b3d.Axis.Z, 360.0 / n)
    bb, rb = shape.bounding_box(), rot.bounding_box()
    scale = max(bb.size.X, bb.size.Y, bb.size.Z, 1.0)
    bbox_ok = all(abs(a - b) <= tol * scale for a, b in
                  zip((bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z),
                      (rb.min.X, rb.min.Y, rb.min.Z, rb.max.X, rb.max.Y, rb.max.Z)))
    t1 = time.perf_counter()
    solids = shape.solids()
    bad = 0
    for v in shape.vertices():
        p = v.rotate(b3d.Axis.Z, 360.0 / n).center()
        d = shape.distance_to(p)
        if d > tol * scale and not any(s.is_inside(p) for s in solids):
            bad += 1
    t2 = time.perf_counter()
    return bbox_ok, bad, round((t1 - t0) * 1000), round((t2 - t1) * 1000)

print("cap n=24 gates (bbox_ok, off-vertices, bbox ms, vertex ms):", gates(cap, 24))
print("cap n=23 gates:", gates(cap, 23))
t0 = time.perf_counter(); print("cap n=24 boolean verdict:", inspector.is_rotationally_symmetric(cap, 24), round(time.perf_counter() - t0, 2), "s")

plate = b3d.Box(67.9, 16.9, 6.4)
cyl = b3d.Cylinder(8.3, 7.2, align=(b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN))
comp = b3d.Compound([cap, cyl, plate])
print("cap+cyl+plate n=24 gates:", gates(comp, 24))

# the rule-4 check: a SYMMETRIC compound with overlapping members (disc through the wall)
disc = b3d.Cylinder(25, 5, align=(b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN))
comp2 = b3d.Compound([cap, disc])
print("cap+overlapping disc n=24 gates:", gates(comp2, 24))
t0 = time.perf_counter()
with b3d.SkipClean():
    diff = comp2.cut(comp2.rotate(b3d.Axis.Z, 15))
print("cap+disc boolean (no clean):", round(diff.volume, 4), round(time.perf_counter() - t0, 2), "s")
t0 = time.perf_counter()
with b3d.SkipClean():
    diff = cap.cut(cap.rotate(b3d.Axis.Z, 15))
print("cap alone boolean (no clean):", round(diff.volume, 4), round(time.perf_counter() - t0, 2), "s")
