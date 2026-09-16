"""Shell (LAUNCH-PLAN.md P4, specs/shell.md): Fusion's Shell as ONE op that eats
its body — walls of one thickness around a cavity, the picked faces removed —
and the planner that hands the tool its face set, its glow and its arrow.

probes/shell_probe.py (2026-09-10) found in the kernel:

    offset(openings=[faces])         -> exact volumes on every corpus body
    Kind.INTERSECTION                -> sharp corners (ARC rounds an outward shell's)
    offset() with NO opening         -> the offset SOLID, not a shell (a shrunk box)
    t = half the width, a face open  -> the body UNCHANGED, called a success
    t past the far wall              -> an OPEN SHELL, called a success
    a closed hollow at t >= half     -> RuntimeError; just under: a bare ValueError
    a curved face as the opening     -> RuntimeError

Every geometric claim below is checked against the kernel: volumes against
formulas, the arrow against the face's own normal.
"""
import json

import build123d as b3d
import pytest

import inspector
import sketch as sk
import toolplan
from document import Document, op_params


def box():
    return b3d.Box(50.0, 50.0, 30.0)       # centred on the origin: top at z = 15


TOP = {"center": [0, 0, 15], "normal": [0, 0, 1]}
PX = {"center": [25, 0, 0], "normal": [1, 0, 0]}


def healthy(part):
    assert inspector.health(part) == []
    return part


# ------------------------------------------------------------------ the op ---

def test_one_opening_leaves_walls_of_exactly_the_thickness():
    out = healthy(sk.shell(box(), 3, ["top"]))
    assert out.volume == pytest.approx(75000 - 44 * 44 * 27, rel=1e-6)
    # the outside stays where it was
    bb = out.bounding_box()
    assert [bb.min.X, bb.max.X, bb.min.Z, bb.max.Z] == pytest.approx([-25, 25, -15, 15], abs=1e-6)


def test_a_pick_names_the_same_face_as_its_name():
    assert sk.shell(box(), 3, [TOP]).volume == pytest.approx(sk.shell(box(), 3, ["top"]).volume)


def test_two_openings_and_a_side_opening():
    assert sk.shell(box(), 3, ["top", "+x"]).volume == pytest.approx(19164, rel=1e-6)
    assert sk.shell(box(), 3, ["+x"]).volume == pytest.approx(75000 - 47 * 44 * 24, rel=1e-6)
    assert sk.shell(box(), 3, ["top", "bottom"]).volume == pytest.approx(16920, rel=1e-6)


def test_two_picks_of_one_face_count_once():
    assert sk.shell(box(), 3, [TOP, "top"]).volume == pytest.approx(22728, rel=1e-6)


def test_no_opening_is_a_closed_hollow_not_a_shrunk_box():
    out = healthy(sk.shell(box(), 3))
    assert out.volume == pytest.approx(75000 - 44 * 44 * 24, rel=1e-6)   # walls, not the inner box
    assert len(out.shells()) == 2 and len(out.solids()) == 1
    assert sk.shell(box(), 3, []).volume == pytest.approx(out.volume)


def test_outside_adds_the_walls_around_the_body_with_sharp_corners():
    out = healthy(sk.shell(box(), 3, ["top"], direction="outside"))
    assert out.volume == pytest.approx(56 * 56 * 33 - 75000, rel=1e-6)   # INTERSECTION: 28488, ARC gave 27818.5
    bb = out.bounding_box()
    assert [bb.min.X, bb.max.X, bb.min.Z, bb.max.Z] == pytest.approx([-28, 28, -18, 15], abs=1e-6)
    closed = healthy(sk.shell(box(), 3, direction="outside"))
    assert closed.volume == pytest.approx(56 * 56 * 36 - 75000, rel=1e-6)


def test_the_legacy_open_face_grammar_still_builds():
    assert sk.shell(box(), 3, open_face="top").volume == pytest.approx(22728, rel=1e-6)
    assert sk.shell(box(), 3, open_face="none").volume == pytest.approx(28536, rel=1e-6)
    # a stored faces list beats it
    assert sk.shell(box(), 3, faces=[], open_face="top").volume == pytest.approx(28536, rel=1e-6)
    import blocks
    assert blocks.shell_out(box(), 3, open_face="bottom").volume == pytest.approx(22728, rel=1e-6)


