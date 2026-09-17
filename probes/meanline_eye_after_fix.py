"""The other half of the guard: the wheels it must NOT refuse, through the
real `build_from_design` with the eye check wired in.

    C:/Python314/python.exe probes/meanline_eye_after_fix.py <case>

    ship     0.5 kg/s PR3 45,000 rpm   (the shipped sample: 428,226.425 mm3)
    micro    0.05 kg/s PR1.8 180,000   (the module's own micro turbo)
    blocked  0.005 kg/s PR1.1 100,000  (the P0: must now be refused)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector   # noqa: E402
import meanline    # noqa: E402

CASES = {
    "ship": dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "micro": dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    "blocked": dict(mass_flow=0.005, pressure_ratio=1.1, rpm=100000,
                    backsweep_deg=35.0),
}

name = sys.argv[1] if len(sys.argv) > 1 else "ship"
d = meanline.design(meanline.Duty(**CASES[name]))
t0 = time.perf_counter()
rep = meanline.build_from_design(d)
print(f"{name}: ok={rep.ok} in {time.perf_counter() - t0:.1f} s")
for p in rep.all_problems():
    print(f"   problem: {p}")
if rep.part is not None:
    m = inspector.measure(rep.part)
    print(f"   volume {m['volume']!r}  faces {m['n_faces']}  "
          f"solids {m['n_solids']}  manifold {m['is_manifold']}  "
          f"size {m['size']}  max_radius {m.get('max_radius')}")
    print(f"   eye passage {meanline.eye_passage(rep.part, d)}")
    print(f"   bore material {meanline.bore_material(rep.part, d):.6f} mm3")
