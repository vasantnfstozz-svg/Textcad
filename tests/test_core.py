"""Core geometry stack: engine (layer 1), inspector (layer 2), blocks."""
import time

import engine
import inspector
import blocks


# ---------------------------------------------------------------- engine ----

GOOD = """
with BuildPart() as p:
    Cylinder(radius=50, height=10)
    with PolarLocations(radius=38, count=6):
        Hole(radius=4)
result = p
"""

BROKEN_API = """
with BuildPart() as p:
    Cylinder(radius=50, height=10)
    p.part.is_valid()          # property, not method
result = p
"""

EMPTY_BOOLEAN = """
with BuildPart() as p:
    Box(10, 10, 10)
    Box(50, 50, 50, mode=Mode.SUBTRACT)
result = p
"""


def test_engine_accepts_good_script(tmp_path):
    r = engine.run_script(GOOD, step_path=str(tmp_path / "good.step"))
    assert r.ok and r.stage == "ok" and r.volume > 0


def test_engine_catches_broken_api():
    r = engine.run_script(BROKEN_API)
    assert not r.ok and r.stage == "exec" and "TypeError" in r.error


def test_engine_catches_empty_geometry():
    r = engine.run_script(EMPTY_BOOLEAN)
    assert not r.ok and r.stage == "geometry"


def test_engine_requires_result_variable():
    r = engine.run_script("x = 1")
    assert not r.ok and "result" in r.error


def test_engine_extra_globals_exposes_blocks(tmp_path):
    r = engine.run_script("result = disc(20, 5)",
                          step_path=str(tmp_path / "d.step"),
                          extra_globals=blocks.EXPORTS)
    assert r.ok


# ------------------------------------------------------------- inspector ----

def test_health_passes_good_solid():
    assert inspector.health(blocks.disc(20, 5)) == []


def test_health_fails_sphereless_open_or_empty():
    from build123d import BuildPart, Box, Mode
    with BuildPart() as p:
        Box(10, 10, 10)
        Box(50, 50, 50, mode=Mode.SUBTRACT)
    assert inspector.health(p) != []


def test_sphere_manifold_false_negative_is_tolerated():
    # build123d 0.11 flags sphere-bearing solids as non-manifold; health must not
    assert inspector.health(blocks.ball(10)) == []


def test_symmetry_detection():
    flange6 = blocks.with_bolt_circle(blocks.disc(50, 10), 6, 4, 76)
    assert inspector.is_rotationally_symmetric(flange6, 6)
    assert not inspector.is_rotationally_symmetric(flange6, 5)


def test_verify_catches_wrong_hole_count():
    flange5 = blocks.with_bolt_circle(blocks.disc(50, 10), 5, 4, 76)
    spec = inspector.Spec(holes={4.0: 6}, tol=0.5)
    fails = inspector.verify(flange5, spec)
    assert any("holes" in f for f in fails)


def test_verify_tip_radius():
    spec = inspector.Spec(tip_radius=50.0, tol=0.5)
    assert inspector.verify(blocks.disc(50, 10), spec) == []
    assert inspector.verify(blocks.disc(40, 10), spec) != []


def test_spec_from_dict_roundtrip():
    s = inspector.spec_from_dict(
        {"size": [100, 100, None], "holes": {"4": 6}, "symmetry": 6})
    assert s.size == (100, 100, None)
    assert s.holes == {4.0: 6}


# ----------------------------------------------------------------- blocks ----

def test_every_block_is_healthy():
    cases = [
        blocks.plate(40, 30, 5),
        blocks.disc(20, 8),
        blocks.ball(15),
        blocks.cone(20, 8, 25),
        blocks.tube(20, 12, 6),
        blocks.polygon_plate(5, 25, 8),
        blocks.hex_plate(30, 8),
        blocks.revolve_profile([(0, 0), (30, 0), (30, 6), (18, 12), (0, 12)]),
        blocks.curved_blade(10, 40, 25, 55, 20, 2.5),
        blocks.with_center_hole(blocks.disc(20, 8), 6),
        blocks.with_bolt_circle(blocks.disc(50, 10), 6, 4, 76),
        blocks.polar_pattern(blocks.curved_blade(10, 40, 25, 55, 20, 2.5), 5),
    ]
    for part in cases:
        assert inspector.health(part) == [], f"unhealthy: {part}"


def test_curved_blade_tip_radius_exact():
    blade = blocks.curved_blade(10, 40, 25, 55, 20, 2.5)
    assert abs(inspector.measure(blade)["max_radius"] - 40.0) < 0.01