@pytest.mark.parametrize("kwargs, words", [
    (dict(thickness=0, faces=["top"]), "thickness must be positive"),
    (dict(thickness=-2, faces=["top"]), "thickness must be positive"),
    (dict(thickness=3, faces=["top"], direction="both"), 'direction must be "inside" or "outside"'),
    (dict(thickness=3, open_face="left"), "open_face must be"),
    (dict(thickness=3, faces=[7]), "an opening is a face name"),
    (dict(thickness=3, faces=7), "faces must be a list of openings"),   # not iterable at all
    (dict(thickness=3, faces=True), "faces must be a list of openings"),
    (dict(thickness=3, faces=["north"]), "not a direction"),
    (dict(thickness=25, faces=["top"]), "nothing was hollowed"),        # the UNCHANGED body
    (dict(thickness=40, faces=["top"]), "nothing would be hollowed"),     # BEFORE the kernel (which built an OPEN SHELL and called it a success)
    (dict(thickness=25), "meet in the middle of this body"),            # half the 30 mm height or more:
    (dict(thickness=24.9), "meet in the middle of this body"),          # refused BEFORE the kernel
])
def test_every_refusal_is_a_sentence_in_the_shells_own_words(kwargs, words):
    with pytest.raises(ValueError, match=words) as e:
        sk.shell(box(), **kwargs)
    for leak in ("TopoDS", "Standard_", "BRep", "offset Error"):
        assert leak not in str(e.value)


def clipped_ball(scale=0.8):
    """THE CRASH BODY of bugs/20260912-175819-isogrid-panel-s9016-crash, built
    the way the journey built it: a YZ rectangle 6 x 10.4 extruded 8.9,
    intersected with a ball of radius 3.2 turned 180 about Z, scaled 0.8 —
    a sphere face clipped by three planes, 2.56 x 4.8 x 5.12 mm."""
    import blocks
    ball = blocks.rotate(blocks.ball(3.2), "Z", 180, pivot="center")
    s = sk.make_sketch("YZ", 0, [dict(kind="rectangle", mode="add", x=0, y=0,
                                      rotation=0, w=6.0, h=10.4)])
    body = sk.extrude_sketch(s, amount=8.9, both=False) & ball
    return blocks.scale_uniform(body, scale) if scale != 1 else body


def test_a_closed_wall_of_half_the_body_is_refused_before_the_kernel():
    """bugs/20260912-175819-isogrid-panel-s9016-crash: a closed inward hollow
    whose wall is at least HALF the body's smallest extent can leave nothing
    hollow, and asking the kernel anyway SEGFAULTED it (0xC0000005 inside
    offset(), measured at t = 1.8, 2 and 3 on the 2.56 mm body and at t = 18
    on the same shape ten times bigger). The bound is not a judgement call:
    every point lies within half the smallest extent of the boundary."""
    # the box: 30 mm tall, so 15 is the wall that meets itself
    for t in (15, 15.5, 29, 100):
        with pytest.raises(ValueError, match="only 30 mm at its thinnest.*under 15 mm"):
            sk.shell(box(), t)
    # just under the bound the kernel takes it: a 0.2 mm cavity, still a hollow
    out = healthy(sk.shell(box(), 14.9))
    assert out.volume == pytest.approx(75000 - 20.2 * 20.2 * 0.2, rel=1e-6)
    # an OPENING changes the bound (a 20 mm floor under a 10 mm-deep cavity is
    # a real shell of the 30 mm box), so the guard is the closed hollow's only
    assert healthy(sk.shell(box(), 20, [TOP])).volume == pytest.approx(75000 - 10 * 10 * 10, rel=1e-6)
    # OUTSIDE grows the body: no bound applies
    assert healthy(sk.shell(box(), 20, direction="outside")).volume == pytest.approx(90 * 90 * 70 - 75000, rel=1e-6)


def hollow_box():
    """the body of bugs/20260915-210615-my-part-s95959-step18, built the way the
    journey built it: a 23.4 x 17.1 x 12.7 box shelled at 1.3 mm, bottom open"""
    return sk.shell(sk.extrude_sketch(sk.make_sketch("XY", 0, [dict(
        kind="rectangle", mode="add", x=0, y=0, rotation=0, w=23.4, h=17.1)]), amount=12.7),
        1.3, ["bottom"])


NOTHING_DEEP = (r"nothing would be hollowed — walls of {t} mm meet in the middle of this body "
                r"everywhere: no point of it is more than {d} mm from the faces that stay "
                r"\(near .*\), so walls must be under {d} mm; use a thinner wall or open a face")


