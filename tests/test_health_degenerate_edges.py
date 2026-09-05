"""inspector.health's closed-shell verdict must survive DEGENERATED edges — the
zero-length edges OCCT puts at a sphere's poles and at a cone's apex. A hexagon
revolved about its own side has two such apexes and is a closed solid; until
2026-09-05 only spheres were exempt from build123d's is_manifold flag, so that
correct solid was called an open shell (and so was every cone) while a sliver-
bearing sweep about an axis a few microns off the edge passed
(probes/revolve_face_probe.py §9)."""
import build123d as b3d
from build123d import Axis

import inspector
import sketch as sk


def hexagon():
    pts = [[30, 0], [15, 25.980762113533157], [-15, 25.980762113533157], [-30, 0],
           [-15, -25.980762113533157], [15, -25.980762113533157]]
    return sk.make_sketch(plane="XY", entities=[{"kind": "polygon", "points": pts}])


def test_a_cone_apex_on_the_axis_is_not_an_open_shell():
    s = hexagon()
    e = s.faces()[0].outer_wire().edges()[0]
    solid = sk._revolve(s, axis=Axis(e @ 0, (e @ 1) - (e @ 0)), revolution_arc=90)
    assert solid.is_manifold is False, "the build123d flag is the false negative this guards"
    assert solid.is_valid and len(solid.faces()) == 7
    assert inspector.health(solid) == []


def test_a_sphere_and_a_cone_pass_and_a_truly_open_shell_still_fails():
    assert inspector.health(b3d.Solid.make_sphere(10)) == []
    assert inspector.health(b3d.Solid.make_cone(10, 0, 10)) == []   # a real apex, closed
    box = b3d.Solid.make_box(10, 10, 10)
    open_shell = b3d.Shell(box.faces()[:-1])                        # one face missing
    assert any("not manifold" in p for p in inspector.health(open_shell))


def test_measure_and_health_give_one_answer_about_watertightness():
    """MCP verify_step reads measure()['is_manifold']; the tree reads health().
    Both must come from the same census, or one caller calls a cone apex broken."""
    s = hexagon()
    e = s.faces()[0].outer_wire().edges()[0]
    solid = sk._revolve(s, axis=Axis(e @ 0, (e @ 1) - (e @ 0)), revolution_arc=90)
    assert inspector.measure(solid)["is_manifold"] is True
    assert inspector.health(solid) == []


def test_a_fillet_pinched_to_a_point_is_still_a_defect():
    """The boundary of the exemption: a fillet larger than the corner it wraps
    pinches its BSPLINE face to a degenerated edge. OCCT calls the result
    valid and closed; the Fillet tool relies on health to refuse it, so only
    cone / sphere / revolution apexes are excused — never a spline's."""
    import blocks
    rc = blocks.fillet_edges(b3d.Solid.make_box(40, 30, 20), 5, "vertical")
    rim = [blocks.edge_ref(rc, e) for e in rc.edges() if abs(e.center().Z - 20) < 1e-6]
    pinched = blocks._b3d_fillet(blocks.edges_for(rc, rim), radius=6)
    assert pinched.is_valid, "OCCT itself does not object — that is why health must"
    assert any("not manifold" in p for p in inspector.health(pinched, check_valid=False))
