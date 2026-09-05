"""Revolve P3b (specs/revolve.md, second part): a picked FACE as the profile,
the profile's own straight edges as the axis, Two sides / Symmetric extents.

Every geometric claim is checked against the kernel — volumes against Pappus
(V = 2*pi*r_centroid*A*theta/360), where the solid sits against its centroid
and the profile plane — and every refusal is a sentence, never an exception.
probes/revolve_face_probe.py (2026-09-05) is where the kernel's answers came
from.
"""
import math

import build123d as b3d
import pytest

import inspector
import sketch as sk
import toolplan
from document import Document
from tests.gauntlet import BODIES, planar_faces


def pappus(r_bar, area, deg):
    return 2 * math.pi * abs(r_bar) * area * abs(deg) / 360.0


def rect(plane="XZ", x=20.0, y=20.0, w=20.0, h=40.0, offset=0.0):
    """A rectangle 10..30 by 0..40 on XZ by default — the P3 checklist profile."""
    return sk.make_sketch(plane=plane, offset=offset, entities=[
        {"kind": "rectangle", "w": w, "h": h, "x": x, "y": y, "mode": "add"}])


LEFT = [[10.0, 0.0], [10.0, 40.0]]        # the rectangle's left side, in sketch coords
XZ = sk.sketch_plane("XZ", 0)


def plate_doc(face="top"):
    """A 60 x 40 x 12 plate and its top / bottom face as a real pick would give
    it: (document, (face, centre, normal))."""
    d = Document(name="face")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.rebuild()
    part = d._parts["b"]
    picked = next((f, c, n) for i, f, c, n in planar_faces(part)
                  if abs(n[2]) > 0.9 and (n[2] > 0) == (face == "top"))
    return d, picked


def off_plane(solid, pl):
    """How far the solid's centroid sits off the profile plane, signed along n."""
    return (solid.center() - pl.origin).dot(pl.z_dir)


# ------------------------------------------------ an edge of the profile as axis ---

def test_the_profiles_own_edge_is_an_axis_and_the_volume_is_pappus():
    solid = sk.revolve_sketch(rect(), axis=LEFT, angle=360)
    assert inspector.health(solid) == []
    assert solid.volume == pytest.approx(pappus(10, 800, 360), rel=1e-6)   # centroid 10 mm off the side
    bb = solid.bounding_box()                     # a solid cylinder: radius 20, height 40
    assert bb.max.Z - bb.min.Z == pytest.approx(40, abs=1e-6)
    assert bb.max.X - bb.min.X == pytest.approx(40, abs=1e-6)


@pytest.mark.parametrize("offset", [0.0, 7.0])
def test_the_edge_axis_lies_in_the_sketch_plane_and_rides_an_offset(offset):
    """The line is stored in the plane's own coordinates, so moving the plane
    (a face or an offset change) carries the axis with it — the offset method
    applied to an axis, exactly as for u / v."""
    s = rect(offset=offset)
    pl = sk.sketch_plane("XZ", offset)
    ax = sk.revolve_axis(s, LEFT)
    assert abs((ax.position - pl.origin).dot(pl.z_dir)) < 1e-9      # the line is IN the plane
    assert abs(ax.direction.dot(pl.z_dir)) < 1e-9
    assert pl.to_local_coords(ax.position).X == pytest.approx(10, abs=1e-9)
    solid = sk.revolve_sketch(s, axis=LEFT, angle=90)
    assert solid.volume == pytest.approx(pappus(10, 800, 90), rel=1e-6)


def test_a_rectangle_across_the_origin_turns_about_its_own_side():
    """P3 refused this (it crosses u and v); Fusion turns it about a side."""
    s = rect(x=0, y=0, w=20, h=40)                        # -10..10 by -20..20
    with pytest.raises(ValueError, match="crosses the v axis"):
        sk.revolve_sketch(s, axis="v", angle=90)
    solid = sk.revolve_sketch(s, axis=[[10, -20], [10, 20]], angle=360)
    assert inspector.health(solid) == []
    assert solid.volume == pytest.approx(pappus(10, 800, 360), rel=1e-6)


def test_a_line_the_profile_crosses_is_refused_with_the_line_named():
    with pytest.raises(ValueError, match=r"crosses the axis line \(20, 0\)-\(20, 40\)"):
        sk.revolve_sketch(rect(), axis=[[20, 0], [20, 40]], angle=90)


