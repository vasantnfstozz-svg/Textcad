"""REVIEW of cc78019: what does the PRE-KERNEL guard cost, and where does it run?

`shell()` calls `assert_something_would_be_hollowed` BEFORE `kernelguard.guarded`,
so `deepest_material` tessellates every face, fires a ray per sample and measures
each station with BRepExtrema IN THE PARENT PROCESS, with no budget and no crash
net. The brief says the 675-face autonomiq-panel body was never measured there.

    python probes/shell_depth_cost_probe.py --body probes/_panel_scaled_body.brep --t 2.7
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import build123d as b3d  # noqa: E402


def main() -> int:
    import sketch
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True)
    ap.add_argument("--t", type=float, default=2.7)
    a = ap.parse_args()
    part = b3d.Part(b3d.import_brep(str(ROOT / a.body)).wrapped)
    faces = part.faces()
    bb = part.bounding_box()
    print(f"body {a.body}: {part.volume:,.1f} mm3, {len(faces)} faces, "
          f"{len(part.solids())} lump(s), bbox {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f}",
          flush=True)
    tol = max(1e-3, 1e-4 * float(bb.diagonal))
    n = len(faces)
    per_face = max(1, min(12, 200_000 // (n * n)))
    print(f"tol {tol:.4g}, per_face {per_face}", flush=True)

    t0 = time.perf_counter()
    tris = 0
    for f in faces:
        tris += len(f.tessellate(tol)[1])
    print(f"tessellate all {n} faces: {time.perf_counter() - t0:.2f} s ({tris} triangles)", flush=True)

    for t in (a.t,):
        t0 = time.perf_counter()
        got = sketch.deepest_material(part, t)
        print(f"deepest_material(t={t}) -> depth {got[0]:.4g} in "
              f"{time.perf_counter() - t0:.2f} s   [allows: {got[0] >= t - got[2]}]", flush=True)
    t0 = time.perf_counter()
    got = sketch.deepest_material(part, 1e9)
    print(f"deepest_material(t=1e9, the REFUSAL path, every station) -> {got[0]:.4g} in "
          f"{time.perf_counter() - t0:.2f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
