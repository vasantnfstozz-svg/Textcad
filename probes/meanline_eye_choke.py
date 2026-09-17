"""Round four: is a TENTH of the ring the right line, or is the line physics?

Round three refuses a wheel whose inlet passage is under 10% of its own eye
annulus, and justifies the number with an aerodynamic sentence: "below a tenth
the wheel's own inlet velocity is supersonic several times over". But the rule
itself knows nothing about the duty — and the velocity does. The SAME 10% is
an easy inlet on a 5,000 rpm industrial wheel and an impossible one on a
250,000 rpm micro turbo, because the air has to move through it at
mdot / (rho * A).

The line with no taste in it at all is CHOKING: the largest mass flow any
opening can pass, from stagnation, is

    mdot_max = A * P01/sqrt(T01) * sqrt(gamma/R) * (2/(gamma+1))**((g+1)/(2(g-1)))
             = A * 241.3 kg/s/m2   for air at 288.15 K and 101,325 Pa

A wheel whose measured passage cannot pass its own duty's mass flow is not a
wheel that flows badly — it is a wheel that CANNOT DO THE DUTY, at any speed,
in any casing. This puts both rules to the same 6,273-design grid and asks:

  * how many wheels does the tenth PASS that cannot pass their own flow?
  * how many does it REFUSE that can?

The open area comes from the calibrated model in
`probes/meanline_eye_model_round4.py` (worst error 2.72 points against nine
kernel-built wheels, and conservative on all nine).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402
from meanline_eye_model_round4 import camber, beta_metal         # noqa: E402


def open_area_mm2(d):
    """(open mm2, available mm2) the model's answer for `eye_passage`."""
    r1s = d.inducer_shroud_radius
    inner = max(d.inducer_hub_radius, d.bore_radius)
    if r1s <= inner:
        return 0.0, 0.0
    thk = max(0.02 * d.tip_radius, 1.5)
    steps = 400
    area_open, area_all = 0.0, 0.0
    dr = (r1s - inner) / steps
    cache = camber(d)
    for i in range(steps):
        r = inner + (i + 0.5) * dr
        c = math.cos(math.radians(beta_metal(d, r, cache)))
        blocked = 1.0 if c <= 1e-6 else d.blade_count * thk / (
            2.0 * math.pi * r * c)
        ring = 2.0 * math.pi * r * dr
        area_all += ring
        area_open += ring * max(0.0, 1.0 - blocked)
    return area_open, area_all


def choke_flux(duty):
    """kg/s per mm2 the inlet can pass at most, from this duty's stagnation
    state (isentropic choked mass flux)."""
    g, R = duty.gamma, duty.R
    gmax = (duty.P01 / math.sqrt(duty.T01) * math.sqrt(g / R)
            * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0))))
    return gmax * 1e-6


FLOWS = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0,
         20.0, 50.0]
PRS = [1.1, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
RPMS = [3000, 5000, 8000, 15000, 25000, 40000, 60000, 90000, 120000, 180000,
        250000]
SWEEPS = [-20.0, 0.0, 25.0, 35.0, 45.0, 60.0]


def main():
    passed_impossible, refused_possible, both = [], [], 0
    designed = 0
    for mf in FLOWS:
        for pr in PRS:
            for rpm in RPMS:
                for bs in SWEEPS:
                    duty = meanline.Duty(mass_flow=mf, pressure_ratio=pr,
                                         rpm=rpm, backsweep_deg=bs)
                    try:
                        d = meanline.design(duty)
                    except ValueError:
                        continue
                    designed += 1
                    a_open, a_all = open_area_mm2(d)
                    if a_all <= 0:
                        continue
                    f = a_open / a_all
                    passes = f >= meanline._EYE_OPEN_FRACTION
                    can_flow = mf <= choke_flux(duty) * a_open
                    if passes and not can_flow:
                        passed_impossible.append((f, mf / (choke_flux(duty)
                                                           * a_open),
                                                  mf, pr, rpm, bs,
                                                  d.tip_radius))
                    if not passes and can_flow:
                        refused_possible.append((f, mf / (choke_flux(duty)
                                                          * a_open),
                                                 mf, pr, rpm, bs,
                                                 d.tip_radius))
                    if passes and can_flow:
                        both += 1
    print(f"{designed} designs in the grid")
    print(f"  the tenth PASSES and the air can get in : {both}")
    print(f"  the tenth PASSES, the flow CANNOT       : "
          f"{len(passed_impossible)}")
    print(f"  the tenth REFUSES, the flow could       : "
          f"{len(refused_possible)}")
    passed_impossible.sort(key=lambda row: -row[1])
    print("\nworst wheels the tenth passes that cannot pass their own flow "
          "(choke ratio = duty / what the passage can pass):")
    for f, ratio, mf, pr, rpm, bs, r2 in passed_impossible[:15]:
        print(f"  open {100 * f:6.2f}%  choke ratio {ratio:7.2f}x  "
              f"{mf:>8g} kg/s PR{pr:<4g} {rpm:>7g} rpm {bs:>5g} deg  "
              f"r2 {r2:8.2f}")
    refused_possible.sort(key=lambda row: row[1])
    print("\nwheels the tenth refuses whose passage could pass the flow:")
    for f, ratio, mf, pr, rpm, bs, r2 in refused_possible[:15]:
        print(f"  open {100 * f:6.2f}%  choke ratio {ratio:7.2f}x  "
              f"{mf:>8g} kg/s PR{pr:<4g} {rpm:>7g} rpm {bs:>5g} deg  "
              f"r2 {r2:8.2f}")
    # and the corpus the tests bless
    print("\nthe sound corpus, against both rules:")
    for name, kw in [
            ("the shipped sample", dict(mass_flow=0.5, pressure_ratio=3.0,
                                        rpm=45000)),
            ("the MCP test duty", dict(mass_flow=1.0, pressure_ratio=3.0,
                                       rpm=40000)),
            ("a small turbo", dict(mass_flow=0.1, pressure_ratio=2.0,
                                   rpm=120000)),
            ("a micro turbo", dict(mass_flow=0.05, pressure_ratio=1.8,
                                   rpm=180000)),
            ("a big turbo", dict(mass_flow=2.0, pressure_ratio=4.0,
                                 rpm=25000)),
            ("an industrial stage", dict(mass_flow=5.0, pressure_ratio=2.5,
                                         rpm=15000)),
            ("a big industrial", dict(mass_flow=20.0, pressure_ratio=3.5,
                                      rpm=8000)),
            ("the largest measured", dict(mass_flow=50.0, pressure_ratio=2.0,
                                          rpm=3000)),
            ("round three 16.06%", dict(mass_flow=0.02, pressure_ratio=2.5,
                                        rpm=150000)),
            ("round three 26.50%", dict(mass_flow=0.005, pressure_ratio=4.0,
                                        rpm=90000, backsweep_deg=0.0)),
            ("round three 37.43%", dict(mass_flow=0.1, pressure_ratio=4.0,
                                        rpm=250000, backsweep_deg=25.0))]:
        duty = meanline.Duty(**kw)
        d = meanline.design(duty)
        a_open, a_all = open_area_mm2(d)
        ratio = duty.mass_flow / (choke_flux(duty) * a_open)
        print(f"  {name:<22} open {100 * a_open / a_all:6.2f}%  "
              f"choke ratio {ratio:6.2f}x  "
              f"({'CHOKED' if ratio > 1 else 'flows'})")


if __name__ == "__main__":
    main()
