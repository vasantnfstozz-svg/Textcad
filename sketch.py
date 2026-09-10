"""
sketch.py — E2: the 2D sketch system, the heart of manual CAD.

A SKETCH is a 2D profile drawn on a plane, built from entities (rectangles,
circles, polygons, slots, ellipses) each added or subtracted. Sketches are
then turned into solids by the sketch-consuming operations:

    sketch  -> extrude  (straight pull normal to the plane)
            -> revolve  (spin around an axis)
            -> loft     (blend between 2+ sketches on parallel planes)
            -> sweep    (drag a profile along a path)

Everything is EXPLICITLY dimensioned (a rectangle is 40x20 at (x,y)); there is
no constraint solver in this version — that is a later stage. All API used
here is confirmed against build123d 0.11.1.
"""

from __future__ import annotations
import math
import re
import build123d as b3d

from blocks import resolve_face   # noqa: F401 — one face resolver (faces, and the edge pick)
from build123d import (
    Rectangle, Circle, Ellipse, Polygon, SlotOverall, RegularPolygon,
    Pos, Axis, Plane, BuildLine, BuildSketch, Spline, Polyline, Line,
    ThreePointArc, make_face,
    extrude as _extrude, revolve as _revolve, loft as _loft, sweep as _sweep,
)

_PLANES = {"XY": Plane.XY, "XZ": Plane.XZ, "YZ": Plane.YZ}
_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}


def _to_bool(v, name: str) -> bool:
    """Strict boolean coercion. bool('false') is True in Python — a UI that
    sends the STRING 'false' must not silently flip a flag (this exact trap
    doubled every dialog-driven extrude before it was caught)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no", ""):
            return False
    raise ValueError(f"{name} must be true or false, got {v!r}")


# ---------------------------------------------------------------------------
# 2D entities -> a composite Sketch on a plane
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# What each entity kind is DIMENSIONED by
#
# The feature tree renders its editable rows from this, so a sketch shows
# "width 40 / height 20" instead of a wall of raw JSON. It lives here, next to
# _entity(), because that is the only other place that knows an entity's field
# names — and a drift test asserts every kind _entity() accepts appears here.
#
# (key, label, unit). `unit` is a display hint only; everything is mm/deg.
# ---------------------------------------------------------------------------

ENTITY_FIELDS = {
    "rectangle":       [("w", "width", "mm"), ("h", "height", "mm")],
    "circle":          [("r", "radius", "mm")],
    "ellipse":         [("rx", "radius X", "mm"), ("ry", "radius Y", "mm")],
    "slot":            [("length", "length (overall)", "mm"),
                        ("height", "height", "mm")],
    "regular_polygon": [("radius", "radius", "mm"),
                        ("sides", "sides", "count")],
    # geometry lives in a coordinate list, not in dimensions: the tree shows a
    # summary and sends the user to the sketch editor rather than 40 numbers
    "polygon":         [],
    "path":            [],
}

# every entity can be placed and turned
ENTITY_COMMON = [("x", "x", "mm"), ("y", "y", "mm"),
                 ("rotation", "angle", "deg")]

# kinds where a DIAMETER row is offered next to the radius: a machinist reads a
# bore as a diameter, and the user asked for exactly this ("i can able to change
# outer diameter and inner diameter")
ENTITY_DIAMETER = {"circle": "r", "regular_polygon": "radius"}

# entities whose shape is a coordinate list -> what to count in the summary
ENTITY_GEOMETRY = {"polygon": "points", "path": "segments"}


def entity_schema() -> dict:
    """JSON-safe description of every entity kind, for the UI."""
    return {
        "fields": {k: [{"key": a, "label": b, "unit": c} for a, b, c in v]
                   for k, v in ENTITY_FIELDS.items()},
        "common": [{"key": a, "label": b, "unit": c} for a, b, c in
                   ENTITY_COMMON],
        "diameter": ENTITY_DIAMETER,
        "geometry": ENTITY_GEOMETRY,
        "modes": ["add", "subtract"],
    }


def entity_kinds_in_code() -> set:
    """The kinds _entity() actually accepts, read out of its own source. Used by
    the drift test: a new kind must not reach users as raw JSON."""
    import inspect
    src = inspect.getsource(_entity)
    return set(re.findall(r'k == "([a-z_]+)"', src))


def _validate_dims(e: dict, k: str) -> None:
    """Every declared dimension must be a POSITIVE number.

    build123d silently absolutises a negative size: Rectangle(-5, 40) builds
    the same face as Rectangle(5, 40) (probed). With dimensions now editable
    straight from the feature tree, a typo'd minus sign would quietly give the
    user a different part with a green check next to it — the one failure this
    project refuses to allow. So refuse it here, naming the field the way the
    tree labels it."""
    for key, label, unit in ENTITY_FIELDS.get(k, []):
        if key not in e:
            continue
        v = e[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k} {label} must be a number, got {e[key]!r}")
        if v <= 0:
            raise ValueError(f"{k} {label} must be greater than 0, got {v:g}"
                             + (" (a negative size silently builds the "
                                "positive one)" if v < 0 else ""))


def _signed_area(pts) -> float:
    """Shoelace: positive for a counter-clockwise ring, negative for clockwise."""
    return 0.5 * sum(x0 * y1 - x1 * y0
                     for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


def _entity(e: dict):
    """One 2D primitive, positioned in the sketch plane's local coordinates."""
    k = e.get("kind")
    _validate_dims(e, k)
    x, y = float(e.get("x", 0)), float(e.get("y", 0))
    rot = float(e.get("rotation", 0))
    if k == "rectangle":
        s = Rectangle(float(e["w"]), float(e["h"]))
    elif k == "circle":
        s = Circle(float(e["r"]))
    elif k == "ellipse":
        s = Ellipse(float(e["rx"]), float(e["ry"]))
    elif k == "slot":
        # length is the OVERALL end-to-end size — exactly what the sketcher
        # canvas draws and dimensions (SlotCenterToCenter would add height).
        length, height = float(e["length"]), float(e["height"])
        if length <= height:
            raise ValueError(f"slot length ({length}) must be greater than its "
                             f"height ({height}) — length is end-to-end overall")
        s = SlotOverall(length, height)
    elif k == "regular_polygon":
        s = RegularPolygon(float(e["radius"]), int(e["sides"]))
    elif k == "polygon":
        pts = [(float(p[0]), float(p[1])) for p in e["points"]]
        if len(pts) < 3:
            raise ValueError("polygon entity needs >= 3 points")
        # OCCT takes the point order as the face's orientation: a clockwise
        # polygon is a face whose normal points -Z, and adding it to a normal
        # face did not fail -- it silently gave TWO overlapping faces, which
        # extrude into a self-intersecting solid (probed 2026-09-05). Build
        # every polygon counter-clockwise; the stored points stay as drawn.
        area = _signed_area(pts)
        # The same shoelace also catches a ring that encloses NOTHING —
        # collinear points, or a bow-tie whose lobes cancel. OCCT builds it: a
        # face of area -0.0 that reports `ok` here and blames the extrude
        # ("OpenCASCADE reports the solid is invalid") several nodes later.
        # Say it where the mistake is.
        if abs(area) < 1e-9:
            raise ValueError("polygon entity encloses no area — its points are "
                             "collinear or the outline crosses itself")
        if area < 0:
            pts.reverse()
        s = Polygon(*pts)
    elif k == "path":
        s = _path_face(e)
    else:
        raise ValueError(f"unknown sketch entity kind '{k}'")
    # Rotate FIRST (about the shape's own centre — every primitive above is
    # built centred on the local origin), THEN translate. The old order
    # rotated the already-positioned shape about the PLANE ORIGIN, so any
    # rotated entity (slots drawn right-to-left carry rotation=180, vertical
    # ones ±90) teleported to a point-reflected position the moment the
    # sketch was built — while the editor, which rotates locally, showed it
    # where the user drew it. (User report 2026-08-05: "after finishing it,
    # it goes completely to different shape".)
    if rot:
        s = s.rotate(Axis.Z, rot)
    s = Pos(x, y) * s
    return s


def _box_within(inner, outer, tol: float = 1e-7) -> bool:
    """Could `inner`'s bounding box sit inside `outer`'s, in the sketch plane?

    NOT `BoundBox.is_inside`, which was measured to be useless here (second
    code review, 2026-09-09): build123d returns `not (STRICTLY inside)`, and a
    2D sketch box is flat in Z, so `min.Z > min.Z` is never true and the whole
    test came back True for every pair. Nothing was ever skipped and every
    pair ran a full boolean — 4128 ms per rebuild of the user's 23-entity
    `rocky-balboa/field_sketch`, 1513 ms for `rocky-keychain/words_sketch`.

    X and Y only, on purpose: the shapes are coplanar, so Z carries nothing.
    """
    return (inner.min.X >= outer.min.X - tol
            and inner.max.X <= outer.max.X + tol
            and inner.min.Y >= outer.min.Y - tol
            and inner.max.Y <= outer.max.Y + tol)


def _boxes_meet(a, b, tol: float = 1e-7) -> bool:
    """Could the two boxes share any area in the sketch plane?

    X and Y only, for the same reason as `_box_within`: the shapes are
    coplanar, so Z carries nothing and build123d's own box tests are useless
    on a box that is flat in Z.
    """
    return (a.min.X <= b.max.X + tol and b.min.X <= a.max.X + tol
            and a.min.Y <= b.max.Y + tol and b.min.Y <= a.max.Y + tol)


def _overlaps(a, b) -> bool:
    """Do the two entity shapes share any area at all? Measured, with the
    bounding boxes only SKIPPING pairs that cannot possibly meet."""
    if not _boxes_meet(a.bounding_box(), b.bounding_box()):
        return False
    try:
        return abs((a & b).area) > 1e-9
    except Exception:                   # noqa: BLE001
        # TRUE is the safe direction here, unlike everywhere else in this
        # file. A False answer leaves the cut at the FRONT of the order,
        # where `_compose` drops it — one boolean that will not run and the
        # P0 this pass exists for is back (measured: the boss/bar/pocket case
        # returns to 78.5398 mm2 instead of 22.3648). A True answer only
        # orders the material first, and subtracting a shape that turns out
        # not to overlap removes nothing anyway.
        return True


def _area_of(shape) -> float:
    """How much area a part-composed profile still has — 0.0 for none.

    A profile cut away to nothing is an empty Compound, which answers 0.0
    (measured, third code review 2026-09-09). Anything that cannot answer at
    all is treated as empty too: the only question asked here is "is there
    material left to cut into?".
    """
    try:
        return float(shape.area)
    except Exception:                   # noqa: BLE001
        return 0.0


