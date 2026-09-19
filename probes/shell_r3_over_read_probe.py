"""The over-read: `deepest_material` answering from a point that is NOT in the
body.

The inert census (`probes/shell_r3_inert_census.py`) found `sliver_intersect_
plate` — one of the four committed crash fixtures — answering 24.3295 mm at
EVERY thickness from 0.2 to 8, from a point the solid classifier calls OUT.
A guard whose whole job is refusing must never read DEEPER than the truth: a
reading that is too deep hands a body the wall does not fit to a kernel that
segfaults on it, and quotes the user a wall limit that is too high.

Where can such a point come from? Every station is `p - nrm * (f * chord)`,
which is interior arithmetic ONLY while `-nrm` really points into the material.
`_climb_to_the_deepest` classifies every candidate it takes, so it cannot be
the source; a STATION is never classified at all.

    C:\\Python314\\python.exe probes/shell_r3_over_read_probe.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def state_of(shape, at) -> str:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(shape.wrapped)
    cls.Perform(gp_Pnt(*at), 1e-7)
    return {TopAbs_State.TopAbs_IN: "IN", TopAbs_State.TopAbs_OUT: "OUT",
            TopAbs_State.TopAbs_ON: "ON"}.get(cls.State(), "?")


def main() -> int:
    import build123d as b3d

    import sketch
    from shell_depth_oracle_probe import oracle_depth
    p = ROOT / "tests" / "fixtures" / "sliver_intersect_plate.brep"
    solid = b3d.Part(b3d.import_brep(str(p)).wrapped)
    bb = solid.bounding_box()
    print(f"sliver_intersect_plate: {len(solid.faces())} faces, "
          f"{len(solid.solids())} lumps, {solid.volume:,.4f} mm3, "
          f"box {bb.size.X:.4g} x {bb.size.Y:.4g} x {bb.size.Z:.4g}")

    print("\n--- what the guard answers ---")
    for t in (0.2, 1.0, 3.0, 8.0):
        got = sketch.deepest_material(solid, t, ())
        depth, at, tol = got
        print(f"  t={t:<5g} depth {depth:9.4f} at "
              f"({at[0]:9.4f},{at[1]:9.4f},{at[2]:9.4f})  "
              f"classifier says {state_of(solid, at)}  tol {tol:.3g}")

    print(f"  box min ({bb.min.X:.4f},{bb.min.Y:.4f},{bb.min.Z:.4f}) "
          f"max ({bb.max.X:.4f},{bb.max.Y:.4f},{bb.max.Z:.4f})")
    print("\n--- the truth, by an independent grid ---")
    truth, where = oracle_depth(solid, coarse=40, refine=5)
    print(f"  deepest material {truth:.4f} at {where} "
          f"[{state_of(solid, where) if where else '-'}]")
    print(f"  a body {bb.size.Z:.4f} mm thick cannot hold material more than "
          f"{bb.size.Z / 2:.4f} mm from its own faces")
    got = sketch.deepest_material(solid, 1e9, ())
    print(f"  the guard says    {got[0]:.4f}  -> "
          f"{'OVER-READ by %.4f mm' % (got[0] - truth) if got[0] > truth + 1e-3 else 'ok'}")

    print("\n--- where does the point come from? outward-pointing normals ---")
    bad = 0
    for i, face in enumerate(solid.faces()):
        c = face.center()
        if not face.is_inside(c):
            continue
        n = face.normal_at(c)
        # a step of one tolerance INTO the material must be inside the body
        step = max(1e-3, 1e-4 * float(solid.bounding_box().diagonal))
        st_in = state_of(solid, (c - n * step * 2).to_tuple())
        st_out = state_of(solid, (c + n * step * 2).to_tuple())
        if st_in != "IN":
            bad += 1
            print(f"  face {i:3d} area {face.area:12.4f} centre "
                  f"({c.X:8.3f},{c.Y:8.3f},{c.Z:8.3f}) normal "
                  f"({n.X:+.3f},{n.Y:+.3f},{n.Z:+.3f}): a step ALONG -normal is "
                  f"{st_in}, along +normal is {st_out}")
    print(f"  {bad} of {len(solid.faces())} faces point the wrong way "
          f"(or are too thin for a two-tolerance step)")

    print("\n--- the same question over the rest of the corpus ---")
    import gauntlet
    names = dict(gauntlet.BODIES)
    for fx in ("oneplus_case_shell_body", "impeller_cut_shell_body",
               "my_part_5_mirror_body"):
        q = ROOT / "tests" / "fixtures" / f"{fx}.brep"
        if q.exists():
            names[fx] = (lambda q=q: b3d.Part(b3d.import_brep(str(q)).wrapped))
    for name, make in names.items():
        body = make()
        g = sketch.deepest_material(body, 1e9, ())
        if g is None:
            print(f"  {name:<26} nothing measured")
            continue
        t_truth, _w = oracle_depth(body, coarse=18, refine=4)
        st = state_of(body, g[1])
        flag = "OVER-READ" if g[0] > t_truth + 1e-3 else ""
        print(f"  {name:<26} guard {g[0]:9.4f}  grid {t_truth:9.4f}  "
              f"point {st:<4} {flag}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
