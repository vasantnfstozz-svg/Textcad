"""Fillet / Chamfer on PICKED edges (LAUNCH-PLAN.md P4, specs/fillet-chamfer.md):
the op guards that make dragging a radius safe, and the planner that hands the
UI its gold edges and the ball handle.

probes/fillet_edges_probe.py (2026-09-04) found in the kernel:

    radius >= the neighbouring face   -> build123d ValueError (friendly, but
                                         names no number to type instead)
    a round bigger than the corner    -> a "successful" INVALID solid — the
    round beside it                      second banned failure, live
    nearest-midpoint identity         -> silently moves to a NEW edge after a
                                         chamfer ate the picked one
    the edge shared by two faces      -> detects the gone edge

Every geometric claim below is checked against the kernel.
"""
import pytest
from build123d import Axis

import blocks
import inspector
import provenance
import toolplan
from document import Document


def box(w=40.0, d=30.0, t=20.0):
    return blocks.plate(w, d, t)


def top(part):
    return list(part.edges().group_by(Axis.Z)[-1])


def mid(edge):
    return [round(v, 4) for v in tuple(edge @ 0.5)]


def healthy(part):
    assert not inspector.health(part), inspector.health(part)
    return part


OPS = {"fillet": blocks.fillet_edges, "chamfer": blocks.chamfer_edges}


# ------------------------------------------------------ the op's guards ------

@pytest.mark.parametrize("op", ["fillet", "chamfer"])
@pytest.mark.parametrize("value", [50, 20])
def test_too_big_refuses_and_says_why(op, value):
    """The op refuses cheaply and truthfully. It does NOT search for the largest
    value that fits: that costs ~8 more kernel builds and a stored-but-failing
    feature would pay it on every rebuild (review 2026-09-04)."""
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    with pytest.raises(ValueError) as ei:
        OPS[op](b, value, [ref])
    msg = str(ei.value)
    assert msg.startswith(op + ":") and "does not fit" in msg
    assert f"{value:g} mm" in msg and "1 edge" in msg
    assert "the kernel could not build it there" in msg
    for leak in ("TopoDS", "NCollection", "Standard_", "BRep", "StdFail"):
        assert leak not in msg


@pytest.mark.parametrize("op", ["fillet", "chamfer"])
def test_the_kernel_is_called_once_with_the_value_the_user_typed(op):
    """No speculative probing. Searching for "the largest that would fit" means
    building at radii nobody asked for, and on esp32-remote one of those
    segfaulted OCCT (2026-09-04) — it would take the user's server with it."""
    calls = []
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    real = blocks._b3d_fillet if op == "fillet" else blocks._b3d_chamfer
    name = "_b3d_fillet" if op == "fillet" else "_b3d_chamfer"

    def spy(es, **kw):
        calls.append(next(iter(kw.values())))
        return real(es, **kw)

    mp = pytest.MonkeyPatch()
    mp.setattr(blocks, name, spy)
    try:
        with pytest.raises(ValueError):
            OPS[op](b, 50, [ref])
        assert calls == [50], calls
        calls.clear()
        OPS[op](b, 3, [ref])
        assert calls == [3], calls
    finally:
        mp.undo()
    assert not hasattr(blocks, "largest_that_builds")


@pytest.mark.parametrize("op", ["fillet", "chamfer"])
@pytest.mark.parametrize("value", [0, -1, None])
def test_non_positive_value_is_refused(op, value):
    b = box()
    with pytest.raises(ValueError, match=f"{op}: .*must be positive"):
        OPS[op](b, value, [blocks.edge_ref(b, top(b)[0])])


def test_the_three_picked_forms_mean_the_same_edge():
    b = box()
    e = top(b)[0]
    ref = blocks.edge_ref(b, e)
    v_ref = healthy(blocks.fillet_edges(b, 3, [ref])).volume
    v_mid = blocks.fillet_edges(b, 3, [{"mid": mid(e)}]).volume
    v_bare = blocks.fillet_edges(b, 3, [tuple(mid(e))]).volume     # document._clean makes tuples
    assert v_ref == pytest.approx(v_mid) == pytest.approx(v_bare)
    assert v_ref < b.volume


@pytest.mark.parametrize("group", ["all", "top", "bottom", "vertical", "horizontal"])
def test_group_names_still_work(group):
    b = box()
    assert healthy(blocks.fillet_edges(b, 2, group)).volume < b.volume
    assert healthy(blocks.chamfer_edges(b, 2, group)).volume < b.volume


def test_unknown_group_and_empty_list_speak():
    b = box()
    with pytest.raises(ValueError, match="picked edges"):
        blocks.fillet_edges(b, 1, "sideways")
    with pytest.raises(ValueError, match="no edges picked"):
        blocks.fillet_edges(b, 1, [])
    with pytest.raises(ValueError, match="midpoint"):
        blocks.fillet_edges(b, 1, [{"type": "LINE"}])


def test_duplicate_picks_collapse_to_one_edge():
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    assert (blocks.fillet_edges(b, 3, [ref, ref, {"mid": ref["mid"]}]).volume
            == pytest.approx(blocks.fillet_edges(b, 3, [ref]).volume))


