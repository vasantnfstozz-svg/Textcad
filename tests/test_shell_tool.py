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
import math

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


def test_the_journeys_shell_never_asks_the_kernel_at_all(monkeypatch):
    """The sentence alone does not prove the crash is fenced: `kernelguard` turns
    a segfault INTO a sentence, so a guard that had gone missing would still
    read as a polite refusal — at the cost of a dead worker every time. What
    makes this row done is that the kernel is never asked.

    Measured 2026-09-16 at HEAD (probes/shell_scaled_ball_head_probe.py, one
    child per thickness, the body 34.9365 mm3 / 4 faces / 1 lump /
    2.56 x 4.8 x 5.12 mm): the journey's own t = 1.8 and the 2026-09-12 sweep's
    crash edge t = 1.29 are both refused in 0.00 s with the kernel untouched,
    while t = 1.27 — just under the dmin/2 bound — DOES go to the kernel and
    comes back its own clean refusal in 4.4 s, in a process that lives. No
    child died at any thickness."""
    body = clipped_ball()
    asked = []
    import kernelguard
    real = kernelguard.guarded
    monkeypatch.setattr(kernelguard, "guarded",
                        lambda kind, solid, info, fn: (asked.append(kind),
                                                       real(kind, solid, info, fn))[1])
    # the filed step, and the thickness the 2026-09-12 sweep measured as the
    # first that segfaulted (1.27 refused cleanly, 1.29 took the process down)
    for t in (1.8, 1.29):
        with pytest.raises(ValueError, match="meet in the middle of this body"):
            sk.shell(body, t, open_face="none")
        assert asked == [], f"t = {t} reached the kernel — the bound before it has gone"
    # and the bound is not a blanket no: under it the kernel is asked, and its
    # own refusal comes back as a sentence
    with pytest.raises(ValueError, match="do not fit this body"):
        sk.shell(body, 1.27, open_face="none")
    assert asked == ["shell"]


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


def test_no_constant_times_area_can_separate_a_sound_shell_from_a_wrong_one():
    """The two populations OVERLAP on `walls / (area * t)`, so the first ratio
    is a first question and never the verdict.

    Measured 2026-09-17 with no sampling error at all, against the closed form
    for a drilled box (probes/shell_skin_thick_plate_probe.py; the same
    arithmetic reproduces the kernel's own 21,107.482 on the 196-hole plate to
    every digit and its 12,759.862 on the 100-hole one):

      * CORRECT, and the highest on record: a 50 x 50 x 60 block with 81 holes
        of r 0.4 at 5 mm pitch, shelled inward at 1.8 mm — 95,594.085 mm3 of
        walls against a closed form of 95,594.085, valid, watertight, health
        clean — reads 1.8229;
      * WRONG, and the lowest on record: the 60 x 60 x 10 plate with 100 holes
        of r 1.0 at t = 1.3, where the kernel hands the whole body back —
        reads 1.6569.

    1.8229 is ABOVE 1.6569, so there is no ceiling that allows every sound
    result and refuses every wrong one. What the first ratio still does is
    separate cheaply and in the safe direction: every wrong result on record
    clears it, so it can gate a SECOND question rather than decide alone."""
    assert sk._SHELL_SKIN_FACTOR >= 1.1309 * 1.15, "no margin over the 196-hole plate"
    assert sk._SHELL_SKIN_FACTOR < 1.8229, \
        "a ceiling above the highest CORRECT result would let the wrong ones through too"


def test_the_coarea_question_is_what_actually_decides_a_refusal():
    """The second question, and the numbers that place it. The walls over the
    MEAN of the two surfaces they lie between, `out.area / 2 * t`, is the
    coarea formula, so it is pinned near 1.0 by geometry rather than by
    calibration — and a hole, whose offset area moves LINEARLY with depth, is
    exactly the feature that sends the first ratio up while leaving this one
    alone. Measured over the gauntlet corpus and the committed crash bodies at
    nine thicknesses in both directions (probes/shell_skin_direction_corpus.py)
    and over the drilled blocks (probes/shell_skin_thick_plate_probe.py):

      SOUND and able to reach this question (first ratio over 1.35):
          1.0054, 1.0059, 1.0114, 1.0116, 1.0155, 1.0190, 1.0283
      SOUND, everything else: 0.96 to 1.0018, plus one outlier at 1.3725 (the
          oneplus case at t = 0.5, where the walls nearly meet and the inner
          surface collapses) — its first ratio is 1.0559, so it never gets
          here.
      WRONG, and past every other check: 2.7116 and 3.3129 (the 100-hole plate
          at t = 1.0 and 1.3), 4.1249 (the 49-hole block at t = 3) and 5.4354
          (the user's own my-part-5 mirror body at t = 3, the P0 this guard was
          built for). The 1.9183 the range's own notes quote is my-part-5 at
          t = 1.5, which `is_valid` already refuses two checks earlier.

    Both margins are pinned here so the next person cannot drift either number
    without measuring again.

    ROUND TWO, 2026-09-18, corrects the last line of that list. The lowest
    WRONG coarea on record is not 2.7116: the same 100-hole plate at t = 3.0
    hands back all but 0.96 mm3 of a 77.4 mm3 cavity and reads **1.4351**,
    which is UNDER this bound and ABOVE the 1.3725 that the sound population
    reaches. So these two populations overlap exactly as the `area * t` ones
    do, and no constant on EITHER normaliser can separate them — which is why
    the refusal that catches that result is
    `assert_the_deepest_point_was_hollowed`, a theorem about the body in hand,
    and not a third number. The bound is kept where it is because moving it
    down to 1.43 would refuse the sound 1.3725 with almost no margin, and
    because as the second half of an AND it can only ever allow."""
    assert sk._SHELL_COAREA_FACTOR >= 1.0283 * 1.25, "no margin over the highest SOUND result"
    assert sk._SHELL_COAREA_FACTOR >= 1.3725, \
        "under the highest sound coarea reading ever measured, in any direction"
    assert 1.3725 < 1.4351 < sk._SHELL_COAREA_FACTOR, \
        "the sound and wrong coarea populations overlap: see the docstring"


