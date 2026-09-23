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
    ThreePointArc, make_face, Transition,
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
    # a word as sketch faces (build123d Text, centred on x / y): the height is
    # the only dimension; the WORD is a string field (ENTITY_STRINGS)
    "text":            [("size", "height", "mm")],
}

# entities that carry a STRING the tree edits as text, not a number
ENTITY_STRINGS = {"text": [("text", "word"), ("font", "font")]}

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
        "strings": {k: [{"key": a, "label": b} for a, b in v]
                    for k, v in ENTITY_STRINGS.items()},
        # kinds whose outline the browser cannot draw itself (a font's glyphs):
        # it asks POST /api/sketch/outline for the loops (R1)
        "server_outline": ["text"],
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
    elif k == "text":
        s = _text_faces(e)
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


TEXT_FONT = "Arial"          # the font a text entity uses when none is named


def _text_faces(e: dict):
    """A WORD as sketch faces — build123d `Text`, centred on the entity origin
    (x / y place the word's centre, like every other entity's). Measured
    (probes/text_api_probe.py): each glyph piece is a finished face with its
    holes as inner wires (O has 1, B has 2), so it composes with + / − like any
    shape — `plate − text` IS the engraving; an unknown font falls back to
    Arial with a kernel warning on stderr; the font manager finds Arial,
    Times New Roman, Courier New and Consolas on this box; letters stay valid
    faces down to 0.1 mm, so the only floor is the positive-size rule."""
    txt = e.get("text")
    if not isinstance(txt, str) or not txt.strip():
        raise ValueError("text entity needs a word — its `text` is empty; type the "
                         "word to write, or remove the entity")
    size = float(e.get("size") or 0.0)
    if size <= 0:
        raise ValueError(f"text height must be greater than 0, got {size:g}")
    font = e.get("font") or TEXT_FONT
    if not isinstance(font, str):
        raise ValueError(f"text font must be a name such as {TEXT_FONT!r}, got {font!r}")
    try:
        with BuildSketch() as bs:
            b3d.Text(txt, size, font=font, align=(b3d.Align.CENTER, b3d.Align.CENTER))
        s = bs.sketch
    except Exception as exc:                        # noqa: BLE001
        raise ValueError(
            f"text entity: the font could not shape {txt!r} — try plain letters and "
            f"digits, or another font") from exc
    if s is None or not s.faces():
        raise ValueError(f"text entity: {txt!r} has no printable letters — spaces and "
                         f"punctuation alone make no shape")
    return s


def entity_outlines(e: dict) -> list[list[list[float]]]:
    """The loops of ONE entity in the sketch's local 2D — every face's outer
    wire and holes, sampled — for a kind the browser cannot draw itself
    (text). Placement and rotation are applied exactly as `_entity` applies
    them, so the sketcher draws what the kernel builds."""
    shape = _entity(e)
    loops = []
    for f in shape.faces():
        for w in f.wires():
            pts = []
            for ed in w.edges():
                n = 2 if ed.geom_type == b3d.GeomType.LINE else 12
                for i in range(n):
                    p = ed @ (i / n)
                    pts.append([round(float(p.X), 4), round(float(p.Y), 4)])
            if len(pts) >= 3:
                loops.append(pts)
    return loops


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


def _compose_order(shapes: list, modes: list | None = None,
                   problems: list | None = None) -> list[int]:
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

    Why the overlap pass runs for EVERY cut and not just a leading one (FIFTH
    review of this rule, 2026-09-11, measured while fixing the Trim item):
    the pass used to run only while the order actually STARTED with a cut, so
    one unrelated shape drawn first switched it off and the same P0 came
    straight back through the next door. `[boss, bar, pocket]` composed the
    correct 22.3648 mm2; adding a far-away circle at the FRONT — a shape that
    touches none of them — gave 157.0796 instead of 100.9046, the boss built
    SOLID with the bar's 56.17 mm2 of red paint lost, green and silent. A cut
    hoisted ahead of the material it bites is lost whether it leads or not:
    leading it is dropped, second it subtracts from something it does not
    touch. Same damage, so the same rule has to cover both, and the result
    stops depending on where in the list a shape was drawn.

    The pass still costs the ordinary sketch nothing: it is reached only when
    something subtracts, it pairs a cut with MATERIAL only, and a hole sitting
    in its plate is a nested pair it skips without measuring. Measured on the
    user's library at ship time — see `tests/test_trim_composition.py`.
    """
    n = len(shapes)
    inside = _containment(shapes)
    needs = [row[:] for row in inside]          # needs[i][j]: j before i
    if modes is None:
        return _order_from(needs, problems)
    for i in range(n):
        if modes[i] != "subtract":
            continue
        for j in range(n):
            if (i == j or modes[j] == "subtract"
                    or needs[i][j] or needs[j][i]      # already ordered
                    or inside[i][j] or inside[j][i]):  # nested: an island
                continue
            if _overlaps(shapes[j], shapes[i]):
                needs[i][j] = True              # the material goes first
    return _order_from(needs, problems)


def _knot_members(needs: list[list[bool]], done: list, seed: int) -> list[int]:
    """The shapes actually caught in the knot around `seed` — the ones it can
    reach and that can reach it back, over the shapes not yet placed.

    Round three of the `3b230b7` review, 2026-09-11: naming every unplaced
    shape instead was an OVERCLAIM. Put a small hole inside one of the knot's
    adds and the note said "entities 1, 2, 3, 4 and 5 ... each has to come
    both before and after another shape it overlaps" — false about entity 5,
    which is in no cycle at all and is merely waiting on one. A warning that
    points at the wrong shape costs the user the time it was written to save.
    """
    live = [i for i in range(len(needs)) if not done[i]]

    def walk(start, forward: bool) -> set:
        seen, todo = {start}, [start]
        while todo:
            k = todo.pop()
            for i in live:
                if i in seen:
                    continue
                # needs[i][j] == "j must come before i", so j -> i is an edge
                if (needs[i][k] if forward else needs[k][i]):
                    seen.add(i)
                    todo.append(i)
        return seen

    return sorted(walk(seed, True) & walk(seed, False))


def _order_from(needs: list[list[bool]],
                problems: list | None = None) -> list[int]:
    """A stable topological order over `needs[i][j] == "j must come before i"`:
    of the entities whose predecessors are all placed, always the one the user
    drew first.

    Some sketches ask for an order that does not exist. Two cuts that overlap
    each other, each containing an add that pokes into the other, demand
    `cut1 -> add1 -> cut2 -> add2 -> cut1`; no sequence of adds and subtracts
    can honour it, because add1 has to survive cut1 and be bitten by cut2
    while add2 needs the mirror image. The loop below still produces an
    order — it falls back to the one the user drew — but the answer is then a
    rule the builder KNOWS it broke, and it used to say nothing: the case
    above builds 210.0 mm2 where the paint says 180.0, green and silent
    (measured 2026-09-11, the review of 3b230b7). `problems` collects the
    entities caught in such a knot so `compose` can tell the user.
    """
    n = len(needs)
    waiting = [sum(row) for row in needs]
    order: list[int] = []
    done = [False] * n
    while len(order) < n:
        nxt = next((i for i in range(n) if not done[i] and not waiting[i]),
                   None)
        if nxt is None:                         # a cycle we cannot order:
            nxt = next(i for i in range(n) if not done[i])   # fall back to
            if problems is not None:            # the drawing order, and SAY SO
                # ONLY when this shape is really on a cycle. The fallback
                # takes the lowest unplaced shape, which is often one that
                # merely WAITS on the knot, and it fires once per stuck
                # shape — so recording every seed put a blameless entity back
                # into the sentence round three had just taken it out of
                # (round four, 2026-09-11). Its own knot is named by the
                # later fallback that lands inside the cycle.
                members = _knot_members(needs, done, nxt)
                if len(members) > 1:
                    problems.extend(members)
        done[nxt] = True
        order.append(nxt)
        for i in range(n):
            if needs[i][nxt] and not done[i]:
                waiting[i] -= 1
    return order


def _knot_note(knotted: list) -> str:
    """The sentence for an order that cannot exist.

    It names EVERY entity caught in the knot, not just the one the fallback
    happened to pick first: the user has to find the pair that overlaps and
    contains at the same time, and one number out of four does not point at
    it (review round two of `3b230b7`, 2026-09-11). Entity numbers are the
    stored positions — the ones the tree shows — like every other note here.
    """
    rows = sorted(set(knotted))
    if len(rows) > 1:
        names = (", ".join(str(i + 1) for i in rows[:-1])
                 + f" and {rows[-1] + 1}")
        head = f"entities {names} cannot all be put in a build order"
    else:                                   # a knot needs two shapes, so this
        head = f"entity {rows[0] + 1} cannot be put in a build order"
    return (f"{head} — each has "
            f"to come both before and after another shape it overlaps, so "
            f"this part of the sketch is built in the order you drew it and a "
            f"cut here may not remove what you expect. Move one of them so it "
            f"sits either fully inside the shape it overlaps or fully clear "
            f"of it.")


def _order_of(shapes: list, modes: list,
              problems: list | None = None) -> list[int]:
    """The composition order for these shapes — the all-add shortcut in one
    place, so `compose` and `compose_order` cannot drift apart."""
    if not any(m == "subtract" for m in modes):
        return list(range(len(shapes)))     # nothing to order: no measurement
    return _compose_order(shapes, modes, problems)


def compose_order(entities: list) -> list[int]:
    """The positions of `entities` in the order the BUILDER composes them.

    Public for the same reason as `compose`: a caller that has to replay the
    sketch's arithmetic — `sketch_trim` classifying which side of a segment
    holds material — must replay it in THIS order, not the drawing order. On
    `[boss, bar, pocket]` the drawing order said "no material" at a point the
    builder fills, so a Trim click offered to dissolve a seam that was really
    the profile's own edge (measured 2026-09-11).
    """
    shapes = [_entity(e) for e in entities]
    return _order_of(shapes, [e.get("mode", "add") for e in entities])


def compose(entities: list, note: bool = True):
    """Combine entities (add/subtract) into a 2D sketch in local coords,
    OUTERS BEFORE THE HOLES INSIDE THEM.

    PUBLIC, and the only copy of this rule in the codebase. `sketch_trim`
    kept a second one and the two disagreed: on `[boss, bar, pocket]` the
    builder composed 22.3648 mm2 and Trim composed 0.0, so every Trim click
    on that cluster answered "the result would have no area left" (measured
    2026-09-11, LAUNCH-PLAN section 10 P1). Anything that needs to know what
    a sketch's entity list MEANS calls this, or `compose_order` for just the
    order. `note=False` composes silently — for a caller answering a question
    about the sketch rather than building the user's feature, whose notes
    would otherwise be drained into the next feature's warnings.

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
    # An OPEN path (`closed: false`, the Sweep tool's path) encloses nothing,
    # so it takes no part in the arithmetic; `_place_sketch` carries it on the
    # sketch as a wire instead.
    closed = [e for e in (entities or []) if not is_open_path(e)]
    if not closed:
        if entities:
            raise ValueError(
                "this sketch holds only open paths (drawn for Sweep) and no "
                "closed shape — there is no area to fill")
        raise ValueError("sketch has no entities")
    entities = closed
    shapes = [_entity(e) for e in entities]
    modes = [e.get("mode", "add") for e in entities]
    knotted: list = []
    order = _order_of(shapes, modes, knotted)
    if knotted and note:
        _note(_knot_note(knotted))
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
                if note:
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


def is_open_path(e: dict) -> bool:
    """A `path` entity drawn OPEN (`closed: false`) — the sketch ribbon's Path
    tool, for Sweep. It builds no face; `_place_sketch` carries it as a wire."""
    return isinstance(e, dict) and e.get("kind") == "path" and e.get("closed") is False


def is_path_sketch(entities) -> bool:
    """Every entity is an open path: a PATH sketch (area 0), the kind Sweep
    follows and Extrude / Revolve refuse with a sentence."""
    ents = entities or []
    return bool(ents) and all(is_open_path(e) for e in ents)


def sketch_paths(sketch) -> list:
    """The open-path wires a built sketch carries (world coordinates, in the
    order they were drawn) — [] for a sketch of closed shapes only."""
    return list(getattr(sketch, "_tc_paths", None) or [])


