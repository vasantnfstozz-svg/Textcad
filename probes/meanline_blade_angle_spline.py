"""Round four, the primary question: the BUILT blade's angles vs the published.

`mcp_server._design_compressor` hands an AI `beta1_deg` and `beta2_deg`. The
blade the kernel cuts is `blocks.curved_blade`'s spline, thickened by `trace`,
so the spline IS the camber of the metal. This measures the angle between that
spline's own tangent and the radial direction at every sample point, and puts
it beside the law the design published:

    beta(r) = beta1 + (beta2 - beta1) * (r - ri) / (ro - ri)

Nothing here is inferred: the tangent comes from the OCCT curve itself (`edge
% u`), not from the polyline the code integrated.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build123d import Spline                                     # noqa: E402

import meanline                                                  # noqa: E402

N = 16


def camber_spline(ri, ro, b1, b2, n=N):
    """The exact spline `blocks.curved_blade` builds, same arithmetic."""
    pts, theta = [], 0.0
    for i in range(n + 1):
        t = i / n
        r = ri + (ro - ri) * t
        pts.append((r * math.cos(theta), r * math.sin(theta)))
        if i < n:
            beta = math.radians(b1 + (b2 - b1) * t)
            theta += math.tan(beta) / r * ((ro - ri) / n)
    return Spline(*pts).edges()[0], pts


def built_angle(edge, u):
    """(radius, blade angle from radial in degrees) at parameter u of the
    curve, both measured on the OCCT edge."""
    p = edge @ u
    tg = edge % u
    r = math.hypot(p.X, p.Y)
    if r <= 0:
        return 0.0, float("nan")
    ur = (p.X / r, p.Y / r)
    radial = tg.X * ur[0] + tg.Y * ur[1]
    tang = -tg.X * ur[1] + tg.Y * ur[0]
    return r, math.degrees(math.atan2(tang, radial))


def published_angle(r, ri, ro, b1, b2):
    return b1 + (b2 - b1) * (r - ri) / (ro - ri)


def angle_at_radius(edge, r_target, samples=801):
    """The built camber's angle from radial where it crosses radius r."""
    best = None
    for i in range(samples):
        u = i / (samples - 1)
        r, beta = built_angle(edge, u)
        if best is None or abs(r - r_target) < abs(best[0] - r_target):
            best = (r, beta)
    return best


def eye_station(name, d):
    """What the metal has at the INLET EYE — the station `beta1_deg` names."""
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    b1, b2 = d.beta1_deg, d.beta2_deg
    edge, _pts = camber_spline(ri, ro, b1, b2)
    r1s = d.inducer_shroud_radius
    r, beta = angle_at_radius(edge, r1s)
    law = published_angle(r, ri, ro, b1, b2)
    print(f"{name:<22} r1s {r1s:8.2f} (r1s/r2 {r1s / ro:5.3f})  published b1 "
          f"{b1:5.1f}  law there {law:6.2f}  METAL {beta:6.2f}  "
          f"delta {beta - b1:+7.2f}")
    return beta - b1


def scan(name, d, samples=201, show=False):
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    b1, b2 = d.beta1_deg, d.beta2_deg
    edge, pts = camber_spline(ri, ro, b1, b2)
    rows = []
    for i in range(samples):
        u = i / (samples - 1)
        r, beta = built_angle(edge, u)
        rows.append((u, r, beta, published_angle(r, ri, ro, b1, b2)))
    # the angle in the metal AT the two published stations
    inlet = rows[0]
    exit_ = rows[-1]
    worst = max(rows, key=lambda row: abs(row[2] - row[3]))
    wrap = math.degrees(math.atan2((edge @ 1).Y, (edge @ 1).X)) % 360.0
    if show:
        for u, r, beta, pub in rows[::10]:
            print(f"    u={u:4.2f} r={r:8.2f} built {beta:8.2f} "
                  f"published {pub:7.2f}  delta {beta - pub:+7.2f}")
    print(f"{name:<22} b1 pub {b1:5.1f} BUILT {inlet[2]:7.2f} "
          f"({inlet[2] - b1:+6.2f}) | b2 pub {b2:5.1f} BUILT {exit_[2]:6.2f} "
          f"({exit_[2] - b2:+5.2f}) | worst delta {worst[2] - worst[3]:+7.2f} "
          f"at r={worst[1]:.2f} | wrap {wrap:.1f}")
    return inlet, exit_, worst


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
    ("the smallest wheel", dict(mass_flow=1e-3, pressure_ratio=1.2,
                                rpm=500000)),
]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "eye":
        print("--- the angle in the metal AT THE INLET EYE (where the air "
              "meets the blade) ---")
        for name, kw in DUTIES:
            d = meanline.design(meanline.Duty(**kw))
            eye_station(name, d)
    else:
        for name, kw in DUTIES:
            d = meanline.design(meanline.Duty(**kw))
            scan(name, d, show=(name == "the shipped sample"))
