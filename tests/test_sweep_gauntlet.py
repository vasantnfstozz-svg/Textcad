"""Sweep × the gauntlet corpus (CLAUDE.md rule 4: an operation is the feature
TIMES the geometry).

A circle sketched on every flat face of every nasty-but-legal body in
tests/gauntlet.py — fused taper seams, DPrism bosses, BSPLINE-typed flat walls
— swept along an L path that leaves the face along its normal and turns 90°.
The contract is assert_op's: a healthy solid or a friendly ValueError, never a
kernel exception and never an invalid "success". Where it builds, the volume
is the circle's area times the path's length (Pappus), to 1e-6.
"""
import math

import build123d as b3d
import pytest

import sketch as sk
from tests.gauntlet import BODIES, assert_op, planar_faces

R = 2.0
UP, OUT = 15.0, 10.0


def _sketch_on(solid, center, normal):
    return sk.sketch_on_face(solid, face_center=center, face_normal=normal,
                             entities=[{"kind": "circle", "r": R, "x": 0, "y": 0,
                                        "mode": "add"}])


def _path_from(centre, normal):
    """An L in world space: from the profile's centre along the face normal,
    then 90° along an in-plane direction — as a path sketch carries it."""
    n = b3d.Vector(*normal).normalized()
    side = n.cross(b3d.Vector(0, 0, 1))
    if side.length < 1e-6:
        side = n.cross(b3d.Vector(1, 0, 0))
    side = side.normalized()
    a = b3d.Vector(*centre)
    b = a + n * UP
    c = b + side * OUT
    wire = b3d.Wire([b3d.Edge.make_line(a, b), b3d.Edge.make_line(b, c)])
    ps = b3d.Sketch(children=list(wire.edges()))
    ps._tc_paths = [wire]
    return ps


@pytest.mark.parametrize("name", sorted(BODIES))
def test_sweeping_a_circle_off_every_flat_face_builds_or_refuses_friendly(name):
    solid = BODIES[name]()
    faces = planar_faces(solid)
    assert faces, name
    built = refused = 0
    for idx, _face, center, normal in faces:
        prof = _sketch_on(solid, center, normal)
        # the path leaves along the PROFILE's normal — a face sketch's plane
        # is the principal plane its face snaps to (face_sketch_plane), so on
        # a wall tapered 8° the face normal is 8° off the profile and the
        # section would be carried at a slant (A·L·cos 8°, measured 311.12
        # against 314.16 on fused_taper_seam.f6): a user's path sketch lies
        # in a perpendicular principal plane, exactly this
        path = _path_from(prof.center(), list(sk.sketch_plane_of(prof).z_dir))
        r = assert_op(f"{name}.f{idx}",
                      lambda: sk.sweep_sketch(prof, path="p", full=True, _path_sketch=path))
        if r is None:
            refused += 1
        else:
            built += 1
            assert r.volume == pytest.approx(math.pi * R * R * (UP + OUT), rel=1e-6), \
                f"{name}.f{idx}: {r.volume}"
    assert built > 0, f"{name}: nothing built ({refused} refused)"