def _path_wire(e: dict, pl: Plane):
    """An OPEN path entity as ONE wire lying on `pl` — the same line / arc
    grammar as `_path_face`, without the auto-close and without a face. The
    entity's own x / y / rotation apply exactly as `_entity` applies them to
    a closed one (rotate about the entity origin, then place)."""
    segs = e.get("segments") or []
    if not segs:
        raise ValueError("path entity needs at least 1 segment")
    if not e.get("start"):
        raise ValueError(
            "path entity has no start point — the editor shows no profile "
            "for it at all; redraw it")
    x = float(e.get("x") or 0.0)
    y = float(e.get("y") or 0.0)
    rot = math.radians(float(e.get("rotation") or 0.0))
    c, s = math.cos(rot), math.sin(rot)

    def place(p):
        px, py = float(p[0]), float(p[1])
        return (px * c - py * s + x, px * s + py * c + y)

    def world(p):
        return pl.from_local_coords((p[0], p[1], 0))

    cur = place(_xy("the path entity's start point", e["start"]))
    edges = []
    for n, seg in enumerate(segs, start=1):
        to = place(_seg_point("end", n, seg.get("to")))
        if abs(to[0] - cur[0]) < 1e-6 and abs(to[1] - cur[1]) < 1e-6:
            raise ValueError(
                f"path segment {n} starts and ends at the same point — "
                f"two clicks landed in one snap cell; move one of them")
        is_arc = seg.get("type") == "arc"
        via = (place(_seg_point("middle", n, seg.get("via")))
               if is_arc else None)
        try:
            edges.append(ThreePointArc(world(cur), world(via), world(to))
                         if is_arc else Line(world(cur), world(to)))
        except Exception as exc:            # noqa: BLE001
            what = ("arc {0}: no curve passes through its three points — "
                    "the middle point lies on the straight line between "
                    "its ends, or sits on top of one of them; move it off "
                    "that line" if is_arc else
                    "segment {0} could not be drawn — its two ends are "
                    "the same point")
            raise ValueError("path entity, " + what.format(n)) from exc
        cur = to
    # Edge by edge, never through BuildLine: a segment that doubles back over
    # the one before it is DROPPED there without a word (measured
    # 2026-09-17, probes/sweep_hairpin_probe.py — up 20 and back 19.5 came
    # out as one 20 mm edge, and the sweep along it was a green straight
    # tube). What the kernel kept must be what the user drew.
    wire = b3d.Wire(edges)
    drawn = sum(ed.length for ed in edges)
    if len(wire.edges()) != len(edges) or abs(wire.length - drawn) > 1e-6 * max(1.0, drawn):
        raise ValueError(
            "path entity: a segment runs back over the one before it, so the "
            "kernel would drop part of the path — give the path a corner or a "
            "bend instead of a hairpin")
    return wire


def _place_sketch(pl: Plane, entities: list | None):
    """Compose the closed entities on `pl` and carry the open paths as wires.

    ONE home for `make_sketch` and `sketch_on_face`. A sketch of open paths
    only is a Sketch of EDGES (area 0, `is_sketch` True): the viewport draws
    its edges as outlines like any other, a move carries it, and Sweep reads
    the wires back off `_tc_paths` (probes/sweep_api_probe6.py). An empty
    Sketch cannot be placed on a plane at all (probe 5), which is why the
    paths are built ON the plane rather than composed in 2D and moved."""
    ents = entities or []
    paths = [_path_wire(e, pl) for e in ents if is_open_path(e)]
    closed = [e for e in ents if not is_open_path(e)]
    if closed:
        sketch = _as_sketch(pl * compose(closed))
        if paths:
            sketch = b3d.Sketch(children=[*sketch.faces(),
                                          *(ed for w in paths for ed in w.edges())])
    elif paths:
        sketch = b3d.Sketch(children=[ed for w in paths for ed in w.edges()])
    else:
        sketch = _as_sketch(pl * compose(ents))    # says "sketch has no entities"
    sketch._tc_paths = paths
    return _on_plane(sketch, pl)


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
                entities: list | None = None, _plane=None):
    """Compose entities into one Sketch placed on a principal plane — or on an
    `offset_plane` feature the document hands in as `_plane` (the sketch's
    `plane` then names that feature, the way a sweep's `path` names a sketch).

    plane: "XY", "XZ" or "YZ", or the id of an offset plane.  offset: shift
    the plane along its normal.  entities: list of {"kind":..., ...params,
    "mode":"add"|"subtract"}. The first entity must be additive."""
    if _plane is not None:
        pl = _plane.offset(float(offset)) if offset else _plane
    else:
        pl = sketch_plane(plane, offset)
    return _place_sketch(pl, entities)


def offset_plane(solid=None, plane: str = "XY", offset: float = 0.0,
                 face: str | None = None, face_center: list | None = None,
                 face_normal: list | None = None, face_area: float | None = None):
    """Fusion's Construct > Offset Plane: a construction plane a distance
    `offset` from a principal plane (no input) or from a flat FACE of `solid`
    (the input body, named the two ways sketch_on_face names a face). The
    result is a build123d Plane — not a solid, not a sketch: sketches are
    drawn on it (`sketch` with `plane` = this feature's id) and move with it
    when its offset changes. The face frame is `face_sketch_plane`'s, so which
    sign goes INTO the material is that frame's (face_outline_2d.into_sign),
    never one rule for every face."""
    off = float(offset or 0.0)
    if solid is None and (face or face_center or face_normal):
        # A named face with no body used to be IGNORED: the plane was quietly
        # measured from the principal plane instead, at the same number, and
        # the row said "ok" (code review 2026-09-23). Wrong placement is the
        # worst class there is, so the face wins the argument and the op says
        # what is missing.
        raise ValueError(
            "offset_plane: a face is named but no body was given — an offset "
            "plane off a face takes that body as its input; give the body, or "
            "drop the face to measure from the {} plane".format(plane))
    if solid is not None:
        picked = pick_face(solid, face_center, face_normal, face, face_area)
        pl = face_sketch_plane(picked)
        if pl is None:
            raise ValueError(
                f"offset_plane: the picked face is {picked.geom_type.name} and not "
                f"flat — an offset plane needs a PLANAR face or a principal plane")
    else:
        pl = sketch_plane(plane, 0.0)            # the op's own sentence on a bad name
    return pl.offset(off) if off else pl


def is_plane(obj) -> bool:
    """A construction plane (an `offset_plane` feature's result)."""
    return isinstance(obj, Plane)


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
                    face: str | None = None, offset: float = 0.0,
                    face_area: float | None = None):
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
        picked = resolve_face(solid, face_center, face_normal, face_area)
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
    # which SIGN of `offset` moves the plane INTO the material: the frame is
    # canonicalised (see face_sketch_plane), so on a top / +x / +y face its z
    # points OUT of the body and a negative offset goes in, on a bottom / -x /
    # -y face the opposite. A server fact for the sketch-plane handle (R1);
    # the same rule sketch_on_face's docstring states in words.
    outward = picked.normal_at(picked.center())
    into_sign = -1 if outward.dot(pl.z_dir) > 0 else 1
    return {"outer": project(outer), "holes": holes, "planar": True,
            "frame": frame, "into_sign": into_sign}


def pick_face(solid, face_center: list | None = None,
              face_normal: list | None = None, face: str | None = None,
              face_area: float | None = None):
    """The face an op names, the two ways it may: by DIRECTION (face="top"/
    "+x"/…, the authoring path — no coordinates to compute, so none to get
    wrong) or by a real pick's centre + normal (resolved by geometry at every
    rebuild, so the pick survives parameter changes). ONE rule for
    sketch_on_face, hole and the planner."""
    if face:
        return named_face(solid, face)
    if face_center is not None:
        return resolve_face(solid, face_center, face_normal, face_area)
    raise ValueError('the face is not named — give face="top"/"bottom"/"+x"/... '
                     "or a face_center from an actual pick")


def sketch_on_face(solid, face_center: list | None = None,
                   face_normal: list | None = None,
                   entities: list | None = None, offset: float = 0.0,
                   face: str | None = None, face_area: float | None = None):
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
    picked = pick_face(solid, face_center, face_normal, face, face_area)
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
    return _place_sketch(pl, entities)


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
                 amount: float = 10.0, taper: float = 0.0, flip: bool = False,
                 face_area: float | None = None):
    """Extrude a planar FACE of an existing solid (the Fusion workflow: click a
    face, press Extrude, pull the arrow). The face is resolved by GEOMETRY at
    every rebuild (nearest center + matching normal), so the pick survives
    parameter changes. Returns ONLY the extruded prism — combine it with the
    body via fuse (boss) or cut (pocket, with a negative/into amount).
    The face's exact outline is used — holes and curved edges included."""
    face = resolve_face(solid, face_center, face_normal, face_area)
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
        if t:
            # The taper IS dropped (a 2 m tapered prism collapses), but it may
            # not be dropped in silence: the panel's taper box and dashed ring
            # went on showing an angle the solid did not have — measured
            # 2026-09-11, a -10 deg through cut built 20 x 30 x 2000 mm, dead
            # straight. extrude.js zeroes the box; this is the same fact for
            # the AI, the MCP and the API.
            _note(f"Through all ignores the {-t:g} deg taper - a cut that runs "
                  f"{THROUGH_MM:g} mm cannot taper; untick Through all and give "
                  f"a distance for tapered walls")
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
    # abs: `amount2` IS "the other way", so its sign carries nothing. Typed
    # negative it used to be dropped without a word — amount 8 + amount2 -5
    # built 4800 mm3, the first side alone (measured 2026-09-11).
    amt2 = abs(float(amount2 or 0.0))
    if amt2 > 0:                      # two-sided: opposite direction by amt2
        s2 = -1.0 if a >= 0 else 1.0
        solid = solid + _tapered_extrude(sketch, s2 * amt2, t)
    return solid


_LOCAL_AXES = {"u": "x_dir", "v": "y_dir"}      # a sketch plane's own axes
MAX_REVOLVE_DEG = 360.0                          # one full turn either way


def face_profile(solid, face_center: list, face_normal: list | None = None,
                 verb: str = "revolved", face_area: float | None = None):
    """A flat face of `solid`, resolved by GEOMETRY (extrude_face's rule: nearest
    centre, matching normal), as the profile a sketch op reads — the face, its
    true plane (`face_profile_plane`) and the Sketch carrying that plane. ONE
    home for the op AND the planner, so the handles and the solid come from the
    same object. The one sentence for a curved face."""
    face = resolve_face(solid, face_center, face_normal, face_area)
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
                 both: bool = False, face_area: float | None = None):
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
    _face, _pl, profile = face_profile(solid, face_center, face_normal,
                                       face_area=face_area)
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
# a result lump identical to one that went in, in mm: the kernel rebuilds even
# the lump it did not touch, and that rebuild measured 0.0 off its input's box
# over 99 lumps (probes/shell_round3_sweep_probe.py)
_SHELL_BOX_TOL_MM = 1e-6


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
         face: str | None = None, face_area: float | None = None,
         at=HOLE_AT, diameter: float = 6.0,
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
    picked = pick_face(solid, face_center, face_normal, face, face_area)
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
    try:
        return list(faces)
    except TypeError:                    # a file / AI value that is not a list:
        raise ValueError(                # `TypeError: 'int' object is not iterable`
            f"shell: faces must be a list of openings — a face name "
            f'("top", "+x", ...) or a pick {{center, normal}} each '
            f"(got {faces!r})") from None


def opening_face(solid, ref):
    """ONE stored opening -> the Face it names (a NAME, or a pick's centre +
    normal resolved by geometry), flatness not yet judged."""
    if isinstance(ref, str):
        return named_face(solid, ref)
    if isinstance(ref, dict) and ref.get("center") is not None:
        return resolve_face(solid, ref["center"], ref.get("normal"),
                            ref.get("area"))
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


def assert_every_lump_open(solid, openings: list) -> None:
    """A body in SEVERAL separate lumps (a pattern's copies, a cut that severed
    a plate) may only be shelled WITH openings if every lump has one.

    Measured 2026-09-10 (review of fb0b8c8): `offset(openings=[…])` shells only
    the lumps a listed face belongs to and hands back the raw offset SOLID for
    the rest — three 20 x 20 x 10 boxes at t = 2, one top open, came back
    [1952, 1536, 1536] where a closed shell is 2464, and Outside came back
    [2912, 8064, 8064]: blocks GROWN by 2 mm. Every check passed it (one solid
    per lump, watertight, health [], the volume neither unchanged nor zero), so
    two of the three bosses silently became smaller blocks with a green row.
    With an opening on every lump the kernel is exact (1952 each), and with NO
    opening the difference route is exact too (2464 / 4064 each) — so only this
    one case is refused."""
    if not openings:
        return                           # the difference route: correct per lump
    lumps = solid.solids()
    if len(lumps) < 2:
        return
    from blocks import _shape_key        # local: blocks imports this module's resolver
    keys = {_shape_key(f) for f in openings}
    bare = sum(1 for lump in lumps
               if not any(_shape_key(f) in keys for f in lump.faces()))
    if bare:
        raise ValueError(
            f"shell: this body is in {len(lumps)} separate lumps and {bare} of "
            f"them {'has' if bare == 1 else 'have'} no face open — the kernel "
            f"would leave {'it' if bare == 1 else 'them'} a solid block instead "
            f"of walls. Open a face on every lump, or none at all (a closed hollow)")


