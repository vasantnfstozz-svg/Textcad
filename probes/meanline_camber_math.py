"""Round four: what ANGLES does `blocks.curved_blade` actually draw?

`meanline.design` publishes `beta1_deg` and `beta2_deg` to an AI through
`mcp_server._design_compressor`, and until this round nothing compared them to
the blade the kernel cuts. `blocks.curved_blade` integrates the camber law
    d(theta) = tan(beta)/r * dr,   beta linear from beta1 (at ri) to beta2 (ro)
with FORWARD EULER over n=16 steps, and the geometry is a spline through those
17 points. This probe is arithmetic only: Euler's polyline against the exact
integral, for every wheel `meanline` designs.

The step ratio is FIXED by construction and is the same on every wheel:
    ri = 0.75 * r1h = 0.75 * 0.105 * r2 = 0.07875 * r2,  ro = r2
so dr/ri = (1 - 0.07875)/16/0.07875 = 0.7311 — the first step advances the
radius by 73% of itself, and the turn it takes is tan(beta1) * 0.7311 radians.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402

N = 16


def euler_points(ri, ro, b1, b2, n=N):
    pts, theta = [], 0.0
    thetas = [0.0]
    for i in range(n):
        t = i / n
        r = ri + (ro - ri) * t
        beta = math.radians(b1 + (b2 - b1) * t)
        theta += math.tan(beta) / r * ((ro - ri) / n)
        thetas.append(theta)
        pts.append(r)
    pts.append(ro)
    return pts, thetas


def exact_theta(ri, ro, b1, b2, steps=200000):
    """theta(r) by fine integration of the same law (midpoint rule)."""
    theta, out = 0.0, [0.0]
    dr = (ro - ri) / steps
    for i in range(steps):
        t = (i + 0.5) / steps
        r = ri + (ro - ri) * t
        beta = math.radians(b1 + (b2 - b1) * t)
        theta += math.tan(beta) / r * dr
        out.append(theta)
    return theta


def chord_angle(r0, th0, r1, th1):
    """Angle from the radial direction at (r0,th0) of the chord to (r1,th1).

    This is what the spline's own end tangent follows: an interpolating spline
    leaves its first point along (very close to) the first chord.
    """
    p0 = (r0 * math.cos(th0), r0 * math.sin(th0))
    p1 = (r1 * math.cos(th1), r1 * math.sin(th1))
    v = (p1[0] - p0[0], p1[1] - p0[1])
    radial = (math.cos(th0), math.sin(th0))
    dot = v[0] * radial[0] + v[1] * radial[1]
    cross = radial[0] * v[1] - radial[1] * v[0]
    return math.degrees(math.atan2(cross, dot))


def report(name, d):
    ri = 0.75 * d.inducer_hub_radius
    ro = d.tip_radius
    b1, b2 = d.beta1_deg, d.beta2_deg
    rs, ths = euler_points(ri, ro, b1, b2)
    wrap_euler = math.degrees(ths[-1])
    wrap_exact = math.degrees(exact_theta(ri, ro, b1, b2))
    first = chord_angle(rs[0], ths[0], rs[1], ths[1])
    last = chord_angle(rs[-2], ths[-2], rs[-1], ths[-1])
    print(f"{name:<22} r2={ro:8.2f} b1={b1:5.1f} b2={b2:5.1f} | "
          f"wrap euler {wrap_euler:8.1f} exact {wrap_exact:8.1f} "
          f"({wrap_euler / wrap_exact:5.2f}x) | first chord {first:7.1f} "
          f"(published {b1:5.1f}) | last chord {last:6.1f} "
          f"(published {b2:5.1f})")
    return wrap_euler, wrap_exact, first, last


DUTIES = [
    ("the shipped sample", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)),
    ("the MCP test duty", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000)),
    ("a small turbo", dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000)),
    ("a micro turbo", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000)),
    ("a big turbo", dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000)),
    ("an industrial stage", dict(mass_flow=5.0, pressure_ratio=2.5, rpm=15000)),
    ("a big industrial", dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000)),
    ("the largest measured", dict(mass_flow=50.0, pressure_ratio=2.0,
                                  rpm=3000)),
    ("backsweep 0", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                         backsweep_deg=0.0)),
    ("backsweep -60", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                           backsweep_deg=-60.0)),
    ("backsweep 74", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                          backsweep_deg=74.0)),
]


if __name__ == "__main__":
    worst = None
    for name, kw in DUTIES:
        d = meanline.design(meanline.Duty(**kw))
        we, wx, first, _last = report(name, d)
        err = abs(first - d.beta1_deg)
        if worst is None or err > worst[1]:
            worst = (name, err)
    print(f"\nworst inlet-angle error: {worst[0]} at {worst[1]:.1f} degrees")