def drilled_block(L: float, H: float, n: int, r: float, pitch: float):
    """an L x L x H block drilled with an n x n square grid of through holes.

    The material within `t` of its boundary is exact arithmetic while the grown
    holes neither merge nor reach the eroded box (`skin_truth` below), which is
    what makes this body an oracle and not just another sample."""
    span = (n - 1) * pitch
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * pitch, -span / 2 + j * pitch, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, L, H)) - cut


def skin_truth(L: float, H: float, n: int, r: float, pitch: float, t: float) -> float:
    """exact mm3 of material within `t` of that block's boundary"""
    N, span = n * n, (n - 1) * pitch
    assert pitch >= 2 * (r + t), "the grown holes merge: the closed form does not apply"
    assert span / 2 + r + t <= L / 2 - t, "a grown hole reaches the eroded box"
    core = (L - 2 * t) ** 2 * (H - 2 * t) - N * math.pi * (r + t) ** 2 * (H - 2 * t)
    return L * L * H - N * math.pi * r * r * H - core


def test_a_correct_shell_of_a_deeply_drilled_block_is_not_refused():
    """The P1 the 1.35 ceiling shipped with: a block full of deep small holes
    is a body where a PERFECTLY correct inward shell reads high, and 1.35
    refused it.

    The sweep that set 1.35 drilled its holes into a 60 x 60 x **10** plate and
    never varied the thickness, which is the dimension that decides the answer:
    a drilled plate's ratio is `1 + (hole area / area) * t/2r`, so the same
    drilling in a thicker block has more hole wall per flat face and climbs
    towards the hole's own `1 + t/2r` without becoming any harder to shell.

    All three thicknesses below match the closed form to every digit the kernel
    prints, and all three are over the first ceiling — the last one at 1.8229,
    past the 1.6569 that the range calls the lowest WRONG result on record."""
    L, H, n, r, pitch = 50.0, 60.0, 9, 0.4, 5.0
    block = drilled_block(L, H, n, r, pitch)
    assert block.volume == pytest.approx(147557.098, rel=1e-6)
    area = block.area
    for t, ratio in ((1.0, 1.4709), (1.5, 1.6935), (1.8, 1.8229)):
        want = skin_truth(L, H, n, r, pitch, t)
        out = healthy(sk.shell(block, t))
        assert bool(out.is_valid) and inspector.closed_shell(out)
        assert out.volume == pytest.approx(want, rel=1e-6), "the kernel is exactly right here"
        assert out.volume / (area * t) == pytest.approx(ratio, abs=1e-3)
        assert ratio > sk._SHELL_SKIN_FACTOR, "this case is only interesting over the ceiling"
        # and the question that saves it: the walls really do lie between the
        # two surfaces they should
        assert out.volume / (out.area / 2 * t) < 1.05


