"""Calibrate the bound that separates a REAL closed hollow from the body handed
back as one (my-part-5 s18800: a 3 mm shell that removed 2.709 mm3 of 413262
and was called a success).

The candidate: the walls of an inward shell of thickness `t` lie within `t` of
the original surface, so their volume is about `area * t` and never a multiple
of it. This sweep asks what ratio `wall_volume / (area * t)` a CORRECT closed
shell actually reaches, across the shared gauntlet corpus plus the three
committed crash bodies, so the refusal can be set above every one of them
rather than guessed.

    python probes/shell_wall_bound_corpus.py

One child per BODY, printing a line per thickness as it goes, so a segfault
costs the rest of that body's ladder and nothing else.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

TS = (0.2, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 5.9, 8.0)
FIXTURES = ("oneplus_case_shell_body", "impeller_cut_shell_body",
            "sliver_intersect_plate")
MIRROR = ROOT / "probes" / "_mirror_shell_body.brep"


def bodies() -> dict:
    import build123d as b3d

    import gauntlet
    out = dict(gauntlet.BODIES)
    for name in FIXTURES:
        p = ROOT / "tests" / "fixtures" / f"{name}.brep"
        out[name] = (lambda p=p: b3d.Part(b3d.import_brep(str(p)).wrapped))
    if MIRROR.exists():
        out["my_part_5_mirror"] = lambda: b3d.Part(b3d.import_brep(str(MIRROR)).wrapped)
    return out


def ladder(name: str, open_face: str | None = None) -> None:
    import build123d as b3d

    import inspector
    import sketch
    solid = bodies()[name]()
    v_in, area = solid.volume, solid.area
    openings = sketch.shell_openings(solid, None, open_face) if open_face else []
    for t in TS:
        try:
            if openings:
                out = b3d.offset(solid, amount=-t, openings=openings,
                                 kind=b3d.Kind.INTERSECTION)
            else:
                off = b3d.offset(solid, amount=-t, kind=b3d.Kind.INTERSECTION)
                out = solid - off
            v_out = out.volume
            ok = (bool(out.is_valid) and not inspector.health(out)
                  and inspector.closed_shell(out) and 0 < v_out < v_in)
            print(f"ROW {name}|{t}|{v_in:.3f}|{area:.3f}|{v_out:.3f}|"
                  f"{v_out / (area * t):.4f}|{int(ok)}", flush=True)
        except Exception as e:                        # noqa: BLE001 -- the point
            print(f"ROW {name}|{t}|{v_in:.3f}|{area:.3f}|refused|"
                  f"{type(e).__name__}|-", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body")
    ap.add_argument("--open-face", default=None)
    ap.add_argument("--only", default=None,
                    help="comma-separated body names (the fast ones, for the open ladder)")
    a = ap.parse_args()
    if a.body:
        ladder(a.body, a.open_face)
        return 0
    names = a.only.split(",") if a.only else list(bodies())
    worst_ok, rows = 0.0, []
    for name in names:
        cmd = [sys.executable, __file__, "--body", name]
        if a.open_face:
            cmd += ["--open-face", a.open_face]
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        got = [ln[4:] for ln in p.stdout.splitlines() if ln.startswith("ROW ")]
        for line in got:
            f = line.split("|")
            if f[4] == "refused":
                print(f"  {f[0]:24s} t={float(f[1]):<4g} refused ({f[5]})", flush=True)
                continue
            ratio, ok = float(f[5]), f[6] == "1"
            rows.append((name, float(f[1]), ratio, ok))
            if ok:
                worst_ok = max(worst_ok, ratio)
            print(f"  {f[0]:24s} t={float(f[1]):<4g} walls {float(f[4]):>12.3f} "
                  f"ratio {ratio:6.3f} {'SOUND' if ok else 'unsound/wrong'}", flush=True)
        if len(got) < len(TS):
            print(f"  {name:24s} DIED after {len(got)} of {len(TS)} "
                  f"(0x{p.returncode & 0xFFFFFFFF:08X})", flush=True)
    print()
    print(f"highest ratio a SOUND closed shell reached: {worst_ok:.4f}")
    bad = [(n, t, r) for n, t, r, ok in rows if not ok]
    if bad:
        print("the unsound/wrong ones, for contrast:")
        for n, t, r in sorted(bad, key=lambda x: -x[2]):
            print(f"  {n:24s} t={t:<4g} ratio {r:6.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
