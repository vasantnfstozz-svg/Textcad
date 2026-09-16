"""REVIEW of cc78019: does `deepest_material`'s SAMPLING ever UNDERSTATE the
depth badly enough to refuse a shell the kernel would build?

The guard refuses when no SAMPLED point is `t` from every staying face.  The
sample set is: one-to-twelve triangle centroids per face (ONE on any body with
130+ faces), each face's centre when it lies on the face, three stations along
each inward ray, two more towards an opening, and every opening sample.  This
probe measures the same quantity a completely different way -- a hierarchical
grid over the solid's interior -- and prints the gap.

A gap of D means the guard would refuse every wall between its own answer and
D, and the corpus that signed this guard off cannot see it: it only checked the
refusals the guard already makes, never whether the number itself is right.

    python probes/shell_depth_oracle_probe.py --shapes
    python probes/shell_depth_oracle_probe.py --designs
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

import build123d as b3d  # noqa: E402


def oracle_depth(solid, openings=(), coarse=14, refine=3, keep=24):
    """The deepest material by GRID, not by rays: classify a lattice of points
    against the solid, measure the inside ones to the staying faces, then
    refine around the best few.  Independent of every choice the guard makes."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    from OCP.TopoDS import TopoDS_Compound
    staying = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(staying)
    for f in solid.faces():
        if not any(f.wrapped.IsSame(o.wrapped) for o in openings):
            builder.Add(staying, f.wrapped)
    cls = BRepClass3d_SolidClassifier(solid.wrapped)
    ext = BRepExtrema_DistShapeShape()
    ext.LoadS1(staying)

    def depth_at(x, y, z):
        cls.Perform(gp_Pnt(x, y, z), 1e-7)
        if cls.State() != TopAbs_State.TopAbs_IN:
            return None
        ext.LoadS2(BRepBuilderAPI_MakeVertex(gp_Pnt(x, y, z)).Vertex())
        ext.Perform()
        return float(ext.Value()) if ext.IsDone() else None

    bb = solid.bounding_box()
    lo = [bb.min.X, bb.min.Y, bb.min.Z]
    hi = [bb.max.X, bb.max.Y, bb.max.Z]
    step = [(hi[i] - lo[i]) / (coarse + 1) for i in range(3)]
    pts = []
    for i in range(1, coarse + 1):
        for j in range(1, coarse + 1):
            for k in range(1, coarse + 1):
                p = (lo[0] + i * step[0], lo[1] + j * step[1], lo[2] + k * step[2])
                d = depth_at(*p)
                if d is not None:
                    pts.append((d, p))
    if not pts:
        return 0.0, None
    for _ in range(refine):
        pts.sort(key=lambda r: -r[0])
        pts = pts[:keep]
        step = [s / 2.5 for s in step]
        nxt = list(pts)
        for _d, p in pts:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        q = (p[0] + dx * step[0], p[1] + dy * step[1], p[2] + dz * step[2])
                        d = depth_at(*q)
                        if d is not None:
                            nxt.append((d, q))
        pts = nxt
    pts.sort(key=lambda r: -r[0])
    return pts[0]


def report(name, solid, openings, label, out):
    import sketch
    t0 = time.perf_counter()
    got = sketch.deepest_material(solid, 1e9, openings)
    guard = got[0] if got else 0.0
    t1 = time.perf_counter()
    od, op = oracle_depth(solid, openings)
    t2 = time.perf_counter()
    gap = od - guard
    flag = "   <<< GUARD UNDERSTATES" if gap > max(0.05, 0.02 * od) else ""
    print(f"  {label:10s} guard {guard:9.4f}  oracle {od:9.4f}  gap {gap:+8.4f}"
          f"   [{t1 - t0:.1f}s / {t2 - t1:.1f}s]{flag}", flush=True)
    if flag:
        out.append((name, label, guard, od, op))


def designs():
    from document import Document
    for path in sorted((ROOT / "designs").glob("*.tcad.json")):
        try:
            doc = Document.from_data(json.loads(path.read_text("utf-8")))
            doc.rebuild()
        except Exception as e:                       # noqa: BLE001
            print(f"{path.stem}: did not build ({str(e)[:60]})", flush=True)
            continue
        for fid, part in doc._parts.items():
            if part is None:
                continue
            try:
                if not part.solids() or part.volume <= 0:
                    continue
            except Exception:                        # noqa: BLE001
                continue
            yield f"{path.stem}/{fid}", part


def shapes():
    """shapes built to defeat a ray-from-the-faces sampler"""
    yield "box50", b3d.Box(50, 50, 50)
    # a thick bulb on a thin stem: the bulb's material is far from every face
    # centre and the stem's rays never reach it
    yield "bulb_on_stem", b3d.Part() + b3d.Cylinder(3, 40) + b3d.Pos(0, 0, 25) * b3d.Sphere(12)
    # a ring of thin fins around a thick hub -- hundreds of faces, so per_face 1
    hub = b3d.Cylinder(14, 30)
    fins = b3d.Part()
    for i in range(48):
        fins += b3d.Rot(0, 0, i * 7.5) * b3d.Pos(22, 0, 0) * b3d.Box(18, 1.6, 26)
    yield "finned_hub", b3d.Part() + hub + fins
    # a thick core buried under a lid, reached only through a slot
    yield "cored_block", b3d.Part() + (b3d.Box(60, 60, 40) - b3d.Pos(0, 0, 21) * b3d.Box(40, 40, 4))
    # a wedge: no face normal passes through the thick end's middle
    yield "wedge", b3d.Part() + b3d.extrude(
        b3d.Plane.XZ * b3d.make_face(b3d.Polyline((-40, 0), (40, 0), (40, 30), (-40, 2), close=True)), 40)
    # an L in plan with a big thick square and a long thin arm
    yield "thick_L", b3d.Part() + b3d.Box(60, 60, 30) + b3d.Pos(55, -26, 0) * b3d.Box(50, 8, 30)


def main() -> int:
    import sketch
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs", action="store_true")
    ap.add_argument("--shapes", action="store_true")
    ap.add_argument("--max-faces", type=int, default=900)
    a = ap.parse_args()
    out = []
    src = designs() if a.designs else shapes()
    for name, part in src:
        nf = len(part.faces())
        if nf > a.max_faces:
            print(f"{name}: {nf} faces -- skipped (oracle too slow)", flush=True)
            continue
        bb = part.bounding_box().size
        print(f"{name}: {nf} faces, {len(part.solids())} lump(s), "
              f"{part.volume:,.0f} mm3, bbox {bb.X:.1f} x {bb.Y:.1f} x {bb.Z:.1f}", flush=True)
        try:
            report(name, part, [], "closed", out)
        except Exception as e:                       # noqa: BLE001
            print(f"  closed: RAISED {type(e).__name__}: {str(e)[:90]}", flush=True)
        try:
            top = sketch.shell_openings(part, None, "top")
        except Exception:                            # noqa: BLE001
            top = None
        if top:
            try:
                report(name, part, top, "top open", out)
            except Exception as e:                   # noqa: BLE001
                print(f"  top open: RAISED {type(e).__name__}: {str(e)[:90]}", flush=True)
    print(f"\n{len(out)} case(s) where the guard's number is BELOW the oracle's:", flush=True)
    for r in out:
        print("   ", r[0], r[1], f"guard {r[2]:.4f} vs oracle {r[3]:.4f} at {r[4]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