def drilled_plate(r: float, pitch: float):
    """a 60 x 60 x 10 plate drilled with a square grid of holes — the shape
    where `1 + t/2r` makes a CORRECT shell read high"""
    n = int((60.0 - 2 * (r + 1.5)) // pitch)
    span = n * pitch
    cut = b3d.Part()
    for i in range(n + 1):
        for j in range(n + 1):
            cut += b3d.Pos(-span / 2 + i * pitch, -span / 2 + j * pitch, 0) * \
                b3d.Cylinder(r, 30)
    return (b3d.Part() + b3d.Box(60.0, 60.0, 10.0)) - cut


def test_a_wrong_hollow_the_old_ceiling_of_2_let_through():
    """100 holes of radius 1 at 6 mm pitch. At t = 0.8 the kernel is right, at
    t = 1.0 it is 59 sigma wrong — and the old ceiling of 2.0 passed the wrong
    one, because it reads 1.7981.

    The oracle is Monte Carlo over the interior, the walls being exactly the
    material within t of the boundary (probes/shell_skin_oracle_probe.py,
    probes/shell_skin_concave_sweep.py): 12,768 +/- 182 at t = 0.8 against the
    kernel's 12,759.9, and 16,212 +/- 189 at t = 1.0 against its 27,429.7 —
    11,218 mm3 of walls that are not there. At t = 1.3 it hands the whole body
    back and that reads 1.6569, which is the lowest wrong result on record and
    what sets the ceiling's upper margin.

    Both wrong thicknesses are refused, and the coarea question is what makes
    the refusal stand: they read 2.7116 and 3.3129 of the two surfaces their
    walls are meant to lie between, where the sound one reads 1.0126."""
    plate = drilled_plate(1.0, 6.0)
    assert plate.volume == pytest.approx(32858.407, rel=1e-6)
    out = healthy(sk.shell(plate, 0.8))
    assert out.volume == pytest.approx(12759.862, rel=1e-5)
    assert out.volume / (plate.area * 0.8) == pytest.approx(1.0456, abs=1e-3)
    assert out.volume / (out.area / 2 * 0.8) == pytest.approx(1.0126, abs=1e-3)
    with pytest.raises(ValueError, match="came back as the body itself") as ei:
        sk.shell(plate, 1.0)
    assert "27,429.7" in str(ei.value), "the sentence names what the kernel returned"
    # and at 1.3 the kernel hands the whole body back — 1.6569 of its skin, the
    # lowest wrong result on record, which the old ceiling of 2.0 also passed
    with pytest.raises(ValueError, match="came back as the body itself") as ei:
        sk.shell(plate, 1.3)
    assert "32,858.3" in str(ei.value)


def test_the_same_handback_goes_silent_once_the_wall_is_thick_enough():
    """Round two, 2026-09-18. `walls / (area * t)` is the body's OWN
    `volume / (area * t)` whenever the kernel hands the body back, so the 1.35
    ceiling can only ever see a handback while `t < volume / (1.35 * area)`.
    Every wrong result the ceiling was calibrated on was measured at t <= 1.3
    on a body whose volume/area is 2.154 — walk the SAME plate past
    32,858.407 / (1.35 * 15,254.867) = 1.596 mm and the same handback reads
    under the ceiling and says nothing.

    Measured against a Monte Carlo oracle over the ANALYTIC distance to a
    drilled box's boundary — no OpenCASCADE, no closed form
    (probes/shell_coarea_merge_probe.py --case flat100 --oracle 2000000):

        t = 2.5   kernel 32,846.427, true 31,886.6 +/- 4.1  — 234 sigma out.
                  12.0 mm3 of cavity where 971.8 mm3 had to go, and it reads
                  0.8613 of its skin: the coarea question is never even asked
        t = 3.0   kernel 32,857.445, true 32,781.0 +/- 1.2  — 64 sigma out.
                  0.96 mm3 where 77.4 had to go, 0.7180 of its skin and 1.4351
                  of its coarea: BOTH ratios under their own bounds

    Neither ratio can see either one. The point the guard already measured
    can: at depth 3.2426 (the middle of the cell the four holes leave, which
    is 6/sqrt2 - 1 mm from all four) it comes back INSIDE the walls."""
    plate = drilled_plate(1.0, 6.0)
    area = plate.area
    assert plate.volume / (area * sk._SHELL_SKIN_FACTOR) == pytest.approx(1.596, abs=1e-3)
    for t, walls, skin, coarea in ((2.5, 32846.427, 0.8613, 1.7181),
                                   (3.0, 32857.445, 0.7180, 1.4351)):
        # the two ratios are BOTH under their bounds here — this is what makes
        # the case, so it is measured and not assumed
        assert walls / (area * t) == pytest.approx(skin, abs=1e-3)
        assert skin < sk._SHELL_SKIN_FACTOR, "the first gate would have caught it"
        with pytest.raises(ValueError, match="hollowed next to nothing") as ei:
            sk.shell(plate, t)
        assert "3.243 mm from every face that stays" in str(ei.value)
    assert 1.4351 < sk._SHELL_COAREA_FACTOR, \
        "at t = 3 the coarea reading is under its own bound too"


def test_the_plate_that_the_kernel_does_hollow_is_untouched_by_the_new_check():
    """The other direction of the same measurement: the same plate at 1.6 mm,
    where the kernel is right. 24,362.544 against the same Monte Carlo oracle's
    24,357.5 +/- 10.8 (0.5 sigma), and the deep point — the same one, depth
    2.0000 there — comes back OUT of the walls."""
    plate = drilled_plate(1.0, 6.0)
    out = healthy(sk.shell(plate, 1.6))
    assert out.volume == pytest.approx(24362.544, rel=1e-5)
    assert abs(out.volume - 24357.5) < 5 * 10.8, "five sigma of the oracle"


def test_the_deep_point_refuses_only_when_both_halves_say_so():
    """Every gate of the new refusal, on one 50 x 50 x 30 box, because each of
    them was put there by a measurement that would otherwise be a false
    refusal.

    A 14.9 mm wall leaves a 20.2 x 20.2 x 0.2 cavity — 0.109 per cent of the
    body, under the "hollowed nothing" floor — so that is the result the point
    is allowed to judge. A 3 mm wall hollows 62 per cent of it, and there the
    point decides nothing however deep it claims to be: a kernel that drops a
    sliver of cavity is not a kernel that handed the body back (the oneplus
    case at t = 0.5 is a real one, 30.7 per cent hollowed with its deep point
    still inside)."""
    body = box()
    in_the_wall = (0.0, 0.0, 14.0)             # the top wall spans z 12..15
    roomy = sk.shell(body, 3.0, None, "inside", None)
    assert (body.volume - roomy.volume) / body.volume > 0.5
    sk.assert_the_deepest_point_was_hollowed(body, roomy, (9.0, in_the_wall, 1e-3),
                                             3.0, "walls of 3 mm")
    thin = sk.shell(body, 14.9, None, "inside", None)
    assert (body.volume - thin.volume) / body.volume < sk._SHELL_NOTHING_HOLLOWED
    with pytest.raises(ValueError, match="hollowed next to nothing"):
        sk.assert_the_deepest_point_was_hollowed(body, thin, (20.0, in_the_wall, 1e-3),
                                                 14.9, "walls of 14.9 mm")
    # no margin: the same point in the same place says nothing
    sk.assert_the_deepest_point_was_hollowed(body, thin, (14.9005, in_the_wall, 1e-3),
                                             14.9, "walls of 14.9 mm")
    # a point in the CAVITY is never a refusal, however deep it claims to be
    sk.assert_the_deepest_point_was_hollowed(body, thin, (99.0, (0.0, 0.0, 0.0), 1e-3),
                                             14.9, "walls of 14.9 mm")
    # ... nor is a point that is not in the body this result came from: a body
    # that MOVED on the way to the worker would weigh the same, and a closed
    # hollow has no picks whose marks would notice
    sk.assert_the_deepest_point_was_hollowed(body, thin, (99.0, (0.0, 0.0, 400.0), 1e-3),
                                             14.9, "walls of 14.9 mm")


def test_the_pre_kernel_guard_hands_its_point_on_instead_of_dropping_it():
    """`assert_something_would_be_hollowed` measured that point already; the
    whole cost of the new check is that it now RETURNS it. A refusal still
    raises, and a body with nothing to measure still answers None."""
    found = sk.assert_something_would_be_hollowed(box(), 3.0, [], "walls of 3 mm")
    depth, at, tol = found
    # it stops at the FIRST station deep enough, so the number is somewhere
    # between the wall it allowed and the truth — never past the truth
    assert 3.0 <= depth <= 15.0 + 1e-6, depth
    assert sk.deepest_material(box(), 1e9)[0] == pytest.approx(15.0, abs=1e-6), \
        "half the 30 mm box, when nothing stops the search early"
    assert len(at) == 3 and tol > 0
    with pytest.raises(ValueError, match="nothing would be hollowed"):
        sk.assert_something_would_be_hollowed(box(), 20.0, [], "walls of 20 mm")


def test_the_skin_ceiling_cannot_be_made_to_mean_anything_outward():
    """LAUNCH-PLAN section 10 asks whether the same ladder can judge an OUTSIDE
    shell. Measured, in the outward direction, over the same corpus at the same
    thicknesses (probes/shell_skin_direction_corpus.py): every sound outward
    result runs from 1.0023 up to 1.5233, rising with `t` and with nothing else
    — the l-bracket reads 1.4894 at t = 8, the dprism boss 1.4573, the cylinder
    1.3840, and the plate with a hole 1.5233.

    That is Steiner's formula and not a kernel fault: growing a body by `t`
    adds `A*t + M*t^2 + (4/3)*pi*t^3`, so the ratio starts at 1 and rises
    without any bound the body's own area knows about. A ball of radius 10
    grown by 8 mm is 2.01 of its skin and exactly right — which is the shape of
    the wrong result this ceiling exists to catch on the INSIDE. So no constant
    can mean the same thing outward, and none is invented: an outside shell
    keeps every other check and not this one.

    The proof that it would really bite: a 50 x 50 x 30 box grown by 8 mm."""
    cube = b3d.Box(50.0, 50.0, 30.0)
    out = healthy(sk.shell(cube, 8.0, None, "outside", None))
    assert bool(out.is_valid) and inspector.closed_shell(out)
    assert out.volume == pytest.approx(66 * 66 * 46 - 75000, rel=1e-9)
    grown = out.volume / (cube.area * 8.0)
    assert grown == pytest.approx(1.4247, abs=1e-3)
    assert grown > sk._SHELL_SKIN_FACTOR, "this correct result would trip the first gate inward"
    assert sk.assert_walls_could_be_a_skin(cube, out, 8.0, "outside", "walls") is None
    # …and it would survive the second one even so, which is the point of
    # asking twice: these walls really do lie between two surfaces of that
    # area. What no inward result survives is the body handed back as its own
    # hollow — no inner surface at all, so it reads 4.55 of the mean of one
    with pytest.raises(ValueError, match="came back as the body itself"):
        sk.assert_walls_could_be_a_skin(cube, cube, 3.0, "inside", "walls of 3 mm")
    assert cube.volume / (cube.area / 2 * 3.0) == pytest.approx(4.545, abs=1e-3)


# ---------------------------------------------------------------------------
# The taper the sampler could not find the middle of (review of cc78019)
# ---------------------------------------------------------------------------

def draft_wedge():
    """a plain draft: 2 mm at one end, 30 mm at the other, 40 mm deep"""
    return b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-40, 0), (40, 0), (40, 30), (-40, 2), close=True)), 40)


