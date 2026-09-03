"""Revolve × the gauntlet corpus (CLAUDE.md rule 4: an operation is the feature
TIMES the geometry).

A sketch on every flat face of every nasty-but-legal body in tests/gauntlet.py
— fused taper seams, DPrism bosses, BSPLINE-typed flat walls — revolved about
both of its plane's axes, a quarter turn and a full turn. The contract is
assert_op's: a healthy solid or a friendly ValueError, never a kernel exception
and never an invalid "success". The rectangle sits OFF the face centre, so one
axis clears it (must build) and the other cuts through it (must refuse with a
sentence): both paths run on every face.
"""
import pytest

import sketch as sk
from tests.gauntlet import BODIES, assert_op, planar_faces


def _sketch_on(solid, center, normal):
    return sk.sketch_on_face(solid, face_center=center, face_normal=normal,
                             entities=[{"kind": "rectangle", "w": 4, "h": 3,
                                        "x": 6, "y": 0, "mode": "add"}])


@pytest.mark.parametrize("name", sorted(BODIES))
def test_revolving_a_sketch_on_every_flat_face_builds_or_refuses_friendly(name):
    solid = BODIES[name]()
    faces = planar_faces(solid)
    assert faces, name
    built = refused = 0
    for idx, _face, center, normal in faces:
        prof = _sketch_on(solid, center, normal)
        for axis in ("v", "u"):
            for angle in (90, 360):
                r = assert_op(f"{name}.f{idx} axis={axis} angle={angle}",
                              lambda: sk.revolve_sketch(prof, axis=axis, angle=angle))
                if r is None:
                    refused += 1
                else:
                    built += 1
    assert built > 0, f"{name}: nothing revolved on any face"
    assert refused > 0, f"{name}: the axis through the profile was never refused"