def test_picked_edges_ride_along_when_the_body_grows():
    """The user's checklist step 4: fillet the top edges, then make the box
    taller — the rounds stay on the TOP edges (which moved 5 mm up)."""
    short, tall = box(t=20), box(t=30)
    refs = [blocks.edge_ref(short, e) for e in top(short)]
    on_tall = healthy(blocks.fillet_edges(tall, 3, refs))
    same_by_fresh_pick = blocks.fillet_edges(tall, 3, [blocks.edge_ref(tall, e) for e in top(tall)])
    assert on_tall.volume == pytest.approx(same_by_fresh_pick.volume)
    # and it is the top that got rounded: the highest face is now narrower
    top_face = max(on_tall.faces(), key=lambda f: f.center().Z)
    assert top_face.area < 40 * 30 - 1


def test_a_removed_edge_is_named_not_quietly_swapped():
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    gone = blocks.chamfer_edges(b, 4, [ref])        # the edge is now a bevel face
    with pytest.raises(ValueError, match="no longer on the body"):
        blocks.fillet_edges(gone, 1, [ref])
    # the fallback form (midpoint only) has no way to know: it picks the
    # nearest, which is why the stored form carries the two faces
    assert blocks.fillet_edges(gone, 1, [{"mid": ref["mid"]}]).volume < gone.volume


def test_an_invalid_success_is_refused_and_says_what_health_found():
    """The second banned failure, live: at radius 6 the kernel ACCEPTS a solid
    that is not watertight. The CHEAP health check sees it, which is why the op
    can use Document.rebuild's own per-feature policy instead of the ~270 ms
    validity analysis — asserted here so the op cannot go blind by accident."""
    rc = blocks.fillet_edges(box(), 5, "vertical")
    rim = [blocks.edge_ref(rc, e) for e in top(rc)]
    built = blocks._b3d_fillet(blocks.edges_for(rc, rim), radius=6)
    assert inspector.health(built, check_valid=False) != []
    with pytest.raises(ValueError) as ei:
        blocks.fillet_edges(rc, 6, rim)
    msg = str(ei.value)
    assert "broken solid" in msg and "manifold" in msg
    healthy(blocks.fillet_edges(rc, 3, rim))        # a value that does fit still builds


def test_a_non_geometric_failure_is_not_dressed_up_as_geometry(monkeypatch):
    """Before the review fix every failure — including our own bugs — was
    reported as 'a face beside them is too small', a fabricated diagnosis that
    also hid the real cause from the tree."""
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    monkeypatch.setattr(blocks, "_b3d_fillet",
                        lambda *a, **k: (_ for _ in ()).throw(TypeError("bad kwarg")))
    with pytest.raises(ValueError) as ei:
        blocks.fillet_edges(b, 3, [ref])
    msg = str(ei.value)
    assert "TypeError: bad kwarg" in msg
    assert "too small" not in msg


def test_kernel_jargon_never_reaches_the_user(monkeypatch):
    class StdFail_NotDone(Exception):
        pass

    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    monkeypatch.setattr(blocks, "_b3d_chamfer", lambda *a, **k: (_ for _ in ()).throw(
        StdFail_NotDone("BRep_API: command not done")))
    with pytest.raises(ValueError) as ei:
        blocks.chamfer_edges(b, 3, [ref])
    msg = str(ei.value)
    assert "the geometry kernel rejected" in msg
    for leak in ("TopoDS", "NCollection", "Standard_", "BRep", "StdFail"):
        assert leak not in msg


def test_two_stored_faces_that_resolve_to_one_face_read_as_a_gone_edge():
    """resolve_face is a NEAREST match that never fails: when one stored face is
    gone, both can land on the same face, whose edges all 'share' it — and the
    fillet would quietly move to a different edge."""
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    same = {"center": [0, 0, 10], "normal": [0, 0, 1]}
    with pytest.raises(ValueError, match="no longer on the body"):
        blocks.resolve_edge(b, {**ref, "faces": [same, dict(same)]})


def test_tangent_chain_is_a_rim_a_sharp_edge_or_a_full_circle():
    rc = blocks.fillet_edges(box(), 5, "vertical")
    rim = top(rc)
    chain = blocks.tangent_chain(rc, rim[0])
    assert len(chain) == 8 and len({blocks._shape_key(e) for e in chain}) == 8
    b = box()
    assert len(blocks.tangent_chain(b, top(b)[0])) == 1       # a sharp corner stops the walk
    cyl = blocks.disc(10, 5)
    assert len(blocks.tangent_chain(cyl, top(cyl)[0])) == 1     # one closed circle
    healthy(blocks.fillet_edges(rc, 3, [blocks.edge_ref(rc, e) for e in chain]))


def test_edge_ref_carries_the_two_faces_and_their_normals():
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    assert ref["type"] == "LINE" and len(ref["faces"]) == 2
    normals = sorted(tuple(f["normal"]) for f in ref["faces"])
    assert (0.0, 0.0, 1.0) in normals            # the top face
    assert all(abs(sum(c * c for c in n) - 1) < 1e-3 for n in normals)
    # the resolved edge is that very edge
    assert mid(blocks.resolve_edge(b, ref)) == ref["mid"]


# ------------------------------------------------------------ the planner ---

def doc_box(w=40, d=30, t=20):
    doc = Document(name="fil")
    doc.add("b", "plate", {"width": w, "depth": d, "thickness": t}, [])
    doc.rebuild()
    return doc


def doc_rounded():
    doc = doc_box()
    doc.add("g1", "fillet", {"radius": 5, "edges": "vertical"}, ["b"])
    doc.rebuild()
    return doc


