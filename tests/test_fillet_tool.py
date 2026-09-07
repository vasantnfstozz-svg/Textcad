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


class _BadEdge:
    """An edge the kernel will not answer for. OCP failures derive from
    Exception, not RuntimeError, so a barrier that catches RuntimeError misses
    them entirely (house rule 5)."""

    def __init__(self, key=-4242):
        self.wrapped = key

    def __matmul__(self, t):
        raise Exception("Standard_Failure: no point on this edge")

    def __mod__(self, t):
        raise Exception("Standard_Failure: no tangent on this edge")

    @property
    def length(self):
        raise Exception("Standard_Failure: no length on this edge")


class _UnkeyedEdge(_BadEdge):
    """...and one that cannot even be identified (our own bug, not the kernel's)"""

    @property
    def wrapped(self):
        raise Exception("Standard_Failure: no shape behind this edge")

    def __init__(self):
        pass


class _StubPart:
    """a body whose edge list we choose"""

    def __init__(self, edges):
        self._edges = edges

    def edges(self):
        return self._edges


def test_a_kernel_refusal_on_one_edge_costs_that_edge_and_nothing_else():
    """Rule 5: a kernel exception must never reach the user. The chips made
    edge_groups measure EVERY edge of the body on EVERY plan, so one edge the
    kernel will not answer for would take the whole Fillet panel down with it —
    before the chips such an edge only misbehaved on its own (review
    2026-09-07). It belongs to no group; the rest of the body is unaffected."""
    doc = doc_pocket()
    part = doc._parts["c"]
    faces = list(part.faces())[:2]
    assert blocks.edge_side(_BadEdge(), faces) is None
    assert blocks.edge_direction(_BadEdge()) == "other"
    good = {k: len(v) for k, v in blocks.edge_groups(part).items()}
    bad, unkeyed = _BadEdge(), _UnkeyedEdge()
    by_edge = dict(blocks._edge_faces(part))
    by_edge[blocks._shape_key(bad)] = faces        # it even has two faces to measure against
    stub = _StubPart(list(part.edges()) + [bad, unkeyed])
    g = blocks.edge_groups(stub, by_edge)
    assert {k: len(v) for k, v in g.items()} == good


@pytest.mark.parametrize("name", sorted(__import__("gauntlet").BODIES))
def test_edge_groups_answers_for_every_corpus_body(name):
    """Rule 4: an operation is the feature TIMES the geometry. The classifier
    runs over every edge of whatever the user has open — cones, tori, fused
    seams — so it answers for the whole corpus or the panel cannot open."""
    from gauntlet import BODIES
    g = blocks.edge_groups(BODIES[name]())
    assert set(g) == set(blocks.EDGE_GROUPS)
    assert all(isinstance(v, list) for v in g.values())
    assert len(g["inside/all"]) >= len(g["inside/vertical"])
    assert len(g["outside/all"]) >= len(g["outside/horizontal"])


def doc_round_pocket():
    """the same box, but the pocket's upright corners are ROUNDED r3 (the shop
    rule: no sharp internal corners in a milled part). Its floor rim is then one
    tangent chain of 8 — 4 lines and 4 flat arcs — so ONE chained click picks
    the whole inside/horizontal group."""
    doc = Document(name="rp")
    doc.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    doc.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
    doc.add("tf", "fillet", {"radius": 3, "edges": "vertical"}, ["t"])
    doc.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["tf"])
    doc.add("c", "cut", {}, ["b", "tm"])
    doc.rebuild()
    return doc


def test_a_lit_chip_takes_its_group_out_when_a_chained_click_lit_it():
    """The chip's lit / part / dim state is read off the PICKED edges — which
    are the picks grown into their tangent chains — while the chip's click used
    to compare the raw picks. On a machinable pocket (rounded corners) one
    chained click lights inside/horizontal 8 of 8 and the tooltip says "click to
    take them out"; the click then ADDED the other 7 and the chat said so, and
    it took a second click to remove anything (review 2026-09-07)."""
    doc = doc_round_pocket()
    part = doc._parts["c"]
    g = blocks.edge_groups(part)
    assert len(g["inside/horizontal"]) == 8 == len(g["inside/all"])
    assert len(g["inside/vertical"]) == 0, "the rounded corners are smooth seams"
    line = next(e for e in g["inside/horizontal"] if blocks._gtype(e) == "LINE")
    p = toolplan.plan(doc, {"tool": "fillet", "body_id": "c", "edges": [],
                            "toggle": {"points": toolplan.edge_polyline(line)}})
    assert p["chain"] is True and len(p["edges"]) == 8, "one click chains the whole rim"
    assert len(p["picks"]) == 1, "as ONE pick"
    assert p["groups"]["inside/horizontal"] == {"total": 8, "picked": 8}, "the chip is LIT"
    q = toolplan.plan(doc, {"tool": "fillet", "body_id": "c", "edges": p["picks"],
                            "group_toggle": {"side": "inside", "dir": "horizontal"}})
    assert q["click"] == "removed", "a lit chip takes its group out on the FIRST click"
    assert q["click_n"] == 8, "and says how many edges went, not how many picks"
    assert q["edges"] == [] and q["groups"]["inside/horizontal"]["picked"] == 0