def test_a_body_that_is_thin_everywhere_is_refused_before_the_kernel():
    """bugs/20260915-210615-my-part-s95959-step18 led here: a SECOND shell on
    a body that already has 1.3 mm walls. CLOSED, every point of it is within
    0.65 mm of a face, so any wall from 0.66 mm up leaves nothing — the box
    bound (12.7 mm at its smallest) never sees that, the rays do. With the TOP
    open the lid's material counts to the cavity ceiling 1.3 mm below it, so
    the line is 1.3 there: 1.5 and 2 are refused in a moment, 0.6 builds (two
    skins inside every wall). The filed step itself, 1.1 with the top open, is
    a legitimate 0.2 mm recess in the lid the kernel CRASHES on, and that one
    is the kernel worker's — see test_kernel_guard.py."""
    body = hollow_box()
    assert body.volume == pytest.approx(1643.538, abs=1e-2)
    for t in (1.1, 0.7, 0.66):
        with pytest.raises(ValueError, match=NOTHING_DEEP.format(t=t, d=r"0\.65")):
            sk.shell(body, t)
    for t in (1.5, 2):
        with pytest.raises(ValueError, match=NOTHING_DEEP.format(t=t, d=r"1\.3")):
            sk.shell(body, t, ["top"])
    out = healthy(sk.shell(body, 0.6, ["top"]))
    assert 0 < out.volume < body.volume


def test_a_thin_part_of_a_thick_body_is_the_kernels_to_fill_not_a_refusal():
    """The first draft of that guard asked the OPPOSITE question — is there a
    wall the offset does not fit? — and refused 11 shells the kernel built
    SOUND (probes/shell_thin_wall_corpus.py, 2026-09-16). A 4 mm rib on a 12 mm
    plate at 3 mm walls: the rib stays solid, the plate hollows, and that is
    correct. Same for a 4 mm web between two pockets."""
    rib = b3d.Part() + b3d.Box(60, 40, 12) + b3d.Pos(0, 0, 10) * b3d.Box(4, 40, 8)
    out = healthy(sk.shell(rib, 3))
    assert 0 < out.volume < rib.volume
    pockets = b3d.Part() + (b3d.Box(60, 40, 12) - b3d.Pos(-12, 0, 6) * b3d.Box(20, 30, 8)
                            - b3d.Pos(12, 0, 6) * b3d.Box(20, 30, 8))
    out = healthy(sk.shell(pockets, 2.5))
    assert 0 < out.volume < pockets.volume


def test_the_material_against_an_opening_counts_to_the_faces_that_stay():
    """With the top open the deepest material of a 10 mm plate sits right under
    the opening, 10 mm from the floor — so 8 mm walls leave a 2 mm cavity, and
    a wall over 10 mm is refused in those words, not after the kernel."""
    plate = b3d.Box(50, 50, 10)
    out = healthy(sk.shell(plate, 8, ["top"]))
    assert out.volume == pytest.approx(50 * 50 * 10 - 34 * 34 * 2, rel=1e-6)
    with pytest.raises(ValueError, match=NOTHING_DEEP.format(t=12, d="10")):
        sk.shell(plate, 12, ["top"])
    # the 30 mm box with the top open takes a 20 mm floor (a 10 mm cavity), as ever
    assert healthy(sk.shell(box(), 20, [TOP])).volume == pytest.approx(75000 - 10 * 10 * 10, rel=1e-6)


def test_a_wall_thicker_than_a_balls_radius_is_refused_not_an_inverted_cavity():
    """The same bound also refuses a SILENT WRONG result the kernel called a
    success: offset(sphere r 3.2, -5) INVERTS to a radius-1.8 sphere, so
    shell(ball, 5) came back "hollowed" — 137.26 -> 112.83 mm3, watertight,
    health [] — with a cavity no 5 mm wall could ever leave."""
    import blocks
    with pytest.raises(ValueError, match="only 6.4 mm at its thinnest.*under 3.2 mm"):
        sk.shell(blocks.ball(3.2), 5)
    with pytest.raises(ValueError, match="meet in the middle"):
        sk.shell(blocks.ball(3.2), 3.2)
    thin = healthy(sk.shell(blocks.ball(3.2), 3.0))          # a 0.2 mm cavity: honest
    assert thin.volume == pytest.approx(4 / 3 * 3.14159265 * (3.2 ** 3 - 0.2 ** 3), rel=1e-4)


