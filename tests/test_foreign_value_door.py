"""Round THREE of the op-catalogue / refusal-sentence review (2026-09-17).

`Document.add` opens a design written by another build without refusing a
thing (`strict=False`, and a file must always open), so by the time the rebuild
unpacks a feature, a parameter can hold ANYTHING. Rounds one and two closed the
MODIFIERS' numeric door. This file locks in what round three measured on top of
current master — after Named parameters rewrote the same code path:

  * the CREATORS never reached that door at all, so `sketch {"offset": null}`
    built silently at Z = 0 and `{"offset": true}` at Z = 1
    (probes/s10_r3_creator_door.py);
  * `curved_blade` did its own arithmetic on whatever it was handed, so six
    parameters answered in Python and three BUILT a different blade
    (probes/s10_r3_valueerror_census.py);
  * `revolve_profile` measured `len(points)` before looking;
  * a face pick and an edge pick that are not points answered
    `could not convert string to float: 'a'` and
    `not enough values to unpack (expected 3, got 2)` — 36 rows of the census;
  * `rotate`'s own refusal HASHED what it was given, so a list there raised
    instead of being refused, and `scale`'s never said what it got;
  * a feature whose `params` is not a dict took the WHOLE rebuild down with a
    `TypeError`, and `Document.rebuild`'s docstring promises it never raises;
  * `plain_cause` passed PYTHON's own ValueError off as one of our sentences
    (probes/s10_r3_raise_marker.py);
  * a refusal could name a feature that is not in this design at all, because
    the rebuild cache is one dict for the whole process and a signature leaves
    feature NAMES out on purpose;
  * a pattern's `count` was not in `numeric_params`, so it could not hold a
    formula though the AI's prompt says every numeric parameter may.

Every assertion here was measured first and was RED before the fix. The
library was scanned read-only before any of it (probes/s10_r3_library_scan.py:
386 files, 8660 numeric parameter values, every one of them a plain number), so
nothing newly refused here is work anybody has saved.
"""
import pytest

import blocks
import paramexpr
from document import CREATORS, Document

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
PLATE = {"width": 20, "depth": 20, "thickness": 5}

# Python's own words about a Python fact: never a sentence for the user
PYTHON_WORDS = (
    "TypeError", "AttributeError", "ZeroDivisionError", "IndexError",
    "could not convert", "unsupported operand", "not supported between",
    "is not iterable", "unhashable", "object has no attribute",
    "not enough values to unpack", "too many values to unpack",
    "has no len()", "dictionary update sequence",
)


def _is_python(text: str) -> bool:
    return any(w in text for w in PYTHON_WORDS)


def _row(op, params):
    """One feature of `op` on a 20x20x5 plate (or on its own), rebuilt."""
    d = Document(name="f")
    if op in CREATORS:
        d.add("p1", op, params, [])
    else:
        d.add("b1", "plate", PLATE, [])
        d.add("p1", op, params, ["b1"])
    d.rebuild()
    return d, d.get("p1")


# --- the creators' numeric door ----------------------------------------------

def test_a_sketch_offset_that_is_not_a_number_is_refused_not_taken_as_zero():
    """MEASURED RED: `offset: null` built at Z = 0 and `offset: true` at Z = 1,
    both green — a silent wrong PLACEMENT, the worst class there is. The
    authoring door already refused both; only the file door did not."""
    for bad in (None, True, False):
        d, f = _row("sketch", {"entities": CIRC, "plane": "XY", "offset": bad})
        assert f.status == "failed", f"offset={bad!r} built at {f.problems}"
        assert "offset" in " ".join(f.problems)
        assert not _is_python(" ".join(f.problems)), f.problems


def test_a_sketch_offset_that_is_a_list_says_so_in_words():
    """MEASURED RED: `TypeError: float() argument must be a string or a real
    number, not 'list'` in the feature row."""
    d, f = _row("sketch", {"entities": CIRC, "plane": "XY", "offset": [1, 2]})
    assert f.status == "failed"
    assert not _is_python(" ".join(f.problems)), f.problems


