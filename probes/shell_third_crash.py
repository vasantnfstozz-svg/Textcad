"""pump-impeller seed 47244 step 56 (overnight run 2026-09-13): editing
`hub_seat.z` from 8.75 to 17.5 rebuilds `j22_shell` — a CLOSED inward shell,
thickness 1.9, on a 3-lump body — and SEGFAULTS. The same shell built at the
previous z. `assert_wall_fits_every_lump` (ac5c11d) does not fire: the
smallest lump extent is 5.8575 mm and 2 x 1.9 = 3.8.

    python probes/shell_third_crash.py            # the sweep
    python probes/shell_third_crash.py --t 1.9
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BREP = ROOT / "tests" / "fixtures" / "impeller_cut_shell_body.brep"


def one(t: float, direction: str) -> None:
    import build123d as b3d
    import sketch
    part = b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    out = sketch.shell(part, t, None, direction, "none")
    print(f"OK t {t} {direction}: {part.volume:.3f} -> {out.volume:.3f} mm3, "
          f"lumps {len(out.solids())}, valid {out.is_valid}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float)
    ap.add_argument("--direction", default="inside")
    a = ap.parse_args()
    if a.t is not None:
        try:
            one(a.t, a.direction)
        except Exception as e:                        # noqa: BLE001 — the point
            print(f"REFUSED t {a.t}: {type(e).__name__}: {str(e)[:140]}", flush=True)
        return 0
    for t in (0.2, 0.5, 0.8, 1.0, 1.2, 1.5, 1.7, 1.9, 2.2, 2.5, 2.9):
        p = subprocess.run([sys.executable, __file__, "--t", str(t)],
                           capture_output=True, text=True, cwd=str(ROOT))
        tail = [ln for ln in p.stdout.splitlines() if ln.startswith(("OK", "REFUSED"))]
        code = p.returncode & 0xFFFFFFFF
        print(f"t={t:<4g} -> {tail[0] if tail else f'DIED 0x{code:08X}'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
