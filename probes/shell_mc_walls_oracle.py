"""What the walls of an inward shell REALLY weigh, for any body, by Monte Carlo.

The walls of a `t` shell are exactly the material within `t` of the faces that
stay, so their volume is a probability: sample the bounding box, keep the
points inside the body, and count the ones whose exact distance to the staying
faces is at most `t`. One classifier and one `BRepExtrema` are built once and
re-used, which is what makes this affordable on a real body.

It is INDEPENDENT of the offset the kernel runs — no `offset`, no boolean, no
closed form — so it is the only thing that can say whether a result the health
checks call sound is the right volume.

    python probes/memcap.py --gb 6 --timeout 1800 -- \\
        C:\\Python314\\python.exe probes/shell_mc_walls_oracle.py \\
        --body oneplus_case_shell_body --t 0.5 --shots 60000
"""
import argparse
import math
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", default="oneplus_case_shell_body")
    ap.add_argument("--t", type=float, default=0.5)
    ap.add_argument("--shots", type=int, default=60000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    import build123d as b3d
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    from OCP.TopoDS import TopoDS_Compound

    p = ROOT / "tests" / "fixtures" / f"{a.body}.brep"
    solid = b3d.Part(b3d.import_brep(str(p)).wrapped)
    v_in = float(solid.volume)
    skin = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(skin)
    for f in solid.faces():
        builder.Add(skin, f.wrapped)
    cls = BRepClass3d_SolidClassifier(solid.wrapped)
    ext = BRepExtrema_DistShapeShape()
    ext.LoadS1(skin)
    bb = solid.bounding_box()
    v_box = (bb.max.X - bb.min.X) * (bb.max.Y - bb.min.Y) * (bb.max.Z - bb.min.Z)
    print(f"{a.body}: {len(solid.faces())} faces, {v_in:,.3f} mm3, "
          f"bbox {v_box:,.3f} mm3, t = {a.t:g}", flush=True)

    rnd = random.Random(a.seed)
    t0, n_in, n_wall = time.perf_counter(), 0, 0
    for k in range(a.shots):
        q = gp_Pnt(rnd.uniform(bb.min.X, bb.max.X),
                   rnd.uniform(bb.min.Y, bb.max.Y),
                   rnd.uniform(bb.min.Z, bb.max.Z))
        cls.Perform(q, 1e-7)
        if cls.State() != TopAbs_State.TopAbs_IN:
            continue
        n_in += 1
        ext.LoadS2(BRepBuilderAPI_MakeVertex(q).Vertex())
        ext.Perform()
        if ext.IsDone() and ext.NbSolution() and float(ext.Value()) <= a.t:
            n_wall += 1
        if (k + 1) % 5000 == 0:
            print(f"   {k + 1:>7,} shots, {n_in:>6,} inside, walls so far "
                  f"{v_box * n_wall / (k + 1):,.1f} mm3 "
                  f"[{time.perf_counter() - t0:.0f}s]", flush=True)
    frac = n_wall / a.shots
    walls = v_box * frac
    sigma = v_box * math.sqrt(max(frac * (1 - frac), 1e-12) / a.shots)
    # the body's own volume by the SAME sample, as a calibration of the sampler
    body_mc = v_box * n_in / a.shots
    print(f"\nwalls {walls:,.1f} +/- {sigma:,.1f} mm3   "
          f"(the same sample weighs the body {body_mc:,.1f} against its exact "
          f"{v_in:,.3f}, i.e. {100 * (body_mc - v_in) / v_in:+.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
