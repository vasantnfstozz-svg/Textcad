"""Click-to-place primitive defaults must produce healthy solids. These mirror
DEFAULTS in static/js/placement.js — keep them in sync (a bad default like a
zero-radius cone or inner>=outer tube would fail the moment a user clicks)."""
import pytest

from document import Document

# mirror of placement.js DEFAULTS
PLACEMENT_DEFAULTS = {
    "plate": {"width": 40, "depth": 40, "thickness": 10},
    "disc": {"radius": 20, "thickness": 10},
    "tube": {"outer_radius": 20, "inner_radius": 10, "height": 30},
    "hex_plate": {"across_flats": 30, "thickness": 10},
}


@pytest.mark.parametrize("op,params", PLACEMENT_DEFAULTS.items())
def test_placement_default_builds_healthy(op, params):
    doc = Document(name=f"place-{op}")
    doc.add("p", op, params)
    assert doc.rebuild(), [f.problems for f in doc.features]
    assert doc.get("p").status == "ok"
    assert doc.get("p").volume and doc.get("p").volume > 0


def test_placement_then_move_positions_center():
    """click-to-place = create at origin + a move to the clicked point."""
    doc = Document(name="place-move")
    doc.add("disc1", "disc", {"radius": 20, "thickness": 10})
    doc.add("disc1_at", "move", {"x": 30, "y": -10, "z": 0}, inputs=["disc1"])
    assert doc.rebuild()
    bb = doc.result().bounding_box()
    cx = (bb.min.X + bb.max.X) / 2
    cy = (bb.min.Y + bb.max.Y) / 2
    assert cx == pytest.approx(30, abs=1e-6)
    assert cy == pytest.approx(-10, abs=1e-6)
