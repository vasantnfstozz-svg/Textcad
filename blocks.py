"""
blocks.py — Phase 2: the verified building-block library.

The single biggest source of hallucination is asking the LLM to INVENT geometry
code from scratch. The fix: give it a curated set of small, already-TESTED
helper functions and tell it to COMPOSE from these instead. You cannot
hallucinate an API you are only calling.

Every function here:
  * takes plain numeric parameters,
  * returns a build123d `Part` (a real solid) using only API confirmed on this
    machine (build123d 0.11.1, algebra mode),
  * is exercised in the self-test at the bottom and validated with
    inspector.health(), so the library is guaranteed sound before the LLM ever
    touches it.

Convention: parts are built centered on the origin, extruded along +/-Z, so the
hole/pattern helpers (which cut tall cutters along Z) work regardless of scale.
TWO EXCEPTIONS, measured 2026-09-10 and load-bearing for saved designs:
`polygon_plate` and `hex_plate` STAND ON Z=0 and run up to +thickness (they are
extruded one way from a BuildSketch on Plane.XY). The
AI's positioning rule in author.AUTHOR_PROMPT says so; it used to call them
centred, which put every hex body it placed half a thickness out.
"""

from __future__ import annotations
import dis
import functools
import math
import os
import re
import struct
import tempfile
from collections import OrderedDict
from pathlib import Path
from build123d import (
    Box, Cylinder, Sphere, Cone, Pos, PolarLocations, BuildSketch, RegularPolygon, BuildLine, Polyline, make_face,
    extrude, revolve, Axis, Plane, Part, Mesher, Solid, Compound, Face,
    scale as _b3d_scale,
    fillet as _b3d_fillet, chamfer as _b3d_chamfer,
    import_step as b3d_import_step,
)
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve      # point-to-edge distance (resolve_edge)
from OCP.BRepClass3d import BRepClass3d_SolidClassifier   # is this shell inside that one
from OCP.Extrema import Extrema_ExtPC
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_State
from OCP.TopExp import TopExp                      # unique vertices/faces of a shell, in C++
from OCP.TopoDS import TopoDS
from OCP.TopTools import (TopTools_IndexedDataMapOfShapeListOfShape,
                          TopTools_IndexedMapOfShape)

import inspector          # health of every fillet / chamfer result
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid

_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}


# ---------------------------------------------------------------------------
# Primitive solids
# ---------------------------------------------------------------------------
# Every dimension is checked BEFORE the kernel sees it. Measured 2026-09-10
# (section 5 review): a zero thickness reached BRepPrimAPI and the feature row
# read `Standard_DomainError('')` — an empty diagnosis, identical for all three
# of a plate's dimensions — while a zero radius came back as a real solid of
# volume 0. Both are banned (CLAUDE.md: a kernel exception reaching the user,
# and a "successful" empty solid), and neither told the user which number to
# change. `_positive` is the one place that sentence is written.

def _numbers(op: str, unit: str, **vals) -> None:
    """Refuse a value that is not a number AT ALL, naming it and its unit.

    The half of `_positive` that has nothing to do with being positive, for the
    values where ZERO and NEGATIVE are real answers — a blade angle of 0 is a
    straight radial blade and a negative one is forward-swept, so `_positive`
    cannot speak for them, and until 2026-09-17 nothing did: `curved_blade`
    compared them straight to a number and a file holding a null angle read
    `TypeError: unsupported operand type(s) for -: 'int' and 'NoneType'` in
    the feature row (probes/s10_r3_creator_door.py, 24 such messages over its
    six parameters, plus six values that BUILT a different blade)."""
    for name, v in vals.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{op}: {name} must be a number in {unit} (got "
                             f"{v!r}) — type just the number, no units")


def _positive(op: str, **dims) -> None:
    """Refuse any dimension that is not a positive number, naming it."""
    for name, v in dims.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{op}: {name} must be a number in mm (got "
                             f"{v!r}) — type just the number, no units")
        if not v > 0:
            raise ValueError(f"{op}: {name} must be more than 0 (got "
                             f"{format(v, 'g')}) — there is no such shape, so "
                             f"type the size you want instead")


def plate(width: float, depth: float, thickness: float) -> Part:
    """A rectangular plate centered on the origin (X=width, Y=depth, Z=thickness)."""
    _positive("plate", width=width, depth=depth, thickness=thickness)
    return Box(width, depth, thickness)


def disc(radius: float, thickness: float) -> Part:
    """A solid cylinder (disc) centered on the origin, axis along Z."""
    _positive("disc", radius=radius, thickness=thickness)
    return Cylinder(radius=radius, height=thickness)


def ball(radius: float) -> Part:
    """A solid sphere centered on the origin. Great for domes (cut in half
    with a box), rounded ends, knobs, and stylized organic shapes."""
    _positive("ball", radius=radius)
    return Sphere(radius=radius)


def cone(bottom_radius: float, top_radius: float, height: float) -> Part:
    """A (truncated) cone centered on the origin, axis along Z — spans
    -height/2 to +height/2. top_radius=0 gives a sharp point. Use for tapers,
    funnels, nose shapes, stylized bodies."""
    _positive("cone", height=height)
    # EITHER end may be the point: cone(0, 10, h) is a funnel standing
    # point-down and OCCT builds it at exactly the volume of the flipped one
    # (2094.40 mm3 measured both ways, round two of the section 5 review) —
    # the fix pass briefly required a positive bottom_radius and took that
    # shape away. So both radii only have to be >= 0; two EQUAL radii is a
    # cylinder the kernel refuses outright ("cone with two identic radii"),
    # which also catches the both-zero case.
    for _n, _v in (("bottom_radius", bottom_radius), ("top_radius", top_radius)):
        if isinstance(_v, bool) or not isinstance(_v, (int, float)):
            raise ValueError(f"cone: {_n} must be a number in mm (got "
                             f"{_v!r}) — type just the number, no units")
        if _v < 0:
            raise ValueError(f"cone: {_n} cannot be negative (got "
                             f"{format(_v, 'g')}) — use 0 for a sharp point")
    if top_radius == bottom_radius:
        raise ValueError(f"cone: bottom_radius and top_radius are both "
                         f"{format(top_radius, 'g')} — that is a cylinder, "
                         f"so use disc instead")
    return Cone(bottom_radius=bottom_radius, top_radius=top_radius,
                height=height)


def tube(outer_radius: float, inner_radius: float, height: float) -> Part:
    """A hollow tube / ring / washer, axis along Z. inner < outer required."""
    _positive("tube", outer_radius=outer_radius, inner_radius=inner_radius,
              height=height)
    if inner_radius >= outer_radius:
        raise ValueError("tube: inner_radius must be < outer_radius")
    return Cylinder(radius=outer_radius, height=height) - Cylinder(
        radius=inner_radius, height=height)


def polygon_plate(sides: int, circumradius: float, thickness: float) -> Part:
    """A regular-polygon prism (hex nut stock, etc.), axis along Z.
    circumradius = distance from center to a corner.

    STANDS ON Z=0 and runs up to +thickness — it is NOT centred like plate and
    disc (module docstring; measured 2026-09-10)."""
    _positive("polygon_plate", circumradius=circumradius, thickness=thickness)
    if isinstance(sides, bool) or not isinstance(sides, (int, float)):
        raise ValueError(f"polygon_plate: sides must be a whole number (got "
                         f"{sides!r})")
    if sides != int(sides):
        raise ValueError(f"polygon_plate: sides must be a whole number (got "
                         f"{format(sides, 'g')}) — a polygon cannot have half "
                         f"a side")
    if int(sides) < 3:
        raise ValueError(f"polygon_plate: sides must be at least 3 (got "
                         f"{int(sides)}) — fewer than three corners is not a "
                         f"shape")
    with BuildSketch() as sk:
        RegularPolygon(radius=circumradius, side_count=int(sides))
    return extrude(sk.sketch, amount=thickness)


def hex_plate(across_flats: float, thickness: float) -> Part:
    """A hexagonal plate specified by its across-flats (wrench) size.

    STANDS ON Z=0 and runs up to +thickness, like polygon_plate."""
    _positive("hex_plate", across_flats=across_flats, thickness=thickness)
    circumradius = across_flats / math.sqrt(3.0)   # AF = circumradius * sqrt(3)
    return polygon_plate(6, circumradius, thickness)


def revolve_profile(points: list[tuple[float, float]]) -> Part:
    """Revolve a 2D profile 360 deg about the Z axis to make an axisymmetric
    solid (hub, pulley, shaft, shroud). `points` are (radius, z) pairs in the XZ
    plane; the profile is auto-closed. All radii must be >= 0. This is the
    workhorse for turned/turbomachinery-style parts."""
    # `len(points)` and the unpacking below ran on whatever the file held:
    # `TypeError: object of type 'NoneType' has no len()` and `not enough
    # values to unpack (expected 2, got 1)` reached the feature row (measured
    # 2026-09-17, probes/s10_r3_valueerror_census.py). As WIDE as what works
    # today — any sequence of two-number pairs, lists or tuples alike.
    if isinstance(points, (str, bytes, dict)) or not isinstance(points, (list, tuple)):
        raise ValueError(f"revolve_profile: points is a list of [radius, z] "
                         f"points (got {points!r})")
    for i, p in enumerate(points):
        if (isinstance(p, (str, bytes, dict))
                or not isinstance(p, (list, tuple)) or len(p) != 2):
            raise ValueError(f"revolve_profile: point {i + 1} is not a "
                             f"[radius, z] pair (got {p!r})")
    if len(points) < 3:
        raise ValueError("revolve_profile: need at least 3 points")
    # the docstring has promised radii >= 0 since this function existed and
    # never checked: a negative one gave `StdFail_NotDone('BRep_API: command
    # not done')` in the feature row (measured 2026-09-10)
    for i, (r, z) in enumerate(points):
        if not isinstance(r, (int, float)) or isinstance(r, bool):
            raise ValueError(f"revolve_profile: point {i + 1} has a radius "
                             f"that is not a number ({r!r})")
        if r < 0:
            raise ValueError(
                f"revolve_profile: point {i + 1} has radius "
                f"{format(float(r), 'g')} — a profile is revolved about the "
                f"Z axis, so every radius must be 0 or more")
    pts = [(float(r), float(z)) for r, z in points]
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
    return revolve(sk.sketch, axis=Axis.Z)


# ---------------------------------------------------------------------------
# Feature operations (take a part, return a modified part)
# ---------------------------------------------------------------------------

def _tall_cutter(radius: float, span: float = 1.0e5) -> Part:
    """A cylinder tall enough to cut clean through any reasonably-sized part."""
    return Cylinder(radius=radius, height=span)


def _drilled(op: str, before: Part, after: Part, what: str) -> Part:
    """A drill that removes nothing did not succeed — it missed.

    Measured 2026-09-10 (section 5 review): `with_center_hole` with radius 0
    handed back the UNDRILLED disc, volume 78539.82, and the tree row was
    green; a bolt circle whose PCD put the holes off the part did the same.
    The same class section 4 closed for `cut` ("a cut whose tool misses
    reported success silently"), through two doors it did not cover."""
    try:
        gone = float(before.volume) - float(after.volume)
    except Exception:                       # a volume we cannot read is not
        return after                        # evidence of anything
    if gone > 1e-6:
        return after
    raise ValueError(f"{op}: nothing was drilled — {what}")


