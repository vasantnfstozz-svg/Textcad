"""The Pattern gauntlet (LAUNCH-PLAN.md rule 4 — an operation is the feature
TIMES the geometry): a ⌀3 through hole a quarter-span from the centre of EVERY
flat face of every corpus body, then a circular pattern of 3 and 5 copies
about that face's own axis and a rectangular pattern of 3 along the face's x.
Each must come back a healthy solid or a sentence — never a raw kernel error,
never a broken "success". Every face of the plain box must build (a copy that
leaves a pentagon face or an L-bracket's arm may be refused: that IS the
sentence — probes/pattern_probe.py §11)."""
import pytest

import pattern
import sketch as sk
from tests.gauntlet import BODIES, holed_faces, assert_op


def seeded(name):
    """(body, [(face index, the body WITH the seed hole, the face's axis in
    stored form, the face's x, the face's span)]) for every flat face"""
    solid, cases = holed_faces(name)
    return solid, [(idx, holed, pattern.stored_face(holed, face),
                    list(sk.face_profile_plane(face).x_dir), span)
                   for idx, face, holed, span in cases]


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