def test_the_closed_bound_is_per_lump_so_a_big_lump_cannot_pay_for_a_small_one():
    body = mixed_lumps(b3d.Box(3.0, 20.0, 10.0))          # 20 x 20 x 10 beside 3 x 20 x 10
    with pytest.raises(ValueError, match="1 of the 2 separate lumps.*only 3 mm at its thinnest"):
        sk.shell(body, 2)
    out = healthy(sk.shell(body, 1))                       # 1 mm fits both
    assert [round(s.volume, 6) for s in out.solids()] == [
        pytest.approx(4000 - 18 * 18 * 8), pytest.approx(600 - 1 * 18 * 8)]


def test_the_crash_bodys_thinner_walls_are_the_kernels_refusal_not_a_crash():
    body = clipped_ball()
    size = body.bounding_box().size
    assert (round(size.X, 3), round(size.Y, 3), round(size.Z, 3)) == (2.56, 4.8, 5.12)
    with pytest.raises(ValueError, match="only 2.56 mm at its thinnest.*under 1.28 mm"):
        sk.shell(body, 1.28)
    with pytest.raises(ValueError, match="do not fit this body"):
        sk.shell(body, 1.0)                                # below the bound: the kernel's own no


def test_the_journeys_shell_is_a_sentence_in_a_process_that_survives():
    """The red form of this test is a DEAD child (exit 0xC0000005), which no
    in-process assertion can express — so the exact crash step runs in a child:
    tests.test_shell_tool.clipped_ball() shelled closed at 1.8 mm inside,
    `open_face: "none"` as the journey sent it."""
    import os
    import subprocess
    import sys
    import textwrap
    code = textwrap.dedent("""
        import sketch as sk
        from tests.test_shell_tool import clipped_ball
        try:
            sk.shell(clipped_ball(), 1.8, open_face="none")
        except ValueError as e:
            print("REFUSED", e)
        """)
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=300, env=env)
    assert p.returncode == 0, f"the child died with {p.returncode & 0xFFFFFFFF:#x}: {p.stderr[-400:]}"
    assert "REFUSED shell: walls of 1.8 mm meet in the middle of this body" in p.stdout


def lumps3():
    """three separate 20 x 20 x 10 boxes as ONE body — what a linear_pattern of
    a boss hands the tree, and what a cut that severs a plate leaves behind"""
    import pattern
    return pattern.linear_pattern(b3d.Box(20.0, 20.0, 10.0), count=3, dx=40.0)


def test_a_lump_with_no_opening_is_refused_not_left_a_solid_block():
    """Measured in the review of fb0b8c8: `offset(openings=[…])` shells only the
    lumps a listed face belongs to and returns the raw offset SOLID for the
    rest — [1952, 1536, 1536] inside (2464 is a closed shell) and
    [2912, 8064, 8064] outside (blocks GROWN by 2 mm), every one of them
    watertight, healthy and green. A failed feature beats a corrupt body."""
    body = lumps3()
    assert len(body.solids()) == 3
    for direction in ("inside", "outside"):
        with pytest.raises(ValueError, match="3 separate lumps and 2 of them have no face open"):
            sk.shell(body, 2, ["top"], direction)


def test_every_lump_open_and_no_lump_open_both_still_build_exactly():
    body = lumps3()
    tops = [f for f in body.faces()
            if abs(f.center().Z - 5) < 1e-6 and sk.face_plane(f) is not None]
    assert len(tops) == 3
    refs = [{"center": list(f.center()), "normal": [0, 0, 1]} for f in tops]
    # an opening on EVERY lump: the kernel is exact — 20*20*10 - 16*16*8 each
    out = healthy(sk.shell(body, 2, refs))
    assert [round(s.volume, 2) for s in out.solids()] == [pytest.approx(1952, rel=1e-6)] * 3
    # no opening at all: the difference route is exact per lump, both directions
    assert [round(s.volume, 2) for s in sk.shell(body, 2).solids()] \
        == [pytest.approx(4000 - 16 * 16 * 6, rel=1e-6)] * 3
    assert [round(s.volume, 2) for s in sk.shell(body, 2, direction="outside").solids()] \
        == [pytest.approx(24 * 24 * 14 - 4000, rel=1e-6)] * 3


def mixed_lumps(second):
    """ONE body in two separate lumps: a 20 x 20 x 10 boss beside a smaller one
    — a linear_pattern whose seed is not square, or a cut that severed a plate
    into unequal halves."""
    return b3d.Part() + b3d.Box(20.0, 20.0, 10.0) + b3d.Pos(40, 0, 0) * second


