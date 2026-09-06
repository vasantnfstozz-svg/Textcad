"""The Pattern gauntlet (LAUNCH-PLAN.md rule 4 — an operation is the feature
TIMES the geometry): a ⌀3 through hole a quarter-span from the centre of EVERY
flat face of every corpus body, then a circular pattern of 3 and 5 copies
about that face's own axis and a rectangular pattern of 3 along the face's x.
Each must come back a healthy solid or a sentence — never a raw kernel error,
never a broken "success". Every face of the plain box must build (a copy that
leaves a pentagon face or an L-bracket's arm may be refused: that IS the
sentence — probes/pattern_probe.py §11)."""
import pytest
from build123d import Vector

import pattern
import sketch as sk
from tests.gauntlet import BODIES, planar_faces, assert_op


def seeded(name):
    """(body, [(face index, the body WITH the seed hole, the face's axis in
    stored form, the face's x, the face's span)]) for every flat face"""
    solid = BODIES[name]()
    cases = []
    for idx, face, _centre, normal in planar_faces(solid):
        pl = sk.face_profile_plane(face)
        bb = face.bounding_box()
        span = min(s for s in (bb.size.X, bb.size.Y, bb.size.Z) if s > 1e-6)
        c = pl.to_local_coords(face.center())          # a quarter-span from the FACE centre
        at = Vector(c.X + span * 0.25, c.Y, 0)         # (the frame's origin is the world's foot)
        try:
            holed = sk.hole(solid, face_center=list(face.center()), face_normal=list(normal),
                            at=[at.X, at.Y], diameter=3, depth=1, through=True)
        except ValueError:
            continue                # a hole this face refuses is Hole's own gauntlet's business
        cases.append((idx, holed, pattern.stored_face(holed, face), list(pl.x_dir), span))
    return solid, cases


@pytest.mark.parametrize("name", sorted(BODIES))
def test_a_circular_pattern_of_a_hole_on_every_flat_face(name):
    solid, cases = seeded(name)
    assert cases, f"{name}: no flat face took a hole"
    for idx, holed, axis, _u, _span in cases:
        for n in (3, 5):
            assert_op(f"{name}.f{idx} circular n={n}",
                      lambda: pattern.polar_pattern(holed, n, axis=axis, seed="h",
                                                    _before=solid, _after=holed),
                      allow_failure=name != "box")


@pytest.mark.parametrize("name", sorted(BODIES))
def test_a_rectangular_pattern_of_a_hole_on_every_flat_face(name):
    solid, cases = seeded(name)
    for idx, holed, _axis, u, span in cases:
        assert_op(f"{name}.f{idx} rectangular",
                  lambda: pattern.linear_pattern(holed, 3, direction=u, distance=-span * 0.2,
                                                 seed="h", _before=solid, _after=holed),
                  allow_failure=name != "box")
