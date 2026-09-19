"""Round three, attack on `_SHELL_NOTHING_HOLLOWED` (1 per cent) from the WRONG
side: the dimension its corpus held constant is that the failure is BINARY.

Every wrong reading behind the floor is a body handed back WHOLE — 6.6e-6 to
1.4e-4 of the body removed — and the one sound reading that reaches the
question is a dropped sliver at 3.1e-1. 1 per cent sits between them. But the
drilled plate walks from a SOUND shell at t = 1.6 to a whole handback at
t = 2.5, and nothing says the walk is a step: a thickness in between can build
PART of the cavity and drop the rest. Anything that removes more than 1 per
cent of the body is waved through by the second half of the AND however little
of the cavity it built.

The oracle is the ANALYTIC distance to the boundary of a drilled box — the
same one `shell_coarea_merge_probe.py` uses — with the nine nearest hole
centres checked instead of all hundred, which is exact for a square grid and
fast enough to scan.

    C:\\Python314\\python.exe probes/shell_r3_partial_handback_probe.py --scan
    python probes/memcap.py --gb 6 --timeout 900 -- \\
        C:\\Python314\\python.exe probes/shell_r3_partial_handback_probe.py --t 2.2

ONE kernel case per run; this is an OpenCASCADE workload.
"""
import argparse
import math
import os
import random
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
SPAN = (N - 1) * P


def drilled():
    import build123d as b3d
    cut = b3d.Part()
    for i in range(N):
        for j in range(N):
            cut += b3d.Pos(-SPAN / 2 + i * P, -SPAN / 2 + j * P, 0) * \
                b3d.Cylinder(R, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def _hole_gap(x, y):
    """Distance from (x, y) to the nearest hole WALL. The centres are a square
    grid, so the nearest one is found by rounding; the 3 x 3 block around that
    index is checked, which covers every tie."""
    i = round((x + SPAN / 2) / P)
    j = round((y + SPAN / 2) / P)
    best = float("inf")
    for a in range(max(0, i - 1), min(N, i + 2)):
        for b in range(max(0, j - 1), min(N, j + 2)):
            best = min(best, math.hypot(x - (-SPAN / 2 + a * P),
                                        y - (-SPAN / 2 + b * P)))
    return best - R


def oracle(t, open_top=False, shots=400_000, seed=4242):
    """(walls, cavity, sigma) by Monte Carlo on the analytic distance."""
    rnd = random.Random(seed)
    hit = 0
    v_box = L * W * H
    for _ in range(shots):
        x = rnd.uniform(-L / 2, L / 2)
        y = rnd.uniform(-W / 2, W / 2)
        z = rnd.uniform(-H / 2, H / 2)
        d = min(L / 2 - abs(x), W / 2 - abs(y), z + H / 2)
        if not open_top:
            d = min(d, H / 2 - z)
        if d > t and _hole_gap(x, y) > t:
            hit += 1
    frac = hit / shots
    cavity = v_box * frac
    sigma = v_box * math.sqrt(max(frac * (1 - frac), 1e-12) / shots)
    v_body = L * W * H - N * N * math.pi * R * R * H
    return v_body - cavity, cavity, sigma


def scan() -> int:
    v_body = L * W * H - N * N * math.pi * R * R * H
    print(f"plate {L}x{W}x{H}, {N * N} holes r{R} pitch {P}: body {v_body:,.3f} mm3")
    print(f"{'t':>5} {'cavity due':>12} {'as frac of body':>16}   "
          f"{'1% floor':>9}")
    for t in (1.0, 1.3, 1.6, 1.8, 2.0, 2.2, 2.4, 2.5, 2.8, 3.0):
        _w, cav, sig = oracle(t, shots=600_000)
        frac = cav / v_body
        print(f"{t:>5g} {cav:>12,.1f} {frac:>16.4e}   "
              f"{'ABOVE' if frac > 0.01 else 'below':>9}  (+/- {sig:,.1f})")
    print("\nA kernel that builds MORE than 1% of the body as cavity is waved "
          "through by `_SHELL_NOTHING_HOLLOWED` whatever fraction of the cavity "
          "it actually built.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, default=None)
    ap.add_argument("--open", default="none", help="top | none")
    ap.add_argument("--shots", type=int, default=3_000_000)
    ap.add_argument("--scan", action="store_true")
    a = ap.parse_args()
    if a.scan or a.t is None:
        return scan()
    import build123d as b3d

    import inspector
    import sketch
    open_top = a.open != "none"
    t0 = time.perf_counter()
    solid = drilled()
    v_in, area = float(solid.volume), float(solid.area)
    print(f"plate: {len(solid.faces())} faces, {v_in:,.3f} mm3, area "
          f"{area:,.3f} mm2 [{time.perf_counter() - t0:.0f}s]", flush=True)
    walls_true, cavity_true, sig = oracle(a.t, open_top, a.shots)
    print(f"oracle (open={a.open}, {a.shots:,} shots): walls {walls_true:,.1f} "
          f"+/- {sig:,.1f}, cavity due {cavity_true:,.1f}", flush=True)

    openings = sketch.shell_openings(solid, None, a.open)
    walls_say = f"walls of {a.t:g} mm"
    try:
        deep = sketch.assert_something_would_be_hollowed(solid, a.t, openings, walls_say)
    except ValueError as e:
        print(f"the BEFORE guard refuses: {e}")
        return 0
    if deep:
        depth, at, tol = deep
        print(f"the guard's point: depth {depth:.4f} at "
              f"({at[0]:.4g},{at[1]:.4g},{at[2]:.4g}); margin over t "
              f"{depth - a.t - tol:+.4f}; inside the INPUT: "
              f"{sketch.point_is_inside(solid, at)}", flush=True)

    t1 = time.perf_counter()
    try:
        if openings:
            out = b3d.offset(solid, amount=-a.t, openings=openings,
                             kind=b3d.Kind.INTERSECTION)
        else:
            out = solid - b3d.offset(solid, amount=-a.t, kind=b3d.Kind.INTERSECTION)
        v_out = float(out.volume)
    except Exception as e:                       # noqa: BLE001 — the point
        print(f"kernel REFUSES: {type(e).__name__}: {str(e)[:120]}")
        return 0
    cavity_got = v_in - v_out
    print(f"kernel: walls {v_out:,.3f} (cavity {cavity_got:,.3f} = "
          f"{cavity_got / max(cavity_true, 1e-9) * 100:.2f}% of what had to go), "
          f"{(v_out - walls_true) / max(sig, 1e-9):+.1f} sigma "
          f"[{time.perf_counter() - t1:.0f}s]", flush=True)
    print(f"  valid {inspector._try(lambda: bool(out.is_valid))}  closed_shell "
          f"{inspector.closed_shell(out)}  health {inspector.health(out) or 'clean'}",
          flush=True)
    skin = v_out / (area * a.t)
    coarea = v_out / (float(out.area) / 2.0 * a.t)
    print(f"  /area.t {skin:.4f} (bound {sketch._SHELL_SKIN_FACTOR})  /mean.t "
          f"{coarea:.4f} (bound {sketch._SHELL_COAREA_FACTOR})  removed "
          f"{cavity_got / v_in:.4e} of the body (floor "
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