def test_a_real_sketch_offset_still_places_the_sketch_where_it_says():
    """The gate must not refuse correct work: a number, a negative number and
    a FORMULA all still place the plane."""
    d = Document(name="g")
    d.set_parameter("lift", "3*2")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 7.0}, [])
    d.add("s2", "sketch", {"entities": CIRC, "plane": "XY", "offset": -4}, [])
    d.add("s3", "sketch", {"entities": CIRC, "plane": "XY", "offset": "lift"}, [])
    assert d.rebuild() is True, [f.problems for f in d.features]
    for fid, z in (("s1", 7.0), ("s2", -4.0), ("s3", 6.0)):
        bb = d._parts[fid].bounding_box()
        assert bb.min.Z == pytest.approx(z, abs=1e-6), fid


def test_every_creator_now_answers_a_null_number_in_words():
    """The census that found it: every numeric parameter of every creator,
    set to null, must read as a sentence naming the parameter."""
    bases = {
        "plate": PLATE,
        "disc": {"radius": 10, "thickness": 5},
        "ball": {"radius": 10},
        "cone": {"bottom_radius": 10, "top_radius": 5, "height": 10},
        "tube": {"outer_radius": 10, "inner_radius": 5, "height": 10},
        "polygon_plate": {"sides": 6, "circumradius": 10, "thickness": 5},
        "hex_plate": {"across_flats": 20, "thickness": 5},
        "curved_blade": {"inner_radius": 5, "outer_radius": 12,
                         "inlet_angle_deg": 30, "exit_angle_deg": 50,
                         "height": 6, "thickness": 1.5},
        "sketch": {"entities": CIRC, "plane": "XY", "offset": 0.0},
    }
    for op, base in bases.items():
        for k in sorted(Document.numeric_params(op)):
            if k not in base:
                continue
            for bad in (None, True, [1, 2]):
                d, f = _row(op, {**base, k: bad})
                said = " ".join(f.problems)
                assert f.status == "failed", f"{op}.{k}={bad!r} built: {said}"
                assert k in said, f"{op}.{k}={bad!r} -> {said}"
                assert not _is_python(said), f"{op}.{k}={bad!r} -> {said}"


def test_a_creator_that_names_its_own_unit_keeps_that_sentence():
    """Round two's rule still holds where the creator HAS its own sentence:
    `blocks._positive` names the unit and is reached first for a number that
    is out of range."""
    d, f = _row("plate", {**PLATE, "width": -5})
    assert f.problems == [
        "plate: width must be more than 0 (got -5) — there is no such shape, "
        "so type the size you want instead"]


# --- curved_blade: its own guard, for every caller ----------------------------

BLADE = dict(inner_radius=5, outer_radius=12, inlet_angle_deg=30,
             exit_angle_deg=50, height=6, thickness=1.5)


def test_curved_blade_refuses_a_value_that_is_not_a_number_by_name():
    """MEASURED RED: `TypeError: unsupported operand type(s) for -: 'int' and
    'NoneType'` and five more, straight out of the camber arithmetic."""
    for k in BLADE:
        for bad in (None, "8mm", [1, 2], True):
            with pytest.raises(ValueError) as e:
                blocks.curved_blade(**{**BLADE, k: bad})
            assert k in str(e.value), (k, bad, str(e.value))
            assert not _is_python(str(e.value)), (k, bad, str(e.value))


def test_curved_blade_refuses_a_zero_inner_radius_instead_of_dividing_by_it():
    """MEASURED RED: `ZeroDivisionError: division by zero` — a number, so the
    numeric door lets it past; the camber integral divides by r."""
    with pytest.raises(ValueError) as e:
        blocks.curved_blade(**{**BLADE, "inner_radius": 0})
    assert "inner_radius" in str(e.value)
    assert not _is_python(str(e.value)), str(e.value)


def test_curved_blade_still_builds_every_blade_it_built_before():
    """A blade angle of 0 is a straight radial blade and a negative one is
    forward-swept: neither may be refused."""
    for inlet, exit_ in ((30, 50), (0, 0), (-20, 40), (60, -10)):
        b = blocks.curved_blade(**{**BLADE, "inlet_angle_deg": inlet,
                                   "exit_angle_deg": exit_})
        assert b.volume > 0, (inlet, exit_)