def thick_L():
    return b3d.Part() + b3d.Box(60, 60, 30) + b3d.Pos(55, -26, 0) * b3d.Box(50, 8, 30)


def test_the_deepest_material_of_a_taper_is_found_not_undershot():
    """`deepest_material`'s stations lie on rays through face sample points, and
    the deepest material of a body sits on one of those only when symmetry puts
    it there — a box, a plate, a cylinder. On a plain draft wedge it does not:
    the stations reached 10.62 mm where the real maximum is 12.42 (measured
    independently by a grid over the whole interior,
    probes/shell_depth_oracle_probe.py), so a CLOSED shell at 11, 11.5 and 12 mm
    was refused BEFORE the kernel — in a sentence that told the user "walls must
    be under 10.62 mm" — while the kernel builds all three SOUND. The best
    sampled points are walked uphill now, away from the face nearest them, which
    is the direction the inscribed sphere grows."""
    wedge = draft_wedge()
    assert wedge.volume == pytest.approx(51200.0, rel=1e-6)
    depth, _at, _tol = sk.deepest_material(wedge, 1e9)
    assert depth == pytest.approx(12.42, abs=0.05), "the taper's real maximum"
    for t, cavity in ((11.0, 314.23), (11.5, 127.46), (12.0, 26.97)):
        out = healthy(sk.shell(wedge, t))
        assert wedge.volume - out.volume == pytest.approx(cavity, rel=0.02)
    # and past the real maximum it is still refused, with the right number
    with pytest.raises(ValueError, match=r"more than 12\.4\d* mm from the faces"):
        sk.shell(wedge, 13.0)