def with_center_hole(part: Part, radius: float) -> Part:
    """Drill a through-hole on the Z axis at the origin."""
    _positive("with_center_hole", radius=radius)
    return _drilled("with_center_hole", part, part - _tall_cutter(radius),
                    "the hole falls outside this body, so there is no "
                    "material on the Z axis to drill through")


def with_bolt_circle(part: Part, count: int, bolt_radius: float,
                     pitch_circle_dia: float) -> Part:
    """Drill `count` through-holes evenly on a bolt circle of the given pitch
    circle diameter (PCD), centered on the origin, axis along Z."""
    if count < 1:
        raise ValueError("with_bolt_circle: count must be >= 1")
    _positive("with_bolt_circle", bolt_radius=bolt_radius,
              pitch_circle_dia=pitch_circle_dia)
    # a PCD of 0 put all `count` locations on the origin, so six holes became
    # ONE at the centre and the row stayed green (measured 2026-09-10)
    if pitch_circle_dia / 2.0 <= bolt_radius and count > 1:
        raise ValueError(
            f"with_bolt_circle: a pitch circle diameter of "
            f"{format(pitch_circle_dia, 'g')} mm is too small for "
            f"{format(bolt_radius, 'g')} mm holes — all {count} of them would "
            f"land on top of each other at the centre. Use a PCD bigger than "
            f"{format(2 * bolt_radius, 'g')} mm, or with_center_hole for one "
            f"hole in the middle")
    cutter = _tall_cutter(bolt_radius)
    result = part
    for loc in PolarLocations(radius=pitch_circle_dia / 2.0, count=count):
        result = result - (loc * cutter)
    return _drilled("with_bolt_circle", part, result,
                    f"a pitch circle diameter of "
                    f"{format(pitch_circle_dia, 'g')} mm puts all {count} "
                    f"holes outside this body")


def polar_pattern(feature: Part, count: int, **kw) -> Part:
    """The union of `count` copies of `feature`, evenly rotated about Z — the
    N-fold symmetric parts (impeller blades) the AI builds from ONE feature.
    Lives in pattern.py now (P4: a pattern repeats a FEATURE too; see there
    for `axis`, `angle`, `seed`); this name stays for the legacy callers."""
    from pattern import polar_pattern as op
    return op(feature, count, **kw)


# ---------------------------------------------------------------------------
# Transform / finishing operations (E1) — take a part, return a new part
# ---------------------------------------------------------------------------

def body_centre(part: Part) -> list[float]:
    """The centre of a body's bounding box — the pivot Fusion's Move/Rotate
    uses by default, and the ONE place the Rotate tool's ring and the `rotate`
    op both take it from (specs/move-rotate.md): the handle can never sit where
    the body does not turn. Exact on a box, a cylinder and a sphere
    (probes/move_rotate_probe.py §3)."""
    c = part.bounding_box().center()
    return [float(c.X), float(c.Y), float(c.Z)]


def _rotate_pivot(part: Part, pivot):
    """`pivot` in its three spellings, or the sentence: None / "origin" is the
    WORLD origin (the legacy behaviour every saved design was built with),
    "center" the body's own centre, [x, y, z] an explicit point."""
    if pivot is None or pivot == "origin":
        return (0.0, 0.0, 0.0)
    if pivot == "center":
        return tuple(body_centre(part))
    try:
        x, y, z = (float(v) for v in pivot)
        if not all(math.isfinite(v) for v in (x, y, z)):
            raise ValueError
        return (x, y, z)
    except (TypeError, ValueError):
        raise ValueError(f'rotate: pivot must be "center", "origin" or [x, y, z] '
                         f"(got {pivot!r})") from None


def rotate(part: Part, axis: str = "Z", angle_deg: float = 90.0, pivot=None) -> Part:
    """Rotate a part about the X, Y or Z direction through `pivot`. The way to
    lay a cylinder on its side: rotate(wheel, "X", 90).

    `pivot` (specs/move-rotate.md): absent / "origin" turns about the WORLD
    ORIGIN — a body that does not sit on the origin MOVES as it turns, the
    behaviour every design saved before 2026-09-11 relies on, so it stays the
    default; "center" turns the body IN PLACE about its own bounding-box centre
    (what the Rotate tool sends, Fusion's default pivot); [x, y, z] is an
    explicit point. The sign is the right-hand rule about the axis (probed:
    +90 about Z takes +X to +Y)."""
    # `axis not in _AXES` alone HASHES what it is given, so a file holding a
    # list or a dict there answered `TypeError: cannot use 'list' as a dict
    # key (unhashable type: 'list')` — the refusal's OWN lookup was the leak
    # (measured 2026-09-17, probes/s10_r3_valueerror_census.py).
    if not isinstance(axis, str) or axis not in _AXES:
        raise ValueError(f'rotate: axis must be "X", "Y" or "Z" (got {axis!r})')
    try:
        deg = float(angle_deg)
        if not math.isfinite(deg):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(f"rotate: angle_deg must be a number in degrees "
                         f"(got {angle_deg!r})") from None
    p = _rotate_pivot(part, pivot)
    if p == (0.0, 0.0, 0.0):
        return part.rotate(_AXES[axis], deg)
    return part.rotate(Axis(p, _AXES[axis].direction), deg)


def mirror_copy(part: Part, plane="YZ", join: bool = False) -> Part:
    """`mirror` in a script — ONE grammar with the feature tree's op
    (`pattern.mirror`, specs/mirror.md). `plane` is an origin plane name
    ("XY" / "XZ" / "YZ"), the body's mid-plane ({"mid": "X"}) or an explicit
    {"origin", "normal"}; `join=True` returns the part fused with its
    reflection (Fusion's Join: one symmetric solid), the default the reflected
    COPY alone, as every older script expects. A picked face needs the tree."""
    import pattern                      # pattern -> sketch -> blocks: never at import time
    return pattern.mirror(part, plane, join=join)


def scale_uniform(part: Part, factor: float) -> Part:
    """Uniformly scale a part about its own SHAPE CENTRE, so the body stays
    where it is (2 = double size).

    Measured 2026-09-10: build123d's scale() is centre-based, not
    origin-based, and this said "about the origin" for as long as it existed.
    `rotate` above turns about the WORLD origin unless given a `pivot` (the
    Rotate tool sends "center"), so a script's two Transform calls do NOT share
    a pivot by default -- stated here and in author.OP_NOTES because a wrong
    pivot is not visible in a signature."""
    # `factor <= 0` alone compared whatever it was given: a script passing
    # "2" answered `TypeError: '<=' not supported between instances of 'str'
    # and 'int'`, and True scaled by 1 without a word. The sentence also says
    # WHAT it got now — every other refusal in this file does.
    _numbers("scale", "times (2 = double size)", factor=factor)
    if factor <= 0:
        raise ValueError(f"scale: factor must be more than 0 (got "
                         f"{format(factor, 'g')}) — 2 is double size, 0.5 is "
                         f"half")
    return _b3d_scale(part, by=factor)


def linear_pattern(feature: Part, count: int, dx: float = 0.0,
                   dy: float = 0.0, dz: float = 0.0, **kw) -> Part:
    """Union of `count` copies of a feature stepped by (dx, dy, dz) each time
    (copy 0 stays in place), e.g. a row of 4 wheels: count=4, dx=30. Lives in
    pattern.py now (P4: `direction`, `distance`, a second direction, `seed`);
    this name stays for the legacy callers."""
    from pattern import linear_pattern as op
    return op(feature, count, dx, dy, dz, **kw)


# ---------------------------------------------------------------- edges ----
# Fillet / Chamfer take edges TWO ways (specs/fillet-chamfer.md): a GROUP name
# (the AI's vocabulary: "all" / "top" / ...) or a list of PICKED edges stored by
# GEOMETRY — never by index, which the next upstream change would reshuffle.
# A picked edge is "the edge shared by these two faces", each face by its
# centre + normal (resolve_face, the rule the face pick already lives by), with
# the midpoint as the tie-breaker when the faces share several edges. Probed
# 2026-09-04 (probes/fillet_edges_probe.py): after a chamfer ATE the edge the
# resolved faces share nothing and the feature says so, where the nearest
# midpoint would have quietly rounded the bevel's new edge instead. The same
# probe found the second banned failure live: a fillet larger than the corner
# fillet next to it "succeeds" as an INVALID solid — so every result is
# health-checked before it is returned.

_EDGE_RULES = ("all", "top", "bottom", "vertical", "horizontal")


def _pick_point(v, name: str) -> tuple:
    """The three numbers a face click left behind, or a sentence naming them.

    `cx, cy, cz = (float(v) for v in face_center)` was the whole of it, so a
    file that holds something else for a pick answered in Python: measured
    2026-09-17 over every parameter of every op
    (probes/s10_r3_valueerror_census.py), `face_center: "abc"` reached the
    feature row as `could not convert string to float: 'a'` and `[1, 2]` as
    `not enough values to unpack (expected 3, got 2)` — 36 rows of the census,
    not one of them naming the thing to change.

    As WIDE as what works today, on purpose: any sequence of three values
    `float()` accepts, so a list, a tuple and even ["0", "0", "5"] resolve
    exactly as they did. Only a word, a mapping, a flag and anything that is
    not three numbers are new refusals, and none of those builds anything
    today — a 3-letter string is the one that would have quietly become a
    point if `float()` were simply let loose on it."""
    if isinstance(v, (str, bytes, bytearray, dict, bool)):
        vals = None
    else:
        try:
            vals = [float(x) for x in v]
        except (TypeError, ValueError):
            vals = None
    if vals is None or len(vals) != 3:
        raise ValueError(
            f"{name} must be three numbers [x, y, z] from a face click (got "
            f"{v!r}) — click the face again, or name the face instead with "
            f'face="top" / "bottom" / "+x" …')
    return tuple(vals)


