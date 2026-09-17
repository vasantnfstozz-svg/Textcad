"""probes/meanline_gate_sentences.py -- read the refusals out loud.

Every sentence a user or an AI now gets back from an impossible duty, plus the
proof that the shipped compressor sample is untouched to the last decimal.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector  # noqa: E402
import meanline  # noqa: E402
import samples  # noqa: E402

CASES = [
    ("rpm 1",        dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1)),
    ("rpm 1000",     dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1000)),
    ("rpm 1e9",      dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1e9)),
    ("PR 1.001",     dict(mass_flow=0.5, pressure_ratio=1.001, rpm=45000)),
    ("PR 1.05",      dict(mass_flow=0.5, pressure_ratio=1.05, rpm=45000)),
    ("PR 1.2",       dict(mass_flow=0.5, pressure_ratio=1.2, rpm=45000)),
    ("10,000 kg/s",  dict(mass_flow=1e4, pressure_ratio=3.0, rpm=45000)),
    ("backsweep -80", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                           backsweep_deg=-80.0)),
]
print("=== the sentences ===")
for name, kw in CASES:
    try:
        meanline.design(meanline.Duty(**kw))
        print(f"{name:15s} NOT REFUSED")
    except ValueError as e:
        print(f"{name:15s} {e}")

print("\n=== the shipped sample, unchanged? ===")
doc = samples.sample_compressor()
cutter = [f for f in doc.features if f.id == "shroud_cutter"][0]
print(f"  shroud_cutter points: {cutter.params['points']}")
t0 = time.perf_counter()
ok = doc.rebuild()
res = doc.result()
m = inspector.measure(res)
print(f"  rebuild ok={ok} in {time.perf_counter() - t0:.2f} s")
print(f"  volume={m['volume']!r}  faces={len(res.faces())}  "
      f"solids={m['n_solids']}  health={inspector.health(res)}")
print("  before the change (probes/compressor_rebuild_cost.py, 2026-09-17): "
      "volume=428259.878 faces=69 n_solids=1")
