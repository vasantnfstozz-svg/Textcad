"""How high can a CORRECT inward shell's `walls / (area * t)` really go?

LAUNCH-PLAN section 10 wants the skin ceiling tightened from 2.0 and says the
sweep it needs first is the one nobody has run: concave-heavy bodies over a
range of thicknesses, because "the ratio of a concave feature is 1 + t/2r, so
it rises with t and falls with detail size".

That formula is the whole risk, and it is worth stating exactly. Shell a hole
of radius `r` through a plate of height `h` inward by `t`: the wall it leaves
is the annulus from `r` to `r+t`,

    walls  = pi*((r+t)^2 - r^2)*h = pi*(2rt + t^2)*h
    skin   = (2*pi*r*h) * t
    ratio  = 1 + t/(2r)

which passes 1.5 at t = r and 2.0 at t = 2r. A body whose surface is MOSTLY
small holes is therefore a body where a perfectly correct shell reads above any
constant ceiling you care to name — if such a body can be shelled at all. The
question this probe answers is whether it can: whether the whole-body ratio
ever reaches the ceiling before the kernel refuses, the walls merge, or the
result stops being sound.

The bodies are synthetic and parametric on purpose (a plate drilled with a grid
of holes, and one slotted with narrow slots), so `t/2r` can be dialled straight
through the danger zone instead of hoping a library design lands in it. Every
result that passes the other checks AND reads above 1.0 is then put to an
independent Monte Carlo oracle, because "sound" here means "the kernel's checks
passed", which is exactly what the wrong results also do.

    python probes/shell_skin_concave_sweep.py
    python probes/shell_skin_concave_sweep.py --case holes_r1_p6 --oracle
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))

PLATE = (60.0, 60.0, 10.0)


def drilled(r: float, pitch: float):
    """a plate drilled with a square grid of holes of radius `r`"""
    import build123d as b3d
    part = b3d.Part() + b3d.Box(*PLATE)
    n = int((PLATE[0] - 2 * (r + 1.5)) // pitch)
    span = n * pitch
    cut = b3d.Part()
    for i in range(n + 1):
        for j in range(n + 1):
            cut += b3d.Pos(-span / 2 + i * pitch, -span / 2 + j * pitch, 0) * \
                b3d.Cylinder(r, PLATE[2] * 2)
    return part - cut


def slotted(w: float, pitch: float):
    """a plate cut by a comb of narrow through slots of width `w`"""
    import build123d as b3d
    part = b3d.Part() + b3d.Box(*PLATE)
    n = int((PLATE[0] - 6.0) // pitch)
    span = n * pitch
    cut = b3d.Part()
    for i in range(n + 1):
        cut += b3d.Pos(-span / 2 + i * pitch, 0, 0) * \
            b3d.Box(w, PLATE[1] - 6.0, PLATE[2] * 2)
    return part - cut


CASES = {
    # name              body                     thicknesses (t/2r crosses 1)
    "holes_r1_p6": (lambda: drilled(1.0, 6.0), (0.2, 0.5, 0.8, 1.0, 1.3, 1.6, 2.0, 2.4)),
    "holes_r0.8_p4": (lambda: drilled(0.8, 4.0), (0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 1.8)),
    "holes_r2_p8": (lambda: drilled(2.0, 8.0), (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)),
    "slots_w1_p5": (lambda: slotted(1.0, 5.0), (0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0)),
    "slots_w2_p6": (lambda: slotted(2.0, 6.0), (0.3, 0.6, 0.9, 1.2, 1.6, 2.0, 2.5, 3.0)),
}


def ladder(case: str, oracle: bool, n: int) -> None:
    import build123d as b3d

    import inspector
    make, ts = CASES[case]
    solid = make()
    v_in, area = float(solid.volume), float(solid.area)
    print(f"HEAD {case}|{len(solid.faces())}|{v_in:.3f}|{area:.3f}", flush=True)
    for t in ts:
        try:
            off = b3d.offset(solid, amount=-t, kind=b3d.Kind.INTERSECTION)
            out = solid - off
            v_out = float(out.volume)
            ok = (bool(out.is_valid) and not inspector.health(out)
                  and inspector.closed_shell(out) and 0 < v_out < v_in)
        except Exception as e:                        # noqa: BLE001 -- the point
            print(f"ROW {case}|{t}|refused|{type(e).__name__}|-|-", flush=True)
            continue
        ratio = v_out / (area * t)
        truth = sigma = float("nan")
        if oracle and ok and ratio > 1.0:
            from shell_skin_oracle_probe import skin_volume
            truth, sigma, _cal = skin_volume(solid, t, False, n)
        print(f"ROW {case}|{t}|{v_out:.3f}|{ratio:.4f}|{int(ok)}|"
              f"{truth:.3f}+/-{sigma:.3f}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--oracle", action="store_true")
    ap.add_argument("-n", type=int, default=8000)
    a = ap.parse_args()
    if a.case:
        ladder(a.case, a.oracle, a.n)
        return 0
    worst = (0.0, "")
    for case in CASES:
        cmd = [sys.executable, __file__, "--case", case, "-n", str(a.n)]
        if a.oracle:
            cmd.append("--oracle")
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        for line in p.stdout.splitlines():
            if line.startswith("HEAD "):
                f = line[5:].split("|")
                print(f"{f[0]}: {f[1]} faces, {float(f[2]):,.0f} mm3, "
                      f"area {float(f[3]):,.0f} mm2", flush=True)
                continue
            if not line.startswith("ROW "):
                continue
            f = line[4:].split("|")
            if f[2] == "refused":
                print(f"   t={float(f[1]):<5g} refused ({f[3]})", flush=True)
                continue
            ratio, ok = float(f[3]), f[4] == "1"
            if ok and ratio > worst[0]:
                worst = (ratio, f"{case} t={f[1]}")
            print(f"   t={float(f[1]):<5g} walls {float(f[2]):>12,.3f} "
                  f"ratio {ratio:7.4f} {'SOUND' if ok else 'unsound/wrong'}"
                  + (f"  oracle {f[5]}" if a.oracle and "nan" not in f[5] else "")
                  + ("   <<< OVER 1.5" if ok and ratio > 1.5 else ""), flush=True)
        if p.returncode:
            print(f"   {case}: CHILD DIED 0x{p.returncode & 0xFFFFFFFF:08X}", flush=True)
    print(f"\nhighest ratio a result that passes every other check reached: "
          f"{worst[0]:.4f}  ({worst[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
