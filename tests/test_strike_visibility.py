"""Struck-out features must not keep hiding what they consumed.

Reported 2026-09-01 on esp32-remote: the user traced a logo, extrude-cut it,
struck the cut out, drew a new logo sketch and extruded it as a NEW body —
and "the whole back body vanished". The struck-out cut still counted as a
consumer of the case body, so the moment another leaf existed the body fell
out of leaf_solid_ids (before that, the result-fallback in /api/model had
been papering over it). Same root cause hid the freed SKETCH: consumed by a
struck extrude, it disappeared from the viewport and could not be re-picked.

The rule (Document.consumed_ids): a suppressed feature consumes nothing —
but it IS a pass-through to its first input during rebuild, so an ACTIVE
feature consuming a struck id really consumes what that id resolves to.
"""
import studio
from document import Document

CIRCLE = {"kind": "circle", "x": 5, "y": 5, "r": 3, "mode": "add"}
CIRCLE2 = {"kind": "circle", "x": -6, "y": -4, "r": 3, "mode": "add"}


def _cut_attempt(doc):
    """box + face sketch + extrude tool + cut — one logo attempt."""
    doc.add("box", "plate", {"width": 40, "depth": 30, "thickness": 10})
    doc.add("s1", "sketch_on_face", {"face": "top", "offset": 0,
                                     "entities": [CIRCLE]}, inputs=["box"])
    doc.add("e1", "extrude", {"amount": -2}, inputs=["s1"])
    doc.add("c1", "cut", inputs=["box", "e1"])


def test_new_body_after_struck_cut_keeps_the_base_visible():
    """The exact vanish: strike the cut, extrude a retry sketch as a new
    body — BOTH the base body and the new body must be leaves."""
    doc = Document(name="logo-vanish")
    _cut_attempt(doc)
    doc.add("s2", "sketch_on_face", {"face": "top", "offset": 0,
                                     "entities": [CIRCLE2]}, inputs=["c1"])
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["c1"]

    doc.strike("c1")                      # takes s1 + e1 with it (tool group)
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["box"]

    doc.add("e2", "extrude", {"amount": 2}, inputs=["s2"])
    assert doc.rebuild()
    assert set(doc.leaf_solid_ids()) == {"box", "e2"}, \
        "the base body vanished when the new-body extrude appeared"


def test_active_consumer_through_a_struck_node_still_hides_the_base():
    """The pass-through: c2 consumes c1 (struck) which resolves to box —
    box must stay hidden, only the tip shows."""
    doc = Document(name="passthrough")
    _cut_attempt(doc)
    doc.add("s2", "sketch_on_face", {"face": "top", "offset": 0,
                                     "entities": [CIRCLE2]}, inputs=["c1"])
    doc.add("e2", "extrude", {"amount": -2}, inputs=["s2"])
    doc.add("c2", "cut", inputs=["c1", "e2"])
    assert doc.rebuild()
    doc.strike("c1")                      # mid-chain strike; c2 stays active
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["c2"], \
        "a body consumed THROUGH a struck pass-through must not reappear"


def test_striking_an_extrude_frees_its_sketch():
    """A sketch consumed only by a struck extrude must come back on screen
    (and be offerable to Extrude again)."""
    doc = Document(name="sketch-free")
    doc.add("box", "plate", {"width": 40, "depth": 30, "thickness": 10})
    doc.add("s1", "sketch_on_face", {"face": "top", "offset": 0,
                                     "entities": [CIRCLE]}, inputs=["box"])
    doc.add("e1", "extrude", {"amount": 2}, inputs=["s1"])
    assert doc.rebuild()
    assert [s["id"] for s in studio._sketches_json(doc)] == []  # consumed

    doc.strike("e1")
    assert doc.rebuild()
    assert [s["id"] for s in studio._sketches_json(doc)] == ["s1"], \
        "striking the extrude must put its sketch back in the viewport"
    assert doc.leaf_solid_ids() == ["box"]


# ---------------------------------------------------------------------------
# Section 2 code review, 2026-09-10: clicking a struck-out row lit up the
# WHOLE upstream body as "what this feature contributes".
#
# A suppressed node is a pass-through during rebuild, so its slot in `_parts`
# holds its first input's solid. /api/feature-mesh served that slot without
# asking whether the feature is switched off, so selecting a struck fillet /
# hole / cut highlighted the entire part in orange — the 2026-08-26 complaint
# ("the whole body is being selected") coming back through the struck rows.
# viewport.js already treats a 404 here as "feature not built (suppressed /
# rolled back)", which is exactly what it must get.
# ---------------------------------------------------------------------------

def _client_with(doc):
    from fastapi.testclient import TestClient
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def _struck_hole_doc():
    doc = Document(name="struck-overlay")
    doc.add("box", "plate", {"width": 40, "depth": 30, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 4}, inputs=["box"])
    return doc


def test_a_struck_feature_serves_no_highlight_mesh():
    doc = _struck_hole_doc()
    client = _client_with(doc)
    assert client.get("/api/feature-mesh/bore.stl").status_code == 200

    client.post("/api/feature/strike", json={"feature_id": "bore"})
    # the pass-through is still there — that is what rebuild needs...
    assert studio._doc()._parts.get("bore") is not None
    # ...but it is the BOX, and the tree must not paint it as the bore's own
    assert client.get("/api/feature-mesh/bore.stl").status_code == 404, \
        "a struck row highlighted the whole upstream body"

    client.post("/api/feature/strike",
                json={"feature_id": "bore", "restore": True})
    assert client.get("/api/feature-mesh/bore.stl").status_code == 200
