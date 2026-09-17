"""Round four's census: every number the module publishes, put to the metal.

`mcp_server._design_compressor` hands an AI ten numbers and `d.report()` prints
eleven. This builds ONE wheel and measures the three that no check reads —

    exit_width_mm            the blade height at the rim
    inducer_shroud_radius_mm where the shroud cut starts, at the inlet plane
    inducer_hub_radius       the hub nose at the inlet plane

— so the census says "measured" or "not measured" on evidence rather than on
a reading of the code.

    python probes/meanline_round4_census.py micro
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build123d import Cylinder, Pos                              # noqa: E402

import meanline                                                  # noqa: E402

WHEELS = {
    "micro": dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    "sample": dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "blower": dict(mass_flow=0.01, pressure_ratio=1.3, rpm=90000),
}


def run(key):
    d = meanline.design(meanline.Duty(**WHEELS[key]))
    t, L = d.backplate_thk, d.axial_length
    t0 = time.time()
    rep = meanline.build_from_design(d)
    part = rep.part
    print(f"{key}: built in {time.time() - t0:.1f} s, ok={rep.ok}")
    if part is None:
        return

    # 1) the exit width: how tall is the metal at the rim, above the backplate?
    eps = min(0.02 * d.tip_radius, 0.3)
    shell = (Cylinder(radius=d.tip_radius, height=4.0 * (t + L))
             - Cylinder(radius=d.tip_radius - eps, height=4.0 * (t + L)))
    rim = part & shell
    bb = rim.bounding_box()
    print(f"  exit width : published {d.exit_width:8.3f} mm   metal at the "
          f"rim {bb.max.Z - t:8.3f} mm   (rim band {eps:.2f} mm wide, "
          f"backplate {t} mm)")

    # 2) the inlet eye radius: the outermost metal in the inlet plane's slab
    h = min(0.02, L / 500.0)
    slab = part & (Pos(0, 0, t + L - h / 2.0)
                   * Cylinder(radius=4.0 * d.tip_radius, height=h))
    reach = max(math.hypot(v.X, v.Y) for v in slab.vertices())
    print(f"  inlet eye  : published {d.inducer_shroud_radius:8.3f} mm   "
          f"metal reaches {reach:8.3f} mm at the inlet plane")

    # 3) the hub nose at the inlet plane, and the bore that may have eaten it
    inner = min((math.hypot(v.X, v.Y) for v in slab.vertices()), default=0.0)
    print(f"  hub nose   : published {d.inducer_hub_radius:8.3f} mm   "
          f"bore {d.bore_radius:.3f} mm   innermost metal in the inlet plane "
          f"{inner:8.3f} mm")

    # 4) ROUND THREE's slab, attacked: is the INLET PLANE the right place to
    #    read the passage, or can a blade shape hide its blockage below it?
    #    The blades are extruded straight up, so their plan shape is the same
    #    at every height; this measures it instead of assuming it.
    #
    #    MEASURED on the micro turbo: 58.41% at t+0.4L, 48.42, 36.10, and
    #    31.37% at the inlet plane — the fraction FALLS as the station rises,
    #    because the hub shrinks and the annulus grows inward, into the radii
    #    where the blades take the most. The top is the tightest reading, so a
    #    blade shape cannot hide blockage below it. (The ring below t+L is
    #    bounded by the SHROUD LINE, which has already moved out past r1s, so
    #    the mm2 printed at those stations is cut off at r1s and is not the
    #    passage there — the percentages are what this is measuring.)
    print("  the passage at five heights (the rule reads the top one):")
    r1s = d.inducer_shroud_radius
    for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
        z_top = t + L * frac
        z_mid = z_top - h / 2.0
        hub_r = d.tip_radius - (d.tip_radius - d.inducer_hub_radius) \
            * ((z_mid - t) / L)
        avail = math.pi * (r1s ** 2 - max(hub_r, d.bore_radius) ** 2)
        free = (Pos(0, 0, z_mid) * Cylinder(radius=r1s, height=h)) - part
        open_mm2 = (float(free.volume) / h - math.pi * d.bore_radius ** 2
                    if free is not None else 0.0)
        print(f"    z = t + {frac:.1f} L : open {open_mm2:9.2f} mm2 of "
              f"{avail:9.2f}   {100 * open_mm2 / avail:6.2f}%"
              f"   (hub {max(hub_r, d.bore_radius):6.2f} mm)")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "micro")
