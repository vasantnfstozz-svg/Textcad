"""probes/meanline_bore_reach.py -- does the blade reach into the SHAFT BORE?

`build_from_design` (and samples.sample_compressor) drills the bore into the
HUB and then fuses the blades on top, so any blade material that reaches
inside the bore radius fills the hole back in -- silently, because the spec
never measures the bore.

The blade's inner end is NOT at `inner_radius`: `blocks.curved_blade` traces a
ribbon of `thickness` around the camber line and the ribbon's cap overshoots
inwards by an amount that depends on the blade angle, not just the thickness.
So the reach is BISECTED with real booleans, never predicted.

    C:/Python314/python.exe probes/meanline_bore_reach.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import blocks        # noqa: E402
import meanline      # noqa: E402
from build123d import Cylinder  # noqa: E402

DUTIES = [
    ("SHIPPED sample",  dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)),
    ("mcp test duty",   dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000)),
    ("a small turbo",   dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000)),
    ("a micro turbo",   dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000)),
    ("a big turbo",     dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000)),
    ("an industrial",   dict(mass_flow=5.0, pressure_ratio=2.5, rpm=15000)),
    ("big industrial",  dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000)),
    ("largest measured", dict(mass_flow=50.0, pressure_ratio=2.0, rpm=3000)),
    ("blower PR1.3",    dict(mass_flow=0.5, pressure_ratio=1.3, rpm=45000)),
]

meanline._check_wheel = lambda d, duty=None: None

hdr = (f"{'duty':18s} {'r2':>9s} {'r_in':>8s} {'thk':>6s} {'bore':>8s} "
       f"{'reach':>8s} {'in bore mm3':>12s}  verdict")
print(hdr)
print("-" * len(hdr))
for name, kw in DUTIES:
    t0 = time.time()
    d = meanline.design(meanline.Duty(**kw))
    r_in = 0.75 * d.inducer_hub_radius
    thk = max(0.02 * d.tip_radius, 1.5)
    one = blocks.curved_blade(inner_radius=r_in, outer_radius=d.tip_radius,
                              inlet_angle_deg=d.beta1_deg,
                              exit_angle_deg=d.beta2_deg,
                              height=d.axial_length, thickness=thk)

    def inside(radius):
        got = one & Cylinder(radius=radius, height=8.0 * d.axial_length)
        return got.volume if got is not None else 0.0

    # bisect the smallest radius that still catches material
    lo, hi = 0.0, r_in
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        if inside(mid) > 1e-9:
            hi = mid
        else:
            lo = mid
    reach = hi
    in_bore = inside(d.bore_radius)
    verdict = "BORE BLOCKED" if in_bore > 1e-9 else "bore clear"
    print(f"{name:18s} {d.tip_radius:9.2f} {r_in:8.4f} {thk:6.3f} "
          f"{d.bore_radius:8.3f} {reach:8.4f} {in_bore:12.4f}  {verdict} "
          f"({time.time() - t0:.1f}s)")