def test_a_degenerate_or_malformed_line_is_a_sentence():
    with pytest.raises(ValueError, match="coincide"):
        sk.revolve_sketch(rect(), axis=[[10, 0], [10, 0]], angle=90)
    for bad in ([[10, 0]], [[10, 0], [10]], "W", 5, [[10, 0], [10, 40], [0, 0]]):
        with pytest.raises(ValueError, match='"u" or "v"'):
            sk.revolve_sketch(rect(), axis=bad, angle=90)


def test_edge_lines_are_the_outer_straight_edges_longest_first_and_canonical():
    lines = sk.revolve_edge_lines(rect())
    assert len(lines) == 4
    lengths = [math.dist(p, q) for p, q in lines]
    assert lengths == sorted(lengths, reverse=True) and lengths[0] == 40
    for p, q in lines:                            # the dominant component runs positive
        du, dv = q[0] - p[0], q[1] - p[1]
        assert (du if abs(du) >= abs(dv) else dv) > 0
    # a hole adds no candidate (material lies on both sides of its edges)
    holed = sk.make_sketch(plane="XZ", entities=[
        {"kind": "rectangle", "w": 20, "h": 40, "x": 20, "y": 20, "mode": "add"},
        {"kind": "rectangle", "w": 4, "h": 4, "x": 20, "y": 20, "mode": "subtract"}])
    assert len(sk.revolve_edge_lines(holed)) == 4


# ------------------------------------------------------ two sides / symmetric ---

def test_symmetric_sweeps_the_angle_to_each_side_and_is_centred_on_the_plane():
    one = sk.revolve_sketch(rect(), axis="v", angle=90)
    sym = sk.revolve_sketch(rect(), axis="v", angle=90, both=True)
    assert inspector.health(sym) == []
    assert sym.volume == pytest.approx(pappus(20, 800, 180), rel=1e-6)    # 90 EACH side
    assert abs(off_plane(sym, XZ)) < 1e-6
    assert abs(off_plane(one, XZ)) > 5                                     # one side is not


def test_two_sides_adds_the_second_angle_the_other_way():
    fwd = sk.revolve_sketch(rect(), axis="v", angle=90)
    two = sk.revolve_sketch(rect(), axis="v", angle=90, angle2=30)
    assert inspector.health(two) == []
    assert two.volume == pytest.approx(pappus(20, 800, 120), rel=1e-6)
    # the extra 30 lie on the far side of the plane: the centroid moves back
    # toward the plane but stays on side one (whichever side of the plane's
    # normal the kernel's positive sweep is — XZ's normal points to -y and the
    # sweep goes to +y, so the sign is read off the one-sided solid)
    d_fwd, d_two = off_plane(fwd, XZ), off_plane(two, XZ)
    assert abs(d_fwd) > 5 and d_two * d_fwd > 0 and abs(d_two) < abs(d_fwd)
    # a negative first side mirrors the whole thing
    neg = sk.revolve_sketch(rect(), axis="v", angle=-90, angle2=30)
    assert off_plane(neg, XZ) == pytest.approx(-d_two, abs=1e-6)
    # side one at 0: the second side is the only side, the other way
    only2 = sk.revolve_sketch(rect(), axis="v", angle=0, angle2=30)
    assert only2.volume == pytest.approx(pappus(20, 800, 30), rel=1e-6)
    assert off_plane(only2, XZ) * d_fwd < 0


def test_two_sides_and_symmetric_guards_are_sentences():
    with pytest.raises(ValueError, match="size, not a direction"):
        sk.revolve_sketch(rect(), axis="v", angle=90, angle2=-10)
    with pytest.raises(ValueError, match="add up to 400"):
        sk.revolve_sketch(rect(), axis="v", angle=300, angle2=100)
    with pytest.raises(ValueError, match="add up to 400"):
        sk.revolve_sketch(rect(), axis="v", angle=200, both=True)
    with pytest.raises(ValueError, match="angle is 0"):
        sk.revolve_sketch(rect(), axis="v", angle=0, angle2=0, both=True)
    with pytest.raises(ValueError):
        sk.revolve_sketch(rect(), axis="v", angle=90, both="maybe")


# ------------------------------------------------------- a picked face profile ---

