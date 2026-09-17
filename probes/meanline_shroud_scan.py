"""probes/meanline_shroud_scan.py -- ROUND TWO: what ELSE can `to_spec` not
see? It checks symmetry, solid count, tip radius and height. The SHROUD CUT is
not among them, and the shroud cutter's line runs from (r1s, t+L) DOWN to
(r2, t+b2) -- so if `exit_width` ever came out at or above the axial length the
line would run the other way, the cut would take nothing off the rim, and the
wheel's exit width would silently not be the design's.

Pure arithmetic over a wide grid of duties: every one that passes every gate is
checked for b2 >= L, and for whether its width was CLAMPED (in which case
`CompressorDesign.notes` already speaks). No kernel.

    C:/Python314/python.exe probes/meanline_shroud_scan.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline  # noqa: E402

flows = [1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.05, 0.1, 0.5, 1.0, 5.0, 20.0, 50.0,
         200.0, 1000.0]
ratios = [1.01, 1.05, 1.2, 1.5, 1.8, 2.0, 3.0, 4.0, 6.0, 10.0, 20.0]
speeds = [300, 1000, 3000, 10000, 45000, 120000, 300000, 1e6, 3e6, 1e7]
sweeps = [-60.0, -30.0, 0.0, 25.0, 35.0, 45.0, 60.0, 74.0]

designed = clamped = flat = flat_unclamped = 0
worst = []
for mdot in flows:
    for pr in ratios:
        for rpm in speeds:
            for beta in sweeps:
                try:
                    d = meanline.design(meanline.Duty(
                        mass_flow=mdot, pressure_ratio=pr, rpm=rpm,
                        backsweep_deg=beta))
                except ValueError:
                    continue
                designed += 1
                was_clamped = bool(d.notes)
                clamped += was_clamped
                if d.exit_width >= d.axial_length:
                    flat += 1
                    if not was_clamped:
                        flat_unclamped += 1
                        worst.append((mdot, pr, rpm, beta, d.tip_radius,
                                      d.exit_width, d.axial_length))
print(f"duties tried  : {len(flows) * len(ratios) * len(speeds) * len(sweeps)}")
print(f"designed      : {designed}")
print(f"width clamped : {clamped}  (the note fires on every one)")
print(f"b2 >= L       : {flat}   -- the shroud cut takes nothing off the rim")
print(f"  of those, NOT clamped (so nothing would say so): {flat_unclamped}")
for row in worst[:20]:
    print(f"    mdot={row[0]:g} PR={row[1]:g} rpm={row[2]:g} beta={row[3]:g} "
          f"-> r2={row[4]} b2={row[5]} L={row[6]}")

# the smallest and largest wheel anything in the grid reaches, for the record
sizes = []
for mdot in flows:
    for pr in ratios:
        for rpm in speeds:
            try:
                d = meanline.design(meanline.Duty(mass_flow=mdot,
                                                  pressure_ratio=pr, rpm=rpm))
            except ValueError:
                continue
            sizes.append(d.tip_radius)
print(f"\nr2 reached at the default backsweep: {min(sizes):.2f} .. "
      f"{max(sizes):.2f} mm over {len(sizes)} duties")
