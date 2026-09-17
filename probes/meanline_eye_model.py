"""The inlet-eye open area as arithmetic, CHECKED against the kernel.

A kernel build costs 12-50 s, so the corpus sweep needs a cheap predictor —
but a predictor is only worth using once it has been put against the real
booleans. `curved_blade` traces a ribbon of `thickness` along a camber line
whose angle runs linearly from `inlet_angle_deg` at `inner_radius` to
`exit_angle_deg` at `outer_radius`, so the metal it puts across the
circumference at radius r is Z * thickness / cos(beta(r)).

Kernel numbers to match (probes/meanline_eye_kernel.py):
    ship     0.5 kg/s PR3 45,000 rpm         passage 2132.558 mm2
    blocked  0.005 kg/s PR1.1 100,000 rpm    passage    3.509 mm2
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline as M   # noqa: E402


def open_eye_area(d, n=2000):
    """mm2 of the inlet annulus that is not blade metal."""
    r_in = 0.75 * d.inducer_hub_radius
    thk = max(0.02 * d.tip_radius, 1.5)
    lo = max(d.inducer_hub_radius, d.bore_radius)
    hi = d.inducer_shroud_radius
    if hi <= lo:
        return 0.0
    span = d.tip_radius - r_in
    out = 0.0
    dr = (hi - lo) / n
    for i in range(n):
        r = lo + (i + 0.5) * dr
        f = (r - r_in) / span if span > 0 else 0.0
        beta = math.radians(d.beta1_deg + (d.beta2_deg - d.beta1_deg) * f)
        metal = d.blade_count * thk / max(math.cos(beta), 1e-6)
        out += max(2.0 * math.pi * r - metal, 0.0) * dr
    return out


def ideal_eye_area(d):
    return math.pi * (d.inducer_shroud_radius ** 2
                      - d.inducer_hub_radius ** 2)


if __name__ == "__main__":
    for name, kw, kernel in (
            ("ship", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
             2132.558),
            ("blocked", dict(mass_flow=0.005, pressure_ratio=1.1, rpm=100000,
                             backsweep_deg=35.0), 3.509)):
        d = M.design(M.Duty(**kw))
        model = open_eye_area(d)
        print(f"{name:9s} model {model:10.3f} mm2   kernel {kernel:10.3f} mm2"
              f"   error {100*(model-kernel)/max(kernel,1e-9):+7.2f}%"
              f"   ideal {ideal_eye_area(d):10.3f}")
