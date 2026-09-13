"""my-part-8 seed 46791 step 14: fillet(radius 0.4, edges "horizontal") on a
50 x 50 x 1.93 mm intersect body SEGFAULTED OCCT (0xC0000005). One radius per
child process, so an access violation is a data point and not the end of the run.

    python probes/fillet_crash_sweep.py                 # the sweep (parent)
    python probes/fillet_crash_sweep.py --radius 0.4    # one attempt (child)
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BREP = ROOT / "tests" / "fixtures" / "sliver_intersect_plate.brep"


def one(radius: float, which: str, op: str) -> None:
    import build123d as b3d
    import blocks
    part = b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    picked = blocks.edges_for(part, which)
    print(f"  body vol {part.volume:.3f}, {len(part.edges())} edges, "
          f"{which} picks {len(picked)}", flush=True)
    fn = blocks.fillet_edges if op == "fillet" else blocks.chamfer_edges
    out = fn(part, radius, which)
    print(f"OK  {op} {radius} {which}: {out.volume:.3f} mm3", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=float)
    ap.add_argument("--edges", default="horizontal")
    ap.add_argument("--op", default="fillet")
    a = ap.parse_args()
    if a.radius is not None:
        try:
            one(a.radius, a.edges, a.op)
        except Exception as e:                       # noqa: BLE001 — the point
            print(f"REFUSED {a.op} {a.radius} {a.edges}: {type(e).__name__}: "
                  f"{str(e)[:160]}", flush=True)
        return 0
    for op, which in (("fillet", "horizontal"), ("fillet", "all"),
                      ("chamfer", "horizontal")):
        for r in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 2.0):
            cmd = [sys.executable, __file__, "--radius", str(r),
                   "--edges", which, "--op", op]
            p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
            tail = [ln for ln in p.stdout.splitlines() if ln.startswith(("OK", "REFUSED"))]
            code = p.returncode & 0xFFFFFFFF
            verdict = tail[0] if tail else f"DIED 0x{code:08X}"
            print(f"{op:8s} {which:10s} r={r:<5g} -> {verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