# --- scale ---------------------------------------------------------------------

def test_scale_says_what_it_got_and_refuses_what_is_not_a_number():
    """MEASURED RED: `scale_uniform(part, "2")` answered `TypeError: '<=' not
    supported between instances of 'str' and 'int'` for a script, `True`
    scaled by 1 without a word, and the refusal for 0 never said what it got."""
    p = blocks.plate(10, 10, 2)
    for bad in ("2", None, True, [2]):
        with pytest.raises(ValueError) as e:
            blocks.scale_uniform(p, bad)
        assert "factor" in str(e.value) and not _is_python(str(e.value))
    with pytest.raises(ValueError) as e:
        blocks.scale_uniform(p, 0)
    assert "got 0" in str(e.value), str(e.value)
    assert blocks.scale_uniform(p, 2).volume == pytest.approx(1600.0, abs=0.1)


# --- revolve_profile ----------------------------------------------------------

def test_revolve_profile_says_what_points_are():
    """MEASURED RED: `TypeError: object of type 'NoneType' has no len()` and
    `not enough values to unpack (expected 2, got 1)`."""
    for bad in (None, True, 0, "abc", [1, 2, 3], [[1, 2], [3, 4], "ab"]):
        with pytest.raises(ValueError) as e:
            blocks.revolve_profile(bad)
        assert not _is_python(str(e.value)), (bad, str(e.value))
        assert "point" in str(e.value).lower(), (bad, str(e.value))


def test_revolve_profile_still_revolves_the_profiles_it_did():
    p = blocks.revolve_profile([(0, 0), (5, 0), (5, 10), (0, 10)])
    assert p.volume == pytest.approx(785.4, abs=0.5)
    q = blocks.revolve_profile([[0, 0], [5, 0], [5, 10], [0, 10]])
    assert q.volume == pytest.approx(785.4, abs=0.5)


# --- the picks: a face click and an edge click --------------------------------

def test_a_face_pick_that_is_not_a_point_is_refused_in_words():
    """MEASURED RED: 36 rows of the census read `could not convert string to
    float: 'a'` or `not enough values to unpack (expected 3, got 2)`."""
    for op, extra in (("hole", {"diameter": 3, "depth": 2}),
                      ("extrude_face", {"amount": 3}),
                      ("sketch_on_face", {"entities": CIRC})):
        for bad in ("abc", [1, 2], {"a": 1}, True, 0, [[1, 2]]):
            d, f = _row(op, {"face_center": bad, "face_normal": [0, 0, 1],
                             **extra})
            said = " ".join(f.problems)
            assert f.status == "failed", f"{op} face_center={bad!r}: {said}"
            assert not _is_python(said), f"{op} face_center={bad!r} -> {said}"


def test_a_face_pick_that_is_three_numbers_still_resolves():
    """The gate must be exactly as wide as what works today: a list, a tuple
    and three numeric STRINGS all still find the top face."""
    for pick in ([0, 0, 5], (0, 0, 5), ["0", "0", "5"], [0.0, 0.0, 5.0]):
        d, f = _row("hole", {"face_center": list(pick),
                             "face_normal": [0, 0, 1],
                             "diameter": 3, "depth": 2})
        assert f.status == "ok", (pick, f.problems)
        assert f.volume == pytest.approx(1985.86, abs=0.5)


def test_a_picked_edge_that_is_not_a_point_is_refused_in_words():
    """MEASURED RED: `TypeError: 'int' object is not iterable`."""
    for bad in ([1, 2], [[1, 2]], [None], ["abc"]):
        d, f = _row("fillet", {"radius": 1, "edges": bad})
        said = " ".join(f.problems)
        assert f.status == "failed", f"edges={bad!r}: {said}"
        assert not _is_python(said), f"edges={bad!r} -> {said}"


