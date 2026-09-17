"""Round four: does the advice in the new sentences actually work?

A refusal that names the wrong dial is worse than no sentence — round two
learned that with "a pressure ratio of 3" for a 10,000 kg/s duty. So both new
sentences are checked here by turning the dial they name and measuring.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402
from meanline_blade_angle_spline import (camber_spline,          # noqa: E402
                                         angle_at_radius)
from meanline_eye_choke import choke_flux, open_area_mm2         # noqa: E402


def eye_gap(d):
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    edge, _ = camber_spline(ri, ro, d.beta1_deg, d.beta2_deg)
    _r, beta = angle_at_radius(edge, d.inducer_shroud_radius)
    return beta - d.beta1_deg


def show(label, **kw):
    duty = meanline.Duty(**kw)
    try:
        d = meanline.design(duty)
    except ValueError as e:
        print(f"  {label:<34} REFUSED: {str(e)[:70]}...")
        return
    a_open, a_all = open_area_mm2(d)
    ratio = duty.mass_flow / (choke_flux(duty) * a_open) if a_open else 1e9
    print(f"  {label:<34} r2 {d.tip_radius:8.2f}  r1s/r2 "
          f"{d.inducer_shroud_radius / d.tip_radius:5.3f}  "
          f"angle gap {eye_gap(d):+7.2f} deg  open {100 * a_open / a_all:6.2f}%"
          f"  choke {ratio:6.2f}x")


if __name__ == "__main__":
    print("BLADE ANGLE — the sentence says LOWER THE SPEED:")
    for rpm in (180000, 120000, 90000, 60000, 30000):
        show(f"micro turbo at {rpm:,} rpm", mass_flow=0.05,
             pressure_ratio=1.8, rpm=rpm)
    print("\n  ...and raising the mass flow (the other dial):")
    for mf in (0.05, 0.1, 0.3, 1.0):
        show(f"{mf} kg/s at 180,000 rpm", mass_flow=mf, pressure_ratio=1.8,
             rpm=180000)

    print("\nCHOKED INLET — the sentence says LOWER THE SPEED or the "
          "PRESSURE RATIO:")
    for rpm in (90000, 60000, 40000, 25000, 15000):
        show(f"micro blower at {rpm:,} rpm", mass_flow=0.01,
             pressure_ratio=1.3, rpm=rpm)
    print()
    for pr in (1.3, 1.2, 1.1, 1.05):
        show(f"micro blower at PR {pr}", mass_flow=0.01, pressure_ratio=pr,
             rpm=90000)
    print()
    for mf in (0.01, 0.05, 0.2, 1.0):
        show(f"{mf} kg/s at PR 1.3, 90,000 rpm", mass_flow=mf,
             pressure_ratio=1.3, rpm=90000)

    print("\nROUND THREE's eye sentence says 'lower the speed or RAISE THE "
          "MASS FLOW,\nwhich makes the wheel bigger'. The wheel's radius is "
          "U2/omega and U2 does not\ndepend on the mass flow at all, so that "
          "half names a dial that moves the EYE, not the rim:")
    for mf in (0.005, 0.01, 0.02, 0.05, 0.1):
        show(f"{mf} kg/s at PR 1.1, 100,000 rpm", mass_flow=mf,
             pressure_ratio=1.1, rpm=100000)
    print()
    for rpm in (100000, 60000, 30000, 15000):
        show(f"0.005 kg/s at PR 1.1, {rpm:,} rpm", mass_flow=0.005,
             pressure_ratio=1.1, rpm=rpm)