def test_the_depth_under_an_opening_is_measured_on_an_asymmetric_body_too():
    """The same undershoot with a face open: an L-plate 30 mm tall, top open,
    read 24.5 mm where the material under the opening is the full 30."""
    body = thick_L()
    depth, _at, _tol = sk.deepest_material(body, 1e9, sk.shell_openings(body, None, "top"))
    assert depth == pytest.approx(30.0, abs=0.05)


def test_walking_uphill_never_invents_a_refusal_nor_lets_a_thin_body_through():
    """The climb accepts a point only when that point measures DEEPER by the
    same exact BRepExtrema the stations use, so it can only ever raise the
    answer: it turns a false refusal into a build and can never create one.
    The bodies the guard exists for really are thin everywhere — the 1.3 mm
    walled box's true maximum IS 0.65 mm — so none of them gets through."""
    body = hollow_box()
    assert sk.deepest_material(body, 1e9)[0] == pytest.approx(0.65, abs=1e-3)
    with pytest.raises(ValueError, match="nothing would be hollowed"):
        sk.shell(body, 0.7)
    for solid, want in ((box(), 15.0), (b3d.Box(50, 50, 10), 5.0), (b3d.Cylinder(20, 40), 20.0)):
        assert sk.deepest_material(solid, 1e9)[0] == pytest.approx(want, abs=1e-3)


def test_opening_every_face_is_the_kernels_refusal_not_a_zero_millimetre_one():
    """Six clicks on a box opens all six faces, and then NO face stays — there
    is no surface left for a wall to lie within, so the depth guard has no
    question to ask. Measuring against an EMPTY compound answered nothing and
    the sentence came out "no point of it is more than 0 mm from the faces that
    stay ... so walls must be under 0 mm"; the kernel's own refusal is the
    honest one, as it was before the guard existed."""
    cube = box()
    names = ["top", "bottom", "+x", "-x", "+y", "-y"]
    assert len(sk.shell_openings(cube, names)) == len(cube.faces()) == 6
    assert sk.deepest_material(cube, 1e9, sk.shell_openings(cube, names)) is None
    with pytest.raises(ValueError, match="nothing was hollowed"):
        sk.shell(cube, 3.0, names)


