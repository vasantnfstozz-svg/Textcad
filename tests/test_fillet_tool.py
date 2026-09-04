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
def test_too_big_refuses_and_names_a_value_that_builds(op, value):
    b = box()
    ref = blocks.edge_ref(b, top(b)[0])
    with pytest.raises(ValueError) as ei:
        OPS[op](b, value, [ref])
    msg = str(ei.value)
    assert msg.startswith(op + ":") and "does not fit" in msg
    fits = float(msg.split("builds here is ")[1].split(" mm")[0])
    assert 19 <= fits <= 19.9, msg              # the side face is 20 tall
    healthy(OPS[op](b, fits, [ref]))            # the number it names BUILDS


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


def test_an_invalid_success_is_refused_with_the_largest_that_fits():
    rc = blocks.fillet_edges(box(), 5, "vertical")
    rim = [blocks.edge_ref(rc, e) for e in top(rc)]
    with pytest.raises(ValueError) as ei:
        blocks.fillet_edges(rc, 6, rim)             # the kernel returns an INVALID solid here
    msg = str(ei.value)
    assert "broken solid" in msg and "largest that builds here is" in msg
    fits = float(msg.split("builds here is ")[1].split(" mm")[0])
    assert fits <= 5.0
    healthy(blocks.fillet_edges(rc, fits, rim))


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


def test_plan_chain_is_on_by_default_and_can_be_turned_off():
    doc = doc_rounded()
    rim = top(doc._parts["g1"])
    line = next(e for e in rim if blocks._gtype(e) == "LINE")
    on = toolplan.plan(doc, {"tool": "fillet", "body_id": "g1", "edges": [mid(line)]})
    off = toolplan.plan(doc, {"tool": "fillet", "body_id": "g1", "edges": [mid(line)],
                              "chain": False})
    assert on["chain"] is True and len(on["edges"]) == 8
    assert off["chain"] is False and len(off["edges"]) == 1
    assert sorted(e["type"] for e in on["edges"]).count("CIRCLE") == 4


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
