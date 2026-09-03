"""toolplan — the ONE geometry authority for the tools (LAUNCH-PLAN.md R1 / P1).

The browser used to carry its own copy of build123d's plane frames and a JS
re-implementation of sketch.face_sketch_plane(); the arrow, the ghost and the
solid disagreed on exactly half the faces of a box (user, 2026-09-01). These
tests pin the server's answer AND check it against what the kernel actually
builds, so the plan can never drift from the op.
"""
import json
import math

import pytest

import sketch as sk
import toolplan
from document import Document

PLATE = ("b", "plate", {"width": 60, "depth": 40, "thickness": 20}, [])


def build(*feats):
    d = Document(name="t")
    for fid, op, params, inputs in feats:
        d.add(fid, op, params, inputs)
    d.rebuild()
    return d


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def ok(plan):
    assert plan["ok"], plan
    json.dumps(plan)                       # must survive the API boundary
    return plan


# --------------------------------------------------------- plane sketches ---

@pytest.mark.parametrize("plane, axis, origin", [
    ("XY", [0, 0, 1], [0, 0, 7]),
    ("XZ", [0, -1, 0], [0, -7, 0]),        # probed: XZ offset +7 lands at y = -7
    ("YZ", [1, 0, 0], [7, 0, 0]),
])
def test_a_plane_sketch_extrudes_along_its_plane(plane, axis, origin):
    d = build(("s", "sketch", {"plane": plane, "offset": 7,
                               "entities": [{"kind": "circle", "r": 5}]}, []))
    p = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"}))
    assert p["mode"] == "sketch" and p["op"] == "extrude" and p["input"] == "s"
    assert p["axis"] == pytest.approx(axis, abs=1e-4)
    assert p["frame"]["z_dir"] == pytest.approx(axis, abs=1e-4)
    assert p["origin"] == pytest.approx(origin, abs=1e-3)
    assert p["into_sign"] is None
    assert len(p["loops"]) == 1 and not p["loops"][0]["holes"]
    assert p["limits"]["outer_radius"] == pytest.approx(5, abs=0.05)
    assert p["limits"]["has_holes"] is False
    # the taper constants are the server's; the meeting depth costs 18 kernel
    # offsets per face, so a plain plan does NOT measure it ...
    assert p["limits"]["max_taper"] == 89 and p["limits"]["apex_fraction"] == pytest.approx(0.999)
    assert p["limits"]["collapse"] is None
    # ... and a plan that asks for it gets the exact per-face value
    m = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s", "measure_collapse": True}))
    assert m["limits"]["collapse"] == pytest.approx([5], abs=0.01)
    # and the KERNEL agrees: +3 along the plan's axis
    solid = sk.extrude_sketch(d._parts["s"], 3)
    bb = solid.bounding_box()
    lo, hi = [getattr(bb.min, c) for c in "XYZ"], [getattr(bb.max, c) for c in "XYZ"]
    k = axis.index(max(axis, key=abs))
    far = hi[k] if axis[k] > 0 else lo[k]
    assert far == pytest.approx(origin[k] + 3 * axis[k], abs=1e-3)


def test_a_sketch_with_a_hole_reports_the_hole_and_the_thin_wall():
    d = build(("s", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 20, "h": 10},
        {"kind": "circle", "r": 2, "mode": "subtract"}]}, []))
    p = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"}))
    assert len(p["loops"]) == 1 and len(p["loops"][0]["holes"]) == 1
    assert p["limits"]["has_holes"] is True
    # half the thinnest wall: the hole's edge (y=±2) to the outer edge (y=±5)
    m = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s", "measure_collapse": True}))
    assert m["limits"]["collapse"] == pytest.approx([1.5], abs=0.01)
    assert p["origin"] == pytest.approx([0, 0, 0], abs=1e-3)


# ------------------------------------------------------------ face sketches ---