def resolve_face(solid, face_center: list, face_normal: list | None = None,
                 face_area: float | None = None):
    """Find the face of `solid` a user picked, by GEOMETRY (nearest center among
    the faces that still point the picked way) — so a stored pick survives
    parameter changes instead of breaking like a face index would. Shared by
    sketch_on_face, extrude_face, the face-outline projection and the edge pick
    (two faces name an edge).

    THE DIRECTION IS A GATE, NOT A NUDGE (review of 9e04ff6, 2026-09-11). It
    used to be a nudge: `d += (1 - align) * 25`, a penalty of 50 mm² for a face
    pointing the OTHER way, competing against SQUARED millimetres. So the
    moment a body was translated further than about its own thickness, the
    nearest face was the opposite one and it won. Measured on the Move tool's
    own documented journey — move a plate, sketch a Ø12 boss on the top face it
    now shows, extrude, fuse, then re-open Move and drag: past +7 mm on a 10 mm
    plate the boss jumped to the BOTTOM face, was built UP INTO the material and
    swallowed whole. 565 mm³ of the user's part gone, every tree row `ok`, not
    a word said. A pick that carried a direction never means a face facing away
    from it, so those faces are not candidates at all; when NONE is left the
    answer is a sentence, because a failed feature beats a body built on a face
    nobody chose. Measured inert on the saved library: 47 resolutions, none of
    them more than 60° off (probes/move_review_probe.py §8).

    A TIE IS STILL A COIN TOSS, and deliberately left one (2026-09-16,
    LAUNCH-PLAN §10). Two faces can be at the SAME place pointing the SAME way:
    a round pocket with a flush pad in it has an outer top of 893.142 mm2 and a
    pad top of 314.159 mm2 whose centroids are both (0, 0, 10) — one stored
    pick, two faces, and `min` answers with whichever the kernel lists first
    (probes/face_pick_frame_probe.py §2). Refusing it was built and MEASURED
    OUT again: a post inside a ring is two concentric lumps whose top faces tie
    exactly, and Shell asks this question once per lump, so the refusal turned
    a shell the kernel builds perfectly into a failure
    (tests/test_shell_tool.py::test_concentric_lumps_a_post_inside_a_ring
    _still_shell). It is not silent geometry either — the wrong face shows up
    on the very first click and the answer is stable across rebuilds, so the
    fix was always going to be the picker SAYING WHICH, not the resolver
    guessing. A pick that carries its size now does say which: the same pocket
    and pad answer 113.097 or 885.841 mm2 as asked
    (tests/test_face_pick_size.py). Without one it is still the coin toss.

    THE SIZE IS A GATE TOO, when the pick carries one (2026-09-16). The pick
    is remembered in WORLD coordinates, and on a stepped body — a plate with a
    boss, two faces pointing +Z — that used to be enough to lose it. A pick on
    the boss top survives a rigid move only as far as HALF the step: at
    dz = 2.49 mm it is still the boss top (201.06 mm2), at dz = 2.50 it is the
    plate top (998.94 mm2), and the design silently becomes 18000.0 mm3 where
    14010.62 was asked for, every row `ok`, the solid valid. A pure PARAMETER
    change does the same thing with no move to carry anything: thicken that
    plate from 10 to 14 and the boss top steps out of reach in exactly the
    same way (probes/face_pick_frame_probe.py §1 and §4). The two are
    ARITHMETICALLY IDENTICAL from a (centre, normal) pick — candidates 1 mm
    and 4 mm away, one right and one wrong — so distance cannot separate them
    and no carry can reach the second one.

    What separates them is the fact the click already knew and threw away: how
    BIG the face was. `face_area` is the area of the face at the moment it was
    clicked (the server measured it for the viewport's pick panel long before
    this, so nothing new is computed and nothing is derived in the browser —
    R1). Among the faces that still point the picked way, the ones that are
    still that size are the candidates; distance decides between THEM, which
    is what makes four identical bosses still resolve one each. It FAILS OPEN
    on purpose: if no face is that size any more — the picked face was itself
    resized, a `scale` ran, the design predates the field — the gate is
    skipped entirely and the answer is exactly what it was before, so this
    cannot turn a correct old answer into a new wrong one.

    WHAT IT STILL CANNOT DO: a pick with no stored area (every design saved
    before 2026-09-16) is resolved by centre and direction alone, exactly as
    described above, and a face that changes size AND has a same-size
    neighbour is still a coin toss. The move half is closed where the answer
    IS known — Document.edit carries every pick downstream of a `move` by that
    move's own delta."""
    rows = _face_rows(solid)
    if not rows:
        raise ValueError("solid has no faces")
    cx, cy, cz = _pick_point(face_center, "face_center")
    nrm = None
    if face_normal:
        nx, ny, nz = _pick_point(face_normal, "face_normal")
        if math.sqrt(nx * nx + ny * ny + nz * nz) > 1e-6:
            nrm = (nx, ny, nz)

    def facing(row):
        n, planar = row[2], row[3]
        # ONLY A PLANE has one normal everywhere, so only a plane can be ruled
        # out by direction. A curved face's `normal_at(center)` is the normal at
        # ONE point (a sphere's is not even defined there) while the stored
        # normal came from a raycast at the point CLICKED, so comparing the two
        # says nothing — those faces keep their chance and the caller's own
        # "that surface is curved" refusal speaks, as it always did.
        if not planar or n is None:
            return True
        return (n[0] * nrm[0] + n[1] * nrm[1] + n[2] * nrm[2]) > 0.0

    cands = [r for r in rows if facing(r)] if nrm else rows
    if not cands:
        raise ValueError(
            "the face this was put on does not point that way on the body any "
            "more — it has been turned over. Pick the face again, or undo the turn.")
    cands = _still_that_size(solid, cands, face_area)

    def score(row):
        _f, (x, y, z), n = row[0], row[1], row[2]
        d = (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2
        if nrm and n is not None:
            align = n[0] * nrm[0] + n[1] * nrm[1] + n[2] * nrm[2]
            d += (1.0 - align) * 25.0          # among same-facing faces: the flattest match
        return d

    return min(cands, key=score)[0]


# How close two areas have to be to be "the same face, still". Wide enough to
# ride out tessellation and rounding (a stored area is rounded to 2 decimals
# for the file) and the millimetre-scale trimming a neighbouring edit does to a
# face's rim; far tighter than the step between the faces this tells apart (a
# boss top against the plate top around it: 201.06 mm2 against 998.94).
_SIZE_TOL = 0.02
# ...and never tighter than this in absolute terms. A stored area is rounded to
# two decimals, so it sits at most 0.005 mm2 off the truth; on a face under
# about 0.25 mm2 that is already more than 2 per cent, and without a floor such
# a face could fail to match ITSELF — harmless, because the gate fails open,
# but it would quietly do nothing on small features, which is exactly where
# picks are hardest. 0.01 is twice the worst rounding error and no more: a
# looser floor would start matching one sliver to another.
_SIZE_FLOOR = 0.01


def _still_that_size(solid, cands: list, face_area: float | None) -> list:
    """The candidates that are still the size the picked face was.

    FAILS OPEN, and that is the whole safety argument: no stored area (every
    pick made before 2026-09-16) or no candidate anywhere near it (the picked
    face was itself resized) leaves the list exactly as it came in, so the
    answer is the one resolve_face would have given before this existed."""
    try:
        a0 = float(face_area)
    except (TypeError, ValueError):
        return cands
    if not (a0 > 0) or not math.isfinite(a0):
        return cands
    areas = _face_areas(solid)
    same = []
    for r in cands:
        a = areas.get(_shape_key(r[0]))
        if a is not None and abs(a - a0) <= max(_SIZE_TOL * max(a, a0),
                                                _SIZE_FLOOR):
            same.append(r)
    return same or cands


def _face_rows(solid) -> list:
    """(face, centre, normal, planar) for every face of a shape, measured ONCE per shape
    object and kept beside it (_cached). resolve_face is asked for BOTH stored
    faces of every picked edge on every plan, and a face centre is a BRepGProp
    integration (0.14 ms): 254 faces x 96 calls was 15 s of a 33 s click on
    esp32-remote (profiled 2026-09-08). A face the kernel will not measure is
    never the nearest; a normal it will not give costs that face its nudge, as
    before."""
    return _cached(solid, "faces", lambda: _measure_face_rows(solid))


def _measure_face_rows(solid) -> list:
    rows = []
    for f in solid.faces():
        try:
            c = f.center()
        except Exception:
            continue
        try:
            n = f.normal_at(c)
            n = (float(n.X), float(n.Y), float(n.Z))
        except Exception:
            n = None
        # by SURFACE TYPE on purpose, not geometrically: this flag only ever
        # TIGHTENS resolve_face's direction gate, so a dead-flat wall the kernel
        # types BSPLINE is left on the loose old path rather than risked
        try:
            planar = str(f.geom_type).split(".")[-1] == "PLANE"
        except Exception:
            planar = False
        rows.append((f, (float(c.X), float(c.Y), float(c.Z)), n, planar))
    return rows


def _face_areas(solid) -> dict:
    """face -> its area, for the faces _face_rows measured, in its own cache
    slot. SEPARATE from the rows on purpose: an area is a second BRepGProp
    integration, as dear as the centre (4.5 ms against 3.2 ms over 36 faces),
    and only a pick that carries a size ever asks for one — so a design saved
    before there was such a thing, and every plan that resolves by name or by
    direction, pays nothing at all."""
    return _cached(solid, "face_areas",
                   lambda: {_shape_key(r[0]): area_of(r[0])
                            for r in _face_rows(solid)})


def area_of(face) -> float | None:
    """A face's area, or None when the kernel will not measure it. ONE home,
    because there were three: toolplan and pattern each had their own copy of
    this try/except, and a pick's size has to mean the same thing in the plan
    that writes it and the resolver that reads it."""
    try:
        return float(face.area)
    except Exception:
        return None


def stored_area(face) -> float | None:
    """The same area as it gets WRITTEN DOWN — two decimals, the same rounding
    the viewport's own face payload uses (studio._body_payload), so a pick and
    the plan that re-derives it cannot disagree in the sixth decimal."""
    a = area_of(face)
    return None if a is None else round(a, 2)


def _shape_key(shape):
    """Identity of a TopoDS shape (its TShape hash — unique within one part,
    1.5 us; see studio._shape_key for the measurement)."""
    return hash(shape.wrapped)


def _v3(v) -> list[float]:
    return [round(float(v.X), 4), round(float(v.Y), 4), round(float(v.Z), 4)]


def _gtype(edge) -> str:
    return str(edge.geom_type).split(".")[-1]


# id(shape) -> [the shape, {slot: (its TopoDS shape, its hash, value)}]
_SHAPE_CACHES = OrderedDict()
_MAX_SHAPE_CACHES = 8       # bodies; ~1.3 MB of python wrappers each at 200 faces


def _cached(shape, slot: str, build):
    """A per-shape memo that lives BESIDE the shape, never on it. Stored as an
    attribute it rides along in build123d's __deepcopy__ — and moved() /
    `Pos * part` copy first and move second, so a moved body inherited its
    parent's face centres at the OLD position and resolve_face named the wrong
    face (probes/shape_cache_probe.py; the fast tier caught it on a moved
    plate).

    Keyed on the IDENTITY of the python object, so a copy is a miss, and
    BOUNDED, oldest out. A weak key could never expire here: the memo holds the
    shape's own Faces and Edges and every one of them points back at the shape
    (Face.topo_parent), so the value kept its own key alive and every
    superseded body stayed in the process for good — 8 throwaway bodies, 8 live
    entries (probes/shape_cache_leak_probe.py §1).

    Freshness is TWO tests because an in-place `part.move()` mutates the SAME
    TopoDS shape: IsEqual then compares it with itself and says True, so the
    stored hash — which the move does change — is what catches it. (The old
    comment credited IsEqual; what actually saved that answer was hash(Part)
    changing, which orphaned the entry and inserted a second immortal one.)"""
    key = id(shape)
    ent = _SHAPE_CACHES.get(key)
    if ent is not None and ent[0] is shape:
        hit = ent[1].get(slot)
        if hit is not None and hit[1] == _shape_key(shape) \
                and hit[0].IsEqual(shape.wrapped):
            _touch(key)
            return hit[2]
    else:
        ent = [shape, {}]                  # holding the shape is what makes id() safe
    value = build()
    ent[1][slot] = (shape.wrapped, _shape_key(shape), value)
    _SHAPE_CACHES[key] = ent
    _touch(key)
    while len(_SHAPE_CACHES) > _MAX_SHAPE_CACHES:
        try:
            _SHAPE_CACHES.popitem(last=False)
        except KeyError:                   # another request evicted it first
            break
    return value


def _touch(key):
    """newest end of the memo — the body in hand must not be the one evicted"""
    try:
        _SHAPE_CACHES.move_to_end(key)
    except KeyError:                       # evicted between the read and here
        pass


def _edge_topo(part: Part) -> dict:
    """The topology an edge tool asks for over and over — every edge, which
    faces share each edge, which edges bound each face, and the two ends of
    every edge (the tangent chain's walk) — enumerated ONCE per built body and
    kept beside it (_cached; a rebuild is a new Part, so nothing goes stale).
    build123d's faces() / edges() are not memoised: on esp32-remote (254 faces,
    609 edges) faces() costs 33 ms and a face's edges() 11 ms, and one plan on
    a 48-edge selection paid for them again for EVERY stored edge — 33 s per
    click (profiled 2026-09-08; probes/feature_edges_probe.py --big)."""
    return _cached(part, "edges", lambda: _build_edge_topo(part))


def _build_edge_topo(part: Part) -> dict:
    edge_faces, face_edges = {}, {}
    for f in part.faces():
        es = list(f.edges())
        face_edges[_shape_key(f)] = es
        for e in es:
            edge_faces.setdefault(_shape_key(e), []).append(f)
    edges = list(part.edges())
    # vertex -> the edges ending there, each with its tangent AT that end; and
    # per edge its two (vertex, tangent) ends — so the chain walk is lookups
    # and dot products (evaluating tangents in the walk was 0.7 s a click)
    ends, edge_ends = {}, {}
    for e in edges:
        mine = []
        for t in (0.0, 1.0):
            try:
                p, tan = e @ t, e % t
            except Exception:
                continue                   # an edge the kernel will not place joins no chain
            vkey = (round(p.X, 4), round(p.Y, 4), round(p.Z, 4))
            ends.setdefault(vkey, []).append((e, tan))
            mine.append((vkey, tan))
        edge_ends[_shape_key(e)] = mine
    return {"edges": edges, "edge_faces": edge_faces, "face_edges": face_edges,
            "ends": ends, "edge_ends": edge_ends}


def _edge_faces(part: Part) -> dict:
    """edge key -> the faces that share it, for the whole part (cached: _edge_topo)."""
    return _edge_topo(part)["edge_faces"]


def _face_edges(part: Part, face) -> list:
    """the edges bounding a face of `part` (cached: _edge_topo)"""
    es = _edge_topo(part)["face_edges"].get(_shape_key(face))
    return es if es is not None else list(face.edges())


def edge_ref(part: Part, edge, faces_by_edge: dict | None = None) -> dict:
    """The STORED form of a picked edge: midpoint, direction, curve type and the
    two faces it separates (centre + normal each)."""
    faces_by_edge = faces_by_edge or _edge_faces(part)
    faces = []
    for f in faces_by_edge.get(_shape_key(edge), [])[:2]:
        c = f.center()
        try:
            n = f.normal_at(c)
        except Exception:
            n = f.normal_at()
        # the SIZE of each host face travels with the pick too, so a stored
        # edge is still found after a parameter change moves a same-facing
        # neighbour nearer than its own face (resolve_face's size gate).
        # read from the body's own cached areas rather than measuring here:
        # a fillet plan asks for dozens of edge_refs at two faces each, and an
        # area is a BRepGProp integration (71 ms for all 1266 faces of
        # esp32-remote's logo body, once, against 0.12 ms per face measured
        # one at a time). Rounded like every other stored area (stored_area).
        a = _face_areas(part).get(_shape_key(f))
        faces.append({"center": _v3(c), "normal": _v3(n),
                      "area": None if a is None else round(a, 2)})
    d = edge % 0.5
    # a stored direction has ONE sign: an edge comes out of a face with the
    # face's orientation, out of the part with its own — identity ignores sign
    if next((c for c in (d.X, d.Y, d.Z) if abs(c) > 1e-9), 1.0) < 0:
        d = -d
    return {"mid": _v3(edge @ 0.5), "dir": _v3(d), "type": _gtype(edge),
            "faces": faces}


def _nearest_edge(edges, ref: dict):
    mx, my, mz = (float(v) for v in ref["mid"])
    d = ref.get("dir")
    gt = ref.get("type")

    def score(e):
        m = e @ 0.5
        s = (m.X - mx) ** 2 + (m.Y - my) ** 2 + (m.Z - mz) ** 2
        if d:
            t = e % 0.5
            s += (1.0 - abs(t.X * d[0] + t.Y * d[1] + t.Z * d[2])) * 25.0
        if gt and _gtype(e) != gt:
            s += 100.0
        return s

    return min(edges, key=score)


def _poly_mid(points) -> list[float]:
    """The point half-way along a polyline's length — the viewport sends an
    edge's drawn points untouched (R1: no maths in JS); for a 2-point line this
    is the exact midpoint, for a 24-step circle it is within 0.1% of it."""
    pts = [tuple(float(c) for c in p) for p in points]
    if len(pts) == 1:
        return list(pts[0])
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    half, run = sum(seg) / 2, 0.0
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if run + L >= half and L > 0:
            t = (half - run) / L
            return [a[i] + (b[i] - a[i]) * t for i in range(3)]
        run += L
    return list(pts[-1])


def _edge_distance(edge, pt) -> float:
    """Distance from a point to the edge ITSELF — bounded by its ends, never the
    infinite line (probes/edge_point_distance_probe.py: 75 us a pair)."""
    ad = BRepAdaptor_Curve(edge.wrapped)
    g = gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))
    best = min(ad.Value(ad.FirstParameter()).Distance(g),
               ad.Value(ad.LastParameter()).Distance(g))
    ext = Extrema_ExtPC(g, ad)
    if ext.IsDone():
        for i in range(1, ext.NbExt() + 1):
            best = min(best, ext.SquareDistance(i) ** 0.5)
    return best


