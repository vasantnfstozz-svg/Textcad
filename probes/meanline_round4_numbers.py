"""Round four: the numbers the new tests pin, printed from the real code.

Two tables:

  1. the inducer angle in the metal, for the duties the tests parametrize
     (`meanline.built_blade_angle` at the inlet eye radius, against the
     published `beta1_deg`);
  2. the nine wheels round three BUILT, with the choke ratio each one's
     KERNEL-measured passage earns — the both-sides evidence for the new
     flow rule, with no model anywhere in it.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402

DUTIES = [
    ("the shipped sample", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)),
    ("the MCP test duty", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000)),
    ("a small turbo", dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000)),
    ("a micro turbo", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000)),
    ("a big turbo", dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000)),
    ("an industrial stage", dict(mass_flow=5.0, pressure_ratio=2.5,
                                 rpm=15000)),
    ("a big industrial", dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000)),
    ("the largest measured", dict(mass_flow=50.0, pressure_ratio=2.0,
                                  rpm=3000)),
    ("backsweep 0", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                         backsweep_deg=0.0)),
    ("backsweep -60", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                           backsweep_deg=-60.0)),
    ("backsweep 74", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                          backsweep_deg=74.0)),
    ("the smallest wheel", dict(mass_flow=1e-3, pressure_ratio=1.2,
                                rpm=500000)),
]

# the nine wheels round three built, with the percentage the KERNEL read
KERNEL = [
    ("dead 3.21", dict(mass_flow=0.005, pressure_ratio=1.8, rpm=250000,
                       backsweep_deg=60.0), 3.21),
    ("dead 3.36", dict(mass_flow=0.005, pressure_ratio=1.1, rpm=100000,
                       backsweep_deg=35.0), 3.36),
    ("dead 6.55", dict(mass_flow=0.005, pressure_ratio=1.8, rpm=90000,
                       backsweep_deg=-20.0), 6.55),
    ("sound 16.06", dict(mass_flow=0.02, pressure_ratio=2.5, rpm=150000,
                         backsweep_deg=35.0), 16.06),
    ("sound 26.50", dict(mass_flow=0.005, pressure_ratio=4.0, rpm=90000,
                         backsweep_deg=0.0), 26.50),
    ("sound 31.37", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000,
                         backsweep_deg=35.0), 31.37),
    ("sound 37.43", dict(mass_flow=0.1, pressure_ratio=4.0, rpm=250000,
                         backsweep_deg=25.0), 37.43),
    ("sound 68.96", dict(mass_flow=20.0, pressure_ratio=2.5, rpm=5000,
                         backsweep_deg=35.0), 68.96),
    ("sound 70.71", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000,
                         backsweep_deg=35.0), 70.71),
]


if __name__ == "__main__":
    print("1. the inducer angle in the metal (built_blade_angle at r1s)")
    for name, kw in DUTIES:
        d = meanline.design(meanline.Duty(**kw))
        built = meanline.built_blade_angle(d, d.inducer_shroud_radius)
        rim = meanline.built_blade_angle(d, d.tip_radius)
        print(f'    ("{name}", {kw!r},'
              f' {d.inducer_shroud_radius / d.tip_radius:.3f},'
              f' {built:.2f}),   # b1 {d.beta1_deg} delta '
              f'{built - d.beta1_deg:+.2f}  rim {rim:.2f} vs {d.beta2_deg}'
              f'  note={"YES" if d.notes and "inducer angle" in d.notes[-1] else "no"}')

    print("\n2. the nine kernel-measured wheels against the flow rule")
    for name, kw, pct in KERNEL:
        d = meanline.design(meanline.Duty(**kw))
        inner = max(d.inducer_hub_radius, d.bore_radius)
        available = math.pi * (d.inducer_shroud_radius ** 2 - inner ** 2)
        open_mm2 = pct / 100.0 * available
        most = d.inlet_choke_flux * open_mm2
        print(f"    {name:<12} open {open_mm2:9.2f} mm2 of {available:9.2f}"
              f"   can pass {most:9.5f} kg/s   asked {d.mass_flow:g}"
              f"   ratio {d.mass_flow / most:7.2f}x"
              f"   {'REFUSED by the tenth' if pct < 10 else ''}"
              f"{'  REFUSED by the flow rule' if d.mass_flow > 2.0 * most and pct >= 10 else ''}")
