"""Round three, the P0 hunt: the same handback the theorem closed, with a face
OPEN.

`probes/shell_r3_deep_point_reach.py` measured that every OPEN shell hands
`assert_the_deepest_point_was_hollowed` a point that lies ON the body, because
an opening face's samples carry a bound of `inf` and so are measured first —
and the solid classifier answers ON, not IN, so the theorem returns without
judging anything. So the whole P0 class round two closed is open again the
moment the user clicks a face.

This puts that to the kernel on the very plate the ceiling was calibrated on,
with the top face open, and measures the result against an INDEPENDENT oracle:
Monte Carlo against the analytic distance to the boundary of a drilled box,
with the TOP dropped from that distance because it is the opening.

ONE case per run; this is an OpenCASCADE workload.

    python probes/memcap.py --gb 6 --timeout 900 -- \\
        C:\\Python314\\python.exe probes/shell_r3_open_handback_probe.py --t 2.5
"""
import argparse
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

# the plate `_SHELL_SKIN_FACTOR` was calibrated on
L = W = 60.0
H = 10.0
N = 10
R = 1.0
P = 6.0


def drilled():
    import build123d as b3d
    span = (N - 1) * P
    cut = b3d.Part()
    for i in range(N):
        for j in range(N):
            cut += b3d.Pos(-span / 2 + i * P, -span / 2 + j * P, 0) * \
                b3d.Cylinder(R, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def oracle(t, open_top: bool, shots=3_000_000, seed=4242):
    """(walls, sigma) by Monte Carlo against the ANALYTIC distance to the faces
    that STAY. With the top open, the top plane is not one of them."""
    import random
    rnd = random.Random(seed)
    span, hit = (N - 1) * P, 0
    cx = [-span / 2 + i * P for i in range(N)]
    v_box = L * W * H
    for _ in range(shots):
        x = rnd.uniform(-L / 2, L / 2)
        y = rnd.uniform(-W / 2, W / 2)
        z = rnd.uniform(-H / 2, H / 2)
        d = min(L / 2 - abs(x), W / 2 - abs(y), z + H / 2)
        if not open_top:
            d = min(d, H / 2 - z)
        if d <= t:
            continue
        for a in cx:
            dx = x - a
            for b in cx:
                rad = math.hypot(dx, y - b)
                if rad - R <= t:
                    d = -1.0
                    break
            if d < 0:
                break
        if d > t:
            hit += 1
    frac = hit / shots
    cavity = v_box * frac
    sigma = v_box * math.sqrt(max(frac * (1 - frac), 1e-12) / shots)
    v_body = L * W * H - N * N * math.pi * R * R * H
    return v_body - cavity, cavity, sigma


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, required=True)
    ap.add_argument("--open", default="top", help="top | none")
    ap.add_argument("--shots", type=int, default=3_000_000)
    a = ap.parse_args()
    import build123d as b3d

    import inspector
    import sketch
    open_top = a.open != "none"
    t0 = time.perf_counter()
    solid = drilled()
    v_in, area = float(solid.volume), float(solid.area)
    print(f"plate {L}x{W}x{H}, {N * N} holes r{R} pitch {P}: {len(solid.faces())} "
          f"faces, {v_in:,.3f} mm3, area {area:,.3f} mm2 "
          f"[{time.perf_counter() - t0:.0f}s]", flush=True)

    walls_true, cavity_true, sig = oracle(a.t, open_top, a.shots)
    print(f"oracle (open={a.open}, {a.shots:,} shots): walls {walls_true:,.1f} "
          f"+/- {sig:,.1f}, cavity {cavity_true:,.1f}", flush=True)

    openings = sketch.shell_openings(solid, None, a.open)
    walls_say = f"walls of {a.t:g} mm"
    deep = sketch.assert_something_would_be_hollowed(solid, a.t, openings, walls_say)
    if deep:
        depth, at, tol = deep
        print(f"the guard's point: depth {depth:.4f} at "
              f"({at[0]:.4g},{at[1]:.4g},{at[2]:.4g}), tol {tol:.4g}; "
              f"margin over t {depth - a.t - tol:+.4f}; "
              f"classifier on the INPUT says "
              f"{sketch.point_is_inside(solid, at)}", flush=True)

    t1 = time.perf_counter()
    if openings:
        out = b3d.offset(solid, amount=-a.t, openings=openings,
                         kind=b3d.Kind.INTERSECTION)
    else:
        out = solid - b3d.offset(solid, amount=-a.t, kind=b3d.Kind.INTERSECTION)
    v_out = float(out.volume)
    cavity_got = v_in - v_out
    print(f"kernel: walls {v_out:,.3f} mm3 (cavity {cavity_got:,.3f}), "
          f"[{time.perf_counter() - t1:.0f}s]", flush=True)
    print(f"  against the oracle: {(v_out - walls_true) / max(sig, 1e-9):+.1f} sigma, "
          f"{cavity_got / max(cavity_true, 1e-9) * 100:.3f}% of the cavity that "
          f"had to go", flush=True)
    print(f"  valid {inspector._try(lambda: bool(out.is_valid))}  "
          f"closed_shell {inspector.closed_shell(out)}  "
          f"health {inspector.health(out) or 'clean'}", flush=True)
    skin = v_out / (area * a.t)
    coarea = v_out / (float(out.area) / 2.0 * a.t)
    print(f"  /area.t {skin:.4f} (bound {sketch._SHELL_SKIN_FACTOR})   "
          f"/mean.t {coarea:.4f} (bound {sketch._SHELL_COAREA_FACTOR})   "
          f"cavity fraction {cavity_got / v_in:.3e} (floor "
          f"{sketch._SHELL_NOTHING_HOLLOWED})", flush=True)

    for name, fn in (
            ("assert_walls_could_be_a_skin",
             lambda: sketch.assert_walls_could_be_a_skin(solid, out, a.t, "inside",
                                                         walls_say)),
            ("assert_every_lump_hollowed",
             lambda: sketch.assert_every_lump_hollowed(solid, out, "inside", walls_say)),
            ("assert_the_deepest_point_was_hollowed",
             lambda: sketch.assert_the_deepest_point_was_hollowed(
                 solid, out, deep, a.t, walls_say))):
        try:
            fn()
            print(f"  {name:<38} PASSES")
        except ValueError as e:
            print(f"  {name:<38} REFUSES — {str(e)[:100]}")
    if deep:
        print(f"  point_is_inside(result) = {sketch.point_is_inside(out, deep[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
