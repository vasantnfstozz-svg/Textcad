"""The ONE door by which `_climb_to_the_deepest` could RAISE the answer wrongly:
`outside()` returns True only for TopAbs_OUT, so UNKNOWN (and ON) are taken as
inside.  An exterior point measures a real, possibly large, distance to the
staying faces, and outside the body that distance RISES with every step — so one
wrong classification lets the climb walk out of the solid and read a depth the
body does not have, and the guard allows a shell the kernel segfaults on.

How often does the classifier answer UNKNOWN on the shapes this guard sees?"""
import json, os, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))
import build123d as b3d
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_State

NAMES = {TopAbs_State.TopAbs_IN: "IN", TopAbs_State.TopAbs_OUT: "OUT",
         TopAbs_State.TopAbs_ON: "ON", TopAbs_State.TopAbs_UNKNOWN: "UNKNOWN"}

def survey(label, part, n=20000, seed=3):
    cls = BRepClass3d_SolidClassifier(part.wrapped)
    bb = part.bounding_box()
    rnd = random.Random(seed)
    tally = {"IN": 0, "OUT": 0, "ON": 0, "UNKNOWN": 0}
    # points spread over a box 20 per cent LARGER than the body, so plenty land
    # just outside, and many exactly on face planes (the awkward ones)
    pad = 0.1 * max(bb.size.X, bb.size.Y, bb.size.Z)
    for _ in range(n):
        p = (rnd.uniform(bb.min.X - pad, bb.max.X + pad),
             rnd.uniform(bb.min.Y - pad, bb.max.Y + pad),
             rnd.uniform(bb.min.Z - pad, bb.max.Z + pad))
        cls.Perform(gp_Pnt(*p), 1e-7)
        tally[NAMES[cls.State()]] += 1
    # and points forced ONTO the faces and their planes (grazing)
    graze = {"IN": 0, "OUT": 0, "ON": 0, "UNKNOWN": 0}
    for f in part.faces()[:60]:
        c = f.center()
        for k in (-1e-6, 0.0, 1e-6, 1e-4):
            nrm = f.normal_at(c)
            p = c + nrm * k
            cls.Perform(gp_Pnt(p.X, p.Y, p.Z), 1e-7)
            graze[NAMES[cls.State()]] += 1
    print(f"{label:28s} random {tally}   on-face {graze}", flush=True)

def main() -> int:
    from document import Document
    survey("box", b3d.Part() + b3d.Box(40, 40, 40))
    survey("box with a through hole", b3d.Part() + (b3d.Box(40, 40, 10) - b3d.Cylinder(8, 30)))
    survey("two lumps", b3d.Part() + b3d.Box(20, 20, 20) + b3d.Pos(60, 0, 0) * b3d.Box(20, 20, 20))
    survey("MIRRORED body", b3d.Part() + b3d.mirror(
        b3d.Part() + b3d.Box(30, 20, 10) + b3d.Pos(10, 0, 8) * b3d.Cylinder(4, 6), b3d.Plane.YZ))
    for name in ("my-part-5", "bit-tray", "my-part-3", "pump-impeller", "hole-box"):
        p = ROOT / "designs" / f"{name}.tcad.json"
        if not p.exists():
            continue
        doc = Document.from_data(json.loads(p.read_text("utf-8")))
        doc.rebuild()
        parts = [q for _f, q in doc._parts.items() if q is not None]
        if parts:
            survey(name, parts[-1], n=8000)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
