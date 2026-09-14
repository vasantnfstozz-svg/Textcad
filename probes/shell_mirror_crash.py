"""my-part-5 seed 18800 step 25 (overnight run 2026-09-14): `shell {thickness:
2.1, open_face: "bottom"}` on `j2_mirror` SEGFAULTS OpenCASCADE. The kernel
worker turns that into a sentence and the app walks on, so the question this
probe answers is the one the my-part-8 folder taught us to ask: is the crash
the WHOLE finding, or is a neighbouring thickness coming back a silent WRONG
result the way that body's one-edge fillet did (`77bc7fa`)?

    python probes/shell_mirror_crash.py --body        # build + measure
    python probes/shell_mirror_crash.py --t 2.1       # one attempt, one child
    python probes/shell_mirror_crash.py               # the sweep

One thickness per child, because an access violation kills the process.
The oracle for a "successful" answer is independent of `shell_after_guards`'
own four checks: the walls must be somewhere between a thin skin and the
whole body, every lump must still be there, and the result must sit inside
the original bounding box (an inside shell cannot grow).
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FOLDER = ROOT / "bugs" / "20260913-193839-my-part-5-s18800-step25"
BREP = ROOT / "probes" / "_mirror_shell_body.brep"


def build_body() -> None:
    """Open the crash folder's `before` the way the app does -- `from_data`,
    never /api/open, which pushes a version into the real .history/."""
    import json

    import build123d as b3d

    from document import Document

    doc = Document.from_data(json.loads((FOLDER / "before.tcad.json").read_text("utf-8")))
    doc.rebuild()
    part = doc._parts.get("j2_mirror")
    if part is None:
        raise SystemExit("j2_mirror has no part -- the design did not build")
    b3d.export_brep(part, str(BREP))
    bb = part.bounding_box().size
    lumps = part.solids()
    print(f"body: {part.volume:.3f} mm3, {len(part.faces())} faces, "
          f"{len(part.edges())} edges, {len(lumps)} lump(s), "
          f"bbox {bb.X:.3f} x {bb.Y:.3f} x {bb.Z:.3f} mm, valid {part.is_valid}", flush=True)
    for i, lump in enumerate(lumps):
        s = lump.bounding_box().size
        print(f"  lump {i}: {lump.volume:.3f} mm3, {len(lump.faces())} faces, "
              f"smallest extent {min(s.X, s.Y, s.Z):.4g} mm", flush=True)


def one(t: float, face: str | None, direction: str) -> None:
    import build123d as b3d

    import sketch
    part = b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    v_in, bb_in, n_in = part.volume, part.bounding_box(), len(part.solids())
    t0 = time.perf_counter()
    out = sketch.shell(part, t, None, direction, face)
    took = time.perf_counter() - t0
    # the independent oracle -- not shell_after_guards' own checks
    bad = []
    if not (0.0 < out.volume < v_in):
        bad.append(f"walls are {out.volume:.3f} of {v_in:.3f} mm3")
    if out.volume < v_in * 0.02:
        bad.append(f"walls are only {100 * out.volume / v_in:.2f}% of the body")
    if len(out.solids()) != n_in:
        bad.append(f"{n_in} lump(s) in, {len(out.solids())} out")
    bb = out.bounding_box()
    grew = max(bb_in.min.X - bb.min.X, bb_in.min.Y - bb.min.Y, bb_in.min.Z - bb.min.Z,
               bb.max.X - bb_in.max.X, bb.max.Y - bb_in.max.Y, bb.max.Z - bb_in.max.Z)
    if direction == "inside" and grew > 1e-6:
        bad.append(f"bounding box grew by {grew:.4g} mm")
    verdict = "WRONG: " + "; ".join(bad) if bad else "sound"
    print(f"OK t {t} face {face} {direction}: {v_in:.3f} -> {out.volume:.3f} mm3 "
          f"({100 * out.volume / v_in:.1f}%), {len(out.solids())} lump(s), "
          f"valid {out.is_valid}, {verdict}, in {took:.1f} s", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", action="store_true")
    ap.add_argument("--t", type=float)
    ap.add_argument("--face", default="bottom")
    ap.add_argument("--direction", default="inside")
    a = ap.parse_args()
    if a.body:
        build_body()
        return 0
    if a.t is not None:
        try:
            one(a.t, None if a.face == "none" else a.face, a.direction)
        except Exception as e:                        # noqa: BLE001 -- the point
            print(f"REFUSED t {a.t} face {a.face}: {type(e).__name__}: "
                  f"{str(e)[:180]}", flush=True)
        return 0
    if not BREP.exists():
        build_body()
    for face in ("bottom", "top", "none"):
        for t in (0.2, 0.5, 0.8, 1.0, 1.5, 2.1, 2.5, 3.0, 5.0):
            p = subprocess.run([sys.executable, __file__, "--t", str(t), "--face", face],
                               capture_output=True, text=True, cwd=str(ROOT))
            tail = [ln for ln in p.stdout.splitlines() if ln.startswith(("OK", "REFUSED"))]
            code = p.returncode & 0xFFFFFFFF
            print(f"face {face:7s} t={t:<4g} -> {tail[0] if tail else f'DIED 0x{code:08X}'}",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
