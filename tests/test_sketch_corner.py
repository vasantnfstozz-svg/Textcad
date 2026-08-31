"""Editable path-arc radii (sketch_corner.py).

Reported (2026-08-31): "if I want to edit this curve dia to smaller or
bigger, how to do that ... it should be there in the tree, wherever we have
a curve." A path's curves are 3-point arcs — no radius is stored — so the
tree had nothing to edit. sketch_corner gives every arc a radius:
corner arcs re-fillet tangent to their neighbouring lines, free arcs
re-bulge between fixed endpoints. Verified against the real kernel: the
rewritten path must still build a valid face whose arc edge MEASURES the
asked-for radius (never trust, always measure).
"""
import math

import build123d as b3d
import pytest

import sketch as sk
import sketch_corner as sc


def rounded_rect():
    """40x30 rect drawn CCW from (-20,-15), ONE r5 round at corner (20,15)."""
    return {
        "kind": "path", "mode": "add", "start": [-20, -15],
        "segments": [
            {"type": "line", "to": [20, -15]},
            {"type": "line", "to": [20, 10]},
            {"type": "arc", "via": [18.5355, 13.5355], "to": [15, 15]},
            {"type": "line", "to": [-20, 15]},
        ],
    }


def measured_radii(entities):
    """Radii of every circular edge of the REBUILT face — kernel truth."""
    face = sk.make_sketch("XY", 0, entities)
    return sorted(round(e.radius, 3) for e in face.edges()
                  if e.geom_type == b3d.GeomType.CIRCLE)


def test_path_arcs_reports_the_corner_and_its_radius():
    arcs = sc.path_arcs(rounded_rect())
    assert len(arcs) == 1
    assert arcs[0]["segment"] == 2 and arcs[0]["kind"] == "corner"
    assert arcs[0]["r"] == pytest.approx(5, abs=1e-3)


def test_growing_a_corner_re_fillets_tangent():
    ents = sc.set_arc_radius([rounded_rect()], 0, 2, 8)
    seg = ents[0]["segments"]
    # tangent points slid ALONG the original lines: x=20 wall, y=15 top
    assert seg[1]["to"] == [20, 7]
    assert seg[2]["to"] == [12, 15]
    # the kernel measures the new round at exactly r8
    assert measured_radii(ents) == [8.0]
    # and the area shrank by exactly the corner nibble: r^2 - pi r^2/4
    face = sk.make_sketch("XY", 0, ents)
    assert face.area == pytest.approx(1200 - (64 - math.pi * 16), abs=1e-2)


def test_shrinking_a_corner_works_too():
    ents = sc.set_arc_radius([rounded_rect()], 0, 2, 2)
    assert measured_radii(ents) == [2.0]
    assert ents[0]["segments"][1]["to"] == [20, 13]


def test_too_big_a_radius_is_refused_with_the_limit():
    """r=40 would eat past the neighbouring edges of a 40x30 rectangle."""
    with pytest.raises(ValueError, match="does not fit"):
        sc.set_arc_radius([rounded_rect()], 0, 2, 40)


def test_free_arc_keeps_its_endpoints_and_hits_the_radius():
    """Two arcs back to back: neither has straight neighbours, so a radius
    edit must keep the endpoints and only change the bulge."""
    lens = {
        "kind": "path", "mode": "add", "start": [0, 0],
        "segments": [
            {"type": "arc", "via": [10, 4], "to": [20, 0]},
            {"type": "arc", "via": [10, -4], "to": [0, 0]},
        ],
    }
    out = sc.set_arc_radius([lens], 0, 0, 30)
    assert out[0]["start"] == [0, 0]
    assert out[0]["segments"][0]["to"] == [20, 0]
    arcs = sc.path_arcs(out[0])
    assert arcs[0]["r"] == pytest.approx(30, abs=1e-2)
    assert arcs[1]["r"] == pytest.approx(14.5, abs=1e-2)   # untouched
    assert 30.0 in measured_radii(out)


def test_free_arc_radius_below_half_chord_is_refused():
    lens = {"kind": "path", "start": [0, 0],
            "segments": [{"type": "arc", "via": [10, 4], "to": [20, 0]},
                         {"type": "arc", "via": [10, -4], "to": [0, 0]}]}
    with pytest.raises(ValueError, match="at least"):
        sc.set_arc_radius([lens], 0, 0, 3)


def test_corner_arc_that_starts_the_path_moves_the_start_point():
    """Arc as segment 0: its incoming edge is the auto-close line, so the
    re-fillet must move the entity's `start`, and the loop stays closed."""
    p = {
        "kind": "path", "mode": "add", "start": [15, -15],
        "segments": [
            {"type": "arc", "via": [18.5355, -13.5355], "to": [20, -10]},
            {"type": "line", "to": [20, 15]},
            {"type": "line", "to": [-20, 15]},
            {"type": "line", "to": [-20, -15]},
        ],
    }
    out = sc.set_arc_radius([p], 0, 0, 8)
    assert out[0]["start"] == [12, -15]
    assert out[0]["segments"][0]["to"] == [20, -7]
    assert measured_radii(out) == [8.0]


def test_wrong_targets_are_clear_errors():
    with pytest.raises(ValueError, match="not a path"):
        sc.set_arc_radius([{"kind": "circle", "r": 5}], 0, 0, 2)
    with pytest.raises(ValueError, match="not an arc"):
        sc.set_arc_radius([rounded_rect()], 0, 0, 2)
    with pytest.raises(ValueError, match="positive"):
        sc.set_arc_radius([rounded_rect()], 0, 2, -1)


def test_input_entities_are_not_mutated():
    ents = [rounded_rect()]
    before = str(ents)
    sc.set_arc_radius(ents, 0, 2, 8)
    assert str(ents) == before
