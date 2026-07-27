"""E1 operation set: transforms, patterns, fillet/chamfer/shell."""
import pytest

import blocks
import inspector
from document import Document, KNOWN_OPS


def test_rotate_lays_cylinder_on_its_side():
    wheel = blocks.rotate(blocks.disc(10, 4), "X", 90)
    size = inspector.measure(wheel)["size"]
    assert size[1] == pytest.approx(4, abs=0.01)     # thickness now along Y
    assert size[2] == pytest.approx(20, abs=0.01)    # diameter upright


def test_mirror_flips_position():
    from build123d import Pos
    part = Pos(20, 0, 0) * blocks.disc(5, 2)
    m = blocks.mirror_copy(part, "YZ")
    assert inspector.measure(m)["com"][0] == pytest.approx(-20, abs=0.01)


def test_scale_volume_cubes():
    v1 = blocks.disc(10, 10).volume
    v2 = blocks.scale_uniform(blocks.disc(10, 10), 2).volume
    assert v2 == pytest.approx(8 * v1, rel=1e-3)


def test_linear_pattern_count_and_reach():
    row = blocks.linear_pattern(blocks.disc(5, 2), count=4, dx=30)
    m = inspector.measure(row)
    assert m["n_solids"] == 4                          # spaced -> separate
    assert m["size"][0] == pytest.approx(100, abs=0.1)  # 3*30 + 2*5


def test_fillet_chamfer_shrink_volume():
    box = blocks.plate(30, 20, 10)
    assert blocks.fillet_edges(box, 2, "all").volume < box.volume
    assert blocks.chamfer_edges(box, 2, "top").volume < box.volume
    assert inspector.health(blocks.fillet_edges(box, 2, "top")) == []


def test_shell_makes_container():
    cup = blocks.shell_out(blocks.disc(20, 30), 2, open_face="top")
    solid = blocks.disc(20, 30)
    assert cup.volume < 0.4 * solid.volume
    assert inspector.health(cup) == []


def test_shell_closed_hollow():
    h = blocks.shell_out(blocks.plate(30, 30, 30), 3, open_face="none")
    assert h.volume < blocks.plate(30, 30, 30).volume


def test_invalid_args_raise():
    with pytest.raises(ValueError):
        blocks.rotate(blocks.disc(5, 2), "Q", 90)
    with pytest.raises(ValueError):
        blocks.mirror_copy(blocks.disc(5, 2), "AB")
    with pytest.raises(ValueError):
        blocks.scale_uniform(blocks.disc(5, 2), 0)
    with pytest.raises(ValueError):
        blocks.fillet_edges(blocks.disc(5, 2), 1, "sideways")
    with pytest.raises(ValueError):
        blocks.shell_out(blocks.disc(5, 2), -1)


def test_new_ops_registered_in_document():
    assert {"rotate", "mirror", "scale", "linear_pattern",
            "fillet", "chamfer", "shell"} <= KNOWN_OPS


def test_new_ops_work_in_a_document_tree():
    doc = Document(name="toy-car-axle")
    doc.add("wheel", "disc", {"radius": 10, "thickness": 4})
    doc.add("wheel_up", "rotate", {"axis": "X", "angle_deg": 90},
            inputs=["wheel"])
    doc.add("axle_row", "linear_pattern", {"count": 2, "dx": 0, "dy": 40},
            inputs=["wheel_up"])
    doc.add("rounded", "fillet", {"radius": 1, "edges": "all"},
            inputs=["axle_row"])
    doc.spec = {"n_solids": 2}
    assert doc.rebuild(), doc.tree()
