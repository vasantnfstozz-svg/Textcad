"""THE SHELL GAUNTLET (tests/gauntlet.py): every corpus body, every flat face as
the one opening, Inside and Outside at t = 2; a closed hollow; the top face
plus each other flat face as a pair. A healthy solid or a sentence, never a raw
kernel error; every face of the plain box must build every one of them
(allow_failure=False). Every CURVED face is refused with its type in the
sentence — the kernel cannot offset a solid with a curved opening.
"""
import pytest

import sketch as sk
from tests.gauntlet import BODIES, assert_op, planar_faces


def ref(c, n):
    return {"center": list(c), "normal": list(n)}


@pytest.mark.parametrize("body", sorted(BODIES))
def test_every_flat_face_is_an_opening_or_says_why(body):
    solid = BODIES[body]()
    strict = body == "box"                 # the easy case must never refuse
    faces = planar_faces(solid)
    built = 0
    for idx, _face, c, n in faces:
        for direction in ("inside", "outside"):
            out = assert_op(f"{body}.f{idx} {direction} t=2",
                            lambda c=c, n=n, direction=direction: sk.shell(
                                solid, 2, [ref(c, n)], direction),
                            allow_failure=not strict)
            if out is not None:
                built += 1
                assert out.volume < solid.volume if direction == "inside" else True
    assert built > 0, f"{body}: no face could be an opening"
    out = assert_op(f"{body} closed hollow t=2", lambda: sk.shell(solid, 2),
                    allow_failure=not strict)
    if out is not None:
        assert len(out.solids()) == 1 and out.volume < solid.volume


@pytest.mark.parametrize("body", sorted(BODIES))
def test_the_top_face_pairs_with_every_other_flat_face(body):
    solid = BODIES[body]()
    strict = body == "box"
    faces = planar_faces(solid)
    top = max(faces, key=lambda r: r[2][2])
    for idx, _face, c, n in faces:
        if idx == top[0]:
            continue
        assert_op(f"{body}.f{top[0]}+f{idx} inside t=2",
                  lambda c=c, n=n: sk.shell(solid, 2, [ref(top[2], top[3]), ref(c, n)]),
                  allow_failure=not strict)


def test_every_curved_face_is_refused_with_its_type():
    seen = 0
    for body, mk in BODIES.items():
        solid = mk()
        for f in solid.faces():
            if sk.face_plane(f) is not None:
                continue
            c = f.center()
            with pytest.raises(ValueError, match="FLAT face") as e:
                sk.shell(solid, 2, [{"center": [c.X, c.Y, c.Z], "normal": None}])
            assert "curved" in str(e.value), f"{body}: {e.value}"
            seen += 1
    assert seen > 0
