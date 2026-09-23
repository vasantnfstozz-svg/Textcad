"""PROBE - Sweep review round two (c908da5), 2026-09-23: a SLANTED start.

A profile the path leaves at angle a to its normal (allowed up to 80 deg,
with a note). Carried rigidly, a point s mm across the profile (in the path's
plane) sweeps backwards on a bend of radius R once s >= R*cos(a) - by the
velocity of the point along the profile's normal, (1 - k*a_m)*cos(a) + ...
Round one's rule compares the in-plane offset s*cos(a) with R, which is
looser still. Does the kernel agree on where the fold starts?

Run: python probes/memcap.py --gb 4 --timeout 600 -- python probes/sweep_slant_probe.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d            # noqa: E402

import sketch as sk                # noqa: E402

circ = (b3d.Plane.XY * b3d.Circle(3)).faces()
A = circ[0].area


def slant_path(R, deg=45.0, leg=10.0, turn=60.0, toward=+1, run=30.0):
    """first leg at `deg` from +Z toward +X; then an arc of `turn` degrees,
    radius R, turning further toward +X (toward=+1) or back (toward=-1)."""
    a = math.radians(deg)
    t0 = (math.sin(a), math.cos(a))                 # (x, z)
    p1 = (leg * t0[0], leg * t0[1])
    nrm = (t0[1] * toward, -t0[0] * toward)         # toward the bend centre
    c = (p1[0] + R * nrm[0], p1[1] + R * nrm[1])
    b = math.radians(turn) * toward
    ang0 = math.atan2(p1[1] - c[1], p1[0] - c[0])

    def on(t):
        return (c[0] + R * math.cos(ang0 - t), c[1] + R * math.sin(ang0 - t))
    mid, end = on(b / 2), on(b)
    a2 = a + b
    far = (end[0] + run * math.sin(a2), end[1] + run * math.cos(a2))
    P = lambda q: (q[0], 0, q[1])                   # noqa: E731
    return b3d.Wire([b3d.Line(P((0, 0)), P(p1)), b3d.ThreePointArc(P(p1), P(mid), P(end)),
                     b3d.Line(P(end), P(far))])


for toward in (+1, -1):
    for R in (2.0, 2.2, 2.5, 3.0, 4.0, 4.3, 5.0):
        w = slant_path(R, toward=toward)
        try:
            out = b3d.sweep(b3d.Sketch(children=list(circ)), path=w,
                            transition=b3d.Transition.RIGHT)
            k = f"valid {out.is_valid} vol/(A*L*cos45) {out.volume / (A * w.length * math.cos(math.pi / 4)):.4f}"
        except Exception as e:      # noqa: BLE001
            k = f"kernel raises {type(e).__name__}"
        try:
            sk._sweep_solid(list(circ), w, 0, True)
            op = "builds"
        except ValueError as e:
            op = "refuses: " + str(e)[:60]
        print(f"toward {toward:+d} R {R}: {k} | op {op}")