def test_the_edge_rules_and_a_real_edge_pick_still_work():
    d, f = _row("fillet", {"radius": 1, "edges": "all"})
    assert f.status == "ok", f.problems
    d, f = _row("fillet", {"radius": 1, "edges": [[10, 0, 2.5]]})
    assert f.status == "ok", f.problems


# --- rotate's own refusal -----------------------------------------------------

def test_rotate_refuses_an_axis_it_cannot_even_look_up():
    """MEASURED RED: `TypeError: cannot use 'list' as a dict key (unhashable
    type: 'list')` — the refusal's OWN lookup was the leak."""
    for bad in ([1, 2], {"a": 1}, [], None):
        d, f = _row("rotate", {"axis": bad, "angle_deg": 45})
        said = " ".join(f.problems)
        assert f.status == "failed", f"axis={bad!r}: {said}"
        assert not _is_python(said), f"axis={bad!r} -> {said}"
        assert "axis" in said


def test_rotate_still_turns_about_the_three_axes():
    for ax in ("X", "Y", "Z"):                       # lower case is refused today
        d, f = _row("rotate", {"axis": ax, "angle_deg": 90})
        assert f.status == "ok", (ax, f.problems)


# --- a feature whose params are not a dict at all -----------------------------

def test_a_feature_whose_params_are_not_a_dict_is_one_red_row_not_a_crash():
    """MEASURED RED: `Document.rebuild()` itself raised `TypeError: object is
    not iterable` from `_resolved`'s `dict(f.params)`, which `_signature` calls
    OUTSIDE the per-feature try — so the whole design failed to draw, though
    rebuild's docstring promises it never raises."""
    for bad in ([1, 2], "abc", 7, True):
        d = Document.from_data({"name": "n", "features": [
            {"id": "a", "op": "plate", "params": bad, "inputs": []}]})
        d.rebuild()                                  # must not raise
        f = d.get("a")
        assert f.status == "failed", (bad, f.problems)
        assert not _is_python(" ".join(f.problems)), (bad, f.problems)


def test_a_feature_whose_params_are_not_a_dict_still_opens_in_the_app():
    """MEASURED RED: `parameters_json` and `resolved_json` are both on
    `/api/doc` and both raised `AttributeError: 'list' object has no attribute
    'items'`, so the design could not be OPENED at all — a worse answer than
    one red row."""
    d = Document.from_data({"name": "n", "parameters": {"w": {"expr": "3"}},
                            "features": [{"id": "a", "op": "plate",
                                          "params": [1, 2], "inputs": []}]})
    assert d.parameters_json()[0]["name"] == "w"
    assert d.resolved_json(d.get("a")) == {}
    assert d.parameter_users("w") == {"features": [], "parameters": []}
    d.rename_parameter("w", "w2")                    # must not raise
    assert "a: plate" in d.tree()


# --- plain_cause: OUR ValueError is a sentence, Python's is not ---------------

def _raised(fn):
    try:
        fn()
    except Exception as e:                           # noqa: BLE001 - that IS the test
        return e
    raise AssertionError("did not raise")


def test_our_own_refusals_still_reach_the_user_word_for_word():
    """The safe direction: a sentence one of OUR `raise` statements wrote must
    never be replaced. Twenty-four of them across five modules were measured
    (probes/s10_r3_raise_marker.py); these stand for the whole set."""
    ours = [
        lambda: blocks.plate(None, 20, 5),
        lambda: blocks.plate(-2, 20, 5),
        lambda: blocks.cone(5, 5, 10),
        lambda: blocks.tube(5, 10, 10),
        lambda: blocks.polygon_plate(2, 10, 5),
        lambda: blocks.revolve_profile([(0, 0), (1, 0)]),
        lambda: blocks.curved_blade(12, 5, 20, 40, 6, 1),
        lambda: blocks.rotate(blocks.plate(10, 10, 2), [1]),
        lambda: blocks.scale_uniform(blocks.plate(10, 10, 2), 0),
        lambda: blocks.edges_for(blocks.plate(10, 10, 2), []),
        lambda: blocks.resolve_face(blocks.plate(10, 10, 2), "abc"),
        lambda: paramexpr.evaluate("1/0", {}),
        lambda: paramexpr.evaluate("wall*2", {}),
    ]
    for fn in ours:
        e = _raised(fn)
        assert blocks.plain_cause(e) == str(e), str(e)