@pytest.mark.parametrize("face, axis, into", [
    ("top",    [0, 0, 1], -1),
    ("bottom", [0, 0, 1], +1),             # canonical frame points INTO the body
    ("+x",     [1, 0, 0], -1),
    ("-x",     [1, 0, 0], +1),
    ("+y",     [0, -1, 0], +1),
    ("-y",     [0, -1, 0], -1),
])
def test_a_face_sketch_extrudes_along_the_canonical_axis_and_knows_which_way_is_in(
        face, axis, into):
    d = build(PLATE, ("s", "sketch_on_face", {"face": face, "offset": 0,
                                              "entities": [{"kind": "circle", "r": 3}]}, ["b"]))
    p = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"}))
    assert p["axis"] == pytest.approx(axis, abs=1e-4)
    assert p["into_sign"] == into
    assert p["frame"]["z_dir"] == pytest.approx(axis, abs=1e-4)
    assert p["target_body"] == "b"
    # the plan's into_sign is TRUE: a +3 extrude that way lands inside the plate
    prism = sk.extrude_sketch(d._parts["s"], 3 * into)
    bb = prism.bounding_box()
    assert -30.01 <= bb.min.X and bb.max.X <= 30.01
    assert -20.01 <= bb.min.Y and bb.max.Y <= 20.01
    assert -10.01 <= bb.min.Z and bb.max.Z <= 10.01, (face, bb)


def test_a_face_sketch_offset_moves_the_arrow_along_the_canonical_axis():
    # bottom face at z=-10; the canonical frame is +Z, so offset +3 is z=-7
    d = build(PLATE, ("s", "sketch_on_face", {"face": "bottom", "offset": 3,
                                              "entities": [{"kind": "circle", "r": 3, "x": 5, "y": 2}]}, ["b"]))
    p = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"}))
    assert p["frame"]["origin"][2] == pytest.approx(-7, abs=1e-3)
    assert p["origin"] == pytest.approx([5, 2, -7], abs=1e-2)


def test_a_face_sketch_named_by_a_real_pick_plans_the_same_as_a_named_face():
    named = build(PLATE, ("s", "sketch_on_face", {"face": "top",
                                                  "entities": [{"kind": "circle", "r": 3}]}, ["b"]))
    picked = build(PLATE, ("s", "sketch_on_face", {"face_center": [0, 0, 10], "face_normal": [0, 0, 1],
                                                   "entities": [{"kind": "circle", "r": 3}]}, ["b"]))
    a = ok(toolplan.plan(named, {"tool": "extrude", "sketch_id": "s"}))
    b = ok(toolplan.plan(picked, {"tool": "extrude", "sketch_id": "s"}))
    for k in ("axis", "origin", "into_sign", "target_body"):
        assert a[k] == b[k], k


# --------------------------------------------------------------- face picks ---

def test_a_picked_bottom_face_builds_along_the_outward_normal_in_its_own_frame():
    d = build(PLATE)
    p = ok(toolplan.plan(d, {"tool": "extrude", "body_id": "b",
                             "face_center": [0, 0, -10], "face_normal": [0, 0, -1]}))
    assert p["mode"] == "face" and p["op"] == "extrude_face" and p["input"] == "b"
    assert p["axis"] == pytest.approx([0, 0, -1], abs=1e-4)
    # the ghost frame is the face's OWN plane: its z IS the build axis
    assert p["frame"]["z_dir"] == pytest.approx([0, 0, -1], abs=1e-4)
    assert p["frame"]["origin"] == pytest.approx([0, 0, -10], abs=1e-3)
    assert p["into_sign"] == -1
    assert p["origin"] == pytest.approx([0, 0, -10], abs=1e-3)
    assert p["target_body"] == "b"
    outer = p["loops"][0]["outer"]
    xs, ys = [q[0] for q in outer], [q[1] for q in outer]
    assert max(xs) - min(xs) == pytest.approx(60, abs=1e-3)
    assert max(ys) - min(ys) == pytest.approx(40, abs=1e-3)
    assert p["limits"]["outer_radius"] == pytest.approx(math.hypot(30, 20), abs=0.05)
    m = ok(toolplan.plan(d, {"tool": "extrude", "body_id": "b", "face_center": [0, 0, -10],
                             "face_normal": [0, 0, -1], "measure_collapse": True}))
    assert m["limits"]["collapse"] == pytest.approx([20], abs=0.01)   # half the short side
    # the KERNEL agrees: +5 from the bottom face goes DOWN
    solid = sk.extrude_face(d._parts["b"], [0, 0, -10], [0, 0, -1], amount=5)
    assert solid.bounding_box().min.Z == pytest.approx(-15, abs=1e-3)