@pytest.mark.parametrize("face", ["top", "bottom"])
def test_a_faces_own_plane_matches_the_sketch_plane_on_aligned_faces(face):
    d, (picked, c, n) = plate_doc(face)
    pp, sp = sk.face_profile_plane(picked), sk.face_sketch_plane(picked)
    for attr in ("origin", "x_dir", "z_dir"):
        assert list(getattr(pp, attr)) == pytest.approx(list(getattr(sp, attr)), abs=1e-9)


def test_a_tilted_face_keeps_its_true_plane():
    """face_sketch_plane snaps a wall tilted under 25 deg to the principal plane;
    a profile must lie in ITS plane (probe §7: edges 1.4 mm off the snapped one)."""
    solid = BODIES["fused_taper_seam"]()
    tilted = next(f for i, f, c, n in planar_faces(solid) if 0.05 < abs(n[2]) < 0.5)
    pl = sk.face_profile_plane(tilted)
    for v in tilted.vertices():
        assert abs((v.center() - pl.origin).dot(pl.z_dir)) < 1e-6      # every corner in the plane
    snapped = sk.face_sketch_plane(tilted)
    assert max(abs((v.center() - snapped.origin).dot(snapped.z_dir))
               for v in tilted.vertices()) > 0.5


@pytest.mark.parametrize("face", ["top", "bottom"])
def test_revolve_face_about_its_own_edge_matches_pappus(face):
    d, (picked, c, n) = plate_doc(face)
    prof = sk._on_plane(b3d.Sketch([picked]), sk.face_profile_plane(picked))
    lines = sk.revolve_edge_lines(prof)
    assert len(lines) == 4 and math.dist(*lines[0]) == pytest.approx(60)
    long_edge = [list(lines[0][0]), list(lines[0][1])]
    solid = sk.revolve_face(d._parts["b"], c, n, axis=long_edge, angle=90)
    assert inspector.health(solid) == []
    # the 60 x 40 face about its 60 mm side: centroid 20 mm off the axis, area 2400
    assert solid.volume == pytest.approx(pappus(20, 2400, 90), rel=1e-6)
    bb, body = solid.bounding_box(), d._parts["b"].bounding_box()
    level = body.max.Z if face == "top" else body.min.Z
    assert min(abs(bb.min.Z - level), abs(bb.max.Z - level)) < 1e-6    # it starts at the face


def test_revolve_face_refusals_are_sentences():
    d, (picked, c, n) = plate_doc("top")
    body = d._parts["b"]
    with pytest.raises(ValueError, match="needs an axis"):
        sk.revolve_face(body, c, n, angle=90)
    with pytest.raises(ValueError, match="crosses the u axis"):
        sk.revolve_face(body, c, n, axis="u", angle=90)      # the plane's axes cross a centred face


# ------------------------------------------------------------------ the planner ---

def sketch_doc(x=20.0, y=20.0, w=20.0, h=40.0, kind="rectangle", r=8.0):
    d = Document(name="rev")
    ent = ({"kind": "circle", "r": r, "x": x, "y": y} if kind == "circle"
           else {"kind": "rectangle", "w": w, "h": h, "x": x, "y": y})
    d.add("p", "sketch", {"plane": "XZ", "offset": 0, "entities": [ent]}, [])
    d.rebuild()
    return d


def plan(d, **req):
    return toolplan.plan(d, {"tool": "revolve", **req})


def test_the_axis_list_is_u_v_then_the_working_edges_with_labels_and_params():
    p = plan(sketch_doc(), sketch_id="p")
    assert p["ok"] and p["axis_name"] == "v" and p["axis_param"] == "v"
    names = [a["name"] for a in p["axes"]]
    assert names == ["v", "u", "e1", "e2", "e3", "e4"]
    assert all(a["ok"] for a in p["axes"])
    e1 = p["axes"][2]
    assert e1["param"] in ([[10.0, 0.0], [10.0, 40.0]], [[30.0, 0.0], [30.0, 40.0]])
    assert "40 mm" in e1["label"] and "along v" in e1["label"]
    for a in p["axes"][2:]:                       # every alternative carries its own handles
        alt = p["alternatives"][a["name"]]
        assert alt["limits"]["max_angle"] == 360 and len(alt["loops"]) == 1
    assert [a["name"] for a in p["axes"] if a["ok"]] == names
    assert [a["kind"] for a in p["axes"]] == ["local", "local", "edge", "edge", "edge", "edge"]