def test_pythons_own_value_error_from_our_own_code_is_not_passed_off_as_one():
    """MEASURED RED: `could not convert string to float: ''` — the message the
    §10 row was opened for — reached the feature row because `float()` raises
    ValueError and `plain_cause` returned a ValueError's message unchanged."""
    import sketch as sk

    for bad in ("", "abc"):
        e = _raised(lambda: sk.make_sketch(                        # noqa: B023
            "XY", 0, [{"kind": "rectangle", "x": bad, "y": 0,      # noqa: B023
                       "w": 5, "h": 5, "mode": "add"}]))
        assert isinstance(e, ValueError), (bad, e)
        assert "could not convert" in str(e), (bad, str(e))
        assert blocks.plain_cause(e) == blocks.NOT_A_SENTENCE, (bad, str(e))


def test_a_value_error_with_no_traceback_is_left_alone():
    """A refusal built by hand (tests, the kernel worker re-raising across the
    process boundary) has no traceback to read: it counts as ours."""
    assert blocks.plain_cause(ValueError("pick a face first")) == "pick a face first"


def test_a_library_value_error_is_left_alone():
    """build123d's own refusals are plain, so a ValueError raised OUTSIDE this
    directory keeps passing through exactly as it did."""
    import build123d as b3d

    e = _raised(lambda: b3d.Cylinder(radius=1, height=1).fillet(
        radius=50, edge_list=b3d.Cylinder(radius=1, height=1).edges()))
    assert isinstance(e, ValueError)
    # the mechanism itself: a frame outside this directory is never called
    # Python's doing, whatever the wording
    assert blocks._python_raised_it(e) is False
    # and the answer is the one it had before round three (the fillet rule,
    # which runs first) — not the value sentence
    assert blocks.plain_cause(e) == "the kernel could not build it there"
    assert blocks.plain_cause(e) != blocks.NOT_A_SENTENCE


# --- a refusal may only name the feature it is about --------------------------

def test_a_refusal_never_names_another_designs_feature():
    """MEASURED RED: the rebuild cache is ONE dict for the whole process and a
    signature deliberately leaves feature NAMES out (inputs go in by signature,
    so a rename costs nothing). Since the refusals started naming the feature,
    the second design's failing row read the FIRST one's name —

        design 1, feature `boss_height` -> "'boss_height' (extrude): amount …"
        design 2, feature `rib_depth`   -> "'boss_height' (extrude): amount …"

    a feature that is not in that design at all, and the cache spans tabs."""
    def failing(fid):
        d = Document(name="d-" + fid)
        d.add("s1", "sketch", {"entities": CIRC, "plane": "XY",
                               "offset": 0.0}, [])
        d.add(fid, "extrude", {"amount": None}, ["s1"])
        d.rebuild()
        return " ".join(d.get(fid).problems)

    first = failing("boss_height")
    second = failing("rib_depth")
    assert "boss_height" in first
    assert "rib_depth" in second, second
    assert "boss_height" not in second, second


def test_a_refusal_never_names_another_designs_INPUT():
    """The same seam through the other name a refusal can carry: the id of the
    upstream feature ("… and 'flat_profile' is a sketch")."""
    def failing(sid):
        d = Document(name="d-" + sid)
        d.add(sid, "sketch", {"entities": CIRC, "plane": "XY",
                              "offset": 0.0}, [])
        d.add("f1", "fillet", {"radius": 1}, [sid])
        d.rebuild()
        return " ".join(d.get("f1").problems)

    first = failing("flat_profile")
    second = failing("lid_outline")
    assert "flat_profile" in first
    assert "lid_outline" in second, second
    assert "flat_profile" not in second, second


