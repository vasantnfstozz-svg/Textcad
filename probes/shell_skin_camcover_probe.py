"""REVIEW of 275eeab: is the hollow `assert_walls_could_be_a_skin` refuses on
designs/cam-cover-lower CORRECT?

The skin ceiling (2.0 x `area * t`) exists for a body handed back as its own
walls (my-part-5: 2.709 mm3 removed of 413262).  On the user's cam-cover-lower
it also fires on a result that removes 971.569 mm3 at t = 1 and 452.798 at
t = 0.5 -- three orders of magnitude more.  Is that a real cavity?

The kernel's cavity is the ERODED body: the points of the solid more than t
from its surface.  This measures that volume a completely different way --
Monte Carlo over the bounding box, classifying each point and measuring its
distance to the surface -- and compares.  If the two agree, the refusal is a
false one.

    python probes/shell_skin_camcover_probe.py
    python probes/shell_skin_camcover_probe.py --design my-part-5 --t 3
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def eroded_volume_by_sampling(solid, t: float, n: int, seed: int = 12345) -> tuple:
    """(estimate of the volume more than `t` from the surface, +/- one sigma),
    by classifying a fixed pseudo-random lattice against the solid"""
    import random

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    shell = solid.wrapped
    cls = BRepClass3d_SolidClassifier(shell)
    ext = BRepExtrema_DistShapeShape()
    ext.LoadS1(_faces_compound(solid))
    bb = solid.bounding_box()
    lo = (bb.min.X, bb.min.Y, bb.min.Z)
    span = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    box_v = span[0] * span[1] * span[2]
    rng = random.Random(seed)
    inside = deep = 0
    for _ in range(n):
        p = gp_Pnt(*(lo[i] + rng.random() * span[i] for i in range(3)))
        cls.Perform(p, 1e-7)
        if cls.State() != TopAbs_State.TopAbs_IN:
            continue
        inside += 1
        ext.LoadS2(BRepBuilderAPI_MakeVertex(p).Vertex())
        ext.Perform()
        if ext.IsDone() and float(ext.Value()) > t:
            deep += 1
    frac = deep / n
    sigma = (frac * (1 - frac) / n) ** 0.5
    return box_v * frac, box_v * sigma, inside / n * box_v


def _faces_compound(solid):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for f in solid.faces():
        b.Add(comp, f.wrapped)
    return comp


def main() -> int:
    import sketch
    from document import Document
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", default="cam-cover-lower")
    ap.add_argument("--t", type=float, action="append")
    ap.add_argument("--n", type=int, default=60000)
    a = ap.parse_args()
    ts = a.t or [0.5, 1.0]
    sketch.assert_walls_could_be_a_skin = lambda *args, **kw: None
    doc = Document.from_data(
        json.loads((ROOT / "designs" / f"{a.design}.tcad.json").read_text("utf-8")))
    doc.rebuild()
    fid, part = [(f, p) for f, p in doc._parts.items() if p is not None][-1]
    area, v_in = float(part.area), float(part.volume)
    print(f"{a.design}/{fid}: {len(part.faces())} faces, {v_in:,.3f} mm3, "
          f"area {area:,.1f} mm2, deepest material "
          f"{sketch.deepest_material(part, 1e9)[0]:.4f} mm", flush=True)
    for t in ts:
        t0 = time.perf_counter()
        try:
            out = sketch.shell_after_guards(part, t, "inside", [], f"walls of {t:g} mm")
        except Exception as e:                                # noqa: BLE001
            print(f"  t={t:g}: refused ({str(e)[:80]})", flush=True)
            continue
        removed = v_in - float(out.volume)
        est, sigma, v_est = eroded_volume_by_sampling(part, t, a.n)
        agree = abs(removed - est) <= 3 * sigma + 0.02 * max(removed, est)
        print(f"  t={t:g}: the kernel removed {removed:,.3f} mm3; sampling says "
              f"{est:,.3f} +/- {sigma:,.3f} (3 sigma) -> "
              f"{'AGREE, the cavity is real' if agree else 'DISAGREE'}", flush=True)
        print(f"        skin ratio {float(out.volume) / (area * t):.4f} against the "
              f"{sketch._SHELL_SKIN_FACTOR} ceiling; the BODY itself is "
              f"{v_in / (area * t):.4f} skins; volume check {v_est:,.0f} vs {v_in:,.0f} "
              f"[{time.perf_counter() - t0:.0f} s]", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
