"""Core geometry stack: engine (layer 1), inspector (layer 2), blocks."""
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