def test_geometry_that_did_not_fail_is_still_shared_between_documents():
    """The cache's whole point: two designs asking the same question build it
    once. Only refusals are kept per name."""
    import document as docmod

    def plate_doc():
        d = Document(name="p")
        d.add("b1", "plate", PLATE, [])
        d.rebuild()
        return d

    plate_doc()
    before = len(docmod._SHARED_CACHE)
    plate_doc()
    assert len(docmod._SHARED_CACHE) == before


# --- the formula door, re-measured after Named parameters ---------------------

# Text that PARSES as a formula is answered by the evaluator, naming what it
# could not work out; text that does not parse at all is answered by the
# numeric door's own sentence. Both name the feature and the parameter, and
# neither is Python. (Measured on current master, after Named parameters.)
FORMULA_CASES = [
    ("", "must be a number"), ("   ", "must be a number"),
    ("8mm", "must be a number"), ("[1,2]", "must be a number"),
    ("'x'", "must be a number"), ("open('x')", "must be a number"),
    ("wall.real", "must be a number"),
    ("1/0", "divides by zero"), ("wall*2", "no parameter named"),
    ("sqrt(-1)", "cannot be worked out"), ("1e400", "no finite value"),
    ("0-9999999999", "too large"), ("2**200", "exponent past"),
]


@pytest.mark.parametrize("expr,want", FORMULA_CASES)
def test_a_formula_that_cannot_work_out_is_a_sentence_naming_the_parameter(expr, want):
    """Named parameters put a whole evaluator behind every numeric slot. Each
    of these must come back naming the feature, the parameter and the reason —
    never Python."""
    d, f = _row("extrude_face", {"face_center": [0, 0, 2.5],
                                 "face_normal": [0, 0, 1], "amount": expr})
    said = " ".join(f.problems)
    assert f.status == "failed", (expr, said)
    assert "amount" in said and "'p1'" in said, (expr, said)
    assert want in said, (expr, said)
    assert not _is_python(said), (expr, said)


def test_a_pattern_count_is_a_number_the_parameters_can_drive():
    """MEASURED RED: the AI's prompt says "any NUMERIC feature param may then
    be a formula string naming them" and the catalogue marks `count` with
    `unit: "count"`, but a pattern's count carried no type annotation, so
    `numeric_params` missed it: `{"count": "ribs"}` was refused as
    "polar_pattern: count must be a whole number ≥ 1 (got 'ribs')" and the
    Parameters panel could not drive a pattern at all."""
    for op, extra in (("polar_pattern", {"axis": "+z"}),
                      ("linear_pattern", {"dx": 30})):
        d = Document(name="c")
        d.set_parameter("ribs", "4")
        d.add("b1", "plate", PLATE, [])
        d.add("p1", op, {"count": "ribs", **extra}, ["b1"])
        assert d.rebuild() is True, (op, d.get("p1").problems)
        assert d.resolved_json(d.get("p1"))["count"] == 4.0, op
        assert d.parameter_users("ribs")["features"] == ["p1"], op


def test_a_pattern_count_still_refuses_what_it_always_refused():
    """The floor and the whole-number rule are `_count`'s and stay there."""
    for bad, want in ((0, "whole number"), (2.5, "whole number"),
                      (-1, "whole number"), (None, "must be a number")):
        d = Document(name="c")
        d.add("b1", "plate", PLATE, [])
        d.add("p1", "polar_pattern", {"count": bad, "axis": "+z"}, ["b1"])
        d.rebuild()
        said = " ".join(d.get("p1").problems)
        assert d.get("p1").status == "failed", (bad, said)
        assert want in said, (bad, said)
        assert not _is_python(said), (bad, said)


def test_a_formula_in_a_numeric_slot_still_drives_the_geometry():
    d = Document(name="p")
    d.set_parameter("wall", "3")
    d.add("b1", "plate", {"width": "wall*10", "depth": 20,
                          "thickness": "wall"}, [])
    assert d.rebuild() is True, d.get("b1").problems
    assert d.get("b1").volume == pytest.approx(1800.0, abs=0.01)