def tops_of(body):
    return [{"center": list(max(l.faces(), key=lambda f: (round(f.center().Z, 6), f.area)).center()),
             "normal": [0, 0, 1]} for l in body.solids()]


def test_a_lump_the_wall_does_not_fit_is_refused_not_left_a_solid_block():
    """Round TWO of the review of fb0b8c8: the SAME P0 through another door.
    `assert_every_lump_open` asks that every lump have an opening — not that
    every lump actually HOLLOWS. With a top open on each, a lump the thickness
    does not fit comes back UNTOUCHED and the whole-body checks all pass:
    measured 20 x 20 x 10 beside 3 x 20 x 10 at t = 2 -> [1952, 600] where 600
    is the raw block, and beside 20 x 20 x 4 at t = 5 -> [3500, 1600] the same
    way. Both watertight, health [], the total volume down, the row green.
    ALONE each small lump is correctly refused ("nothing was hollowed") — it is
    the WHOLE-BODY volume check that a second, bigger lump defeats."""
    for second, t, block in ((b3d.Box(3.0, 20.0, 10.0), 2, 600.0),      # too NARROW
                             (b3d.Box(20.0, 20.0, 4.0), 5, 1600.0)):    # too FLAT
        alone = b3d.Part() + second
        # BEFORE the kernel since 2026-09-16 (no point of a 3 mm rib is 2 mm from
        # its faces), where it used to be the kernel's "nothing was hollowed"
        with pytest.raises(ValueError, match="nothing (was|would be) hollowed"):
            sk.shell(alone, t, tops_of(alone))              # one lump: already refused
        body = mixed_lumps(second)
        assert len(body.solids()) == 2
        with pytest.raises(ValueError, match="do not fit 1 of the 2 separate lumps"):
            sk.shell(body, t, tops_of(body))
        assert block > 0          # the volume the block used to come back with


def test_a_thickness_that_fits_every_lump_still_builds_exactly():
    """The other half of the guard: it must not refuse a shell that is right.
    20 x 20 x 10 beside 12 x 20 x 10 at t = 2 is exact per lump, and the whole
    OUTSIDE direction measured clean on the hostile corpus
    (probes/shell_round2_outside_probe.py) — walls there are added around every
    lump, so no lump can come back untouched."""
    body = mixed_lumps(b3d.Box(12.0, 20.0, 10.0))
    out = healthy(sk.shell(body, 2, tops_of(body)))
    assert [round(s.volume, 6) for s in out.solids()] == [
        pytest.approx(20 * 20 * 10 - 16 * 16 * 8), pytest.approx(12 * 20 * 10 - 8 * 16 * 8)]
    # outside grows every lump: the narrow one that Inside refuses is fine here
    thin = mixed_lumps(b3d.Box(3.0, 20.0, 10.0))
    grown = healthy(sk.shell(thin, 2, tops_of(thin), "outside"))
    assert [round(s.volume, 6) for s in grown.solids()] == [
        pytest.approx(24 * 24 * 12 - 20 * 20 * 10), pytest.approx(7 * 24 * 12 - 3 * 20 * 10)]


def test_concentric_lumps_a_post_inside_a_ring_still_shell():
    """Round THREE: round two's guard paired result lumps to input lumps by
    nearest bounding box CENTRE, and two CONCENTRIC lumps share a centre
    exactly — a post inside a ring, a spigot in a bore. The tie sent both
    results to one seat, left the other empty and refused a shell the kernel
    had built perfectly: measured ring 3628.54 and post 458.28, each to its
    own oracle's decimal, watertight and healthy. Identity by the whole BOX
    tells them apart where a centre cannot (40 x 40 x 10 against 10 x 10 x 10)."""
    ring = b3d.Cylinder(20, 10) - b3d.Cylinder(15, 10)
    body = b3d.Part() + ring + b3d.Cylinder(5, 10)
    assert len(body.solids()) == 2
    centres = {tuple(round(c, 6) for c in tuple(s.bounding_box().center()))
               for s in body.solids()}
    assert len(centres) == 1, "the two lumps must share a centre, or this proves nothing"
    out = healthy(sk.shell(body, 1.5, tops_of(body)))
    import math
    ring_walls = math.pi * (400 - 225) * 10 - math.pi * (18.5 ** 2 - 16.5 ** 2) * 8.5
    post_walls = math.pi * 25 * 10 - math.pi * 3.5 ** 2 * 8.5
    assert sorted(round(s.volume, 2) for s in out.solids()) == [
        pytest.approx(post_walls, rel=1e-6), pytest.approx(ring_walls, rel=1e-6)]


