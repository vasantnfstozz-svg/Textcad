"""A tapered extrude lands on the SAME side of the face as the untapered one.

User, 2026-09-03 (screenshot): a rectangle tapered to its ridge, then one of
the wedge's tilted walls extruded — fine — then a taper on that extrude, and
"it goes to the opposite direction". Measured on the kernel: on the 45° walls
the untapered stub sat +2.50 mm OUTSIDE the body along the normal, a narrowing
taper put it -2.40 mm INSIDE, a flaring taper +2.59 outside.

Cause: build123d's Solid.extrude_taper uses OCCT's LocOpe_DPrism when the face
points upward, the taper narrows and the face has no holes; DPrism follows the
face's internal orientation, and a face made by an earlier taper is stored
REVERSED. sketch._taper_loft builds every tapered face extrude as a loft along
the explicit outward normal instead. Taper sign here is Fusion's: negative
narrows.
"""
import pytest

import inspector
import sketch as sk
from document import Document


def v(x):
    return [x.X, x.Y, x.Z]


def wedge():
    """rect 20x30 extruded 10 with a near-collapse narrowing taper: a roof whose
    four walls all lean 45° — the faces the user extruded."""
    d = Document(name="w")
    d.add("s", "sketch", {"plane": "XY", "entities": [{"kind": "rectangle", "w": 20, "h": 30}]}, [])
    d.add("e", "extrude", {"amount": 10, "taper": -44.9}, ["s"])
    d.rebuild()
    assert d.get("e").status == "ok", d.get("e").problems
    return d


def tilted_walls(solid):
    out = []
    for f in solid.faces():
        n = sk.face_plane(f).z_dir
        if abs(n.Z) < 0.9:                      # the four leaning walls
            out.append((f, n))
    assert len(out) == 4
    return out


def side_of(stub, face, normal):
    """signed distance of the stub's centre from the face, along its outward
    normal: positive = outside the body, negative = inside"""
    return (stub.center() - face.center()).dot(normal)


@pytest.mark.parametrize("taper", [0.0, -10.0, 10.0])
def test_every_tilted_wall_extrudes_outward_whatever_the_taper(taper):
    d = wedge()
    body = d._parts["e"]
    for face, n in tilted_walls(body):
        stub = sk.extrude_face(body, v(face.center()), v(n), amount=5, taper=taper)
        assert not inspector.health(stub), inspector.health(stub)
        s = side_of(stub, face, n)
        assert s > 1.5, (f"taper {taper}: stub centre {s:+.2f} along the outward "
                         f"normal of wall {v(n)} — it went the wrong way")


def test_flip_sends_the_tapered_stub_inside_on_every_tilted_wall():
    d = wedge()
    body = d._parts["e"]
    for face, n in tilted_walls(body):
        for taper in (0.0, -10.0, 10.0):
            stub = sk.extrude_face(body, v(face.center()), v(n), amount=5, taper=taper, flip=True)
            assert side_of(stub, face, n) < -1.5, (taper, v(n))


def test_narrowing_removes_and_flaring_adds_material_on_a_tilted_wall():
    d = wedge()
    body = d._parts["e"]
    face, n = tilted_walls(body)[0]
    plain = sk.extrude_face(body, v(face.center()), v(n), amount=5)
    narrow = sk.extrude_face(body, v(face.center()), v(n), amount=5, taper=-10)
    flare = sk.extrude_face(body, v(face.center()), v(n), amount=5, taper=10)
    assert narrow.volume < plain.volume < flare.volume


def test_a_face_sketch_on_a_tilted_wall_tapers_on_the_same_side_too():
    d = wedge()
    body = d._parts["e"]
    face, n = tilted_walls(body)[0]
    d.add("fs", "sketch_on_face", {"face_center": v(face.center()), "face_normal": v(n),
                                   "entities": [{"kind": "circle", "r": 2}]}, ["e"])
    d.rebuild()
    assert d.get("fs").status == "ok", d.get("fs").problems
    profile = d._parts["fs"]
    plain = sk.extrude_sketch(profile, 4)
    narrow = sk.extrude_sketch(profile, 4, taper=-15)
    # both stubs on the same side of the sketch plane (the plan's axis)
    pl_z = sk.face_sketch_plane(face).z_dir
    for stub in (plain, narrow):
        assert (stub.center() - face.center()).dot(pl_z) > 1.0, stub.center()
    assert narrow.volume < plain.volume


def test_the_box_top_still_grows_a_narrowing_boss_upward():
    """the case DPrism used to handle — the loft must give the same answer"""
    d = Document(name="b")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20}, [])
    d.rebuild()
    body = d._parts["b"]
    plain = sk.extrude_face(body, [0, 0, 10], [0, 0, 1], amount=8)
    narrow = sk.extrude_face(body, [0, 0, 10], [0, 0, 1], amount=8, taper=-20)
    assert narrow.bounding_box().max.Z == pytest.approx(18, abs=1e-3)
    assert narrow.bounding_box().min.Z == pytest.approx(10, abs=1e-3)
    assert narrow.volume < plain.volume
    assert not inspector.health(narrow)
    # the top of the boss is the offset rectangle: 60-2*8*tan20 by 40-2*8*tan20
    import math
    top_w = 60 - 2 * 8 * math.tan(math.radians(20))
    assert narrow.volume == pytest.approx(8 * (60 * 40 + top_w * (40 - 2 * 8 * math.tan(math.radians(20)))
                                               + math.sqrt(60 * 40 * top_w * (40 - 2 * 8 * math.tan(math.radians(20))))) / 3,
                                          rel=1e-3)          # frustum volume
