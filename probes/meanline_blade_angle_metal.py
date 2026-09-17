"""Round four: the blade angle IN THE METAL, by boolean, not by arithmetic.

`probes/meanline_blade_angle_spline.py` reads the camber curve. This one reads
the SOLID `meanline.one_blade` hands the pattern: a thin annular shell at each
radius, intersected with the blade; the centre of mass of that chunk is the
camber point there, and the angle between two of them is the blade angle

    beta(r) = atan( r * dtheta/dr )

which is the definition `blocks.curved_blade`'s own docstring integrates. No
model, no spline: what a probe on the finished part would read.

    python probes/meanline_blade_angle_metal.py sample
    python probes/meanline_blade_angle_metal.py micro
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build123d import Cylinder, Pos                              # noqa: E402

import meanline                                                  # noqa: E402

DUTIES = {
    "sample": dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "micro": dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    "big": dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000),
    "mcp": dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000),
}


def theta_at(blade, r, band, height):
    """Angular position of the blade's camber at radius r, by intersection."""
    shell = (Cylinder(radius=r + band / 2.0, height=height)
             - Cylinder(radius=r - band / 2.0, height=height))
    try:
        chunk = blade & (Pos(0, 0, height / 2.0) * shell)
    except Exception:
        return None
    if chunk is None or chunk.volume <= 0:
        return None
    c = chunk.center()
    return math.atan2(c.Y, c.X), float(chunk.volume)


def run(key):
    d = meanline.design(meanline.Duty(**DUTIES[key]))
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    print(f"{key}: r2 {ro:.2f}  ri {ri:.2f}  beta1 {d.beta1_deg}  "
          f"beta2 {d.beta2_deg}  thk {max(0.02 * ro, 1.5):.2f}  "
          f"L {d.axial_length:.2f}")
    t0 = time.time()
    blade = meanline.one_blade(d)
    print(f"  blade built in {time.time() - t0:.1f} s, "
          f"volume {blade.volume:,.3f} mm3")
    band = (ro - ri) / 200.0
    # the ribbon's ROUNDED CAPS are trimmed by the tip cylinder and by the
    # bore, so a station inside a blade-thickness of either end measures the
    # cap, not the camber: on the micro turbo, 0.30 mm inside a 1.50 mm thick
    # rim reads -15.50 degrees. Both end stations stand two thicknesses clear.
    thk = max(0.02 * ro, 1.5)
    stations = [("inlet (+2 thk)", max(ri, d.bore_radius) + 2.0 * thk),
                ("25%", ri + 0.25 * (ro - ri)),
                ("50%", ri + 0.50 * (ro - ri)),
                ("75%", ri + 0.75 * (ro - ri)),
                ("exit (-2 thk)", ro - 2.0 * thk)]
    for label, r in stations:
        step = 0.01 * (ro - ri)
        a = theta_at(blade, r - step / 2.0, band, d.axial_length)
        b = theta_at(blade, r + step / 2.0, band, d.axial_length)
        if a is None or b is None:
            print(f"  {label:<16} r={r:8.2f}  (no metal)")
            continue
        dth = b[0] - a[0]
        while dth > math.pi:
            dth -= 2 * math.pi
        while dth < -math.pi:
            dth += 2 * math.pi
        beta = math.degrees(math.atan2(r * dth, step))
        pub = d.beta1_deg + (d.beta2_deg - d.beta1_deg) * (r - ri) / (ro - ri)
        print(f"  {label:<16} r={r:8.2f}  MEASURED {beta:8.2f} deg   "
              f"published {pub:7.2f}   delta {beta - pub:+7.2f}")
    print(f"  total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "sample")
