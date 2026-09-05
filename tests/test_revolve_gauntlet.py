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
import build123d as b3d
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


@pytest.mark.parametrize("name", sorted(BODIES))
def test_revolving_every_flat_face_about_each_of_its_straight_edges_builds_or_refuses_friendly(name):
    """P3b: the face ITSELF is the profile (revolve_face) and each of its
    straight edges the axis — a quarter turn each, a full turn about the
    longest. Every corpus body, every flat face: tilted DPrism walls whose true
    plane is not a principal one, BSPLINE-typed seam edges, faces with holes."""
    solid = BODIES[name]()
    faces = planar_faces(solid)
    assert faces, name
    built = refused = tried = 0
    for idx, face, center, normal in faces:
        prof = sk._on_plane(b3d.Sketch([face]), sk.face_profile_plane(face))
        for k, (p, q) in enumerate(sk.revolve_edge_lines(prof)):
            for angle in ((90, 360) if k == 0 else (90,)):
                tried += 1
                r = assert_op(f"{name}.f{idx} edge={k} angle={angle}",
                              lambda: sk.revolve_face(solid, center, normal,
                                                      axis=[list(p), list(q)], angle=angle))
                if r is None:
                    refused += 1
                else:
                    built += 1
    assert built > 0 or tried == 0, f"{name}: no face revolved about any of its edges"
    if name == "l_bracket":       # a reflex corner: some side's line cuts through the face
        assert refused > 0, "an edge the face straddles must be refused with a sentence"
