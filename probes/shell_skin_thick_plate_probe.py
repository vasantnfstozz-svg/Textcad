"""Does the 1.35 skin ceiling refuse a CORRECT shell?

`_SHELL_SKIN_FACTOR` came down to 1.35 on 2026-09-17 against a sweep of
60 x 60 x **10** plates (probes/shell_skin_concave_sweep.py). The plate's
thickness was never a variable there, and it is the one that decides the
answer: the ratio of a drilled plate is

    ratio = 1 + (A_hole / A) * (t / 2r)

so a THICKER plate — same holes, more hole wall per flat face — pushes the
whole-body ratio towards the hole's own `1 + t/2r` without changing anything
about the shape's difficulty. A 60 x 60 x 10 plate drilled at r 0.8 tops out at
1.13; the same drilling in a 40 mm block is over 1.4.

This probe needs no Monte Carlo. For a box of L x W x H drilled with a square
grid of N through holes of radius `r` at pitch `p`, the material within `t` of
the boundary is exact arithmetic, as long as the holes do not merge when grown
(`p >= 2(r+t)`) and every grown hole still sits inside the eroded box:

    V     = L*W*H - N*pi*r^2*H
    core  = (L-2t)(W-2t)(H-2t) - N*pi*(r+t)^2*(H-2t)
    walls = V - core

That closed form reproduces the author's own corpus exactly — 21,107.482 mm3
for the 196-hole r 0.8 plate at t = 1, against the kernel's 21,107.5 — and it
gives 15,999.504 for the 100-hole r 1.0 plate at t = 1 where the kernel says
27,429.7, which is the wrong result the ceiling exists to catch. So the same
arithmetic decides both directions, with no sampling error at all.

    python probes/memcap.py --gb 6 --timeout 900 -- \
        C:\\Python314\\python.exe probes/shell_skin_thick_plate_probe.py --case thick49

One case per run: two OpenCASCADE workloads at once is how this box dies.
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

# name -> (L, W, H, n holes per side, r, pitch, thicknesses to try)
CASES = {
    # the author's own two, as a calibration of the closed form
    "flat196": (60.0, 60.0, 10.0, 14, 0.8, 4.0, (1.0, 1.2)),
    "flat100": (60.0, 60.0, 10.0, 10, 1.0, 6.0, (0.8, 1.0, 1.3)),
    # the same drilling in a THICK plate: generous 3 mm webs, 49 holes
    "thick49": (60.0, 60.0, 40.0, 7, 0.5, 8.0, (1.0, 1.5, 2.0, 2.5, 3.0)),
    "thick36": (50.0, 50.0, 40.0, 6, 0.5, 8.0, (2.0, 3.0)),
    "thick64": (50.0, 50.0, 40.0, 8, 0.5, 6.0, (1.5, 2.0)),
    "thick81": (50.0, 50.0, 60.0, 9, 0.4, 5.0, (1.0, 1.5, 1.8)),
    # ... and the case that attacks the SECOND normaliser: a wide rim so the
    # grown holes never reach the eroded box, and `t` walked up until the webs
    # between holes all but close, which is what collapsed the inner surface of
    # the oneplus case (its walls over the mean read 1.3725 and were SOUND)
    "closeweb": (74.0, 74.0, 40.0, 7, 0.5, 8.0, (3.0, 3.2, 3.4, 3.45)),
    "closeweb2": (74.0, 74.0, 24.0, 7, 0.5, 8.0, (2.0, 3.0, 3.4)),
    # ... and the case that attacks it the other way: the coarea excess of a
    # hole-dominated plate is about `2t/3H` (the genus term of Steiner's
    # formula over the trapezoid), so it is largest when `t` is a large
    # fraction of the plate's own thickness — and `t < H/2` for a closed hollow
    # caps that model at 1.33
    "thinhigh": (74.0, 74.0, 12.0, 7, 0.5, 8.0, (2.0, 3.0, 3.4)),
    "thinhigh2": (40.0, 40.0, 7.0, 7, 0.3, 3.0, (0.8, 1.0, 1.2)),
}


def truth(L, W, H, n, r, p, t):
    """exact mm3 of material within `t` of the boundary, or None when the
    closed form does not apply (grown holes merge, or reach the eroded box)"""
    N, span = n * n, (n - 1) * p
    if p < 2 * (r + t) or span / 2 + r + t > L / 2 - t or H - 2 * t <= 0:
        return None
    V = L * W * H - N * math.pi * r * r * H
    core = (L - 2 * t) * (W - 2 * t) * (H - 2 * t) - N * math.pi * (r + t) ** 2 * (H - 2 * t)
    return V - core


def drilled(L, W, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="thick49")
    ap.add_argument("--through-guard", action="store_true",
                    help="call sketch.shell (the shipped guards) instead of the kernel")
    a = ap.parse_args()
    import build123d as b3d

    import inspector
    import sketch
    L, W, H, n, r, p, ts = CASES[a.case]
    t0 = time.perf_counter()
    solid = drilled(L, W, H, n, r, p)
    v_in, area = float(solid.volume), float(solid.area)
    print(f"{a.case}: {n * n} holes r{r} pitch {p} in {L}x{W}x{H} — "
          f"{len(solid.faces())} faces, {v_in:,.3f} mm3, area {area:,.3f} mm2 "
          f"[{time.perf_counter() - t0:.0f}s build]", flush=True)
    for t in ts:
        want = truth(L, W, H, n, r, p, t)
        t1 = time.perf_counter()
        try:
            if a.through_guard:
                out = sketch.shell(solid, t)
            else:
                off = b3d.offset(solid, amount=-t, kind=b3d.Kind.INTERSECTION)
                out = solid - off
            v_out = float(out.volume)
            ok = (bool(out.is_valid) and not inspector.health(out)
                  and inspector.closed_shell(out) and 0 < v_out < v_in)
        except Exception as e:                            # noqa: BLE001 — the point
            print(f"  t={t:<5g} REFUSED ({type(e).__name__}: {str(e)[:90]})"
                  f"   truth {want:,.3f}   [{time.perf_counter() - t1:.0f}s]", flush=True)
            continue
        ratio = v_out / (area * t)
        # the other normaliser the range's own notes raise: the MEAN of the two
        # surfaces the walls lie between, which is the coarea formula and means
        # the same thing in both directions
        mean_r = v_out / (float(out.area) / 2.0 * t)
        err = "" if want is None else f"{(v_out - want) / want * 100:+.3f}% of truth"
        print(f"  t={t:<5g} walls {v_out:>13,.3f}  truth {want if want else float('nan'):>13,.3f}  "
              f"{err:<22}/area.t {ratio:7.4f}  /mean.t {mean_r:7.4f}  "
              f"{'SOUND' if ok else 'UNSOUND'}  [{time.perf_counter() - t1:.0f}s]"
              + ("   <<< OVER THE 1.35 CEILING" if ratio > sketch._SHELL_SKIN_FACTOR else ""),
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
