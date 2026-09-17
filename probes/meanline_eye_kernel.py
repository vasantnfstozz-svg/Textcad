"""ROUND THREE: is the INLET EYE the design publishes an opening in the metal?

`inducer_shroud_radius_mm` leaves through the MCP door beside `exit_width_mm`.
Round two proved the exit width can be 39% wrong with every check green. The
inlet eye is the same kind of number from the other end of the wheel: it is
what the machine INGESTS, and nothing measures it against the built solid —
`to_spec` pins symmetry, solid count, tip radius and overall height only.

The measurement: a thin slab across the inlet station (just under the top of
the wheel), inside the published eye radius. Everything in that slab that is
NOT the wheel is passage. Divided by the slab height it is the open axial area
at the inlet, which is the number an eye radius is a claim about.

    C:/Python314/python.exe probes/meanline_eye_kernel.py <case>
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector   # noqa: E402
import meanline    # noqa: E402
from build123d import Cylinder, Pos  # noqa: E402

CASES = {
    # the shipped sample — the reference for what a sound eye measures
    "ship":    dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "micro":   dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    # arithmetic (probes/meanline_eye_band.py) says the annulus is solid metal
    "blocked": dict(mass_flow=0.005, pressure_ratio=1.1, rpm=100000,
                    backsweep_deg=35.0),
    "blocked2": dict(mass_flow=0.005, pressure_ratio=1.1, rpm=150000,
                     backsweep_deg=25.0),
    "half":    dict(mass_flow=0.02, pressure_ratio=1.3, rpm=100000,
                    backsweep_deg=35.0),
}

name = sys.argv[1] if len(sys.argv) > 1 else "blocked"
d = meanline.design(meanline.Duty(**CASES[name]))
t, L = d.backplate_thk, d.axial_length
r1h, r1s = d.inducer_hub_radius, d.inducer_shroud_radius
print(f"CASE {name}: {CASES[name]}")
print(f"  r2 {d.tip_radius}  Z {d.blade_count}  t {t}  L {L}  b2 {d.exit_width}")
print(f"  eye: r1h {r1h}  r1s {r1s}  bore {d.bore_radius}  beta1 {d.beta1_deg}")
print(f"  blade thickness {max(0.02 * d.tip_radius, 1.5):.2f}")
ideal = math.pi * (r1s ** 2 - r1h ** 2)
print(f"  annulus area the continuity equation asked for: {ideal:.3f} mm2")

t0 = time.perf_counter()
rep = meanline.build_from_design(d)
print(f"  build ok={rep.ok} in {time.perf_counter() - t0:.1f} s  "
      f"problems={rep.all_problems()}")
part = rep.part
if part is None:
    sys.exit(0)
m = inspector.measure(part)
print(f"  volume={m['volume']!r} faces={m['n_faces']} solids={m['n_solids']} "
      f"manifold={m['is_manifold']} size={m['size']}")
print(f"  health={inspector.health(part)}")
print(f"  {d.blade_count}-fold symmetric: "
      f"{inspector.is_rotationally_symmetric(part, d.blade_count)}")

h = min(0.05, L / 100.0)
for frac in (0.02, 0.15, 0.40):
    z_top = t + L - frac * L
    slab = Pos(0, 0, z_top - h) * Cylinder(radius=r1s, height=h,
                                           align=(None, None, None))
    # Cylinder aligns centred by default; place it explicitly
    slab = Cylinder(radius=r1s, height=h)
    slab = Pos(0, 0, z_top - h / 2.0) * slab
    free = slab - part
    open_area = (float(free.volume) / h) if free is not None else 0.0
    bore_area = math.pi * d.bore_radius ** 2
    print(f"  station z={z_top:.3f} ({frac*100:.0f}% down from the top): "
          f"open area {open_area:9.3f} mm2  (the shaft bore is "
          f"{bore_area:.3f} of it) -> passage {open_area - bore_area:9.3f} mm2"
          f"  = {100.0 * (open_area - bore_area) / ideal:6.2f}% of the "
          f"{ideal:.3f} mm2 the design asked for")