def test_the_evaluator_never_returns_a_value_the_ops_cannot_use():
    """Whatever a formula says, `evaluate` answers a finite float or raises a
    sentence — never None, a string, a complex number, inf or nan."""
    for expr in ("2**0.5", "-3", "0", "sqrt(2)", "min(3,4)", "round(2.6)",
                 "1e9", "-1e9", "abs(-2)", "ceil(1.2)", "sin(90)"):
        v = paramexpr.evaluate(expr, {})
        assert isinstance(v, float) and v == v and abs(v) != float("inf"), expr
    for expr in ("1e400", "-1e400", "0/0", "1/0", "10**10**10", "2**1000"):
        with pytest.raises(ValueError):
            paramexpr.evaluate(expr, {})


# --- ROUND FOUR: the key the refusal itself is kept under ---------------------
#
# Round three keyed a refusal by `f"{sig}!{f.id}<{','.join(f.inputs)}"`, so a
# second design's failing row could no longer read the FIRST design's feature
# name. Two things that key does not survive, both measured 2026-09-17
# (probes/s10_r4_cache_key.py, probes/s10_r4_fail_key_and_spec.py).

def test_a_refusal_key_does_not_take_the_rebuild_down():
    """MEASURED RED: `','.join(f.inputs)` is `rebuild`'s FIRST look at a
    feature, before the per-feature try, so an input id a foreign file holds
    as a number raised `TypeError: sequence item 0: expected str instance,
    int found` out of `Document.rebuild()` — which promises it never raises.
    Round three closed exactly this class for `params` and opened it here."""
    d = Document.from_data({"name": "n", "features": [
        {"id": 5, "op": "plate", "params": PLATE, "inputs": []},
        {"id": "b", "op": "fillet", "params": {"radius": None}, "inputs": [5]},
    ]})
    d.rebuild()                                      # must not raise
    assert d.get("b").status == "failed"
    assert not _is_python(" ".join(d.get("b").problems)), d.get("b").problems
    assert d.tree()                                  # /api/doc walks it too


