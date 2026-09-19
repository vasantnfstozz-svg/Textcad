"""The dimension the COAREA corpus held constant: the grown holes never MERGE.

`_SHELL_COAREA_FACTOR` (1.5) was calibrated on drilled plates whose holes, when
grown by the wall thickness, never touch each other — `r + t < p/2` in every
case of `shell_skin_thick_plate_probe.py` (its own "closeweb" walks t to 3.45
against a pitch of 8 and a radius of 0.5, i.e. rho = 3.95 against a half-pitch
of 4.0, so the webs stay OPEN). That is the one dimension that decides this
ratio, because the coarea formula is EXACT —

    V(walls) = integral over s in [0, t] of A(s),   A(s) = area of the surface
                                                    offset inward by s

— so `V / (t * (A(0) + A(t)) / 2)` is the trapezoid error of that integral and
nothing else. It is 1.0 when A(s) moves linearly and rises towards 2.0 when
A(s) holds up and then COLLAPSES at the end. A drilled plate's A(s) rises (the
hole walls grow); the moment the grown holes MERGE it falls off a cliff, and
the ratio climbs straight through 1.5 on a body the kernel hollows exactly.

The whole thing is arithmetic. For a box L x W x H drilled with an n x n square
grid of through holes of radius r at pitch p, the surface offset inward by s is

    rho   = r + s,  h = H - 2s,  inner rect = (L-2s) x (W-2s)
    U(s)  = N*pi*rho^2 - E*lens(rho, p)          union of the grown discs
    P(s)  = N*2*pi*rho - E*4*alpha*rho           its perimeter
    R(s)  = inner rect minus that union
    A(s)  = 2*area(R) + h*perim(R)

with E = 2n(n-1) edge-adjacent pairs, alpha = acos(p / 2rho) and the standard
two-circle lens. It is EXACT as long as the DIAGONAL neighbours stay apart
(rho < p/sqrt2), which is also what keeps every overlap pairwise, and as long
as the grown discs stay inside the eroded rectangle. Both are asserted.

    python probes/shell_coarea_merge_probe.py --scan
    python probes/memcap.py --gb 6 --timeout 900 -- \
        C:\\Python314\\python.exe probes/shell_coarea_merge_probe.py --case merge64
    ... --case merge64 --through-guard      (the shipped door, refusal and all)

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
    # 64 holes of r 0.8 at 4 mm pitch in a 40 mm block: the grown holes touch
    # at t = 1.2 and the interstitial cavity is nearly gone by t = 1.6
    "merge64": (36.4, 36.4, 40.0, 8, 0.8, 4.0, (1.2, 1.4, 1.6, 1.7)),
    # the same drilling in a 20 mm plate: the same merge, less hole wall
    "merge64thin": (36.4, 36.4, 20.0, 8, 0.8, 4.0, (1.4, 1.6)),
    # a coarser grid, so the merge happens later and the webs are fatter
    "merge36": (44.0, 44.0, 40.0, 6, 1.2, 6.0, (2.0, 2.4, 2.6)),
    # the MILDEST merge the scan finds with both gates cleared: the grown holes
    # overlap by 11.7 per cent and the cavity is still 15,711 mm3
    "mild100": (67.0, 67.0, 40.0, 10, 0.4, 6.0, (2.8, 2.95, 3.0)),
    # the author's own closeweb, for the contrast: rho never reaches p/2
    "closeweb": (74.0, 74.0, 40.0, 7, 0.5, 8.0, (3.0, 3.45)),
    # the very plate `_SHELL_SKIN_FACTOR` was calibrated on — the one whose
    # t = 1.3 handback reads 1.6569 and is the "lowest wrong result on record"
    # — walked PAST that thickness, where the same handback reads under 1.35
    "flat100": (60.0, 60.0, 10.0, 10, 1.0, 6.0, (1.3, 1.6, 2.0, 2.5, 3.0)),
}


def oracle(L, W, H, n, r, p, t, shots=4_000_000, seed=12345):
    """The cavity volume by Monte Carlo against the ANALYTIC distance to the
    boundary of a drilled box — no OpenCASCADE, no closed form, no assumption
    that the grown holes stay apart or inside. Returns (walls, sigma)."""
    import random
    rnd = random.Random(seed)
    span, hit = (n - 1) * p, 0
    cx = [-span / 2 + i * p for i in range(n)]
    v_box = L * W * H
    for _ in range(shots):
        x = rnd.uniform(-L / 2, L / 2)
        y = rnd.uniform(-W / 2, W / 2)
        z = rnd.uniform(-H / 2, H / 2)
        d = min(L / 2 - abs(x), W / 2 - abs(y), H / 2 - abs(z))
        if d <= t:
            continue
        for a in cx:
            dx = x - a
            for b in cx:
                dy = y - b
                rad = math.hypot(dx, dy)
                if rad - r <= t:
                    d = -1.0
                    break
            if d < 0:
                break
        if d > t:
            hit += 1
    frac = hit / shots
    cavity = v_box * frac
    sigma = v_box * math.sqrt(max(frac * (1 - frac), 1e-12) / shots)
    v_body = L * W * H - n * n * math.pi * r * r * H
    return v_body - cavity, sigma


def lens(rho: float, d: float) -> tuple:
    """(area, alpha) of the overlap of two circles of radius `rho` whose
    centres are `d` apart — (0, 0) when they do not meet."""
    if d >= 2 * rho:
        return 0.0, 0.0
    alpha = math.acos(d / (2 * rho))
    return 2 * rho * rho * alpha - (d / 2) * math.sqrt(4 * rho * rho - d * d), alpha


def erode(L, W, H, n, r, p, s):
    """(area, perimeter, height) of the region left when the drilled box is
    eroded by `s`, or None when the closed form does not apply."""
    N, E, span = n * n, 2 * n * (n - 1), (n - 1) * p
    rho, h = r + s, H - 2 * s
    if h <= 0 or rho >= p / math.sqrt(2.0) or span / 2 + rho > L / 2 - s:
        return None
    a_lens, alpha = lens(rho, p)
    union_a = N * math.pi * rho * rho - E * a_lens
    union_p = N * 2 * math.pi * rho - E * 4 * alpha * rho
    area = (L - 2 * s) * (W - 2 * s) - union_a
    perim = 2 * ((L - 2 * s) + (W - 2 * s)) + union_p
    return area, perim, h


def surface(L, W, H, n, r, p, s):
    """A(s): the area of the surface offset inward by `s`."""
    got = erode(L, W, H, n, r, p, s)
    if got is None:
        return None
    area, perim, h = got
    return 2 * area + h * perim


def model(L, W, H, n, r, p, t):
    """The exact walls volume and both ratios, or None outside the closed form.

    `check` is the same volume by numeric integration of A(s) — the coarea
    identity — which is how this arithmetic proves itself."""
    got = erode(L, W, H, n, r, p, t)
    if got is None:
        return None
    area_t, _perim_t, h_t = got
    N = n * n
    v_body = L * W * H - N * math.pi * r * r * H
    a0 = surface(L, W, H, n, r, p, 0.0)
    a_t = 2 * area_t + h_t * _perim_t
    walls = v_body - area_t * h_t
    m = 4000
    check = sum(surface(L, W, H, n, r, p, (k + 0.5) * t / m) for k in range(m)) * (t / m)
    return {"walls": walls, "v_body": v_body, "a0": a0, "at": a_t,
            "cavity": area_t * h_t,
            "skin": walls / (a0 * t), "coarea": walls / ((a0 + a_t) / 2 * t),
            "integral": check, "drift": abs(check - walls) / walls}


def drilled(L, W, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def scan() -> int:
    """Pure arithmetic: which drilled plates does the shipped AND refuse?"""
    import sketch
    hits = []
    for H in (20.0, 30.0, 40.0, 60.0):
        for p in (3.0, 4.0, 5.0, 6.0):
            for r in (0.4, 0.6, 0.8, 1.0, 1.2):
                if 2 * r >= p:
                    continue
                for n in (6, 8, 10):
                    span = (n - 1) * p
                    for t in [x / 20 for x in range(4, 61)]:
                        L = span + 2 * (r + t) + 2 * t + 0.4
                        m = model(L, L, H, n, r, p, t)
                        if m is None or m["cavity"] <= 1e-6:
                            continue
                        if m["skin"] > sketch._SHELL_SKIN_FACTOR and \
                                m["coarea"] > sketch._SHELL_COAREA_FACTOR:
                            hits.append((m["coarea"], m["skin"], L, H, n, r, p, t, m))
    print(f"{len(hits)} (L,H,n,r,p,t) combinations where BOTH ratios clear the "
          f"shipped gate on an EXACT closed form\n")
    # the merge factor `(r+t)/(p/2)` is the dimension the coarea corpus held
    # constant: every case behind 1.5 has it UNDER 1.0 (the grown holes never
    # touch). The mildest merges are the ones a kernel might still build.
    for label, key in (("deepest merge first", lambda x: -x[0]),
                       ("MILDEST merge first", lambda x: (x[5] + x[7]) / (x[6] / 2))):
        print(f"--- {label} ---")
        print(f"{'L':>7} {'H':>5} {'n':>3} {'r':>5} {'p':>5} {'t':>5} {'merge':>6}  "
              f"{'walls':>12} {'cavity':>10}  {'/area.t':>8} {'/mean.t':>8}  drift")
        for coarea, skin, L, H, n, r, p, t, m in sorted(hits, key=key)[:12]:
            print(f"{L:7.2f} {H:5g} {n:3d} {r:5g} {p:5g} {t:5g} "
                  f"{(r + t) / (p / 2):6.3f}  "
                  f"{m['walls']:12,.3f} {m['cavity']:10,.3f}  {skin:8.4f} {coarea:8.4f}  "
                  f"{m['drift']:.2e}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--through-guard", action="store_true")
    ap.add_argument("--oracle", type=int, default=0,
                    help="Monte Carlo shots for the independent oracle (0 = off)")
    a = ap.parse_args()
    if a.scan or not a.case:
        return scan()
    import build123d as b3d

    import inspector
    import sketch
    L, W, H, n, r, p, ts = CASES[a.case]
    t0 = time.perf_counter()
    solid = drilled(L, W, H, n, r, p)
    v_in, area = float(solid.volume), float(solid.area)
    m0 = model(L, W, H, n, r, p, 1e-9)
    print(f"{a.case}: {n * n} holes r{r} pitch {p} in {L}x{W}x{H} — "
          f"{len(solid.faces())} faces, {v_in:,.3f} mm3 (model "
          f"{m0['v_body']:,.3f}), area {area:,.3f} mm2 (model {m0['a0']:,.3f}) "
          f"[{time.perf_counter() - t0:.0f}s build]", flush=True)
    for t in ts:
        want = model(L, W, H, n, r, p, t)
        if want:
            print(f"  --- t={t:g} closed form: walls {want['walls']:,.3f}, cavity "
                  f"{want['cavity']:,.3f}, integral of A(s) {want['integral']:,.3f} "
                  f"(drift {want['drift']:.1e})", flush=True)
        if a.oracle:
            w, sig = oracle(L, W, H, n, r, p, t, a.oracle)
            print(f"  --- t={t:g} Monte Carlo oracle ({a.oracle:,} shots): walls "
                  f"{w:,.1f} +/- {sig:,.1f}", flush=True)
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
            print(f"  t={t:<5g} REFUSED ({type(e).__name__}: {str(e)[:110]})",
                  flush=True)
            if want:
                print(f"           model says walls {want['walls']:,.3f}, cavity "
                      f"{want['cavity']:,.3f}, /area.t {want['skin']:.4f}, "
                      f"/mean.t {want['coarea']:.4f}", flush=True)
            continue
        skin = v_out / (area * t)
        coarea = v_out / (float(out.area) / 2.0 * t)
        err = "" if want is None else f"{(v_out - want['walls']) / want['walls'] * 100:+.4f}%"
        print(f"  t={t:<5g} walls {v_out:>13,.3f}  model "
              f"{want['walls'] if want else float('nan'):>13,.3f}  {err:<11} "
              f"/area.t {skin:7.4f} (model {want['skin'] if want else float('nan'):7.4f})  "
              f"/mean.t {coarea:7.4f} (model {want['coarea'] if want else float('nan'):7.4f})  "
              f"{'SOUND' if ok else 'UNSOUND'}  [{time.perf_counter() - t1:.0f}s]"
              + ("   <<< BOTH GATES CLEARED -> REFUSED"
                 if skin > sketch._SHELL_SKIN_FACTOR and coarea > sketch._SHELL_COAREA_FACTOR
                 else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
