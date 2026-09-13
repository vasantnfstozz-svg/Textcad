"""oneplus_7_pro_case seed 46794 step 8 (overnight run 2026-09-13): shell with
an OPEN face — thickness 1.1, open_face "bottom" — SEGFAULTED OCCT on a
78.9 x 165.6 x 12 mm, 60-face case body. One thickness per child process.

`ac5c11d`'s `assert_wall_fits_every_lump` does not apply here: it guards the
CLOSED inward hollow only (`d == "inside" and not openings`), and this shell
has an opening.

    python probes/shell_open_face_crash.py                       # the sweep
    python probes/shell_open_face_crash.py --t 1.1 --face bottom # one attempt
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BREP = ROOT / "tests" / "fixtures" / "oneplus_case_shell_body.brep"


def one(t: float, face: str | None, direction: str) -> None:
    import build123d as b3d
    import sketch
    part = b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    out = sketch.shell(part, t, None, direction, face)
    print(f"OK t {t} face {face} {direction}: {part.volume:.3f} -> {out.volume:.3f} mm3, "
          f"valid {out.is_valid}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float)
    ap.add_argument("--face", default="bottom")
    ap.add_argument("--direction", default="inside")
    a = ap.parse_args()
    if a.t is not None:
        try:
            one(a.t, None if a.face == "none" else a.face, a.direction)
        except Exception as e:                        # noqa: BLE001 — the point
            print(f"REFUSED t {a.t} face {a.face}: {type(e).__name__}: "
                  f"{str(e)[:150]}", flush=True)
        return 0
    for face in ("bottom", "top", "none"):
        for t in (0.2, 0.5, 0.8, 1.0, 1.1, 1.5, 2.0, 3.0, 5.0):
            p = subprocess.run([sys.executable, __file__, "--t", str(t), "--face", face],
                               capture_output=True, text=True, cwd=str(ROOT))
            tail = [ln for ln in p.stdout.splitlines() if ln.startswith(("OK", "REFUSED"))]
            code = p.returncode & 0xFFFFFFFF
            print(f"face {face:7s} t={t:<4g} -> {tail[0] if tail else f'DIED 0x{code:08X}'}",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