def long_draft_prism():
    """a plain draft 180 mm long: 2 mm at one end, 34 at the other, 40 deep"""
    return b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-90, 0), (90, 0), (90, 34), (-90, 2), close=True)), 40)


def ramped_plate():
    """a plate with a ramped rib whose thick part sits away from the base face's
    centre AND away from both its triangle centroids"""
    return b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-60, 0), (60, 0), (60, 8), (10, 26), (-60, 8), close=True)), 50)


def test_a_flat_face_is_sampled_to_its_budget_not_to_its_triangle_count():
    """A FLAT face tessellates into one to six triangles however big it is, so
    one ray per centroid spent 33 of a 108-point budget on the review's
    wedge-in-a-slab and put no ray within 40 mm of the taper's thick end. The
    climb is a LOCAL walk, so a seed has to start somewhere near: coverage is
    what it needs, not more steps. Each picked triangle is filled to the budget
    now. Measured 2026-09-16 (the code review of 3bbfcca, probes/
    shell_depth_oracle_probe.py for the truth): this 180 mm draft read 14.8189
    where the real maximum is 15.4781, and the ramped plate 11.8232 against
    12.6900 — so every wall between those numbers was refused before the kernel
    while the kernel builds them sound. On the user's library the same change
    takes my-part-3 from 26.1037 to 27.6434 (its oracle is 27.6094) and
    cam-cover-lower from 3.2447 to 3.7189."""
    prism = long_draft_prism()
    assert prism.volume == pytest.approx(129600.0, rel=1e-6)
    assert sk.deepest_material(prism, 1e9)[0] == pytest.approx(15.50, abs=0.05)
    for t, cavity in ((14.9, 49.795), (15.2, 11.742), (15.34, 3.255)):
        out = healthy(sk.shell(prism, t))
        assert prism.volume - out.volume == pytest.approx(cavity, rel=0.05)
    plate = ramped_plate()
    assert sk.deepest_material(plate, 1e9)[0] == pytest.approx(12.71, abs=0.05)
    for t, cavity in ((11.9, 241.427), (12.29, 63.407)):
        out = healthy(sk.shell(plate, t))
        assert plate.volume - out.volume == pytest.approx(cavity, rel=0.05)


def test_the_climb_walks_a_ridge_instead_of_dying_on_it():
    """The residual two reviews declared and neither closed, and the reason it
    was not a seeding fault.

    "Away from the nearest face" is the gradient of the distance field where
    the field is smooth, and it stops being smooth on the MEDIAL AXIS: the
    inscribed sphere touches on two sides, the step walks into the second wall,
    the distance does not rise, the step halves and the seed dies on the ridge
    instead of walking along it. The ramped plate is that shape — the guard
    answered 12.2987 and refused every wall from there up, while the kernel
    builds them sound.

    The way on costs no new machinery: the failed candidate was MEASURED, so
    its own nearest point came back with it, and `u1 + u2` rises against both
    walls to first order. The answer this reaches is not a matter of opinion —
    the section of this plate is the polygon (-60,0) (60,0) (60,8) (10,26)
    (-60,8), whose largest inscribed circle touches the bottom and both slopes
    at r = 12.713 by hand, and 50 mm of extrusion cannot beat that. The climb
    answers 12.7125.

    THE RULE: a guard whose job is refusing proves nothing by reading a bigger
    number. Every wall this newly allows was put to the kernel over the four
    plateau bodies, the gauntlet corpus and the four committed crash fixtures
    (probes/shell_depth_ridge_allowed_probe.py): 12 build and are SOUND, 16 the
    kernel refuses with a sentence, none crashed and none came back unsound —
    and the crash fixtures do not move at all. The three that matter most are
    built here."""
    plate = ramped_plate()
    assert sk.deepest_material(plate, 1e9)[0] == pytest.approx(12.7125, abs=0.005), \
        "the exact inscribed radius of this section is 12.713"
    for t, cavity in ((12.4022, 33.934), (12.5056, 14.982), (12.6090, 3.733)):
        out = healthy(sk.shell(plate, t))
        assert bool(out.is_valid) and inspector.closed_shell(out)
        assert plate.volume - out.volume == pytest.approx(cavity, rel=0.08, abs=0.02)
    # ... and past the answer the refusal still stands, naming the new number.
    # 12.9 and not 13.5: this plate is 26 mm at its thinnest, so from 13 mm up
    # the bounding-box guard speaks first and this one is never reached
    with pytest.raises(ValueError, match=r"more than 12\.7\d* mm from the faces"):
        sk.shell(plate, 12.9)