def test_the_block_is_caught_by_IDENTITY_not_by_a_volume_drop():
    """The signal is exact and must stay exact: an untouched lump matches its
    input at d(volume) 0.0 and d(box) 0.0, while a lump that really hollowed
    came no closer than 0.992 of its input over 99 measured lumps
    (probes/shell_round3_sweep_probe.py). So a THIN but honest cavity must
    build — 8 mm walls in a 20 mm box leave 4 x 4 x 2 — and only the exact
    block is refused."""
    body = mixed_lumps(b3d.Box(20.0, 20.0, 10.0))       # the twin: both hollow
    out = healthy(sk.shell(body, 8, tops_of(body)))     # 0.992 of the input each
    assert [round(s.volume, 6) for s in out.solids()] == [
        pytest.approx(4000 - 4 * 4 * 2)] * 2
    thin = mixed_lumps(b3d.Box(3.0, 20.0, 10.0))        # the block: exactly 1.000
    with pytest.raises(ValueError, match="do not fit 1 of the 2 separate lumps"):
        sk.shell(thin, 2, tops_of(thin))


def test_a_curved_opening_is_refused_with_its_type():
    cyl = b3d.Cylinder(25, 40)
    wall = next(f for f in cyl.faces() if f.geom_type.name == "CYLINDER")
    c = wall.center()
    with pytest.raises(ValueError, match="FLAT face — that face is CYLINDER"):
        sk.shell(cyl, 2, [{"center": [c.X, c.Y, c.Z], "normal": None}])
    # its caps are fine
    assert healthy(sk.shell(cyl, 2, ["top"])).volume > 0


def test_the_catalogue_knows_every_key_and_a_strict_add_refuses_a_stranger():
    assert [n for n, _ in op_params("shell")] == ["thickness", "faces", "direction", "open_face"]
    d = Document(name="strict")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    with pytest.raises(ValueError):
        d.add("s", "shell", {"thickness": 3, "openings": ["top"]}, ["b"], strict=True)


# ------------------------------------------------------------- the document ---

def plate_doc():
    d = Document(name="plan")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.rebuild()
    return d


PTOP = dict(face_center=[0, 0, 6], face_normal=[0, 0, 1])
PLATE_TOP_OPEN = 28800 - 54 * 34 * 9          # 12276


def last(d):
    return d.features[-1]


def test_a_shell_feature_builds_eats_its_body_and_rides_an_upstream_change():
    d = plate_doc()
    d.add("s", "shell", {"thickness": 3, "faces": ["top"]}, ["b"])
    d.rebuild()
    assert last(d).status == "ok"
    assert last(d).volume == pytest.approx(PLATE_TOP_OPEN, rel=1e-6)
    d.edit_many("b", {"thickness": 20})
    d.rebuild()
    assert last(d).volume == pytest.approx(60 * 40 * 20 - 54 * 34 * 17, rel=1e-6)


def test_a_failing_shell_is_a_red_row_with_a_sentence_not_a_missing_body():
    d = plate_doc()
    d.add("s", "shell", {"thickness": 30, "faces": ["top"]}, ["b"])
    d.rebuild()
    f = last(d)
    assert f.status == "failed" and f.problems
    assert "shell:" in f.problems[0] and "Standard_" not in f.problems[0]


# ----------------------------------------------------------------- the plan ---

def ok(plan):
    assert plan["ok"], plan
    json.dumps(plan)                       # must survive the API boundary
    return plan


