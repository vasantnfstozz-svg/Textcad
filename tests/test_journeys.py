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


def test_every_exception_class_the_app_can_raise_is_recognised():
    """_never_die writes f"{type(e).__name__}: {e}", so the classifier has to
    know the class NAMES, and it only knew the ones ending in
    Error/Exception/Failure/Fault plus Standard_*. OpenCASCADE has a SECOND
    family — a leaked `StdFail_NotDone: BRep_API: command not done`, the
    commonest kernel exception there is, read as the product working — and
    several builtins carry no suffix at all (P5b review, 2026-09-12)."""
    import builtins
    names = []
    for mod in ("Standard", "StdFail"):
        try:
            m = __import__(f"OCP.{mod}", fromlist=["*"])
        except ImportError:                          # pragma: no cover
            continue
        names += [n for n in dir(m) if n.startswith(f"{mod}_")
                  and isinstance(getattr(m, n), type)
                  and issubclass(getattr(m, n), BaseException)]
    assert any(n == "StdFail_NotDone" for n in names), "OCP shape changed"
    names += [n for n, o in vars(builtins).items()
              if isinstance(o, type) and issubclass(o, BaseException)
              and not issubclass(o, Warning)]
    missed = [n for n in names if not journeys.unhandled(f"{n}: something")]
    assert not missed, f"a leak of these would read as the product working: {missed}"


def test_a_real_leak_through_the_barrier_is_a_bug(monkeypatch):
    """End to end: make a route raise the OCCT exception the classifier used
    to miss, and let _never_die word it. The journey must stop."""
    from OCP.StdFail import StdFail_NotDone

    import document
    j = journeys.Journey("empty", None, seed=1, steps=0, verbose=False)
    j.run()

    def boom(self, *a, **k):
        raise StdFail_NotDone("BRep_API: command not done")
    monkeypatch.setattr(document.Document, "rebuild", boom)
    with pytest.raises(journeys.Bug) as ex:
        j.call("add", "POST", "/api/feature/add",
               {"id": "leak", "op": "plate",
                "params": {"width": 20, "depth": 10, "thickness": 4}, "inputs": []})
    assert ex.value.kind == "unhandled-error"
    assert "StdFail_NotDone" in ex.value.detail


def test_one_signature_per_failure_class_whatever_the_numbers():
    a = journeys.signature("green-but-unsound", "fillet",
                           "'j3_fillet' (fillet) is green but: non-positive volume (-12.5)")
    b = journeys.signature("green-but-unsound", "fillet",
                           "'j9_fillet' (fillet) is green but: non-positive volume (-3)")
    assert a == b
    assert a != journeys.signature("green-but-unsound", "chamfer", "x")


def test_a_dry_run_that_changed_the_document_is_a_bug():
    """A dry run is a question, answered before anything is snapshotted — one
    that wrote would be a change with no undo step behind it. The move sends it
    with mutating=True and nothing compared the document across it (P5b
    review)."""
    import document
    j = journeys.Journey("empty", None, seed=1, steps=0, verbose=False)
    j.run()
    j.call("add", "POST", "/api/feature/add",
           {"id": "b1", "op": "plate",
            "params": {"width": 20, "depth": 10, "thickness": 4}, "inputs": []})
    j.call("add", "POST", "/api/feature/add",
           {"id": "b2", "op": "disc", "params": {"radius": 8, "thickness": 3},
            "inputs": []})
    orig = document.Document.remove_plan

    def sneaky(self, fid, mode="auto"):
        plan = orig(self, fid, mode)
        self.features[0].params["width"] = 999.0
        return plan
    document.Document.remove_plan = sneaky
    try:
        with pytest.raises(journeys.Bug) as ex:
            j.call("remove-plan", "POST", "/api/feature/remove",
                   {"feature_id": "b2", "mode": "auto", "dry_run": True})
    finally:
        document.Document.remove_plan = orig
    assert ex.value.kind == "dry-run-changed-doc"


def test_the_runner_never_touches_the_repo_s_own_viewport_mesh():
    """/api/new and a remove that empties the design DELETE ROOT/_studio_mesh.stl.
    The user's Studio is open on this checkout while the runner plays overnight
    (P5b review), so the runner gets its own."""
    studio, _client = journeys.make_client()
    assert Path(studio.MESH_PATH).parent != journeys.ROOT


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