@pytest.mark.parametrize("tool", ["fillet", "chamfer"])
def test_plan_for_one_pick(tool):
    doc = doc_box()
    e = top(doc._parts["b"])[0]
    p = toolplan.plan(doc, {"tool": tool, "body_id": "b", "edges": [{"mid": mid(e)}]})
    assert p["ok"] and p["op"] == tool and p["input"] == "b"
    assert len(p["edges"]) == 1 and len(p["edges"][0]["points"]) == 3
    assert p["edges"][0]["length"] == pytest.approx(e.length)
    assert p["ball"]["origin"] == mid(e)
    assert len(p["edges_param"][0]["faces"]) == 2
    assert p["will_build"] == f"{tool} 1 edge of b"


def test_plan_ball_points_into_the_material_on_every_top_edge():
    doc = doc_box()
    b = doc._parts["b"]
    for e in top(b):
        p = toolplan.plan(doc, {"tool": "fillet", "body_id": "b", "edges": [{"mid": mid(e)}]})
        d = p["ball"]["dir"]
        assert sum(c * c for c in d) == pytest.approx(1, abs=1e-3)
        assert d[2] == pytest.approx(-0.7071, abs=1e-3)          # down, into the box
        inward = [-p["ball"]["origin"][0], -p["ball"]["origin"][1], 0]   # toward the centre
        assert d[0] * inward[0] + d[1] * inward[1] > 0


def test_plan_midpoint_straight_from_the_model_edge_line():
    """The browser sends the middle point of the edge's polyline (no maths):
    for a LINE that is points[1] of 3 — and it is the exact midpoint."""
    doc = doc_box()
    e = top(doc._parts["b"])[0]
    poly = toolplan.edge_polyline(e)
    p = toolplan.plan(doc, {"tool": "fillet", "body_id": "b", "edges": [poly[1]]})
    assert p["ok"] and p["edges"][0]["mid"] == mid(e)


def preview(doc, radius=3):
    """the body the viewport shows while a round is being tried: the box with
    its first top edge rounded — the top edges beside it TRIMMED by the radius,
    and the round's own two rims where the new face meets the top and the wall"""
    b = doc._parts["b"]
    e = top(b)[0]
    return e, healthy(blocks.fillet_edges(b, radius, [blocks.edge_ref(b, e)]))


def test_a_click_on_a_trimmed_preview_edge_means_the_edge_it_came_from():
    """While the preview is up the lines on screen are the ROUNDED body's. A top
    edge beside the round is shorter by the radius and its midpoint has moved by
    half of it; it still lies ON its parent, and lying-on is the identity."""
    doc = doc_box()
    e, res = preview(doc)
    zt = (e @ 0.5).Z
    trimmed = [x for x in res.edges() if blocks._gtype(x) == "LINE"
               and abs((x @ 0.5).Z - zt) < 1e-6 and round(x.length, 6) not in (30, 40)]
    assert len(trimmed) == 2 and all(round(x.length) in (27, 37) for x in trimmed)
    for t in trimmed:
        poly = toolplan.edge_polyline(t)
        p = toolplan.plan(doc, {"tool": "fillet", "body_id": "b", "edges": [], "chain": False,
                                "toggle": {"points": poly, "type": "LINE"}})
        assert p["ok"] and len(p["edges"]) == 1 and p["click"] == "added"
        parent = blocks.resolve_edge(doc._parts["b"], {"points": poly})
        assert round(parent.length) == round(t.length) + 3, "the UNTRIMMED edge"
        assert max(blocks._edge_distance(parent, q) for q in poly) < 1e-6, "the line lies on it"
        assert p["edges"][0]["mid"] == mid(parent)


def test_a_rim_the_preview_made_is_refused_not_swapped_for_the_edge_it_replaced():
    """The round's own rims — where the new face meets the top and the wall —
    are edges of NO body in the tree. Nearest-midpoint answered with the rounded
    edge itself, so a click on a rim silently un-picked the edge it replaced."""
    doc = doc_box()
    b = doc._parts["b"]
    e, res = preview(doc)
    rims = [x for x in res.edges() if blocks._gtype(x) == "LINE"
            and abs(x.length - e.length) < 1e-6 and 2.9 < (x @ 0.5 - e @ 0.5).length < 3.1]
    assert len(rims) == 2
    for rim in rims:
        p = toolplan.plan(doc, {"tool": "fillet", "body_id": "b", "chain": False,
                                "edges": [blocks.edge_ref(b, e)],
                                "toggle": {"points": toolplan.edge_polyline(rim), "type": "LINE"}})
        assert p["ok"] is False
        assert "not an edge of this body" in p["error"] and "previewed" in p["error"]


def test_the_plan_says_whether_a_click_added_or_released():
    """With chain on, a click on any edge of a picked smooth rim releases the
    whole rim; the browser says so instead of looking like a refused click."""
    doc = doc_rounded()
    g = doc._parts["g1"]
    lines = [x for x in top(g) if blocks._gtype(x) == "LINE"]
    arcs = [x for x in top(g) if blocks._gtype(x) == "CIRCLE"]
    p = toolplan.plan(doc, {"tool": "fillet", "body_id": "g1", "edges": [],
                            "toggle": {"points": toolplan.edge_polyline(lines[0]), "type": "LINE"}})
    assert p["ok"] and p["click"] == "added" and len(p["edges"]) == 8
    q = toolplan.plan(doc, {"tool": "fillet", "body_id": "g1", "edges": p["picks"],
                            "toggle": {"points": toolplan.edge_polyline(arcs[0]), "type": "CIRCLE"}})
    assert q["ok"] and q["click"] == "removed" and q["edges"] == []
    assert toolplan.plan(doc, {"tool": "fillet", "body_id": "g1",
                               "edges": [{"mid": mid(lines[0])}]})["click"] is None


