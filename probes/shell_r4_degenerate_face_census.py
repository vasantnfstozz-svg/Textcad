"""ROUND FOUR, attack three: round three stops BELIEVING a degenerate face's
ray; it does not stop CASTING it. Two questions it left unmeasured:

  1. Do the user's own bodies carry such a face at all?
  2. Does a ray from one ever reach a station that the classifier calls
     material — i.e. is "stop believing it" enough, or does a degenerate face
     also hand `deepest_material` a station it cannot tell from a good one?

A face is degenerate here when its own area is a vanishing fraction of the
body's: `sliver_intersect_plate` carries one of 4.725e-08 mm2 against a body
area of about 7,600 mm2, which is 6e-12. The census prints the smallest faces
of every body, the fraction they are, and — for the smallest — whether the ray
the sampler would cast from it runs through AIR.

    C:\\Python314\\python.exe probes/shell_r4_degenerate_face_census.py
    C:\\Python314\\python.exe probes/shell_r4_degenerate_face_census.py --design bit-tray
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-r4-hist"))

TINY = 1e-6            # mm2: a face this small cannot carry a trustworthy normal


def ray_report(solid, face, tol):
    """what the sampler's own ray from this face's first sample does: how far it
    runs, and whether the point at half of it is material"""
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    import sketch as sk
    try:
        verts, tris = face.tessellate(tol)
        if not tris:
            return None
        a, b, c = (verts[i] for i in tris[0])
        p = (a + b + c) * (1 / 3)
        nrm = face.normal_at(p)
    except Exception as e:                                       # noqa: BLE001
        return {"err": str(e)[:60]}
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(solid.wrapped, 1e-6)
    inter.Perform(gp_Lin(gp_Pnt(*(p - nrm * (2 * tol))), gp_Dir(*(-nrm))), 0.0, 1e9)
    if not inter.IsDone() or inter.NbPnt() == 0:
        return {"chord": None}
    hit = min(range(1, inter.NbPnt() + 1), key=inter.WParameter)
    chord = inter.WParameter(hit) + 2 * tol
    mid = p - nrm * (0.5 * chord)
    return {"chord": float(chord),
            "mid_material": sk.point_is_inside(solid, (mid.X, mid.Y, mid.Z))}


def census(name: str, solid) -> dict:
    import sketch as sk                                          # noqa: F401
    faces = solid.faces()
    total = float(solid.area)
    diag = float(solid.bounding_box().diagonal)
    tol = max(1e-3, 1e-4 * diag)
    areas = []
    for f in faces:
        try:
            areas.append((float(f.area), f))
        except Exception:                                        # noqa: BLE001
            areas.append((0.0, f))
    areas.sort(key=lambda x: x[0])
    tiny = [a for a, _f in areas if a < TINY]
    smallest, sf = areas[0]
    rep = ray_report(solid, sf, tol) if smallest < TINY else None
    row = {"body": name, "faces": len(faces), "area": total, "diag": diag,
           "smallest": smallest, "frac": (smallest / total) if total else None,
           "tiny_faces": len(tiny), "ray": rep}
    print(f"{name:34s} {len(faces):4d} faces  area {total:12,.2f}  smallest "
          f"{smallest:.6g} mm2 ({row['frac']:.2e} of it)  faces < {TINY:g}: {len(tiny)}"
          + (f"   RAY {rep}" if rep else ""), flush=True)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design")
    ap.add_argument("--out", default=str(ROOT / "probes" / "_r4_degenerate_faces.jsonl"))
    a = ap.parse_args()
    import build123d as b3d
    rows = []
    if a.design:
        from document import Document
        doc = Document.from_data(json.loads(
            (ROOT / "designs" / f"{a.design}.tcad.json").read_text(encoding="utf-8")))
        doc.rebuild()
        best = None
        for fid in doc.leaf_solid_ids():
            part = doc._parts.get(fid)
            if part is None:
                continue
            v = float(part.volume)
            if best is None or v > best[1]:
                best = (part, v)
        if best:
            rows.append(census(a.design, best[0]))
    else:
        import gauntlet
        for nm, make in sorted(gauntlet.BODIES.items()):
            rows.append(census("corpus/" + nm, make()))
        for p in sorted((ROOT / "tests" / "fixtures").glob("*.brep")):
            rows.append(census("fixture/" + p.stem,
                               b3d.Part(b3d.import_brep(str(p)).wrapped)))
    with Path(a.out).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
