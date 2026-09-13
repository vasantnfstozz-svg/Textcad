"""Two costs a kernel sidecar lives or dies by.

  (a) a COLD child: how long does a fresh python that imports build123d take
      before it can do any work? If that is seconds, the sidecar must be a
      persistent, pre-warmed worker, not a subprocess per call.
  (b) a BIG body: the overnight run's slow findings are traced-PNG keychains of
      600-670 faces. If a .brep round trip of one of those costs seconds, the
      sidecar is too expensive for the ops that are already fast.

Run serially. Never beside another OCCT workload.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SCRATCH = ROOT / "probes" / "_sidecar_tmp"
SCRATCH.mkdir(exist_ok=True)

# --- (a) cold child ---------------------------------------------------------
print("=== cold child: a fresh python importing build123d")
for i in range(3):
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "-c",
                    "import build123d, time; print(time.time())"],
                   capture_output=True, check=True)
    print(f"  run {i + 1}: {(time.perf_counter() - t0) * 1000:8.0f} ms")

print("\n=== cold child: python with NOTHING imported (the floor)")
for i in range(2):
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "-c", "pass"], capture_output=True, check=True)
    print(f"  run {i + 1}: {(time.perf_counter() - t0) * 1000:8.0f} ms")

# --- (b) a big traced body --------------------------------------------------
from build123d import Part, export_brep, import_brep      # noqa: E402
from document import Document                             # noqa: E402

BEFORE = ROOT / "bugs" / "20260913-014525-rocky-keychain-2-s46966-step15" / "before.tcad.json"
print(f"\n=== big body from {BEFORE.name}")
t0 = time.perf_counter()
doc = Document.from_data(json.loads(BEFORE.read_text(encoding="utf-8")))
doc.rebuild()
print(f"  whole-document rebuild: {(time.perf_counter() - t0) * 1000:.0f} ms")

bodies = doc.result_bodies()
print(f"  {len(bodies)} result bodies")
rows = []
for i, b in enumerate(bodies):
    part = Part(b.wrapped) if not isinstance(b, Part) else b
    nf, ne = len(part.faces()), len(part.edges())
    path = SCRATCH / f"big_{i}.brep"
    t0 = time.perf_counter()
    export_brep(part, str(path))
    tw = time.perf_counter() - t0
    t0 = time.perf_counter()
    back = Part(import_brep(str(path)).wrapped)
    tr = time.perf_counter() - t0
    same_e = [round(e.length, 9) for e in part.edges()] == [round(e.length, 9) for e in back.edges()]
    same_f = [round(f.area, 9) for f in part.faces()] == [round(f.area, 9) for f in back.faces()]
    print(f"  body {i}: faces {nf:4d} edges {ne:4d}  {path.stat().st_size / 1024:8.1f} kB  "
          f"write {tw * 1000:7.1f} ms  read {tr * 1000:7.1f} ms  "
          f"edge order {same_e}  face order {same_f}")
    rows.append(dict(body=i, faces=nf, edges=ne, kb=round(path.stat().st_size / 1024, 1),
                     write_ms=round(tw * 1000, 1), read_ms=round(tr * 1000, 1),
                     edge_order=same_e, face_order=same_f))

(SCRATCH / "cost.json").write_text(json.dumps(rows, indent=1))
print("\nwrote", SCRATCH / "cost.json")