def doc_pocket():
    """the box with a 20 x 12 pocket 5 deep: 4 inside uprights, 4 inside floor
    rims, 4 outside uprights, 12 outside flat edges (two rims + the opening)"""
    doc = Document(name="pk")
    doc.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    doc.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
    doc.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["t"])
    doc.add("c", "cut", {}, ["b", "tm"])
    doc.rebuild()
    return doc


# ------------------------------------------- faces and tree rows as picks ---
# Fusion's Fillet takes edges, FACES (every edge of one) and FEATURES (the
# edges of the faces a feature made, as they are now). The user (2026-09-08):
# "if I am selecting an extrude and pressing Fillet, those selected face or
# body edges should be selected … another click on the selected body should
# deselect". The rule and every number here: probes/feature_edges_probe.py.

FLOOR = {"center": [0, 0, 5], "normal": [0, 0, 1]}          # the pocket's floor


def zs(edges):
    return sorted({round(e["mid"][2], 3) for e in edges})


def plan(doc, **req):
    return toolplan.plan(doc, {"tool": "fillet", "edges": [], **req})


def test_a_face_click_adds_its_edges_and_a_second_click_takes_them_out():
    doc = doc_pocket()
    p = plan(doc, body_id="c", face_toggle=FLOOR)
    assert p["ok"] and (p["click"], p["click_n"], p["click_of"]) == ("added", 4, "face")
    assert len(p["edges"]) == 4 and zs(p["edges"]) == [5.0]     # the floor's rim, nothing else
    q = plan(doc, body_id="c", edges=p["picks"], face_toggle=FLOOR)
    assert (q["click"], q["click_n"]) == ("removed", 4) and q["edges"] == []
    # a face with ONE of its edges picked already: the click adds the other three
    one = plan(doc, body_id="c", toggle={"mid": [10, 0, 5]})
    assert len(one["edges"]) == 1
    r = plan(doc, body_id="c", edges=one["picks"], face_toggle=FLOOR)
    assert (r["click"], r["click_n"]) == ("added", 3) and len(r["edges"]) == 4


def test_the_added_count_is_the_edges_that_joined_not_the_sets_own():
    """The browser says the count out loud beside the total — "added N edges —
    that face's edges — M picked now" — so N has to be the number that JOINED.
    A wall of a rounded box has FOUR edges and the click brings EIGHTEEN: each
    of its four picks arrives with its tangent rim (review 2026-09-08, which
    measured "added 4 … 18 picked now")."""
    doc = doc_rounded()
    part = doc._parts["g1"]
    wall = next(f for f in part.faces() if blocks._gtype(f) == "PLANE"
                and abs(f.normal_at(f.center()).Z) < 1e-6)
    c, n = wall.center(), wall.normal_at(wall.center())
    pick = {"center": [c.X, c.Y, c.Z], "normal": [n.X, n.Y, n.Z]}
    assert len(toolplan._corners(wall.edges(), blocks._edge_faces(part))) == 4
    p = plan(doc, body_id="g1", face_toggle=pick)
    assert p["ok"] and len(p["picks"]) == 4
    assert (p["click"], p["click_n"], len(p["edges"])) == ("added", 18, 18)
    q = plan(doc, body_id="g1", edges=p["picks"], face_toggle=pick)
    assert (q["click"], q["click_n"]) == ("removed", 18) and q["edges"] == []


def test_a_tree_row_adds_the_edges_its_feature_made_and_again_takes_them_out():
    doc = doc_pocket()
    p = plan(doc, body_id="c", feature_toggle="c")
    assert p["ok"] and (p["click"], p["click_n"], p["click_of"]) == ("added", 12, "c")
    assert zs(p["edges"]) == [5.0, 7.5, 10.0]        # floor rim, uprights, the opening's rim
    q = plan(doc, body_id="c", edges=p["picks"], feature_toggle="c")
    assert (q["click"], q["click_n"]) == ("removed", 12) and q["edges"] == []
    # the base plate's faces AS THEY ARE NOW: the outer twelve and the opening
    b = plan(doc, body_id="c", feature_toggle="b")
    assert len(b["edges"]) == 16 and zs(b["edges"]) == [-10.0, 0.0, 10.0]
    # the tool prism's row means the pocket too — its faces ARE the pocket's
    t = plan(doc, body_id="c", feature_toggle="tm")
    assert len(t["edges"]) == 12
    # ...and the row's edges are what the op is given (stored form, R1)
    assert len(p["edges_param"]) == 12 and all("faces" in r for r in p["edges_param"])


def doc_flush_boss():
    """the pocketed box with a 6 x 6 x 5 boss standing IN the pocket, its top
    flush with the plate top at z = +10 and offset in x so it is not centred
    (probes/feature_faces_newest_probe.py §1)"""
    doc = doc_pocket()
    doc.add("s", "plate", {"width": 6, "depth": 6, "thickness": 5}, [])
    doc.add("sm", "move", {"x": 5, "y": 0, "z": 7.5}, ["s"])
    doc.add("u", "fuse", {}, ["c", "sm"])
    doc.rebuild()
    return doc


