"""my-part-8 s46791: fillet on a 1.93 mm thin plate with BSPLINE walls does
not round an edge — it EATS the body, and comes back valid and healthy.

    python probes/fillet_eats_body.py            # the sweep (one radius per child)
    python probes/fillet_eats_body.py --idx 0 --radius 0.4
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BREP = ROOT / "tests" / "fixtures" / "sliver_intersect_plate.brep"


def one(idx: int, radius: float) -> None:
    import build123d as b3d
    import blocks
    import inspector
    part = b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    picked = blocks.edges_for(part, "horizontal")
    e = picked[idx]
    before = part.volume
    out = b3d.fillet([e], radius=radius)
    bb, ob = part.bounding_box(), out.bounding_box()
    print(f"RESULT idx {idx} r {radius:<5g} {before:8.3f} -> {out.volume:8.3f} mm3 "
          f"({100 * out.volume / before:5.1f}%)  valid {out.is_valid}  "
          f"health {inspector.health(out, check_valid=False)}  "
          f"faces {len(part.faces())}->{len(out.faces())}  "
          f"bbox z {bb.size.Z:.4g}->{ob.size.Z:.4g} x {bb.size.X:.4g}->{ob.size.X:.4g}",
          flush=True)


def main() -> int:
    if "--idx" in sys.argv:
        i = sys.argv.index("--idx")
        r = sys.argv.index("--radius")
        try:
            one(int(sys.argv[i + 1]), float(sys.argv[r + 1]))
        except Exception as e:                       # noqa: BLE001 — the point
            print(f"REFUSED idx {sys.argv[i+1]} r {sys.argv[r+1]}: "
                  f"{type(e).__name__}: {str(e)[:110]}", flush=True)
        return 0
    for idx in range(8):
        for radius in (0.1, 0.4, 0.9):
            p = subprocess.run([sys.executable, __file__, "--idx", str(idx),
                                "--radius", str(radius)],
                               capture_output=True, text=True, cwd=str(ROOT))
            tail = [ln for ln in p.stdout.splitlines()
                    if ln.startswith(("RESULT", "REFUSED"))]
            code = p.returncode & 0xFFFFFFFF
            print(tail[0] if tail else f"DIED idx {idx} r {radius} 0x{code:08X}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
