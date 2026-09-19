"""What does it cost to CLASSIFY every station `deepest_material` measures?

The over-read (`probes/shell_r3_over_read_probe.py`) is a station that is not
in the material: a zero-area face's normal is meaningless, so the ray along it
runs through AIR and the station at half of that chord is 24.3295 mm from a
body 1.93 mm thick. Every station is arithmetic on a normal and a chord and is
never classified; `_climb_to_the_deepest` classifies every candidate it takes,
which is why the climb cannot do this and the sampling can.

The honest fix is to classify a station before believing it. This measures the
price: a `BRepClass3d_SolidClassifier.Perform` against the
`BRepExtrema_DistShapeShape` the station already pays for, on the bodies with
the most faces in the corpus — and then the end-to-end cost of the refusal
path, which is the one that measures every station.

    C:\\Python314\\python.exe probes/shell_r3_station_classify_cost.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def drilled(L, W, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def main() -> int:
    import build123d as b3d
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS_Compound

    import sketch
    cases = {
        "drilled_100 (106 faces)": lambda: drilled(60.0, 60.0, 10.0, 10, 1.0, 6.0),
        "drilled_19x19 (367 faces)": lambda: drilled(120.0, 120.0, 10.0, 19, 1.0, 6.0),
    }
    print(f"{'body':<28} {'faces':>6} {'extrema':>12} {'classify':>12}  ratio")
    for name, make in cases.items():
        solid = make()
        staying = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(staying)
        for f in solid.faces():
            builder.Add(staying, f.wrapped)
        ext = BRepExtrema_DistShapeShape()
        ext.LoadS1(staying)
        cls = BRepClass3d_SolidClassifier(solid.wrapped)
        pts = [(x * 0.7, x * 0.3 - 5, x * 0.1 - 2) for x in range(-40, 40)]
        t0 = time.perf_counter()
        for q in pts:
            ext.LoadS2(BRepBuilderAPI_MakeVertex(gp_Pnt(*q)).Vertex())
            ext.Perform()
            ext.Value()
        t1 = time.perf_counter()
        for q in pts:
            cls.Perform(gp_Pnt(*q), 1e-7)
            cls.State()
        t2 = time.perf_counter()
        a, b = (t1 - t0) / len(pts), (t2 - t1) / len(pts)
        print(f"{name:<28} {len(solid.faces()):>6} {a * 1e3:>9.3f} ms "
              f"{b * 1e3:>9.3f} ms  {b / max(a, 1e-12):6.3f}x", flush=True)

    print("\nend-to-end, the REFUSAL path (every station measured):")
    for name, make in cases.items():
        solid = make()
        t0 = time.perf_counter()
        got = sketch.deepest_material(solid, 1e9, ())
        print(f"  {name:<28} {time.perf_counter() - t0:6.2f} s  -> {got[0]:.4f}",
              flush=True)

    print("\nthe sliver fixture, whose station is OUT:")
    p = ROOT / "tests" / "fixtures" / "sliver_intersect_plate.brep"
    sliver = b3d.Part(b3d.import_brep(str(p)).wrapped)
    areas = sorted(float(f.area) for f in sliver.faces())
    print(f"  face areas: {', '.join(f'{x:.4g}' for x in areas[:6])} ... "
          f"{areas[-1]:.4g}")
    print(f"  smallest is {areas[0]:.3e} mm2")
    t0 = time.perf_counter()
    got = sketch.deepest_material(sliver, 1e9, ())
    print(f"  deepest_material {time.perf_counter() - t0:.2f} s -> {got[0]:.4f} "
          f"at {tuple(round(c, 4) for c in got[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