def test_a_flush_boss_belongs_to_the_boss_row_not_the_plates():
    """NEWEST WINS. A face a LATER feature made, coplanar with and inside the
    bounding box of an earlier feature's face, passes the host test for BOTH —
    so the base plate's row lit the flush boss's rim as well as its own, and a
    radius rounded it (review 2026-09-08: 7 faces / 20 edges instead of 6 / 16)."""
    doc = doc_flush_boss()
    boss_top = next(f for f in doc._parts["u"].faces()
                    if abs(f.center().Z - 10) < 1e-6 and abs(f.area - 36) < 0.01)
    assert abs(boss_top.center().X - 5) < 1e-6         # the boss's own top, a = 36
    # the plate's row is its SIX faces as they are now — not the boss's seventh
    assert len(provenance.feature_faces(doc, "b", "u")) == 6
    b = plan(doc, body_id="u", feature_toggle="b")
    assert b["ok"] and len(b["edges"]) == 16 and zs(b["edges"]) == [-10.0, 0.0, 10.0]
    # ...and the boss's top is on the row that DID make it, as it always was
    assert blocks._shape_key(boss_top) in provenance.feature_faces(doc, "u", "u")
    u = plan(doc, body_id="u", feature_toggle="u")
    assert u["ok"] and len(u["edges"]) == 12


def test_the_cut_side_of_newest_wins_too():
    """The same accident on the CUT side, so nobody fixes only the fuse path: a
    pocket milled through a boss back down to the base plane leaves a floor
    coplanar with, and inside, the plate's own top. (Its plan is not asserted:
    a row click on this shape raises over blocks.resolve_face's nearest-centre
    tie between two faces that share a centre — a separate finding, red before
    and after this one.)"""
    doc = Document(name="cs")
    doc.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    doc.add("s", "plate", {"width": 20, "depth": 12, "thickness": 5}, [])
    doc.add("sm", "move", {"x": 0, "y": 0, "z": 12.5}, ["s"])
    doc.add("u", "fuse", {}, ["b", "sm"])
    doc.add("t2", "plate", {"width": 8, "depth": 6, "thickness": 5}, [])
    doc.add("t2m", "move", {"x": 0, "y": 0, "z": 12.5}, ["t2"])
    doc.add("c2", "cut", {}, ["u", "t2m"])
    doc.rebuild()
    floor = next(f for f in doc._parts["c2"].faces()
                 if abs(f.center().Z - 10) < 1e-6 and abs(f.area - 48) < 0.01)
    assert len(provenance.feature_faces(doc, "b", "c2")) == 6
    assert blocks._shape_key(floor) in provenance.feature_faces(doc, "c2", "c2")


def test_a_row_picked_before_the_tool_names_the_body_it_is_on():
    doc = doc_pocket()
    p = plan(doc, feature_toggle="tm")                    # no body_id at all
    assert p["ok"] and p["input"] == "c" and len(p["edges"]) == 12
    p = toolplan.plan(doc, {"tool": "chamfer", "edges": [], "feature_toggle": "b"})
    assert p["ok"] and p["input"] == "c" and len(p["edges"]) == 16


def test_rows_that_are_not_edges_of_this_body_speak():
    doc = doc_pocket()
    doc.add("x", "plate", {"width": 5, "depth": 5, "thickness": 5}, [])
    doc.add("sk1", "sketch", {"plane": "XY", "entities": [{"kind": "circle", "cx": 0, "cy": 0, "r": 3}]})
    doc.rebuild()
    r = plan(doc, body_id="c", feature_toggle="x")
    assert not r["ok"] and "not part of c's history" in r["error"]
    r = plan(doc, body_id="c", feature_toggle="nope")
    assert not r["ok"] and "no feature 'nope'" in r["error"]
    r = plan(doc, body_id="c", feature_toggle="sk1")
    assert not r["ok"] and "a sketch has no edges" in r["error"]
    r = plan(doc, feature_toggle="sk1")                    # a sketch row names no body either
    assert not r["ok"] and "a sketch has no edges" in r["error"]
    r = plan(doc)
    assert not r["ok"] and "needs the edges of a body" in r["error"]


def test_a_face_only_the_preview_has_is_refused_a_survivor_accepted():
    """the picker hands the tool clicks on its own PREVIEW body: a fillet band's
    centre would resolve to the nearest wall of the input body and round ITS
    edges — refused; the preview's top face is the input's top face, trimmed"""
    doc = doc_rounded()                                   # b, then g1 rounds its uprights
    band = next(f for f in doc._parts["g1"].faces() if blocks._gtype(f) == "CYLINDER")
    c = band.center()
    r = plan(doc, body_id="b", face_toggle={"center": [c.X, c.Y, c.Z]})
    assert not r["ok"] and "not on b" in r["error"]
    p = plan(doc, body_id="b", face_toggle={"center": [0, 0, 10], "normal": [0, 0, 1]})
    assert p["ok"] and len(p["edges"]) == 4               # b's top has 4 edges (g1's has 8)
    r = plan(doc, body_id="b", face_toggle={})
    assert not r["ok"] and "no centre" in r["error"]


def disc_band_pick(radius=3.0):
    """a disc r10 h20 with its top rim rounded, and the PREVIEW band's centre +
    normal in the form the payload carries them (studio.py rounds a centre to
    2 decimals, a normal to 3)"""
    doc = Document(name="disc")
    doc.add("d", "disc", {"radius": 10, "thickness": 20}, [])
    doc.add("f1", "fillet", {"radius": radius, "edges": "top"}, ["d"])
    doc.rebuild()
    band = next(f for f in doc._parts["f1"].faces() if blocks._gtype(f) == "TORUS")
    c = band.center()
    n = band.normal_at(c)
    return doc, {"center": [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)],
                 "normal": [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)]}


