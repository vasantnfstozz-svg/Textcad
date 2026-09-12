"""The Mirror gauntlet (LAUNCH-PLAN.md rule 4 — an operation is the feature
TIMES the geometry): a ⌀3 through hole a quarter-span from the centre of EVERY
flat face of every corpus body, mirrored across each of the body's three
mid-planes and across the face's own plane; and every BODY mirrored (joined)
across each of its flat faces and each mid-plane. Each must come back a
healthy solid or a sentence — never a raw kernel error, never a broken
"success". An image that is the seed itself (the hole lies in the mid-plane)
or lands off the body (across the face it was drilled from) is refused by
number: that IS the sentence (probes/mirror_probe.py §3, §4, §10)."""
import pytest

import pattern
from tests.gauntlet import BODIES, holed_faces, planar_faces, assert_op

MIDS = ({"mid": "X"}, {"mid": "Y"}, {"mid": "Z"})


@pytest.mark.parametrize("name", sorted(BODIES))
def test_a_mirror_of_a_hole_on_every_flat_face(name):
    solid, cases = holed_faces(name)
    assert cases, f"{name}: no flat face took a hole"
    built = 0
    for idx, face, holed, _span in cases:
        for plane in (*MIDS, pattern.stored_face(holed, face)):
            out = assert_op(f"{name}.f{idx} mirror across {plane}",
                            lambda: pattern.mirror(holed, plane, seed="h",
                                                   _before=solid, _after=holed))
            built += out is not None
    assert built, f"{name}: no plane put a mirror image on any face"


@pytest.mark.parametrize("name", sorted(BODIES))
def test_a_body_joined_with_its_reflection_across_every_face_and_mid_plane(name):
    solid = BODIES[name]()
    for idx, face, _centre, _normal in planar_faces(solid):
        stored = pattern.stored_face(solid, face)
        # the ONE legal refusal: a part-ball joined with its reflection through
        # its own centre SEGFAULTS the kernel (the clipped ball across its flat
        # face, 2026-09-12) — the product refuses it by the same rule asked here
        pl, _ = pattern.plane_of(solid, stored, "mirror")
        part_ball = pattern._part_ball_through(solid, pl) is not None
        assert_op(f"{name}.f{idx} body across its face",
                  lambda: pattern.mirror(solid, stored, join=True),
                  allow_failure=part_ball)
    for plane in MIDS:                    # an asymmetric body grows, a symmetric one is itself
        assert_op(f"{name} body across {plane}",
                  lambda: pattern.mirror(solid, plane, join=True), allow_failure=False)
