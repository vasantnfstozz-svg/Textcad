"""What ratio does a shell's walls reach OUTSIDE, where the skin ceiling has
never looked?

`assert_walls_could_be_a_skin` returns early for `direction != "inside"`: an
outward shell's walls sit outside the old surface, so `area * t` was never
measured for them. LAUNCH-PLAN section 10 asks whether the same ladder can be
made meaningful outward, or whether the numbers say it cannot.

There is a reason to expect it cannot, and this probe is here to put a number
on it rather than to argue it. Steiner's formula: growing a CONVEX body by `t`
adds `A*t + M*t^2 + (4/3)*pi*t^3`, so the ratio `walls / (A*t)` starts at 1 and
RISES with `t` without any bound that the body's own area knows about — a ball
of radius 10 grown by 8 mm is 2.01 of its skin and perfectly correct, where the
same number inside is the shape of the wrong result the ceiling exists to
catch. The inside ratio is bounded because the walls are a subset of the body;
the outside ratio is not bounded by anything of the kind.

Both directions are run, on the same bodies at the same thicknesses, so the two
columns can be read side by side. One child per body: a segfault costs that
body's ladder and nothing else.

    python probes/shell_skin_direction_corpus.py
    python probes/shell_skin_direction_corpus.py --body wedge --direction outside
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

TS = (0.2, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0)
FIXTURES = ("oneplus_case_shell_body", "impeller_cut_shell_body",
            "sliver_intersect_plate", "my_part_5_mirror_body")


def bodies() -> dict:
    import build123d as b3d

    import gauntlet
    out = dict(gauntlet.BODIES)
    for name in FIXTURES:
        p = ROOT / "tests" / "fixtures" / f"{name}.brep"
        out[name] = (lambda p=p: b3d.Part(b3d.import_brep(str(p)).wrapped))
    return out


def ladder(name: str, direction: str) -> None:
    import build123d as b3d

    import inspector
    solid = bodies()[name]()
    v_in, area = float(solid.volume), float(solid.area)
    outward = direction == "outside"
    print(f"HEAD {name}|{len(solid.faces())}|{len(solid.solids())}|{v_in:.3f}|{area:.3f}",
          flush=True)
    for t in TS:
        try:
            off = b3d.offset(solid, amount=(t if outward else -t),
                             kind=b3d.Kind.INTERSECTION)
            out = (off - solid) if outward else (solid - off)
            v_out = float(out.volume)
            ok = (bool(out.is_valid) and not inspector.health(out)
                  and inspector.closed_shell(out) and v_out > 0
                  and (outward or v_out < v_in))
            # two normalisers: today's `area * t` (the body's OWN surface) and
            # the mean of the two surfaces the walls lie between, which is what
            # the walls really are by the coarea formula and which has a
            # meaning in BOTH directions
            mean = float(out.area) / 2.0
            print(f"ROW {name}|{t}|{v_out:.3f}|{v_out / (area * t):.4f}|{int(ok)}|"
                  f"{v_out / (mean * t):.4f}|{out.area:.3f}", flush=True)
        except Exception as e:                        # noqa: BLE001 -- the point
            print(f"ROW {name}|{t}|refused|{type(e).__name__}|-|-|-", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body")
    ap.add_argument("--direction", default="inside", choices=("inside", "outside"))
    ap.add_argument("--only")
    a = ap.parse_args()
    if a.body:
        ladder(a.body, a.direction)
        return 0
    names = a.only.split(",") if a.only else list(bodies())
    worst = {"inside": [0.0, "", 0.0, ""], "outside": [0.0, "", 0.0, ""]}
    for name in names:
        for direction in ("inside", "outside"):
            p = subprocess.run([sys.executable, __file__, "--body", name,
                                "--direction", direction],
                               capture_output=True, text=True, cwd=str(ROOT))
            rows = [ln[4:] for ln in p.stdout.splitlines() if ln.startswith("ROW ")]
            for line in rows:
                f = line.split("|")
                if f[2] == "refused":
                    print(f"  {direction:7s} {f[0]:24s} t={float(f[1]):<4g} "
                          f"refused ({f[3]})", flush=True)
                    continue
                ratio, ok, mean_r = float(f[3]), f[4] == "1", float(f[5])
                w = worst[direction]
                if ok and ratio > w[0]:
                    w[0], w[1] = ratio, f"{name} t={f[1]}"
                if ok and mean_r > w[2]:
                    w[2], w[3] = mean_r, f"{name} t={f[1]}"
                print(f"  {direction:7s} {f[0]:24s} t={float(f[1]):<4g} "
                      f"walls {float(f[2]):>13,.3f} /area.t {ratio:7.4f} "
                      f"/mean.t {mean_r:7.4f} {'SOUND' if ok else 'unsound/wrong'}",
                      flush=True)
            if len(rows) < len(TS):
                print(f"  {direction:7s} {name:24s} DIED after {len(rows)} of "
                      f"{len(TS)} (0x{p.returncode & 0xFFFFFFFF:08X})", flush=True)
    print()
    for direction, w in worst.items():
        print(f"highest SOUND {direction}: /area.t {w[0]:.4f} ({w[1]})   "
              f"/mean.t {w[2]:.4f} ({w[3]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
