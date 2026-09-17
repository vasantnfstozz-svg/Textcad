"""Named parameters (Tier 2, specs/named-parameters.md): the safe evaluator,
the document's parameter rules, cache invalidation by MEASURED volume, the
file format, the API.

Every string in INJECTION was run against the evaluator first
(probes/paramexpr_probe.py): none ran, none leaked a Python error.
"""
import glob
import json
import os

import pytest

import paramexpr as px
from document import Document

V = {"wall": 3.0, "base": 12.0}
INJECTION = ["__import__('os').system('dir')", "().__class__", "wall.__class__", "open('x')",
             "lambda: 1", "[1,2][0]", "{'a': 1}", "'abc'", "f'{wall}'", "wall if 1 else 2",
             "1 < 2", "1 and 2", "not 1", "10**10**10", "1e400", "1/0", "wall/0", "wal*2",
             "print(1)", "eval('1')", "exec('x=1')", "import os", "x = 1", "wall; 1", "1,2",
             "True", "None", "sqrt", "sqrt(-1)", "min()", "round(1, 2, 3)", "2 // 3", "7 % 2",
             "~1", "1 @ 2", "wall(2)", "a" * 300, "", "   ", "(-8) ** 0.5", "9e300 * 9e300",
             "2 ** 65", "1e12", "8mm", "3 mm", "wall*"]
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ------------------------------------------------- the evaluator ------------

@pytest.mark.parametrize("expr,value", [
    ("3", 3), ("2.5", 2.5), ("wall", 3), ("wall*2", 6), ("(wall+1)/2", 2), ("-wall", -3),
    ("base - wall*2", 6), ("2**3", 8), ("min(wall, base)", 3), ("max(1, wall) + abs(-2)", 5),
    ("round(wall/2)", 2), ("sqrt(16)", 4), ("sin(30)*2", 1), ("cos(60)", 0.5),
    ("floor(2.7) + ceil(2.1)", 5), ("1e3", 1000), ("wall ** 2", 9), (7, 7), (2.5, 2.5),
])
def test_the_evaluator_works_out_formulas(expr, value):
    assert px.evaluate(expr, V) == pytest.approx(value)


@pytest.mark.parametrize("expr", INJECTION)
def test_every_injection_is_a_sentence_and_never_runs(expr):
    with pytest.raises(ValueError) as e:
        px.evaluate(expr, V)
    assert "Traceback" not in str(e.value) and len(str(e.value)) > 10


def test_unknown_names_come_with_a_suggestion_and_division_by_zero_is_named():
    with pytest.raises(ValueError, match="no parameter named 'wal' — did you mean 'wall'"):
        px.evaluate("wal*2", V)
    with pytest.raises(ValueError, match="divides by zero"):
        px.evaluate("wall/(base-12)", V)


def test_names_in_and_rename_by_token():
    assert px.names_in("wall*2 + max(base, wall_2)") == ["wall", "base", "wall_2"]
    assert px.rename_in("wall*2 + wall_2 - (wall)", "wall", "thickness") == \
        "thickness*2 + wall_2 - (thickness)"
    assert px.rename_in("  wall  *2", "wall", "t") == "  t  *2", "spacing is kept"


@pytest.mark.parametrize("name,ok", [("wall", True), ("wall_2", True), ("_w", True),
                                     ("2x", False), ("a b", False), ("min", False),
                                     ("lambda", False), ("True", False), ("", False)])
def test_parameter_names(name, ok):
    assert (px.name_problem(name) is None) is ok


# ------------------------------------------------- the document -------------

def doc():
    d = Document(name="np")
    d.add("s", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 20, "h": 10, "mode": "add"}]}, [])
    d.set_parameter("wall", "3", "wall thickness")
    d.add("e", "extrude", {"amount": "wall*2"}, ["s"], strict=True)
    d.rebuild()
    return d


def test_a_formula_drives_a_feature_and_a_parameter_change_rebuilds_it():
    d = doc()
    assert d.get("e").status == "ok" and d.get("e").volume == pytest.approx(1200)
    d.set_parameter("wall", "4")
    d.rebuild()
    assert d.get("e").volume == pytest.approx(1600), "the cache followed the value"
    d.set_parameter("wall", "4")                       # no change: still 1600
    d.rebuild()
    assert d.get("e").volume == pytest.approx(1600)
    assert d.param_values == {"wall": 4.0} and d.param_problems == {}