def test_a_picked_top_face_runs_with_its_frame():
    d = build(PLATE)
    p = ok(toolplan.plan(d, {"tool": "extrude", "body_id": "b",
                             "face_center": [0, 0, 10], "face_normal": [0, 0, 1]}))
    assert p["axis"] == pytest.approx([0, 0, 1], abs=1e-4)
    assert p["frame"]["z_dir"] == pytest.approx([0, 0, 1], abs=1e-4)


def test_a_tilted_flat_face_keeps_its_own_normal():
    """A tapered wall is flat but principal-plane-free: the axis is ITS normal
    and the frame is built from it — no canonical snap for oblique faces."""
    d = build(("s", "sketch", {"plane": "XY", "entities": [{"kind": "rectangle", "w": 40, "h": 40}]}, []),
              ("e", "extrude", {"amount": 20, "taper": -20}, ["s"]))   # Fusion sign: negative narrows
    part = d._parts["e"]
    wall = max((f for f in part.faces() if sk.face_plane(f) is not None
                and abs(sk.face_plane(f).z_dir.Z) < 0.9),
               key=lambda f: f.center().X)
    n = sk.face_plane(wall).z_dir
    p = ok(toolplan.plan(d, {"tool": "extrude", "body_id": "e",
                             "face_center": list(wall.center()), "face_normal": [n.X, n.Y, n.Z]}))
    assert dot(p["axis"], [n.X, n.Y, n.Z]) > 0.999
    assert p["axis"][0] > 0.3 and p["axis"][2] > 0.3, p["axis"]     # genuinely tilted
    assert dot(p["frame"]["z_dir"], p["axis"]) > 0.999
    assert abs(dot(p["frame"]["x_dir"], p["axis"])) < 1e-3          # a real frame


# ------------------------------------------------------------ target body ---

def test_the_default_target_is_the_body_the_sketch_lives_on_walked_to_now():
    d = build(PLATE,
              ("s1", "sketch_on_face", {"face": "top", "entities": [{"kind": "circle", "r": 4}]}, ["b"]),
              ("e1", "extrude", {"amount": -5}, ["s1"]),
              ("c1", "cut", {}, ["b", "e1"]),
              ("b2", "plate", {"width": 10, "depth": 10, "thickness": 5}, []),
              ("s2", "sketch_on_face", {"face": "bottom", "entities": [{"kind": "circle", "r": 3}]}, ["b"]),
              ("s3", "sketch", {"plane": "XY", "offset": 30, "entities": [{"kind": "circle", "r": 3}]}, []))
    # a face sketch on b targets what b has BECOME (the cut), not the newest body
    assert ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s2"}))["target_body"] == "c1"
    # a plane sketch targets the newest solid
    assert ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s3"}))["target_body"] == "b2"


def test_a_lone_sketch_has_no_target_and_still_plans():
    d = build(("s", "sketch", {"plane": "XY", "entities": [{"kind": "circle", "r": 5}]}, []))
    p = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"}))
    assert p["target_body"] is None


# ---------------------------------------------------------------- edit mode ---

def test_an_existing_extrude_derives_its_input_from_the_feature():
    d = build(PLATE,
              ("s", "sketch_on_face", {"face": "top", "entities": [{"kind": "circle", "r": 4}]}, ["b"]),
              ("e", "extrude", {"amount": 5}, ["s"]),
              ("ef", "extrude_face", {"face_center": [0, 0, -10], "face_normal": [0, 0, -1],
                                      "amount": 5}, ["b"]))
    by_feature = ok(toolplan.plan(d, {"tool": "extrude", "feature_id": "e"}))
    by_sketch = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"}))
    assert by_feature == by_sketch
    face = ok(toolplan.plan(d, {"tool": "extrude", "feature_id": "ef"}))
    assert face["mode"] == "face" and face["axis"] == pytest.approx([0, 0, -1], abs=1e-4)


# ---------------------------------------------------------- failures speak ---