PICK_ON_EDGE_TOL = 0.05     # mm; the drawn points are the mesh's own nodes, to 1e-4


def _edge_under(part: Part, points, gtype: str | None = None):
    """The edge of `part` a drawn line lies ON — its two ends and its middle all
    within PICK_ON_EDGE_TOL of the edge — or None when it lies on none."""
    pts = [tuple(float(c) for c in p) for p in points]
    samples = (pts[0], pts[len(pts) // 2], pts[-1])
    best, best_d = None, None
    for e in _edge_topo(part)["edges"]:
        if gtype and _gtype(e) != gtype:
            continue
        d = 0.0
        for q in samples:
            d = max(d, _edge_distance(e, q))
            if d > PICK_ON_EDGE_TOL:
                break
        if d <= PICK_ON_EDGE_TOL and (best_d is None or d < best_d):
            best, best_d = e, d
    return best


def _shared_edges(part: Part, faces: list, sized: bool) -> list:
    """The edges the two stored host faces of an edge still have in common.

    resolve_face is a NEAREST match — it always returns something. When one of
    the two stored faces is gone, both can land on the SAME face, whose edges
    all "share" it: [] says so, so the caller's refusal is not skipped and the
    feature cannot quietly round a different edge."""
    fa, fb = (resolve_face(part, f["center"], f.get("normal"),
                           f.get("area") if sized else None) for f in faces)
    if _shape_key(fa) == _shape_key(fb):
        return []
    kb = {_shape_key(e) for e in _face_edges(part, fb)}
    return [e for e in _face_edges(part, fa) if _shape_key(e) in kb]


def resolve_edge(part: Part, ref: dict):
    """The edge of `part` a stored pick means — by the two faces it separates
    when the pick recorded them, else by the nearest midpoint (+ direction).
    Raises the sentence the feature shows when the edge is gone.

    A RAW viewport pick carries the drawn `points` of a line on screen instead:
    an edge of this body — or of the PREVIEW body a round is being tried on,
    whose unchanged and TRIMMED edges lie exactly on their parents while the
    round's own new rims lie on none. So the identity is "lies on", never
    "nearest midpoint": nearest answered a click on a new rim with the edge it
    replaced, and the click silently un-picked it."""
    if ref.get("mid") is None and ref.get("points"):
        e = _edge_under(part, ref["points"], ref.get("type"))
        if e is None:
            x, y, z = _poly_mid(ref["points"])
            raise ValueError(
                f"the line clicked at ({x:g}, {y:g}, {z:g}) is not an edge of this "
                f"body — it is a rim the round or bevel being previewed has made. "
                f"Click an edge of the body itself; the gold lines are the ones picked so far.")
        return e
    faces = ref.get("faces") or []
    if len(faces) == 2:
        # THE STORED SIZES GET THE FIRST SAY AND THE LAST WORD IS SIZELESS.
        # resolve_face narrows to the faces that are still the size the pick
        # recorded, which is what keeps a stored edge off a same-facing
        # neighbour — but when a host face is ITSELF resized the narrowing can
        # answer with a same-sized face somewhere else, and two faces that do
        # not meet make the refusal below fire on an edge that is sitting right
        # there. Measured 2026-09-16 (probes/section10_pick_probe2.py §4): a
        # plate with two pads whose tops are both 200 mm2, a chamfer on one
        # pad's top rim, and widening THAT pad 20 -> 24 mm turned the edge at
        # (-15, 0, 11) — alive at (-13, 0, 11) — into "an upstream change
        # removed it", a red feature. So a refusal has to be earned by BOTH
        # rules; the fall-back can only ever turn a refusal back into the
        # answer the resolver gave before the sizes existed.
        for sized in (True, False):
            shared = _shared_edges(part, faces, sized)
            if shared:
                return shared[0] if len(shared) == 1 else _nearest_edge(shared, ref)
            if not sized or not any(f.get("area") is not None for f in faces):
                break                    # no sizes: the second pass IS the first
        x, y, z = ref.get("mid", [0, 0, 0])
        raise ValueError(
            f"the picked edge at ({x:g}, {y:g}, {z:g}) is no longer on the "
            f"body — an upstream change removed it (the two faces it sat "
            f"between no longer meet). Re-pick the edges of this feature.")
    if len(faces) == 1:                         # a SEAM of a round face touches one face
        fa = resolve_face(part, faces[0]["center"], faces[0].get("normal"),
                          faces[0].get("area"))
        return _nearest_edge(_face_edges(part, fa), ref)
    if ref.get("mid") is None:
        raise ValueError("a picked edge needs its midpoint ('mid': [x, y, z]) — "
                         "pick it in the viewport")
    return _nearest_edge(_edge_topo(part)["edges"], ref)


def tangent_chain(part: Part, edge, tol: float = 0.99) -> list:
    """`edge` plus every edge smoothly connected to it (Fusion's tangent chain):
    walk shared vertices while the tangents agree. A rounded rim is one chain;
    a sharp box edge is a chain of one (probed 2026-09-04). The vertex table is
    the body's, built once (_edge_topo): rebuilding it here cost 265 ms per
    picked edge on esp32-remote."""
    topo = _edge_topo(part)
    ends, own = topo["ends"], topo["edge_ends"]
    seen = {_shape_key(edge)}
    out, todo = [edge], [edge]
    while todo:
        e = todo.pop()
        for vkey, tan in own.get(_shape_key(e), []):
            for other, otan in ends.get(vkey, []):
                if _shape_key(other) in seen:
                    continue
                if abs(tan.dot(otan)) > tol:
                    seen.add(_shape_key(other))
                    out.append(other)
                    todo.append(other)
    return out


def _pick_edges(part: Part, which: str):
    edges = part.edges()
    if which == "all":
        return edges
    if which == "top":
        return edges.group_by(Axis.Z)[-1]
    if which == "bottom":
        return edges.group_by(Axis.Z)[0]
    if which == "vertical":
        # edges parallel to Z — the 4 corner edges of a box (round-the-corners)
        picked = edges.filter_by(Axis.Z)
        if not picked:
            raise ValueError('no "vertical" edges (none run parallel to Z)')
        return picked
    if which == "horizontal":
        # edges lying flat (parallel to X or Y) — top+bottom rims
        picked = edges.filter_by(Axis.X) + edges.filter_by(Axis.Y)
        if not picked:
            raise ValueError('no "horizontal" edges (none parallel to X or Y)')
        return picked
    raise ValueError(f'edges must be one of {", ".join(_EDGE_RULES)}, or a list '
                     f"of picked edges")


def edges_for(part: Part, edges) -> list:
    """The edges an `edges` param names: a group name, or a list of picked
    edges (dicts from edge_ref, or bare [x, y, z] midpoints)."""
    if isinstance(edges, str):
        return list(_pick_edges(part, edges))
    if isinstance(edges, (list, tuple)):
        if not edges:
            raise ValueError("no edges picked — click at least one edge of the body")
        out, seen = [], set()
        for r in edges:
            if not isinstance(r, dict):
                # `{"mid": list(r)}` on its own answered `TypeError: 'int'
                # object is not iterable` for a list of bare numbers, and
                # `not enough values to unpack (expected 3, got 2)` for a
                # two-number point (measured 2026-09-17,
                # probes/s10_r3_valueerror_census.py).
                try:
                    r = {"mid": list(_pick_point(r, "a picked edge"))}
                except ValueError:
                    raise ValueError(
                        f"a picked edge is a point [x, y, z] on that edge "
                        f"(got {r!r}) — click the edge again, or name a "
                        f'group: {", ".join(_EDGE_RULES)}') from None
            e = resolve_edge(part, r)
            if _shape_key(e) not in seen:
                seen.add(_shape_key(e))
                out.append(e)
        return out
    raise ValueError(f'edges must be one of {", ".join(_EDGE_RULES)}, or a list '
                     f"of picked edges")


# OCCT's own vocabulary. A user-facing sentence never carries it (the same
# rule tests/gauntlet.py enforces), so a failure wearing it is named plainly.
_KERNEL_WORDS = ("TopoDS", "NCollection", "Standard_", "BRep", "StdFail",
                 "Geom_", "gp_", "TColStd", "BOPAlgo")


# Python's own two ways of saying "the parameters do not match the op". Both
# reach a feature row: a REQUIRED parameter left out (the AI could not tell it
# apart from an optional one — document.REQUIRED exists so the catalogue now
# can), and a parameter this build no longer has (a design written by another
# build opens on purpose, `Document.add` strict=False, and says so at the next
# rebuild). Both used to say it in Python.
_MISSING_ARGS = re.compile(
    r"^\w+\(\) missing \d+ required (?:positional|keyword-only) "
    r"arguments?: (?P<names>.+)$")
_UNKNOWN_ARG = re.compile(
    r"^\w+\(\) got an unexpected keyword argument '(?P<name>[^']+)'$")


def _name_and(names) -> str:
    """'a', 'a and b', 'a, b and c' — the joining document._name_list uses."""
    names = list(names)
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _missing_or_unknown_params(msg: str) -> str | None:
    """A TypeError about PARAMETERS turned into a sentence naming them.

    Only these two exact shapes; any other TypeError is our own bug and keeps
    saying so. The names come out of the message because this module cannot
    import `document` (document imports blocks), and because the same sentence
    has to serve a script and the kernel worker as well as a feature row."""
    m = _MISSING_ARGS.match(msg)
    if m:
        names = re.findall(r"'([^']+)'", m.group("names"))
        if names:
            return (f"{_name_and(names)} is required — set a value for it"
                    if len(names) == 1 else
                    f"{_name_and(names)} are required — set a value for each")
    m = _UNKNOWN_ARG.match(msg)
    if m:
        return (f"{m.group('name')} is not a parameter of this feature — "
                f"remove it")
    return None


# Where this file lives. Every module of the product is flat beside it
# (blocks, sketch, document, pattern, paramexpr, inspector, kernelguard …), so
# "our own code" is a directory test and no list has to be kept up to date.
_OUR_DIR = os.path.dirname(os.path.abspath(__file__))
_RAISE_OPS = ("RAISE_VARARGS", "RERAISE")

# What a failure says when it is NOT one of our sentences and not the kernel
# either: Python's own words name a Python fact, never the thing to change.
NOT_A_SENTENCE = ("one of this feature's values is not one it can use — open "
                  "the feature and check what is in each box")


def _python_raised_it(e: Exception) -> bool:
    """Did PYTHON raise this ValueError from inside one of OUR OWN files?

    `plain_cause` passes every `ValueError` through unchanged, on the
    assumption that a ValueError came from our code and is therefore already a
    sentence. It is not: `float("")`, `int("x")` and unpacking all raise
    ValueError from inside the lines we wrote. Measured 2026-09-17
    (probes/s10_r3_entity_value_door.py): a sketch entity whose `x` is a word
    read `could not convert string to float: 'abc'` in the feature row, and an
    empty one `could not convert string to float: ''` — the very message the
    §10 row was opened for.

    Two facts separate the two, and NEITHER of them reads the text (guessing a
    sentence from its wording is how the old assumption went wrong):

      * the innermost frame's FILE — build123d and OCP live elsewhere, and
        build123d's own refusals are plain, so they keep passing through;
      * the BYTECODE at that frame's last instruction — a `raise` we wrote is
        `RAISE_VARARGS` (or `RERAISE`), while Python raising on its own account
        inside one of our lines is a `CALL`, an `UNPACK_SEQUENCE`, a
        `BINARY_OP`… Measured over 24 of our own refusals across five modules
        and Python's own from three call sites: 24 RAISE_VARARGS, 0 misread
        (probes/s10_r3_raise_marker.py).

    SAFE IN ONE DIRECTION: anything this cannot read counts as OURS, so a
    refusal is never swallowed — the worst it can do is let a Python message
    through, which is what happens today anyway.

    A refusal handed across the kernel-worker boundary is still ours: it is
    re-raised by a `raise` statement in `kernelguard`, in this directory."""
    tb = e.__traceback__
    if tb is None:
        return False
    while tb.tb_next is not None:
        tb = tb.tb_next
    try:
        code = tb.tb_frame.f_code
        if os.path.dirname(os.path.abspath(code.co_filename)) != _OUR_DIR:
            return False                  # a library's ValueError: left alone
        for ins in dis.get_instructions(code):
            if ins.offset == tb.tb_lasti:
                return ins.opname not in _RAISE_OPS
    except Exception:
        return False                      # any doubt: it is one of ours
    return False


def plain_cause(e: Exception) -> str:
    """The REAL reason a build failed, in words a user can act on.

    build123d's own refusal is already plain; a raw OCP error is jargon, so it
    is named without its internals; anything else (a TypeError — our own bug)
    says what it is instead of being dressed up as a geometry problem. Never
    invent a diagnosis: before 2026-09-04 every failure here was reported as
    \"a face beside them is too small\", which was a guess for all but one of them.

    Document.rebuild uses this too, as the last barrier before a feature row is
    painted: it used to print `repr(e)`, so a zero thickness read
    `Standard_DomainError('')` and a string in a dimension printed twelve lines
    of pybind11 constructor overloads (measured 2026-09-10, section 5)."""
    msg = (str(e) or "").strip()
    if re.match(r"Failed creating a (fillet|chamfer)", msg):
        return "the kernel could not build it there"
    if not msg or any(w in msg or w in type(e).__name__ for w in _KERNEL_WORDS):
        return "the geometry kernel rejected the shape it would produce"
    if isinstance(e, TypeError):
        named = _missing_or_unknown_params(msg)
        if named:
            return named
    if isinstance(e, ValueError):
        # OUR ValueError is the refusal we wrote and already names what to
        # change. Python's own — `float("")`, `int("x")`, unpacking a pair
        # into three names — names a Python fact instead, and used to be
        # handed to the user word for word (see _python_raised_it).
        return NOT_A_SENTENCE if _python_raised_it(e) else msg
    # our own bug, or a binding complaining about an argument. Either way the
    # user gets ONE line: a pybind11 overload dump is not a sentence, and
    # anything multi-line came from a library, not from us.
    first = msg.splitlines()[0].strip()
    if len(msg.splitlines()) > 1 or len(first) > 200:
        return "the geometry kernel rejected the shape it would produce"
    return f"{type(e).__name__}: {first}"


# A blend is a LOCAL change: the corpus of every fillet and chamfer in the
# library (probes/fillet_result_corpus.py, 2026-09-13) moves between 0.204 and
# 0.377 of `value^2 x picked edge length` — the 90-degree ideals are 1 - pi/4 =
# 0.215 for a round and 0.5 for a bevel — and retracts the bounding box by at
# most 0.155 x value. These bounds leave that eight- and seventy-fold behind,
# because they exist to catch a kernel answer that is not a blend at all.
_BLEND_VOLUME_FACTOR = 3.0      # x value^2 x edge length
_BLEND_SHRINK_FACTOR = 12.0     # x value

# The 90-degree ideal itself: a round on a right-angled edge moves
# tan(45) - pi/4 of `radius^2` per mm of edge. Every figure above is a multiple
# of it, and the sharpness below is measured against it.
_BLEND_SQUARE_UNIT = math.tan(math.pi / 4) - math.pi / 4     # 0.2146

# A corner sharper than 5 degrees is a slit, not a corner: past it the formula
# below runs away (tan -> infinity) and the bound would stop bounding anything.
_BLEND_SHARP_CAP = 100.0


def _corner_sharpness(faces_of, edge) -> float:
    """How much more material a round on THIS edge moves than the same round on
    a right-angled one: 1.0 for a right angle or blunter, about 15 for a
    25-degree corner, 46 for a 10-degree spike. Never below 1.0, so a blunt
    edge keeps the flat bound above and nothing gets TIGHTER than it was.

    A round of radius r on an edge whose two faces meet at `a` (the angle
    between their normals) moves r^2 x (tan(a/2) - a/2) per mm of edge. Derived
    and then MEASURED to the fourth decimal on extruded wedges of 90, 30 and 10
    degrees (review of 2026-09-13). The same size holds for a CONCAVE crease,
    which ADDS that much instead of removing it, because tan((pi+x)/2)-(pi+x)/2
    is exactly the negative of tan((pi-x)/2)-(pi-x)/2 — so nothing here has to
    work out which way the corner turns, which is the kind of test that has
    refused correct geometry twice on this project already.

    WHY IT EXISTS. The flat bound refuses CORRECT geometry on any corner
    sharper than about 26 degrees. On the user's own spiderman-logo a round of
    0.2 mm on a 160.5-degree crease moved 0.0628 mm3 of a 26707 mm3 body —
    0.0002 per cent of it, bounding box untouched, health empty — and was told
    it was "not a blend of this body", blaming sliver faces on a sound part.
    rocky-balboa carries two such edges; a traced outline or a wing rib's
    trailing edge is where they come from."""
    if faces_of is None:
        return 1.0
    try:
        if not faces_of.Contains(edge.wrapped):
            return 1.0
        faces = faces_of.FindFromKey(edge.wrapped)
        if faces.Size() != 2:                # a seam, or a non-manifold edge
            return 1.0
        point = edge @ 0.5
        n0 = Face(faces.First()).normal_at(point)
        n1 = Face(faces.Last()).normal_at(point)
        a = math.acos(max(-1.0, min(1.0, n0.dot(n1))))
    except Exception:                        # a corner we cannot measure keeps
        return 1.0                           # the flat bound, never a looser one
    if a <= math.pi / 2:
        return 1.0
    if a >= math.radians(175.0):
        return _BLEND_SHARP_CAP
    return min(_BLEND_SHARP_CAP,
               max(1.0, (math.tan(a / 2) - a / 2) / _BLEND_SQUARE_UNIT))


def _blend_span(name: str, part: Part, picked) -> float:
    """The picked edge length the volume bound may spend, each edge counted by
    the sharpness of the corner it sits in.

    Only a ROUND grows with sharpness. A bevel of leg d removes
    d^2 x sin(a) / 2 per mm at ANY angle, which is largest at a right angle, so
    the flat bound is already a chamfer's worst case and a chamfer is counted
    plainly. One C++ pass for the edge -> faces map (TopExp), not
    `_edge_topo`: this runs in the kernel worker, on a body that has no cache,
    and `_edge_topo` also evaluates a tangent at both ends of every edge."""
    if name != "fillet":
        return sum(e.length for e in picked)
    try:
        m = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(part.wrapped, TopAbs_ShapeEnum.TopAbs_EDGE,
                                       TopAbs_ShapeEnum.TopAbs_FACE, m)
    except Exception:                        # no map: every edge counts plainly
        m = None
    return sum(e.length * _corner_sharpness(m, e) for e in picked)


def _bbox_retreat(before, after) -> float:
    """How far `after`'s bounding box pulled IN from `before`'s, mm, on its
    worst side. Growth reads negative: a blend fills a concave corner, it
    never pushes past a face it was tangent to."""
    return max(max(getattr(after.min, k) - getattr(before.min, k),
                   getattr(before.max, k) - getattr(after.max, k))
               for k in ("X", "Y", "Z"))


def _assert_is_a_blend(name: str, part: Part, out, picked, value: float, unit: str) -> None:
    """A fillet/chamfer the kernel called a success, MEASURED — because on the
    wrong body it hands back a different part and every check we had said fine.

    Measured 2026-09-13 (the overnight journey run, my-part-8 seed 46791,
    probes/fillet_eats_body.py): an `intersect` body of 181.499 mm3 — valid by
    BRepCheck_Analyzer, unchanged by `.clean()`, but carrying a ZERO-area
    cylindrical face and edges 0.00014 mm long — filleted on ONE picked edge at
    radius 0.4 came back 44.621 mm3. Valid. `inspector.health` empty. Three
    quarters of the part gone, a green row, and saved. Every one of its eight
    flat rims did the same (34-46 mm3 of 181.5, bounding box 50.67 mm wide
    collapsing to 1.0 mm); the same call on all eight at once SEGFAULTED, which
    no `except` can catch and this cannot help. The volume test alone misses the
    widest radius (3.8x, under the bound) and the box test alone is loose on a
    sharp wedge, so BOTH run: a real blend passes both by an order of magnitude.

    The volume half is per-CORNER, not per-mm (see `_corner_sharpness`): the
    flat bound refused correct rounds on anything sharper than 26 degrees, and
    the user's own logo designs have such edges. It costs the crash body
    nothing — its rims meet at 90 and 62.6 degrees, and both halves still
    refuse them at every radius by 2x and 10x (review of 2026-09-13)."""
    total = part.volume
    span = _blend_span(name, part, picked)
    moved = abs(out.volume - total)
    allowed = max(_BLEND_VOLUME_FACTOR * value * value * span, 1e-6 * abs(total))
    retreat = _bbox_retreat(part.bounding_box(), out.bounding_box())
    if moved <= allowed and retreat <= _BLEND_SHRINK_FACTOR * value:
        return
    n = len(picked)
    low = unit.lower()
    raise ValueError(
        f"{name}: the kernel accepted {low} {value:g} mm on {n} edge{'s' if n != 1 else ''} "
        f"but what it returned is not a blend of this body — "
        f"{total:.4g} mm3 became {out.volume:.4g} mm3"
        + (f" and it shrank by {retreat:.4g} mm" if retreat > _BLEND_SHRINK_FACTOR * value else "")
        + f". That happens on a body carrying sliver faces or near-zero-length "
        f"edges. Try a smaller {low}, pick different edges, or round the shape "
        f"before the step that made those slivers")


_BLEND_KERNEL = {
    "fillet": lambda es, v: _b3d_fillet(es, radius=v),
    "chamfer": lambda es, v: _b3d_chamfer(es, length=v),
}


def blend_after_guards(name: str, part: Part, picked, value: float, unit: str):
    """The half of a fillet/chamfer that can kill the process — the kernel call
    and the two measurements that judge what it hands back.

    Split out of `_finish` on 2026-09-13 so it can run in the kernel worker
    (kernelguard.py): `fillet` on eight picked rims of a sliver body dies with
    an access violation at every radius from 0.05 to 0.5, and no `except` in
    this process could ever see it. Both sides of the guard call THIS, so the
    in-process path and the worker path are the same code, not two copies."""
    n = len(picked)
    on = f"{n} edge{'s' if n != 1 else ''}"
    low = unit.lower()
    try:
        out = _BLEND_KERNEL[name](picked, value)
    except Exception as e:                      # OCP errors are Exception, not RuntimeError
        raise ValueError(f"{name}: {low} {value:g} mm does not fit on {on} — "
                         f"{plain_cause(e)}. Try a smaller {low}, or pick "
                         f"different edges.") from e
    # measured OUTSIDE that try on purpose: a health check that throws is our
    # own problem, and must never be reported as a value that "does not fit"
    problems = inspector.health(out, check_valid=False)
    if problems:
        raise ValueError(f"{name}: {low} {value:g} mm leaves a broken solid on {on} — "
                         f"{problems[0]}. It runs into a neighbouring face or round; "
                         f"try a smaller {low}.")
    # ... and healthy is not the same as RIGHT: measure what came back
    _assert_is_a_blend(name, part, out, picked, value, unit)
    return out


def _finish(name: str, part: Part, edges, value: float, unit: str):
    """Shared by fillet_edges / chamfer_edges: the value guard, the kernel call,
    the health check, and a refusal that says the TRUE reason.

    NOTHING here is speculative: the kernel is called ONCE, with the value the
    user asked for. A bisection for "the largest that would fit" used to run
    here — 10 more builds on every rebuild of a failing feature — and probing
    radii nobody typed is not merely slow: on the user's esp32-remote design
    (254 faces) a refused radius 4 made it try 2.0, and OCCT SEGFAULTED, taking
    the server and every unsaved tab with it (reproduced 2026-09-04, exit 139).

    The health check is the CHEAP one — Document.rebuild's own per-feature
    policy. OCCT's validity analysis is ~270 ms on a large solid, and the RESULT
    gets it anyway in the deep-check pass after the rebuild loop. It still
    catches the second banned failure: a round larger than the round beside it
    comes back as a solid the kernel ACCEPTS, and it is not watertight
    (measured 2026-09-04 — the manifold check sees it, validity adds nothing)."""
    if value is None or not value > 0:
        raise ValueError(f"{name}: {unit} must be positive (got "
                         f"{'nothing' if value is None else format(value, 'g')}) — "
                         f"drag the handle or type a value")
    picked = edges_for(part, edges)
    n = len(picked)
    on = f"{n} edge{'s' if n != 1 else ''}"
    low = unit.lower()
    import kernelguard                           # local: kernelguard reads blocks
    return kernelguard.guarded(
        "blend", part,
        {"kind": name, "value": value, "unit": unit,
         "picks": kernelguard.indices(part.edges(), picked),
         "marks": kernelguard._marks(picked),
         "crashed":
             f"{name}: {low} {value:g} mm on {on} {kernelguard.CRASH_PHRASE} — "
             f"nothing was changed and the app is unharmed. That happens on a "
             f"body carrying sliver faces or near-zero-length edges. Try a "
             f"smaller {low}, pick fewer edges, or round the shape before the "
             f"step that made those slivers.",
         "stopped":
             f"{name}: {low} {value:g} mm on {on} {kernelguard.STOPPED_PHRASE} "
             f"<minutes> and nothing was changed. Rounding every edge of a "
             f"traced outline can take that long. Pick fewer edges, or try a "
             f"smaller {low}."},
        lambda: blend_after_guards(name, part, picked, value, unit))


def fillet_edges(part: Part, radius: float, edges="all") -> Part:
    """Round edges with a radius. `edges`: "all", "top", "bottom", "vertical"
    (the 4 upright corner edges — for rounding the corners of a box/enclosure),
    "horizontal" (the flat top+bottom rims), or a LIST of picked edges (see
    edge_ref). The radius must be smaller than the neighbouring faces allow;
    the refusal names the largest that fits."""
    return _finish("fillet", part, edges, radius, "radius")


def chamfer_edges(part: Part, length: float, edges="all") -> Part:
    """Cut a flat 45-degree bevel on edges. `edges` as for fillet_edges."""
    return _finish("chamfer", part, edges, length, "distance")


def shell_out(part: Part, thickness: float = 0.0, faces=None, direction: str = "inside",
              open_face=None) -> Part:
    """Fusion's Shell — `sketch.shell`, the tree's op, under the name the script
    path (generate.py, blocks.EXPORTS) has always used: ONE grammar for both.
    `faces` are the openings (names or picks), none = a closed hollow; the
    legacy `open_face` still works. Imported lazily: sketch imports this module."""
    import sketch                                     # local: avoids an import cycle
    return sketch.shell(part, thickness, faces, direction, open_face)


# ---------------------------------------------------------------------------
# Mesh import (STL from outside sources)
# ---------------------------------------------------------------------------

IMPORTS_DIR = Path(__file__).parent / "imports"   # UI uploads land here
MAX_STL_TRIANGLES = 20_000                        # keeps rebuild + display usable


def _stl_triangles(data: bytes) -> tuple[str, int]:
    """('ascii'|'binary', triangle count) without a full parse. ASCII is
    detected by content, not just the 'solid' prefix — some binary exporters
    put 'solid' in the 80-byte header too, so the size formula decides."""
    # a Windows text editor's UTF-8 byte-order mark is not part of "solid":
    # with it in front, the text read as a binary header and was called "cut
    # short — its header says 824,211,557 triangles" (section 8, round two)
    head = data[:83].removeprefix(b"\xef\xbb\xbf").lstrip()
    if head.startswith(b"solid") and b"facet" in data:
        return "ascii", data.count(b"facet normal")
    if len(data) >= 84:
        (n,) = struct.unpack_from("<I", data, 80)
        have = (len(data) - 84) // 50
        if n and have >= n:
            return "binary", n
        if n == 0 and len(data) == 84:        # a genuinely empty binary STL
            return "binary", 0
        if n and have and n <= 50_000_000:     # a plausible count (2.5 GB)
            # a part-downloaded or truncated file used to read "not an STL
            # file", a diagnosis it does not deserve (section 8 review)
            raise ValueError(
                f"import_stl: this STL file is cut short — its header says "
                f"{n:,} triangles but only {have:,} are in the file. Export or "
                "download it again.")
    if head.startswith(b"solid"):
        return "ascii", 0
    raise ValueError("import_stl: not an STL file (neither binary nor ascii STL)")


def _ascii_stl_to_binary(data: bytes) -> bytes:
    """lib3mf's STL reader only accepts BINARY STL — ascii files fail with a
    cryptic 'Reading from a stream was not possible'. Convert up front."""
    verts = re.findall(
        rb"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", data)
    if not verts or len(verts) % 3:
        raise ValueError("import_stl: malformed ascii STL "
                         "(vertex count is not a multiple of 3)")
    out = bytearray(b"\0" * 80)
    out += struct.pack("<I", len(verts) // 3)
    for i in range(0, len(verts), 3):
        out += struct.pack("<3f", 0.0, 0.0, 0.0)   # normals recomputed on read
        for v in verts[i:i + 3]:
            out += struct.pack("<3f", float(v[0]), float(v[1]), float(v[2]))
        out += struct.pack("<H", 0)
    return bytes(out)


def _bbox_holds(outer, inner, tol: float = 1e-6) -> bool:
    """Does `outer`'s bounding box contain `inner`'s?"""
    return all(getattr(outer.min, a) <= getattr(inner.min, a) + tol
               and getattr(outer.max, a) >= getattr(inner.max, a) - tol
               for a in ("X", "Y", "Z"))


def _outward(shell) -> tuple:
    """(TopoDS_Shell wound outward, its Solid, was the FILE's winding inward).
    A closed shell's orientation is ours to set from its role; what the file
    said is kept as a hint — an inward shell that sits inside a body is the
    cavity the file says it is, and needs one confirming point, not a survey."""
    sol = Solid(BRepBuilderAPI_MakeSolid(shell.wrapped).Solid())
    if sol.volume < 0:
        tsh = TopoDS.Shell_s(shell.wrapped.Reversed())
        return tsh, Solid(BRepBuilderAPI_MakeSolid(tsh).Solid()), True
    return shell.wrapped, sol, False


_NEST_SAMPLE = 400      # vertices sampled per shell, and as many face centres
_NEST_BUDGET = 100_000  # face-evaluations the classifier may spend per kind


def _nest_cap(container_faces: int) -> int:
    """How many vertices (and as many face centres) to test against a
    container of that many faces. OCCT's point classifier is LINEAR in the
    container's faces — ~5 us a face, so 173 ms a point against a 32k-face
    body (probes/s8r4_b_bigcontainer.py) — and round three's fixed 400 + 400
    would have taken ~140 s for one cavity. The budget keeps it near a
    second: 8 + 8 points against 32k faces, 100 + 100 against 1k."""
    return max(8, min(_NEST_SAMPLE, _NEST_BUDGET // max(1, container_faces)))


def _spread(n: int, cap: int):
    """1-based indices into a map of n: all of them, or `cap` spread evenly."""
    return range(1, n + 1) if n <= cap else [1 + (k * n) // cap for k in range(cap)]


def _shell_points(shell, cap: int = _NEST_SAMPLE) -> list:
    """Points ON a shell: up to `cap` of its unique vertices and as many face
    centres, spread over the whole shell. TopExp.MapShapes does the walk in
    C++ — build123d's .vertices() took 1.8 s on a 32k-triangle shell and a
    Python explorer 3.8 s; this takes 0.15 s (probes/s8r3_d_mapshapes.py)."""
    pts = []
    vm = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shell.wrapped, TopAbs_ShapeEnum.TopAbs_VERTEX, vm)
    for i in _spread(vm.Extent(), cap):
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vm.FindKey(i)))
        pts.append((p.X(), p.Y(), p.Z()))
    fm = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shell.wrapped, TopAbs_ShapeEnum.TopAbs_FACE, fm)
    for i in _spread(fm.Extent(), cap):
        sub = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(fm.FindKey(i), TopAbs_ShapeEnum.TopAbs_VERTEX, sub)
        x = y = z = 0.0
        for j in range(1, sub.Extent() + 1):
            p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(sub.FindKey(j)))
            x, y, z = x + p.X(), y + p.Y(), z + p.Z()
        pts.append((x / sub.Extent(), y / sub.Extent(), z / sub.Extent()))
    return pts


def _shell_inside(shell, solid, points=None) -> bool:
    """Is `shell` WHOLLY inside `solid`? The bounding boxes pre-filter; then
    every sampled vertex AND face centre of the shell must classify IN on an
    OUTWARD solid (against an inward one OCCT says OUT of a point that is
    inside — probed 2026-09-12, probes/s8r2_e_orient.py).

    ONE vertex was not enough (round three, 2026-09-12): a bracket overlapping
    the notch of a C-shaped frame has a corner inside the frame's material,
    and it became a VOID of the frame — 640 mm3 gone from a 21,640 mm3 pair,
    valid and green. Face centres catch the pin whose ends are embedded in two
    walls while its middle spans the gap between them: every vertex inside,
    not one face. A body that pokes out by less than one sampled point in 400
    still reads as a void, and MakeSolid.Add then builds an INVALID solid,
    which the deep validity pass paints red — wrong, but never silent."""
    if not _bbox_holds(solid.bounding_box(), shell.bounding_box()):
        return False
    cls = BRepClass3d_SolidClassifier(solid.wrapped)
    for x, y, z in (_shell_points(shell) if points is None else points):
        cls.Perform(gp_Pnt(x, y, z), 1e-7)
        if cls.State() != TopAbs_State.TopAbs_IN:
            return False
    return True


def _solids_from_shells(shp) -> tuple[list, int]:
    """A shape that is not one valid solid, exploded into shells and regrouped
    into bodies by NESTING DEPTH: a shell inside no other is a body; a shell
    directly inside a body is a sealed void of that body; a shell inside a
    void is a body again (a loose part sealed in a cavity). Each shell is then
    wound to fit its role — outward for a body, inward for a void — whatever
    the file said. MakeSolid.Add needs the void inward (outward, the same
    void gave 1064 mm3 and an invalid solid), and the file's winding is
    exactly what an inside-out export gets wrong: deciding void-or-body by the
    SIGN of each shell's volume, a hollow part wound inside-out still came in
    as 1064 mm3 in two bodies (section 8 round two, 2026-09-12)."""
    closed, open_shells = [], 0
    for sh in shp.shells():
        if not BRep_Tool.IsClosed_s(sh.wrapped):
            open_shells += 1
            continue
        closed.append((sh, *_outward(sh)))  # (Shell, outward TopoDS_Shell, Solid, inward?)
    n = len(closed)
    sampled: dict = {}                     # (shell index, cap) -> sample points, once
    faces: dict = {}                       # shell index -> its face count, once

    def nested(i, j):
        """Is shell i wholly inside body j? One point says whether it sits
        inside at all. If it does and the FILE wound it inward, it is the
        cavity the file says it is. If the file wound it OUTWARD — a cavity
        MeshLab re-oriented, or a body embedded in / overlapping j — only its
        surface can tell, and that survey is sized to what j costs to ask."""
        sh_i, _, _, inward_i = closed[i]
        sol_j = closed[j][2]
        if i == j or not _bbox_holds(sol_j.bounding_box(), sh_i.bounding_box()):
            return False
        if not _shell_inside(sh_i, sol_j, _shell_points(sh_i, 1)):
            return False
        if inward_i:
            return True
        if j not in faces:
            fm = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(sol_j.wrapped, TopAbs_ShapeEnum.TopAbs_FACE, fm)
            faces[j] = fm.Extent()
        cap = _nest_cap(faces[j])
        if (i, cap) not in sampled:
            sampled[i, cap] = _shell_points(sh_i, cap)
        return _shell_inside(sh_i, sol_j, sampled[i, cap])

    inside = [[nested(i, j) for j in range(n)] for i in range(n)]
    depth = [sum(row) for row in inside]
    out = []
    for i, (_, tsh, sol, _) in enumerate(closed):
        if depth[i] % 2:
            continue                             # a void: added to its body below
        voids = [j for j in range(n) if depth[j] == depth[i] + 1 and inside[j][i]]
        if not voids:
            out.append(sol)
            continue
        mk = BRepBuilderAPI_MakeSolid(tsh)
        for j in voids:
            mk.Add(TopoDS.Shell_s(closed[j][1].Reversed()))
        out.append(Solid(mk.Solid()))
    return out, open_shells


def _stl_bytes_to_solids(data: bytes) -> tuple[list, int]:
    """One binary STL through lib3mf into closed Solids. Returns
    (solids, open_shell_count). A shape that is already a valid positive
    Solid is taken AS-IS — exploding it per shell would split a hollow part
    into an outer solid plus a phantom cavity solid.

    That as-is path was DEAD until 2026-09-12 (section 8 review): `is_valid`
    is a PROPERTY, so calling it raised TypeError into the bare `except` below
    and every shape was exploded. A hollow 936 mm3 part imported as TWO bodies
    totalling 1,064 — the cavity filled, plus a phantom block inside it, all
    green. lib3mf hands back ONE Solid holding every shell in the file, so the
    as-is path alone is not enough either: two disjoint bodies make that solid
    invalid, and then the shells must be regrouped (_solids_from_shells)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        try:
            shapes = Mesher().read(tmp.name)
        except Exception as e:   # lib3mf errors do NOT derive from RuntimeError
            raise ValueError(f"import_stl: could not read the STL ({e})") from e
    finally:
        tmp.close()
        os.unlink(tmp.name)

    solids, open_shells = [], 0
    for shp in shapes:
        try:
            if isinstance(shp, Solid) and shp.volume > 0 and shp.is_valid:
                solids.append(shp)
                continue
        except Exception:
            pass
        grouped, opens = _solids_from_shells(shp)
        solids.extend(grouped)
        open_shells += opens
    return solids, open_shells


@functools.lru_cache(maxsize=8)
def _read_stl_solids(path_str: str, mtime_ns: int, size: int) -> tuple:
    """Read (+ auto-repair) an STL into (tuple of closed Solids, report dict).
    Cached on (path, mtime, size): Document.rebuild() re-evaluates every
    feature on every edit, and re-parsing a big mesh each time would crawl.
    Downstream ops never mutate OCCT shapes, so sharing the cached Solids
    across rebuilds is safe.

    Clean meshes under MAX_STL_TRIANGLES go straight to the kernel. Anything
    dirty (duplicated interface walls, pinched edges, too dense) goes through
    meshrepair's heal/split/remesh/decimate pipeline first — feeding a broken
    mesh straight to OCCT produced a 6-minute read returning an EMPTY invalid
    solid (probed on a real Fusion assembly export)."""
    import meshrepair

    data = Path(path_str).read_bytes()
    fmt, ntri = _stl_triangles(data)
    if ntri == 0:
        raise ValueError("import_stl: the file contains no triangles")
    if ntri > meshrepair.MAX_INPUT_TRIANGLES:
        raise ValueError(
            f"import_stl: mesh has {ntri:,} triangles — beyond the "
            f"{meshrepair.MAX_INPUT_TRIANGLES:,} import limit even for "
            "auto-repair. Decimate it in a mesh tool (Blender/MeshLab) "
            "and re-export.")
    if fmt == "ascii":
        data = _ascii_stl_to_binary(data)

    verts, faces = meshrepair.parse_binary_stl(data)
    boundary, overshared = meshrepair.edge_counts(faces)
    dupes = bool(meshrepair.duplicate_triangles(faces).any())
    report = {"input_triangles": ntri, "output_triangles": ntri,
              "healed_wall_triangles": 0, "remeshed_bodies": 0,
              "repaired": False}

    if ntri <= MAX_STL_TRIANGLES and not (boundary or overshared or dupes):
        pieces = [data]
    else:
        try:
            pieces, rep = meshrepair.repair_stl_mesh(data)
        except ValueError as e:
            raise ValueError(f"import_stl: {e}") from e
        report.update(rep)
        report["repaired"] = True

    solids, open_shells = [], 0
    for piece in pieces:
        s, o = _stl_bytes_to_solids(piece)
        solids.extend(s)
        open_shells += o
    if open_shells:
        raise ValueError(
            f"import_stl: the mesh is not watertight ({open_shells} open "
            f"shell(s), {len(solids)} closed) — a solid needs a fully closed "
            "surface. Repair it in a mesh tool and re-export.")
    if not solids:
        raise ValueError("import_stl: no solid found in the mesh")
    report["bodies"] = len(solids)
    return tuple(solids), report


def _resolve_stl_path(file: str) -> Path:
    if not isinstance(file, str) or not file.strip():
        raise ValueError("import_stl: file must be a filename or path")
    path = Path(file)
    if not path.is_absolute():
        path = IMPORTS_DIR / file
    if not path.is_file():
        raise ValueError(f"import_stl: file not found: {path}")
    return path


def import_stl(file: str, scale: float = 1.0) -> Part:
    """Import an external STL mesh file as a solid body. `file` is an absolute
    path, or the name of a file in the imports/ folder (where UI uploads
    land). The triangles become a faceted solid; broken meshes (duplicated
    interface walls, pinched edges, too dense) are auto-repaired via
    meshrepair — meshes with actual holes are refused. STL units are read as
    mm; `scale` resizes on import (e.g. 25.4 for a file modeled in inches)."""
    if not isinstance(scale, (int, float)) or scale <= 0:
        raise ValueError("import_stl: scale must be a positive number")
    path = _resolve_stl_path(file)
    st = path.stat()
    solids, _report = _read_stl_solids(str(path), st.st_mtime_ns, st.st_size)
    # NOTE: Part(solid.wrapped) reports volume 0 (probed) — never wrap that
    # way. Multi-body imports become a Compound, NOT a fuse: assembly exports
    # overlap/touch, and fusing two 10k-triangle meshes can hang the kernel.
    part = solids[0] if len(solids) == 1 else Compound(children=list(solids))
    if scale != 1.0:
        part = _b3d_scale(part, by=float(scale))
    return part


def _resolve_step_path(file: str) -> Path:
    if not isinstance(file, str) or not file.strip():
        raise ValueError("import_step: file must be a filename or path")
    path = Path(file)
    if not path.is_absolute():
        path = IMPORTS_DIR / file
    if not path.is_file():
        raise ValueError(f"import_step: file not found: {path}")
    if path.suffix.lower() not in (".step", ".stp"):
        raise ValueError(f"import_step: {path.name} is not a STEP file "
                         "(.step / .stp)")
    # OCCT's reader does NOT raise on a file that is not STEP: it prints its
    # own parse error to the server console and hands back an EMPTY shape, so
    # every such file was diagnosed "contains no solid bodies — surfaces or
    # curves alone cannot be used here" and sent the user looking for surfaces
    # in a file that was never STEP (measured 2026-09-12). Every STEP file
    # starts with the ISO-10303-21 header.
    with path.open("rb") as fh:          # closed before the caller may unlink it
        head = fh.read(512)
    if b"ISO-10303" not in head:
        raise ValueError(f"import_step: {path.name} is not a STEP file — a "
                         "STEP file starts with ISO-10303-21. Re-export it "
                         "as STEP (.step / .stp).")
    return path


def import_step(file: str, scale: float = 1.0) -> Part:
    """Import a STEP file (.step/.stp) as exact BREP solid bodies. `file` is an
    absolute path, or the name of a file in the imports/ folder.

    Unlike STL there is no faceting and nothing to repair: the geometry comes
    back as real curves and surfaces, so cylinders stay round and a design
    exported from HERE re-imports losslessly (the user's round-trip case,
    2026-08-31). Multi-solid files become a Compound, NOT a fuse — assemblies
    overlap or touch, and merging them is not this op's decision. STEP files
    carry their own units (read as mm); `scale` resizes on import."""
    if not isinstance(scale, (int, float)) or scale <= 0:
        raise ValueError("import_step: scale must be a positive number")
    path = _resolve_step_path(file)
    try:
        shape = b3d_import_step(str(path))
    except Exception as e:      # OCP read errors are Exception, not RuntimeError
        raise ValueError(f"import_step: could not read the STEP ({e})") from e
    solids = shape.solids()
    if not solids:
        raise ValueError("import_step: the file contains no solid bodies — "
                         "surfaces or curves alone cannot be used here")
    # NOTE: never Part(solid.wrapped) — that reports volume 0 (probed).
    part = solids[0] if len(solids) == 1 else Compound(children=list(solids))
    try:
        vol = float(part.volume)
    except Exception:
        vol = 0.0
    if vol <= 0:
        raise ValueError("import_step: the imported geometry has no volume")
    if scale != 1.0:
        part = _b3d_scale(part, by=float(scale))
    return part


def import_stl_report(file: str) -> dict:
    """The repair/import report for an STL (free: served from the same cache
    as import_stl). Keys: input_triangles, output_triangles, bodies,
    healed_wall_triangles, remeshed_bodies, repaired."""
    path = _resolve_stl_path(file)
    st = path.stat()
    return _read_stl_solids(str(path), st.st_mtime_ns, st.st_size)[1]


# ---------------------------------------------------------------------------
# Registry — the exact names exposed to the LLM's script namespace
# ---------------------------------------------------------------------------

EXPORTS = {
    "plate": plate,
    "disc": disc,
    "ball": ball,
    "cone": cone,
    "tube": tube,
    "polygon_plate": polygon_plate,
    "hex_plate": hex_plate,
    "revolve_profile": revolve_profile,
    "with_center_hole": with_center_hole,
    "with_bolt_circle": with_bolt_circle,
    "polar_pattern": polar_pattern,
    "rotate": rotate,
    "mirror": mirror_copy,
    "scale": scale_uniform,
    "linear_pattern": linear_pattern,
    "fillet": fillet_edges,
    "chamfer": chamfer_edges,
    "shell": shell_out,
    "import_stl": import_stl,
    "import_step": import_step,
}


def api_summary() -> str:
    """A compact, copy-pasteable list of the blocks, for the system prompt."""
    return "\n".join(
        f"  {name}{_signature(fn)}" for name, fn in EXPORTS.items())


def _signature(fn) -> str:
    import inspect
    return str(inspect.signature(fn))


# ---------------------------------------------------------------------------
# Self-test — build every block and validate it with the inspector. No LLM.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import inspector
    from build123d import export_stl as _export_stl

    # import_stl needs a real file: round-trip a box through STL
    _selftest_stl = Path(tempfile.gettempdir()) / "_blocks_selftest.stl"
    _export_stl(Box(20, 10, 5), str(_selftest_stl))

    _selftest_step = Path(tempfile.gettempdir()) / "_blocks_selftest.step"
    import build123d as _b3d_mod
    _b3d_mod.export_step(Box(20, 10, 5), str(_selftest_step))

    cases = {
        "import_stl (box roundtrip)": import_stl(str(_selftest_stl)),
        "import_step (box roundtrip)": import_step(str(_selftest_step)),
        "plate":        plate(40, 30, 5),
        "disc":         disc(20, 8),
        "ball":         ball(15),
        "cone":         cone(20, 8, 25),
        "tube":         tube(20, 12, 6),
        "polygon_plate": polygon_plate(5, 25, 8),
        "hex_plate":    hex_plate(across_flats=30, thickness=8),
        "revolve_profile (pulley)":
            revolve_profile([(0, 0), (30, 0), (30, 6), (18, 12),
                             (18, 20), (0, 20)]),
        "with_center_hole": with_center_hole(disc(20, 8), 6),
        "with_bolt_circle (6)":
            with_bolt_circle(disc(50, 10), count=6, bolt_radius=4,
                             pitch_circle_dia=76),
        "polar_pattern (blades x8)":
            polar_pattern(Pos(20, 0, 0) * Box(24, 3, 10), count=8),
    }

    print("=== block library self-test (validated by inspector.health) ===")
    all_ok = True
    for name, part in cases.items():
        problems = inspector.health(part)
        status = "OK   " if not problems else "FAIL "
        if problems:
            all_ok = False
        vol = round(part.volume, 1)
        sym = inspector.rotational_symmetry_order(part)
        extra = f"vol={vol:<10} sym={sym}"
        print(f"  {status}{name:28} {extra}  {problems if problems else ''}")

    print("\nALL BLOCKS HEALTHY" if all_ok else "\nSOME BLOCKS FAILED — fix before use")

    print("\n=== api_summary (goes into the LLM system prompt) ===")
    print(api_summary())
