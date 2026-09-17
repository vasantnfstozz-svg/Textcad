"""How open the inlet eye is across the duties both gates accept.

Uses the kernel-checked model in probes/meanline_eye_model.py (73.3% modelled
against 69.3% measured on the shipped wheel; 4.9% against 3.1% on the dead
one), so the fractions below are right to a few points — enough to see whether
there is a BAND or a CLIFF, which is what a threshold has to be earned by.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline as M                       # noqa: E402
from meanline_eye_model import (open_eye_area,   # noqa: E402
                                ideal_eye_area)

FLOW = [0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 20.0, 50.0]
PR = [1.05, 1.1, 1.3, 1.8, 2.5, 4.0, 6.0]
RPM = [500, 1500, 5000, 15000, 45000, 90000, 150000, 250000]
BS = [-20.0, 0.0, 25.0, 35.0, 45.0, 60.0]

rows = []
for f in FLOW:
    for p in PR:
        for n in RPM:
            for b in BS:
                try:
                    d = M.design(M.Duty(mass_flow=f, pressure_ratio=p, rpm=n,
                                        backsweep_deg=b))
                except ValueError:
                    continue
                ideal = ideal_eye_area(d)
                if ideal <= 0:
                    rows.append((0.0, f, p, n, b, d))
                    continue
                rows.append((open_eye_area(d) / ideal, f, p, n, b, d))

rows.sort(key=lambda r: r[0])
print(f"duties accepted by design() today: {len(rows)}")
edges = [0.0, .01, .05, .10, .20, .30, .40, .50, .60, .70, .80, 1.01]
for lo, hi in zip(edges, edges[1:]):
    k = sum(1 for r in rows if lo <= r[0] < hi)
    print(f"  open/ideal {lo:5.2f}..{hi:5.2f} : {k:5d}"
          + ("   <-- shipped wheel" if lo <= 0.733 < hi else ""))
print()
print("the 8 least open, and the duty that made them:")
for r in rows[:8]:
    d = r[5]
    print(f"  {r[0]*100:6.2f}%  {r[1]:g} kg/s PR{r[2]:g} {r[3]:g} rpm bs{r[4]:g}"
          f" | r2 {d.tip_radius:8.2f} Z {d.blade_count:2d} r1h "
          f"{d.inducer_hub_radius:7.2f} r1s {d.inducer_shroud_radius:8.2f} "
          f"bore {d.bore_radius:6.2f} thk {max(0.02*d.tip_radius,1.5):5.2f}")
print()
print("duties straddling 10/20/30/40% (candidates for a kernel check):")
for want in (0.05, 0.10, 0.20, 0.30, 0.40, 0.55):
    best = min(rows, key=lambda r: abs(r[0] - want))
    d = best[5]
    print(f"  ~{want*100:.0f}% -> {best[0]*100:6.2f}%  {best[1]:g} kg/s "
          f"PR{best[2]:g} {best[3]:g} rpm bs{best[4]:g} | r2 "
          f"{d.tip_radius:8.2f} Z {d.blade_count:2d} r1s "
          f"{d.inducer_shroud_radius:8.2f}")
print()
big = [r for r in rows if r[5].tip_radius >= 75.0]
print(f"wheels at or above 75 mm radius (thickness scales with r2): {len(big)}"
      f"  least open {min(r[0] for r in big)*100:.2f}%")
small = [r for r in rows if r[5].tip_radius < 75.0]
print(f"wheels under 75 mm radius (the 1.5 mm floor rules): {len(small)}"
      f"  least open {min(r[0] for r in small)*100:.2f}%"
      f"  under 20% open: {sum(1 for r in small if r[0] < 0.2)}")