def test_a_rectangle_over_the_origin_opens_on_its_longest_side_and_says_why_not_u_v():
    d = sketch_doc(x=0, y=0)
    p = plan(d, sketch_id="p")
    assert p["ok"] and p["axis_name"] == "e1"
    byname = {a["name"]: a for a in p["axes"]}
    assert not byname["u"]["ok"] and "crosses u" in byname["u"]["why"]
    assert not byname["v"]["ok"] and "crosses v" in byname["v"]["why"]
    assert [a["name"] for a in p["axes"] if a["ok"]] == ["e1", "e2", "e3", "e4"]
    solid = sk.revolve_sketch(d._parts["p"], axis=p["axis_param"], angle=360)
    assert solid.volume == pytest.approx(pappus(10, 800, 360), rel=1e-6)


def test_a_centred_circle_is_refused_with_both_reasons_and_the_missing_edge():
    p = plan(sketch_doc(x=0, y=0, kind="circle"), sketch_id="p")
    assert p["ok"] is False
    assert "crosses v" in p["error"] and "crosses u" in p["error"]
    assert "no straight edge" in p["error"] and "one side" in p["error"]


def test_a_stored_edge_line_is_recognised_as_that_edge_on_edit():
    d = sketch_doc()
    d.add("r", "revolve", {"axis": LEFT, "angle": 90}, ["p"])
    d.rebuild()
    assert d.get("r").status == "ok"
    p = plan(d, feature_id="r")
    assert p["ok"] and p["axis_name"].startswith("e") and p["fallback"] is None
    assert p["axis_param"] == LEFT
    assert not any(a["name"] == "stored" for a in p["axes"])


def test_a_stored_line_no_longer_on_an_edge_is_offered_as_the_stored_line():
    """The profile was resized after the axis was picked: the line stays where
    the edge was (a construction line), listed under its own name while it
    works — never silently the nearest edge."""
    d = sketch_doc()
    d.add("r", "revolve", {"axis": [[8.0, 0.0], [8.0, 40.0]], "angle": 90}, ["p"])
    d.rebuild()
    assert d.get("r").status == "ok"              # 2 mm clear of the profile: a bore
    p = plan(d, feature_id="r")
    assert p["ok"] and p["axis_name"] == "stored" and p["fallback"] is None
    assert p["axis_param"] == [[8.0, 0.0], [8.0, 40.0]]
    assert "stored line" in next(a["label"] for a in p["axes"] if a["name"] == "stored")


def test_a_stored_line_the_profile_now_crosses_falls_back_with_the_reason():
    d = sketch_doc()
    d.add("r", "revolve", {"axis": [[20.0, 0.0], [20.0, 40.0]], "angle": 90}, ["p"])
    d.rebuild()
    assert d.get("r").status == "failed"
    p = plan(d, feature_id="r")
    assert p["ok"] and p["axis_name"] == "v"
    assert p["fallback"]["from"] == "the stored line" and "crosses" in p["fallback"]["why"]


@pytest.mark.parametrize("face", ["top", "bottom"])
def test_a_picked_face_plans_in_face_mode_on_its_longest_edge(face):
    d, (picked, c, n) = plate_doc(face)
    p = plan(d, body_id="b", face_center=c, face_normal=n)
    assert p["ok"] and p["mode"] == "face" and p["op"] == "revolve_face"
    assert p["input"] == "b" and p["target_body"] == "b"
    byname = {a["name"]: a for a in p["axes"]}
    assert not byname["u"]["ok"] and not byname["v"]["ok"]       # a centred face crosses both
    assert p["axis_name"] == "e1" and "60 mm" in byname["e1"]["label"]
    assert [a["name"] for a in p["axes"] if a["ok"]] == ["e1", "e2", "e3", "e4"]
    bb = d._parts["b"].bounding_box()                          # the ring is level with the face
    level = bb.max.Z if face == "top" else bb.min.Z
    assert p["origin"][2] == pytest.approx(level, abs=1e-6)
    assert min(q[0] for q in p["loops"][0]["outer"]) >= -1e-6   # outline on the material side
    solid = sk.revolve_face(d._parts["b"], c, n, axis=p["axis_param"], angle=90)
    assert solid.volume == pytest.approx(pappus(20, 2400, 90), rel=1e-6)