def test_two_feature_names_never_share_one_refusal():
    """MEASURED RED: `<` and `,` are the key's own separators and a feature id
    may hold either, so `'a<b'` with input `'c'` and `'a'` with input `'b<c'`
    built the SAME key — and the second design's row read "'a<b' (extrude)",
    a feature that is not in it. The same leak round three closed, through the
    key that closed it."""
    def failing(fid, sid):
        d = Document(name="c-" + fid)
        d.add(sid, "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
        d.add(fid, "extrude", {"amount": None}, [sid])
        d.rebuild()
        return " ".join(d.get(fid).problems)

    first = failing("a<b", "c")
    second = failing("a", "b<c")
    assert "'a<b'" in first, first
    assert "'a'" in second and "'a<b'" not in second, second


# --- ROUND FOUR: the SHAPE of a feature, not just the values in it ------------
#
# Round three's census walked every PARAMETER of every op. A foreign file also
# decides the shape of the feature AROUND those parameters — its id, its op,
# what it is built from, whether it is switched off — and of the document
# around that. Measured 2026-09-17 (probes/s10_r4_feature_shape.py): 35 shapes,
# 16 of them answering in Python, most of them at OPEN, which is the one answer
# a design cannot recover from.

def _opens(payload):
    """(the document or None, the sentence the user gets)"""
    try:
        return Document.from_data(payload), ""
    except Exception as e:                           # noqa: BLE001 - that IS the test
        return None, f"{type(e).__name__}: {e}"


def test_a_file_whose_parameters_are_not_a_table_still_opens():
    """MEASURED RED: `AttributeError: 'list' object has no attribute 'items'`
    from `from_data` itself, so a design whose FEATURES are all fine could not
    be opened at all — against the promise three lines above it ("parameters
    FIRST and without refusal: a file must always open")."""
    for bad in ([1, 2], "wall", 5):
        d, said = _opens({"name": "n", "parameters": bad, "features": [
            {"id": "a", "op": "plate", "params": PLATE, "inputs": []}]})
        assert d is not None, (bad, said)
        assert d.parameters == {}
        assert d.rebuild() is True
        assert d.get("a").volume == pytest.approx(2000.0)


def test_a_damaged_feature_says_so_instead_of_answering_in_python():
    """Every shape that CANNOT open must still be a sentence. Measured before
    the fix: `TypeError: cannot use 'list' as a dict key`, `... as a set
    element`, `KeyError: 'id'`, `KeyError: 'op'`, `'int' object is not
    iterable`, `list indices must be integers`."""
    cases = [
        {"id": ["a"], "op": "plate", "params": PLATE},          # id unhashable
        {"id": {"a": 1}, "op": "plate", "params": PLATE},
        {"op": "plate", "params": PLATE},                       # no id
        {"id": "a", "op": ["plate"], "params": PLATE},          # op unhashable
        {"id": "a", "op": {"plate": 1}, "params": PLATE},
        {"id": "a", "params": PLATE},                           # no op
        {"id": "a", "op": "plate", "params": PLATE, "inputs": 5},
        {"id": "a", "op": "plate", "params": PLATE, "inputs": True},
        [1, 2],                                                 # not a feature
        "plate",
    ]
    for bad in cases:
        d, said = _opens({"name": "n", "features": [bad]})
        assert d is None, (bad, "opened anyway")
        assert said.startswith("ValueError"), (bad, said)
        assert not _is_python(said), (bad, said)


def test_a_file_that_is_not_a_design_says_so():
    for bad in ({"features": [{"id": "a", "op": "plate", "params": PLATE}]},
                {"name": "n"},
                {"name": "n", "features": {"a": 1}},
                {"name": "n", "features": "plate"},
                [1, 2], "n"):
        d, said = _opens(bad)
        assert d is None, (bad, "opened anyway")
        assert said.startswith("ValueError"), (bad, said)
        assert not _is_python(said), (bad, said)


def test_a_spec_that_is_not_a_table_does_not_stop_the_design_opening():
    """MEASURED RED: `tree()` raised `AttributeError: 'list' object has no
    attribute 'items'` and `_spec_obj()` `TypeError: object is not iterable`,
    both on a design whose features are all fine. The spec is kept as written
    (nothing a file holds is thrown away on the way in), and the two places
    that READ it look first."""
    d, said = _opens({"name": "n", "spec": [1, 2], "features": [
        {"id": "a", "op": "plate", "params": PLATE, "inputs": []}]})
    assert d is not None, said
    d.rebuild()                                      # must not raise
    assert d.get("a").status == "ok"                 # the GEOMETRY is fine
    assert d.get("a").volume == pytest.approx(2000.0)
    assert "a: plate" in d.tree()
    assert d.to_data()["spec"] == [1, 2]             # not thrown away
    # the spec itself cannot be checked, and says so in words
    assert d.spec_problems and not _is_python(" ".join(d.spec_problems)), \
        d.spec_problems


def test_a_switch_that_is_not_a_switch_is_read_and_saved_as_one():
    """`suppressed` decides whether a feature is in the model at all. A file
    holding a word there was read by Python truthiness and written back out
    the same way, so the tree and the file could disagree about it."""
    for bad, want in (("yes", True), (1, True), (0, False), (None, False),
                      ([], False), ({"a": 1}, True)):
        d, said = _opens({"name": "n", "features": [
            {"id": "a", "op": "plate", "params": PLATE, "inputs": [],
             "suppressed": bad}]})
        assert d is not None, said
        assert d.get("a").suppressed is want, (bad, d.get("a").suppressed)
        assert d.to_data()["features"][0]["suppressed"] is want


def test_a_design_written_by_this_build_still_opens_byte_for_byte():
    """The other direction, which matters more: none of the above may refuse
    work that is correct. A full document round-trips unchanged."""
    d = Document(name="round-trip")
    d.set_parameter("wall", "3")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("b1", "extrude", {"amount": "wall*2"}, ["s1"])
    d.add("f1", "fillet", {"radius": 1, "edges": "all"}, ["b1"])
    d.get("f1").suppressed = True
    data = d.to_data()
    again = Document.from_data(data)
    assert again.to_data() == data
    assert again.rebuild() is True
    assert again.get("b1").volume == pytest.approx(471.24, abs=0.01)