def test_the_opening_click_is_the_first_face_and_the_arrow_points_into_the_material():
    p = ok(toolplan.plan(plate_doc(), {"tool": "shell", "body_id": "b", **PTOP}))
    assert p["op"] == "shell" and p["mode"] == "face" and p["input"] == "b" == p["target_body"]
    assert p["n_open"] == 1 and len(p["faces"]) == 1
    assert p["faces"][0]["center"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["faces"][0]["normal"] == pytest.approx([0, 0, 1], abs=1e-6)
    assert p["origin"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["axis"] == pytest.approx([0, 0, -1], abs=1e-6)          # INTO the material
    assert len(p["edges"]) == 4 and all(len(e["points"]) >= 2 for e in p["edges"])
    assert p["direction"] == "inside"
    assert p["seed_words"] == "1 face open of b"
    assert "open now" in p["click_words"]


def test_a_second_click_on_an_open_face_closes_it_and_the_words_say_so():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP}))
    q = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "faces": p["faces"],
                             "face_toggle": {"center": [0, 0, 6], "normal": [0, 0, 1]}}))
    assert q["n_open"] == 0 and q["faces"] == [] and q["edges"] == []
    assert q["seed_words"] == "no face open — a closed hollow body"
    assert "closed again" in q["click_words"]
    # the arrow moves to the largest flat face and still points inward
    assert abs(q["origin"][2]) == pytest.approx(6, abs=1e-6)
    assert q["axis"][2] * q["origin"][2] < 0


def test_a_click_on_another_face_opens_it_too():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP}))
    q = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "faces": p["faces"],
                             "face_toggle": {"center": [30, 0, 0], "normal": [1, 0, 0]}}))
    assert q["n_open"] == 2 and len(q["edges"]) == 8
    assert q["seed_words"] == "2 faces open of b"
    assert q["origin"] == pytest.approx([0, 0, 6], abs=1e-6)         # the FIRST opening keeps the arrow


def test_outside_flips_the_arrow_and_an_unknown_direction_is_refused():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "direction": "outside"}))
    assert p["axis"] == pytest.approx([0, 0, 1], abs=1e-6) and p["direction"] == "outside"
    r = toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "direction": "both"})
    assert not r["ok"] and "inside" in r["error"]


def test_a_faces_list_is_the_selection_even_when_empty():
    p = ok(toolplan.plan(plate_doc(), {"tool": "shell", "body_id": "b", **PTOP, "faces": []}))
    assert p["n_open"] == 0


def test_edit_reads_the_stored_set_names_stay_names_and_legacy_rows_open():
    d = plate_doc()
    d.add("s", "shell", {"thickness": 3, "faces": ["top"], "direction": "outside"}, ["b"])
    d.add("legacy", "shell", {"thickness": 3, "open_face": "bottom"}, ["b"])
    d.rebuild()
    p = ok(toolplan.plan(d, {"tool": "shell", "feature_id": "s"}))
    assert p["faces"] == ["top"] and p["n_open"] == 1 and p["direction"] == "outside"
    assert p["origin"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["axis"] == pytest.approx([0, 0, 1], abs=1e-6)             # outside: OUT of the material
    q = ok(toolplan.plan(d, {"tool": "shell", "feature_id": "legacy"}))
    assert q["faces"] == ["bottom"] and q["n_open"] == 1
    assert q["origin"] == pytest.approx([0, 0, -6], abs=1e-6)
    # a click during the edit toggles against the stored set
    r = ok(toolplan.plan(d, {"tool": "shell", "feature_id": "s",
                             "face_toggle": {"center": [0, 0, 6], "normal": [0, 0, 1]}}))
    assert r["n_open"] == 0


def test_the_plan_agrees_with_the_op():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP}))
    d.add("s", "shell", {"thickness": 3, "faces": p["faces"], "direction": p["direction"]}, ["b"])
    d.rebuild()
    assert last(d).status == "ok" and last(d).volume == pytest.approx(PLATE_TOP_OPEN, rel=1e-6)


def test_plan_refuses_with_a_sentence_never_an_exception():
    d = plate_doc()
    # an id that names nothing falls through to the newest solid (_pick_body's
    # rule for every face-mode plan: a pick before any body was named)
    r = toolplan.plan(d, {"tool": "shell", "body_id": "nope", **PTOP})
    assert r["ok"] and r["input"] == "b"
    # a face the body does not have (a preview's own face, a wrong body)
    r = toolplan.plan(d, {"tool": "shell", "body_id": "b",
                          "face_toggle": {"center": [0, 0, 40], "normal": [0, 0, 1]}})
    assert not r["ok"] and "not on b" in r["error"]
    c = Document(name="c")
    c.add("c", "disc", {"radius": 25, "thickness": 40}, [])
    c.rebuild()
    # a click on the cylinder's WALL: a curved face is never on the body's
    # picked-face terms (its centre is off its surface) — a sentence either way
    r = toolplan.plan(c, {"tool": "shell", "body_id": "c",
                          "face_toggle": {"center": [25, 0, 0], "normal": [1, 0, 0]}})
    assert not r["ok"] and r["error"] and "Standard_" not in r["error"]
    e = Document(name="empty")
    r = toolplan.plan(e, {"tool": "shell", "body_id": None})
    assert not r["ok"] and "build a body first" in r["error"]