def wedge_in_slab():
    """LAUNCH-PLAN section 10's plateau repro: the same 2-to-30 mm draft wedge,
    fused into an 80 x 80 x 24 slab. ONE solid, 155,657.143 mm3."""
    return b3d.Part() + (draft_wedge() + b3d.Pos(0, -30.0, 12.0) * b3d.Box(80, 80, 24))


def test_a_uniform_plateau_does_not_outrank_the_taper_it_is_fused_to():
    """The other half of the 2026-09-16 finding, and the harder half.

    A uniform region measures exactly what its chord allows, so this slab's
    mid-plane reads 12.0000 at a dozen points more than 12 mm apart — and the
    climb's seeds were ranked by DEPTH, so the plateau took all three and the
    wedge fused into it, whose real maximum is 12.4300 by an independent grid,
    never got one. The guard then refused 12.05, 12.2 and 12.4 mm in a sentence
    that told the user "walls must be under 12 mm", while the kernel builds all
    three sound. More seeds do not help (the plateau has dozens more) and
    neither do more steps (a plateau has no gradient to climb): measured, the
    station the answer is really found from is ranked #159 of 177 by depth and
    starts 2.4271 mm from a face. What it has is ROOM — its own chord passed
    through 40 mm of material — and `bound / depth` is exactly 1.0 on every
    plateau station, the lowest score there is.

    THE RULE this test exists for: a corpus behind a refusing guard only ever
    tests its refusals, so raising its number proves nothing until the walls it
    newly ALLOWS are put to the kernel. All four of them are, below."""
    body = wedge_in_slab()
    assert len(body.solids()) == 1, "the repro is ONE solid, not two lumps"
    assert body.volume == pytest.approx(155657.143, rel=1e-6)
    assert sk.deepest_material(body, 1e9)[0] == pytest.approx(12.4499, abs=0.01)
    for t, cavity in ((12.0416, 22.110), (12.1662, 10.524), (12.2909, 3.270),
                      (12.4222, 0.103)):
        out = healthy(sk.shell(body, t))
        assert bool(out.is_valid) and inspector.closed_shell(out)
        assert body.volume - out.volume == pytest.approx(cavity, rel=0.08, abs=0.03)
    # and past the answer it is still refused, with the right number in it
    with pytest.raises(ValueError, match=r"more than 12\.4\d* mm from the faces"):
        sk.shell(body, 13.0)


def plateau_pair():
    """a uniform 20 mm slab with a fat 34 x 34 x 24 post on it: the slab's
    plateau reads 10.0 everywhere and the deepest material is in the post"""
    return b3d.Part() + (b3d.Pos(0, 0, 10) * b3d.Box(120, 80, 20)
                         + b3d.Pos(40, 0, 32) * b3d.Box(34, 34, 24))


def test_the_third_ranking_gets_enough_budget_to_reach_the_post():
    """The body the THIRD ranking ("deepest, and with room") exists for, and
    the one that showed the climb's shared budget starving the rankings that
    were added beside it.

    A slab carrying a fat post: the slab's mid-plane is a 10.0 plateau, the
    post is deeper, and the winning station sits ON the plateau and climbs up
    into the post. `_seeds_for_the_climb`'s own docstring records 17.0000 ->
    17.2160 against a grid oracle of 17.2047 — and at a budget of 120 the
    shipped code answered 17.0000, because the three DEEPEST seeds are spent
    first, can take 41 measurements each, and leave nothing for the seed the
    answer is on (probes/shell_depth_seed_starvation_probe.py). Re-ordering
    does not help; the budget is the whole of it."""
    body = plateau_pair()
    assert body.volume == pytest.approx(219744.0, rel=1e-9)
    assert sk.deepest_material(body, 1e9)[0] == pytest.approx(17.2242, abs=0.01)
    # the guard now steps out of the way over the whole band it used to refuse,
    # and the kernel's own refusal is a sentence, not a corrupt body
    for t in (17.0216, 17.1512, 17.2052):
        with pytest.raises(ValueError, match="could not offset its faces"):
            sk.shell(body, t)
    with pytest.raises(ValueError, match=r"more than 17\.2\d* mm from the faces"):
        sk.shell(body, 18.0768)