def test_failures_are_sentences_never_exceptions():
    empty = Document(name="t")
    empty.rebuild()
    r = toolplan.plan(empty, {"tool": "sweep", "sketch_id": "s"})   # no planner yet
    assert r["ok"] is False and "sweep" in r["error"] and "revolve" in r["error"]
    r = toolplan.plan(empty, {"tool": "extrude", "sketch_id": "nope"})
    assert r["ok"] is False and "nope" in r["error"]
    r = toolplan.plan(empty, {"tool": "extrude", "face_center": [0, 0, 0]})
    assert r["ok"] is False and "no solid" in r["error"]
    r = toolplan.plan(empty, {"tool": "extrude"})
    assert r["ok"] is False and "sketch" in r["error"]
    # a CURVED face: a ball's only face
    d = build(("d", "ball", {"radius": 10}, []))
    r = toolplan.plan(d, {"tool": "extrude", "body_id": "d",
                          "face_center": [0, 0, 0], "face_normal": [1, 0, 0]})
    assert r["ok"] is False and "curved" in r["error"], r
    # a sketch that never built (negative size is refused by sketch.py)
    d = build(("s", "sketch", {"plane": "XY", "entities": [{"kind": "circle", "r": -5}]}, []))
    r = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"})
    assert r["ok"] is False and "not been built" in r["error"], r
    # a feature that is not an extrude
    d = build(PLATE)
    r = toolplan.plan(d, {"tool": "extrude", "feature_id": "b"})
    assert r["ok"] is False and "not an extrude" in r["error"]
    for res in (r,):
        json.dumps(res)


def test_the_http_route_is_read_only():
    from fastapi.testclient import TestClient
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(Document(name="untitled"))
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    c.post("/api/feature/add", json={"id": "b", "op": "plate",
                                     "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    before = c.get("/api/doc").json()
    r = c.post("/api/tool/plan", json={"tool": "extrude", "body_id": "b",
                                       "face_center": [0, 0, -10], "face_normal": [0, 0, -1]}).json()
    assert r["ok"] and r["axis"] == pytest.approx([0, 0, -1], abs=1e-4)
    after = c.get("/api/doc").json()
    assert [f["id"] for f in after["features"]] == [f["id"] for f in before["features"]]
    assert after["rebuild_ms"] == before["rebuild_ms"], "a plan must never rebuild"
    bad = c.post("/api/tool/plan", json={"tool": "extrude", "sketch_id": "zz"}).json()
    assert bad["ok"] is False and "zz" in bad["error"]


# ------------------------------------------------------------ sketch plans ---

def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


@pytest.mark.parametrize("plane, offset, z_dir, origin", [
    ("XY", 0, [0, 0, 1], [0, 0, 0]),
    ("XY", 7, [0, 0, 1], [0, 0, 7]),
    ("XZ", 7, [0, -1, 0], [0, -7, 0]),      # probed: XZ's normal points -Y
    ("YZ", -3, [1, 0, 0], [-3, 0, 0]),
])
def test_a_sketch_plan_is_the_frame_the_kernel_builds_on(plane, offset, z_dir, origin):
    """The browser draws a NEW plane sketch's grid on this frame (R1, P2: it
    carried its own copy of the three frames until then). It must be the very
    plane make_sketch() builds on — the kernel-built face is the proof — and
    the same frame Extrude later pulls along (one home, two readers)."""
    d = build(("s", "sketch", {"plane": plane, "offset": offset,
                               "entities": [{"kind": "circle", "r": 5}]}, []))
    p = ok(toolplan.plan(d, {"tool": "sketch", "plane": plane, "offset": offset}))
    fr = p["frame"]
    assert fr["z_dir"] == pytest.approx(z_dir, abs=1e-6)
    assert fr["origin"] == pytest.approx(origin, abs=1e-6)
    assert dot(cross(fr["x_dir"], fr["y_dir"]), fr["z_dir"]) == pytest.approx(1, abs=1e-9)
    face = d._parts["s"].faces()[0]                           # what the kernel built
    assert list(face.center()) == pytest.approx(origin, abs=1e-6)
    assert list(face.normal_at()) == pytest.approx(z_dir, abs=1e-6)
    e = ok(toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"}))
    for k in ("origin", "x_dir", "y_dir", "z_dir"):
        assert e["frame"][k] == pytest.approx(fr[k], abs=1e-6), k


def test_a_sketch_plan_needs_no_features_and_refuses_an_unknown_plane():
    d = build()
    p = ok(toolplan.plan(d, {"tool": "sketch"}))
    assert p["plane"] == "XY" and p["offset"] == 0 and "XY" in p["will_build"]
    for name in ("AB", "xy"):                  # exactly what the kernel refuses
        bad = toolplan.plan(d, {"tool": "sketch", "plane": name})
        assert bad["ok"] is False and "XY" in bad["error"], bad