# ---------------------------------------------------------------------------
# The body handed back as a hollow (my-part-5 seed 18800, 2026-09-14)
# ---------------------------------------------------------------------------

def mirror_body():
    """my-part-5's `j2_mirror` at the step the overnight runner crashed on:
    413262.875 mm3, 25 faces, one lump, 35 x 313.383 x 116.214 mm."""
    from pathlib import Path
    p = Path(__file__).resolve().parent / "fixtures" / "my_part_5_mirror_body.brep"
    return b3d.Part(b3d.import_brep(str(p)).wrapped)


def test_the_body_handed_back_as_a_hollow_is_refused():
    """The P0 found beside the segfault the folder was filed for. A closed 3 mm
    shell returned 413260.165 of 413262.875 mm3 — 2.709 mm3 removed, 0.00066
    per cent — valid, watertight, health empty, green in the tree and saved.
    Every check that existed asked about IDENTITY, and "nothing was hollowed"
    is `abs(v_out - v_in) <= 1e-6`, which 2.709 clears by seven orders of
    magnitude."""
    body = mirror_body()
    assert round(body.volume, 3) == 413262.875, "the fixture is not the crash body"
    with pytest.raises(ValueError, match="came back as the body itself"):
        sk.shell(body, 3.0, None, "inside", None)


def test_a_solid_OpenCASCADE_calls_invalid_never_leaves_the_op():
    """The same body at 1.5 mm: 137707.973 mm3, `closed_shell` True — every edge
    on exactly two faces — and `is_valid` False. `closed_shell` is a topology
    census, not BRepCheck_Analyzer, so the op has to ask OCCT too: the document
    runs health with check_valid=False on INTERMEDIATE features, and an op that
    eats its body must not hand one of those on."""
    with pytest.raises(ValueError, match="OpenCASCADE itself reports it invalid"):
        sk.shell(mirror_body(), 1.5, None, "inside", None)


def test_a_correct_shell_that_is_almost_a_block_still_builds():
    """The guard that catches the block must not catch this: a 12 mm plate at
    5.9 mm walls leaves 521 mm3 of cavity — the walls are 98.91 per cent of the
    body, closer to a block than anything else measured — and it is CORRECT.
    That is why the ceiling is `area * t` and not a volume fraction; this plate
    reads 0.72 of its skin where the wrong result reads 2.72."""
    plate = b3d.Box(80.0, 50.0, 12.0)
    out = healthy(sk.shell(plate, 5.9, None, "inside", None))
    assert out.volume == pytest.approx(47478.952, rel=1e-6)
    assert out.volume / plate.volume > 0.98, "this case is only interesting if it is near-solid"


def test_the_skin_ceiling_sits_above_every_sound_result_ever_measured():
    """Calibrated, not guessed (probes/shell_wall_bound_corpus.py, 2026-09-14):
    over the gauntlet corpus and the committed crash bodies at nine thicknesses
    from 0.2 to 8 mm, a sound CLOSED hollow measured 0.61-1.056 of `area * t`
    and a sound OPEN one 0.61-0.955. Above 1 is real and expected — a surface
    that is mostly CONCAVE has inner parallel faces larger than its outer ones
    — so the ceiling has to clear it with room."""
    assert sk._SHELL_SKIN_FACTOR >= 1.056 * 1.5, "no margin over the measured ceiling"
    assert sk._SHELL_SKIN_FACTOR <= 2.72 / 1.25, "no margin under the result it must catch"


def test_the_skin_ceiling_leaves_outside_shells_alone():
    """Their walls sit OUTSIDE the old surface and were never measured, so they
    are not judged by this bound (they keep every other check)."""
    # a 50 mm cube is 125000 mm3 against a 3 mm skin of 6 x 2500 x 3 = 45000,
    # so handing the body back as its own walls is 2.78x the ceiling
    cube = b3d.Box(50.0, 50.0, 50.0)
    assert cube.volume / (cube.area * 3.0) == pytest.approx(2.778, rel=1e-3)
    assert sk.assert_walls_could_be_a_skin(cube, cube, 3.0, "outside", "walls of 3 mm") is None
    with pytest.raises(ValueError, match="came back as the body itself"):
        sk.assert_walls_could_be_a_skin(cube, cube, 3.0, "inside", "walls of 3 mm")