def test_the_climb_spends_what_it_measurably_needs_and_no_more():
    """Nine seeds of forty steps could spend 369 distance measurements, and one
    costs about 0.12 s on a 330-face body, so the whole climb shares one
    budget.

    That budget was 120 — "no more than the three seeds it used to take" — and
    it was measured starving the two rankings the same commit added: the slab
    with a post answered 17.0000 where the seeding really reaches 17.2160, and
    the wedge in the slab 12.4156 where it reaches 12.4444. So the number comes
    from what the climb actually SPENDS when nothing stops it, which is a
    measurement and not a theoretical worst case: over the plateau bodies, the
    gauntlet corpus, the four committed crash fixtures and drilled plates up to
    330 faces, the unstopped spend is 3 to 172 and never approaches 369, since
    seeds terminate early when the step halves out
    (probes/shell_depth_seed_starvation_probe.py). On the 330-face body the
    climb stops itself at 106 whichever budget it is given, so the rise costs
    nothing there. Counted, not timed — wall-clock on this box swings 3x."""
    assert sk._DEPTH_CLIMB_CALLS == 200
    assert sk._DEPTH_CLIMB_CALLS < sk._DEPTH_CLIMB_SEEDS * 3 * (sk._DEPTH_CLIMB_STEPS + 1), \
        "a budget that nine seeds could not reach is not a budget"
    spent, real = [0], sk._climb_to_the_deepest

    def counting(solid, measure, seen, best, tol):
        def counted(q):
            spent[0] += 1
            return measure(q)
        return real(solid, counted, seen, best, tol)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sk, "_climb_to_the_deepest", counting)
        for solid in (wedge_in_slab(), plateau_pair(), box(),
                      b3d.Cylinder(20, 40), draft_wedge()):
            spent[0] = 0
            sk.deepest_material(solid, 1e9)            # t = infinity: always climbs
            assert 0 < spent[0] <= sk._DEPTH_CLIMB_CALLS, spent[0]


def test_a_climb_stopped_by_its_budget_reads_lower_and_never_deeper():
    """Round two, 2026-09-18: the other half of the budget question. 200 is
    what the climb SPENDS on every body measured so far — but a body nobody has
    built yet can exhaust it, and the only thing that matters then is which way
    the answer moves.

    It moves DOWN, and that is structural rather than lucky: out of budget,
    `spend` answers exactly as "nothing could be measured" does, and every
    depth this function ever keeps came back from the same exact
    `BRepExtrema`, so a starved climb keeps a point it really measured and a
    shorter walk simply stops earlier. A lower reading is a SAFER refusal (the
    guard refuses walls the kernel might have built), never a deeper one (which
    would let a body the wall does not fit reach the kernel and crash it).

    Measured here on the body the third ranking exists for, at four budgets
    down to zero, and on the plateau repro at one."""
    post, wedge = plateau_pair(), wedge_in_slab()
    full = sk.deepest_material(post, 1e9)[0]
    assert full == pytest.approx(17.2242, abs=0.01), "the shipped answer moved"
    with pytest.MonkeyPatch.context() as mp:
        for budget, solid, top in ((30, post, full), (3, post, full), (0, post, full),
                                   (0, wedge, 12.4499)):
            mp.setattr(sk, "_DEPTH_CLIMB_CALLS", budget)
            got = sk.deepest_material(solid, 1e9)[0]
            assert got <= top + 1e-9, \
                f"a climb starved to {budget} calls read {got}, DEEPER than {top}"
            assert got > 0.0, "a starved climb must still answer the sample's own best"


def test_a_plateau_station_scores_the_lowest_room_there_is():
    """The seeding rule on its own, with no kernel in it: a station can never
    measure more than its own chord allows, so `bound / depth` is 1.0 on a
    plateau and above 1 everywhere else. Here the plateau holds every one of
    the three deepest places and the taper's station is last by depth — and it
    is still seeded."""
    from build123d import Vector
    flat = [(12.0, Vector(20 * i, 0, 12), 12.0) for i in range(6)]
    taper = (2.4, Vector(0, 200, 25), 20.0)
    seeds = sk._seeds_for_the_climb(flat + [taper], 12.0, 1e-3)
    assert taper[1] in [q for _d, q in seeds], "the station with room was not seeded"
    assert seeds[0][0] == 12.0, "the deepest is still seeded first"
    # a station on a face is all room and no use: it would crawl through the
    # whole budget a fraction of a millimetre at a time
    onface = [(0.001, Vector(0, -200, 0), 30.0)]
    assert onface[0][1] not in [q for _d, q in
                                sk._seeds_for_the_climb(flat + onface, 12.0, 1e-3)]


def test_the_extra_samples_cost_a_body_with_hundreds_of_faces_nothing():
    """The budget is `200_000 // faces**2` rays per face, so a body of 130+ faces
    already gets ONE, and one sample is the centroid and nothing else — the same
    point cc78019 fired its ray through. That is what keeps the 675-face panel's
    refusal path at 7.6 s (measured 2026-09-16) while small bodies are sampled
    properly."""
    assert sk._barycentres(1) == ((1 / 3, 1 / 3, 1 / 3),)
    assert sk._barycentres(4)[0] == (1 / 3, 1 / 3, 1 / 3)
    for k in (1, 2, 3, 4, 7, 12):
        got = sk._barycentres(k)
        assert len(got) == k
        assert all(abs(sum(w) - 1.0) < 1e-12 for w in got), "barycentric"
        assert all(all(0.0 < x < 1.0 for x in w) for w in got), "strictly inside"
