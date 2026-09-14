"""autonomiq-panel seed 18884 step 2 (overnight run 2026-09-13): a CLOSED shell,
thickness 2.7, on a `scale 1.5` of designs/autonomiq-panel answered NOTHING for
600 s and the runner killed the child. The runner's stall ceiling was 600 s
against the guard's 900 s budget, so nobody ever learned what the kernel was
doing; `751db79` lifted the ceiling to the budget, and this probe asks the
question directly instead of replaying a 20-minute journey.

    python probes/shell_slow_panel.py --body      # build + measure the body
    python probes/shell_slow_panel.py --t 2.7     # one shell, one child, timed
    python probes/shell_slow_panel.py             # the sweep

One thickness per child, because an access violation kills the process.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BREP = ROOT / "probes" / "_panel_scaled_body.brep"


def build_body() -> None:
    """The journey's step 1: open the design the way the app does (from_data --
    NEVER /api/open, which pushes a version into the real .history/) and scale
    it by 1.5."""
    import json

    import build123d as b3d

    import blocks
    from document import Document

    data = json.loads((ROOT / "designs" / "autonomiq-panel.tcad.json").read_text("utf-8"))
    doc = Document.from_data(data)
    doc.rebuild()
    part = doc._parts.get("autonomiq_panel")
    if part is None:
        raise SystemExit("autonomiq_panel has no part -- the design did not build")
    scaled = blocks.scale_uniform(part, 1.5)
    b3d.export_brep(scaled, str(BREP))
    bb = scaled.bounding_box().size
    lumps = scaled.solids()
    print(f"body: {scaled.volume:.1f} mm3, {len(scaled.faces())} faces, "
          f"{len(scaled.edges())} edges, {len(lumps)} lump(s), "
          f"bbox {bb.X:.2f} x {bb.Y:.2f} x {bb.Z:.2f} mm", flush=True)
    for i, lump in enumerate(lumps):
        s = lump.bounding_box().size
        print(f"  lump {i}: {lump.volume:.1f} mm3, {len(lump.faces())} faces, "
              f"smallest extent {min(s.X, s.Y, s.Z):.4g} mm", flush=True)


def one(t: float, direction: str) -> None:
    import build123d as b3d

    import sketch
    part = b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    t0 = time.perf_counter()
    out = sketch.shell(part, t, None, direction, None)
    print(f"OK t {t} {direction}: {part.volume:.1f} -> {out.volume:.1f} mm3, "
          f"valid {out.is_valid} in {time.perf_counter() - t0:.1f} s", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", action="store_true")
    ap.add_argument("--t", type=float)
    ap.add_argument("--direction", default="inside")
    a = ap.parse_args()
    if a.body:
        build_body()
        return 0
    if a.t is not None:
        t0 = time.perf_counter()
        try:
            one(a.t, a.direction)
        except Exception as e:                        # noqa: BLE001 -- the point
            print(f"REFUSED t {a.t}: {type(e).__name__}: {str(e)[:200]} "
                  f"in {time.perf_counter() - t0:.1f} s", flush=True)
        return 0
    if not BREP.exists():
        build_body()
    for t in (0.5, 1.0, 2.7, 5.0):
        t0 = time.perf_counter()
        p = subprocess.run([sys.executable, __file__, "--t", str(t)],
                           capture_output=True, text=True, cwd=str(ROOT))
        tail = [ln for ln in p.stdout.splitlines() if ln.startswith(("OK", "REFUSED"))]
        code = p.returncode & 0xFFFFFFFF
        print(f"t={t:<4g} -> {tail[0] if tail else f'DIED 0x{code:08X}'} "
              f"[child {time.perf_counter() - t0:.1f} s]", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