def _containment(shapes: list) -> list[list[bool]]:
    """`inside[i][j]` — does entity shape i sit inside entity shape j?

    Containment is MEASURED, never guessed: A is inside B when A minus B has
    no area left. The bounding box only SKIPS a pair (a box that does not fit
    inside cannot be contained); it never decides one — a circle straddling
    the rim passes the bbox test and fails the real one (probed 2026-09-09).

    Two copies of one shape (a mirror in place) contain EACH OTHER, which is
    not a nesting order at all; those pairs are dropped so they cannot make a
    cycle out of the ordering below.
    """
    n = len(shapes)
    boxes = [s.bounding_box() for s in shapes]
    inside = [[False] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j or not _box_within(boxes[i], boxes[j]):
                continue
            try:
                if abs((shapes[i] - shapes[j]).area) < 1e-7 * max(
                        shapes[i].area, 1.0):
                    inside[i][j] = True
            except Exception:               # a boolean that will not run tells
                continue                    # us nothing; leave the pair alone
    for i in range(n):
        for j in range(i + 1, n):
            if inside[i][j] and inside[j][i]:
                inside[i][j] = inside[j][i] = False
    return inside


def _nesting_depth(shapes: list) -> list[int]:
    """How many of the OTHER entity shapes each shape sits inside."""
    return [sum(row) for row in _containment(shapes)]


def _compose_order(shapes: list, modes: list | None = None) -> list[int]:
    """The order to compose in: an OUTER before anything nested inside it,
    MATERIAL before a cut that overlaps it, and the user's DRAWING order
    everywhere else.

    Why not a sort by nesting depth (the first fix pass, 556a611): depth is
    not an ordering constraint, so sorting by it moved entities that no
    nesting relates. A top-level subtraction — one that is inside nothing —
    sorted to the very front, ahead of the adds it was drawn after, and the
    user's `esp32-remote/logo_1_sketch` went from 4.37 mm2 to a red feature
    (second code review, 2026-09-09). The only thing the kernel actually
    needs is what the first review measured: the shape a hole sits in has to
    exist before the hole cuts it. That is one edge per nested pair and
    nothing else, so this is a stable topological order — of the entities
    whose outers are all composed, it always takes the one drawn first.

    Why containment is not the whole constraint (FOURTH code review,
    2026-09-09): an entity waits only for the shapes it is NESTED INSIDE, so a
    cut can be ordered ahead of material it overlaps for a reason that has
    nothing to do with that material — because the material happens to sit
    inside a DIFFERENT cut and is therefore waiting itself. `_compose` then
    drops the leading cut as one that meets nothing, and the cut is lost.
    Measured: a boss and a bar across it composed 22.3648 mm2; adding a pocket
    around them — which the boss sits inside — gave 78.5398, the whole boss,
    as if the bar had never been drawn. So the order has two constraints:
    an outer before what is nested inside it, AND material before a cut that
    overlaps it without containing it. Only a cut that still leads after both
    is one that genuinely meets nothing.

    The overlap pass costs nothing for the ordinary sketch: it runs only while
    the order actually STARTS with a cut, which needs a cut that contains an
    add (one sketch in the user's whole library).
    """
    n = len(shapes)
    inside = _containment(shapes)
    needs = [row[:] for row in inside]          # needs[i][j]: j before i
    order = _order_from(needs)
    if modes is None:
        return order
    for _ in range(n):                          # each pass frees one lead cut
        lead = []
        for i in order:
            if modes[i] != "subtract":
                break
            lead.append(i)
        if not lead:
            break
        grew = False
        for i in lead:
            for j in range(n):
                if (i == j or modes[j] == "subtract"
                        or needs[i][j] or needs[j][i]      # already ordered
                        or inside[i][j] or inside[j][i]):  # nested: an island
                    continue
                if _overlaps(shapes[j], shapes[i]):
                    needs[i][j] = True          # the material goes first
                    grew = True
        if not grew:
            break
        order = _order_from(needs)
    return order


def _order_from(needs: list[list[bool]]) -> list[int]:
    """A stable topological order over `needs[i][j] == "j must come before i"`:
    of the entities whose predecessors are all placed, always the one the user
    drew first."""
    n = len(needs)
    waiting = [sum(row) for row in needs]
    order: list[int] = []
    done = [False] * n
    while len(order) < n:
        nxt = next((i for i in range(n) if not done[i] and not waiting[i]),
                   None)
        if nxt is None:                         # a cycle we cannot order:
            nxt = next(i for i in range(n) if not done[i])   # fall back to
        done[nxt] = True                        # the drawing order
        order.append(nxt)
        for i in range(n):
            if needs[i][nxt] and not done[i]:
                waiting[i] -= 1
    return order


def _compose(entities: list):
    """Combine entities (add/subtract) into a 2D sketch in local coords,
    OUTERS BEFORE THE HOLES INSIDE THEM.

    Why the reorder (code review 2026-09-09, measured): this loop is
    sequential, but an entity list arrives in the order the user DREW in.
    Draw a bore and then its rim and the arithmetic was `hole + outer` — a
    solid disc of 2827.43 mm2 where the editor had shown a 2513.27 washer,
    reported `ok`, with no warning. Draw r10, r30, r20 and the island was cut
    away again: 1570.80 mm2 instead of 1884.96. The even-odd regions the
    sketcher SHOWS only mean what they look like if every outer is composed
    before the holes inside it.

    The stored entity list is untouched — it keeps the user's drawing order,
    so the tree's rows and every saved design stay as they are; only the
    arithmetic is reordered, and only where a nested pair demands it
    (`_compose_order`). Containment is measured only when something actually
    subtracts, so the ordinary all-add sketch pays nothing.
    """
    if not entities:
        raise ValueError("sketch has no entities")
    shapes = [_entity(e) for e in entities]
    modes = [e.get("mode", "add") for e in entities]
    order = list(range(len(shapes)))
    if any(m == "subtract" for m in modes):
        order = _compose_order(shapes, modes)
    # A subtraction that comes FIRST removes NOTHING (third code review,
    # 2026-09-09). It can legitimately come first: a subtraction that CONTAINS
    # an add owes that add an order, so it leads — which is exactly why
    # holding it back to just after the first add, as the last fix pass did,
    # was self-defeating: it then cut away the very add the order existed to
    # save. Three identical bars inside one subtract blob built 144.0 mm2
    # instead of 216.0 with the FIRST bar silently missing; `[r20 subtract,
    # r10 add]` built a "successful" 0.0; the user's
    # `esp32-remote/logo_1_sketch` built 4.3671 where the editor paints
    # 7.6656 (a 3.2985 mm2 green bar inside a red blob). Nothing is composed
    # yet, so there is nothing to cut — and the note says so rather than
    # leaving the user to wonder where their cut went.
    result = None
    added = False
    for i in order:
        mode = modes[i]
        if result is None:
            if mode == "subtract":
                # Say which of the two it is. The note read "nothing in this
                # sketch is drawn beneath it" either way, which is a false
                # statement about the user's own sketch when material HAD
                # been drawn there and an earlier cut removed it (fourth code
                # review, 2026-09-09).
                _note(f"entity {i + 1} removes nothing — everything drawn "
                      f"beneath it had already been cut away"
                      if added else
                      f"entity {i + 1} is a cut with nothing under it — "
                      f"nothing in this sketch is drawn beneath it, so it "
                      f"removes nothing")
                continue
            result = shapes[i]
            added = True
        else:
            result = (result - shapes[i] if mode == "subtract"
                      else result + shapes[i])
            added = added or mode != "subtract"
        # A cut that removes everything leaves an empty Compound. Passing
        # that to the NEXT subtraction raised build123d's "Dimensions of
        # objects to subtract from are inconsistent", and passing it on to
        # `_as_sketch` made `pl * <empty>` a plain list, so the tree showed
        # `AttributeError: 'list' object has no attribute 'faces'` (third
        # code review — both are rule 5 breaches). Empty is not failed: the
        # next add starts the profile again.
        # ONLY after a cut. Applied after an add as well, it took a single
        # tiny entity — a radius typed as 0.00001 in the tree, area 3.1e-10 —
        # and raised "the cuts removed everything that was drawn" for a
        # sketch with no cut in it, where it used to build (fourth code
        # review, 2026-09-09).
        if mode == "subtract" and _area_of(result) <= 1e-9:
            result = None
    if result is None:
        if added:
            raise ValueError(
                "sketch is empty — the cuts removed everything that was "
                "drawn; move or shrink them")
        raise ValueError(
            "sketch: every entity is a cut — there is nothing for them to "
            "cut into")
    return result


def _path_face(e: dict):
    """A closed profile chained from LINE and ARC segments — the free-drawing
    tool. Format:
        {"kind": "path", "start": [x, y], "segments": [
            {"type": "line", "to": [x, y]},
            {"type": "arc", "via": [x, y], "to": [x, y]},   # 3-point arc
        ]}
    The profile auto-closes with a straight line back to the start."""
    segs = e.get("segments") or []
    if not segs:
        raise ValueError("path entity needs at least 1 segment")
    # No start point is NOT the origin (third code review, 2026-09-09):
    # every reader in the editor guards `&& e.start` and draws nothing, so a
    # path without one is invisible and unclickable there — while this built
    # it from [0, 0] and saved the result. The editor and the kernel must not
    # disagree about what a sketch contains.
    if not e.get("start"):
        raise ValueError(
            "path entity has no start point — the editor shows no profile "
            "for it at all; redraw it")
    start = _xy("the path entity's start point", e["start"])
    _validate_path(start, segs)
    with BuildSketch() as sk:
        with BuildLine():
            cur = start
            for n, s in enumerate(segs, start=1):
                to = _seg_point("end", n, s.get("to"))
                is_arc = s.get("type") == "arc"
                # `via` is read OUTSIDE the try below. Inside it, a segment
                # with no middle point at all raised `KeyError('via')` and
                # came out as "the middle point lies on the straight line
                # between its ends" — a sentence about a point that is not
                # there (third code review, 2026-09-09). `_validate_path`
                # cannot catch it either: it guards with `s.get("via")`.
                via = (_seg_point("middle", n, s.get("via"))
                       if is_arc else None)
                # Rule 5 again, one level deeper (second code review,
                # 2026-09-09): the try below wrapped only make_face(), so a
                # segment the kernel cannot build spoke for itself —
                # `StdFail_NotDone: GC_MakeArcOfCircle::Value() - no result`
                # in the tree and a 500 from /api/sketch/trim/pieces. The
                # kernel stays the JUDGE of a three-point arc (it accepts a
                # middle point 1e-6 off a 100 mm chord, so no threshold of
                # ours could tell a flat arc from a dead one without
                # rejecting real profiles); we only translate its verdict.
                try:
                    if is_arc:
                        ThreePointArc(cur, via, to)
                    else:
                        Line(cur, to)
                except Exception as exc:            # noqa: BLE001
                    what = ("arc {0}: no curve passes through its three "
                            "points — the middle point lies on the straight "
                            "line between its ends, or sits on top of one of "
                            "them; move it off that line"
                            if is_arc else
                            "segment {0} could not be drawn — its two ends "
                            "are the same point")
                    raise ValueError(
                        "path entity, " + what.format(n)) from exc
                cur = to
            if abs(cur[0] - start[0]) > 1e-6 or abs(cur[1] - start[1]) > 1e-6:
                Line(cur, start)                        # auto-close
        try:
            make_face()
        except Exception as exc:                        # noqa: BLE001
            # Rule 5: an OpenCASCADE error must never BE the message. The
            # guards above name the mistakes we can name; anything left is
            # still a path that will not close, said in a sentence.
            raise ValueError(
                "path entity could not be closed into a face — the outline "
                "doubles back on itself or crosses itself somewhere; redraw "
                "the profile with points that go once around") from exc
    return sk.sketch


def _xy(label: str, value) -> tuple:
    """One [x, y] out of sketch data, or a sentence naming what is wrong.

    The fourth review's own fix validated that a point EXISTS but not that it
    holds two numbers, so `start: [5]` still reached the tree as
    `IndexError('tuple index out of range')` and `["a", "b"]` as a raw
    `float()` message (fourth review follow-up, 2026-09-09).
    """
    try:
        x, y = (float(v) for v in value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{label} must be two numbers, [x, y]") from None
    return (x, y)


def _seg_point(what: str, n: int, value) -> tuple:
    """One [x, y] out of a path segment, or a sentence naming what is missing.

    The third review moved the `via` read out of the arc translator's try so a
    missing middle point would speak for itself — but the `to` read one line
    above it was never wrapped at all, so a segment the AI author wrote
    without a destination reached the tree as `KeyError('to')`, and a `via`
    holding one number as `IndexError` (fourth code review, 2026-09-09).
    Neither is the kernel's fault; both are our own data, and this is where
    they are named.
    """
    if not value:
        raise ValueError(
            f"path segment {n} has no {what} point — a segment needs the "
            f"point it ends at, written as [x, y]" if what == "end" else
            f"path segment {n} has no {what} point — an arc needs a point it "
            f"passes through, written as [x, y]")
    return _xy(f"path segment {n}'s {what} point", value)


def _segments_cross(a0, a1, b0, b1) -> bool:
    """Do the two open straight segments cross at a point interior to both?
    Touching at a shared endpoint is not a crossing."""
    def side(p, q, r):
        return ((q[0] - p[0]) * (r[1] - p[1])
                - (q[1] - p[1]) * (r[0] - p[0]))
    d1, d2 = side(a0, a1, b0), side(a0, a1, b1)
    d3, d4 = side(b0, b1, a0), side(b0, b1, a1)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _validate_path(start, segs: list) -> None:
    """The mistakes a hand-drawn path actually makes, each said in a sentence.

    Before this (code review 2026-09-09, measured) the kernel spoke for
    itself and `document.rebuild` put the raw text in `f.problems`, so the
    tree and the chat showed `Standard_TypeMismatch('TopoDS::Face')` (four
    points that cross), `StdFail_NotDone('BRep_API: command not done')` (two
    clicks in one snapped grid cell) or "Face can only be created with closed
    wires" (start + one point + double-click). The same three inputs also
    500'd `/api/sketch/trim/pieces`, which builds every entity's face —
    exactly the tool a user reaches for to clean a crossing up.
    """
    pts = [start]
    for i, s in enumerate(segs):
        to = _seg_point("end", i + 1, s.get("to"))
        if s.get("type") == "arc":
            _seg_point("middle", i + 1, s.get("via"))
        if abs(to[0] - pts[-1][0]) < 1e-6 and abs(to[1] - pts[-1][1]) < 1e-6:
            raise ValueError(
                f"path segment {i + 1} starts and ends at the same point — "
                f"two clicks landed in one snap cell; move one of them")
        pts.append(to)

    distinct = {(round(p[0], 6), round(p[1], 6)) for p in pts}
    distinct |= {(round(float(s["via"][0]), 6), round(float(s["via"][1]), 6))
                 for s in segs if s.get("type") == "arc" and s.get("via")}
    if len(distinct) < 3:
        raise ValueError(
            "path entity needs at least 3 different points to enclose an "
            "area — this one is a single line")

    # A crossing is only checked between STRAIGHT segments, and only between
    # ones that do not share an end: an arc's chord is not the arc, and
    # guessing there would reject good crescent profiles.
    kinds = [s.get("type", "line") for s in segs]
    loop = [(pts[i], pts[i + 1], kinds[i]) for i in range(len(segs))]
    if (abs(pts[-1][0] - pts[0][0]) > 1e-6
            or abs(pts[-1][1] - pts[0][1]) > 1e-6):
        loop.append((pts[-1], pts[0], "line"))          # the auto-close
    n = len(loop)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue                                # adjacent round the loop
            if loop[i][2] != "line" or loop[j][2] != "line":
                continue
            if _segments_cross(loop[i][0], loop[i][1], loop[j][0], loop[j][1]):
                raise ValueError(
                    f"path crosses itself (segment {i + 1} cuts through "
                    f"segment {j + 1}) — a profile has to go once around "
                    f"without overlapping")

    # The shoelace only speaks for a path made of straight segments: an arc
    # carries area its chord does not, so a lens (two points and a bulge) is
    # a perfectly good profile whose control polygon is a line.
    if "arc" not in kinds:
        ring = list(pts[:-1]) if len(pts) > 2 and (
            abs(pts[-1][0] - pts[0][0]) < 1e-6
            and abs(pts[-1][1] - pts[0][1]) < 1e-6) else list(pts)
        if abs(_signed_area(ring)) < 1e-9:
            raise ValueError(
                "path entity encloses no area — its points are collinear or "
                "the outline crosses itself")


def _as_sketch(shape):
    """Normalize to a real Sketch. Combining DISJOINT entities (e.g. two
    separate bolt-hole circles) returns a Compound, which downstream code
    would then mistake for a (failed) solid — rewrap its faces instead."""
    if isinstance(shape, b3d.Sketch):
        return shape
    return b3d.Sketch(shape.faces())


def make_sketch(plane: str = "XY", offset: float = 0.0,
                entities: list | None = None):
    """Compose entities into one Sketch placed on a principal plane.

    plane: "XY", "XZ" or "YZ".  offset: shift the plane along its normal.
    entities: list of {"kind":..., ...params, "mode":"add"|"subtract"}.
    The first entity must be additive."""
    pl = sketch_plane(plane, offset)
    return _on_plane(_as_sketch(pl * _compose(entities or [])), pl)


def _on_plane(sketch, pl: Plane):
    """Remember the plane a sketch was drawn on, ON the object itself, so an op
    that needs the sketch's own axes (revolve about "u" / "v") reads the very
    plane the sketch was built on — one home, no second derivation. Probed
    2026-09-03 (probes/revolve_axis_probe.py): build123d Sketch objects accept
    attributes, and the document cache hands back the same object."""
    sketch._tc_plane = pl
    return sketch


def sketch_plane_of(sketch) -> Plane:
    """The plane a sketch was drawn on — the one it was built on when we built
    it (`_on_plane`), moved along its own normal if the sketch has since been
    translated out of it (the axes ride a move). Never guessed: a sketch that
    came through mirror / scale carries no plane, and one that was rotated has
    a plane that no longer matches its geometry; both raise a sentence, since
    "u" / "v" would otherwise mean a different axis than the sketcher showed
    (review 2026-09-03)."""
    pl = getattr(sketch, "_tc_plane", None)
    if pl is None:
        raise ValueError("this sketch does not carry the plane it was drawn on (it "
                         "came through a modifier such as mirror or scale) — revolve "
                         "the original sketch, or use a world axis (X, Y, Z) that "
                         "lies in its plane")
    faces = sketch.faces()
    if not faces:
        raise ValueError("the sketch has no face to read a plane from")
    f = faces[0]
    c = f.center()
    if abs(abs(f.normal_at(c).dot(pl.z_dir)) - 1.0) > 1e-6:
        raise ValueError("this sketch was rotated after it was drawn, so its own axes "
                         "no longer lie in its plane — revolve the original sketch, "
                         "or use a world axis (X, Y, Z) that lies in its plane")
    d = (c - pl.origin).dot(pl.z_dir)
    return pl.offset(d) if abs(d) > 1e-9 else pl


def sketch_plane(plane: str, offset: float = 0.0) -> Plane:
    """The plane a `sketch` feature is drawn in: a principal plane shifted
    along its own normal. ONE home for build123d's plane frames (XZ's normal
    points -Y, so an XZ offset of +7 lands at y = -7): make_sketch() builds
    here and toolplan.plan_sketch() reports the same object to the browser, so
    the grid the user draws on and the face the kernel builds cannot differ."""
    if plane not in _PLANES:
        raise ValueError('sketch: plane must be "XY", "XZ" or "YZ"')
    pl = _PLANES[plane]
    if offset:
        pl = pl.offset(float(offset))
    return pl


# The six named directions an author can point at without inventing a
# coordinate. The UI always has a real pick (a face center + normal from the
# raycast), but a tree authored from TEXT does not — and "compute the top face
# center yourself" is exactly where a number gets hallucinated. Same vocabulary
# blocks.shell_out/fillet_edges already use.
FACE_DIRS = {
    "top": (0.0, 0.0, 1.0), "+z": (0.0, 0.0, 1.0),
    "bottom": (0.0, 0.0, -1.0), "-z": (0.0, 0.0, -1.0),
    "+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0), "-y": (0.0, -1.0, 0.0),
    "front": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0),
    "right": (1.0, 0.0, 0.0), "left": (-1.0, 0.0, 0.0),
}


def named_face(solid, name: str, align_tol: float = 0.001):
    """The OUTERMOST flat face pointing in a named direction ("top", "+x",
    "front"...). Used so a sketch can say WHICH face it lives on by name.

    Only faces whose outward normal really points that way are candidates
    (align > 1 - align_tol), and of those the one farthest along the direction
    wins — so "top" on a part with a pocket is the outer top face, not the
    pocket floor. Flatness is judged by face_plane(), so a dead-flat wall the
    kernel stores as a BSPLINE (loft/sweep leave those) still counts."""
    key = str(name).strip().lower()
    if key not in FACE_DIRS:
        raise ValueError(
            f"face '{name}' is not a direction — use one of "
            f"{sorted(set(FACE_DIRS))}, or give face_center/face_normal from "
            f"an actual pick")
    dx, dy, dz = FACE_DIRS[key]

    def scan(faces):
        best, best_reach = None, None
        for f in faces:
            pl = face_plane(f)
            if pl is None:
                continue                   # genuinely curved: not sketchable
            n = pl.z_dir
            if n.X * dx + n.Y * dy + n.Z * dz < 1.0 - align_tol:
                continue                   # not facing this way
            c = f.center()
            reach = c.X * dx + c.Y * dy + c.Z * dz
            if best_reach is None or reach > best_reach:
                best, best_reach = f, reach
        return best

    # Real parts carry hundreds of faces and this runs on every rebuild of
    # every feature, so try the kernel-typed planes first — face_plane()'s
    # 9-sample flatness probe only runs on the leftovers, and only when no
    # honest PLANE points this way.
    faces = solid.faces()
    typed = [f for f in faces if f.geom_type == b3d.GeomType.PLANE]
    best = scan(typed)
    if best is None and len(typed) != len(faces):
        best = scan([f for f in faces if f.geom_type != b3d.GeomType.PLANE])
    if best is None:
        raise ValueError(
            f"this solid has no flat face pointing '{name}' — pick a different "
            f"direction, or sketch on a principal plane")
    return best


def face_plane(face, ang_tol_deg: float = 1.0, dist_tol: float = 1e-2):
    """A build123d Plane if `face` is geometrically FLAT — even when the kernel
    stores it as a BSPLINE / BEZIER / EXTRUSION surface. Taper, loft and sweep
    routinely produce a wall that is dead flat yet NOT typed PLANE; those must
    still be sketchable/extrudable. A surface is planar ⇔ its normal is constant
    and its points are coplanar. Returns None for genuinely curved faces."""
    from build123d import Plane
    try:
        c = face.center()
    except Exception:
        return None
    if face.geom_type == b3d.GeomType.PLANE:
        try:
            return Plane(face)
        except Exception:
            pass
    normals, pts = [], []
    for u in (0.15, 0.5, 0.85):
        for v in (0.15, 0.5, 0.85):
            try:
                p = face.position_at(u, v)
                n = face.normal_at(p)
                normals.append((n.X, n.Y, n.Z)); pts.append((p.X, p.Y, p.Z))
            except Exception:
                pass
    if len(normals) < 3:
        return None
    n0 = normals[0]
    cos_tol = math.cos(math.radians(ang_tol_deg))
    for n in normals[1:]:                       # every normal must be parallel
        if abs(n0[0]*n[0] + n0[1]*n[1] + n0[2]*n[2]) < cos_tol:
            return None
    for p in pts:                               # and every point coplanar
        if abs((p[0]-c.X)*n0[0] + (p[1]-c.Y)*n0[1] + (p[2]-c.Z)*n0[2]) > dist_tol:
            return None
    try:
        return Plane(origin=(c.X, c.Y, c.Z), z_dir=n0)
    except Exception:
        return None


def face_sketch_plane(face):
    """The plane a sketch on `face` is drawn in. Returns None when the face is
    genuinely curved.

    A face supplies the plane's POSITION. Its ORIENTATION is always the part's
    own — canonicalised to the principal plane of that axis (Z-facing -> XY,
    X-facing -> YZ, Y-facing -> XZ), the same three frames the sketcher and
    every `plane:` sketch already use. So `sketch_on_face` is exactly "a
    principal-plane sketch positioned by a face", and an entity at (x, y) means
    the same thing on every face of the part.

    Two things this deliberately avoids:

    * build123d's `Plane(face)` puts the origin at the face CENTROID. The top
      face of a shell is the rim minus every pocket cut so far, so its centroid
      MOVES whenever an upstream feature changes, dragging every entity with it.
    * Following the face's OUTWARD normal (what this did first, 2026-08-27)
      keeps one sign rule for "into the material" on every face, but a
      right-handed frame with the normal pointing -Z must mirror an in-plane
      axis: an entity authored at (10, 8) landed at world y = -8 on the bottom
      face, and the esp32 cavity came out mirrored and non-manifold. Uniform
      signs are not worth a silent mirror.

    The cost is that "into the material" is no longer one sign everywhere: on a
    top face it is a negative offset / `flip`, on a bottom face a positive
    offset / no flip. The author knows which side they are on, and getting it
    wrong cuts air — which fails loudly instead of quietly building the wrong
    part."""
    return _face_frame(face, snap=True)


def face_profile_plane(face):
    """The plane a FACE is a PROFILE in (Revolve on a picked face, P3b): the
    same framing rule as face_sketch_plane, WITHOUT the snap — the face's true
    plane, because a profile must lie in its plane (a wall tilted under 25 deg
    sketches as if upright, but its edges sit off that plane —
    probes/revolve_face_probe.py §7 measured 1.4 mm). Identical to
    face_sketch_plane on the axis-aligned faces of a box, so (u, v) on a face
    means what it means in a sketch drawn there. None for a curved face."""
    return _face_frame(face, snap=False)


def _face_frame(face, snap: bool):
    """ONE framing rule for a flat face — face_sketch_plane is this with `snap`
    on, face_profile_plane with it off. The principal frame nearest the face's
    normal (within ~25 deg, |n·k| > 0.9) supplies the ORIENTATION: its x, and its
    z as the canonical side; the world origin's foot on the plane is the origin.
    `snap` puts the plane ON that principal plane (a sketch is positioned by the
    face, not oriented by it); off, the plane is the face's own with the frame's
    x laid into it. Past ~25 deg no principal frame fits and both take the face's
    normal with a seeded x. None for a curved face."""
    pl = face_plane(face)
    if pl is None:
        return None
    n = pl.z_dir
    for frame in (Plane.XY, Plane.YZ, Plane.XZ):
        if abs(n.dot(frame.z_dir)) > 0.9:        # this face's axis
            k = frame.z_dir
            if snap:
                return Plane(origin=k * k.dot(pl.origin),
                             x_dir=frame.x_dir, z_dir=k)
            z = n if n.dot(k) > 0 else n * -1.0                  # the canonical side
            x = frame.x_dir - z * z.dot(frame.x_dir)              # the frame's x, in the plane
            return Plane(origin=z * z.dot(pl.origin), x_dir=x.normalized(), z_dir=z)
    # a genuinely oblique flat face (a tapered wall): no principal plane fits,
    # so derive a stable frame from the normal itself
    seed = next((c for c in (b3d.Vector(1, 0, 0), b3d.Vector(0, 1, 0), b3d.Vector(0, 0, 1))
                 if abs(n.dot(c)) < 0.9), b3d.Vector(1, 0, 0))
    return Plane(origin=n * n.dot(pl.origin),
                 x_dir=(seed - n * n.dot(seed)).normalized(), z_dir=n)


def face_outline_2d(solid, face_center: list | None = None,
                    face_normal: list | None = None,
                    face: str | None = None, offset: float = 0.0):
    """Project a picked PLANAR face's boundary into its own plane's local 2D
    coordinates — the outer wire plus any inner wires (holes). Returned in the
    SAME frame the sketch entities are placed in, so the sketcher can show the
    selected surface as reference geometry to draw against.

    The face is named the same two ways sketch_on_face accepts: by geometry
    (`face_center` from a real pick) or by direction (`face="top"`, the
    authoring path) — so EVERY committed face sketch can be reopened for
    editing. `offset` shifts the frame exactly like sketch_on_face shifts the
    sketch plane, so the editor's grid lands where the sketch actually lives.

    -> {"outer": [[x,y],...], "holes": [[[x,y],...],...], "planar": bool}
    """
    if face:
        picked = named_face(solid, face)
    elif face_center is not None:
        picked = resolve_face(solid, face_center, face_normal)
    else:
        raise ValueError('face_outline_2d needs either face="top"/"+x"/... '
                         "or a face_center from an actual pick")
    pl = face_sketch_plane(picked)              # the SKETCH frame, world-aligned
    if pl is None:                              # genuinely curved — can't project
        return {"outer": [], "holes": [], "planar": False}
    off = float(offset or 0.0)
    if off:
        pl = pl.offset(off)                     # mirror sketch_on_face exactly

    def project(wire):
        poly = []
        for e in wire.edges():
            steps = 2 if e.geom_type == b3d.GeomType.LINE else 24
            for i in range(steps + 1):
                loc = pl.to_local_coords(e @ (i / steps))
                poly.append([round(loc.X, 3), round(loc.Y, 3)])
        return poly

    outer = picked.outer_wire()
    holes = [project(w) for w in picked.wires() if w.length != outer.length]

    def vec(v):
        return [round(v.X, 4), round(v.Y, 4), round(v.Z, 4)]

    # the plane's world frame, so a UI can draw ghost geometry in place
    frame = {"origin": vec(pl.origin), "x_dir": vec(pl.x_dir),
             "y_dir": vec(pl.y_dir), "z_dir": vec(pl.z_dir)}
    return {"outer": project(outer), "holes": holes, "planar": True,
            "frame": frame}


def pick_face(solid, face_center: list | None = None,
              face_normal: list | None = None, face: str | None = None):
    """The face an op names, the two ways it may: by DIRECTION (face="top"/
    "+x"/…, the authoring path — no coordinates to compute, so none to get
    wrong) or by a real pick's centre + normal (resolved by geometry at every
    rebuild, so the pick survives parameter changes). ONE rule for
    sketch_on_face, hole and the planner."""
    if face:
        return named_face(solid, face)
    if face_center is not None:
        return resolve_face(solid, face_center, face_normal)
    raise ValueError('the face is not named — give face="top"/"bottom"/"+x"/... '
                     "or a face_center from an actual pick")


def sketch_on_face(solid, face_center: list | None = None,
                   face_normal: list | None = None,
                   entities: list | None = None, offset: float = 0.0,
                   face: str | None = None):
    """Draw a sketch ON a face of an existing solid (the Fusion workflow:
    pick a face, sketch, extrude a boss/cut). Two ways to say which face:

      * face="top"|"bottom"|"+x"|"-x"|"+y"|"-y"|"front"|"back"|"left"|"right"
        — the outermost flat face pointing that way (see named_face). This is
        the AUTHORING path: no coordinates to compute, so none to get wrong.
      * face_center (+ optional face_normal) — what the UI sends from a real
        raycast pick. Resolved by GEOMETRY at every rebuild (nearest center,
        best-matching normal) so it survives parameter changes instead of
        breaking like a stored face index would.

    `offset` shifts the sketch plane along the sketch frame's own +z — the
    PRINCIPAL axis nearest the face's normal, never the outward normal itself
    (see face_sketch_plane: following the outward normal kept one sign rule
    but silently MIRRORED in-plane coordinates on -z/-x/-y faces, which is
    how the esp32 cavity came out non-manifold). So "into the material" is
    not one sign everywhere, and this docstring said it was until the code
    review of 2026-09-09:

        top / +x / +y face    offset < 0   INTO the material
        bottom / -x / -y face offset > 0   INTO the material

    In both cases the opposite sign lifts the plane clear into the air, which
    fails loudly by cutting nothing instead of quietly building the wrong
    part. The author knows which side of the part it is on.

    This is the "offset method" (user mandate 2026-08-27): a pocket's plane is
    stated as a depth FROM A FACE, never as an absolute Z. Change the base
    thickness and the sketch rides with the face instead of being left behind
    — which is exactly what hardcoded principal-plane offsets did to 251 of
    the 274 sketches authored before this."""
    picked = pick_face(solid, face_center, face_normal, face)
    pl = face_sketch_plane(picked)
    if pl is None:
        raise ValueError(
            f"sketch_on_face: the picked face is {picked.geom_type.name} and not "
            f"flat — a sketch needs a PLANAR face. For a slot/pocket in a curved "
            f"surface, sketch on a principal plane (offset to the surface) and "
            f"extrude-cut through the body instead.")
    off = float(offset or 0.0)
    if off:
        pl = pl.offset(off)
    return _on_plane(_as_sketch(pl * _compose(entities or [])), pl)


# ---------------------------------------------------------------------------
# Sketch-consuming operations -> solids
# ---------------------------------------------------------------------------

def _is_straight(edge, tol: float = 1e-4) -> bool:
    """True if `edge` is geometrically a straight segment, whatever the kernel
    stores it as. Fusing a tapered (lofted) body leaves seam edges typed
    BSPLINE that are dead straight — see _straighten_face."""
    try:
        p0, p1 = edge @ 0, edge @ 1
    except Exception:
        return False
    chord = (p1 - p0).length
    if chord < 1e-9:
        return False
    for i in range(1, 12):                      # every sample on the chord?
        try:
            p = edge @ (i / 12)
        except Exception:
            return False
        if ((p - p0).cross(p1 - p0)).length / chord > tol:
            return False
    return True


def _straighten_face(face):
    """Rebuild `face` with every straight-but-curve-typed edge replaced by a
    real LINE edge — or return it unchanged when there is nothing to fix.

    WHY: OCCT's 2D offset (BRepOffsetAPI_MakeOffset, which build123d uses for
    tapered extrudes) mis-handles BSPLINE edges. Offsetting such a wire toward
    ONE side silently returns a degenerate wire — measured: a 4-edge rectangle
    with one straight BSPLINE edge offset by +0.2mm came back as a SINGLE edge
    of length 50.4 instead of 161.6 — which then detonates inside make_loft
    (Standard_NoSuchObject, or an OCCT access violation that kills the
    process). The other side offsets fine, which is exactly why a taper works
    outward but fails inward on the same face. Straight BSPLINE seam edges are
    left behind by fusing a tapered body, so any face touching that seam is
    affected. Rebuilt as LINEs, all directions offset correctly."""
    try:
        outer = face.outer_wire()
        wires = face.wires()
    except Exception:
        return face
    inner = [w for w in wires if w.length != outer.length]

    def fix(wire):
        edges, changed = [], False
        for e in wire.edges():
            if e.geom_type != b3d.GeomType.LINE and _is_straight(e):
                edges.append(b3d.Edge.make_line(e @ 0, e @ 1)); changed = True
            else:
                edges.append(e)
        return (b3d.Wire(edges), True) if changed else (wire, False)

    new_outer, ch = fix(outer)
    new_inner, changed = [], ch
    for w in inner:
        nw, c = fix(w)
        new_inner.append(nw); changed = changed or c
    if not changed:
        return face
    try:
        rebuilt = b3d.Face(new_outer, new_inner) if new_inner \
            else b3d.Face(new_outer)
    except Exception:
        return face                             # never make things worse
    # only accept a faithful rebuild (same area to 0.1%)
    try:
        if face.area > 0 and abs(rebuilt.area - face.area) / face.area > 1e-3:
            return face
    except Exception:
        return face
    return rebuilt


# Non-fatal facts an op wants the user to hear (a taper that ended at the tip).
# document.rebuild() drains this after every feature build into Feature.notes
# and Document.warnings, so the AI, MCP and API paths hear it too - not only
# the browser's ring (LAUNCH-PLAN.md R7, review finding 2026-09-03).
_NOTES: list = []


def _note(msg: str) -> None:
    _NOTES.append(msg)


def drain_notes() -> list:
    out = list(_NOTES)
    _NOTES.clear()
    return out


def collapse_offset(face):
    """How far this face's outline can be offset INWARD before the material is
    gone - the depth at which a narrowing taper's walls MEET (a point for a
    circle or square, a ridge for a rectangle, wherever the medial axis peaks
    for an odd shape). Measured by bisection on the kernel's own 2D offset, so
    it is exact for any outline; a hole caps it at half the EXACT kernel
    distance between the hole and the outer wall (or another hole) - build123d
    offsets holes OUTWARD under a taper, so hole and outer wall meet in the
    middle. (Point sampling was 5% off on a 200 mm plate and let a hole break
    through the wall with status ok - review 2026-09-03.)

    Returns None when it cannot be measured; callers then apply NO cap and let
    the usual guards speak. Used by the tapered extrude to end the solid where
    the walls meet (Fusion's semantics) and by the tool plan, so the handle,
    the ghost and the solid share one number."""
    from build123d import Kind, Plane
    try:
        pl = Plane(face)
        outer_w = face.outer_wire()
        outer = pl.to_local_coords(outer_w)
        bb = outer.bounding_box()
        hi = max(bb.size.X, bb.size.Y) / 2.0 + 1e-6      # this much surely eats everything

        def alive(o: float) -> bool:
            try:
                w = outer.offset_2d(-o, kind=Kind.INTERSECTION)
                if not w.edges():
                    return False
                try:
                    return abs(b3d.Face(w).area) > 1e-6
                except Exception:
                    return abs(make_face(w).area) > 1e-6
            except Exception:
                return False

        if not alive(hi * 1e-3):                     # the smallest step fails: unknown
            return None
        lo = 0.0
        for _ in range(18):                              # ~4e-6 of the size
            mid = (lo + hi) / 2.0
            if alive(mid):
                lo = mid
            else:
                hi = mid
        r = lo
        inner = list(face.inner_wires())
        if inner:
            thin = min(h.distance_to(outer_w) for h in inner)       # exact, ~0.2 ms each
            for i in range(len(inner)):
                for j in range(i + 1, len(inner)):
                    thin = min(thin, inner[i].distance_to(inner[j]))
            r = min(r, thin / 2.0)
        return r if r > 1e-6 else None
    except Exception:
        return None


# the tapered solid stops a hair short of the exact apex: OCCT reports the
# mathematically perfect tip as a broken solid (probes/taper_apex_probe.py -
# a cone built at 100% of the meeting height fails, 99.9% builds watertight)
APEX_FRACTION = 0.999
MAX_TAPER_DEG = 89.0          # a wall cannot lean past flat


def _apex_cap(face, amount: float, taper: float) -> float:
    """FUSION SEMANTICS (user, 2026-09-03: "in Fusion they go until -90, until
    flat as the sketch - there is no limit"): the distance is a MAXIMUM. When a
    narrowing taper's walls meet before it, the solid ends where they meet - a
    complete cone / pyramid / ridge that gets lower as the angle steepens and
    lies flat on the sketch at 90 deg. ONE face at a time: each profile of a
    multi-face sketch ends at its own tip. Returns the amount actually built and
    records a note when it shortened it. `taper` is in the kernel helpers'
    convention (positive narrows)."""
    if taper <= 0 or not amount:
        return amount
    r = collapse_offset(face)
    if r is None:
        return amount                            # unknown: no cap, the guards speak
    h_apex = APEX_FRACTION * r / math.tan(math.radians(taper))
    if abs(amount) <= h_apex:
        return amount
    _note(f"the walls meet {h_apex:.2f} mm in at {-taper:g} deg, before the "
          f"{abs(amount):g} mm asked - the solid ends at the tip (Fusion does "
          f"the same); a gentler angle makes it taller")
    return math.copysign(h_apex, amount)


def _taper_offset_problem(profile, amount: float, taper: float):
    """Replicate the 2D offset build123d will perform for a tapered extrude and
    report a problem STRING if it comes back degenerate — before OCCT is handed
    that garbage and crashes the process (an access violation would take the
    whole server down, so this check must happen here, not in an except:).

    Mirrors Solid.extrude_taper: the loft path (the fragile one) is used unless
    the direction matches the face normal AND the plane faces up AND the taper
    is positive AND there are no holes; offset = -|amount| * tan(taper)."""
    if not taper:
        return None
    try:
        face = profile if isinstance(profile, b3d.Face) else None
        if face is None:
            faces = profile.faces()
            if len(faces) != 1:
                return None                     # multi-face: let build123d try
            face = faces[0]
        pl = b3d.Plane(face)
        direction = pl.z_dir * amount
        inner = face.inner_wires()
        if (direction.normalized() == face.normal_at()
                and pl.z_dir.Z > 0 and taper > 0 and not inner):
            return None                         # robust DPrism path, no offset
        # (when DPrism goes the wrong way and _taper_loft takes over, the loft
        # checks its own offset wires — see there)
        off = -abs(amount) * math.tan(math.radians(taper))
        if abs(off) < 1e-9:
            return None
        for i, wire in enumerate([face.outer_wire()] + list(inner)):
            flip = -1 if i > 0 else 1           # build123d flips inner wires
            local = pl.to_local_coords(wire)
            n_before = len(local.edges())
            try:
                res = local.offset_2d(flip * off, kind=b3d.Kind.INTERSECTION)
            except Exception as e:
                return (f"the {'hole' if i else 'outline'} cannot be offset by "
                        f"{abs(off):.3f}mm ({type(e).__name__})")
            n_after = len(res.edges())
            # the degenerate signature: a polygon collapses to one or two
            # edges (the BSPLINE-seam garbage that access-violated OCCT came
            # back as a SINGLE edge). A wire merely LOSING an edge is normal —
            # the 0.07mm top of a near-collapsed wedge wall vanishes under any
            # inward offset and the loft builds fine (2026-09-03); refusing
            # that made a flipped taper on such a wall impossible.
            if n_after < n_before and n_before >= 3 and n_after < 3:
                return (f"the {'hole' if i else 'outline'} collapses when "
                        f"offset by {abs(off):.3f}mm "
                        f"({n_before} edges -> {n_after})")
    except Exception:
        return None                             # a check must never break a build
    return None


def _tapered_extrude(profile, amount: float, taper: float):
    """extrude() with the taper failure modes handled honestly:
      * every face of a multi-face sketch ends at ITS OWN tip (_apex_cap);
      * straight BSPLINE seam edges (from a fused tapered body) are rebuilt as
        LINEs first, which makes the offset - and the extrude - actually work;
      * a genuinely degenerate offset is caught BEFORE OCCT crashes on it;
      * a face of a solid always builds on its OUTWARD side (_same_side);
      * kernel errors are reported as-is, naming the distance the USER asked.
    OCP raises Standard_NoSuchObject etc., which derive from Exception and NOT
    from RuntimeError - an `except RuntimeError` here never caught them and the
    raw kernel error reached the feature tree."""
    if not taper:
        return _extrude(profile, amount=amount, taper=0.0)
    if isinstance(profile, b3d.Face):
        return _tapered_extrude_face(profile, amount, taper, from_solid=True)
    faces = list(profile.faces())
    if len(faces) <= 1:
        return _tapered_extrude_face(faces[0] if faces else profile, amount, taper,
                                     from_solid=False)
    parts = [_tapered_extrude_face(f, amount, taper, from_solid=False) for f in faces]
    return b3d.Part(children=parts)


def _tapered_extrude_face(face, amount: float, taper: float, from_solid: bool):
    """One face. `from_solid`: a picked face of an existing body (may be stored
    reversed, may carry BSPLINE seams) rather than a fresh sketch face."""
    asked = amount                                   # what the user typed - for messages
    outward = None
    fp = face_plane(face)
    if fp is not None:
        outward = fp.z_dir                           # captured BEFORE any rebuild
    if from_solid:
        # _straighten_face may rebuild the face with its normal FLIPPED
        # (measured 2026-09-03 on a fused body's wall) - every direction
        # decision below uses `outward`, never the rebuilt face's normal
        face = _straighten_face(face)
    amount = _apex_cap(face, amount, taper)          # the walls may meet first
    problem = _taper_offset_problem(face, amount, taper)
    if problem:
        raise ValueError(
            f"taper {-taper:g} deg over {abs(asked):g}mm does not work on this "
            f"profile: {problem}. Try a smaller taper, a shorter distance, "
            f"or taper the other way.")
    solid = None
    tried_loft = False
    try:
        solid = _extrude(face, amount=amount, taper=taper)
        # A FACE OF A SOLID can come out on the WRONG SIDE of a tapered build:
        # build123d hands an upward, narrowing, hole-less face to OCCT's
        # LocOpe_DPrism, which follows the face's INTERNAL orientation (a face
        # made by an earlier taper is stored reversed), and the straightened
        # face may carry a flipped normal. Either way the stub landed INSIDE
        # the body (user 2026-09-03: "it goes to the opposite direction").
        # Measure the side against the ORIGINAL outward normal; if the kernel
        # went the wrong way, build the loft along that explicit direction.
        if outward is not None and not _same_side(solid, face, amount, outward):
            tried_loft = True
            solid = None                             # never keep the wrong-sided solid
            solid = _taper_loft(face, amount, taper, outward)
    except Exception as e:
        err = e
        if outward is not None and not tried_loft:   # the other construction may work
            try:
                solid = _taper_loft(face, amount, taper, outward)
            except Exception as e2:
                err = e2
        if solid is None:
            raise ValueError(
                f"taper {-taper:g} deg over {abs(asked):g}mm failed on this profile "
                f"({type(err).__name__}: {str(err)[:100]}). Try a smaller taper, "
                f"a shorter distance, or taper the other way.") from err
    # A tapered extrude can also SUCCEED into a broken solid (measured on an
    # L-bracket's reflex corner and a DPrism boss face: an open shell /
    # OCCT-invalid result). Handing that to a fuse corrupts the model
    # silently, so refuse it here - a failed feature beats a bad body.
    import inspector                                 # local: avoids an import cycle
    problems = inspector.health(solid)
    if problems:
        # OCCT's loft-based taper INTERMITTENTLY flags valid geometry as an
        # invalid solid (probed on a 97mm extrude from a tilted face). ShapeFix
        # heals the bookkeeping; accept the repair only if it passes health
        # with the volume unchanged (0.1%).
        healed = _shapefix(solid)
        if healed is not None and not inspector.health(healed):
            return healed
        raise ValueError(
            f"taper {-taper:g} deg over {abs(asked):g}mm produces a broken solid "
            f"on this profile ({problems[0]}). Try a smaller taper, a shorter "
            f"distance, or taper the other way.")
    return solid


def _same_side(solid, face, amount: float, outward) -> bool:
    """Does the extruded solid lie on the side of `face` its amount asked for?
    (centre of mass along the face's ORIGINAL outward normal; a prism off a
    face never straddles it)"""
    try:
        d = (solid.center() - face.center()).dot(outward)
        return (d > 0) == (float(amount) > 0)
    except Exception:
        return True                             # a check must never break a build


def _taper_loft(face, amount: float, taper: float, outward):
    """A tapered extrude of a FACE OF A SOLID along its OUTWARD normal, built as
    a loft from the face to its 2D-offset copy moved by `amount` — the same
    construction build123d's `Solid.extrude_taper` uses for every case but one.

    The one it does differently is the bug (user, 2026-09-03: "I tried a
    taper on the triangle face and it goes in the opposite direction"): when a
    face points upward, the taper narrows and the face has no holes, build123d
    hands the job to OCCT's `LocOpe_DPrism`, which follows the face's INTERNAL
    orientation rather than its outward normal. A face created by an earlier
    taper is stored reversed, so the tapered stub landed INSIDE the body while
    the untapered one went outside (measured: +2.50 vs -2.40 mm along the
    normal on a 45° wedge wall). Here the direction is explicit — the same
    `face_plane` normal the untapered extrude and the tool's plan use — so the
    tapered and untapered results always lie on the same side. `taper` is in
    the kernel helpers' convention (positive narrows), like _extrude."""
    from build123d import Kind, Location, Plane, Solid, Vector
    n = outward                  # the ORIGINAL face's normal, never the rebuilt face's
    direction = Vector(n.X, n.Y, n.Z) * float(amount)
    offset_amt = -direction.length * math.tan(math.radians(taper))
    pl = Plane(face)                            # a 2D frame for the offset only
    wires = [face.outer_wire()] + face.inner_wires()
    solids = []
    for i, wire in enumerate(wires):
        flip = -1 if i > 0 else 1               # holes taper the other way
        local = pl.to_local_coords(wire)
        try:
            shrunk = local.offset_2d(flip * offset_amt, kind=Kind.INTERSECTION)
        except Exception as e:                  # the offset eats the whole wire
            raise ValueError(
                f"the walls meet before the end: the {'hole' if i else 'outline'} "
                f"cannot be offset by {abs(offset_amt):.2f}mm ({type(e).__name__}) "
                f"— use a smaller taper or a shorter distance") from e
        # never hand OCCT a degenerate wire (the garbage that once
        # access-violated the whole server): a polygon offset must stay a
        # polygon — a circle (1 edge) is fine, 1-2 edges from 3+ is not
        if len(wire.edges()) >= 3 and len(shrunk.edges()) < 3:
            raise ValueError(
                f"the {'hole' if i else 'outline'} collapses when offset by "
                f"{abs(offset_amt):.3f}mm ({len(wire.edges())} edges -> "
                f"{len(shrunk.edges())})")
        moved = pl.from_local_coords(shrunk)
        moved.move(Location(direction))
        solids.append(Solid.make_loft([wire, moved]))
    solid = solids[0]
    if len(solids) > 1:
        solid = solid.cut(*solids[1:])
    return solid


def _shapefix(solid):
    """Repair an OCCT-invalid solid; None unless the repair is FAITHFUL
    (same volume to 0.1%) — a repair must never quietly change geometry."""
    try:
        from OCP.ShapeFix import ShapeFix_Shape
        fixer = ShapeFix_Shape(solid.wrapped)
        fixer.Perform()
        healed = b3d.Solid(fixer.Shape())
        if solid.volume > 1e-9 and \
                abs(healed.volume - solid.volume) / solid.volume < 1e-3:
            return healed
    except Exception:
        pass
    return None


def extrude_face(solid, face_center: list, face_normal: list | None = None,
                 amount: float = 10.0, taper: float = 0.0, flip: bool = False):
    """Extrude a planar FACE of an existing solid (the Fusion workflow: click a
    face, press Extrude, pull the arrow). The face is resolved by GEOMETRY at
    every rebuild (nearest center + matching normal), so the pick survives
    parameter changes. Returns ONLY the extruded prism — combine it with the
    body via fuse (boss) or cut (pocket, with a negative/into amount).
    The face's exact outline is used — holes and curved edges included."""
    face = resolve_face(solid, face_center, face_normal)
    if face_plane(face) is None:               # flat BSPLINE/BEZIER walls are OK
        raise ValueError(
            f"extrude_face: the picked face is {face.geom_type.name} and not "
            f"flat — only planar faces can be extruded.")
    a = float(amount)
    if _to_bool(flip, "flip"):
        a = -a
    return _tapered_extrude(face, a, _fusion_taper(taper))


def _fusion_taper(taper) -> float:
    """The public taper sign is FUSION'S (user decision 2026-09-03, Autodesk
    help: "a negative angle tapers the extrusion inward, a positive value
    outward"). The kernel helpers below keep their historical convention
    (positive narrows), so this is the ONE place the sign turns around - and
    the one place a wall leaning past flat is refused, for every extrude path."""
    t = float(taper or 0.0)
    if abs(t) >= 90:
        raise ValueError(f"taper {t:g} deg - a wall cannot lean past flat (90 deg); "
                         f"use a smaller angle")
    return -t


# How far a "through all" cut reaches. Anything longer than the part is
# equivalent — a cutting tool that overshoots removes exactly the same material
# — and 2 m is far past any plate this tool works with while staying well inside
# OCCT's comfortable range.
THROUGH_MM = 2000.0


def extrude_sketch(sketch, amount: float, both: bool = False,
                   amount2: float = 0.0, taper: float = 0.0, flip: bool = False,
                   through: bool = False):
    """Pull a sketch straight, normal to its plane, into a solid (Fusion-style
    Extrude). Direction:
      * one side   : amount  (flip = extrude the other way)
      * symmetric  : both=True — extrude `amount` to EACH side
      * two sides  : amount one way + amount2 the opposite way
    `taper` degrees tapers the walls — FUSION'S SIGN (user decision
    2026-09-03): NEGATIVE narrows as it extrudes, POSITIVE flares outward.
    (Before 2026-09-03 positive narrowed; saved designs were migrated.)
    FUSION'S SEMANTICS too: `amount` is a MAXIMUM. If the narrowing walls meet
    before it, the solid ends where they meet (see _apex_cap) - every face of
    a multi-face sketch at its own tip. Any angle below 90 deg builds, steeper
    is simply lower; 90 deg and beyond (a wall past flat) is refused.

    `through` = THROUGH ALL: ignore the distance and run far past the material,
    keeping the direction. This is what a CUTTING tool almost always wants. A
    tool that stops INSIDE material does not clear it — it slices it, and
    whatever was above the cut is left as a loose piece. That is what happened
    when a pillar trim was shortened from 6 mm to 2 mm: it took a band out of
    four pillars and left their caps floating (user, 2026-08-26: "if i am
    increasing or decreasing the extrude value, it should increase or decrease,
    it should not create a new body"). With `through` the depth simply cannot
    land inside the part, so the cut can only ever clear.

    Taper is ignored for a through cut: a 2 m tapered prism collapses."""
    a = float(amount)
    if _to_bool(flip, "flip"):
        a = -a
    t = _fusion_taper(taper)
    if _to_bool(through, "through"):
        a = THROUGH_MM if a >= 0 else -THROUGH_MM
        t = 0.0
    if _to_bool(both, "both"):
        try:
            faces = list(sketch.faces()) if not isinstance(sketch, b3d.Face) else [sketch]
            parts = [_extrude(f, amount=_apex_cap(f, a, t), both=True, taper=t)
                     for f in faces]
            return parts[0] if len(parts) == 1 else b3d.Part(children=parts)
        except Exception as e:
            if t:
                raise ValueError(
                    f"taper {-t:g}° over {abs(a):g}mm (symmetric) failed on this "
                    f"profile ({type(e).__name__}: {str(e)[:80]}). Try a "
                    f"smaller taper, a shorter distance, or the other way.") from e
            raise
    solid = _tapered_extrude(sketch, a, t)
    amt2 = float(amount2 or 0.0)
    if amt2 > 0:                      # two-sided: opposite direction by amt2
        s2 = -1.0 if a >= 0 else 1.0
        solid = solid + _tapered_extrude(sketch, s2 * amt2, t)
    return solid


_LOCAL_AXES = {"u": "x_dir", "v": "y_dir"}      # a sketch plane's own axes
MAX_REVOLVE_DEG = 360.0                          # one full turn either way


def face_profile(solid, face_center: list, face_normal: list | None = None,
                 verb: str = "revolved"):
    """A flat face of `solid`, resolved by GEOMETRY (extrude_face's rule: nearest
    centre, matching normal), as the profile a sketch op reads — the face, its
    true plane (`face_profile_plane`) and the Sketch carrying that plane. ONE
    home for the op AND the planner, so the handles and the solid come from the
    same object. The one sentence for a curved face."""
    face = resolve_face(solid, face_center, face_normal)
    pl = face_profile_plane(face)
    if pl is None:
        raise ValueError(f"the picked face is {face.geom_type.name} (curved) — only a "
                         f"FLAT face can be {verb}; tilted flat faces are fine")
    return face, pl, _on_plane(b3d.Sketch([face]), pl)


def _axis_line(axis):
    """A revolve axis given as a LINE in the sketch plane's own coordinates,
    [[u1, v1], [u2, v2]] — two (u, v) float pairs, or None when `axis` is not
    that shape. The Revolve tool stores a picked straight edge of the profile
    this way (P3b): it rides the plane exactly as "u" / "v" do (a face or an
    offset move carries it), and a later change to the profile leaves a
    construction line where the edge was — never a silently different axis."""
    if isinstance(axis, str) or not isinstance(axis, (list, tuple)) or len(axis) != 2:
        return None
    try:
        a, b = axis
        return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
    except (TypeError, ValueError, IndexError, KeyError):   # KeyError: [{"u":..}, ..]
        return None


def _axis_word(axis) -> str:
    """How a sentence names an axis: 'v axis', 'Z axis', or the line."""
    line = _axis_line(axis)
    if line is None:
        return f"{axis} axis"
    (u1, v1), (u2, v2) = line
    return f"axis line ({u1:g}, {v1:g})-({u2:g}, {v2:g})"


def revolve_axis(sketch, axis) -> Axis:
    """The Axis for a revolve axis. "u" / "v" are the sketch plane's own x / y
    through the sketch origin — they RIDE the geometry when a face or an
    offset moves (the offset method, applied to an axis). "X" / "Y" / "Z" are
    the world axes: the authoring path. [[u1, v1], [u2, v2]] is a line in the
    sketch plane's own coordinates — one of the profile's straight edges, as
    the Revolve tool offers them (P3b); it rides the plane like u / v."""
    if isinstance(axis, str) and axis in _LOCAL_AXES:
        pl = sketch_plane_of(sketch)
        return Axis(pl.origin, getattr(pl, _LOCAL_AXES[axis]))
    if isinstance(axis, str) and axis in _AXES:
        return _AXES[axis]
    line = _axis_line(axis)
    if line is not None:
        (u1, v1), (u2, v2) = line
        if math.hypot(u2 - u1, v2 - v1) < 1e-6:
            raise ValueError("revolve: the axis line's two points coincide — give two "
                             "different points of the sketch plane, [[u1, v1], [u2, v2]]")
        snapped = _snap_to_edge(sketch, line)
        if snapped is not None:
            a, b = snapped
        else:
            pl = sketch_plane_of(sketch)
            a = pl.from_local_coords(b3d.Vector(u1, v1, 0))
            b = pl.from_local_coords(b3d.Vector(u2, v2, 0))
        return Axis(a, b - a)
    raise ValueError('revolve: axis must be "u" or "v" (the sketch plane\'s own '
                     'axes), "X", "Y", "Z", or a line in the sketch plane as '
                     '[[u1, v1], [u2, v2]]')


def _straight_edges(sketch) -> list:
    """Every straight edge of the profile's OUTER wires, walked ONCE per Sketch
    object (cached on it: the document hands back the same object, and a plan
    asks once per candidate axis): [(a, b, p, q)] — a / b the kernel's own
    world endpoints, p / q the same in the sketch plane's coordinates rounded
    to 0.1 µm (`_r4`). Inner wires are left out: material lies on both sides of
    a hole's edge, so it always straddles. Straight-but-BSPLINE seam edges
    count (_is_straight). The one walk behind revolve_edge_lines (what the
    panel offers) and _snap_to_edge (what a stored line resolves to), so the
    two cannot disagree about which edges exist."""
    cached = getattr(sketch, "_tc_straight", None)
    if cached is not None:
        return cached
    pl = sketch_plane_of(sketch)
    out = []
    for f in sketch.faces():
        for e in f.outer_wire().edges():
            if not _is_straight(e):
                continue
            a, b = e @ 0, e @ 1
            la, lb = pl.to_local_coords(a), pl.to_local_coords(b)
            out.append((a, b, (_r4(la.X), _r4(la.Y)), (_r4(lb.X), _r4(lb.Y))))
    try:
        sketch._tc_straight = out
    except AttributeError:
        pass
    return out


def _snap_to_edge(sketch, line, tol: float = 1e-3):
    """The exact world endpoints of the profile's straight edge that `line`
    (sketch-plane coordinates) lies ALONG — both of its points within `tol` of
    the edge's infinite line, directions parallel — ordered the line's way,
    else None. Collinear, not endpoint-equal: the stored line is the edge as it
    was when picked, and the profile may since have been resized along it (the
    spec's construction-line promise); the axis must still be the kernel's own
    vertices, because a line even 0.1 µm off the edge makes OCCT sweep the edge
    into a SLIVER face instead of collapsing it — a valid-looking junk solid
    (probes/revolve_face_probe.py §9)."""
    (u1, v1), (u2, v2) = line
    du, dv = u2 - u1, v2 - v1
    L = math.hypot(du, dv)
    if L < 1e-9:
        return None
    for a, b, p, q in _straight_edges(sketch):
        eu, ev = q[0] - p[0], q[1] - p[1]
        E = math.hypot(eu, ev)
        if E < 1e-9 or abs(du * eu + dv * ev) / (L * E) < 1 - 1e-9:   # not parallel
            continue
        off = max(abs((u1 - p[0]) * ev - (v1 - p[1]) * eu),        # both points, off the line
                  abs((u2 - p[0]) * ev - (v2 - p[1]) * eu)) / E
        if off > tol:
            continue
        return (a, b) if du * eu + dv * ev > 0 else (b, a)
    return None


def _plane_for_axis_check(sketch):
    """The plane a revolve axis must lie in: the recorded one when it is still
    valid, else the first face's own plane — enough to check a WORLD axis on a
    sketch that came through a modifier (u / v need the record and say so)."""
    try:
        return sketch_plane_of(sketch)
    except ValueError:
        faces = sketch.faces()
        if not faces:
            return None
        f = faces[0]
        return Plane(origin=f.center(), z_dir=f.normal_at(f.center()))


def revolve_extent(sketch, ax: Axis):
    """The profile's reach in the (radial, axial) frame of `ax`:
    (r_lo, r_hi, h_lo, h_hi, straddles) — radial along n × a (the sketch
    plane's normal crossed with the axis), axial along the axis, both from the
    axis point; `straddles` is True when ANY ONE FACE reaches both sides of the
    axis (faces on opposite sides, none crossing, revolve cleanly). None when
    the axis does not lie in the sketch's plane — its direction OR its line:
    an axis parallel to the plane but outside it makes OCCT return a valid
    solid of the WRONG shape (probed 2026-09-03: lathe volume, displaced
    centroid), the banned silent-wrong-geometry failure. ONE measurement for
    the op's guard and the tool's ring / ghost, on the kernel's own bounding
    boxes, so a circle's whole reach counts, not just its seam vertex."""
    pl = _plane_for_axis_check(sketch)
    if pl is None:
        return None
    n, a = pl.z_dir, ax.direction
    if abs(n.dot(a)) > 1e-6:                              # direction out of the plane
        return None
    if abs(n.dot(ax.position - pl.origin)) > 1e-6:       # the LINE runs outside it
        return None
    radial = n.cross(a).normalized()
    local = Plane(origin=ax.position, x_dir=radial, z_dir=radial.cross(a))   # y = the axis
    bbs = [local.to_local_coords(f).bounding_box() for f in sketch.faces()]
    if not bbs:
        return None
    straddles = any(bb.min.X < -1e-6 and bb.max.X > 1e-6 for bb in bbs)
    return (min(float(bb.min.X) for bb in bbs), max(float(bb.max.X) for bb in bbs),
            min(float(bb.min.Y) for bb in bbs), max(float(bb.max.Y) for bb in bbs),
            straddles)


def revolve_axis_span(sketch, ax: Axis):
    """(r_lo, r_hi) of revolve_extent — how far the profile reaches either side
    of the axis, radially; None when the axis is not in the sketch's plane."""
    e = revolve_extent(sketch, ax)
    return None if e is None else (e[0], e[1])


def _r4(x: float) -> float:
    """Round to 0.1 µm, with -0.0 folded into 0.0 (it prints as "-0")."""
    r = round(float(x), 4)
    return 0.0 if abs(r) < 5e-5 else r


def revolve_edge_lines(sketch) -> list:
    """The straight edges of the profile's outline as lines in the sketch
    plane's own coordinates, [((u1, v1), (u2, v2)), ...] — Fusion's "pick a
    line of the profile as the axis" (P3b), read off `_straight_edges`.
    Endpoints are ordered so the direction's dominant component is positive
    (the ring's positive drag means the same thing on every rebuild), the
    longest edge first, an edge two faces share listed once."""
    seen, out = set(), []
    for _a, _b, p, q in _straight_edges(sketch):
        du, dv = q[0] - p[0], q[1] - p[1]
        if math.hypot(du, dv) < 1e-6:
            continue
        if (abs(du) >= abs(dv) and du < 0) or (abs(dv) > abs(du) and dv < 0):
            p, q = q, p
        if (p, q) in seen:
            continue
        seen.add((p, q))
        out.append((p, q))
    out.sort(key=lambda l: -math.hypot(l[1][0] - l[0][0], l[1][1] - l[0][1]))
    return out


def revolve_sketch(sketch, axis="Z", angle: float = 360.0, angle2: float = 0.0,
                   both: bool = False):
    """Spin a sketch about an axis to make a solid of revolution.

    axis: "u" / "v" — the sketch plane's own x / y through the sketch origin
    (what the Revolve tool sends: it rides the geometry), "X" / "Y" / "Z" — a
    world axis (the authoring path), or [[u1, v1], [u2, v2]] — a line in the
    sketch plane, normally one of the profile's straight edges (P3b). The
    axis LINE must lie in the sketch plane and no face of the profile may
    cross it (a profile on XZ at positive x, revolved about Z or "v").

    Extents, Fusion's Direction option (P3b), spelled as extrude_sketch spells
    them: ONE SIDE sweeps `angle` (signed) from the profile plane; TWO SIDES
    adds `angle2` (a size, >= 0) the OTHER way; `both` (Fusion's Symmetric)
    sweeps `angle` to EACH side (Autodesk: "a single angle to revolve in each
    direction"). Built as one sweep of the total, turned back about the axis so
    the profile plane sits where Fusion puts it — exact, the symmetric centroid
    lies in the plane (probes/revolve_face_probe.py §5).

    Every way of getting this wrong used to reach the user raw or wrong
    (probes/revolve_axis_probe.py, 2026-09-02/03):
      * a face straddling the axis -> StdFail_NotDone, an OCP exception that
        does NOT derive from RuntimeError;
      * an axis perpendicular to the plane -> a "successful" solid of volume 0;
      * an axis parallel to the plane but OUTSIDE it -> a valid solid of the
        wrong shape;
      * angle 0 -> build123d quietly makes a FULL turn; 400 -> quietly 40.
    Each is a ValueError that says what to change — the tool shows it, and the
    AI repair loop reads it. An empty result is caught by the document's
    health check like every other op's."""
    ax = revolve_axis(sketch, axis)
    word = _axis_word(axis)
    a1 = float(angle)
    a2 = float(angle2 or 0.0)
    if a2 < 0:                                   # checked BEFORE `both` overrides it
        raise ValueError("revolve: the second side's angle is a size, not a direction "
                         "— give it as a positive number; the FIRST angle's sign says "
                         "which way side one turns")
    if _to_bool(both, "both"):
        a2 = abs(a1)                             # symmetric: the angle to EACH side
    if not -MAX_REVOLVE_DEG <= a1 <= MAX_REVOLVE_DEG:
        raise ValueError(f"revolve: angle must be between -{MAX_REVOLVE_DEG:g} and "
                         f"{MAX_REVOLVE_DEG:g}, got {a1:g} (the kernel would "
                         f"quietly wrap it)")
    total = abs(a1) + a2
    if total < 1e-9:
        raise ValueError("revolve: angle is 0, so there is nothing to build — "
                         "drag the ring or type an angle first")
    if total > MAX_REVOLVE_DEG + 1e-9:
        raise ValueError(f"revolve: the two sides add up to {total:g} deg, more than "
                         f"one full turn ({MAX_REVOLVE_DEG:g}) — the sweep would overlap "
                         f"itself; make the angles smaller")
    ext = revolve_extent(sketch, ax)
    if ext is None:
        raise ValueError(
            f"revolve: the sketch's plane does not contain the {word} (its "
            f"direction or its line lies outside the plane), so spinning around it "
            f"does not make a true solid of revolution. Revolve about u or v — the "
            f"plane's own axes through the sketch origin — a world axis that "
            f"lies in the plane, or one of the profile's own straight edges.")
    r_lo, r_hi, _h0, _h1, straddles = ext
    if straddles:
        raise ValueError(
            f"revolve: the profile crosses the {word} (it reaches "
            f"{r_lo:.3g} to {r_hi:.3g} either side), so the sweep would pass "
            f"through itself. Move the profile entirely to one side of the "
            f"axis, or revolve about another axis in its plane.")
    sign = 1.0 if a1 >= 0 else -1.0
    try:
        solid = _revolve(sketch, axis=ax, revolution_arc=sign * total)
        if a2:
            solid = solid.rotate(ax, -sign * a2)
    except Exception as e:      # OCP errors derive from Exception, not RuntimeError
        # probed 2026-09-05: an axis 1e-7 mm off an edge of the profile is a raw
        # Standard_OutOfRange from BRepPrimAPI_MakeRevol (the class name stays in
        # the chain, not in the sentence — the kernel's names are not the user's)
        raise ValueError(
            f"revolve: the kernel could not sweep this profile about the {word} — "
            f"an axis a hair off an edge of the profile does this; turn about the "
            f"edge itself, or move the axis clear of the profile.") from e
    import inspector                                 # local: avoids an import cycle
    # the rebuild's own per-feature policy (document.py): the cheap census, not
    # OCCT's ~270 ms validity analysis — the result gets that once, at the end.
    # The junk this guards against (a sliver face, an open shell) is a census
    # matter; an intermittent validity flag is healed downstream, not refused here.
    problems = inspector.health(solid, check_valid=False)
    if problems:                                     # a failed feature beats a corrupt body
        raise ValueError(
            f"revolve: the sweep about the {word} came back broken ({problems[0]}) "
            f"— turn about another axis, or move this one clear of the profile.")
    return solid


def revolve_face(solid, face_center: list, face_normal: list | None = None,
                 axis=None, angle: float = 360.0, angle2: float = 0.0,
                 both: bool = False):
    """Revolve a planar FACE of an existing solid (the Fusion workflow: click a
    face, press Revolve, choose one of its edges as the axis, drag). The face
    is resolved by GEOMETRY at every rebuild — nearest centre, matching normal,
    the same rule as extrude_face — so the pick survives parameter changes
    (`face_profile`, shared with the planner). `axis` is a line in the face's
    own plane, [[u1, v1], [u2, v2]] in face_profile_plane's coordinates
    (normally one of the face's straight edges, as the Revolve tool offers
    them), or "u" / "v" for a face that lies to one side of the plane's axes.
    Returns ONLY the new solid — Join / Cut are the tree's combiners; the body
    is referenced, not consumed."""
    _face, _pl, profile = face_profile(solid, face_center, face_normal)
    if axis is None:
        raise ValueError(
            "revolve_face needs an axis: one of the face's straight edges as a "
            "line [[u1, v1], [u2, v2]] in the face's plane (what the Revolve tool "
            'offers), or "u" / "v"')
    return revolve_sketch(profile, axis, angle, angle2, both)


# ---------------------------------------------------------------------------
# Hole — Fusion's Hole tool as ONE op (LAUNCH-PLAN.md P4, specs/hole.md)
# ---------------------------------------------------------------------------

HOLE_KINDS = ("simple", "counterbore", "countersink")
# where a hole sits when nobody said: the frame's own origin. The op's default
# AND the planner's, so a feature stored without an `at` opens where it cuts.
HOLE_AT = (0.0, 0.0)
# "nothing was cut" is a MISS, not a small hole: a cutter that misses entirely
# leaves the volume unchanged to the last bit (probes/hole_review_probe.py §2
# measured exactly 0.0), while a genuine ⌀0.5 x 0.5 hole removes 0.098 mm³. A
# floor relative to the BODY refused real holes in big parts.
_CUT_FLOOR_MM3 = 1e-6


def hole_frame(face, at=None, point=None):
    """Where a hole sits on `face`: its true plane (face_profile_plane), the
    world centre of the point `at` = [u, v] in that plane, the outward normal
    there, and `at` itself — worked out from a world `point` (where the face
    was clicked) when the caller has none stored, and from the face's centre
    when there is neither. (u, v) on the axis-aligned faces of a box are the
    very x / y a sketch drawn on that face uses (probes/hole_probe.py §6:
    (5, 7, 10) on a top face -> (5, 7); (5, 7, -10) on the bottom face ->
    (5, 7)), and they ride the face when an upstream dimension moves it. The
    centre must lie ON the face — a hole may run out over an edge, its centre
    may not (Fusion's At Point). Shared by the op and the planner, so the
    marker and the cut agree and the flat-face guard exists ONCE."""
    pl = face_profile_plane(face)
    if pl is None:
        raise ValueError(
            f"the picked face is {face.geom_type.name} (curved) — a hole "
            f"starts on a FLAT face; tilted flat faces are fine")
    if at is None:                          # the click, in the face's own coordinates
        p = pl.to_local_coords(b3d.Vector(*point) if point else face.center())
        at = [round(p.X, 4), round(p.Y, 4)]
    try:
        u, v = float(at[0]), float(at[1])
    except (TypeError, IndexError, ValueError, KeyError):
        raise ValueError("hole: `at` must be [x, y] in the face's own "
                         f"coordinates (got {at!r})") from None
    centre = pl.from_local_coords(b3d.Vector(u, v, 0))
    if not face.is_inside(centre, tolerance=1e-3):
        raise ValueError(
            f"hole: the point ({u:g}, {v:g}) is not on the face — the hole's "
            f"centre must lie on it; click a point on the face")
    return pl, centre, face.normal_at(centre), [u, v]


def through_reach(solid) -> float:
    """How far a cut must reach to leave THIS body from any face: the shared
    THROUGH_MM (2 m — what every through extrude uses), and past the far side
    of anything bigger, so "through" can never quietly become a blind hole in a
    body deeper than the constant. One number for the op and the plan."""
    try:
        return max(THROUGH_MM, solid.bounding_box().size.length + 1.0)
    except Exception:                       # an unmeasurable body: the constant
        return THROUGH_MM


def material_depth(solid, origin, direction, span: float):
    """How much material lies under `origin` along `direction` before the
    first exit, in mm — the first piece of the line that is INSIDE the solid
    (probes/hole_probe.py §5: Edge ∩ Solid returns exactly those pieces; a box
    top at (5, 5) gives 20, the wedge's slanted face 45.96). None when the line
    finds no material at the face. The Hole plan's `limits.material`."""
    o = b3d.Vector(*origin)
    d = b3d.Vector(*direction).normalized()
    try:
        pieces = b3d.Edge.make_line(o - d * 1e-3, o + d * span).intersect(solid)
        edges = pieces.edges() if hasattr(pieces, "edges") else []
    except Exception:                       # a measurement, never a failure
        return None
    spans = sorted((min(a, b), max(a, b)) for a, b in
                   (((e @ 0 - o).dot(d), (e @ 1 - o).dot(d)) for e in edges))
    for lo, hi in spans:
        if hi > 1e-6:
            return round(hi, 4) if lo <= 1e-3 else None
    return None


def _csink_height(diameter: float, csink_diameter: float, csink_angle: float) -> float:
    """How deep a countersink's cone reaches below the face — ONE expression,
    read by the cutter that builds the cone and by the guard that refuses one
    deeper than the hole (they were two algebraically identical copies 57 lines
    apart; probes/hole_review_probe.py §5)."""
    return ((csink_diameter - diameter) / 2.0
            / math.tan(math.radians(csink_angle / 2.0)))


def hole_cutter(pl: Plane, centre, into, diameter: float, depth: float,
                kind: str = "simple", cbore_diameter: float = 0.0,
                cbore_depth: float = 0.0, csink_diameter: float = 0.0,
                csink_angle: float = 90.0):
    """The tool a hole removes, in a frame at the hole's centre whose z points
    INTO the material: the bore, plus a wider counterbore cylinder or a
    countersink cone whose wide end sits at the face. The cutter starts exactly
    at the face (probes/hole_probe.py §2: the coplanar cap builds clean — and
    material beside the hole ABOVE the face, a wall next to a step, is left
    alone, as in Fusion)."""
    A = (b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN)
    frame = Plane(origin=centre, x_dir=pl.x_dir, z_dir=into)
    r = diameter / 2.0
    tool = frame * b3d.Cylinder(r, depth, align=A)
    if kind == "counterbore":
        tool = tool + (frame * b3d.Cylinder(cbore_diameter / 2.0, cbore_depth, align=A))
    elif kind == "countersink":
        h = _csink_height(diameter, csink_diameter, csink_angle)
        tool = tool + (frame * b3d.Cone(bottom_radius=csink_diameter / 2.0,
                                        top_radius=r, height=h, align=A))
    return tool


def hole(solid, face_center: list | None = None, face_normal: list | None = None,
         face: str | None = None, at=HOLE_AT, diameter: float = 6.0,
         depth: float = 10.0, through: bool = False, kind: str = "simple",
         cbore_diameter: float = 0.0, cbore_depth: float = 0.0,
         csink_diameter: float = 0.0, csink_angle: float = 90.0):
    """Drill ONE hole into `solid` from a flat face (Fusion's Hole, At Point):
    the face by name (face="top"/"bottom"/"+x"/… — the authoring path) or by a
    real pick (face_center + face_normal, resolved by geometry at every
    rebuild), the centre `at` = [x, y] in that face's OWN plane (`hole_frame`:
    the sketch's x / y on an axis-aligned face, the face's true plane on a
    tilted one — they part company as the tilt grows), the
    bore `diameter` and `depth` from the face INTO the material — or `through`
    (Fusion's All), which runs out the far side whatever the thickness. `kind`
    "counterbore" adds a wider flat seat (cbore_diameter, cbore_depth) at the
    face, "countersink" a conical one (csink_diameter, csink_angle). Returns
    the body WITH the hole: this op eats its input, no cut feature follows.
    Every failure is a sentence in the hole's own words, and a cut that comes
    back broken or removes nothing is refused — a failed feature beats a
    corrupt body (probes/hole_probe.py §3)."""
    kind = str(kind or "simple").lower()
    if kind not in HOLE_KINDS:
        raise ValueError(f"hole: kind must be one of {list(HOLE_KINDS)} (got {kind!r})")
    through = _to_bool(through, "through")
    d = float(diameter or 0.0)
    if d <= 0:
        raise ValueError(f"hole: diameter must be positive (got {d:g}) — type a diameter")
    dep = float(depth or 0.0)
    if not through and dep <= 0:
        raise ValueError(f"hole: depth must be positive (got {dep:g}) — drag the arrow "
                         f"or type a depth, or tick Through all")
    cb_d, cb_h = float(cbore_diameter or 0.0), float(cbore_depth or 0.0)
    cs_d, cs_a = float(csink_diameter or 0.0), float(csink_angle or 0.0)
    # The seat's numbers are judged BEFORE the face is resolved: they are
    # certain refusals, and resolving a face on a big body costs ~400 ms, paid
    # by every half-typed value. A THROUGH hole has no depth for the seat to
    # sit inside, so those two comparisons only apply to a blind one (they used
    # to run against the bounding-box span and print a meaningless "112.4 mm").
    if kind == "counterbore":
        if cb_d <= d:
            raise ValueError(f"hole: the counterbore diameter ({cb_d:g} mm) must be larger "
                             f"than the hole diameter ({d:g} mm)")
        if cb_h <= 0:
            raise ValueError(f"hole: the counterbore depth must be positive (got {cb_h:g})")
        if not through and cb_h >= dep:
            raise ValueError(f"hole: the counterbore depth ({cb_h:g} mm) must be less than "
                             f"the hole depth ({dep:g} mm) — or tick Through all")
    elif kind == "countersink":
        if cs_d <= d:
            raise ValueError(f"hole: the countersink diameter ({cs_d:g} mm) must be larger "
                             f"than the hole diameter ({d:g} mm)")
        if not 0 < cs_a < 180:
            raise ValueError(f"hole: the countersink angle must be between 0° and 180° "
                             f"(got {cs_a:g}) — 90° is the usual seat")
        h = _csink_height(d, cs_d, cs_a)
        if not through and h >= dep:
            raise ValueError(f"hole: the countersink (⌀{cs_d:g} at {cs_a:g}°) is {h:.2f} mm "
                             f"deep and reaches past the hole's depth ({dep:g} mm) — "
                             f"deepen the hole or shrink the countersink")
    picked = pick_face(solid, face_center, face_normal, face)
    # the op never delegates its OWN default: hole_frame's point fallback is
    # the planner's (a click to turn into coordinates), and letting `at=None`
    # reach it would drill at the face centre while the plan says (0, 0)
    pl, centre, n, at = hole_frame(picked, list(HOLE_AT) if at is None else at)
    into = n * -1.0
    if through:                        # past the far side, whatever the body
        dep = through_reach(solid)
    where = f"⌀{d:g} hole at ({at[0]:g}, {at[1]:g})"
    try:                   # the CUTTER is built in here too: a kernel error
        tool = hole_cutter(pl, centre, into, d, dep, kind, cb_d, cb_h, cs_d, cs_a)
        out = solid - tool                       # while building it is still ours to explain
        v_in, v_out = solid.volume, out.volume   # ONE pass each, reused below
    except Exception as e:      # OCP errors derive from Exception, not RuntimeError
        raise ValueError(f"hole: the kernel could not cut the {where} here — move the "
                         f"hole or change its size") from e
    import inspector                                 # local: avoids an import cycle
    if v_in - v_out <= _CUT_FLOOR_MM3:
        raise ValueError(f"hole: nothing was cut — the {where} finds no material under "
                         f"the face; move it onto solid material")
    # the closed-shell census, without health's own second volume pass — the
    # rebuild runs the full check on what this returns (a failed feature beats
    # a corrupt body)
    if v_out <= 0 or not inspector.closed_shell(out):
        why = "empty result" if v_out <= 0 else "an open shell, not watertight"
        raise ValueError(f"hole: the {where} leaves a broken solid ({why}) — it is "
                         f"wider than the face allows or runs out through an edge; use a "
                         f"smaller diameter or move it inward")
    return out


# --------------------------------------------------------------------- shell ---
# Fusion's Shell (LAUNCH-PLAN P4, specs/shell.md): the body becomes walls of one
# thickness around a cavity, with the picked faces removed. probes/shell_probe.py
# (2026-09-10) found in the kernel:
#
#     offset(openings=[faces])            -> exact volumes on every corpus body
#     Kind.INTERSECTION                   -> sharp cavity corners (ARC rounds the OUTER
#                                            corners of an outward shell)
#     t = half the width, a face open     -> "succeeds" and returns the body UNCHANGED
#     t past the far wall, a face open    -> an OPEN SHELL the kernel calls a success
#     a closed hollow at t >= half        -> RuntimeError "offset Error"; t just under
#                                            it a bare ValueError "Null TopoDS_Shape"
#     a CURVED face as the opening        -> RuntimeError
SHELL_DIRECTIONS = ("inside", "outside")
_LEGACY_OPEN = {"top": "top", "bottom": "bottom", "none": None}


def shell_refs(faces=None, open_face=None) -> list:
    """A shell's openings in STORED form, normalised: the `faces` list as given
    (one ref becomes a list of one), or the legacy `open_face` read as one
    named face / none. A `faces` list beats `open_face`. Shared by the op and
    the planner, so both read a stored feature the same way."""
    if faces is None:
        if open_face is None:
            return []
        key = str(open_face).strip().lower()
        if key not in _LEGACY_OPEN:
            raise ValueError(f'shell: open_face must be "top", "bottom" or "none" '
                             f"(got {open_face!r}) — or give faces")
        return [_LEGACY_OPEN[key]] if _LEGACY_OPEN[key] else []
    if isinstance(faces, (str, dict)):
        return [faces]
    return list(faces)


def opening_face(solid, ref):
    """ONE stored opening -> the Face it names (a NAME, or a pick's centre +
    normal resolved by geometry), flatness not yet judged."""
    if isinstance(ref, str):
        return named_face(solid, ref)
    if isinstance(ref, dict) and ref.get("center") is not None:
        return resolve_face(solid, ref["center"], ref.get("normal"))
    raise ValueError(f'shell: an opening is a face name ("top", "+x", ...) or a '
                     f"pick {{center, normal}} — got {ref!r}")


def assert_flat_opening(face):
    """The kernel cannot offset a solid with a CURVED opening (probed: a
    cylinder's wall raises) — refused with the face's own type in the sentence."""
    if face_plane(face) is None:
        raise ValueError(f"shell: an opening must be a FLAT face — that face is "
                         f"{face.geom_type.name} (curved); pick a flat face")
    return face


def shell_openings(solid, faces=None, open_face=None) -> list:
    """The opening Faces a shell's stored params mean — resolved, flat,
    de-duplicated (two picks can name one face)."""
    from blocks import _shape_key            # local: blocks imports this module's resolver
    out, seen = [], set()
    for ref in shell_refs(faces, open_face):
        f = assert_flat_opening(opening_face(solid, ref))
        k = _shape_key(f)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def shell(solid, thickness: float = 0.0, faces=None, direction: str = "inside",
          open_face=None):
    """Hollow `solid` into walls of `thickness` (Fusion's Shell). `faces` lists
    the openings — each a face NAME ("top"/"bottom"/"+x"/… — the authoring
    path) or a pick {center, normal} resolved by geometry at every rebuild;
    none = a closed hollow body. `direction` "inside" grows the walls inward
    (the outside stays), "outside" adds them around the body (the old surface
    becomes the cavity). The legacy `open_face` ("top"/"bottom"/"none") is read
    as one named face when `faces` is not given. Returns the hollowed body:
    this op eats its input. Every failure is a sentence, and a result that is
    unchanged or not watertight is refused — the kernel calls both a success
    (probes/shell_probe.py §6)."""
    t = float(thickness or 0.0)
    if t <= 0:
        raise ValueError(f"shell: thickness must be positive (got {t:g}) — drag the "
                         f"arrow or type a wall thickness")
    d = str(direction or "inside").strip().lower()
    if d not in SHELL_DIRECTIONS:
        raise ValueError(f'shell: direction must be "inside" or "outside" (got {direction!r})')
    openings = shell_openings(solid, faces, open_face)
    walls = f"walls of {t:g} mm"
    try:
        amount = -t if d == "inside" else t
        if openings:
            out = b3d.offset(solid, amount=amount, openings=openings, kind=b3d.Kind.INTERSECTION)
        else:
            # no opening: offset() returns the offset SOLID (the box, shrunk or
            # grown — probed: 46464 = the 44 x 44 x 24 inner box, a "success"
            # the direction check would have passed); the hollow is the difference
            off = b3d.offset(solid, amount=amount, kind=b3d.Kind.INTERSECTION)
            out = solid - off if d == "inside" else off - solid
        v_in, v_out = solid.volume, out.volume
    except Exception as e:      # OCP errors derive from Exception; build123d raises bare ValueErrors
        raise ValueError(f"shell: {walls} do not fit this body — the kernel could not "
                         f"offset its faces; use a thinner wall or open another face") from e
    import inspector                                 # local: avoids an import cycle
    # the walls alone are what comes back, so an OUTSIDE shell is smaller than
    # the body too (28488 vs 75000 on the probe's box); only an inside one must be
    if abs(v_out - v_in) <= _CUT_FLOOR_MM3 or (d == "inside" and v_out >= v_in):
        raise ValueError(f"shell: nothing was hollowed — {walls} meet in the middle of "
                         f"this body; use a thinner wall")
    if v_out <= 0 or not inspector.closed_shell(out):
        why = "empty result" if v_out <= 0 else "an open shell, not watertight"
        raise ValueError(f"shell: {walls} leave a broken solid ({why}) — use a thinner wall")
    return out


def loft_sketches(sketches: list):
    """Blend between two or more sketches (usually on parallel, offset planes)
    to make a smoothly-transitioning solid."""
    if len(sketches) < 2:
        raise ValueError("loft needs at least 2 sketches")
    return _loft(list(sketches))


def sweep_sketch(sketch, path_points: list, smooth: bool = False):
    """Drag a profile sketch along a path defined by 3D points [[x,y,z],...].
    smooth=True fits a spline through the points; otherwise straight segments."""
    smooth = _to_bool(smooth, "smooth")
    pts = [(float(p[0]), float(p[1]), float(p[2])) for p in path_points]
    if len(pts) < 2:
        raise ValueError("sweep path needs >= 2 points")
    with BuildLine() as bl:
        if smooth and len(pts) >= 3:
            Spline(*pts)
        else:
            Polyline(*pts)
    return _sweep(sketch, path=bl.line)


# ops that produce a 2D sketch (not a solid) — the document engine checks these
# for area, not solid health
SKETCH_PRODUCERS = {"sketch", "sketch_on_face"}

# ops whose solid input is only a FACE REFERENCE (where to work), never
# geometric consumption: a sketch drawn on a box's face does not eat the box,
# and extrude_face outputs a separate boss solid while the source body lives
# on. The document engine must NOT count their inputs as "consumed" or the
# referenced body vanishes from the viewport the moment the sketch is used
# (reported: "after finishing the sketch and extruding, the main body
# vanishes").
FACE_REFERENCE_OPS = {"sketch_on_face", "extrude_face", "revolve_face"}


def is_sketch(obj) -> bool:
    return isinstance(obj, b3d.Sketch)