def _box6(shape) -> tuple:
    """A shape's bounding box as six numbers — its place AND its size, where a
    centre alone is only its place (see `assert_every_lump_hollowed`)."""
    b = shape.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


def assert_every_lump_hollowed(solid, out, direction: str, walls: str) -> None:
    """The sibling of `assert_every_lump_open`, and the SAME P0 through another
    door: that one asks that every lump have an opening, this one that no lump
    came back UNTOUCHED. It has to run AFTER the kernel because only the kernel
    knows whether a wall fits a particular lump.

    Measured 2026-09-11 (round two of the review of fb0b8c8,
    probes/shell_round2_confirm_probe.py): with a top open on EVERY lump — so
    the opening guard is satisfied — a lump the thickness does not fit comes
    back exactly as it went in. 20 x 20 x 10 beside 3 x 20 x 10 at t = 2 gave
    [1952, 600], where 600 is the raw block; beside 20 x 20 x 4 at t = 5 it
    gave [3500, 1600] the same way; three patterned bosses with the middle one
    narrow left that one solid. Every check passed: watertight, health [], the
    total volume down, the row green. ALONE each of those small lumps is
    correctly refused ("nothing was hollowed") — it is the WHOLE-BODY volume
    check that a second, bigger lump defeats, because the big lump's hollow
    pays for the small one's block.

    A result lump is that block when it is IDENTICAL to a lump that went in —
    same bounding box, same volume. Nothing is paired up and nothing is
    measured by distance, because both invite an error the geometry cannot
    justify: round two paired result lumps to input lumps by nearest bounding
    box CENTRE, and two CONCENTRIC lumps (a post inside a ring, a spigot in a
    bore) share a centre exactly, so the tie sent both results to one seat,
    left the other empty and REFUSED a shell the kernel had built perfectly
    (measured round three: ring 3628.54 and post 458.28, both to the oracle's
    own decimal, watertight, health []). The whole BOX tells those two apart
    where the centre cannot — 40 x 40 x 10 against 10 x 10 x 10.

    Identity is exact, not a judgement call: over 99 result lumps across five
    second-lumps and ten thicknesses in both directions
    (probes/shell_round3_sweep_probe.py) an untouched lump matched its input at
    d(volume) 0.0 and d(box) 0.0 — 1.1e-13 at worst — while the closest a
    lump that really did hollow ever came was 0.992 of its input (an honest
    4 x 4 x 2 cavity at t = 8). So this can only ever fire on the block."""
    lumps = solid.solids()
    if len(lumps) < 2:
        return                           # the whole-body check above IS this one
    was = [(_box6(lump), lump.volume) for lump in lumps]
    bare = sum(1 for piece in out.solids()
               if any(abs(piece.volume - v) <= _CUT_FLOOR_MM3
                      and all(abs(a - b) <= _SHELL_BOX_TOL_MM
                              for a, b in zip(_box6(piece), box))
                      for box, v in was))
    if bare:
        raise ValueError(
            f"shell: {walls} do not fit {bare} of the {len(lumps)} separate lumps "
            f"of this body — the kernel handed "
            f"{'that one' if bare == 1 else 'those'} back as a solid block "
            f"instead of walls. Use a thinner wall")


# How many times `area * t` the walls of an inward shell may measure before the
# result is refused as the body itself. Re-calibrated 2026-09-17 over THREE
# corpora and moved down from 2.0, because 2.0 was measured to let a wrong
# result through:
#
#   * the gauntlet corpus and the committed crash bodies, nine thicknesses from
#     0.2 to 8 mm (probes/shell_wall_bound_corpus.py): the highest a SOUND
#     closed hollow reached is 1.0559 (the oneplus case at t = 0.5);
#   * the user's own 50 designs at t = 1/2/3, the check patched off so a result
#     it would refuse is still measured (probes/shell_skin_library_probe.py):
#     38 sound results, the highest 1.0377, and four wrong ones at 2.0524 and
#     2.7189;
#   * concave-heavy plates whose `t/2r` is dialled straight through the danger
#     zone, every result over 1.0 put to an independent Monte Carlo oracle
#     (probes/shell_skin_concave_sweep.py). This is the one that moved the
#     number. A hole of radius r shelled at t leaves an annulus, so its own
#     ratio is `1 + t/2r` and rises with t — and the sweep found BOTH edges of
#     the real band there:
#         a 60 x 60 x 10 plate, 196 holes of r 0.8 at 4 mm pitch, t = 1.0:
#             21,107.5 mm3 of walls against an oracle of 20,908 +/- 187 (1.1
#             sigma) — CORRECT, and the highest correct result on record at
#             1.1309;
#         the same plate with 100 holes of r 1.0 at 6 mm pitch, t = 1.0:
#             27,429.7 mm3 against an oracle of 16,212 +/- 189 — 59 SIGMA out,
#             11,218 mm3 of "walls" that are not there, and it reads 1.7981;
#             at t = 1.3 the kernel hands the whole body back (32,858.3 against
#             20,464 +/- 188) and that reads 1.6569.
#
# So the lowest WRONG result on record is 1.6569, not 2.72, and the old ceiling
# of 2.0 passed both of those silently. 1.35 sits 1.19x above every correct
# result ever measured and 1.23x below the nearest wrong one. That is a
# narrower band than it looks from the old numbers, and it is the honest state
# of it: a body whose surface is MOSTLY small holes has correct walls of
# `1 + t/2r`, so the two sides really are converging, and anything tighter
# would start refusing the user's drilled plates.
#
# 2026-09-17, the review of that re-calibration: the two sides do not converge,
# they OVERLAP, and no constant here can ever separate them. The sweep behind
# the numbers above drilled its holes into a 60 x 60 x **10** plate and never
# varied the thickness, which is the one dimension that decides the answer —
# a drilled plate's ratio is `1 + (hole area / area) * t/2r`, so the same
# drilling in a THICKER plate has more hole wall per flat face and climbs
# towards the hole's own `1 + t/2r` without becoming any harder to shell.
# Measured exactly, with no sampling error at all, against the closed form for
# a drilled box (probes/shell_skin_thick_plate_probe.py):
#
#   50 x 50 x 60, 81 holes of r 0.4 at 5 mm pitch, t = 1.8:
#       95,594.085 mm3 of walls against a closed-form 95,594.085 — EXACT to
#       every digit, valid, watertight, health clean — and it reads 1.8229,
#       ABOVE the 1.6569 that the comment above calls the lowest wrong result
#       on record. The same body reads 1.6935 at t = 1.5 and 1.4709 at t = 1.
#   60 x 60 x 40, 49 holes of r 0.5 at 8 mm pitch (3 mm webs), t = 2:
#       64,200.679 against a closed-form 64,200.679, and it reads 1.4030.
#
# So a ceiling of 1.35 refuses a shell the kernel builds perfectly, and there
# is no number that both allows 1.8229 and refuses 1.6569. The ratio is kept —
# it is the cheap first question and every wrong result on record clears it —
# but a refusal now needs a SECOND, independent answer as well.
_SHELL_SKIN_FACTOR = 1.35

# That second question is the one the direction corpus of this range already
# wrote down and did not act on: the walls over the MEAN of the two surfaces
# they lie between, `out.area / 2 * t`. That is the coarea formula, so it is
# pinned near 1.0 by geometry rather than by calibration — the trapezoid is
# exact when the offset surface's area moves linearly with depth, and a hole,
# whose area does move linearly, is exactly the feature that sends the other
# ratio up. Measured on every result on record (probes/shell_skin_thick_plate_-
# probe.py, probes/shell_skin_direction_corpus.py):
#
#   SOUND, and reaching the first gate: 1.0054 / 1.0059 / 1.0114 / 1.0116 /
#       1.0155 / 1.0190 / 1.0283 — the drilled plates above, whose `area * t`
#       ratios run 1.21 to 1.82.
#   SOUND, everything else: 0.96 to 1.0018 over the gauntlet corpus at nine
#       thicknesses in BOTH directions, and one outlier at 1.3725 (the oneplus
#       case at t = 0.5, where the walls nearly meet and the inner surface
#       collapses) — which never reaches this question, its first ratio being
#       1.0559.
#   WRONG: 1.9183 and 5.4354 (the user's own designs), 2.7116 and 3.3129 (the
#       100-hole plate at t = 1.0 and 1.3, the two this range was built on),
#       4.1249 (the 49-hole plate at t = 3, where the kernel hands the body
#       back).
#
# 1.5 sits 1.46x above the highest SOUND result that can reach it and 1.28x
# below the lowest WRONG one — and because the gate is an AND, this can only
# ever ALLOW more than the ratio alone did: no shell that builds today is
# refused by adding it.
#
# 2026-09-18, round two of that review: the last sentence of the paragraph
# above is the one to keep and the one before it is not. The lowest WRONG
# reading on record is **1.4351**, not 2.7116 — the same 100-hole plate at
# t = 3.0, where the kernel hands back all but 0.96 mm3 of a 77.4 mm3 cavity
# (probes/shell_coarea_merge_probe.py, against a Monte Carlo oracle over the
# analytic distance to a drilled box). That is UNDER this bound and ABOVE the
# 1.3725 the sound population reaches, so these two populations overlap
# exactly as the `area * t` ones do and no constant on either normaliser can
# separate them. The number is left where it is — moving it to 1.43 would
# refuse a sound 1.3725 with no margin at all, and as the second half of an
# AND it can only ever allow — and the result that neither ratio can see is
# refused by `assert_the_deepest_point_was_hollowed` instead, which asks about
# the body in hand rather than about a population.
_SHELL_COAREA_FACTOR = 1.5


def assert_walls_could_be_a_skin(solid, out, t: float, direction: str, walls: str) -> None:
    """An inward shell's walls lie within `t` of the surface they came from, so
    their volume is about `area * t` — never a multiple of it. A result that
    measures more than that is the BODY, handed back as a hollow.

    The P0 this closes (my-part-5 seed 18800, 2026-09-14, found beside the
    segfault the folder was filed for): a CLOSED 3 mm shell of a 413262.875 mm3
    mirrored body returned 413260.165 mm3 — 2.709 mm3 removed, 0.00066 per cent
    — valid, watertight, health empty, green in the tree and saved. Every check
    that existed passed, because all of them ask about IDENTITY: "nothing was
    hollowed" is `abs(v_out - v_in) <= 1e-6`, and 2.709 clears 1e-6 by seven
    orders of magnitude. Identity is the wrong question; "is this plausibly a
    wall" is the right one.

    Why a VOLUME FRACTION cannot do this job, measured the same day: a 12 mm
    plate shelled at 5.9 mm leaves 521 mm3 of cavity and walls that are 98.91
    per cent of the body — CORRECT, and closer to a block than anything else in
    the corpus. Dividing by `area * t` normalises that away: the same plate
    reads 0.72 while the wrong result reads 2.72.

    TWO questions, both of which must say "this is the body" before a refusal
    stands, and the corpora behind both numbers are above `_SHELL_SKIN_FACTOR`
    and `_SHELL_COAREA_FACTOR`. Neither is a theorem: a body whose surface is
    mostly CONCAVE detail has inner parallel surfaces larger than its outer
    one, which is why the first ratio alone cannot decide — measured, a
    perfectly correct shell of a deeply drilled plate reaches 1.8229 of
    `area * t`, past the lowest WRONG result on record, while its walls over
    the mean of the two surfaces read 1.0155 where the wrong results this pair
    was built on read 1.9183 or more.

    Neither question is a fence, and since round two of this review neither is
    the last word: a wrong result can read UNDER both (0.7180 and 1.4351 on
    the 100-hole plate at t = 3.0 — see `_SHELL_COAREA_FACTOR` and
    `assert_the_deepest_point_was_hollowed`, which is the check that catches
    it). These two stay because they are cheap and they own the cases they
    were measured on.

    OUTSIDE shells are not judged here, and since 2026-09-17 that is a
    measurement and not an omission. The same corpus at the same nine
    thicknesses, run outward (probes/shell_skin_direction_corpus.py): every
    sound result runs 1.0023 to 1.5233, rising with `t` and with nothing else —
    the l-bracket 1.4894 at t = 8, the dprism boss 1.4573, the cylinder 1.3840,
    the plate with a hole 1.5233. That is Steiner's formula, not a kernel
    fault: growing a body by `t` adds `A*t + M*t^2 + (4/3)*pi*t^3`, so the
    ratio starts at 1 and rises without any bound the body's own area knows
    about (a ball of radius 10 grown by 8 mm is 2.01 of its skin and exactly
    right). No constant can mean the same thing outward, so none is invented;
    an outside shell keeps every other check and not this one.

    That outward run also wrote down the second question this now asks — the
    walls over the MEAN of the two surfaces they lie between — as something
    worth passing on rather than acting on. It is acted on now, INWARD only and
    only as the second half of an AND, so it can allow and never refuse; the
    numbers are above `_SHELL_COAREA_FACTOR`. Outward it still decides nothing,
    for the reason in the paragraph above."""
    if direction != "inside":
        return
    import inspector                                 # local: avoids an import cycle
    area = inspector._try(lambda: float(solid.area))
    v_out = inspector._try(lambda: float(out.volume))
    if not area or area <= 0 or v_out is None:
        return                                       # nothing to judge against
    skin = area * t
    if v_out <= _SHELL_SKIN_FACTOR * skin:
        return
    # the second question: are these walls also too heavy for the two surfaces
    # they actually lie between? A drilled plate says no — that is the whole
    # point of asking twice — and a body handed back as its own hollow has no
    # inner surface at all, so it says yes twice as loudly
    mean = inspector._try(lambda: float(out.area))
    if mean and v_out <= _SHELL_COAREA_FACTOR * (mean / 2.0) * t:
        return
    raise ValueError(
        f"shell: {walls} came back as the body itself, not as walls — the kernel "
        f"returned {v_out:,.6g} mm3 of walls where a {t:g} mm skin over this surface "
        f"holds about {skin:,.6g} mm3, so almost nothing was hollowed. Try a "
        f"different thickness, or open a face")


