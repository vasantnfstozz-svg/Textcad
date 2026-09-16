"""REVIEW-QUEUE.md section 12 — the server layer, reviewed 2026-09-16.

Everything here was measured first (probes/server_layer_review_probe*.py) and
was RED before the fix:

* F1/F7 (P1) — /api/export built its file name from the RAW design name while
  /api/save and mcp_server._safe_name both slugify it, and it had none of
  save's three collision doors. Measured: designs/_probe-collide.step held a
  68455.304 mm3 flange; a SECOND, different design carrying the same name
  (whose save was refused) exported straight over it and the file came back
  200.0 mm3, with "⬇ Exported: …" and no warning. That is the 2026-08-31 CAM
  class of bug — the .step on disk is not the design you think it is.
* F2 (P1) — the session checkpoint restored only the FIRST MAX_TABS tabs, and
  /api/open has no tab cap, so the tab you were looking at was the one thrown
  away. Measured: 13 tabs, the 13th active and holding unsaved work, restart,
  12 came back and the unsaved one was gone with no prompt.
* F3 (P1) — /api/spec filtered the KEY set and nothing else. Measured:
  {"volume": "50"} answered 200 with "TypeError: unsupported operand type(s)
  for -: 'float' and 'str'", stayed in the document, made EVERY later
  /api/edit raise the same TypeError, and was written into the design file.
* F4 (P2) — /api/export made four OCCT calls (rebuild, export_step, rebuild,
  measure) with _KERNEL_LOCK held on none of them, while an AI "create" job
  in another tab is free to be in the kernel at the same time.
* F5/F6 (P2) — refusals answered 200, against _refused's own contract.
"""
import json
import threading

import pytest
from fastapi.testclient import TestClient

import inspector
import studio
from document import Document

TMP = "_test-server-layer"


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    yield TestClient(studio.app)
    for p in list(studio.DESIGNS.glob("_test-server-layer*")):
        p.unlink(missing_ok=True)
    for p in list(studio.DESIGNS.glob("_test-tabs-*")):
        p.unlink(missing_ok=True)
    # designs/ is the user's own work: the sample-export test below writes
    # flange-100.step into it, and round one left it there (measured, round
    # two). test_export_guard.py's fixture removes the same file for the same
    # reason — "keep the library clean".
    (studio.DESIGNS / "flange-100.step").unlink(missing_ok=True)


def _library_design(name: str, thickness: float = 5) -> Document:
    """A minimal saveable design, so a test can give a FILE and the NAME
    inside it different spellings — which is what four of the user's 50
    designs actually do."""
    d = Document(name=name)
    d.add("base", "plate",
          {"width": 20, "depth": 20, "thickness": thickness}, [])
    return d


# --------------------------------------------------------------- F1 / F7 ---

def test_export_uses_the_same_file_name_as_save(client):
    """A design has ONE name on disk. The export used the raw doc.name, so a
    design called "cam cover plaque" saved as cam-cover-plaque.tcad.json and
    exported as "cam cover plaque.step" — while the MCP, exporting the same
    design, wrote cam-cover-plaque.step. Two .step files, quietly diverging."""
    studio._doc().name = TMP + " with spaces"
    saved = client.post("/api/save").json()["saved"]
    exported = client.post("/api/export").json()["path"]
    assert exported.endswith(f"{saved}.step"), \
        f"saved as {saved}.tcad.json but exported as {exported}"


def test_export_refuses_to_overwrite_another_designs_step(client):
    """/api/save refuses to write over a design it does not own; the export
    wrote over that design's STEP file without a word."""
    studio._doc().name = TMP
    assert client.post("/api/save").json()["saved"] == TMP
    first = client.post("/api/export").json()
    assert first["volume"] > 1000, first          # the flange

    # a SECOND, different design carrying the same name (save refuses this)
    client.post("/api/new", json={"name": TMP})
    client.post("/api/feature/add", json={
        "id": "slab", "op": "plate",
        "params": {"width": 10, "depth": 10, "thickness": 2}, "inputs": []})
    assert client.post("/api/save").json().get("error")

    r = client.post("/api/export")
    assert r.status_code == 400, "the export overwrote another design's STEP"
    assert TMP in r.json()["error"]
    # and the file on disk is still the first design's
    now = inspector.measure(first["path"])
    assert abs(now["volume"] - first["volume"]) < 1e-6, \
        "the other design's .step was replaced"


