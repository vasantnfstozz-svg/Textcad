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


# bodies the kernel cannot shell AT ALL — every route is a sentence (measured
# 2026-09-12, probes/shell_scaled_halfball_crash.py: the clipped ball at t = 2,
# 10 and 12, any opening, either direction, is "do not fit" or "nothing was
# hollowed"; at half its extent it used to SEGFAULT). If one of these ever
# builds, the kernel learned something: move it out of this set on purpose.
KERNEL_CANNOT_SHELL = {"clipped_ball"}


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
    if body in KERNEL_CANNOT_SHELL:
        assert built == 0, f"{body}: the kernel now shells it — take it out of KERNEL_CANNOT_SHELL"
    else:
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


# THE MULTI-LUMP CORNER of the gauntlet. The shared corpus is all ONE-lump
# bodies, which is how the same P0 got through twice: a lump that did not
# hollow is invisible to a WHOLE-BODY volume check as soon as a second, bigger
# lump pays for it. Shell reaches multi-lump bodies by one click (`bodyRow`),
# so every pair below is swept at every thickness, in both directions.
LUMP_PAIRS = {                              # a 20 x 20 x 10 boss beside...
    "equal":  (20.0, 20.0, 10.0),           # ...its twin (a linear_pattern)
    "narrow": (3.0, 20.0, 10.0),            # ...a rib the wall cannot fit across
    "flat":   (20.0, 20.0, 4.0),            # ...a pad the wall cannot fit down
    "wide":   (12.0, 20.0, 10.0),           # ...a smaller boss that fits fine
}


def concentric():
    """A post inside a ring: TWO lumps that share a bounding-box centre exactly
    — the shape that made round two's nearest-centre pairing refuse a shell the
    kernel had built perfectly (round three)."""
    import build123d
    return build123d.Part() + (build123d.Cylinder(20, 10) - build123d.Cylinder(15, 10))         + build123d.Cylinder(5, 10)


def two_lumps(size):
    import build123d
    return build123d.Part() + build123d.Box(20.0, 20.0, 10.0) \
        + build123d.Pos(40, 0, 0) * build123d.Box(*size)


def tops_of(body):
    return [ref(max((f for f in l.faces() if sk.face_plane(f) is not None),
                    key=lambda f: (round(f.center().Z, 6), f.area)).center(),
                [0, 0, 1]) for l in body.solids()]


def same_box(shape, box):
    return all(abs(a - b) <= 1e-6 for a, b in zip(sk._box6(shape), box))


@pytest.mark.parametrize("pair", sorted(LUMP_PAIRS))
@pytest.mark.parametrize("direction", ("inside", "outside"))
def test_no_lump_ever_comes_back_a_solid_block(pair, direction):
    """Every lump of the result must be walls, or the whole thing must be a
    sentence. A lump whose volume is unchanged is the P0's signature: the
    kernel handed it back raw and every whole-body check passed it green."""
    body = two_lumps(LUMP_PAIRS[pair])
    was = [(sk._box6(l), l.volume) for l in body.solids()]
    built = 0
    for t in (0.5, 1, 2, 3, 5, 6):
        out = assert_op(f"{pair} {direction} t={t}", lambda t=t: sk.shell(body, t, tops_of(body),
                                                                         direction))
        if out is None:
            continue                        # refused with a sentence: allowed
        built += 1
        # IDENTITY, not a volume drop: a lump that really hollows can come as
        # close as 0.992 of its input (an honest 4 x 4 x 2 cavity at t = 8),
        # while an untouched one matches at d(volume) 0.0 AND d(box) 0.0
        for lump in out.solids():
            for box, v in was:
                assert not (abs(lump.volume - v) <= 1e-6 and same_box(lump, box)), \
                    f"{pair} {direction} t={t}: a lump came back unchanged at {v:g} mm3"
        assert len(out.solids()) >= len(was), f"{pair} {direction} t={t}: a lump vanished"
    assert built > 0, f"{pair} {direction}: nothing built at any thickness"


def test_the_openings_guard_and_the_hollowed_guard_are_both_live():
    """The two halves, so neither can quietly stop firing: a lump with NO
    opening (round one) and a lump the wall does not fit (round two)."""
    body = two_lumps(LUMP_PAIRS["equal"])
    with pytest.raises(ValueError, match="separate lumps and 1 of them has no face open"):
        sk.shell(body, 2, [tops_of(body)[0]])
    thin = two_lumps(LUMP_PAIRS["narrow"])
    with pytest.raises(ValueError, match="do not fit 1 of the 2 separate lumps"):
        sk.shell(thin, 2, tops_of(thin))


@pytest.mark.parametrize("direction", ("inside", "outside"))
def test_concentric_lumps_are_never_refused_for_sharing_a_centre(direction):
    """A post inside a ring, over the thickness ladder: a refusal is allowed
    only when the kernel really could not do it, never because two lumps sit at
    the same place. Every built result must hollow BOTH lumps."""
    body = concentric()
    assert len({tuple(round(c, 6) for c in tuple(s.bounding_box().center()))
                for s in body.solids()}) == 1, "the lumps must share a centre"
    was = [(sk._box6(l), l.volume) for l in body.solids()]
    built = 0
    for t in (0.25, 0.5, 1, 1.5, 2):
        out = assert_op(f"concentric {direction} t={t}",
                        lambda t=t: sk.shell(body, t, tops_of(body), direction))
        if out is None:
            continue
        built += 1
        assert len(out.solids()) == 2, f"t={t}: {len(out.solids())} lumps out of 2"
        for lump in out.solids():
            for box, v in was:
                assert not (abs(lump.volume - v) <= 1e-6 and same_box(lump, box)),                     f"concentric {direction} t={t}: a lump came back unchanged"
    assert built >= 4, f"concentric {direction}: only {built} of 5 thicknesses built"