def test_a_revolve_face_feature_builds_edits_and_plans_from_its_feature():
    d, (picked, c, n) = plate_doc("top")
    p = plan(d, body_id="b", face_center=c, face_normal=n)
    d.add("rf", "revolve_face", {"face_center": c, "face_normal": n,
                                 "axis": p["axis_param"], "angle": 90}, ["b"])
    d.rebuild()
    f = d.get("rf")
    assert f.status == "ok" and f.volume == pytest.approx(pappus(20, 2400, 90), rel=1e-6)
    assert "b" not in d.consumed_ids(), "a face reference never consumes its body"
    q = plan(d, feature_id="rf")
    assert q["ok"] and q["mode"] == "face" and q["axis_name"] == p["axis_name"]
    assert q["fallback"] is None
    d.edit("rf", "angle", 180)
    d.rebuild()
    assert d.get("rf").volume == pytest.approx(pappus(20, 2400, 180), rel=1e-6)
    d.edit_many("rf", {"angle": 90, "both": True})
    d.rebuild()
    assert d.get("rf").volume == pytest.approx(pappus(20, 2400, 180), rel=1e-6)


def test_revolve_face_plan_refusals_are_sentences():
    p = plan(Document(name="empty"), body_id="b", face_center=[0, 0, 0])
    assert p["ok"] is False and "build a body first" in p["error"]
    d, (picked, c, n) = plate_doc("top")
    d.add("rf", "revolve_face", {"face_center": c, "face_normal": n, "angle": 90}, ["b"])
    d.rebuild()
    f = d.get("rf")
    assert f.status == "failed" and "needs an axis" in f.problems[0]


# ------------------------------------------------- the kernel's edge cases ---

HEX = [[30, 0], [15, 25.980762113533157], [-15, 25.980762113533157], [-30, 0],
       [-15, -25.980762113533157], [15, -25.980762113533157]]


def test_a_stored_line_snaps_to_the_exact_edge_so_no_sliver_face_is_swept():
    """The line is stored to 0.1 µm; an axis that far off its edge makes OCCT
    sweep the edge into a sliver face — valid, but junk, and it passed the old
    manifold check (probe §9). Snapped to the kernel's own vertices, the edge
    collapses onto the axis: 5 sweeps + 2 caps, nothing extra."""
    s = sk.make_sketch(plane="XY", entities=[{"kind": "polygon", "points": HEX}])
    for p, q in sk.revolve_edge_lines(s):                 # 4-decimal lines, as stored
        solid = sk.revolve_sketch(s, axis=[list(p), list(q)], angle=90)
        assert inspector.health(solid) == []
        assert len(solid.faces()) == 7
        assert min(f.area for f in solid.faces()) > 100
    # a construction line that matches no edge is used exactly as given
    ax = sk.revolve_axis(s, [[40, -10], [40, 10]])
    assert ax.position.X == pytest.approx(40) and abs(ax.direction.Y) == pytest.approx(1)


def test_a_kernel_error_inside_the_sweep_is_a_sentence(monkeypatch):
    class Boom(Exception):                # OCP errors derive from Exception, not RuntimeError
        pass

    def explode(*a, **k):
        raise Boom("NCollection_Sequence::Value")
    monkeypatch.setattr(sk, "_revolve", explode)
    with pytest.raises(ValueError, match="could not sweep"):
        sk.revolve_sketch(rect(), axis="v", angle=90)


def test_a_broken_sweep_is_refused_not_returned(monkeypatch):
    """A failed feature beats a corrupt body: whatever the kernel hands back is
    health-checked inside the op, and a problem is a sentence."""
    box = b3d.Solid.make_box(10, 10, 10)
    monkeypatch.setattr(sk, "_revolve", lambda *a, **k: b3d.Shell(box.faces()[:-1]))
    with pytest.raises(ValueError, match="came back broken"):
        sk.revolve_sketch(rect(), axis="v", angle=90)


# ------------------------------------------------- after the review (2026-09-05)

def test_a_dict_shaped_axis_is_a_sentence_not_a_key_error():
    """An AI near-miss on the documented [[u1, v1], [u2, v2]] form."""
    with pytest.raises(ValueError, match='"u" or "v"'):
        sk.revolve_sketch(rect(), axis=[{"u": 10, "v": 0}, {"u": 10, "v": 40}], angle=90)


def test_a_negative_second_side_is_refused_even_when_both_is_set():
    with pytest.raises(ValueError, match="size, not a direction"):
        sk.revolve_sketch(rect(), axis="v", angle=90, angle2=-30, both=True)


