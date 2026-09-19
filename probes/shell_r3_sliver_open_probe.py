"""What the over-read costs: the sliver plate with a face OPEN.

`assert_wall_fits_every_lump` — the bounding-box bound that refuses a wall of
half a lump's smallest extent, the one written to stop a segfault — runs ONLY
for a CLOSED inward shell (`sketch.shell`: `if d == "inside" and not
openings`). With a face open, the only bound on the wall is
`assert_something_would_be_hollowed`, and on `sliver_intersect_plate` that
guard answers 24.3295 mm from a station in the AIR (probes/
shell_r3_over_read_probe.py) on a body whose bounding box is 1.9296 mm thick.

So this body's open shell reaches the kernel at EVERY thickness with no bound
at all. One child per thickness, so a crash costs that thickness and nothing
else; the exit code is reported.

    C:\\Python314\\python.exe probes/shell_r3_sliver_open_probe.py
    C:\\Python314\\python.exe probes/shell_r3_sliver_open_probe.py --t 3
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

TS = (0.3, 0.4, 0.5, 0.6, 0.8, 0.9, 1.0, 1.5, 3.0)


def body():
    import build123d as b3d
    p = ROOT / "tests" / "fixtures" / "sliver_intersect_plate.brep"
    return b3d.Part(b3d.import_brep(str(p)).wrapped)


def biggest_flat(solid):
    """the largest PLANAR face — what a user clicking 'open this face' hits"""
    from build123d import GeomType
    flats = [f for f in solid.faces() if f.geom_type == GeomType.PLANE]
    return max(flats, key=lambda f: float(f.area))


def one(t: float, closed: bool) -> None:
    os.environ["TEXTCAD_KERNEL_GUARD"] = "0"       # raw kernel, in this process
    import sketch
    solid = body()
    openings = [] if closed else [biggest_flat(solid)]
    walls = f"walls of {t:g} mm"
    try:
        deep = sketch.assert_something_would_be_hollowed(solid, t, openings, walls)
        said = f"guard ALLOWS on depth {deep[0]:.4f}" if deep else "nothing measured"
    except ValueError as e:
        said = "guard REFUSES: " + str(e)[:60]
        deep = None
    # the kernel is asked WHATEVER the guard said: the newly refused band has
    # to be proved wrong, not assumed wrong
    try:
        out = sketch.shell_after_guards(solid, t, "inside", openings, walls, None)
        import inspector
        ok = (bool(out.is_valid) and not inspector.health(out)
              and inspector.closed_shell(out) and 0 < out.volume < solid.volume)
        print(f"ROW {t}|kernel {'BUILDS SOUND' if ok else 'builds UNSOUND'} "
              f"{out.volume:.4f} of {solid.volume:.4f}|{said}", flush=True)
    except ValueError as e:
        print(f"ROW {t}|kernel refuses: {str(e)[:52]}|{said}", flush=True)
    except Exception as e:                           # noqa: BLE001 — the point
        print(f"ROW {t}|kernel raises {type(e).__name__}|{said}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, default=None)
    ap.add_argument("--closed", action="store_true")
    ap.add_argument("--seconds", type=float, default=200.0)
    a = ap.parse_args()
    if a.t is not None:
        one(a.t, a.closed)
        return 0
    solid = body()
    bb = solid.bounding_box()
    print(f"sliver_intersect_plate: {solid.volume:.4f} mm3, "
          f"{bb.size.X:.4g} x {bb.size.Y:.4g} x {bb.size.Z:.4g} — a wall of more "
          f"than {bb.size.Z / 2:.4f} mm can hollow nothing")
    for closed in (True, False):
        print(f"--- {'CLOSED' if closed else 'one face OPEN'} ---")
        for t in TS:
            cmd = [sys.executable, __file__, "--t", str(t)]
            if closed:
                cmd.append("--closed")
            try:
                p = subprocess.run(cmd, capture_output=True, text=True,
                                   cwd=str(ROOT), timeout=a.seconds)
                rows = [ln[4:] for ln in p.stdout.splitlines()
                        if ln.startswith("ROW ")]
                code = p.returncode & 0xFFFFFFFF
            except subprocess.TimeoutExpired:
                print(f"  t={t:<5g} THE KERNEL DID NOT ANSWER IN "
                      f"{a.seconds:g} s", flush=True)
                continue
            if not rows:
                print(f"  t={t:<5g} THE KERNEL KILLED THE PROCESS (0x{code:08X})",
                      flush=True)
                continue
            f = rows[0].split("|")
            print(f"  t={f[0]:<5} {f[1]:<52} {f[2] if len(f) > 2 else ''}",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
