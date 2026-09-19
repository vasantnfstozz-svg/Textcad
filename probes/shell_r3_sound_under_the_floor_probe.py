"""Attack on `_SHELL_NOTHING_HOLLOWED` (1 per cent) from the SOUND side.

The corpus behind the floor holds one dimension constant: every SOUND result
that reaches the theorem is the oneplus case, where the kernel drops a sliver
and still hollows 31 per cent of the body. The floor is only a floor if some
CORRECT shell leaves less than 1 per cent of the body as cavity AND keeps the
guard's own deep point inside the walls. Two shapes can leave that little:

  * a thick plate shelled at just under half its thickness — the docstring's
    own 12 mm plate at 5.9 mm walls is 1.09 per cent, so 5.95 mm is 0.54;
  * a bar open at BOTH ends shelled at just under half its width — the cavity
    is a tunnel, 0.25 per cent of the bar.

Both are built for real and every guard is asked, because the question is not
what the arithmetic says but whether the deep point survives a result the
kernel calls sound.

    C:\\Python314\\python.exe probes/shell_r3_sound_under_the_floor_probe.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def main() -> int:
    import build123d as b3d

    import inspector
    import sketch
    os.environ["TEXTCAD_KERNEL_GUARD"] = "0"      # raw kernel, in this process
    cases = [
        ("plate 60x60x12 closed", lambda: b3d.Part() + b3d.Box(60, 60, 12),
         5.95, None),
        ("plate 60x60x12 closed", lambda: b3d.Part() + b3d.Box(60, 60, 12),
         5.9, None),
        ("bar 20x20x100, top open", lambda: b3d.Part() + b3d.Box(20, 20, 100),
         9.5, "top"),
        ("bar 20x20x100, top open", lambda: b3d.Part() + b3d.Box(20, 20, 100),
         9.8, "top"),
        ("box 50 closed", lambda: b3d.Part() + b3d.Box(50, 50, 50), 24.6, None),
    ]
    print(f"{'body':<26} {'t':>6} {'cavity':>12} {'of body':>10} {'depth':>8} "
          f"{'margin':>8} {'point in walls':>14}  verdict")
    for name, make, t, open_face in cases:
        solid = make()
        v_in = float(solid.volume)
        walls = f"walls of {t:g} mm"
        openings = sketch.shell_openings(solid, None, open_face) if open_face else []
        try:
            deep = sketch.assert_something_would_be_hollowed(solid, t, openings, walls)
        except ValueError as e:
            print(f"{name:<26} {t:>6g} the guard refuses first: {str(e)[:50]}")
            continue
        try:
            out = sketch.shell_after_guards(solid, t, "inside", openings, walls, None)
        except ValueError as e:
            print(f"{name:<26} {t:>6g} the kernel/checks refuse: {str(e)[:50]}")
            continue
        v_out = float(out.volume)
        cav = v_in - v_out
        ok = (bool(out.is_valid) and not inspector.health(out)
              and inspector.closed_shell(out) and 0 < v_out < v_in)
        held = sketch.point_is_inside(out, deep[1]) is True
        fired = ""
        try:
            sketch.assert_the_deepest_point_was_hollowed(solid, out, deep, t, walls)
        except ValueError as e:
            fired = "  <<< REFUSED: " + str(e)[:40]
        print(f"{name:<26} {t:>6g} {cav:>12,.4f} {cav / v_in:>10.4e} "
              f"{deep[0]:>8.4f} {deep[0] - t - deep[2]:>+8.4f} {str(held):>14}  "
              f"{'SOUND' if ok else 'unsound'}{fired}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