def test_a_pair_move_files_a_repro_that_actually_reproduces(tmp_path):
    """Half the oracles judge a PAIR of requests (strike + restore, rollback +
    release, edit + undo) against the document from before the FIRST of them.
    The folder kept the document from before the LAST one and resent only that
    one, so a live, 100%-deterministic finding replayed as "the step passes
    now" every time (P5b review, 2026-09-12)."""
    import document
    j = journeys.Journey("empty", None, seed=11, steps=0, verbose=False)
    j.run()
    j.call("add", "POST", "/api/feature/add",
           {"id": "b1", "op": "plate",
            "params": {"width": 20, "depth": 10, "thickness": 4}, "inputs": []})
    j.call("add", "POST", "/api/feature/add",
           {"id": "r1", "op": "fillet", "params": {"radius": 1, "edges": "all"},
            "inputs": ["b1"]})
    orig = document.Document.unstrike

    def leaky(self, fid):                 # a restore that puts back too much
        plan = orig(self, fid)
        self.features[0].params["width"] = 21.0
        self._mark_stale()
        return plan
    document.Document.unstrike = leaky
    try:
        with pytest.raises(journeys.Bug) as ex:
            j.move_strike_restore()
        bug = ex.value
        assert bug.kind.startswith("strike-restore")
        folder, dup = journeys.write_bug(j, bug, bug.before, j.data(), bugs_dir=tmp_path)
        assert folder is not None and dup is None
        rec = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
        assert len(rec["replay"]) == 2 and rec["identity"] is True
        report = (folder / "report.md").read_text(encoding="utf-8")
        assert "2 steps that broke it" in report
        out = journeys.replay(folder, verbose=False)
        assert out["result"] == "bug", "the folder's own --replay said it passes now"
    finally:
        document.Document.unstrike = orig


def test_a_finding_made_on_OPEN_leaves_a_folder_that_replays(tmp_path, monkeypatch):
    """"This saved design is already broken" is the cheapest finding there is,
    and it is made before any request — so there was no `before` document and
    the folder's own --replay line exited with "holds no before.tcad.json"
    (P5b review). The document IS there, under the name after.tcad.json."""
    import inspector
    real_health, real_check = inspector.health, journeys.Journey.check_bodies
    inside = []

    def check(self, rec, resp):
        inside.append(1)                  # health is the app's own during rebuild
        try:
            return real_check(self, rec, resp)
        finally:
            inside.pop()
    monkeypatch.setattr(journeys.Journey, "check_bodies", check)
    monkeypatch.setattr(inspector, "health",
                        lambda p, **k: (["staged: not watertight"] if inside
                                        else real_health(p, **k)))
    src = tmp_path / "tiny.tcad.json"
    src.write_text(json.dumps({"name": "tiny", "spec": {}, "features": [
        {"id": "b", "op": "plate",
         "params": {"width": 20, "depth": 10, "thickness": 4},
         "inputs": [], "suppressed": False}]}), encoding="utf-8")

    out = journeys.run_one("tiny", src, seed=1, steps=0, log_path=None,
                           bugs_dir=tmp_path / "bugs", verbose=False)
    assert out["exit"] == journeys.EXIT_BUG, out
    folder = Path(out["folder"])
    assert not (folder / "before.tcad.json").exists()
    assert (folder / "after.tcad.json").exists()
    assert journeys.replay(folder, verbose=False)["result"] == "bug"


# --------------------------------------------------------------- crash folders ---

def test_the_machine_running_out_is_not_a_finding(tmp_path):
    """Measured 2026-09-12: a 20-journey run beside a full pytest run put the
    box out of memory and two children died — one with a stack overflow
    mid-`ball`, one with a MemoryError importing sklearn through build123d.
    Both were filed as "the server process died" and the console evidence,
    which said MemoryError in as many words, was kept nowhere."""
    steps = {"steps": [{"n": 1, "kind": "add", "op": "ball",
                        "method": "POST", "url": "/api/feature/add", "body": {}}]}
    oom = ("Traceback (most recent call last):\n  ...\nMemoryError\n"
           "OpenBLAS error: Memory allocation still failed after 10 retries, giving up.\n")
    folder, dup = journeys.write_crash("bit-tray", 9001, 3221225725, dict(steps),
                                       oom, tmp_path)
    assert folder is None and dup is None, "an out-of-memory child filed a folder"
    assert not list(tmp_path.glob("*crash"))

    # a real kernel segfault still files one, and says what the child said
    folder, dup = journeys.write_crash("bit-tray", 9001, 0xC0000005, dict(steps),
                                       "Windows fatal exception: access violation\n", tmp_path)
    assert folder is not None and dup is None
    assert (folder / "child-output.txt").exists()
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert "access violation" in report and "--designs bit-tray --seed 9001" in report
    rec = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    assert rec["kind"] == "process-died" and rec["replay"] == []
