"""Is a shell result SOUND, or is it the body handed back as a hollow?

`assert_walls_could_be_a_skin` refuses an inward shell whose walls measure more
than `_SHELL_SKIN_FACTOR * area * t`. Calibrating that ceiling needs the one
thing the corpora never had: an answer to "what SHOULD this result weigh",
measured a completely different way from the kernel that produced it.

THE ORACLE. The walls an inward shell keeps are exactly the material within `t`
of the surface, so

    true walls = vol({p in solid : dist(p, boundary) <= t})

and an OUTSIDE shell's walls are the same set on the other side,

    true walls = vol({p not in solid : dist(p, boundary) <= t}).

Both are measured by Monte Carlo over the bounding box (grown by `t` for the
outside case): classify each point against the solid, measure its exact
distance to the boundary with `BRepExtrema`, and scale by the box volume. The
count is reported with its standard error, so "the kernel is wrong" is a
statement with a sigma on it and not a feeling. The classification is
calibrated against the solid's own `volume`, which catches a broken sampler
before it can call a good result bad.

    python probes/shell_skin_oracle_probe.py --design cam-cover-lower --t 1
    python probes/shell_skin_oracle_probe.py --body wedge --t 3 --direction outside
    python probes/shell_skin_oracle_probe.py --design my-part-3 --t 1 2 3 -n 20000

One body per run: the classifier and the distance tool are OCCT, and two of
those at once is how this box has been killed before.
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def skin_volume(solid, t: float, outside: bool, n: int, seed: int = 20260917):
    """(volume, standard error, calibration) of the material within `t` of the
    boundary, on the inside (or outside) of `solid`, by Monte Carlo.

    `calibration` is the sampler's own estimate of the solid's volume over the
    real one: a number near 1.0 says the classifier and the box agree, and
    anything else says the estimate below is not to be believed."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(solid.wrapped)
    ext = BRepExtrema_DistShapeShape()
    ext.LoadS1(solid.wrapped)
    bb = solid.bounding_box()
    pad = t * 1.05 if outside else 0.0
    lo = (bb.min.X - pad, bb.min.Y - pad, bb.min.Z - pad)
    hi = (bb.max.X + pad, bb.max.Y + pad, bb.max.Z + pad)
    box_v = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
    rng = random.Random(seed)
    hits = inside = 0
    for _ in range(n):
        p = gp_Pnt(*(lo[i] + rng.random() * (hi[i] - lo[i]) for i in range(3)))
        cls.Perform(p, 1e-7)
        is_in = cls.State() == TopAbs_State.TopAbs_IN
        inside += is_in
        if is_in == outside:                      # wrong side for this question
            continue
        ext.LoadS2(BRepBuilderAPI_MakeVertex(p).Vertex())
        ext.Perform()
        if ext.IsDone() and float(ext.Value()) <= t:
            hits += 1
    f = hits / n
    err = (f * (1 - f) / n) ** 0.5
    return f * box_v, err * box_v, (inside / n * box_v) / float(solid.volume)


def the_body(args):
    import build123d as b3d
    if args.design:
        from document import Document
        doc = Document.from_data(json.loads(
            (ROOT / "designs" / f"{args.design}.tcad.json").read_text("utf-8")))
        doc.rebuild()
        parts = [p for p in doc._parts.values() if p is not None]
        return args.design, parts[-1]
    if args.fixture:
        p = ROOT / "tests" / "fixtures" / f"{args.fixture}.brep"
        return args.fixture, b3d.Part(b3d.import_brep(str(p)).wrapped)
    import gauntlet
    return args.body, gauntlet.BODIES[args.body]()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design")
    ap.add_argument("--fixture")
    ap.add_argument("--body")
    ap.add_argument("--direction", default="inside", choices=("inside", "outside"))
    ap.add_argument("--t", type=float, nargs="+", default=[1.0])
    ap.add_argument("-n", type=int, default=12000)
    args = ap.parse_args()

    import build123d as b3d

    import inspector
    import sketch
    sketch.assert_walls_could_be_a_skin = lambda *a, **k: None    # the thing under test
    name, solid = the_body(args)
    v_in, area = float(solid.volume), float(solid.area)
    out_dir = args.direction == "outside"
    print(f"{name}: {len(solid.faces())} faces, {len(solid.solids())} lump(s), "
          f"{v_in:,.3f} mm3, area {area:,.3f} mm2, {args.direction}", flush=True)
    for t in args.t:
        t0 = time.perf_counter()
        truth, err, cal = skin_volume(solid, t, out_dir, args.n)
        t1 = time.perf_counter()
        try:
            amount = t if out_dir else -t
            off = b3d.offset(solid, amount=amount, kind=b3d.Kind.INTERSECTION)
            got = (off - solid) if out_dir else (solid - off)
            v_out = float(got.volume)
            sound = (inspector._try(lambda: bool(got.is_valid)) is not False
                     and inspector.closed_shell(got) and v_out > 0
                     and (out_dir or v_out < v_in))
        except Exception as e:                                   # noqa: BLE001
            print(f"  t={t:<5g} kernel refused ({type(e).__name__}: {str(e)[:60]})",
                  flush=True)
            continue
        ratio = v_out / (area * t)
        off_by = (v_out - truth) / max(err, 1e-9)
        print(f"  t={t:<5g} walls {v_out:>13,.3f}  oracle {truth:>13,.3f} "
              f"+/- {err:>9,.3f}  ratio {ratio:7.4f}  {off_by:+9.1f} sigma  "
              f"{'checks-pass' if sound else 'CHECKS-FAIL'}  cal {cal:.4f}  "
              f"[{t1 - t0:.0f}s MC]"
              + ("   <<< THE KERNEL IS WRONG" if abs(off_by) > 8 else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
