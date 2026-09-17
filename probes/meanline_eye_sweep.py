"""Kernel-measured inlet passage across the whole band the model predicts.

A threshold has to be earned on BOTH sides, so this builds real wheels at
model-predicted 5 / 10 / 20 / 30 / 40 / 55 / 73 percent open and measures what
the passage actually is. One child, one wheel at a time.

    C:/Python314/python.exe probes/meanline_eye_sweep.py <index>
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import inspector   # noqa: E402
import meanline    # noqa: E402
from meanline_eye_model import open_eye_area, ideal_eye_area  # noqa: E402
from build123d import Cylinder, Pos  # noqa: E402

DUTIES = [
    ("p05", dict(mass_flow=0.005, pressure_ratio=1.8, rpm=250000,
                 backsweep_deg=60.0)),
    ("p10", dict(mass_flow=0.005, pressure_ratio=1.8, rpm=90000,
                 backsweep_deg=-20.0)),
    ("p20", dict(mass_flow=0.02, pressure_ratio=2.5, rpm=150000,
                 backsweep_deg=35.0)),
    ("p30", dict(mass_flow=0.005, pressure_ratio=4.0, rpm=90000,
                 backsweep_deg=0.0)),
    ("p40", dict(mass_flow=0.1, pressure_ratio=4.0, rpm=250000,
                 backsweep_deg=25.0)),
    ("p55", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000,
                 backsweep_deg=35.0)),
    ("p73", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000,
                 backsweep_deg=35.0)),
]


def passage(part, d):
    """mm2 of the inlet annulus that is open, measured with a boolean."""
    t, L = d.backplate_thk, d.axial_length
    h = min(0.05, L / 100.0)
    z = t + L - 0.02 * L
    slab = Pos(0, 0, z - h / 2.0) * Cylinder(radius=d.inducer_shroud_radius,
                                             height=h)
    free = slab - part
    area = (float(free.volume) / h) if free is not None else 0.0
    return area - math.pi * d.bore_radius ** 2


idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
name, kw = DUTIES[idx]
d = meanline.design(meanline.Duty(**kw))
ideal = ideal_eye_area(d)
model = open_eye_area(d)
print(f"{name}: {kw}")
print(f"  r2 {d.tip_radius}  Z {d.blade_count}  r1h {d.inducer_hub_radius} "
      f"r1s {d.inducer_shroud_radius}  bore {d.bore_radius}  "
      f"thk {max(0.02*d.tip_radius, 1.5):.2f}  beta1 {d.beta1_deg}")
print(f"  ideal annulus {ideal:.3f} mm2   model open {model:.3f} "
      f"({100*model/max(ideal,1e-9):.2f}%)")
t0 = time.perf_counter()
rep = meanline.build_from_design(d)
dt = time.perf_counter() - t0
print(f"  build ok={rep.ok} in {dt:.1f} s  problems={rep.all_problems()}")
if rep.part is None:
    sys.exit(0)
m = inspector.measure(rep.part)
print(f"  volume={m['volume']!r} solids={m['n_solids']} "
      f"manifold={m['is_manifold']} health={inspector.health(rep.part)}")
t1 = time.perf_counter()
a = passage(rep.part, d)
print(f"  KERNEL passage {a:.3f} mm2 = {100*a/max(ideal,1e-9):.2f}% of ideal"
      f"   (measurement cost {time.perf_counter()-t1:.2f} s of a {dt:.1f} s "
      f"build)")