def assert_wall_fits_every_lump(solid, t: float, walls: str) -> None:
    """A CLOSED, inward hollow whose wall is at least HALF a lump's smallest
    extent can leave nothing hollow — and asking the kernel anyway SEGFAULTS it.

    Measured 2026-09-12 (bugs/20260912-175819-isogrid-panel-s9016-crash,
    probes/shell_scaled_halfball_crash.py): a ball clipped by a box to
    2.56 x 4.8 x 5.12 mm, shelled closed at t = 1.8, took the server down with
    0xC0000005 inside `offset()`; so did t = 2 and t = 3, and the same shape
    ten times bigger at t = 18. Below half the smallest extent (t = 1, 0.5)
    the kernel refuses with an exception the sentence below already
    translates. No `except` can catch an access violation, so the only guard
    is one that runs BEFORE the kernel — and this one is not a judgement
    call: every point of a lump lies within half its smallest bounding-box
    extent of the boundary, so an inward offset by that much or more is
    empty. Per lump, because a big lump's hollow would otherwise pay for the
    small one's (see `assert_every_lump_hollowed`), and the crash is the
    small lump's alone.

    The same bound also refuses a silent WRONG result the kernel called a
    success (probed the same day): a ball of radius 3.2 at t = 5 came back
    "hollowed" (137 -> 113 mm3) because the offset sphere INVERTED to a
    radius-1.8 cavity that no 5 mm wall could ever leave."""
    tight = []
    for lump in solid.solids():
        size = lump.bounding_box().size
        dmin = min(size.X, size.Y, size.Z)
        if 2.0 * t >= dmin - _SHELL_BOX_TOL_MM:
            tight.append(dmin)
    if not tight:
        return
    dmin = min(tight)
    n = len(solid.solids())
    where = ("this body" if n == 1 else
             f"{len(tight)} of the {n} separate lumps of this body")
    raise ValueError(
        f"shell: {walls} meet in the middle of {where} — it is only {dmin:.4g} mm "
        f"at its thinnest, so a closed hollow needs walls under {dmin / 2:.4g} mm; "
        f"use a thinner wall or open a face")


# Sampling for `deepest_material`: rays per face, the face-evaluation budget
# that lowers that count on a body with hundreds of faces (the intersector
# tests a ray against every face's box, so cost is rays x faces), where along
# each chord the interior is probed, and the extra stations towards an OPENING
# (the deepest material sits ON the face that goes, not in the middle).
_DEPTH_RAYS_PER_FACE = 12
_DEPTH_RAY_BUDGET = 200_000
_DEPTH_STATIONS = (0.5, 0.25, 0.75)
_DEPTH_STATIONS_TO_OPENING = (1.0, 0.9)
# ... and the climb that turns the best SAMPLE into the real maximum before a
# refusal is allowed to stand: how many of the measured points EACH of the three
# rankings in `_seeds_for_the_climb` walks uphill, and how many steps each gets.
_DEPTH_CLIMB_SEEDS = 3
_DEPTH_CLIMB_STEPS = 40
# ... and the whole climb's budget in distance measurements, shared by every
# seed, because nine seeds of forty steps could in theory spend 369 and a
# measurement costs about 0.12 s on a 330-face body.
#
# It was `_DEPTH_CLIMB_SEEDS * _DEPTH_CLIMB_STEPS` — 120, "no more than the
# three seeds it used to take" — and 2026-09-17's review measured that number
# STARVING the two rankings the same commit added. The three DEEPEST seeds are
# spent first and can take 41 each, so on a body whose deep seeds run their
# full forty steps there is nothing left for the rankings added beside them,
# and the seeding is the old one wearing a new coat. Measured
# (probes/shell_depth_seed_starvation_probe.py): the slab with a fat post —
# the body the THIRD ranking exists for, and whose 17.0000 -> 17.2160 the
# docstring below records — answers 17.0000 at a budget of 120 and 17.2160 as
# soon as the budget lets the seeds run; the wedge in the slab answers 12.4156
# against 12.4444. Re-ordering does not help: spending the budget round-robin
# across the three rankings instead of deepest-first answers IDENTICALLY on all
# 17 bodies (probes/shell_depth_seed_order_probe.py), because the answer sits
# on a seed that the first three exhaust the budget before reaching, whichever
# three they are.
#
# So the budget is set from what the climb actually SPENDS when nothing stops
# it, not from what nine seeds could spend in theory. Measured over the four
# plateau bodies, the gauntlet corpus, the four committed crash fixtures and
# drilled plates of 6x6, 12x12 and 18x18 holes (up to 330 faces), the unstopped
# spend is 3 to 172 and never once approaches 369 — seeds terminate early
# because the step halves out. 200 covers every one of them with margin, and
# measured on the 330-face body it costs nothing at all: its climb stops itself
# at 106 either way.
#
# 2026-09-18, round two: the ridge step in `_climb_to_the_deepest` spends more
# — a seed that used to die on the medial axis now walks along it — so the
# unstopped spend is 166 to 516 and 200 really is BINDING. It is kept, because
# what it binds is the spending and not the ANSWER: measured at 200 against
# 10,000 (probes/shell_depth_budget_headroom_probe.py), all four plateau bodies
# and a 19 x 19 drilled plate of 367 faces — more faces than anything this has
# ever been run on — answer to the last digit either way (12.4499, 15.4997,
# 12.7125, 17.2242, 5.0639), while the unstopped runs want 189, 516, 440, 166
# and 291.
#
# And when a budget is not enough, the answer moves DOWN, which is the safe
# direction: the same 367-face plate reads 5.0639 at 200, 4.4594 at 120, 4.4570
# at 30 and 4.2501 at 0 — never deeper, because out of budget `spend` answers
# exactly as "nothing could be measured" does and every depth this keeps came
# back from the same exact BRepExtrema. A lower reading refuses walls the
# kernel might have built; a deeper one would hand a body the wall does not fit
# to a kernel that segfaults on it. That ladder is also why 120 was not enough:
# on a body nobody had built, it was 0.6 mm short.
_DEPTH_CLIMB_CALLS = 200


def _barycentres(k: int) -> tuple:
    """`k` points spread INSIDE a triangle, as barycentric weights.

    The centroid comes first, so asking for one point is exactly what
    `deepest_material` did before this existed; the rest are the interior of
    the order-`d` lattice, `d` raised until there are enough of them. Points of
    a tessellation triangle lie on the face, so this needs no `is_inside` test
    and no surface evaluation — it is arithmetic on three vertices."""
    if k <= 1:
        return ((1 / 3, 1 / 3, 1 / 3),)
    d = 4
    while (d - 1) * (d - 2) // 2 < k - 1:
        d += 1
    pts = [(1 / 3, 1 / 3, 1 / 3)]
    pts += [(i / d, j / d, (d - i - j) / d)
            for i in range(1, d) for j in range(1, d - i)]
    return tuple(pts[:k])


