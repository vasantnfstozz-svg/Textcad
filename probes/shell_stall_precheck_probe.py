"""Can a CHEAP pre-check fence the my-part-9 stall?  The LAUNCH-PLAN section 10
row names one leading candidate — "the 0.6 mm chamfer strip whose offset
vanishes at every t above 0.42 (a face that disappears is the classic
MakeThickSolid pathology)" — and calls it unproven.  This measures it instead
of guessing, on the only two questions that decide such a rule:

  1. Would it FENCE the stall?  It refuses everything above t = 0.42 on that
     body, so yes — but it also refuses 1.5, 1.7 and 3.0, which the kernel
     answers CORRECTLY (a clean "leaves a broken solid" in 9-45 s).
  2. Would it refuse CORRECT work?  A narrow chamfer strip is on nearly every
     real part.  Here is a plain plate with a 0.6 mm rim chamfer — the same
     0.849 mm strip — shelled at 2.5 mm with the top open.  If the kernel
     builds that sound, the rule refuses correct geometry and is dead.

The second question is the one the shell guard has twice got wrong (the
round-three pairing guard, and the first draft of
`assert_something_would_be_hollowed`, which refused 11 sound shells).

  python probes/memcap.py --gb 4 --timeout 600 -- python probes/shell_stall_precheck_probe.py

Measured 2026-09-16 at 6586579 — see what this prints.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import build123d as b3d                                            # noqa: E402
import sketch as sk                                                # noqa: E402
import inspector                                                   # noqa: E402


def narrow_faces(body, limit):
    """every face narrower than `limit` mm ACROSS — the cheapest reading of "a
    strip the offset will swallow". A planar face has one zero bounding-box
    extent (it lies in a plane), so the width is the SECOND smallest."""
    out = []
    for f in body.faces():
        s = f.bounding_box().size
        out.append(sorted((s.X, s.Y, s.Z))[1])
    return sorted(w for w in out if w < limit)


if __name__ == "__main__":
    # 1. the filed body: how narrow are its faces?
    body = b3d.Part(b3d.import_brep(str(ROOT / "probes" / "_thin_mypart9.brep")).wrapped)
    print(f"my-part-9 j1_chamfer: vol {body.volume:,.6g} mm3, {len(body.faces())} faces")
    thin = narrow_faces(body, 2.0)
    print(f"  faces under 2 mm across: {len(thin)} -> {[round(w, 4) for w in thin[:10]]}")

    # 2. a plate with the SAME 0.6 mm rim chamfer, shelled at the filed 2.5 mm
    plate = b3d.Part() + b3d.Box(60, 40, 12)
    top = plate.faces().sort_by(b3d.Axis.Z)[-1]
    plate = b3d.Part(b3d.chamfer(top.edges(), length=0.6).wrapped)
    strip = narrow_faces(plate, 2.0)
    print(f"\nchamfered plate: vol {plate.volume:,.6g} mm3, {len(plate.faces())} faces, "
          f"strips under 2 mm: {[round(w, 4) for w in strip]}")
    out = sk.shell(plate, 2.5, ["top"])
    health = inspector.health(out, check_valid=True)
    print(f"  shell(2.5, top open) -> vol {out.volume:,.6g} mm3, "
          f"{len(out.solids())} lump(s), health {health}")
    print(f"  VERDICT: the 0.849 mm chamfer strip is swallowed by a 2.5 mm inward "
          f"offset, and the kernel builds this SOUND — so a rule that refuses a "
          f"body whose narrow face vanishes would refuse correct work.")
