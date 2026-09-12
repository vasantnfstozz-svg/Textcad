"""tests/journeys.py — the random-journey runner (LAUNCH-PLAN.md P5b, §6 tier 4).

The runner is the machine playing the user overnight; these lock in that it
tells a leaked exception from a sentence, files one bug once with a working
repro, and plays only moves the product offers. The journeys here are SHORT
and SEEDED: a red row means the runner (or the product under it) changed,
never that the dice fell differently."""
import json
from pathlib import Path

import pytest

import journeys


# ------------------------------------------------------------- classifier ---

def test_a_leaked_exception_is_told_from_a_sentence():
    for leaked in ("KeyError: 'face'", "TypeError: unsupported operand",
                   "Standard_ConstructionError: BRep_API: command not done",
                   "OCP.Standard.Standard_Failure: kernel said no",
                   "Traceback (most recent call last):\n  File ..."):
        assert journeys.unhandled(leaked), leaked
    for sentence in ("the radius must be smaller than half the wall",
                     "cannot remove 'base_disc': used by ['base_disc_seat']",
                     "Extrude needs a sketch profile or a picked flat face",
                     "Error: none", "", None):
        assert not journeys.unhandled(sentence), sentence


def test_one_signature_per_failure_class_whatever_the_numbers():
    a = journeys.signature("green-but-unsound", "fillet",
                           "'j3_fillet' (fillet) is green but: non-positive volume (-12.5)")
    b = journeys.signature("green-but-unsound", "fillet",
                           "'j9_fillet' (fillet) is green but: non-positive volume (-3)")
    assert a == b
    assert a != journeys.signature("green-but-unsound", "chamfer", "x")


def test_sources_name_designs_without_the_tcad_suffix():
    names = dict(journeys.sources())
    assert {"empty", "pump-impeller", "esp32-remote"} <= set(names)
    assert names["pump-impeller"].name == "pump-impeller.tcad.json"
    with pytest.raises(SystemExit):
        journeys.sources(only=["no-such-design"])


def test_the_library_tier_can_collect():
    """`pytest -m library` could not even collect until tests/ became a
    package: pytest 9 refuses two rootless modules of one basename, and
    seven tool tests share theirs with tests/e2e/ (P5b)."""
    assert (Path(__file__).parent / "__init__.py").exists()


# ---------------------------------------------------------------- journeys ---

def test_a_short_journey_from_nothing_is_clean_and_stays_in_the_catalogue():
    import author
    ops = {e["op"] for e in author.op_catalog()}
    j = journeys.Journey("empty", None, seed=1, steps=15, verbose=False)
    out = j.run()
    assert out["result"] == "clean", str(out["bug"])
    adds = [s for s in j.steps if s["kind"] == "add"]
    assert adds and all(s["op"] in ops for s in adds), [s["op"] for s in adds]
    assert all(s["status"] in (200, 400) for s in j.steps)
    assert j.solids(), "fifteen moves from nothing left no body on screen"


def test_a_short_journey_on_a_fixture_is_clean():
    path = dict(journeys.sources())["pump-impeller"]
    j = journeys.Journey("pump-impeller", path, seed=3, steps=8, verbose=False)
    out = j.run()
    assert out["result"] == "clean", str(out["bug"])
    assert out["requests"] >= 8


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


class _Client:
    def __init__(self, resp):
        self.resp = resp

    def post(self, url, json=None):
        return self.resp

    def get(self, url):
        return self.resp


def test_a_leaked_exception_in_a_200_is_a_bug_and_a_plain_refusal_is_not():
    j = journeys.Journey("empty", None, seed=1, steps=0, verbose=False)
    j.run()
    j.client = _Client(_Resp(200, {"error": "KeyError: 'face'"}))
    with pytest.raises(journeys.Bug) as ex:
        j.call("add", "POST", "/api/feature/add", {"id": "x", "op": "plate"})
    assert ex.value.kind == "unhandled-error"
    j.client = _Client(_Resp(400, {"error": "the radius must be positive"}))
    j.call("add", "POST", "/api/feature/add", {"id": "x", "op": "plate"})   # no raise
    j.client = _Client(_Resp(500, {}))
    with pytest.raises(journeys.Bug) as ex:
        j.call("doc", "GET", "/api/doc")
    assert ex.value.kind == "http-status"


def test_a_refusal_that_changed_the_document_is_a_bug():
    j = journeys.Journey("empty", None, seed=1, steps=0, verbose=False)
    j.run()
    real = j.client

    class Sneaky:
        def post(self, url, json=None):
            real.post(url, json=json)             # the add lands ...
            return _Resp(400, {"error": "refused, honestly"})   # ... and is denied
    j.client = Sneaky()
    with pytest.raises(journeys.Bug) as ex:
        j.call("add", "POST", "/api/feature/add",
               {"id": "b1", "op": "plate", "params": {"width": 20, "depth": 10, "thickness": 4},
                "inputs": []})
    assert ex.value.kind == "refusal-changed-doc"


# ------------------------------------------------------------- bug folders ---

def test_a_bug_is_filed_once_with_a_working_repro(tmp_path):
    j = journeys.Journey("empty", None, seed=5, steps=0, verbose=False)
    j.run()
    j.call("add", "POST", "/api/feature/add",
           {"id": "b1", "op": "plate", "params": {"width": 20, "depth": 10, "thickness": 4},
            "inputs": []})
    before = j.data()
    bug = journeys.Bug("green-but-unsound", "'b1' (plate) is green but: non-positive volume (-1)",
                       j.steps[-1], {"error": None})
    folder, dup = journeys.write_bug(j, bug, before, j.data(), bugs_dir=tmp_path)
    assert folder is not None and dup is None
    names = {p.name for p in folder.iterdir()}
    assert {"journey.json", "before.tcad.json", "after.tcad.json", "report.md"} <= names
    rec = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    assert rec["request"]["url"] == "/api/feature/add"
    assert rec["failing_step"] == j.steps[-1]["n"] and rec["steps"]
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert "python tests/journeys.py --replay" in report and "/api/feature/add" in report
    # the same failure class again, other numbers: a repeat, not a second folder
    bug2 = journeys.Bug("green-but-unsound", "'b7' (plate) is green but: non-positive volume (-3.25)",
                        j.steps[-1], None)
    folder2, dup2 = journeys.write_bug(j, bug2, before, None, bugs_dir=tmp_path)
    assert folder2 is None and dup2 == folder.name
    # replay opens before.tcad.json in a fresh server and resends the step
    out = journeys.replay(folder, verbose=False)
    assert out["result"] == "clean"          # a plain plate IS sound; the bug above was staged