@pytest.mark.parametrize("radius", [3.0, 0.5, 0.1])
def test_a_round_this_tool_drew_is_refused_on_a_body_of_revolution(radius):
    """The case a bounding box could not see: a cylinder wall's box is the whole
    cube around the body, so the band's centre was "inside" it, resolve_face
    named the WALL, and the plan quietly added the disc's BOTTOM rim 20 mm away
    (review 2026-09-08). Smaller radii bring the band's centre closer to the
    wall, which is why distance alone is not the guard."""
    doc, pick = disc_band_pick(radius)
    r = plan(doc, body_id="d", face_toggle=pick)
    assert not r["ok"] and "not on d" in r["error"]
    assert "TORUS" not in r["error"] and "bounding" not in r["error"]


def test_the_disc_wall_itself_still_picks_both_of_its_rims():
    """the guard must not cost the legitimate click: the WALL really has both"""
    doc, _ = disc_band_pick()
    wall = next(f for f in doc._parts["d"].faces() if blocks._gtype(f) == "CYLINDER")
    c, n = wall.center(), wall.normal_at(wall.center())
    p = plan(doc, body_id="d", face_toggle={
        "center": [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)],
        "normal": [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)]})
    assert p["ok"] and len(p["edges"]) == 2
    assert zs(p["edges"]) == [-10.0, 10.0]


def test_a_face_whose_own_centre_is_off_its_material_still_picks():
    """A washer's top face is an ANNULUS and `Face.center()` is the AREA
    CENTROID of a plane, so the clicked centre sits in the HOLE — on the face's
    surface, not on its material. The guard asks the first question only
    (probes/face_of_revolve_probe.py §2/§3), or a real pick would be refused."""
    doc = Document(name="wash")
    doc.add("d", "disc", {"radius": 10, "thickness": 5}, [])
    doc.add("h", "with_center_hole", {"radius": 4}, ["d"])
    doc.rebuild()
    ring = next(f for f in doc._parts["h"].faces()
                if blocks._gtype(f) == "PLANE" and f.center().Z > 0)
    c, n = ring.center(), ring.normal_at(ring.center())
    assert abs(c.X) < 1e-6 and abs(c.Y) < 1e-6          # in the hole
    p = plan(doc, body_id="h", face_toggle={
        "center": [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)],
        "normal": [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)]})
    assert p["ok"] and len(p["edges"]) == 2 and {e["type"] for e in p["edges"]} == {"CIRCLE"}


def test_a_seam_is_not_an_edge_a_face_or_a_row_offers():
    """a fused boss: its wall's seam bounds ONE face — a line on the mesh, not a
    corner. Neither the wall nor the boss's row offers it."""
    doc = Document(name="boss")
    doc.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    doc.add("p", "disc", {"radius": 6, "thickness": 5}, [])
    doc.add("pm", "move", {"x": 5, "y": 0, "z": 12.5}, ["p"])
    doc.add("f", "fuse", {}, ["b", "pm"])
    doc.rebuild()
    p = plan(doc, body_id="f", feature_toggle="f")
    assert len(p["edges"]) == 2 and {e["type"] for e in p["edges"]} == {"CIRCLE"}
    wall = next(f for f in doc._parts["f"].faces() if blocks._gtype(f) == "CYLINDER")
    c = wall.center()
    q = plan(doc, body_id="f", face_toggle={"center": [c.X, c.Y, c.Z]})
    assert q["ok"] and len(q["edges"]) == 2 and {e["type"] for e in q["edges"]} == {"CIRCLE"}


def test_a_row_whose_faces_were_consumed_speaks():
    """the tool prism 't' sits at z -5..5 before its move: only its top face
    coincides with the pocket floor, so it still owns 4 edges — while a feature
    with NO face left on the body says so instead of picking nothing quietly"""
    doc = doc_pocket()
    t = plan(doc, body_id="c", feature_toggle="t")
    assert t["ok"] and len(t["edges"]) == 4 and zs(t["edges"]) == [5.0]
    doc.add("t2", "plate", {"width": 4, "depth": 4, "thickness": 4}, [])
    doc.add("t2m", "move", {"x": 30, "y": 30, "z": 30}, ["t2"])
    doc.add("c2", "cut", {}, ["c", "t2m"])                  # cuts nothing: the tool is off the body
    doc.rebuild()
    r = plan(doc, body_id="c2", feature_toggle="c2")
    assert not r["ok"] and "has no edges left on c2" in r["error"]


def test_plan_chain_is_on_for_fresh_picking_and_can_be_turned_off():
    """Fusion's default for PICKING. (A stored selection defaults the other way
    — see test_a_chain_off_fillet_is_not_grown_when_it_is_reopened.)"""
    doc = doc_rounded()
    rim = top(doc._parts["g1"])
    line = next(e for e in rim if blocks._gtype(e) == "LINE")
    req = {"tool": "fillet", "body_id": "g1", "edges": [mid(line)]}
    assert toolplan.plan(doc, req)["chain"] is True          # nothing asked: chain
    on = toolplan.plan(doc, {**req, "chain": True})
    off = toolplan.plan(doc, {**req, "chain": False})
    assert on["chain"] is True and len(on["edges"]) == 8
    assert off["chain"] is False and len(off["edges"]) == 1
    assert sorted(e["type"] for e in on["edges"]).count("CIRCLE") == 4


