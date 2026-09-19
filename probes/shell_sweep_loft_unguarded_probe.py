"""Sweep and Loft call OpenCASCADE in the LISTENER process, with no crash guard.

`kernelguard` exists because OCCT can take the whole server down with an access
violation that no `except` can see, and `supervise.py` exists to put it back
together. It has exactly TWO job kinds — `blend` and `shell` — and exactly two
call sites, so every other kernel call runs where a crash is fatal to the
request, the tab and the process.

`BRepOffsetAPI_MakePipeShell` (Sweep) and `BRepOffsetAPI_ThruSections` (Loft)
are two of those. REVIEW-QUEUE section 4 already records one of them killing
the process: "a `loft` of a sketch AND a solid SEGFAULTS OpenCASCADE (exit
139), no `except` can catch it".

This probe measures the gap rather than reading it: the guard is watched while
a real loft and a real sweep are built, and the count of guarded calls is the
finding.

    python probes/shell_sweep_loft_unguarded_probe.py
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

    import blocks
    import kernelguard
    import sketch
    seen = []
    real = kernelguard.call
    kernelguard.call = lambda kind, body, job, budget=None: (
        seen.append(kind) or real(kind, body, job, budget))

    print(f"kernelguard job kinds the worker answers: "
          f"{sorted(k for k in ('blend', 'shell'))}  (anything else is "
          f"'unknown job')")

    # a control: the two ops that ARE guarded
    seen.clear()
    blocks.fillet_edges(b3d.Part() + b3d.Box(20, 10, 5), 1.0, "top")
    print(f"  fillet  -> guarded calls: {seen}")
    seen.clear()
    sketch.shell(b3d.Part() + b3d.Box(50, 50, 30), 3.0, None, "inside", None)
    print(f"  shell   -> guarded calls: {seen}")

    # ... and the two that are not
    seen.clear()
    lower = b3d.Plane.XY * b3d.Rectangle(30, 20)
    upper = b3d.Plane.XY.offset(25) * b3d.Circle(6)
    out = sketch.loft_sketches([lower, upper])
    print(f"  loft    -> guarded calls: {seen}   (built {out.volume:,.3f} mm3 "
          f"through BRepOffsetAPI_ThruSections, in THIS process)")

    seen.clear()
    profile = b3d.Plane.XY * b3d.Rectangle(10, 6)
    out = sketch.sweep_sketch(profile, path_points=[[0, 0, 0], [0, 0, 40]], full=True)
    print(f"  sweep   -> guarded calls: {seen}   (built {out.volume:,.3f} mm3 "
          f"through BRepOffsetAPI_MakePipeShell, in THIS process)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