def test_a_stored_line_snaps_to_the_edge_it_lies_along_after_a_resize():
    """The profile grew along the axis edge after it was picked: the stored line
    no longer matches the edge's endpoints, but it lies along it — the axis must
    still be the kernel's own vertices (a rounded line 0.1 µm off sweeps a
    sliver face, probe §9): 3 sweeps + 2 caps, nothing extra."""
    grown = rect(h=60, y=30)                                    # 10..30 by 0..60
    ax = sk.revolve_axis(grown, LEFT)                           # LEFT is 0..40 tall
    corners = [v.center() for v in grown.faces()[0].vertices()]
    assert min((ax.position - c).length for c in corners) < 1e-9, "snapped to a real vertex"
    solid = sk.revolve_sketch(grown, axis=LEFT, angle=90)
    assert inspector.health(solid) == [] and len(solid.faces()) == 5
    assert solid.volume == pytest.approx(pappus(10, 1200, 90), rel=1e-6)
    # a line clear of every edge is a construction line, used as given
    ax2 = sk.revolve_axis(grown, [[8, 0], [8, 60]])
    assert XZ.to_local_coords(ax2.position).X == pytest.approx(8)


def test_a_face_on_a_body_away_from_the_origin_opens_on_its_edge_not_on_v():
    """u / v pass through the world origin's foot on the face plane — far from a
    body that is not centred on it, and 'valid' precisely because they miss the
    face. Face mode lists the edges first, so the default lies on the face."""
    d = Document(name="off")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("m", "move", {"x": 100, "y": 50}, ["b"])
    d.rebuild()
    part = d._parts["m"]
    _, face, c, n = next(x for x in planar_faces(part) if x[3][2] > 0.9)
    p = plan(d, body_id="m", face_center=c, face_normal=n)
    assert p["ok"] and p["mode"] == "face"
    assert [a["kind"] for a in p["axes"]][:4] == ["edge"] * 4
    assert p["axis_name"] == "e1"
    byname = {a["name"]: a for a in p["axes"]}
    assert byname["v"]["ok"] and byname["u"]["ok"], "they miss the face, so they 'work'"
    bb, o = part.bounding_box(), p["origin"]                    # the default axis lies ON the face
    assert bb.min.X - 1e-6 <= o[0] <= bb.max.X + 1e-6
    assert bb.min.Y - 1e-6 <= o[1] <= bb.max.Y + 1e-6


def test_the_panel_is_offered_at_most_twelve_edges_and_the_plan_stays_quick():
    """A traced outline has hundreds of straight segments: the plan was O(N²)
    in them (1.8 s for a 40-gon, 20 s for a 120-gon) and the dropdown useless."""
    import time
    pts = [[30 * math.cos(2 * math.pi * i / 40), 30 * math.sin(2 * math.pi * i / 40)]
           for i in range(40)]
    d = Document(name="40gon")
    d.add("p", "sketch", {"plane": "XZ", "entities": [{"kind": "polygon", "points": pts}]}, [])
    d.rebuild()
    t = time.perf_counter()
    p = plan(d, sketch_id="p")
    dt = time.perf_counter() - t
    assert p["ok"]
    assert sum(a["kind"] == "edge" for a in p["axes"]) == toolplan.MAX_EDGE_AXES
    assert dt < 3.0, f"plan took {dt:.1f} s"


def test_one_axis_the_kernel_chokes_on_is_dropped_not_the_tool_refused(monkeypatch):
    """OCP errors do not derive from RuntimeError: a candidate the kernel cannot
    measure costs that candidate, never the whole plan."""
    real = sk.revolve_extent

    def flaky(sketch, ax):
        # the LEFT side only: it starts at u = 10 like the two horizontal sides,
        # but it is the one running along v
        if (abs(XZ.to_local_coords(ax.position).X - 10) < 1e-6
                and abs(ax.direction.dot(XZ.x_dir)) < 1e-6):
            raise RuntimeError("Standard_OutOfRange")
        return real(sketch, ax)
    monkeypatch.setattr(sk, "revolve_extent", flaky)
    p = plan(sketch_doc(), sketch_id="p")
    assert p["ok"] and p["axis_name"] == "v"
    assert len([a for a in p["axes"] if a["kind"] == "edge"]) == 3
