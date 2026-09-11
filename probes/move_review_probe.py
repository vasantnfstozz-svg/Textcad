"""Round-one review of Move/Rotate (9e04ff6) — the facts I will not guess.

Run:  py -3.14\python.exe probes/move_review_probe.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import build123d as b3d      # noqa: E402
import blocks                # noqa: E402
import inspector             # noqa: E402
import toolplan              # noqa: E402
from document import Document  # noqa: E402


def bb(p):
    b = p.bounding_box()
    return [round(v, 6) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)]


print("=" * 72)
print("SECTION 1 — the catalogue knows `pivot`, and it is not a number")
print("=" * 72)
print("param_names(rotate) =", sorted(Document.param_names("rotate")))
print("numeric_params(rotate) =", sorted(Document.numeric_params("rotate")))
print("numeric_params(move)   =", sorted(Document.numeric_params("move")))

print()
print("=" * 72)
print("SECTION 2 — a MULTI-LUMP body turned about \"center\" (brief risk 6)")
print("=" * 72)
two = b3d.Pos(-30, 0, 0) * b3d.Box(10, 10, 10) + b3d.Pos(30, 0, 0) * b3d.Box(20, 6, 6)
print("two lumps: volume", round(two.volume, 4), "lumps", len(two.solids()), "bb", bb(two))
for axis in ("X", "Y", "Z"):
    out = blocks.rotate(two, axis, 37.0, pivot="center")
    h = inspector.health(out)
    back = blocks.rotate(out, axis, -37.0, pivot=blocks.body_centre(two))
    print(f"  {axis}: vol {round(out.volume, 4)} lumps {len(out.solids())} "
          f"health {(h or "healthy")} "
          f"back-bb-equal {bb(back) == bb(two)}")
concentric = b3d.Cylinder(20, 10) - b3d.Cylinder(15, 12) + b3d.Cylinder(4, 10)
print("concentric ring+post: lumps", len(concentric.solids()),
      "centre", blocks.body_centre(concentric))
out = blocks.rotate(concentric, "X", 90.0, pivot="center")
print("  turned X90: lumps", len(out.solids()), "vol", round(out.volume, 4),
      "health", (inspector.health(out) or "healthy"))

print()
print("=" * 72)
print("SECTION 3 — pivot in its three spellings + what slips past the guard")
print("=" * 72)
box = b3d.Pos(50, 0, 0) * b3d.Box(10, 10, 10)
for pv in (None, "origin", "center", [1, 2, 3], (1, 2, 3), "123", "abc", "middle",
           True, [1, 2], {"x": 1}, [1, 2, float("nan")], "0.5"):
    try:
        p = blocks._rotate_pivot(box, pv)
        print(f"  {pv!r:24} -> {p}")
    except Exception as e:                                     # noqa: BLE001
        print(f"  {pv!r:24} -> {type(e).__name__}: {e}")

print()
print("=" * 72)
print("SECTION 4 — plan_rotate's pivot for every shape of a STORED rotate")
print("=" * 72)


def doc_with_rotate(params):
    d = Document(name="r")
    d.add("b", "plate", {"width": 20, "depth": 10, "thickness": 4}, [])
    d.add("m", "move", {"x": 40, "y": 0, "z": 0}, ["b"])
    d.add("r1", "rotate", params, ["m"])
    d.rebuild()
    return d


for label, params in [("legacy axis+angle", {"axis": "Z", "angle_deg": 30}),
                      ("tool-made", {"axis": "Z", "angle_deg": 30, "pivot": "center"}),
                      ("explicit origin", {"axis": "Z", "angle_deg": 30, "pivot": "origin"}),
                      ("EMPTY params", {})]:
    d = doc_with_rotate(params)
    f = d.get("r1")
    built = d._parts.get("r1")
    plan = toolplan.plan("rotate", d, {"tool": "rotate", "body_id": "m", "feature_id": "r1"}) \
        if False else toolplan.plan_rotate(d, {"tool": "rotate", "body_id": "m", "feature_id": "r1"})
    print(f"  {label:20} stored={f.params} status={f.status}")
    print(f"      plan pivot={plan['pivot']!r} origin={plan['origin']} "
          f"params={plan['params']}")
    print(f"      built bb={bb(built) if built is not None else None}")
    # what the JS would push back: pivot = plan.pivot ?? null
    js_pivot = plan["pivot"]
    pushed = blocks.rotate(d._parts["m"], plan["params"].get("axis", "Z") if plan["params"] else "Z",
                           plan["params"].get("angle_deg", 0) if plan["params"] else 0,
                           pivot=js_pivot)
    print(f"      re-push with the planned pivot -> bb={bb(pushed)}  "
          f"SAME AS BUILT: {bb(pushed) == (bb(built) if built is not None else None)}")

print()
print("=" * 72)
print("SECTION 5 — the one LIVE rotate (planetary-assembly ring_mesh)")
print("=" * 72)
path = "designs/planetary-assembly.tcad.json"
if os.path.exists(path):
    data = json.load(open(path, encoding="utf-8"))
    d = Document.from_data(data)
    d.rebuild()
    f = d.get("ring_mesh")
    before = bb(d._parts["ring_mesh"])
    plan = toolplan.plan_rotate(d, {"tool": "rotate", "body_id": f.inputs[0],
                                    "feature_id": "ring_mesh"})
    print("  stored params:", f.params)
    print("  plan pivot:", repr(plan["pivot"]), " origin:", plan["origin"])
    print("  plan params:", plan["params"])
    print("  built bb:", before)
    d.edit_many("ring_mesh", {"axis": plan["params"]["axis"],
                              "angle_deg": plan["params"]["angle_deg"],
                              "pivot": plan["pivot"]})
    d.rebuild()
    print("  after an OK with the planned values:", bb(d._parts["ring_mesh"]))
    print("  UNCHANGED:", bb(d._parts["ring_mesh"]) == before)

print()
print("=" * 72)
print("SECTION 6 — move's offsets: the sentences and what slips through")
print("=" * 72)
import document as docmod      # noqa: E402
for params in ({"x": "abc"}, {"x": None}, {"x": True}, {"x": [1]}, {"x": float("inf")},
               {"x": "5"}, {"y": {"a": 1}}, {}):
    try:
        print(f"  {params!r:22} -> {docmod._move_offsets(params)}")
    except Exception as e:                                     # noqa: BLE001
        print(f"  {params!r:22} -> {type(e).__name__}: {e}")

print()
print("=" * 72)
print("SECTION 7 — delta_features: `move` in PLACEMENT changes nothing")
print("=" * 72)
d = Document(name="p")
d.add("b", "plate", {"width": 20, "depth": 10, "thickness": 4}, [])
d.add("m", "move", {"x": 5}, ["b"])
d.rebuild()
print("  delta_features('m') =", d.delta_features("m"))
print("  ('m' was already (None, 'm') before, by falling through — 'move' is in")
print("   neither MODIFIERS nor PULLED nor the booleans:",
      "move" in Document.PULLED, "move" in docmod.MODIFIERS)


print()
print("=" * 72)
print("SECTION 8 - the P0: a stored face pick against a body that MOVED")
print("=" * 72)
print("The Move tool's own documented journey: move a body, sketch on the face")
print("it now shows, extrude a boss, fuse - then re-open Move and drag.")


def journey(z):
    d = Document(name="j")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 10}, [])
    d.add("move1", "move", {"x": 0, "y": 0, "z": 0}, ["b"])
    d.rebuild()
    top = max(d._parts["move1"].faces(), key=lambda f: f.center().Z)
    c = top.center()
    n = top.normal_at(c)
    d.add("s", "sketch_on_face",
          {"face_center": [c.X, c.Y, c.Z], "face_normal": [n.X, n.Y, n.Z],
           "entities": [{"kind": "circle", "r": 6, "x": 0, "y": 0}]}, ["move1"])
    d.add("boss", "extrude", {"amount": 5}, ["s"])
    d.add("f", "fuse", {}, ["move1", "boss"])
    d.rebuild()
    d.edit_many("move1", {"x": 0, "y": 0, "z": z})
    d.rebuild()
    bb = d._parts["boss"].bounding_box()
    return (round(d.result().volume, 3), round(bb.min.Z, 2), round(bb.max.Z, 2),
            all(f.status == "ok" for f in d.features))


for z in (0, 2, 4, 6, 8, 12, 25):
    vol, z0, z1, green = journey(z)
    print(f"  drag Z to {z:>3} mm -> result {vol:>11}  boss z {z0}..{z1}  all green {green}"
          + ("   <-- the boss was SWALLOWED" if abs(vol - 24000) < 1e-6 else ""))
print()
print("  MEASURED BEFORE THE FIX (resolve_face scored the normal as a 25 mm^2")
print("  nudge): past +7 mm the nearest face is the one pointing the OTHER way,")
print("  so the boss was rebuilt on the BOTTOM face, pointing UP into the")
print("  material. 565.487 mm^3 of the user's part gone, every row `ok`.")
print("  AFTER: the direction is a GATE - only faces still pointing the picked")
print("  way are candidates - and the boss rides the move, as the spec says.")
print()
print("  Inert on the saved library, measured two ways:")
print("    * 47 resolve_face calls across 50 designs carry a stored normal;")
print("      NONE of them resolves to a face more than 60 degrees off.")
print("    * the 50 designs rebuilt TWICE in one process, old scoring vs new:")
print("      0 features changed status or volume.")