def deepest_material(solid, t: float, openings=()) -> tuple | None:
    """Is there ANY material at least `t` from every face that stays?

    An inward shell keeps the material within `t` of the faces that stay and
    removes the rest, so it hollows something exactly when some interior
    point is `t` or more from all of them — the OPENING faces do not count,
    their material is what the cavity replaces. Interior points are found by
    rays: from sample points on every staying face along the inward normal to
    the first face the ray meets, then stations along that chord, and each
    station's distance to the staying faces is measured exactly. Stops at the
    first point that is deep enough (one is all a cavity needs), so a thick
    body answers in one measurement; a body that is thin everywhere measures
    every station and comes back with the deepest it found — and only after
    `_climb_to_the_deepest` has walked that one uphill, because a station is
    where a ray happened to land and not where the material is thickest.

    Returns (depth, point, slack): depth >= t - slack means a cavity fits.
    None when nothing could be measured (no faces, no face STAYS, no ray
    landed) — then this guard has no question to ask and the kernel speaks.

    Measured 2026-09-16 (probes/shell_thin_wall_probe.py, probes/
    shell_thin_wall_corpus.py): on the 1.3 mm-walled open box of the my-part
    finding every station sits 0.65 mm from a wall, and the kernel's crash
    boundary was exactly there (0.64 built, 0.66 segfaulted). The first draft
    of this guard asked the OPPOSITE question — is there any wall the offset
    does not fit? — and refused 11 shells the kernel built SOUND (a 4 mm rib,
    a 4 mm pin, a 4 mm web between pockets, all left solid inside a hollowed
    plate): a thin PART of a body is the kernel's to fill; a body that is thin
    EVERYWHERE is the one that dies. The sample point is a triangle centroid,
    which sits up to the tessellation tolerance on the AIR side of a curved
    face, so the ray starts two tolerances in, or it re-crosses its own face
    at 0.003 mm."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.TopAbs import TopAbs_State
    from OCP.TopoDS import TopoDS_Compound
    from build123d import Vector
    faces = solid.faces()
    n = len(faces)
    if n == 0:
        return None
    tol = max(1e-3, 1e-4 * float(solid.bounding_box().diagonal))
    per_face = max(1, min(_DEPTH_RAYS_PER_FACE, _DEPTH_RAY_BUDGET // (n * n)))

    def stays(topo_face) -> bool:
        return not any(topo_face.IsSame(o.wrapped) for o in openings)

    staying = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(staying)
    kept = 0
    for face in faces:
        if stays(face.wrapped):
            builder.Add(staying, face.wrapped)
            kept += 1
    if not kept:
        # every face opened (six clicks on a box): there is no surface for a
        # wall to lie within, so this guard has no question to ask and the
        # distance to an EMPTY compound is no answer — it measured nothing and
        # the sentence came out "no point of it is more than 0 mm from the
        # faces that stay, so walls must be under 0 mm". The kernel's own
        # refusal is the honest one, as it was before this guard existed.
        return None
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(solid.wrapped, 1e-6)
    stations = []                         # (upper bound on depth, point)

    def samples(face):
        """spread points over the face's triangles, plus the face's own centre
        when it lies on the face — a rectangle's centroids never reach its
        middle (two triangles, centroids a third of the way in), and the middle
        is where the deepest material under an opening sits (the plain 50 mm box
        read 16.67 without it, 25 with).

        A FLAT face tessellates into one to six triangles however big it is, so
        one centroid each spent 33 of a 108-point budget on the wedge-in-a-slab
        of the 2026-09-16 review and put no ray within 40 mm of the taper's
        thick end. Each picked triangle is filled to the budget instead — the
        centroid first, so a body that already had enough triangles is sampled
        exactly as before, and a body with hundreds of faces has `per_face` 1
        and is untouched."""
        verts, tris = face.tessellate(tol)
        m = len(tris)
        picks = list(range(m)) if m <= per_face else [(k * m) // per_face
                                                     for k in range(per_face)]
        pts = []
        for k in picks:
            a, b, c = (verts[i] for i in tris[k])
            for wa, wb, wc in _barycentres(max(1, per_face // max(1, len(picks)))):
                pts.append(a * wa + b * wb + c * wc)
        centre = face.center()
        if face.is_inside(centre):
            pts.append(centre)
        return pts

    for face in faces:
        if not stays(face.wrapped):
            # the material AT an opening counts to the faces that stay; its
            # centre is the deepest such point on a convex opening. Its INWARD
            # direction travels with it: the point itself lies ON the surface,
            # where the solid classifier answers ON and not IN, and
            # `assert_the_deepest_point_was_hollowed` can then say nothing
            # about it — see the nudge at the end of this function.
            inward = -face.normal_at(face.center())
            for q in samples(face):
                stations.append((float("inf"), q, inward))
            continue
        for p in samples(face):
            nrm = face.normal_at(p)
            inter.Perform(gp_Lin(gp_Pnt(*(p - nrm * (2 * tol))), gp_Dir(*(-nrm))), 0.0, 1e9)
            if not inter.IsDone() or inter.NbPnt() == 0:
                continue
            hit = min(range(1, inter.NbPnt() + 1), key=inter.WParameter)
            chord = inter.WParameter(hit) + 2 * tol
            far_stays = stays(inter.Face(hit))
            for f in _DEPTH_STATIONS + (() if far_stays else _DEPTH_STATIONS_TO_OPENING):
                bound = min(f, 1 - f) * chord if far_stays else f * chord
                # at f = 1 the station sits exactly ON the opening the ray
                # ended at, where the classifier answers ON and the theorem
                # after the kernel is mute; the way back into the material is
                # +nrm, the way the ray came
                back = nrm if not far_stays and f >= 1.0 else None
                stations.append((bound, p - nrm * (f * chord), back))
    if not stations:
        return None
    stations.sort(key=lambda st: -st[0])
    ext = BRepExtrema_DistShapeShape()
    ext.LoadS1(staying)
    try:
        cls = BRepClass3d_SolidClassifier(solid.wrapped)
    except Exception:                     # OCP errors derive from Exception
        cls = None                        # cannot ask: every station is believed,
        # exactly as before this existed

    def in_material(q) -> bool:
        """Is this station MATERIAL? A station is arithmetic on a face normal
        and a chord, and neither means anything on a DEGENERATE face: the
        committed `sliver_intersect_plate` fixture carries a face of
        4.725e-08 mm2 whose normal points along the plate, so the ray ran
        68.8 mm through AIR and the station at half of it measured 24.3295 mm
        from a body whose bounding box is 1.9296 mm thick — 25x the most that
        body can possibly hold (probes/shell_r3_over_read_probe.py, the 2026-
        09-19 review). A guard whose job is REFUSING must never read deeper
        than the truth; that reading switched this guard off at every
        thickness, and the open shell it then let through hung the kernel for
        more than 600 s (probes/shell_r3_sliver_open_probe.py).

        `_climb_to_the_deepest` has always classified every candidate it
        takes, which is why the climb could not do this and the sampling
        could. Asked ONLY of a station that is about to change the answer —
        become the best, or end the loop — because a classification costs
        0.33x to 1.04x of a distance measurement and the refusal path measures
        every station (probes/shell_r3_station_classify_cost.py); the answer
        changes a handful of times, so this is a handful of calls.

        Fails OPEN like every other branch of this guard: a classifier that
        will not run believes the station, which is what happened before this
        existed."""
        if cls is None:
            return True
        try:
            cls.Perform(gp_Pnt(q.X, q.Y, q.Z), 1e-7)
            return cls.State() != TopAbs_State.TopAbs_OUT
        except Exception:                 # OCP errors derive from Exception
            return True

    def measure(q):
        """distance from `q` to the faces that stay, and the nearest point on
        them — which is the direction an inscribed sphere grows AWAY from"""
        ext.LoadS2(BRepBuilderAPI_MakeVertex(gp_Pnt(q.X, q.Y, q.Z)).Vertex())
        ext.Perform()
        if not ext.IsDone() or ext.NbSolution() < 1:
            return None, None
        near = ext.PointOnShape1(1)
        return float(ext.Value()), Vector(near.X(), near.Y(), near.Z())

    best = (0.0, stations[0][1])
    best_in = None                        # the winner's way INTO the material
    seen = []                             # every station actually measured
    for bound, q, inward in stations:
        if bound < t - tol and bound <= best[0]:
            break                         # nothing left can be deep enough, or deeper
        d, _near = measure(q)
        if d is None:
            continue
        if (d > best[0] or d >= t - tol) and not in_material(q):
            continue                      # a station in the AIR measures nothing
        seen.append((d, q, bound))        # the bound travels: the climb ranks on it
        if d > best[0]:
            best, best_in = (d, q), inward
        if d >= t - tol:
            break                         # one deep point is all a cavity needs
    if best[0] < t - tol:
        climbed = _climb_to_the_deepest(solid, measure, seen, best, tol)
        if climbed[0] > best[0]:
            best, best_in = climbed, None
    if best_in is not None:
        # The winner is a sample of an OPENING face, so it lies ON the body and
        # `assert_the_deepest_point_was_hollowed` returns without judging
        # anything — measured over the corpus, that is 104 of the 109 open
        # cells that reach it, against 0 of 125 closed ones
        # (probes/shell_r3_inert_census.py, 2026-09-19). The material just
        # inside the opening makes the same statement from a point the
        # classifier calls IN, and distance is 1-Lipschitz so it moves by at
        # most the nudge. It is MEASURED rather than assumed, and taken only
        # when it leaves this function's own verdict unchanged, so no shell
        # that builds today is refused for it.
        q = best[1] + best_in * (2 * tol)
        d, _near = measure(q)
        if d is not None and d >= t - tol and in_material(q):
            best = (d, q)
    return best[0], (best[1].X, best[1].Y, best[1].Z), tol


def _spread_out(ranked: list, tol: float, k: int) -> list:
    """The first `k` of an already-ranked list, each further than its own radius
    from the ones taken.

    The top three of any ranking are usually three stations on ONE ray, which
    climb the same hill three times; a seed that must clear its own radius
    lands on another branch of the medial axis instead."""
    seeds, taken = [], []
    for _score, d0, q0 in ranked:
        if len(seeds) >= k:
            break
        if all((q0 - p).length > max(d0, tol) for p in taken):
            seeds.append((d0, q0))
            taken.append(q0)
    return seeds


def _seeds_for_the_climb(seen: list, deepest: float, tol: float) -> list:
    """Which measured stations are worth walking uphill — three questions, three
    seeds each.

    Ranking them by DEPTH alone is what a PLATEAU exploits, and that was the
    other half of the 2026-09-16 finding (LAUNCH-PLAN section 10). A uniform
    region measures exactly what its chord allows, so an 80 x 80 x 24 slab's
    mid-plane reads 12.0000 at a dozen points more than 12 mm apart and takes
    every seed, while the 2-to-30 mm draft wedge fused into it — whose real
    maximum is 12.4300 — never gets one. Raising the seed count does not help
    (the plateau has dozens more), and neither do more steps (a plateau has no
    gradient). Measured on the repro (probes/shell_depth_plateau_seeds_probe.py):
    climbing ALL 177 stations does find 12.4464, and the station it finds it
    from is ranked #159 of 177 BY DEPTH. It started 2.4271 mm from a face.

    What that station has is ROOM: its own ray passed through 40 mm of material
    while the station itself measured 2.43, so `bound / depth` is 8.2 where
    every plateau station scores exactly 1.0 — the lowest score there is, since
    a station can never measure more than its own chord allows. That ranking
    puts it #31, and its top three find the wedge.

    So three rankings, because one is not enough for both shapes of plateau:

      * the DEEPEST stations — today's rule, and the right one whenever the
        thickest material happens to sit on a ray (a box, a plate, a cylinder);
      * the stations with the most ROOM, wherever they are — the wedge fused
        into a slab, where the answer sits beside a face and not near one;
      * the deepest stations that ALSO have room — a slab carrying a fat post,
        where the winner is on the plateau itself (depth 10.0 of a 17.0 best,
        ranked #13 by depth and #132 by room) and climbs up into the post.

    Measured over the four bodies, against a grid oracle: the wedge in a slab
    12.0000 -> 12.4444 (oracle 12.4300), the slab with a post 17.0000 ->
    17.2160 (17.2047), the 180 mm draft prism unchanged at 15.3405, the ramped
    plate unchanged at 12.2987 — that last one is the climb's own limit and not
    the seeding's: climbing all 160 of its stations reaches 12.2987 too. Those
    numbers are what the code answered until 2026-09-18; they were first
    written down from a run with no budget on the climb, and until
    2026-09-17's review the budget of 120 meant the shipped code answered
    12.4156 and 17.0000 instead (see `_DEPTH_CLIMB_CALLS`).

    The ramped plate was the one live cost of that residual — the kernel builds
    walls of 12.36 to 12.62 mm on it SOUND while this guard refused all of them
    — and it was NOT a seeding fault, exactly as this paragraph said: the climb
    stalled where the inscribed sphere touches on two sides at once. Round two
    of the review closed it in the climb itself, so the shipped answers are now
    12.4499, 17.2242, 15.4997 and 12.7125 (the ramped plate's exact inscribed
    radius is 12.713 by hand) — see `_climb_to_the_deepest`."""
    deep, room = [], []
    for d0, q0, bound in seen:
        deep.append((d0, d0, q0))
        # an opening sample has no chord to bound it, and a station that is
        # already ON a face has nothing but room — it would crawl through the
        # whole budget a fraction of a millimetre at a time
        if bound != float("inf") and d0 >= 0.1 * deepest:
            room.append((bound / max(d0, 1e-9), d0, q0))
    both = [r for r in room if r[1] >= 0.5 * deepest]
    picked = [_spread_out(sorted(r, key=lambda x: -x[0]), tol, _DEPTH_CLIMB_SEEDS)
              for r in (deep, room, both)]
    # the deepest first, so a body the old rule already answered is answered the
    # same way and the budget below only ever pays for what is left over
    order = picked[0] + [s for pair in zip(picked[1], picked[2]) for s in pair] \
        + picked[1][len(picked[2]):] + picked[2][len(picked[1]):]
    seeds, at = [], []
    for d0, q0 in order:
        if all((q0 - p).length > tol for p in at):
            seeds.append((d0, q0))
            at.append(q0)
    return seeds


def _climb_to_the_deepest(solid, measure, seen: list, best: tuple, tol: float) -> tuple:
    """Walk the best sampled points UPHILL, and only then let a refusal stand.

    `deepest_material`'s stations lie on rays through face sample points, so
    they find the true deepest material only when it happens to sit on one —
    which symmetry arranges for a box, a plate or a cylinder and nothing
    arranges for a taper. Measured 2026-09-16 (this review,
    probes/shell_depth_oracle_probe.py, against a grid over the whole
    interior): a plain draft wedge (2 mm at one end, 30 at the other, 40 deep)
    has material 12.42 mm from every face, and the stations reach 10.62 — so a
    closed shell at 11, 11.5 and 12 mm was refused BEFORE the kernel, in a
    sentence that told the user "walls must be under 10.62 mm", while the
    kernel builds all three sound (314, 127 and 27 mm3 of cavity). An L-plate
    with the top open read 24.5 against 29.25 the same way.

    The deepest material is the centre of the largest sphere that fits, and
    from any interior point that sphere grows AWAY from the face nearest it —
    so each seed is stepped along that direction while the distance keeps
    rising, the step halving whenever it does not, and a candidate outside the
    body is never taken. Several seeds because the field has one maximum per
    medial branch and the best sample need not sit on the right one —
    `_seeds_for_the_climb` says which, and why depth alone is not the question.

    "Away from the face nearest it" is the gradient of this field wherever the
    field is smooth, and it stops being smooth on the MEDIAL AXIS, where the
    sphere touches on two sides at once: the step then walks into the second
    wall, the distance does not rise, the step halves and the seed dies on the
    ridge instead of walking along it. That was the residual the 2026-09-16
    review declared and the 2026-09-17 one measured but did not close — the
    ramped plate, where the guard answered 12.2987 and refused walls of 12.36,
    12.43, 12.49, 12.56 and 12.62 mm that the kernel builds SOUND. Round two
    closes it with the bisector step in the loop below, for no new machinery
    and no new constant: the largest circle of that plate's section touches
    three edges at a radius of 12.713 by hand, and the climb now answers
    12.7125 (probes/shell_depth_ridge_climb_probe.py). The prism reads 15.4997
    where it read 15.3405, the wedge in the slab 12.4499 where it read 12.4444.

    A climb that reads DEEPER allows more, so every wall it newly allows was
    put to the kernel (probes/shell_depth_ridge_allowed_probe.py) over the four
    plateau bodies, the gauntlet corpus and the four committed crash fixtures:
    **12 newly allowed walls BUILD and are sound** — the ramped plate's own
    band at cavities of 33.934, 14.982 and 3.733 mm3 — **16 the kernel refuses
    with a sentence, and nothing crashed or came back unsound.** The crash
    fixtures do not move at all: the oneplus case, the impeller, the sliver
    plate, my-part-5's mirror body and the clipped ball answer exactly what
    they answered before, so a body that segfaults OCCT gains no new door.

    This can only ever RAISE the answer — it accepts a point only when that
    point measures deeper, by the same exact `BRepExtrema` the stations use —
    so it can turn a refusal into a build and can never invent one. That is
    why it is safe to add underneath a guard whose whole job is refusing: the
    thin-everywhere bodies it exists to catch really are thin everywhere (the
    1.3 mm-walled box's true maximum IS 0.65 mm), and nothing it does lets one
    of them through. It runs ONLY when the guard is about to refuse, so the
    ordinary path — one station deep enough, done — pays nothing for it."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(solid.wrapped)

    def outside(q) -> bool:
        cls.Perform(gp_Pnt(q.X, q.Y, q.Z), 1e-7)
        return cls.State() == TopAbs_State.TopAbs_OUT

    left = [_DEPTH_CLIMB_CALLS]

    def spend(q):
        """`measure`, against the climb's shared budget. Out of budget reads the
        same as "nothing could be measured", which already ends a climb."""
        if left[0] <= 0:
            return None, None
        left[0] -= 1
        return measure(q)

    seeds = _seeds_for_the_climb(seen, best[0], tol) or [best]
    for d0, q0 in seeds:
        if left[0] <= 0:
            break
        # `deepest_material` classifies a station only when it would change the
        # answer, so a station in the AIR can still reach this list — and a
        # seed that never improves is handed back as `best` at the end of this
        # loop, which would make the climb a second door to the same over-read
        if outside(q0):
            continue
        q, d = q0, d0
        step, near = max(d0, tol), None
        for _ in range(_DEPTH_CLIMB_STEPS):
            if left[0] <= 0:
                break                     # the budget, not the step count
            if near is None:
                got = spend(q)
                if got[0] is None:
                    break                 # keep the seed's own depth, not None
                d, near = got
            away = q - near
            reach = away.length
            if reach <= 1e-9:
                break                     # the point is ON a face: no way uphill
            cand = q + away * (step / reach)
            got = (None, None) if outside(cand) else spend(cand)
            if got[0] is not None and got[0] > d:
                q, d, near = cand, got[0], got[1]
                continue
            # The step failed, which on this field usually means the inscribed
            # sphere has reached a RIDGE and touches on two sides at once:
            # walking away from one wall walks into the other. The way on is
            # the bisector of the two, and both directions are already in hand
            # — the failed candidate was measured, so its own nearest point
            # came back with it. `u1 + u2` rises against BOTH walls to first
            # order, since (u1+u2).u1 = 1 + u1.u2 > 0 unless they are exactly
            # opposite, which is a slab and has no ridge to walk.
            took = False
            if got[1] is not None:
                u1 = away * (1.0 / reach)
                away2 = cand - got[1]
                if away2.length > 1e-9:
                    u2 = away2 * (1.0 / away2.length)
                    ridge = u1 + u2
                    # the same wall again would just repeat the step that failed
                    if u1.dot(u2) < 0.99 and ridge.length > 1e-6:
                        alt = q + ridge * (step / ridge.length)
                        alt_got = (None, None) if outside(alt) else spend(alt)
                        if alt_got[0] is not None and alt_got[0] > d:
                            q, d, near = alt, alt_got[0], alt_got[1]
                            took = True
            if not took:
                step *= 0.5
                if step <= tol * 0.25:
                    break                 # the sphere touches on every side
        if d > best[0]:
            best = (d, q)
    return best


def assert_something_would_be_hollowed(solid, t: float, openings: list,
                                       walls: str) -> tuple | None:
    """An inward shell of a body that is thin EVERYWHERE — relative to the wall
    asked for — has nothing to hollow, and asking the kernel anyway CRASHES it.

    The overnight finding of 2026-09-15 (bugs/20260915-210615-my-part-s95959-
    step18): a SECOND shell, 1.1 mm with the top open, on a body that already
    had 1.3 mm walls segfaulted OCCT (0xC0000005 inside offset()). The
    bounding-box bound of `assert_wall_fits_every_lump` never sees it — that
    body is 12.7 mm at its smallest extent and the hollow is OPEN anyway. This
    is the same certainty read from the inside: a point of material survives
    as wall when it is within `t` of a face that stays, so when no point is
    `t` or more from all of them the cavity is empty — and that is decided
    before the kernel, in a sentence that names how thick the body is.

    Refused only when SURE: `deepest_material` measures exact distances but
    from SAMPLED points, so one deep point allows the shell (the kernel and the
    checks after it judge the result, as before) and only a body with no deep
    point among them is refused. Measured 2026-09-16 over the gauntlet corpus,
    the four committed crash bodies and both finding bodies at seven
    thicknesses, closed and open: zero refusals of a shell the kernel built
    sound (probes/shell_thin_wall_corpus.py).

    Returns the `(depth, point, tol)` it allowed on, because that point is also
    a statement about the RESULT — see `assert_the_deepest_point_was_hollowed`,
    which is the whole reason this measurement is no longer thrown away. None
    when there was nothing to measure."""
    found = deepest_material(solid, t, openings)
    if found is None:
        return None
    depth, at, tol = found
    if depth >= t - tol:
        return found
    raise ValueError(
        f"shell: nothing would be hollowed — {walls} meet in the middle of this body "
        f"everywhere: no point of it is more than {depth:.4g} mm from the faces that "
        f"stay (near x {at[0]:.3g}, y {at[1]:.3g}, z {at[2]:.3g}), so walls must be "
        f"under {depth:.4g} mm; use a thinner wall or open a face")


def assert_the_deepest_point_was_hollowed(solid, out, deep, t: float, walls: str) -> None:
    """The point the guard ALREADY measured, put to the result the kernel
    returned. This is a theorem about this one body, not a constant calibrated
    on a corpus of other people's bodies.

    An inward shell keeps exactly the material within `t` of the faces that
    stay, so a point measured `d` mm from ALL of them, with `d > t`, lies
    `d - t` mm inside the cavity and cannot be in the walls. Before the kernel,
    `assert_something_would_be_hollowed` already finds such a point and its
    exact `BRepExtrema` distance and then throws both away; keeping them costs
    one solid classification and answers the one question the two ratios above
    cannot, because it asks about THIS body instead of about a population.

    The P0 it closes (round two of this review, 2026-09-18,
    probes/shell_coarea_merge_probe.py, probes/shell_deep_point_survives_probe.py):
    a ratio of `walls / (area * t)` is the body's own `volume / (area * t)`
    when the kernel hands the body back, so the 1.35 ceiling only ever catches
    a handback while `t < volume / (1.35 * area)` — every wrong result the
    ceiling was calibrated on was measured at t <= 1.3 on bodies whose
    volume/area is about 2.2. Walk the SAME plate past that thickness and the
    same handback goes silent. Measured on the very plate the ceiling was
    calibrated on, a 60 x 60 x 10 with 100 holes of r 1.0 at 6 mm pitch:

        t = 1.3   32,858.3 of a true 20,400.6 +/- 12.1 — reads 1.6569, REFUSED
        t = 2.5   32,846.4 of a true 31,886.6 +/-  4.1 — reads 0.8613, and the
                  coarea question is never even asked. 959.8 mm3 of "walls"
                  that are not there: the user asked for a 2.5 mm shell and got
                  a body with a 12.0 mm3 hole in it where 971.8 mm3 had to go,
                  valid, watertight, health clean, green in the tree
        t = 3.0   32,857.4 of a true 32,781.0 +/- 1.2 — reads 0.7180, and the
                  coarea reads 1.4351, UNDER its own bound: neither ratio can
                  see it. 0.96 mm3 of cavity where 77.4 mm3 had to go

    Both of those are caught here, from the point the guard had already paid
    for: depth 3.2426 at (0, -18, -1), IN the walls both times. The oracle is
    Monte Carlo against the ANALYTIC distance to a drilled box's boundary — no
    OpenCASCADE, no closed form — and the t = 1.6 shell of the same plate is
    SOUND (24,362.5 against 24,357.5 +/- 10.8) with that same point OUT of the
    walls, so this does not fire on a correct result.

    IN the walls is not on its own the verdict, and the corpus is what says so
    (probes/shell_deep_point_corpus.py, 2026-09-18). A kernel that drops a thin
    SLIVER of cavity — which is what it does where the walls nearly meet —
    leaves the point just inside a surface it really did build, and the oneplus
    case at t = 0.5 is exactly that: a point 0.1 mm past a 0.5 mm wall,
    classified IN, on a result that still hollowed 30.7 per cent of the body.
    Calibrating a margin between that 0.1 mm and the 0.2426 mm of a wrong
    result would be the same mistake this function exists to stop making, and
    so would a bound on how far the point sits from the RESULT's own surface
    (measured, over `t`: 1.2000 on that sound oneplus against 1.0809 on the
    wrong drilled plate — the same overlap again).

    What separates them is not another distance. It is WHAT THE FEATURE DID:

        the point proves material that had to go is still there
        AND the kernel removed next to nothing at all

    — and the second half is the check this file has always had, `abs(v_out -
    v_in) <= 1e-6`, with a floor a person would recognise instead of one that
    only catches a result identical to the last decimal. On its own a volume
    fraction cannot judge a shell (a 12 mm plate at 5.9 mm walls leaves 1.09
    per cent and is CORRECT), and on its own the point cannot either; together
    they say "this feature did nothing, and here is the proof it should have
    done something", which is a sentence the user can act on. The margins are
    at `_SHELL_NOTHING_HOLLOWED`.

    The point is also put to the INPUT body first. It was measured in the
    parent process and the kernel half runs in the worker, which reads the body
    back off a .brep; `same_weight` proves the weight survived that trip but a
    body that MOVED would weigh the same, and with no openings there are no
    picks whose marks would notice. A point that is not inside the body this
    result came from is not a statement about it, so it decides nothing. Every
    other branch fails open the same way: a classifier that will not run, a
    volume that will not measure, a point with no margin all leave the verdict
    to the two ratios above."""
    if not deep:
        return
    try:
        depth, at, tol = float(deep[0]), tuple(float(c) for c in deep[1]), float(deep[2])
    except (TypeError, ValueError, IndexError):
        return                            # nothing to judge against
    if depth <= t + tol:
        return                            # no margin: the point is ON the cavity wall
    import inspector                                 # local: avoids an import cycle
    v_in = inspector._try(lambda: float(solid.volume))
    v_out = inspector._try(lambda: float(out.volume))
    if not v_in or v_in <= 0 or v_out is None:
        return                                       # nothing to judge against
    if v_in - v_out > _SHELL_NOTHING_HOLLOWED * v_in:
        return                            # a real cavity: a dropped sliver at worst
    if point_is_inside(solid, at) is not True or point_is_inside(out, at) is not True:
        return
    raise ValueError(
        f"shell: {walls} hollowed next to nothing — the kernel took "
        f"{v_in - v_out:,.6g} mm3 out of {v_in:,.6g} and left material {depth:.4g} mm "
        f"from every face that stays (near x {at[0]:.3g}, y {at[1]:.3g}, "
        f"z {at[2]:.3g}), which a {t:g} mm wall cannot reach. Try a different "
        f"thickness, or open a face")


# What fraction of the body a shell may remove and still count as having
# hollowed NOTHING — asked only once the deep point has proved that material
# a `t` wall cannot reach came back inside the result, so it is the second half
# of an AND and never a verdict on its own.
#
# Measured 2026-09-18 over the gauntlet corpus, the four committed crash
# fixtures and three drilled blocks at nine thicknesses
# (probes/shell_deep_point_corpus.py). Of the cells whose deep point came back
# INSIDE the result:
#
#   WRONG — the kernel handed the body back, and every other check passed it:
#       my-part-5's mirror body at t = 3      6.6e-6 of the body (2.709 mm3)
#       the 81-hole block at t = 3            2.7e-5 (4.02 where ~207 had to go)
#       the 100-hole plate at t = 3           2.9e-5 (0.96 where 77.4 had to go)
#       the 49-hole block at t = 5            2.1e-5 (3.0 mm3)
#       the 49-hole block at t = 3            1.4e-4 (20.3 mm3)
#   SOUND, and reaching this question because the kernel dropped a sliver of
#   cavity where the walls nearly meet:
#       the oneplus case at t = 0.5           3.1e-1 of the body
#           (13,918.990 mm3 of cavity out of 45,328.348)
#
# 1 per cent sits 70x above the highest wrong reading and 31x below the sound
# one. It is also above the cavity of every SOUND result in the corpus that
# comes anywhere near a block by volume (the 12 mm plate at 5.9 mm walls is
# 1.09 per cent) — and those never reach this question at all, because their
# deep point is properly gone.
#
# 2026-09-19, round three: that last sentence is the one that carries this, and
# the "31x below the sound one" is not. The sound population does NOT stop at
# 3.1e-1 — it reaches 4.1e-6, BELOW every wrong reading above. Measured
# (probes/shell_r3_sound_under_the_floor_probe.py) on five shells the kernel
# builds sound and every check calls sound: a 60 x 60 x 12 plate at 5.95 mm
# walls removes 5.4e-3 of itself, a 20 x 20 x 100 bar with the top open at
# 9.8 mm removes 3.6e-4, and a 50 mm box at 24.6 mm removes 4.1e-6 — 0.512 mm3
# out of 125,000. So no number here separates the two populations either, and
# this floor is not what makes the AND safe.
#
# What makes it safe is the OTHER half, and structurally rather than by
# calibration: the point this is asked about is the DEEPEST material in the
# body, so a correct shell is exactly the result that takes it away. All five
# of those sound results have their point OUT of the walls and never reach this
# question, at cavities four orders of magnitude under the floor. The floor's
# job is only to spare the one shape that keeps the point honestly — a kernel
# that drops a sliver where the walls nearly meet (the oneplus case at t = 0.5,
# 3.1e-1) — and for that job "the kernel did next to nothing" is the right
# question and 1 per cent is a number a person can read.
_SHELL_NOTHING_HOLLOWED = 0.01


def point_is_inside(shape, at) -> bool | None:
    """Is `at` inside `shape`? None when OCCT cannot say. Its own function so a
    probe can ask without a refusal, and so both asks share one rule."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    try:
        cls = BRepClass3d_SolidClassifier(shape.wrapped)
        cls.Perform(gp_Pnt(*at), 1e-7)
        return cls.State() == TopAbs_State.TopAbs_IN
    except Exception:                     # OCP errors derive from Exception
        return None


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
    assert_every_lump_open(solid, openings)
    walls = f"walls of {t:g} mm"
    if d == "inside" and not openings:
        assert_wall_fits_every_lump(solid, t, walls)
    deep = None
    if d == "inside":
        # the deep point this measures is asked about again AFTER the kernel
        # (`assert_the_deepest_point_was_hollowed`), so it travels with the job
        deep = assert_something_would_be_hollowed(solid, t, openings, walls)
    import kernelguard                           # local: kernelguard reads sketch
    return kernelguard.guarded(
        "shell", solid,
        {"thickness": t, "direction": d, "walls": walls, "deep": deep,
         "picks": kernelguard.indices(solid.faces(), openings),
         "marks": kernelguard._marks(openings),
         "crashed":
             f"shell: {walls} {kernelguard.CRASH_PHRASE} — nothing was changed "
             f"and the app is unharmed. This body's faces cannot all be offset "
             f"by {t:g} mm at once. The thicknesses that work are not one band, "
             f"so a thinner AND a thicker wall are both worth trying, or open "
             f"another face.",
         "stopped":
             f"shell: {walls} {kernelguard.STOPPED_PHRASE} <minutes> and nothing "
             f"was changed. Hollowing a body with hundreds of faces can take "
             f"that long. Try a thinner wall, or shell the body before the "
             f"features that added those faces."},
        lambda: shell_after_guards(solid, t, d, openings, walls, deep))


def shell_after_guards(solid, t: float, d: str, openings: list, walls: str,
                       deep=None):
    """The half of shell() that can kill the process — the kernel offset, the
    boolean that follows a closed hollow, and the four checks that judge what
    comes back.

    Split out of `shell` on 2026-09-13 so it can run in the kernel worker
    (kernelguard.py). FOUR bodies segfault OpenCASCADE in here and no bound on
    the bounding box fences any of them: a box-clipped ball outside from 1.2 mm
    up, the oneplus case open-bottom at 0.5/0.8/1.0/1.1/1.5 but NOT at 0.2 or
    2.0, and the pump impeller's three lumps closed at every thickness from 0.8
    to 2.9. Both sides of the guard call THIS, so the in-process path and the
    worker path are the same code, not two copies."""
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
    # OCCT's own verdict, which `closed_shell` is NOT: the topology census walks
    # the edges, and a shell can have every edge on exactly two faces while
    # BRepCheck_Analyzer still refuses the solid. Measured 2026-09-14 on
    # my-part-5 s18800's mirror body at t = 1.5: 413262.875 -> 137707.973 mm3,
    # closed_shell True, `is_valid` False. `inspector.health` reads the same
    # flag, so the DOCUMENT catches this one on a result feature — but it runs
    # health with check_valid=False on INTERMEDIATE features (Document.rebuild,
    # for the 270 ms), and the op that eats its body must not hand one on.
    # A property that RAISES is not an exception to this — `_try` handles it
    # (section 4 round two).
    if inspector._try(lambda: bool(out.is_valid)) is False:
        raise ValueError(f"shell: {walls} leave a broken solid (OpenCASCADE itself "
                         f"reports it invalid) — use a thinner wall")
    assert_walls_could_be_a_skin(solid, out, t, d, walls)
    assert_every_lump_hollowed(solid, out, d, walls)
    # last, so the two sentences above keep the cases they already own — this
    # one speaks for the results neither ratio can see
    assert_the_deepest_point_was_hollowed(solid, out, deep, t, walls)
    return out


# ---------------------------------------------------------------------------
# Loft (Tier 2, specs/loft.md). Measured first (probes/loft_api_probe.py):
#   two sections of any shapes: exact (cylinder, cone, circle->square, twist)
#   three sections: `ruled` is exact piecewise; smooth bulges (0.75 of ruled
#     on r5-r2-r5) — a real spline, not a defect
#   coplanar sections: a 0-volume "solid" (health says empty)
#   sections OUT OF ORDER along the axis (z 0, 20, 10): a self-intersecting
#     solid at 1.98x the honest volume, is_valid True, health [] — only the
#     ORDER catches it, so the sections must run one way along the loft
#   the same sketch twice: StdFail_NotDone (gated by id in the document)
# ---------------------------------------------------------------------------
LOFT_STEP_TOL = 1e-3         # two sections closer than this along the loft are one plane


def loft_geometry(sections: list, ids: list | None = None) -> dict:
    """Everything the op AND the planner must agree on about a set of
    sections — ONE home. Each section: one face; the loft's axis is the mean
    of the section normals; the sections must step one way along it. Returns
    the centroids, normals, areas, the axis, each section's station along it
    and the order the sections would need to be in; raises a sentence for
    what cannot be lofted."""
    names = list(ids) if ids else [f"section {i + 1}" for i in range(len(sections))]
    if len(sections) < 2:
        raise ValueError("loft needs at least 2 profiles — pick a second sketch")
    faces = []
    for name, s in zip(names, sections):
        fs = s.faces()
        if len(fs) != 1:
            raise ValueError(
                f"loft blends ONE closed profile per sketch, and '{name}' holds "
                f"{len(fs)} — " + ("draw a closed shape in it" if not fs else
                                    "draw each profile in its own sketch"))
        faces.append(fs[0])
    centroids = [f.center() for f in faces]
    normals = [f.normal_at(f.center()) for f in faces]
    axis = b3d.Vector(0, 0, 0)
    for n in normals:                            # normals may point either way
        axis = axis + (n if n.dot(normals[0]) >= 0 else -n)
    if axis.length < 1e-9:
        raise ValueError("loft: the profiles face opposite ways with no common direction "
                         "— turn one of the sketch planes")
    axis = axis.normalized()
    stations = [float((c - centroids[0]).dot(axis)) for c in centroids]
    for i, (a, b) in enumerate(zip(stations, stations[1:]), start=1):
        if abs(b - a) < LOFT_STEP_TOL:
            raise ValueError(
                f"loft produced no solid — '{names[i - 1]}' and '{names[i]}' are on the same "
                f"plane; a loft needs them on DIFFERENT planes")
    steps = [b - a for a, b in zip(stations, stations[1:])]
    if any(s > 0 for s in steps) and any(s < 0 for s in steps):
        order = [names[i] for i in sorted(range(len(names)), key=lambda i: stations[i])]
        if order[0] != names[0]:
            order.reverse()
        raise ValueError(
            "loft: the profiles do not run one way along the loft — "
            + ", ".join(names) + " would fold the solid back through itself (the kernel "
            "builds that and calls it sound). Loft them in the order they lie: "
            + ", ".join(order))
    return {"faces": faces, "centroids": centroids, "normals": normals,
            "areas": [float(f.area) for f in faces], "axis": axis, "stations": stations,
            "length": abs(stations[-1] - stations[0])}


def loft_sketches(sketches: list, ruled: bool = False, ids: list | None = None):
    """Blend two or more single-profile sketches on different planes into one
    solid, in the order given (they must step one way along the loft);
    `ruled` joins them with straight walls, otherwise a smooth spline."""
    sections = list(sketches)
    loft_geometry(sections, ids)                 # the sentences, before the kernel
    try:
        out = _loft(sections, ruled=_to_bool(ruled, "ruled"))
    except Exception as e:      # OCP errors derive from Exception, not RuntimeError
        raise ValueError(
            "loft could not blend these profiles — they must be on DIFFERENT "
            "planes, each one a single closed area") from e
    import inspector                                 # local: avoids an import cycle
    vol = inspector._try(lambda: out.volume) or 0
    if not vol > 0:
        raise ValueError(
            "loft produced no solid — the profiles are on the same plane; a "
            "loft needs them on DIFFERENT planes")
    problems = inspector.health(out, check_valid=False)
    if problems:
        raise ValueError(
            f"loft: the blended solid came back broken ({problems[0]}) — move a profile, "
            f"or loft fewer of them at once")
    return out


# ---------------------------------------------------------------------------
# Sweep (Tier 2, specs/sweep.md): a profile dragged along a PATH sketch.
# Every number below was measured first (probes/sweep_api_probe*.py):
#   the kernel moves the path so its START sits at the profile's CENTRE and
#     the profile follows the path's SHAPE; a path that neither starts nor ends
#     on the profile's plane lands the solid where nobody asked (probe 3, 4)
#   a path leaving IN the profile's plane is a 0-volume "valid" solid (probe 1)
#   a slanted start thins the section by cos(angle): 45° = exactly A·L·cos45
#   a bend tighter than the profile reaches folds the inside over itself —
#     volume A·L, is_valid True, health [] (probe 2): only a number catches it
#   a corner with a leg shorter than the mitre folds too, and there the kernel
#     does say invalid (probe 7) — the sentence is still ours
#   TRANSFORMED swept ONE leg of a sharp corner (half the volume, status ok);
#     RIGHT mitres and gives A·L exactly on tangent and sharp paths alike
#   Wire.trim(0, f) trims by LENGTH fraction — a partial sweep is A·L exactly
# ---------------------------------------------------------------------------
SWEEP_INPLANE_DEG = 80.0     # a path leaving within this of the profile's plane makes no solid
SWEEP_SLANT_DEG = 2.0        # steeper than this: the section thins by cos(angle) — a note
#                              (8° already costs 1 % of the volume, measured on the
#                              gauntlet's tapered wall; 2° costs 0.06 %)
SWEEP_VOLUME_TOL = 0.02      # a perpendicular sweep of one face along a planar path is A·L


def _reverse_wire(wire):
    return b3d.Wire([e.reversed() for e in reversed(wire.edges())])


def _profile_reach(faces, centre) -> float:
    """How far the profile extends from its centre (its outline sampled — a
    circle has one vertex, so vertices alone would say 0)."""
    reach = 0.0
    for f in faces:
        for e in f.edges():
            n = 2 if e.geom_type == b3d.GeomType.LINE else 16
            for i in range(n + 1):
                reach = max(reach, (e @ (i / n) - centre).length)
    return reach


def sweep_geometry(faces: list, wire) -> dict:
    """Everything the op AND the planner must agree on about a profile and a
    path — ONE home, so the handles and the solid come from the same verdict.

    Returns the wire as it will be swept (reversed when only its far end
    touches the profile's plane), the profile's centre and normal, the start,
    the angle the path leaves at, the profile's reach, the path's length, the
    tightest bend and the notes to say; raises a sentence for each measured
    way the sweep cannot be right (see the module comment above)."""
    if not faces:
        raise ValueError("sweep: the profile has no closed shape to sweep — a path "
                         "sketch (open lines) is what Sweep FOLLOWS, not what it sweeps")
    prof = b3d.Sketch(children=list(faces))
    centre = prof.center()
    normal = faces[0].normal_at(faces[0].center())
    length = wire.length
    if length <= 1e-9:
        raise ValueError("sweep: the path has no length")
    tol = max(0.1, 1e-3 * length)
    d_start = abs((wire.start_point() - centre).dot(normal))
    d_end = abs((wire.end_point() - centre).dot(normal))
    was_reversed = False
    if d_start > tol:
        if d_end > tol:
            raise ValueError(
                f"sweep: the path starts {d_start:.3g} mm off the profile's plane (its far "
                f"end {d_end:.3g} mm) — start it ON the profile: draw the path from the "
                f"profile's centre, snapping to the profile's plane")
        wire = _reverse_wire(wire)
        was_reversed = True
    start = wire.start_point()
    t0 = wire.tangent_at(0)
    angle = math.degrees(math.acos(max(-1.0, min(1.0, abs(t0.dot(normal))))))
    if angle >= SWEEP_INPLANE_DEG:
        raise ValueError(
            f"sweep: the path runs along the profile instead of away from it (it leaves "
            f"at {angle:.0f}° to the profile's normal) — draw the path on a plane "
            f"perpendicular to the profile, leaving the profile face-on")
    notes = []
    if was_reversed:
        notes.append("the path was read from its far end — the end that touches the "
                     "profile's plane")
    if angle > SWEEP_SLANT_DEG:
        notes.append(f"the path leaves the profile at {angle:.0f}° — the section is "
                     f"thinner by that angle; a path perpendicular to the profile keeps "
                     f"the profile's true shape")
    reach = _profile_reach(faces, centre)
    off = (start - centre).length
    if off > reach + tol:
        notes.append(f"the path starts {off:.3g} mm from the profile's centre — the sweep "
                     f"runs from the centre, following the path's shape")
    # bends: an arc tighter than the reach folds the inside of the bend
    min_bend = None
    for e in wire.edges():
        if e.geom_type == b3d.GeomType.CIRCLE:
            r = float(e.radius)
            min_bend = r if min_bend is None else min(min_bend, r)
            if r <= reach + 1e-6:
                raise ValueError(
                    f"sweep: the bend of radius {r:.3g} mm is tighter than the profile "
                    f"reaches ({reach:.3g} mm) — the inside of the bend folds over itself; "
                    f"widen the bend or shrink the profile")
    # corners: a mitre needs reach·tan(turn/2) of straight path on each side
    edges = wire.edges()
    s = 0.0
    for i, (a, b) in enumerate(zip(edges, edges[1:]), start=1):
        s += a.length
        ta = wire.tangent_at(max(0.0, (s - 1e-4) / length))
        tb = wire.tangent_at(min(1.0, (s + 1e-4) / length))
        turn = math.degrees(math.acos(max(-1.0, min(1.0, ta.dot(tb)))))
        if turn < 1.0:
            continue
        if turn > 179.0:
            raise ValueError(
                f"sweep: the path turns straight back on itself at corner {i} — a "
                f"profile cannot be swept through a hairpin; round the corner")
        mitre = reach * math.tan(math.radians(turn / 2))
        for leg, word in ((a.length, "before"), (b.length, "after")):
            if leg < mitre - 1e-6:
                raise ValueError(
                    f"sweep: the {leg:.3g} mm leg {word} the {turn:.0f}° corner is shorter "
                    f"than the {mitre:.3g} mm the profile needs to turn there — the corner "
                    f"folds over itself; lengthen the leg, round the corner, or shrink "
                    f"the profile")
    return {"wire": wire, "reversed": was_reversed, "centre": centre, "normal": normal,
            "start": start, "angle_deg": angle, "reach": reach, "length": length,
            "min_bend": min_bend, "notes": notes}


def sweep_length(distance, full, length: float, label: str = "sweep") -> float:
    """How far along the path a sweep goes — the op's and the planner's ONE
    reading of `distance` / `full`: the whole path for `full`, else a distance
    in (0, length]; 0 is nothing to sweep and beyond the end is refused."""
    if _to_bool(full, "full"):
        return length
    d = float(distance or 0.0)
    if d <= 0:
        raise ValueError(f"{label}: nothing to sweep — the distance is 0; give a distance "
                         f"along the path, or full=true for the whole path")
    if d > length + 1e-6:
        raise ValueError(f"{label}: the distance {d:g} mm is longer than the path "
                         f"({length:.4g} mm) — use full=true for the whole path")
    return min(d, length)


def _sweep_solid(faces: list, wire, distance, full, label: str = "sweep"):
    geo = sweep_geometry(faces, wire)
    length = geo["length"]
    used_len = sweep_length(distance, full, length, label)
    w = geo["wire"]
    used = w if used_len >= length - 1e-6 else w.trim(0, used_len / length)
    try:
        out = _sweep(b3d.Sketch(children=list(faces)), path=used,
                     transition=Transition.RIGHT)
    except Exception as e:      # OCP errors derive from Exception, not RuntimeError
        raise ValueError(
            f"{label}: the kernel could not sweep this profile along the path — a bend "
            f"or a corner is too tight for the profile, or the path crosses itself; "
            f"round the corners or shrink the profile") from e
    import inspector                                 # local: avoids an import cycle
    problems = inspector.health(out)
    if problems:                                     # a failed feature beats a corrupt body
        raise ValueError(
            f"{label}: the swept solid came back broken ({problems[0]}) — a bend or a "
            f"corner of the path is too tight for this profile")
    vol = float(out.volume)
    if vol <= 1e-9:
        raise ValueError(f"{label}: the sweep produced no material — the path leaves "
                         f"within the profile's plane; draw it on a perpendicular plane")
    # Pappus: a section carried perpendicularly along a planar path sweeps
    # exactly area × length. Off by more, it folded over itself somewhere the
    # bend and corner checks could not see (one face only: a second face off
    # the path follows a longer or shorter trajectory of its own).
    if len(faces) == 1 and geo["angle_deg"] <= SWEEP_SLANT_DEG:
        expected = float(faces[0].area) * used.length
        if abs(vol - expected) > SWEEP_VOLUME_TOL * expected:
            raise ValueError(
                f"{label}: the swept solid folded over itself (its volume is "
                f"{100 * vol / expected:.0f} % of what the path's length allows) — a bend "
                f"or a corner is tighter than the profile; widen it or shrink the profile")
    for n in geo["notes"]:
        _note(n)
    return out


def _path_point_list(path_points, label: str) -> list:
    """The legacy `path_points` as points, or a sentence naming what is wrong.

    `[(float(p[0]), float(p[1]), float(p[2])) for p in path_points]` was the
    whole of it, so a tree holding anything else answered in raw Python.
    Measured 2026-09-19: `[1, 2]` reached the feature row as `'int' object is
    not subscriptable`, `true` as `'bool' object is not iterable`, and `"abc"`
    and a table as `could not convert string to float: 'a'` — not one of them
    naming the thing to change.

    Same shape as `blocks._pick_point`, and as WIDE as what works today: any
    sequence of three or more values `float()` accepts, so ["0", "0", "5"]
    resolves exactly as it did. The only new refusals are a word, a mapping, a
    flag and anything that is not three numbers, and none of those builds a
    path today."""
    if isinstance(path_points, (str, bytes, bytearray, dict, bool)) \
            or not hasattr(path_points, "__iter__"):
        raise ValueError(
            f"{label}: path_points must be a list of points, each [x, y, z] in mm "
            f"(got {path_points!r}) — or give `path` = the id of a sketch holding "
            f"an open path drawn with the Path tool")
    out = []
    for p in path_points:
        if isinstance(p, (str, bytes, bytearray, dict, bool)):
            vals = None
        else:
            try:
                vals = [float(x) for x in p]
            except (TypeError, ValueError):
                vals = None
        if vals is None or len(vals) < 3:
            raise ValueError(
                f"{label}: every point of path_points must be three numbers "
                f"[x, y, z] in mm (got {p!r}) — or give `path` = the id of a "
                f"sketch holding an open path drawn with the Path tool")
        out.append((vals[0], vals[1], vals[2]))
    return out


def _sweep_path(path, path_points, smooth, _path_sketch, label: str = "sweep"):
    """The wire a sweep follows: the path sketch the document handed over
    (`path`, a reference the document resolves — see Document._path_part), or
    the legacy `path_points` polyline / spline of AI-authored trees."""
    if _path_sketch is not None:
        wires = sketch_paths(_path_sketch)
        if not wires:
            raise ValueError(f"{label}: '{path}' holds no open path — draw one in it with "
                             f"the sketch ribbon's Path tool (an open line-and-arc chain)")
        if len(wires) > 1:
            _note(f"'{path}' holds {len(wires)} paths — the first one drawn is the "
                  f"sweep's path")
        return wires[0]
    if path:
        raise ValueError(f"{label}: the path sketch '{path}' was not resolved — sweep "
                         f"through the document, which hands the path sketch over")
    if path_points:
        smooth = _to_bool(smooth, "smooth")
        pts = _path_point_list(path_points, label)
        if len(pts) < 2:
            raise ValueError(f"{label}: path_points needs at least 2 points")
        with BuildLine() as bl:
            if smooth and len(pts) >= 3:
                Spline(*pts)
            else:
                Polyline(*pts)
        return bl.wire()
    raise ValueError(f"{label} needs a path: `path` = the id of a sketch holding an open "
                     f"path drawn with the Path tool")


def sweep_sketch(sketch, path: str | None = None, distance: float = 0.0,
                 full: bool = False, path_points: list | None = None,
                 smooth: bool = False, _path_sketch=None):
    """Drag a profile sketch along a PATH: `path` names a path sketch (an open
    line-and-arc chain drawn with the Path tool on a plane perpendicular to the
    profile, starting on it); `distance` in mm along it, or `full` for the
    whole path. Legacy: `path_points` [[x,y,z],…] (straight, or `smooth`).
    The kernel sweeps from the profile's CENTRE along the path's shape."""
    if isinstance(path, (list, tuple)):          # the legacy positional point list
        path, path_points = None, list(path)
    faces = sketch.faces()
    if not faces:
        raise ValueError("sweep: the profile sketch holds only a path (open lines, no "
                         "closed shape) — a profile needs a closed shape; the path "
                         "sketch goes in `path`")
    wire = _sweep_path(path, path_points, smooth, _path_sketch)
    if path_points and _path_sketch is None and not full and not distance:
        full = True                              # a legacy tree swept the whole polyline
    return _sweep_solid(faces, wire, distance, full)


def sweep_face(solid, face_center: list, face_normal: list | None = None,
               face_area: float | None = None, path: str | None = None,
               distance: float = 0.0, full: bool = False, _path_sketch=None):
    """Sweep a flat face of the input body along a path sketch (a FACE-REFERENCE
    op like extrude_face: the body lives on; fuse / cut the result with it).
    The face is resolved by geometry at every rebuild (extrude_face's rule)."""
    face, _pl, _prof = face_profile(solid, face_center, face_normal, "swept", face_area)
    wire = _sweep_path(path, None, False, _path_sketch, "sweep_face")
    return _sweep_solid([face], wire, distance, full, "sweep_face")


# ops that produce a 2D sketch (not a solid) — the document engine checks these
# for area, not solid health
SKETCH_PRODUCERS = {"sketch", "sketch_on_face"}

# ops that produce a construction PLANE (Fusion's Construct menu): neither a
# solid nor a sketch — a place to sketch on. Checked for nothing at rebuild
# (a Plane is a frame); sketches name one in their `plane` (specs/offset-plane.md)
PLANE_PRODUCERS = {"offset_plane"}
PRINCIPAL_PLANES = tuple(_PLANES)        # "XY", "XZ", "YZ": a `plane` that is not a feature

# ops whose solid input is only a FACE REFERENCE (where to work), never
# geometric consumption: a sketch drawn on a box's face does not eat the box,
# and extrude_face outputs a separate boss solid while the source body lives
# on. The document engine must NOT count their inputs as "consumed" or the
# referenced body vanishes from the viewport the moment the sketch is used
# (reported: "after finishing the sketch and extruding, the main body
# vanishes").
FACE_REFERENCE_OPS = {"sketch_on_face", "extrude_face", "revolve_face", "sweep_face",
                      "offset_plane"}      # a plane off a face does not eat the body


def is_sketch(obj) -> bool:
    return isinstance(obj, b3d.Sketch)