def test_a_chain_off_fillet_is_not_grown_when_it_is_reopened():
    """The founding rule: geometry never changes without the user asking. A
    single edge of a smooth rim was picked with the chain box OFF; reopening it
    must not silently turn it into the whole rim (review 2026-09-04)."""
    doc = doc_rounded()
    rc = doc._parts["g1"]
    line = next(e for e in top(rc) if blocks._gtype(e) == "LINE")
    one = blocks.edge_ref(rc, line)
    doc.add("f1", "fillet", {"radius": 1, "edges": [one]}, ["g1"])
    doc.rebuild()
    p = toolplan.plan(doc, {"tool": "fillet", "feature_id": "f1"})    # no chain: the default
    assert p["chain"] is False and len(p["edges"]) == 1
    assert p["edges_param"] == [one]
    # the user can still opt in — and then SEES all 8 before pressing OK
    assert len(toolplan.plan(doc, {"tool": "fillet", "feature_id": "f1",
                                   "chain": True})["edges"]) == 8


def test_a_chain_on_fillet_reopens_with_its_whole_chain_and_nothing_added():
    """The stored set IS the answer on edit — for a chain-ON fillet that means
    the same 8 edges come back, and no further growth is possible."""
    doc = doc_rounded()
    rc = doc._parts["g1"]
    rim = [blocks.edge_ref(rc, e) for e in top(rc)]
    assert len(rim) == 8
    doc.add("f1", "fillet", {"radius": 1, "edges": rim}, ["g1"])
    doc.rebuild()
    p = toolplan.plan(doc, {"tool": "fillet", "feature_id": "f1"})
    assert p["chain"] is False and len(p["edges"]) == 8
    assert p["edges_param"] == rim


def test_one_click_on_an_ai_authored_group_adds_only_that_edge():
    """A group written by the AI ('horizontal' = the straight rim lines) has
    tangent neighbours (the corner arcs). One extra click used to add all of
    them — the click must add exactly the edge clicked."""
    doc = doc_rounded()
    rc = doc._parts["g1"]
    group = blocks.edges_for(rc, "horizontal")
    refs = [blocks.edge_ref(rc, e) for e in group]
    assert len(toolplan._expand(rc, refs, True)) > len(group), \
        "this group must HAVE tangent neighbours or the test proves nothing"
    doc.add("f1", "fillet", {"radius": 0.5, "edges": "horizontal"}, ["g1"])
    doc.rebuild()
    p = toolplan.plan(doc, {"tool": "fillet", "feature_id": "f1"})
    assert p["chain"] is False                      # not chain-closed: never grown
    assert p["edges_param"] == "horizontal" and len(p["edges"]) == len(group)
    vert = next(e for e in rc.edges()
                if blocks._shape_key(e) not in {blocks._shape_key(g) for g in group}
                and blocks._gtype(e) == "LINE")
    p2 = toolplan.plan(doc, {"tool": "fillet", "feature_id": "f1",
                             "toggle": {"points": toolplan.edge_polyline(vert)}})
    assert len(p2["edges"]) == len(group) + 1
    assert isinstance(p2["edges_param"], list)      # the group became explicit picks


def test_a_fresh_pick_still_chains_by_default():
    doc = doc_rounded()
    rc = doc._parts["g1"]
    line = next(e for e in top(rc) if blocks._gtype(e) == "LINE")
    p = toolplan.plan(doc, {"tool": "fillet", "body_id": "g1", "edges": [],
                            "toggle": {"points": toolplan.edge_polyline(line)}})
    assert p["chain"] is True and len(p["edges"]) == 8


def test_plan_with_nothing_picked_keeps_the_pick_alive():
    p = toolplan.plan(doc_box(), {"tool": "chamfer", "body_id": "b", "edges": []})
    assert p["ok"] and p["edges"] == [] and p["ball"] is None
    assert "pick the edges of b" in p["will_build"]


def test_plan_refusals_are_sentences():
    doc = doc_box()
    assert "click an edge" in toolplan.plan(doc, {"tool": "fillet"})["error"]
    assert "no body 'zz'" in toolplan.plan(doc, {"tool": "fillet", "body_id": "zz",
                                                 "edges": [[0, 0, 0]]})["error"]
    doc.add("bad", "fillet", {"radius": 99, "edges": "all"}, ["b"])
    doc.rebuild()
    assert doc.get("bad").status == "failed"
    err = toolplan.plan(doc, {"tool": "fillet", "body_id": "bad", "edges": [[0, 0, 0]]})["error"]
    assert "not a built solid" in err and "fix it first" in err
    assert "is a plate, not fillet / chamfer" in toolplan.plan(
        doc, {"tool": "fillet", "feature_id": "b"})["error"]
    garbage = toolplan.plan(doc, {"tool": "fillet", "body_id": "b", "edges": [{"foo": 1}]})
    assert garbage["ok"] is False and "midpoint" in garbage["error"]


def test_plan_edges_param_is_what_the_op_takes():
    doc = doc_box()
    b = doc._parts["b"]
    p = toolplan.plan(doc, {"tool": "fillet", "body_id": "b",
                            "edges": [mid(e) for e in top(b)]})
    doc.add("f1", "fillet", {"radius": 3, "edges": p["edges_param"]}, ["b"])
    doc.rebuild()
    f = doc.get("f1")
    assert f.status == "ok" and f.volume < b.volume
    # the tree stores geometry, never an index
    assert all(set(r) == {"mid", "dir", "type", "faces"} for r in f.params["edges"])


