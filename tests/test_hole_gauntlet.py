"""THE HOLE GAUNTLET (tests/gauntlet.py): every corpus body, every flat face, a
hole at the face's centre and one toward a vertex, plain / counterbore /
countersink, blind — and a through hole at the centre. A healthy solid or a
sentence, never a raw kernel error; every face of the plain box must build
every one of them (allow_failure=False), and every body must take at least one.
"""
import build123d as b3d
import pytest

import sketch as sk
from tests.gauntlet import BODIES, assert_op, planar_faces

KINDS = {"simple": {},
         "counterbore": dict(cbore_diameter=6, cbore_depth=1),
         "countersink": dict(csink_diameter=6, csink_angle=90)}


def points(face, c):
    """the face's centre and a point 70% of the way to its first vertex, in
    the face's own frame — the second one runs a seat over an edge on a small
    face, and lands INSIDE the bore of an annular face (a sentence, not a crash)"""
    pl = sk.face_profile_plane(face)
    v0 = b3d.Vector(*tuple(face.vertices()[0]))
    return [pl.to_local_coords(p) for p in (c, c + (v0 - c) * 0.7)]


@pytest.mark.parametrize("body", sorted(BODIES))
def test_every_flat_face_takes_a_hole_or_says_why(body):
    solid = BODIES[body]()
    strict = body == "box"                 # the easy case must never refuse
    built = 0
    for idx, face, c, n in planar_faces(solid):
        centre, near = points(face, b3d.Vector(*c))
        cases = [(centre, kind, False) for kind in KINDS] + \
                [(near, kind, False) for kind in KINDS] + [(centre, "simple", True)]
        for at, kind, through in cases:
            where = "centre" if at is centre else "near-vertex"
            label = f"{body}.f{idx} {kind} {where} through={through}"
            out = assert_op(label, lambda: sk.hole(
                solid, face_center=c, face_normal=n, at=[at.X, at.Y], diameter=3,
                depth=3, through=through, kind=kind, **KINDS[kind]),
                allow_failure=not strict)
            if out is not None:
                built += 1
                assert out.volume < solid.volume, label
    assert built > 0, f"{body}: no hole built on any face"