def test_parameters_may_name_each_other_and_a_file_may_list_them_in_any_order():
    d = doc()
    d.set_parameter("lip", "1.5")
    d.set_parameter("depth", "wall * 2 + lip")
    assert d.param_values == {"wall": 3.0, "lip": 1.5, "depth": 7.5}
    data = d.to_data()
    # a file listing the user before the used: evaluated in dependency order
    data["parameters"] = {"depth": {"expr": "wall * 2 + lip"}, "lip": {"expr": "1.5"},
                          "wall": {"expr": "3"}}
    d2 = Document.from_data(data)
    assert d2.param_values == {"wall": 3.0, "lip": 1.5, "depth": 7.5} and d2.param_problems == {}


def test_a_parameter_naming_a_missing_one_is_refused_and_nothing_changes():
    d = doc()
    before = json.dumps(d.to_data(), sort_keys=True)
    with pytest.raises(ValueError, match="no parameter named 'lip'"):
        d.set_parameter("depth", "wall*2 + lip")
    assert json.dumps(d.to_data(), sort_keys=True) == before


def test_loops_self_reference_reserved_and_feature_names_are_refused():
    d = doc()
    d.set_parameter("a", "1")
    d.set_parameter("b", "a + 1")
    with pytest.raises(ValueError, match="loop of parameters"):
        d.set_parameter("a", "b + 1")
    assert d.param_values["a"] == 1 and d.param_values["b"] == 2, "put back as it was"
    with pytest.raises(ValueError, match="defined by itself"):
        d.set_parameter("c", "c + 1")
    with pytest.raises(ValueError, match="reserved word"):
        d.set_parameter("min", "1")
    with pytest.raises(ValueError, match="name of a feature"):
        d.set_parameter("e", "1")
    with pytest.raises(ValueError, match="name of a parameter"):
        d.add("wall", "plate", {"width": 1, "depth": 1, "thickness": 1}, [])
    with pytest.raises(ValueError, match="name of a parameter"):
        d.rename("e", "wall")


def test_rename_rewrites_every_formula_by_token_and_delete_is_refused_while_used():
    d = doc()
    d.set_parameter("wall_2", "wall + 1")
    d.rename_parameter("wall", "thickness")
    assert d.get("e").params["amount"] == "thickness*2"
    assert d.parameters["wall_2"]["expr"] == "thickness + 1", "wall_2 itself untouched"
    assert "wall" not in d.parameters and d.parameters["thickness"]["comment"] == "wall thickness"
    d.rebuild()
    assert d.get("e").status == "ok" and d.get("e").volume == pytest.approx(1200)
    with pytest.raises(ValueError, match="used by feature 'e', parameter 'wall_2'"):
        d.remove_parameter("thickness")
    d.remove_parameter("wall_2")
    assert d.parameter_users("thickness") == {"features": ["e"], "parameters": []}
    d.edit_many("e", {"amount": 6})
    d.remove_parameter("thickness")
    assert d.parameters == {}


def test_bad_formulas_in_a_feature_are_refused_at_the_door_with_the_sentence():
    d = doc()
    with pytest.raises(ValueError, match="no parameter named 'wal' — did you mean 'wall'"):
        d.edit_many("e", {"amount": "wal*2"})
    with pytest.raises(ValueError, match="must be a number .* without units"):
        d.edit_many("e", {"amount": "8mm"})            # no formula: the old sentence stands
    # an injection is no formula at all, so it never enters the evaluator:
    # the plain "must be a number" sentence, nothing about functions
    with pytest.raises(ValueError, match="must be a number"):
        d.add("e2", "extrude", {"amount": "__import__('os')"}, ["s"], strict=True)
    with pytest.raises(ValueError, match="not allowed"):
        d.set_parameter("x", "__import__('os')")
    assert d.get("e").params["amount"] == "wall*2", "nothing half-applied"
    # a word that is NOT a numeric param stays a word
    d.add("b", "plate", {"width": 30, "depth": 20, "thickness": 5}, [])
    d.add("f", "fillet", {"radius": "wall/3", "edges": "vertical"}, ["b"], strict=True)
    d.rebuild()
    assert d.get("f").status == "ok", d.get("f").problems


