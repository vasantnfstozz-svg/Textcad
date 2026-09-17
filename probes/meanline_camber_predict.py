"""Round four: can meanline PREDICT the built blade angle without the kernel?

`design()` runs with no geometry, so the sentence it publishes about the blade
has to be arithmetic. This checks that arithmetic — a centred difference on the
same 17-point polyline `blocks.curved_blade` integrates — against the OCCT
spline's own tangent (probes/meanline_blade_angle_spline.py), which was itself
checked against the metal with real booleans
(probes/meanline_blade_angle_metal.py: 48.3 interpolated vs 47.99 predicted at
the shipped sample's eye radius).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402
from meanline_blade_angle_spline import (DUTIES, camber_spline,  # noqa: E402
                                         angle_at_radius)


def polyline_angle(d, radius):
    """The camber's angle from radial at `radius`, from the polyline alone."""
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    b1, b2 = d.beta1_deg, d.beta2_deg
    n = 16
    rs, ths, theta = [], [], 0.0
    for i in range(n + 1):
        t = i / n
        rs.append(ri + (ro - ri) * t)
        ths.append(theta)
        if i < n:
            beta = math.radians(b1 + (b2 - b1) * t)
            theta += math.tan(beta) / rs[-1] * ((ro - ri) / n)
    # Each Euler step is the arc of a LOGARITHMIC SPIRAL — the curve of
    # constant blade angle — and the angle of the one that joins the two nodes
    # is atan(dtheta / ln(r2/r1)). That is the segment's own angle; the curve's
    # angle at a NODE is the average of the segments either side (which is
    # what an interpolating spline's tangent does), and in between it is
    # linear in r.
    seg = [math.degrees(math.atan2(ths[i + 1] - ths[i],
                                   math.log(rs[i + 1] / rs[i])))
           for i in range(n)]
    node = [seg[0]] + [0.5 * (seg[i - 1] + seg[i]) for i in range(1, n)] \
        + [seg[-1]]
    step = (ro - ri) / n
    x = min(max((radius - ri) / step, 0.0), float(n))
    i = min(int(x), n - 1)
    f = x - i
    return node[i] + (node[i + 1] - node[i]) * f


if __name__ == "__main__":
    print(f"{'duty':<22} {'station':>10} {'spline':>8} {'polyline':>9} "
          f"{'delta':>7}")
    worst = 0.0
    for name, kw in DUTIES:
        d = meanline.design(meanline.Duty(**kw))
        ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
        edge, _ = camber_spline(ri, ro, d.beta1_deg, d.beta2_deg)
        for label, r in (("eye", d.inducer_shroud_radius),
                         ("rim", ro - 0.02 * (ro - ri))):
            _rr, spline = angle_at_radius(edge, r)
            poly = polyline_angle(d, r)
            worst = max(worst, abs(spline - poly))
            print(f"{name:<22} {label:>10} {spline:8.2f} {poly:9.2f} "
                  f"{spline - poly:+7.2f}")
    print(f"\nworst polyline-vs-spline disagreement: {worst:.2f} degrees")
