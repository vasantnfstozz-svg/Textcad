"""Do the two overnight shell findings (2026-09-15/16) share one cause — a wall
thinner than the offset can survive — and can a ray cast see it BEFORE the
kernel is asked?  Run under probes/memcap.py; the shells here crash and stall.

  python probes/memcap.py --gb 6 --timeout 900 -- python probes/shell_thin_wall_probe.py bodies
  python probes/memcap.py --gb 6 --timeout 900 -- python probes/shell_thin_wall_probe.py shells
"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

from build123d import export_brep, import_brep, Part, Vector
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin, gp_Pnt, gp_Dir

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = {
    "mypart": ("bugs/20260915-210615-my-part-s95959-step18", "j5_shell"),
    "mypart9": ("bugs/20260916-011919-my-part-9-s96223-step19", "j1_chamfer"),
}


def body_of(folder: str, fid: str):
    from document import Document
    doc = Document.from_data(json.loads((ROOT / folder / "before.tcad.json").read_text(encoding="utf-8")))
    doc.rebuild()
    return doc._parts[fid]


def thinnest(body, openings=(), per_face=12, tol=0.01):
    """(min wall, need-factor, point, n_rays, seconds) by rays from face samples along -normal."""
    t0 = time.perf_counter()
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(body.wrapped, 1e-6)
    best = None
    n_rays = 0
    for face in body.faces():
        if any(face.wrapped.IsSame(o.wrapped) for o in openings):
            continue
        verts, tris = face.tessellate(tol)
        if not tris:
            continue
        step = max(1, len(tris) // per_face)
        for tri in tris[::step]:
            a, b, c = (verts[i] for i in tri)
            p = (a + b + c) / 3
            n = face.normal_at(p)
            # start 2 tolerances INSIDE: a curved face's triangle centroid sits on the
            # air side by up to `tol`, and the ray re-crossed its own face at 0.003 mm
            lin = gp_Lin(gp_Pnt(*(p - n * (2 * tol))), gp_Dir(*(-n)))
            inter.Perform(lin, 0.0, 1e9)
            n_rays += 1
            if not inter.IsDone() or inter.NbPnt() == 0:
                continue
            w = min(inter.WParameter(i) for i in range(1, inter.NbPnt() + 1)) + 2 * tol
            i_hit = min(range(1, inter.NbPnt() + 1), key=inter.WParameter)
            hit_open = any(inter.Face(i_hit).IsSame(o.wrapped) for o in openings)
            need = 1.0 if hit_open else 2.0
            if best is None or w / need < best[0] / best[1]:
                best = (w, need, tuple(round(x, 2) for x in p))
    return best, n_rays, time.perf_counter() - t0


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "bodies"
    import sketch
    if what == "bodies":
        for key, (folder, fid) in FOLDERS.items():
            body = body_of(folder, fid)
            export_brep(body, str(ROOT / "probes" / f"_thin_{key}.brep"))
            print(f"{key}: vol {body.volume:.3f} faces {len(body.faces())} lumps {len(body.solids())} "
                  f"bbox {body.bounding_box().size}")
            top = sketch.shell_openings(body, None, "top")
            for label, ops in (("closed", ()), ("top open", top)):
                best, n, s = thinnest(body, ops)
                print(f"   {label:9s}: thinnest {best[0]:.3f} mm (need factor {best[1]:g}) near {best[2]}, "
                      f"{n} rays in {s:.2f} s")
        # a plain box for the timing baseline + correctness (20x20x10 -> 10 closed, 10 top open with factor 1)
        from build123d import Box
        box = Part(Box(20, 20, 10).wrapped)
        print("box closed", thinnest(box)[0], "top open", thinnest(box, sketch.shell_openings(box, None, "top"))[0])
    else:
        import kernelguard
        for key, ts, budget in (
                                ("mypart9", (1.6, 1.7, 1.8, 1.85), 90),):
            body = import_brep(str(ROOT / "probes" / f"_thin_{key}.brep"))
            body = Part(body.wrapped) if not isinstance(body, Part) else body
            for t in ts:
                t0 = time.perf_counter()
                try:
                    openings = sketch.shell_openings(body, None, "top")
                    walls = f"walls of {t:g} mm"
                    out = kernelguard.guarded("shell", body, {
                        "thickness": t, "direction": "inside", "walls": walls,
                        "picks": kernelguard.indices(body.faces(), openings),
                        "marks": kernelguard._marks(openings),
                        "crashed": f"shell: {walls} CRASHED", "stopped": f"shell: {walls} STOPPED <minutes>"},
                        lambda: sketch.shell_after_guards(body, t, "inside", openings, walls), budget=budget)
                    print(f"{key} t={t}: OK {body.volume:.2f} -> {out.volume:.2f} in {time.perf_counter()-t0:.1f} s")
                except Exception as e:
                    print(f"{key} t={t}: {type(e).__name__} in {time.perf_counter()-t0:.1f} s: {str(e)[:90]}")
        kernelguard.shutdown()
