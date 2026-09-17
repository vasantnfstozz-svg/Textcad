"""Round three attacking round two's own two fixes.

1. Can `bore_material` read 0.000000 on a wheel that IS plugged? The
   adversarial shape the brief names: a blade that ENTERS the bore and comes
   out the other side, crossing the axis without filling the cylinder.
2. Does drilling the bore LAST hurt a user who edits the sample tree? The
   worry is a bore that now cuts through a blade and severs it. Built here
   through the real Document engine at three bore radii.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math                      # noqa: E402
import blocks                    # noqa: E402
import inspector                 # noqa: E402
import meanline                  # noqa: E402
import samples                   # noqa: E402
from build123d import Box, Cylinder, Pos   # noqa: E402

print("=== 1. a blade that crosses the bore without filling it ===")
d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                  rpm=45000))
t, L = d.backplate_thk, d.axial_length
room = math.pi * d.bore_radius ** 2 * (t + L)
hub = blocks.with_center_hole(
    blocks.revolve_profile([(0, 0), (d.tip_radius, 0), (d.tip_radius, t),
                            (d.inducer_hub_radius, t + L), (0, t + L)]),
    d.bore_radius)
print(f"  bore radius {d.bore_radius} mm, bore volume over the wheel "
      f"{room:,.2f} mm3, the check fires above {0.005*room:,.2f} mm3")
for thk in (4.0, 1.88, 0.5, 0.1, 0.02):
    # a plate straight through the middle of the bore, hub to hub
    bar = Pos(0, 0, (t + L) / 2.0) * Box(4.0 * d.tip_radius, thk, t + L)
    part = hub + (bar & Cylinder(radius=d.tip_radius, height=8.0 * (t + L)))
    plug = meanline.bore_material(part, d)
    prob = meanline.bore_problem(part, d)
    print(f"  a {thk:5.2f} mm bar across the bore: {plug:9.4f} mm3 measured "
          f"({100*plug/room:6.3f}% of the bore) -> "
          f"{'REFUSED' if prob else 'passed'}")

print()
print("=== 2. the sample tree with the bore edited bigger ===")
print("  (hub base radius 22, hub nose 10, blades 9 -> 40)")
for r in (6, 15, 25):
    doc = samples.sample_impeller()
    doc.features[-1].params["radius"] = r
    doc.rebuild()
    part = doc.result_shape()
    if part is None:
        print(f"  bore {r:2d}: no body — spec {doc.spec_problems}")
        continue
    m = inspector.measure(part)
    print(f"  bore {r:2d}: volume {m['volume']!r} solids {m['n_solids']} "
          f"manifold {m['is_manifold']} spec {doc.spec_problems}")