def test_export_refuses_even_when_the_other_design_is_closed(client):
    """The second door: the design whose .step this is need not still be open
    — the file on disk is what is at stake."""
    studio._doc().name = TMP
    client.post("/api/save")
    first = client.post("/api/export").json()
    assert not first.get("error")
    client.post("/api/tabs/close", json={"id": studio.STATE["active"]})

    client.post("/api/new", json={"name": TMP})
    client.post("/api/feature/add", json={
        "id": "slab", "op": "plate",
        "params": {"width": 10, "depth": 10, "thickness": 2}, "inputs": []})
    r = client.post("/api/export")
    assert r.status_code == 400, "a closed design's .step was overwritten"
    now = inspector.measure(first["path"])
    assert abs(now["volume"] - first["volume"]) < 1e-6


def test_a_design_can_still_export_over_its_own_step(client):
    """The guard must not block the everyday case: export, edit, export."""
    studio._doc().name = TMP
    client.post("/api/save")
    assert not client.post("/api/export").json().get("error")
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    r = client.post("/api/export").json()
    assert not r.get("error") and r["path"].endswith(f"{TMP}.step")


# ------------------------------------------------- round two, F1 of F1/F7 ---
# Round one keyed the export file (and its new clash guard) off doc.NAME. A
# design opened from the library is bound to its FILE, and the two can differ:
# measured over the user's own 50 designs (probes/section12_round2_export_probe
# .py), FOUR carry a name that does not slug to their own stem —
# designs/esp32-remote-live-t2.tcad.json and -t3 are both named "esp32-remote",
# designs/bottle_cap_28mm.tcad.json is named "bottle-cap-28mm",
# designs/water_bottle_750ml.tcad.json is named "water-bottle-750ml".

def test_a_library_design_can_still_be_exported(client):
    """Open from the library, press Export. Measured 2026-09-16: on the two
    esp32-remote-live-t* designs round one's guard REFUSED it outright —
    "there is already a different design called 'esp32-remote'" — because the
    export asked about the NAME instead of the file this tab is bound to."""
    _library_design(TMP).save(str(studio.DESIGNS / f"{TMP}.tcad.json"))
    _library_design(TMP, thickness=9).save(
        str(studio.DESIGNS / f"{TMP}-v2.tcad.json"))    # its NAME is the other
    assert not client.post(f"/api/open/{TMP}-v2").json().get("error")

    r = client.post("/api/export")
    assert r.status_code == 200, \
        f"a design opened from the library cannot export: {r.json()['error']}"
    assert r.json()["path"].endswith(f"{TMP}-v2.step")


def test_the_export_lands_beside_the_designs_own_file(client):
    """One design, ONE .step, beside its own .tcad.json — the twin-file trap
    the export exists to avoid. designs/bottle_cap_28mm.tcad.json is named
    "bottle-cap-28mm", so round one exported it as bottle-cap-28mm.step: a
    .step whose name matches no design file in the library."""
    stem = f"{TMP}_underscored"
    _library_design(f"{TMP}-underscored").save(
        str(studio.DESIGNS / f"{stem}.tcad.json"))
    client.post(f"/api/open/{stem}")
    r = client.post("/api/export").json()
    assert not r.get("error"), r["error"]
    assert r["path"].endswith(f"{stem}.step"), \
        f"designs/{stem}.tcad.json exported as {r['path']}"


def test_the_export_guard_reads_the_filesystems_own_case_rule(client):
    """Section 3 of this queue found a P0 where a slug collision on a
    case-INSENSITIVE filesystem let one design overwrite another's file
    ("Cam Cover Plaque" onto cam-cover-plaque). designs/X.step and
    designs/x.step are one file on this machine, so the export's clash guard
    has to catch the other spelling too — measured here rather than assumed."""
    _library_design(TMP).save(str(studio.DESIGNS / f"{TMP}.tcad.json"))
    client.post("/api/new", json={"name": TMP.upper()})    # unbound, different
    client.post("/api/feature/add", json={
        "id": "slab", "op": "plate",
        "params": {"width": 10, "depth": 10, "thickness": 2}, "inputs": []})
    r = client.post("/api/export")
    if (studio.DESIGNS / f"{TMP.upper()}.tcad.json").exists():
        assert r.status_code == 400, \
            f"'{TMP.upper()}' exported over designs/{TMP}.step"
    else:                          # a case-SENSITIVE filesystem: two designs
        assert r.status_code == 200


# -------------------------------------------------------------- F5 / F4 ---

