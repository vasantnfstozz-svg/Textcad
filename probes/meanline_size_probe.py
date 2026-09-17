"""probes/meanline_size_probe.py -- what does meanline.design actually ANSWER?

No kernel. Sweeps duties: the sound ones this repo ships and the user's own
plausible band, then the impossible ones LAUNCH-PLAN s10 records. Prints every
number a size gate could read, so the gate's bounds are measured, not taste.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline


ROWS = [
    # name,                  flow,  PR,     rpm
    ("SHIPPED sample",        0.5,  3.0,   45000),
    ("mcp test duty",         1.0,  3.0,   40000),
    ("turbo small",           0.1,  2.0,  120000),
    ("turbo tiny",           0.05,  1.8,  180000),
    ("turbo big",             2.0,  4.0,   25000),
    ("industrial",            5.0,  2.5,   15000),
    ("big industrial",       20.0,  3.5,    8000),
    ("huge slow",            50.0,  2.0,    3000),
    ("low PR sane",           0.5,  1.05,  45000),
    ("PR 1.2",                0.5,  1.2,   45000),
    ("--- impossible ---",   None, None,    None),
    ("rpm 1",                 0.5,  3.0,       1),
    ("rpm 10",                0.5,  3.0,      10),
    ("rpm 100",               0.5,  3.0,     100),
    ("rpm 1000",              0.5,  3.0,    1000),
    ("PR 1.001",              0.5,  1.001, 45000),
    ("PR 1.01",               0.5,  1.01,  45000),
    ("tiny flow",            1e-6,  3.0,   45000),
    ("huge flow",           1e4,    3.0,   45000),
    ("rpm 1e9",               0.5,  3.0,     1e9),
]

hdr = (f"{'duty':22s} {'r2 mm':>12s} {'b2 mm':>10s} {'r1s':>10s} "
       f"{'r1h':>8s} {'L':>10s} {'Z':>3s} {'b2/r2':>8s} {'r1s/r2':>8s} "
       f"{'r_in-2':>9s} {'U2 m/s':>9s} {'kW':>10s}")
print(hdr)
print("-" * len(hdr))
for name, w, pr, rpm in ROWS:
    if w is None:
        print(name)
        continue
    try:
        d = meanline.design(meanline.Duty(mass_flow=w, pressure_ratio=pr,
                                          rpm=rpm))
    except Exception as e:
        print(f"{name:22s} REFUSED: {type(e).__name__}: {e}")
        continue
    r_in = 0.75 * d.inducer_hub_radius
    print(f"{name:22s} {d.tip_radius:12.2f} {d.exit_width:10.2f} "
          f"{d.inducer_shroud_radius:10.2f} {d.inducer_hub_radius:8.3f} "
          f"{d.axial_length:10.2f} {d.blade_count:3d} "
          f"{d.exit_width/d.tip_radius:8.3f} "
          f"{d.inducer_shroud_radius/d.tip_radius:8.3f} "
          f"{r_in - 2.0:9.2f} {d.tip_speed:9.1f} {d.power_kw:10.1f}")