def test_a_chip_adds_only_what_the_chain_has_not_already_picked():
    """The other half of the same rule: a chip that is PART lit adds the rest
    and counts only those — never the edges the chain already brought in."""
    doc = doc_round_pocket()
    part = doc._parts["c"]
    g = blocks.edge_groups(part)
    line = next(e for e in g["inside/horizontal"] if blocks._gtype(e) == "LINE")
    p = toolplan.plan(doc, {"tool": "fillet", "body_id": "c", "edges": [],
                            "toggle": {"points": toolplan.edge_polyline(line)},
                            "chain": False})
    assert len(p["edges"]) == 1 and p["groups"]["inside/horizontal"]["picked"] == 1
    q = toolplan.plan(doc, {"tool": "fillet", "body_id": "c", "edges": p["picks"],
                            "chain": False,
                            "group_toggle": {"side": "inside", "dir": "horizontal"}})
    assert q["click"] == "added" and q["click_n"] == 7, "the one already picked is not added again"
    assert len(q["edges"]) == 8


def test_edge_groups_tell_inside_corners_from_outside_edges():
    """probes/edge_side_probe.py, locked in: concave vs convex by the in-face
    direction against the other face's normal; flat-lying vs upright; smooth
    seams and one-face seams belong to no group; classified once per body."""
    doc = doc_pocket()
    part = doc._parts["c"]
    g = blocks.edge_groups(part)
    assert {k: len(v) for k, v in g.items()} == {
        "inside/vertical": 4, "inside/horizontal": 4, "inside/all": 8,
        "outside/vertical": 4, "outside/horizontal": 12, "outside/all": 16}
    for e in g["inside/all"]:                      # every inside edge is IN the pocket
        m = e @ 0.5
        assert abs(m.X) <= 10 + 1e-6 and abs(m.Y) <= 6 + 1e-6 and 5 - 1e-6 <= m.Z <= 10 + 1e-6
    assert blocks.edge_groups(part) is g, "cached on the body"
    r = doc_rounded()._parts["g1"]                 # uprights rounded r5
    gr = {k: len(v) for k, v in blocks.edge_groups(r).items()}
    assert gr["inside/all"] == 0 and gr["outside/vertical"] == 0, "8 smooth seams are no corner"
    assert gr["outside/horizontal"] == 16 == gr["outside/all"], "8 lines + 8 flat arcs"


def test_a_group_chip_adds_the_whole_group_and_a_second_click_takes_it_out():
    doc = doc_pocket()
    req = lambda edges, side, d: {"tool": "fillet", "body_id": "c", "edges": edges,
                                  "group_toggle": {"side": side, "dir": d}}
    p = toolplan.plan(doc, req([], "inside", "vertical"))
    assert p["ok"] and p["click"] == "added" and p["click_n"] == 4 and len(p["edges"]) == 4
    assert p["groups"]["inside/vertical"] == {"total": 4, "picked": 4}
    assert p["groups"]["inside/all"] == {"total": 8, "picked": 4}       # the chip shows PART
    assert p["groups"]["outside/horizontal"] == {"total": 12, "picked": 0}
    q = toolplan.plan(doc, req(p["picks"], "inside", "horizontal"))
    assert q["click"] == "added" and q["click_n"] == 4 and len(q["edges"]) == 8
    assert q["groups"]["inside/all"]["picked"] == 8
    r = toolplan.plan(doc, req(q["picks"], "inside", "vertical"))      # all picked: out
    assert r["click"] == "removed" and r["click_n"] == 4 and len(r["edges"]) == 4
    s = toolplan.plan(doc, req(r["picks"], "inside", "all"))           # partly picked: ADD the rest
    assert s["click"] == "added" and s["click_n"] == 4 and len(s["edges"]) == 8
    assert len(s["edges_param"]) == 8 and all(len(e["faces"]) == 2 for e in s["edges_param"])
    # the round itself builds on the group — an inside round ADDS material
    v0 = doc._parts["c"].volume
    assert healthy(blocks.fillet_edges(doc._parts["c"], 2, s["edges_param"])).volume > v0
    # a group the body lacks is a sentence, not an empty click
    e = toolplan.plan(doc_rounded(), {"tool": "fillet", "body_id": "g1", "edges": [],
                                      "group_toggle": {"side": "inside", "dir": "vertical"}})
    assert e["ok"] is False and "has no upright inside-corner edges" in e["error"]
    # a plan with NO click still reports the groups, for the chips' first paint
    z = toolplan.plan(doc, {"tool": "fillet", "body_id": "c", "edges": []})
    assert z["ok"] and z["click"] is None and z["groups"]["inside/all"] == {"total": 8, "picked": 0}


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
