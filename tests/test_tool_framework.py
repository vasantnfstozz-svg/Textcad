"""Section 11 — the tool framework core (REVIEW-QUEUE.md).

The framework every tool stands on: the one selection resolver, the one-command
-at-a-time lock, the plan request path and the dialogs. A bug here is seven
tools' bug, so each of these pins a failure the review of 2026-09-16 measured.

The JS half is pinned by reading the source, the way `test_launch_rules.py`
pins R1/R3: there is no browser in the fast tier, and the invariants here are
about ORDER and about which call sits behind which guard.
"""
import math
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sketch as sk
import studio
import toolplan
from document import Document

JS = Path(__file__).resolve().parents[1] / "static" / "js"


def _src(name):
    return (JS / name).read_text(encoding="utf-8")


def _slice(src, start, end):
    a = src.index(start)
    return src[a:src.index(end, a)]


def _block(src, start):
    """The { … } block that follows `start`, brace-matched (the message strings
    in these handlers carry braces of their own, so a first-`}` slice lies)."""
    i = src.index("{", src.index(start))
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise AssertionError(f"unbalanced block after {start!r}")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TEXTCAD_HISTORY_ROOT", str(tmp_path))
    return TestClient(studio.app)


def build(*feats):
    d = Document(name="t")
    for fid, op, params, inputs in feats:
        d.add(fid, op, params, inputs)
    d.rebuild()
    return d


# ---------------------------------------------------------------------------
# F1 — ONE COMMAND AT A TIME reaches the document tab bar
# ---------------------------------------------------------------------------

def test_the_document_tab_bar_refuses_while_a_tool_panel_is_open():
    """An open tool panel remembers its feature by ID only — it never listens
    for 'doc-updated' — and every write it makes is addressed to the ACTIVE
    tab. So a tab click under an open panel used to send that panel's next
    write into the OTHER design (see the test below for the damage). The
    ribbon already refuses every File action this way; the tab bar must too."""
    src = _src("doctabs.js")
    assert "modalGuard" in src, "doctabs.js does not know about the modal lock"
    body = src[src.index("export function renderDocTabs"):]
    handlers = [ln.strip() for ln in body.splitlines()
                if re.match(r"^\s*(x|el|plus)\.onclick\s*=", ln)]
    assert len(handlers) == 3, handlers
    for ln in handlers:
        assert "modalGuard" in ln or "guarded(" in ln, \
            f"tab-bar handler runs with no modal guard: {ln}"