def test_an_export_refusal_answers_400(client):
    """_refused: 'a route that answers a refusal with 200 is telling a script
    the opposite of what happened'."""
    doc = studio._doc()
    doc.name = TMP
    doc.add("broken", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    doc.features[-1].status = "failed"
    doc.features[-1].problems = ["deliberately broken for the test"]
    doc._parts["broken"] = None
    r = client.post("/api/export")
    assert r.status_code == 400
    assert "did not build" in r.json()["error"]


def test_export_touches_the_kernel_under_the_kernel_lock(client):
    """OCCT is not thread-safe and an AI 'create' job runs in its own thread
    in its own tab, where the one-writer middleware does not see it."""
    seen = []
    real_step, real_measure = studio.b3d.export_step, studio.inspector.measure
    real_rebuild = Document.rebuild

    def spy_step(shape, path, *a, **k):
        seen.append(("export_step", studio._KERNEL_LOCK._is_owned()))
        return real_step(shape, path, *a, **k)

    def spy_measure(x, *a, **k):
        seen.append(("measure", studio._KERNEL_LOCK._is_owned()))
        return real_measure(x, *a, **k)

    def spy_rebuild(self, *a, **k):
        seen.append(("rebuild", studio._KERNEL_LOCK._is_owned()))
        return real_rebuild(self, *a, **k)

    studio._doc().name = TMP
    studio._doc().rollback = studio._doc().features[-1].id   # an editor is open
    studio.b3d.export_step = spy_step
    studio.inspector.measure = spy_measure
    Document.rebuild = spy_rebuild
    try:
        client.post("/api/export")
    finally:
        studio.b3d.export_step = real_step
        studio.inspector.measure = real_measure
        Document.rebuild = real_rebuild
    assert seen, "the export made no kernel call at all"
    assert all(held for _, held in seen), \
        f"kernel calls made outside the lock: {seen}"


def test_the_export_lock_cannot_deadlock_and_is_always_given_back(client):
    """Round two. Holding a lock across a whole endpoint is how a race becomes
    a HANG WITH NO MESSAGE, which is worse than the race. Two things make it
    safe and both are measured here: the lock is RE-ENTRANT (to_step rebuilds
    twice inside the with-block, on this very thread), and a `with` gives it
    back on the failure path too."""
    # re-entrant: a plain Lock would block on the second acquire
    assert studio._KERNEL_LOCK.acquire(blocking=False)
    assert studio._KERNEL_LOCK.acquire(blocking=False), \
        "_KERNEL_LOCK is not re-entrant: a rebuild inside to_step self-locks"
    studio._KERNEL_LOCK.release()
    studio._KERNEL_LOCK.release()

    doc = studio._doc()
    doc.name = TMP
    doc.add("broken", "plate",
            {"width": 20, "depth": 20, "thickness": 5}, [])
    doc.features[-1].status = "failed"
    doc.features[-1].problems = ["deliberately broken for the test"]
    doc._parts["broken"] = None
    assert client.post("/api/export").status_code == 400

    free = []                    # an RLock is released by its OWNER, so ask
    def grab():                  # noqa: E306 - the thread is the measurement
        ok = studio._KERNEL_LOCK.acquire(timeout=5)
        free.append(ok)
        if ok:
            studio._KERNEL_LOCK.release()
    t = threading.Thread(target=grab)
    t.start()
    t.join(10)
    assert free == [True], \
        "a refused export kept the kernel lock: every later rebuild would hang"


# ---------------------------------------------------------------------- F2 ---

def test_every_open_tab_comes_back_after_a_restart(client, tmp_path):
    """The user mandate the session file exists for: 'all other designs that I
    am working on close and vanish, do not do that'. /api/open has no tab cap,
    so a session can hold more than MAX_TABS — and the checkpoint used to keep
    the FIRST MAX_TABS, i.e. throw away the tab you were looking at."""
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    n = studio.MAX_TABS + 1
    for i in range(n):
        d = studio.sample_flange()
        d.name = f"_test-tabs-{i}"
        d.save(str(studio.DESIGNS / f"_test-tabs-{i}.tcad.json"))
        client.post(f"/api/open/_test-tabs-{i}")
    assert len(studio.STATE["docs"]) == n
    # the newest tab is the one being worked in, and it has unsaved work
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 7})
    active_name = studio._doc().name
    assert active_name == f"_test-tabs-{n - 1}"

    old = studio.SESSION_PATH
    studio.SESSION_PATH = tmp_path / "session.json"
    try:
        studio._persist_session()
        studio.STATE["docs"].clear()
        studio.STATE["active"] = None
        back = studio._restore_session(rebuild=False)
    finally:
        studio.SESSION_PATH = old
    names = [e["doc"].name for e in studio.STATE["docs"].values()]
    assert back == n, f"{n} tabs were open, {back} came back"
    assert active_name in names, \
        f"the tab being worked in vanished on restart: {names}"


# ---------------------------------------------------------------------- F3 ---

