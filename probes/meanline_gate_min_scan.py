"""probes/meanline_gate_min_scan.py -- is `_R2_MIN_MM = 1.0` mm too high?

No kernel: a wide grid of duties, gate patched out, looking for the SMALLEST
tip radius that survives the other two rules (exit width < r2, inlet eye < r2).
If nothing real lands near 1 mm the lower bound refuses nothing, and the whole
question is closed by arithmetic instead of by a 90-second build.

    C:/Python314/python.exe probes/meanline_gate_min_scan.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline  # noqa: E402

meanline._check_wheel = lambda d, duty=None: None

FLOWS = [1e-6, 1e-5, 1e-4, 1e-3, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 20.0, 50.0]
PRS = [1.05, 1.1, 1.2, 1.5, 1.8, 2.0, 3.0, 4.0, 6.0, 10.0]
RPMS = [1e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6, 1e7, 1e8]

rows = []
for w in FLOWS:
    for pr in PRS:
        for rpm in RPMS:
            try:
                d = meanline.design(meanline.Duty(mass_flow=w,
                                                  pressure_ratio=pr, rpm=rpm))
            except ValueError:
                continue
            if d.exit_width >= d.tip_radius:
                continue
            if d.inducer_shroud_radius >= d.tip_radius:
                continue
            rows.append((d.tip_radius, w, pr, rpm, d.exit_width,
                         d.inducer_shroud_radius, max(0.02 * d.tip_radius, 1.5)))

rows.sort()
print(f"{len(rows)} duties out of {len(FLOWS) * len(PRS) * len(RPMS)} pass the "
      f"exit-width and inlet-eye rules.")
print(f"\nthe 15 SMALLEST wheels among them (the lower bound is "
      f"{meanline._R2_MIN_MM} mm):")
print(f"{'r2 mm':>9s} {'flow':>9s} {'PR':>6s} {'rpm':>10s} {'b2':>7s} "
      f"{'eye':>8s} {'blade thk':>10s}  thk > r2?")
for r2, w, pr, rpm, b2, eye, thk in rows[:15]:
    print(f"{r2:9.3f} {w:9g} {pr:6g} {rpm:10g} {b2:7.2f} {eye:8.2f} "
          f"{thk:10.2f}  {thk > r2}")

print(f"\nthe 5 LARGEST (the upper bound is {meanline._R2_MAX_MM} mm):")
for r2, w, pr, rpm, b2, eye, thk in rows[-5:]:
    print(f"{r2:9.1f} {w:9g} {pr:6g} {rpm:10g} {b2:7.2f} {eye:8.2f} "
          f"{thk:10.2f}")
