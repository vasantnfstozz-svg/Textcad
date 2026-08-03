"""Trim tool geometry (sketch_trim.py) — the last P1 backlog item.

Trim = click a piece of an entity outline between intersections:
  * seam between material regions   -> dissolved (shapes union-rebuilt)
  * boundary of an enclosed gap     -> gap filled into the profile
  * outer boundary                  -> refused with a clear message
  * crossing-free entity            -> deleted whole (Fusion parity)
Rebuilt clusters become exact path/circle entities; untouched entities
stay parametric.
"""
import math
import pytest

import sketch as sk
import sketch_trim as tr

RECT = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 40, "h": 20}


def area_of(entities):
    return sk.make_sketch("XY", 0, entities).area


def mid(piece):
    return piece["pts"][len(piece["pts"]) // 2]


def circle_piece(pieces, ent, pred):
    return next(p for p in pieces if p["ent"] == ent and pred(mid(p)))


# ---------------------------------------------------------------- pieces --

def test_pieces_split_at_intersections():
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    pieces = tr.trim_pieces(ents)
    # rect outline cut in 2, circle outline cut in 2 — none "whole"
    assert len([p for p in pieces if p["ent"] == 0]) == 2
    assert len([p for p in pieces if p["ent"] == 1]) == 2
    assert not any(p["whole"] for p in pieces)
    assert all(len(p["pts"]) >= 2 for p in pieces)


def test_crossing_free_entity_is_one_whole_piece():
    ents = [dict(RECT), {"kind": "circle", "mode": "add",
                         "x": 100, "y": 0, "r": 5}]
    pieces = tr.trim_pieces(ents)
    lone = [p for p in pieces if p["ent"] == 1]
    assert len(lone) == 1 and lone[0]["whole"]


# ----------------------------------------------------------------- apply --

def test_trim_dangling_arc_dissolves_to_material():
    """Cut circle biting the rect edge: trimming the OUTSIDE (dangling) arc
    keeps the bite — material is untouched, the dangle just disappears."""
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    dangle = circle_piece(tr.trim_pieces(ents), 1, lambda m: m[0] > 20.05)
    res = tr.trim_apply(ents, dangle["id"])
    bite = math.pi * 64 / 2                       # half the disc is inside
    assert area_of(res["entities"]) == pytest.approx(800 - bite, abs=0.5)


def test_trim_bite_arc_fills_exactly_the_inside_cell():
    """Trimming the bite boundary INSIDE the rect fills only the inside half
    of the disc (a U-minus-M component spans both halves — the arrangement
    cell must be clipped to the rect)."""
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    arc = circle_piece(tr.trim_pieces(ents), 1, lambda m: m[0] < 19.95)
    res = tr.trim_apply(ents, arc["id"])
    assert area_of(res["entities"]) == pytest.approx(800, abs=0.2)


def test_trim_seam_of_two_add_circles_gives_exact_union():
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    ents = [A, B]
    inner = circle_piece(tr.trim_pieces(ents), 0, lambda m: m[0] > 2.05)
    res = tr.trim_apply(ents, inner["id"])
    lens = 2 * 100 * math.acos(0.6) - 6 * math.sqrt(400 - 144)
    union = 2 * math.pi * 100 - lens
    assert len(res["entities"]) == 1
    assert res["entities"][0]["kind"] == "path"
    assert area_of(res["entities"]) == pytest.approx(union, abs=0.2)


def test_trim_outer_boundary_is_refused():
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    outer = circle_piece(tr.trim_pieces([A, B]), 0, lambda m: m[0] < 1.95)
    with pytest.raises(ValueError, match="outer boundary"):
        tr.trim_apply([A, B], outer["id"])


def test_trim_whole_deletes_entity_and_hole_gesture():
    # far-away circle: whole-delete
    ents = [dict(RECT), {"kind": "circle", "mode": "add",
                         "x": 100, "y": 0, "r": 5}]
    whole = next(p for p in tr.trim_pieces(ents) if p["ent"] == 1)
    res = tr.trim_apply(ents, whole["id"])
    assert [e["kind"] for e in res["entities"]] == ["rectangle"]
    # a hole fully inside is also crossing-free: clicking it removes the hole
    holed = [dict(RECT), {"kind": "circle", "mode": "subtract",
                          "x": 0, "y": 0, "r": 4}]
    hw = next(p for p in tr.trim_pieces(holed) if p["ent"] == 1)
    res = tr.trim_apply(holed, hw["id"])
    assert area_of(res["entities"]) == pytest.approx(800, abs=0.1)


def test_untouched_entities_stay_parametric():
    """Only the overlapping CLUSTER is rebuilt as paths; a far-away rectangle
    and a hole inside it survive as their original parametric kinds."""
    far_rect = {"kind": "rectangle", "mode": "add", "x": 200, "y": 0,
                "w": 30, "h": 30}
    far_hole = {"kind": "circle", "mode": "subtract", "x": 200, "y": 0, "r": 5}
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    ents = [far_rect, far_hole, A, B]
    inner = circle_piece(tr.trim_pieces(ents), 2, lambda m: 2.05 < m[0] < 12)
    res = tr.trim_apply(ents, inner["id"])
    kinds = [(e["kind"], e["mode"]) for e in res["entities"]]
    assert ("rectangle", "add") in kinds and ("circle", "subtract") in kinds
    assert any(k == "path" for k, _ in kinds)


def test_cluster_rebuild_preserves_full_circles_as_circles():
    """A hole contained in the cluster (no outline crossing) is rebuilt as a
    parametric circle entity, not a path."""
    hole = {"kind": "circle", "mode": "subtract", "x": -10, "y": 0, "r": 3}
    bump = {"kind": "circle", "mode": "add", "x": 20, "y": 0, "r": 6}
    ents = [dict(RECT), hole, bump]                # bump crosses the rect edge
    seam = circle_piece(tr.trim_pieces(ents), 2, lambda m: m[0] < 19.95)
    res = tr.trim_apply(ents, seam["id"])
    circles = [e for e in res["entities"]
               if e["kind"] == "circle" and e["mode"] == "subtract"]
    assert len(circles) == 1
    assert circles[0]["r"] == pytest.approx(3, abs=1e-3)
    exp = 800 + math.pi * 36 / 2 - math.pi * 9    # rect + half bump - hole
    assert area_of(res["entities"]) == pytest.approx(exp, abs=0.5)


def test_result_feeds_extrude():
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    inner = circle_piece(tr.trim_pieces([A, B]), 0, lambda m: m[0] > 2.05)
    res = tr.trim_apply([A, B], inner["id"])
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, res["entities"]), 5)
    assert solid.volume == pytest.approx(area_of(res["entities"]) * 5, rel=1e-3)


def test_stale_piece_id_is_a_clear_error():
    with pytest.raises(ValueError, match="stale"):
        tr.trim_apply([dict(RECT)], "7:3")


# ------------------------------------------------------------- HTTP API --

def test_trim_endpoints_are_stateless_and_speak_errors():
    from fastapi.testclient import TestClient
    import studio
    client = TestClient(studio.app)
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    pieces = client.post("/api/sketch/trim/pieces",
                         json={"entities": ents}).json()["pieces"]
    assert len(pieces) == 4
    arc = circle_piece(pieces, 1, lambda m: m[0] < 19.95)
    out = client.post("/api/sketch/trim/apply",
                      json={"entities": ents, "piece": arc["id"]}).json()
    assert "error" not in out
    assert area_of(out["entities"]) == pytest.approx(800, abs=0.2)
    # errors arrive as {"error": ...} for the chat toast, never a 500
    bad = client.post("/api/sketch/trim/apply",
                      json={"entities": ents, "piece": "9:9"}).json()
    assert "stale" in bad["error"]
    empty = client.post("/api/sketch/trim/pieces",
                        json={"entities": []}).json()
    assert empty["pieces"] == [] and "error" in empty
