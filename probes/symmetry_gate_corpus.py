"""Old verdict vs new on every live design with a symmetry spec (read-only)."""
import glob, json, sys, time
sys.path.insert(0, ".")
import build123d as b3d, document, inspector
for p in sorted(glob.glob("designs/*.tcad.json")):
    data = json.loads(open(p, encoding="utf-8").read())
    spec = data.get("spec") or {}
    n = spec.get("symmetry")
    if not n:
        continue
    doc = document.Document.from_data(data); doc.spec = None; doc.rebuild()
    shape = doc.result_shape()
    if shape is None:
        print(f"{p:40s} no result shape"); continue
    t0 = time.perf_counter(); new = inspector.is_rotationally_symmetric(shape, n); t_new = time.perf_counter() - t0
    t0 = time.perf_counter()
    rot = shape.rotate(b3d.Axis.Z, 360.0 / n)
    old = (shape - rot).volume <= 1e-3 * shape.volume
    t_old = time.perf_counter() - t0
    flag = "" if old == new else "   <-- DIFFERS"
    print(f"{p:40s} n={n:2d} solids={len(shape.solids())} old={old!s:5s} {t_old*1000:6.0f} ms  new={new!s:5s} {t_new*1000:6.0f} ms{flag}")