@pytest.mark.parametrize("spec, word", [
    ({"volume": "50"}, "volume"),
    ({"volume": [1, 2]}, "volume"),
    ({"tol": "loose"}, "tol"),
    ({"n_solids": 1.5}, "n_solids"),
    ({"size": 5}, "size"),
    ({"size": [10, 10]}, "size"),
    ({"size": ["a", None, None]}, "size"),
    ({"holes": [4, 6]}, "holes"),
    ({"holes": 6}, "holes"),
    ({"holes": {"4": "six"}}, "holes"),
    ({"com": {"x": 1}}, "com"),
    ({"require_manifold": "yes"}, "require_manifold"),
])
def test_spec_refuses_a_value_of_the_wrong_type(client, spec, word):
    before = dict(studio._doc().spec or {})
    r = client.post("/api/spec", json={"spec": spec})
    assert r.status_code == 400, f"{spec} was accepted"
    assert word in r.json()["error"]
    assert studio._doc().spec == before, "the bad value was kept anyway"


def test_a_refused_spec_leaves_the_design_editable(client):
    """Measured before the fix: {"volume": "50"} stayed in the document, so
    EVERY later /api/edit answered 'TypeError: unsupported operand type(s)
    for -: float and str' — and /api/save wrote it into the design file."""
    client.post("/api/spec", json={"spec": {"volume": "50"}})
    r = client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": 9})
    assert r.status_code == 200 and "error" not in r.json()
    studio._doc().name = TMP
    client.post("/api/save")
    on_disk = json.loads((studio.DESIGNS / f"{TMP}.tcad.json")
                         .read_text(encoding="utf-8"))
    assert "volume" not in (on_disk.get("spec") or {}), on_disk.get("spec")


@pytest.mark.parametrize("spec", [
    {"volume": 10 ** 400},               # a JSON integer no float can hold
    {"tol": 10 ** 400},
    {"size": [10 ** 400, None, None]},
    {"holes": {"4": 10 ** 400}},
    {"holes": {str(10 ** 400): 2}},
])
def test_spec_refuses_a_number_the_verifier_cannot_use(client, spec):
    """Round two of this review. _spec_problem asks what TYPE the value is and
    never whether the number can be used: 10**400 is an int, so it walked
    straight through the guard written to stop exactly this. Measured
    2026-09-16 — /api/spec answered 200 with "OverflowError: int too large to
    convert to float", the value STAYED in the document, and every later
    /api/edit answered with the same OverflowError. That is F3's own brick,
    through a shape F3's guard admits."""
    before = dict(studio._doc().spec or {})
    r = client.post("/api/spec", json={"spec": spec})
    assert r.status_code == 400, f"{list(spec)} was accepted"
    assert studio._doc().spec == before, "the unusable value was kept anyway"
    e = client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": 9})
    assert e.status_code == 200 and "error" not in e.json(), \
        f"the design was bricked: {e.json().get('error')}"


def test_spec_still_takes_everything_the_dialog_sends(client):
    """The Spec dialog (dialogs.js:394-404) sends null for an empty box, a
    3-list with nulls for a partly-filled size, and raw JSON with STRING keys
    for holes. None of that may be refused."""
    d = client.post("/api/spec", json={"spec": {
        "n_solids": 1, "symmetry": None, "tip_radius": None, "tol": 0.5,
        "size": [100, None, None], "holes": {"4": 6}}}).json()
    assert "error" not in d
    assert d["spec"]["size"] == [100, None, None]
    assert d["spec_checked"] and d["ok"] is not None
    # and a wrong one is still caught, not silently passed
    d = client.post("/api/spec", json={"spec": {
        "size": [999, None, None]}}).json()
    assert d["ok"] is False and "X dimension" in d["spec_problems"][0]


# ---------------------------------------------------------------------- F6 ---

def test_refusals_of_this_layer_answer_400(client):
    assert client.post("/api/sample/nope").status_code == 400
    assert client.post("/api/tabs/switch",
                       json={"id": "t999"}).status_code == 400
    assert client.post("/api/tabs/close",
                       json={"id": "t999"}).status_code == 400
    for i in range(studio.MAX_TABS):
        client.post("/api/new", json={"name": f"x{i}"})
    r = client.post("/api/new", json={"name": "one too many"})
    assert r.status_code == 400 and "too many open tabs" in r.json()["error"]


def test_a_known_sample_and_a_real_tab_still_answer_200(client):
    assert client.post("/api/sample/flange").status_code == 200
    tid = studio.STATE["active"]
    assert client.post("/api/tabs/switch", json={"id": tid}).status_code == 200


def test_an_untouched_sample_can_still_be_exported(client):
    """The clash guard's content escape, the one save already has: a sample
    tab whose content IS the library file's may write beside it. (Once it has
    been EDITED it is a different design, and it is told so — the same answer
    /api/save gives.)"""
    lib = studio.DESIGNS / "flange-100.tcad.json"
    if not lib.exists():
        pytest.skip("designs/flange-100.tcad.json is not in this library")
    r = client.post("/api/sample/flange")
    assert r.status_code == 200
    assert not client.post("/api/export").json().get("error")
