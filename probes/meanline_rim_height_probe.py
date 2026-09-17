"""probes/meanline_rim_height_probe.py -- ROUND TWO: is the exit blade width
the design REPORTS the exit blade width the wheel HAS?

`to_spec` pins symmetry, solid count, tip radius and overall height. It says
nothing about the exit width, and the shroud cutter's line runs from
(r1s, t+L) DOWN to (r2, t+b2). `probes/meanline_shroud_scan.py` found 43 duties
in a 12,320-duty grid that pass every gate with b2 >= L and an UNCLAMPED width
-- the line then runs UPWARD, the cut takes nothing off the rim, and the blades
keep their full height there. Whether that is really what the kernel builds is
a question only measurement answers.

The rim height is measured by cutting a thin outer shell off the finished wheel
and reading its Z extent: everything above the backplate in that shell is blade.

    C:/Python314/python.exe probes/meanline_rim_height_probe.py <case>

    micro   a normal duty -- proves the MEASUREMENT before it is trusted
    flat    0.05 kg/s, PR 1.01, 10,000 rpm, 25 deg: r2 35.66, b2 17.29, L 12.48
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector   # noqa: E402
import meanline    # noqa: E402
from build123d import Cylinder  # noqa: E402

CASES = {
    "micro": dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    "flat":  dict(mass_flow=0.05, pressure_ratio=1.01, rpm=10000,
                  backsweep_deg=25.0),
    "flat2": dict(mass_flow=0.5, pressure_ratio=1.01, rpm=3000,
                  backsweep_deg=35.0),
}

name = sys.argv[1] if len(sys.argv) > 1 else "micro"
d = meanline.design(meanline.Duty(**CASES[name]))
t, L = d.backplate_thk, d.axial_length
print(f"CASE {name}: {CASES[name]}")
print(f"  r2 {d.tip_radius}  backplate t {t}  axial L {L}  "
      f"exit width b2 {d.exit_width}  Z {d.blade_count}")
print(f"  b2 >= L ? {d.exit_width >= L}   notes={d.notes}")

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

big = 8.0 * (t + L)
for band in (0.5, 1.0):
    shell = (part & Cylinder(radius=d.tip_radius, height=big)) \
        - Cylinder(radius=d.tip_radius - band, height=big)
    if shell is None or shell.volume <= 0:
        print(f"  rim band {band} mm: nothing there")
        continue
    bb = shell.bounding_box()
    print(f"  rim band {band:.1f} mm: material from z={bb.min.Z:.3f} to "
          f"z={bb.max.Z:.3f}  -> blade height at the rim "
          f"{bb.max.Z - t:.3f} mm   (design says {d.exit_width}, "
          f"axial length is {L})")
