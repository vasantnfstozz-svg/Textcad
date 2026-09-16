"""REVIEW of cc78019 / 275eeab: the assumptions `deepest_material` rests on.

1. Face.is_inside -- what does build123d actually do for a FACE?  (the code
   uses it to decide whether a face's centre lies ON the face)
2. `stays()` compares openings by IsSame -- do the Faces `shell_openings`
   returns really compare same against `solid.faces()`, for a NAME and a PICK?
   (`assert_every_lump_open` deliberately uses a geometric _shape_key instead)
3. normal_at on a REVERSED face: does the inward ray really go inward?
4. is the guard's exception surface translated?  it runs OUTSIDE kernelguard.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import build123d as b3d  # noqa: E402


def sec(s):
    print(f"\n=== {s} ===", flush=True)


def main() -> int:
    import blocks
    import sketch

    sec("1. Face.is_inside on a FACE")
    import inspect as _i
    print("build123d is_inside source:", flush=True)
    try:
        print(_i.getsource(b3d.Face.is_inside)[:600], flush=True)
    except Exception as e:
        print("  (no own is_inside:", e, ") -> inherited from Shape", flush=True)
        print(_i.getsource(b3d.topology.Shape.is_inside)[:600], flush=True)

    box = b3d.Box(50, 50, 50)
    top = sketch.named_face(box, "top")
    print(f"box top face: centre {tuple(round(v,3) for v in top.center())} "
          f"is_inside -> {top.is_inside(top.center())}", flush=True)
    cyl = b3d.Cylinder(10, 30)
    wall = [f for f in cyl.faces() if f.geom_type != b3d.GeomType.PLANE][0]
    print(f"cylinder wall: centre {tuple(round(v,3) for v in wall.center())} "
          f"(on the AXIS, not on the face) is_inside -> {wall.is_inside(wall.center())}", flush=True)
    # an L-shaped (non-convex) face: centre of mass lies OFF the face
    ell = b3d.Box(40, 40, 10) - b3d.Pos(10, 10, 0) * b3d.Box(24, 24, 20)
    lf = sketch.named_face(ell, "top")
    print(f"L-shaped top face: centre {tuple(round(v,3) for v in lf.center())} "
          f"is_inside -> {lf.is_inside(lf.center())}", flush=True)

    sec("2. openings vs solid.faces(): IsSame?")
    named = sketch.shell_openings(box, None, "top")
    print(f"NAME 'top': {len(named)} opening(s); "
          f"IsSame against solid.faces(): "
          f"{[any(o.wrapped.IsSame(f.wrapped) for f in box.faces()) for o in named]}", flush=True)
    c = named[0].center()
    pick = sketch.shell_openings(box, [{"center": [c.X, c.Y, c.Z], "normal": [0, 0, 1]}], None)
    print(f"PICK centre+normal: {len(pick)} opening(s); "
          f"IsSame against solid.faces(): "
          f"{[any(o.wrapped.IsSame(f.wrapped) for f in box.faces()) for o in pick]}", flush=True)
    d_closed = sketch.deepest_material(box, 1e9)
    d_open = sketch.deepest_material(box, 1e9, named)
    d_openpick = sketch.deepest_material(box, 1e9, pick)
    print(f"50mm box deepest: closed {d_closed[0]:.4f}, open-by-NAME {d_open[0]:.4f}, "
          f"open-by-PICK {d_openpick[0]:.4f}   (must match)", flush=True)

    sec("3. normal_at on a mirrored / reversed body")
    mir = b3d.Part(b3d.import_brep(str(ROOT / "tests/fixtures/my_part_5_mirror_body.brep")).wrapped)
    rev = sum(1 for f in mir.faces() if f.wrapped.Orientation().name == "TopAbs_REVERSED")
    print(f"my_part_5_mirror: {len(mir.faces())} faces, {rev} REVERSED", flush=True)
    bad = 0
    for f in mir.faces()[:200]:
        try:
            p = f.center()
            if not f.is_inside(p):
                continue
            n = f.normal_at(p)
            inside = mir.is_inside(p - n * 0.05)
            outside = mir.is_inside(p + n * 0.05)
            if not (inside and not outside):
                bad += 1
        except Exception:
            pass
    print(f"faces whose -normal does NOT point into the material: {bad} "
          f"(of the ones with an on-face centre)", flush=True)

    sec("4. what the user sees when the guard raises a non-ValueError")
    from OCP.StdFail import StdFail_NotDone
    for e in (StdFail_NotDone("BRep_Tool::Surface"), RuntimeError("Standard_ConstructionError")):
        print(f"  {type(e).__name__} -> {blocks.plain_cause(e)!r}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
