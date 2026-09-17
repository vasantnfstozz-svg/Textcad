"""probes/meanline_backsweep_sweep.py -- what the BACKSWEEP does to the size.

tests/test_mcp_server.py asserts that `meanline.design` answers for every
backsweep in (-60, 0, 25, 35, 45, 60, 70, 74) at 1.0 kg/s, PR 3, 40,000 rpm.
A size gate must not refuse any of those, so measure them before writing it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline  # noqa: E402

hdr = (f"{'beta':>7s} {'r2 mm':>12s} {'b2 mm':>10s} {'r1s':>10s} {'r1h':>9s} "
       f"{'b2/r2':>8s} {'r1s/r2':>8s} {'r1s/r1h':>8s} {'U2':>8s}")
print(hdr)
print("-" * len(hdr))
for beta in (-90, -80, -60, -30, 0, 25, 35, 45, 60, 70, 72, 73, 74, 74.3):
    try:
        d = meanline.design(meanline.Duty(mass_flow=1.0, pressure_ratio=3.0,
                                          rpm=40000, backsweep_deg=beta))
    except Exception as e:
        print(f"{beta:7.2f} REFUSED: {e}")
        continue
    print(f"{beta:7.2f} {d.tip_radius:12.2f} {d.exit_width:10.2f} "
          f"{d.inducer_shroud_radius:10.2f} {d.inducer_hub_radius:9.3f} "
          f"{d.exit_width / d.tip_radius:8.3f} "
          f"{d.inducer_shroud_radius / d.tip_radius:8.3f} "
          f"{d.inducer_shroud_radius / d.inducer_hub_radius:8.3f} "
          f"{d.tip_speed:8.1f}")
