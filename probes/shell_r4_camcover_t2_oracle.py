"""ROUND FOUR, job one: the ONE cell of the user's library this sweep newly
REFUSES — is the refusal right or wrong?

`shell_r4_compare_verdicts.py` over all 362 refused cells of 45 designs found
exactly one cell that the PRE-SWEEP code (0670f58) allowed and the code at
HEAD refuses: designs/cam-cover-lower, 2 mm walls, closed, refused by
`assert_the_deepest_point_was_hollowed`. The old run's own record is

    {'t': 2.0, 'mode': 'closed', 'verdict': 'ALLOWED',
     'v_out': 73276.15540460715}

against a body of 73,433.800 mm3 — 157.645 mm3 removed, 0.215 per cent.

A refusal only stands if the thing refused is WRONG, so the cavity is measured
a completely different way: Monte Carlo over the bounding box, each point
classified against the solid and its distance to the surface measured exactly,
which is the same oracle `probes/shell_skin_camcover_probe.py` used to prove
this design's t = 1 handback in 2026-09-16. No offset is involved in the
oracle at all.

    C:\\Python314\\python.exe probes/shell_r4_camcover_t2_oracle.py
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-r4-hist"))


def main() -> int:
    import build123d as b3d

    import inspector
    import sketch
    from shell_skin_camcover_probe import eroded_volume_by_sampling
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", default="cam-cover-lower")
    ap.add_argument("--t", type=float, default=2.0)
    ap.add_argument("--n", type=int, default=120000)
    a = ap.parse_args()
    os.environ["TEXTCAD_KERNEL_GUARD"] = "0"        # raw kernel, in this process
    bodies = Path(os.environ.get("TEXTCAD_R4_BODIES") or (ROOT / "probes" / "_r4_bodies"))
    part = b3d.Part(b3d.import_brep(str(bodies / f"{a.body}.brep")).wrapped)
    v_in, area = float(part.volume), float(part.area)
    t = a.t
    print(f"{a.body}: {len(part.faces())} faces, {v_in:,.3f} mm3, "
          f"area {area:,.1f} mm2", flush=True)

    deep = sketch.assert_something_would_be_hollowed(part, t, [], f"walls of {t:g} mm")
    print(f"  the guard's own deep point: depth {deep[0]:.4f} mm at "
          f"({deep[1][0]:.4g}, {deep[1][1]:.4g}, {deep[1][2]:.4g}), tol {deep[2]:.3g}",
          flush=True)

    # both checks this sweep added, off: what the PRE-SWEEP code handed the user
    sketch.assert_walls_could_be_a_skin = lambda *args, **kw: None
    sketch.assert_the_deepest_point_was_hollowed = lambda *args, **kw: None
    out = sketch.shell_after_guards(part, t, "inside", [], f"walls of {t:g} mm")
    v_out = float(out.volume)
    print(f"  the kernel's result: {v_out:,.4f} mm3 of walls, cavity "
          f"{v_in - v_out:,.4f} mm3 ({(v_in - v_out) / v_in:.3%} of the body)",
          flush=True)
    print(f"  and every check the OLD code had says it is fine: valid "
          f"{bool(out.is_valid)}, watertight {inspector.closed_shell(out)}, "
          f"health {inspector.health(out)}", flush=True)

    cav, sig, v_mc = eroded_volume_by_sampling(part, t, a.n)
    print(f"  the ORACLE (Monte Carlo, {a.n:,} points, no offset): the body is "
          f"{v_mc:,.1f} mm3 by the same sampler (true {v_in:,.1f}), and the "
          f"material more than {t:g} mm from the surface is "
          f"{cav:,.1f} +/- {sig:,.1f} mm3", flush=True)
    off = (cav - (v_in - v_out)) / sig if sig else float("inf")
    print(f"  the kernel removed {v_in - v_out:,.4f} where {cav:,.1f} had to go "
          f"— {off:,.0f} sigma out", flush=True)

    at = deep[1]
    print(f"  and the deep point is IN the result the old code returned: "
          f"{sketch.point_is_inside(out, at)}  (it is {deep[0] - t:.4f} mm past "
          f"a {t:g} mm wall, so a correct shell cannot keep it)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
