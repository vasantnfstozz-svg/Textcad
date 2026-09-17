"""The inlet passage, measured at the INLET PLANE and against what is there
to be blocked.

The first sweep (meanline_eye_sweep.py) read a slab 2% of the wheel's depth
below the top and got 0.000 mm2 on a duty whose annulus is 0.86 mm wide: the
hub cone grows by (r2-r1h)*0.02 in that distance, which on that wheel is the
whole annulus. The station is the TOP of the wheel, z = t+L, where the hub is
exactly r1h -- and the honest denominator is what the slab would hold with the
hub alone, so the hub's own growth across the slab cancels.

    C:/Python314/python.exe probes/meanline_eye_sweep2.py <index>
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
    ("ship", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000,
                  backsweep_deg=35.0)),
    ("blocked", dict(mass_flow=0.005, pressure_ratio=1.1, rpm=100000,
                     backsweep_deg=35.0)),
    ("big", dict(mass_flow=20.0, pressure_ratio=2.5, rpm=5000,
                 backsweep_deg=35.0)),
]


def eye(part, d):
    """(passage mm2, available mm2) at the inlet plane, both by boolean."""
    t, L = d.backplate_thk, d.axial_length
    h = min(0.02, L / 500.0)
    z_mid = t + L - h / 2.0
    slab = Pos(0, 0, z_mid) * Cylinder(radius=d.inducer_shroud_radius, height=h)
    free = slab - part
    open_a = (float(free.volume) / h) if free is not None else 0.0
    hub_r = d.tip_radius - (d.tip_radius - d.inducer_hub_radius) * \
        ((z_mid - t) / L)
    inner = max(hub_r, d.bore_radius)
    avail = math.pi * (d.inducer_shroud_radius ** 2 - inner ** 2)
    return open_a - math.pi * d.bore_radius ** 2, max(avail, 0.0)


idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
name, kw = DUTIES[idx]
d = meanline.design(meanline.Duty(**kw))
ideal = ideal_eye_area(d)
model = open_eye_area(d)
print(f"{name}: {kw}")
print(f"  r2 {d.tip_radius}  Z {d.blade_count}  r1h {d.inducer_hub_radius} "
      f"r1s {d.inducer_shroud_radius}  bore {d.bore_radius}  "
      f"thk {max(0.02*d.tip_radius, 1.5):.2f}  beta1 {d.beta1_deg}")
print(f"  design annulus {ideal:.3f} mm2   model open {model:.3f} "
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
p, avail = eye(rep.part, d)
print(f"  KERNEL passage {p:.3f} mm2 of an available {avail:.3f} mm2 "
      f"= {100*p/max(avail,1e-9):.2f}%   (and {100*p/max(ideal,1e-9):.2f}% of "
      f"the design's annulus)   cost {time.perf_counter()-t1:.2f} s")