def test_plan_edit_reads_the_stored_edges_and_keeps_a_legacy_group():
    doc = doc_box()
    b = doc._parts["b"]
    refs = [blocks.edge_ref(b, e) for e in top(b)[:2]]
    doc.add("f1", "fillet", {"radius": 3, "edges": refs}, ["b"])
    doc.add("g1", "chamfer", {"length": 2, "edges": "vertical"}, ["f1"])
    doc.rebuild()
    pe = toolplan.plan(doc, {"tool": "fillet", "feature_id": "f1"})
    assert pe["ok"] and pe["input"] == "b" and len(pe["edges"]) == 2
    assert pe["edges_param"] == refs
    pg = toolplan.plan(doc, {"tool": "chamfer", "feature_id": "g1"})
    assert pg["ok"] and pg["input"] == "f1" and len(pg["edges"]) == 4
    assert pg["edges_param"] == "vertical"     # the AI's vocabulary survives an edit
    # an edit plan reports a gone edge instead of guessing
    doc.get("f1").params["edges"] = [{**refs[0], "faces": [
        {"center": [0, 0, 10], "normal": [0, 0, 1]},
        {"center": [0, 0, -10], "normal": [0, 0, -1]}]}]   # top and bottom share no edge
    assert "no longer on the body" in toolplan.plan(doc, {"tool": "fillet", "feature_id": "f1"})["error"]


def test_edge_polyline_shapes():
    cyl = blocks.disc(10, 5)
    line = top(box())[0]
    circle = top(cyl)[0]
    pl, pc = toolplan.edge_polyline(line), toolplan.edge_polyline(circle)
    assert len(pl) == 3 and len(pc) == 25
    assert pl[0] == [round(v, 4) for v in tuple(line @ 0)]
    assert all(abs((x * x + y * y) ** 0.5 - 10) < 1e-3 for x, y, _ in pc)


# ------------------------------------------------ the per-body memo's key ---

def test_a_moved_copy_does_not_inherit_its_parents_faces():
    """blocks._face_rows / _edge_topo remember a body's faces so a 48-edge plan
    costs 0.4 s instead of 34 s. Stored as ATTRIBUTES on the Part they rode
    along in build123d's deepcopy — moved() and `Pos * part` copy first and move
    second — so a moved plate resolved a face by its parent's centres (caught by
    test_revolve_p3b in the full tier, 2026-09-08; probes/shape_cache_probe.py).
    The memo lives beside the shape now: a copy misses, an in-place move misses."""
    from copy import deepcopy

    from build123d import Location, Pos

    b = box()
    top = blocks.resolve_face(b, [0, 0, 10], [0, 0, 1])            # fills b's memo
    assert [round(v, 3) for v in tuple(top.center())] == [0, 0, 10]
    by_edge = blocks._edge_faces(b)
    assert len(by_edge) == 12
    moved = Pos(100, 50, 0) * b
    got = blocks.resolve_face(moved, [100, 50, 10], [0, 0, 1])
    assert [round(v, 3) for v in tuple(got.center())] == [100, 50, 10], "the moved body's own top"
    e = blocks.resolve_edge(moved, {"mid": [100, 65, 10]})           # a top edge, at its new place
    assert [round(v, 3) for v in tuple(e @ 0.5)] == [100, 65, 10]
    assert blocks._edge_faces(moved) is not by_edge, "a copy has its own adjacency"
    # in place: the same Python object, a different TopoDS location
    r = deepcopy(b)
    blocks.resolve_face(r, [0, 0, 10], [0, 0, 1])
    r.move(Location((0, 0, 5)))
    got = blocks.resolve_face(r, [0, 0, 15], [0, 0, 1])
    assert [round(v, 3) for v in tuple(got.center())] == [0, 0, 15]
    # and the memo does hold for the same, unmoved body
    assert blocks._edge_faces(b) is by_edge


def test_the_body_memo_lets_a_dead_body_go():
    """The memo holds each body's own Faces and Edges, and every one of them
    points back at the body (Face.topo_parent) — so a weak key could never
    expire and every superseded body stayed in the process for good: eight
    throwaway bodies, eight live entries, 1.3 MB of python wrappers each on a
    200-face body (probes/shape_cache_leak_probe.py §1). It is bounded now."""
    import gc
    import weakref

    refs = []
    for _ in range(blocks._MAX_SHAPE_CACHES + 4):
        p = blocks.plate(40, 30, 20)
        blocks._face_rows(p)                       # both slots
        blocks._edge_faces(p)
        refs.append(weakref.ref(p))
        del p
    gc.collect()
    alive = [r for r in refs if r() is not None]
    assert len(alive) <= blocks._MAX_SHAPE_CACHES, f"{len(alive)} dead bodies still held"
    assert len(blocks._SHAPE_CACHES) <= blocks._MAX_SHAPE_CACHES


def test_the_memo_is_fresh_after_an_in_place_move():
    """The stored TopoDS shape IS the live one after `part.move()` — it mutates
    in place — so IsEqual compares it with itself and says True. The stored
    hash is what notices (review 2026-09-08)."""
    from build123d import Location

    b = box()
    assert [round(v, 3) for v in tuple(blocks.resolve_face(b, [0, 0, 10], [0, 0, 1]).center())] \
        == [0, 0, 10]
    ent = blocks._SHAPE_CACHES[id(b)]
    stored = ent[1]["faces"]
    b.move(Location((0, 0, 5)))
    assert stored[0].IsEqual(b.wrapped), "the same TopoDS object: IsEqual cannot see the move"
    assert stored[1] != blocks._shape_key(b), "the hash can"
    got = blocks.resolve_face(b, [0, 0, 15], [0, 0, 1])
    assert [round(v, 3) for v in tuple(got.center())] == [0, 0, 15]
