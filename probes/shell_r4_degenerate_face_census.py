"""ROUND FOUR, attack three: round three stops BELIEVING a degenerate face's
ray; it does not stop CASTING it. Two questions it left unmeasured:

  1. Do the user's own bodies carry such a face at all?
  2. Does a ray from one ever reach a station the classifier calls material —
     i.e. is "stop believing it" enough, or does a degenerate face also hand
     `deepest_material` a station it cannot tell from a good one?

A face is degenerate here when its own area is a vanishing fraction of the
body's: `sliver_intersect_plate` carries one of 4.725e-08 mm2 against a body
area of about 7,600 mm2. The census prints the smallest faces of every body,
the fraction they are, and — for every face under the threshold — what the ray
the sampler would cast from it does.

The user's bodies are read from the .brep cache the verdict probe writes
(`probes/_r4_bodies`), so no design is rebuilt here.

    C:\\Python314\\python.exe probes/shell_r4_degenerate_face_census.py
    C:\\Python314\\python.exe probes/shell_r4_degenerate_face_census.py --body bit-tray
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-r4-hist"))

TINY = float(os.environ.get("TEXTCAD_R4_TINY") or 1e-6)   # mm2: a face this
# small cannot carry a trustworthy normal. Raised by the environment to ask the
# same question of the smallest faces a body DOES carry.
BODY_S = 300.0


def bodies_dir() -> Path:
    return Path(os.environ.get("TEXTCAD_R4_BODIES") or (ROOT / "probes" / "_r4_bodies"))


def ray_report(solid, face, tol) -> dict:
    """what the sampler's own ray from this face's first sample does: how far it
    runs, and whether the point at half of it is material"""
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    import sketch as sk
    try:
        verts, tris = face.tessellate(tol)
        if not tris:
            return {"tris": 0}
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
    chord = float(inter.WParameter(hit)) + 2 * tol
    mid = p - nrm * (0.5 * chord)
    return {"chord": chord,
            "mid_material": sk.point_is_inside(solid, (mid.X, mid.Y, mid.Z)),
            "mid_depth_over_thin": None}


def census(name: str, solid) -> dict:
    faces = solid.faces()
    total = float(solid.area)
    bb = solid.bounding_box()
    diag = float(bb.diagonal)
    thin = min(bb.size.X, bb.size.Y, bb.size.Z)
    tol = max(1e-3, 1e-4 * diag)
    areas = []
    for f in faces:
        try:
            areas.append((float(f.area), f))
        except Exception:                                        # noqa: BLE001
            areas.append((0.0, f))
    areas.sort(key=lambda x: x[0])
    tiny = [(a, f) for a, f in areas if a < TINY]
    smallest, sf = areas[0]
    rays = [ray_report(solid, f, tol) for _a, f in tiny[:6]]
    air = sum(1 for r in rays if r.get("mid_material") is False)
    row = {"body": name, "faces": len(faces), "area": total, "thinnest": thin,
           "smallest": smallest, "frac": (smallest / total) if total else None,
           "tiny_faces": len(tiny), "rays": rays, "air_rays": air}
    print(f"{name:32s} {len(faces):5d} faces  area {total:12,.2f}  thinnest "
          f"{thin:8.4f}  smallest face {smallest:.6g} mm2 ({row['frac']:.2e})  "
          f"faces < {TINY:g}: {len(tiny)}"
          + (f"  RAYS {rays}" if tiny else ""), flush=True)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", help="one cached .brep stem, or a corpus/fixture name")
    ap.add_argument("--out", default=str(ROOT / "probes" / "_r4_degenerate_faces.jsonl"))
    a = ap.parse_args()
    out = Path(a.out)
    if a.body:
        import build123d as b3d
        if a.body.startswith("corpus/"):
            import gauntlet
            solid = gauntlet.BODIES[a.body[len("corpus/"):]]()
        elif a.body.startswith("fixture/"):
            solid = b3d.Part(b3d.import_brep(str(
                ROOT / "tests" / "fixtures" / (a.body[len("fixture/"):] + ".brep"))).wrapped)
        else:
            solid = b3d.Part(b3d.import_brep(str(bodies_dir() / f"{a.body}.brep")).wrapped)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(census(a.body, solid)) + "\n")
        return 0
    import gauntlet
    names = ["corpus/" + n for n in sorted(gauntlet.BODIES)]
    names += ["fixture/" + p.stem for p in sorted((ROOT / "tests" / "fixtures").glob("*.brep"))]
    names += [p.stem for p in sorted(bodies_dir().glob("*.brep"))]
    for n in names:
        try:
            p = subprocess.run([sys.executable, __file__, "--body", n, "--out", str(out)],
                               capture_output=True, text=True, cwd=str(ROOT),
                               timeout=BODY_S,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired:
            print(f"{n}: TIMED OUT - not covered", flush=True)
            continue
        if p.stdout.strip():
            print(p.stdout.strip(), flush=True)
        elif p.stderr.strip():
            print(f"{n}: died 0x{p.returncode & 0xFFFFFFFF:08X} "
                  f"{p.stderr.strip().splitlines()[-1][:120]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