def test_resolved_and_parameters_json_carry_what_the_tree_shows():
    d = doc()
    assert d.resolved_json(d.get("e")) == {"amount": 6.0}
    assert d.resolved_json(d.get("s")) == {}
    [p] = d.parameters_json()
    assert p == {"name": "wall", "expr": "3", "value": 3.0, "comment": "wall thickness",
                 "users": ["e"], "used_by_parameters": [], "problem": None}


# ------------------------------------------------- the file -----------------

def test_to_data_carries_parameters_only_when_there_are_some():
    d = Document(name="plain")
    d.add("b", "plate", {"width": 30, "depth": 20, "thickness": 5}, [])
    assert "parameters" not in d.to_data()
    d2 = doc()
    data = d2.to_data()
    assert data["parameters"] == {"wall": {"expr": "3", "comment": "wall thickness"}}
    d3 = Document.from_data(json.loads(json.dumps(data)))
    d3.rebuild()
    assert d3.get("e").volume == pytest.approx(1200) and d3.param_values == {"wall": 3.0}


def test_every_fixture_design_round_trips_byte_for_byte():
    files = glob.glob(os.path.join(FIXTURES, "*.tcad.json"))
    assert files
    for path in files:
        raw = json.load(open(path, encoding="utf-8"))
        out = Document.from_data(raw).to_data()
        assert "parameters" not in out, path
        want = {"name": raw["name"], "spec": raw.get("spec", {}), "features": raw["features"]}
        assert json.dumps(out, sort_keys=True) == json.dumps(
            {**want, "features": [{k: f.get(k, False if k == "suppressed" else None)
                                   for k in ("id", "op", "params", "inputs", "suppressed")}
                                  for f in raw["features"]]}, sort_keys=True), path


def test_a_file_whose_parameter_is_gone_or_looped_still_opens_red():
    data = doc().to_data()
    del data["parameters"]["wall"]
    d = Document.from_data(data)
    d.rebuild()
    assert d.get("e").status == "failed"
    assert "no parameter named 'wall'" in d.get("e").problems[0]
    looped = doc().to_data()
    looped["parameters"] = {"a": {"expr": "b"}, "b": {"expr": "a"}, "wall": {"expr": "3"}}
    d = Document.from_data(looped)
    assert "loop" in d.param_problems["a"] and d.param_values == {"wall": 3.0}
    d.rebuild()
    assert d.get("e").status == "ok"


# ------------------------------------------------- the API ------------------

def test_the_api_sets_renames_and_removes_with_sentences():
    from fastapi.testclient import TestClient

    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(Document(name="api"))
    with TestClient(studio.app) as c:
        c.post("/api/feature/add", json={"id": "s", "op": "sketch", "params": {
            "plane": "XY", "entities": [{"kind": "circle", "r": 5, "mode": "add"}]}, "inputs": []})
        r = c.post("/api/parameters", json={"name": "wall", "expr": "3", "comment": "t"}).json()
        assert r["parameters"] == [{"name": "wall", "expr": "3", "value": 3.0, "comment": "t",
                                    "users": [], "used_by_parameters": [], "problem": None}]
        c.post("/api/feature/add", json={"id": "e", "op": "extrude", "params": {"amount": "wall*2"},
                                         "inputs": ["s"]})
        r = c.post("/api/edit", json={"feature_id": "e", "param": "amount", "value": "wall*3"}).json()
        e = next(f for f in r["features"] if f["id"] == "e")
        assert e["params"]["amount"] == "wall*3" and e["resolved"] == {"amount": 9.0}
        assert e["volume"] == pytest.approx(3.141592653589793 * 25 * 9, rel=1e-4)
        bad = c.post("/api/parameters", json={"name": "wall", "expr": "wall+1"})
        assert bad.status_code == 400 and "defined by itself" in bad.json()["error"]
        r = c.post("/api/parameters/rename", json={"old": "wall", "new": "t"}).json()
        assert next(f for f in r["features"] if f["id"] == "e")["params"]["amount"] == "t*3"
        bad = c.post("/api/parameters/remove", json={"name": "t"})
        assert bad.status_code == 400 and "used by feature 'e'" in bad.json()["error"]