def test_a_panels_write_after_a_tab_switch_lands_on_the_other_design(client):
    """The damage the guard above exists to stop, measured end to end.
    `uid()` hands out the same names in every design, so two designs normally
    both hold an `extrude1`; the panel's next /api/feature/params writes into
    whichever tab is active, not the one the panel was opened on."""
    def make(name, amount):
        client.post("/api/new", json={"name": name})
        client.post("/api/feature/add", json={
            "id": "b", "op": "plate",
            "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
        client.post("/api/feature/add", json={
            "id": "s1", "op": "sketch_on_face",
            "params": {"face": "top", "entities": [{"kind": "circle", "r": 6}]},
            "inputs": ["b"]})
        return client.post("/api/feature/add", json={
            "id": "extrude1", "op": "extrude",
            "params": {"amount": amount}, "inputs": ["s1"]}).json()

    a = make("tab-a", 5)
    id_a = a["active_tab"]
    b = make("tab-b", 9)
    id_b = b["active_tab"]
    assert id_a != id_b

    client.post("/api/tabs/switch", json={"id": id_a})      # the panel opens on A
    client.post("/api/tabs/switch", json={"id": id_b})      # the user clicks B
    doc = client.post("/api/feature/params",
                      json={"feature_id": "extrude1",
                            "params": {"amount": 30}}).json()
    got = next(f for f in doc["features"] if f["id"] == "extrude1")
    assert got["params"]["amount"] == 30          # B was rewritten...
    back = client.post("/api/tabs/switch", json={"id": id_a}).json()
    mine = next(f for f in back["features"] if f["id"] == "extrude1")
    assert mine["params"]["amount"] == 5          # ...and A never changed


# ---------------------------------------------------------------------------
# F2 — the Spec dialog may not weaken the spec and then call it a pass
# ---------------------------------------------------------------------------

def test_the_spec_dialog_stops_when_the_holes_box_will_not_parse():
    """/api/spec REPLACES the whole spec, so carrying on past a parse failure
    DELETED the hole requirement — and the very next line said "design
    verifies against the new requirements"."""
    form = _slice(_src("dialogs.js"), "getElementById('specForm').onsubmit",
                  "export function actionSpec")
    assert "return" in _block(form, "catch"), \
        "the malformed-holes branch falls through and posts the spec anyway"
    assert form.index("JSON.parse") < form.index("specDialog().close()"), \
        "the spec dialog closes before its own text is parsed"


def test_a_spec_posted_without_holes_forgets_the_holes(client):
    """Why the guard above matters: the endpoint keeps only what it is sent."""
    client.post("/api/new", json={"name": "spec-holes"})
    client.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    doc = client.post("/api/spec",
                      json={"spec": {"n_solids": 1, "holes": {"4": 2}}}).json()
    assert doc["spec"]["holes"] == {"4": 2}
    doc = client.post("/api/spec", json={"spec": {"n_solids": 1}}).json()
    assert "holes" not in doc["spec"]


def test_the_add_feature_dialog_says_so_when_a_list_will_not_parse():
    """A missing bracket in a `points` box threw out of the submit handler —
    after the dialog had closed — so the feature was never added and nothing
    was said at all (fusion-parity rule 7)."""
    form = _slice(_src("dialogs.js"), "getElementById('featForm').onsubmit",
                  "getElementById('libClose')")
    assert form.index("JSON.parse") < form.index("featDialog().close()"), \
        "the Add Feature dialog closes before its own text is parsed"
    assert "return" in _block(form, "catch"), \
        "a malformed list is swallowed and the dialog closes on nothing"
    assert "try" in form[:form.index("JSON.parse")]


# ---------------------------------------------------------------------------
# F3 — every viewport pick outranks a tree row (fusion-parity rule 2)
# ---------------------------------------------------------------------------

def test_every_viewport_pick_outranks_a_tree_row():
    """A tree click REPLACES the viewport pick (tree.selectFeature calls
    clearPick) but nothing clears the row, so the row must rank LAST — curved
    picks included. The feature row was moved below the curved pick in the P4
    review; the SKETCH row was left above it, so selecting a sketch row and
    then clicking a cylinder wall extruded the SKETCH and Extrude / Revolve
    never said "needs a FLAT face"."""
    body = _slice(_src("tool.js"), "function currentSelection(",
                  "export const selectionKind")
    row = body.index("S.selected")
    for pick in ("S.pickedEdge", "S.pickedFace", "S.pickedProfile",
                 "S.pickedCurved"):
        assert body.index(pick) < row, \
            f"{pick} is read AFTER the tree row — a stale row hides that pick"


# ---------------------------------------------------------------------------
# F5 — a plan that is not a plan must still be a sentence
# ---------------------------------------------------------------------------

def test_plan_request_turns_a_non_200_into_a_sentence():
    """A 422 or a 500 answers with `detail`, never `ok`, so the panel refused
    with "cannot start: undefined" and closed itself. Same trap askJSON
    closed on 2026-09-09."""
    fn = _slice(_src("api.js"), "export async function planRequest",
                "A read-only QUESTION")
    assert "r.ok" in fn, "planRequest takes any HTTP status for a plan"


def test_the_plan_endpoint_really_can_answer_422(client):
    """The door the guard above covers is open: pydantic refuses a field of
    the wrong type before toolplan.plan() is ever reached."""
    client.post("/api/new", json={"name": "plan-422"})
    r = client.post("/api/tool/plan",
                    json={"tool": "fillet", "body_id": "b", "chain": "maybe"})
    assert r.status_code == 422
    assert "ok" not in r.json()


def test_an_unknown_tool_is_still_a_sentence(client):
    client.post("/api/new", json={"name": "plan-unknown"})
    p = client.post("/api/tool/plan", json={"tool": "nope"}).json()
    assert p["ok"] is False and "no plan for tool" in p["error"]


# ---------------------------------------------------------------------------
# F6 — the plan's `origin` is the profile's centre, not a sampling artefact
# ---------------------------------------------------------------------------

def _kernel_centroid(faces, pl):
    ax = ay = tot = 0.0
    for f in faces:
        c = pl.to_local_coords(f.center())
        ax += f.area * c.X
        ay += f.area * c.Y
        tot += f.area
    return ax / tot, ay / tot


def test_the_sampled_outline_is_ordered():
    """_poly_centroid only works because _project_wire walks a wire edge by
    edge: its shoelace area is the face's own area (exactly, on straight
    edges; 24-segment curves fall a little short by construction)."""
    for ents, tol in (
        ([{"kind": "rectangle", "w": 30, "h": 20}], 1e-6),
        ([{"kind": "regular_polygon", "radius": 12, "sides": 6}], 1e-3),
        ([{"kind": "circle", "r": 15},
          {"kind": "circle", "r": 5, "mode": "subtract"}], 0.02),
    ):
        d = build(("s", "sketch", {"plane": "XY", "entities": ents}, []))
        pl = sk.sketch_plane("XY", 0)
        faces = list(d._parts["s"].faces())
        loops = toolplan._loops(faces, pl)
        poly = 0.0
        for L in loops:
            poly += abs(toolplan._poly_centroid(L["outer"])[0])
            for h in L["holes"]:
                poly -= abs(toolplan._poly_centroid(h)[0])
        real = sum(f.area for f in faces)
        assert abs(poly - real) / real <= tol, (ents, poly, real)


def test_the_extrude_arrow_sits_on_an_L_shaped_profiles_centre():
    """The centre used to be the plain average of the sampled boundary POINTS:
    a line contributes 2, a curve 24. On this L (two rectangles, 400 + 200 mm2)
    the true centroid is (15, 10) and the average answered (16.667, 13.333) —
    3.7 mm out, on an everyday sketch."""
    d = build(("s", "sketch", {"plane": "XY", "entities": [
        {"kind": "polygon", "points": [[0, 0], [40, 0], [40, 10],
                                       [10, 10], [10, 30], [0, 30]]}]}, []))
    p = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"})
    assert p["ok"], p
    assert p["origin"] == pytest.approx([15.0, 10.0, 0.0], abs=1e-3)


def test_the_arrow_follows_the_AREA_not_the_busier_island():
    """A big circle (24 samples) beside a square (8) pulled the centre onto the
    circle: measured (-10.0, 0) against a true (2.404, 0), 12.4 mm out."""
    d = build(("s", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 10, "x": -20},
        {"kind": "rectangle", "w": 20, "h": 20, "x": 20}]}, []))
    pl = sk.sketch_plane("XY", 0)
    cx, cy = _kernel_centroid(list(d._parts["s"].faces()), pl)
    p = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"})
    assert p["ok"], p
    assert math.hypot(p["origin"][0] - cx, p["origin"][1] - cy) < 0.2, p["origin"]


@pytest.mark.parametrize("ents", [
    [{"kind": "circle", "r": 10}],
    [{"kind": "rectangle", "w": 30, "h": 20}],
    [{"kind": "circle", "r": 15}, {"kind": "circle", "r": 5, "mode": "subtract"}],
    [{"kind": "regular_polygon", "radius": 12, "sides": 6}],
    [{"kind": "slot", "length": 40, "height": 10}],
])
def test_a_symmetric_profile_keeps_the_centre_it_always_had(ents):
    """The change may not move the arrow on the ordinary profiles."""
    d = build(("s", "sketch", {"plane": "XY", "entities": ents}, []))
    p = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"})
    assert p["ok"], p
    assert p["origin"] == pytest.approx([0.0, 0.0, 0.0], abs=1e-3)


def test_a_profile_with_no_area_is_a_sentence_not_a_crash():
    """_limits answers None for a profile with no area, and plan_extrude turns
    that into a sentence — `_world(pl, *None)` would be a TypeError repr."""
    assert toolplan._limits([])[1] is None
    assert toolplan._limits([{"outer": [[0, 0], [1, 1]], "holes": []}])[1] is None
