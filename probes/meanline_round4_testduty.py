"""Round four: the duty the tenth-of-the-ring test needs.

`test_the_eye_rule_cuts_where_the_measurements_put_it` pins the 10% line with
a synthetic wheel blocked to 8% and to 12%. On the shipped sample's duty the
12% wheel is now refused by the FLOW rule instead (369.25 mm2 can pass 0.089
kg/s and the duty asks 0.5), so the test would be pinning the wrong rule. This
finds duties where the tenth is the rule that bites — low pressure ratio, where
the air the eye has to swallow is slow — so both rules keep a test of their own.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402

if __name__ == "__main__":
    print(f"{'duty':<34} {'r2':>8} {'ring mm2':>10} {'8%':>8} {'12%':>8} "
          f"  verdicts")
    for mf, pr, rpm in ((0.5, 1.15, 10000), (0.5, 1.15, 15000),
                        (1.0, 1.15, 10000), (0.5, 1.1, 12000),
                        (0.2, 1.15, 20000), (2.0, 1.15, 6000)):
        try:
            d = meanline.design(meanline.Duty(mass_flow=mf,
                                              pressure_ratio=pr, rpm=rpm))
        except ValueError as e:
            print(f"{mf} kg/s PR{pr} {rpm} rpm  REFUSED: {str(e)[:60]}")
            continue
        inner = max(d.inducer_hub_radius, d.bore_radius)
        ring = math.pi * (d.inducer_shroud_radius ** 2 - inner ** 2)
        out = []
        for f in (0.08, 0.12):
            most = d.inlet_choke_flux * f * ring
            out.append(f"{'choked' if mf > 2.0 * most else 'flows'}"
                       f"({mf / most:4.1f}x)")
        print(f"{mf} kg/s PR{pr} {rpm} rpm{'':<8} {d.tip_radius:8.2f} "
              f"{ring:10.1f} {0.08 * ring:8.1f} {0.12 * ring:8.1f}   "
              f"{out[0]:>16} {out[1]:>16}")
