"""Does `assert_the_deepest_point_was_hollowed` ever refuse a SOUND shell?

The new check is a theorem — a point measured `d` mm from every staying face,
`d > t`, cannot be in the walls of a `t` shell — but a theorem still meets a
kernel with a tolerance, so the one question that matters is whether it fires
on a result every other check calls sound. This runs the shared gauntlet
corpus, the committed crash fixtures and the drilled blocks over a ladder of
thicknesses, closed and with the top open, and prints one row per cell:

    the depth the pre-kernel guard measured, the margin `d - t` it has, the
    kernel's own verdict on the result, and where the point landed.

One child per BODY, so a segfault costs that body's ladder and nothing else.

    python probes/memcap.py --gb 6 --timeout 3600 -- \
        C:\\Python314\\python.exe probes/shell_deep_point_corpus.py
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
            "sliver_intersect_plate", "my_part_5_mirror_body")


def drilled(L, W, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def bodies() -> dict:
    import build123d as b3d

    import gauntlet
    out = dict(gauntlet.BODIES)
    for name in FIXTURES:
        p = ROOT / "tests" / "fixtures" / f"{name}.brep"
        if p.exists():
            out[name] = (lambda p=p: b3d.Part(b3d.import_brep(str(p)).wrapped))
    # the bodies this check was built for: drilled plates whose holes merge
    out["drilled_100"] = lambda: drilled(60.0, 60.0, 10.0, 10, 1.0, 6.0)
    out["drilled_81"] = lambda: drilled(50.0, 50.0, 60.0, 9, 0.4, 5.0)
    out["drilled_49"] = lambda: drilled(60.0, 60.0, 40.0, 7, 0.5, 8.0)
    return out


def ladder(name: str, open_face: str | None = None) -> None:
    import build123d as b3d

    import inspector
    import sketch
    solid = bodies()[name]()
    v_in = solid.volume
    openings = sketch.shell_openings(solid, None, open_face) if open_face else []
    for t in TS:
        walls = f"walls of {t:g} mm"
        try:
            deep = sketch.assert_something_would_be_hollowed(solid, t, openings, walls)
        except ValueError:
            print(f"ROW {name}|{t}|pre-kernel refusal|-|-|-|-", flush=True)
            continue
        if deep is None:
            print(f"ROW {name}|{t}|nothing measured|-|-|-|-", flush=True)
            continue
        depth, at, tol = deep
        try:
            if openings:
                out = b3d.offset(solid, amount=-t, openings=openings,
                                 kind=b3d.Kind.INTERSECTION)
            else:
                off = b3d.offset(solid, amount=-t, kind=b3d.Kind.INTERSECTION)
                out = solid - off
            v_out = out.volume
        except Exception as e:                        # noqa: BLE001 -- the point
            print(f"ROW {name}|{t}|kernel refused|{type(e).__name__}|-|-|-", flush=True)
            continue
        ok = (bool(out.is_valid) and not inspector.health(out)
              and inspector.closed_shell(out) and 0 < v_out < v_in)
        fired = 0
        try:
            sketch.assert_the_deepest_point_was_hollowed(solid, out, deep, t, walls)
        except ValueError:
            fired = 1
        # the two raw numbers the rule is set from: is the deep point still in
        # the result, and what fraction of the body the kernel actually removed
        held = sketch.point_is_inside(out, at) is True and \
            sketch.point_is_inside(solid, at) is True
        print(f"ROW {name}|{t}|{v_out:.4f}|{int(ok)}|{depth:.4f}|"
              f"{depth - t:.4f}|{fired}|{tol:.2e}|"
              f"{'IN ' if held else '-  '}{(v_in - v_out) / v_in:.3e}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body")
    ap.add_argument("--open-face", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--seconds", type=float, default=240.0,
                    help="per-BODY wall clock: one slow ladder must not eat the sweep")
    a = ap.parse_args()
    if a.body:
        ladder(a.body, a.open_face)
        return 0
    names = a.only.split(",") if a.only else list(bodies())
    fired_sound, fired_wrong, cells = [], [], 0
    for name in names:
        cmd = [sys.executable, __file__, "--body", name]
        if a.open_face:
            cmd += ["--open-face", a.open_face]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                               timeout=a.seconds)
            out, code = p.stdout, p.returncode
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace") \
                if isinstance(e.stdout, bytes) else (e.stdout or "")
            code = -1
        got = [ln[4:] for ln in out.splitlines() if ln.startswith("ROW ")]
        for line in got:
            f = line.split("|")
            if len(f) < 9:
                print(f"  {f[0]:26s} t={float(f[1]):<4g} {f[2]}", flush=True)
                continue
            t, v_out, ok = float(f[1]), float(f[2]), f[3] == "1"
            depth, margin, fired = float(f[4]), float(f[5]), f[6] == "1"
            cells += 1
            if fired:
                (fired_sound if ok else fired_wrong).append(
                    (name, t, v_out, depth, margin, f[8]))
            print(f"  {f[0]:26s} t={t:<4g} walls {v_out:>13,.3f} "
                  f"{'SOUND ' if ok else 'unsound'} depth {depth:7.4f} "
                  f"margin {margin:+8.4f} point {f[8]:>14s}"
                  f"{'   <<< THE NEW CHECK FIRES' if fired else ''}", flush=True)
        if len(got) < len(TS):
            print(f"  {name:26s} DIED after {len(got)} of {len(TS)} "
                  f"({'timed out' if code == -1 else f'0x{code & 0xFFFFFFFF:08X}'})",
                  flush=True)
    print(f"\n{cells} cells reached the new check.")
    print(f"  fired on a result every other check calls SOUND: {len(fired_sound)}")
    for row in fired_sound:
        print(f"    {row}")
    print(f"  fired on a result already unsound: {len(fired_wrong)}")
    for row in fired_wrong:
        print(f"    {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
