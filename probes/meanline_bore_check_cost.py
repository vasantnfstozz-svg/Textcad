"""probes/meanline_bore_check_cost.py -- what does it COST to actually measure
that the shaft bore is a hole?

`to_spec` checks symmetry, solid count and tip radius, and a wheel with a
plugged bore passes all three (round one's P0). The only definitive answer is
a boolean: intersect the finished wheel with the bore cylinder and read the
volume. Before putting that in `build_from_design` on every build, measure it.

    C:/Python314/python.exe probes/meanline_bore_check_cost.py [sample|micro]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector   # noqa: E402
import meanline    # noqa: E402
from build123d import Cylinder  # noqa: E402

DUTIES = {
    "sample": dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "micro":  dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    # the two ends of the band the round-one bound NEWLY ALLOWS (2000 ->
    # 10,000 mm). The corpus only tests refusals, so the newly allowed wheels
    # have to be put to the kernel WITH the round-two bore check on them.
    "big":    dict(mass_flow=50.0, pressure_ratio=2.0, rpm=1500),
    "huge":   dict(mass_flow=50.0, pressure_ratio=2.0, rpm=325.3597),
    "rpm1000": dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1000),
}

which = sys.argv[1] if len(sys.argv) > 1 else "sample"
d = meanline.design(meanline.Duty(**DUTIES[which]))
print(f"{which}: r2 {d.tip_radius} mm, bore {d.bore_radius} mm, "
      f"Z {d.blade_count}")
for n in d.notes:
    print(f"  NOTE: {n}")
t0 = time.perf_counter()
rep = meanline.build_from_design(d)
t_build = time.perf_counter() - t0
print(f"  build_from_design ok={rep.ok} in {t_build:.1f} s   "
      f"problems={rep.all_problems()}")

part = rep.part
if part is not None:
    m = inspector.measure(part)
    print(f"  volume={m['volume']!r} faces={m['n_faces']} "
          f"solids={m['n_solids']} manifold={m['is_manifold']} "
          f"max_radius={m.get('max_radius')}")
    for i in range(2):
        t0 = time.perf_counter()
        plug = part & Cylinder(radius=d.bore_radius,
                               height=8.0 * d.axial_length)
        vol = float(plug.volume) if plug is not None else 0.0
        print(f"  bore intersection #{i + 1}: {vol:.6f} mm3 in "
              f"{time.perf_counter() - t0:.2f} s")