def test_polar_pattern_symmetry_by_construction():
    part = blocks.polar_pattern(blocks.curved_blade(10, 40, 25, 55, 20, 2.5), 7)
    assert inspector.is_rotationally_symmetric(part, 7)


def test_block_input_validation():
    import pytest
    with pytest.raises(ValueError):
        blocks.tube(10, 12, 5)          # inner >= outer
    with pytest.raises(ValueError):
        blocks.polar_pattern(blocks.disc(5, 2), 0)
    with pytest.raises(ValueError):
        blocks.curved_blade(40, 10, 25, 55, 20, 2.5)   # inner >= outer


# ---------------------------------------------------------------------------
# The symmetry proof must never be unbounded work (2026-09-12: one plate
# added beside the 24-rib bottle cap made the spec check's boolean run for
# 22 minutes and take 44 GB, and a 16 GB laptop died)
# ---------------------------------------------------------------------------

_BOTTLE_CAP = [   # designs/bottle_cap_28mm as data: revolve + 24 ribs, fused
    {"id": "cap_shell", "op": "revolve_profile", "inputs": [],
     "params": {"points": [[0, 22], [19, 22], [20.5, 20], [20.5, 0], [17, 0], [17, 19.5], [0, 19.5]]}},
    {"id": "grip_rib", "op": "plate", "inputs": [], "params": {"width": 2, "depth": 3, "thickness": 20}},
    {"id": "rib_placed", "op": "move", "inputs": ["grip_rib"], "params": {"x": 20.5, "y": 0, "z": 10}},
    {"id": "rib_ring", "op": "polar_pattern", "inputs": ["rib_placed"], "params": {"count": 24}},
    {"id": "cap", "op": "fuse", "inputs": ["cap_shell", "rib_ring"], "params": {}},
]


def _bottle_cap():
    import document
    doc = document.Document.from_data({"name": "cap", "features": _BOTTLE_CAP})
    assert doc.rebuild(), [f.problems for f in doc.features]
    return doc.result_shape()


def test_a_stray_plate_beside_a_symmetric_part_fails_the_gates_before_any_boolean(monkeypatch):
    """The exact geometry that ate the box: the cap, a cylinder in its
    cavity and a 67.9 x 16.9 plate through everything, asked for 24-fold.
    The bounding-box gate answers in milliseconds; the boolean is never run."""
    import build123d as b3d
    cap = _bottle_cap()
    cyl = b3d.Cylinder(8.3, 7.2, align=(b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN))
    plate = b3d.Box(67.9, 16.9, 6.4)
    comp = b3d.Compound([cap, cyl, plate])

    def never(*_a, **_k):
        raise AssertionError("the boolean ran on a shape the gates should have refused")
    monkeypatch.setattr(inspector, "_rotation_residual", never)
    t0 = time.perf_counter()
    assert not inspector.is_rotationally_symmetric(comp, 24)
    assert time.perf_counter() - t0 < 10, "the gates themselves are slow"
    # a wrong order on the cap alone: the box is round enough to pass the
    # extent gate, the rib corners land off the part — still no boolean
    assert not inspector.is_rotationally_symmetric(cap, 23)


def test_the_gates_let_a_true_symmetry_through_to_the_proof():
    """Passing the gates is necessary, not sufficient: the boolean still
    decides. A pocket at +X on a 2-fold candidate keeps the bounding box and
    every rotated vertex lands on or inside the part, so both gates pass and
    only the boolean can say no. And a symmetric compound whose members
    OVERLAP (the cap with a disc through its wall) is still proven, without
    the clean pass, in well under a second per op."""
    import build123d as b3d
    cap = _bottle_cap()
    assert inspector.is_rotationally_symmetric(cap, 24)
    disc = b3d.Cylinder(25, 5, align=(b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN))
    assert inspector.is_rotationally_symmetric(b3d.Compound([cap, disc]), 24)
    bar = b3d.Box(40, 20, 5)
    pocket = b3d.Pos(12, 0, 2) * b3d.Box(6, 6, 2)      # 1.5 mm deep into the top face
    assert inspector.is_rotationally_symmetric(bar, 2)
    assert inspector._rotation_keeps_extent(bar - pocket, (bar - pocket).rotate(b3d.Axis.Z, 180), 0.04)
    assert inspector._rotation_keeps_vertices(bar - pocket, (bar - pocket).rotate(b3d.Axis.Z, 180), 0.04)
    assert not inspector.is_rotationally_symmetric(bar - pocket, 2)
