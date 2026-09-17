"""The exact numbers for the duties that replace the five the new eye rule
refuses, so the tests pin measurements rather than guesses."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline as M   # noqa: E402

CAND = [
    ("clamp, micrometres + N times", dict(mass_flow=1e-4, pressure_ratio=1.5,
                                          rpm=50000)),
    ("clamp, micrometres + N times b", dict(mass_flow=1e-4,
                                            pressure_ratio=1.5, rpm=20000)),
    ("clamp, under a micrometre + thousands",
     dict(mass_flow=1e-5, pressure_ratio=5.0, rpm=20000)),
    ("gate reads the clamped width", dict(mass_flow=1e-5, pressure_ratio=2.0,
                                          rpm=60000)),
    ("the smallest wheel left", dict(mass_flow=1e-3, pressure_ratio=1.2,
                                     rpm=500000)),
]
for name, kw in CAND:
    d = M.design(M.Duty(**kw))
    ratio = d.exit_width / d.exit_width_ideal if d.exit_width_ideal else 0.0
    print(f"{name}: {kw}")
    print(f"   r2 {d.tip_radius}  r1h {d.inducer_hub_radius}  r1s "
          f"{d.inducer_shroud_radius}  bore {d.bore_radius}  Z {d.blade_count}")
    print(f"   b2 {d.exit_width}  ideal {d.exit_width_ideal:.10f}  "
          f"ratio {ratio:,.6f}  L {d.axial_length}")
    print(f"   notes: {d.notes}")
