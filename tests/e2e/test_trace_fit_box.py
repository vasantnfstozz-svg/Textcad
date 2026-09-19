"""E2E: the Trace Image BUTTON fits art to the server's inscribed box.

/api/face-outline returns `fit_box` — the biggest rectangle that fits INSIDE
the picked face's outline. `_trace_face_fit` (the feature-creating path that
"stays for scripts and the MCP tools") uses it, but the button the user
actually presses is `traceIntoSketch` in sketcher.js, and that derived the box
itself from the outline's min/max — which is the face only when the face is a
rectangle (LAUNCH-PLAN R1: never re-derive a backend fact in the frontend).

Measured on a 30 mm disc with a square picture (probes/imgtrace_fitbox_unused.py):
the browser's own box was 60x60 and 8 of 8 traced points landed OFF the disc,
the furthest 37.85 mm from the centre; the server's box is 42x42 and every
point lands on the material, the furthest 26.49 mm.

This drives the REAL button — the file chooser its own <input> opens — and
measures where the entities ended up.
"""
import pytest

pytest.importorskip("playwright.sync_api")

BUILD_DISC = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'disc1', op: 'disc', params: { radius: 30, thickness: 10 },
      inputs: [] }, 'add');
  await loadMesh(true);
}
"""

# the disc spans z 0..10 -> its top face is at (0, 0, 5), normal +Z. This is
# exactly what the viewport's face pick emits when the user clicks it.
OPEN_FACE_SKETCH = """
async () => {
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sketch-on-face', { center: [0, 0, 5], normal: [0, 0, 1],
                               body: 'disc1' });
}
"""

SKETCH_ACTIVE = """
async () => (await import('/static/js/sketch3d.js')).sketch3DActive()
"""

TRACE = """
async () => { (await import('/static/js/sketcher.js')).traceIntoSketch(); }
"""

ENTS = """
async () => (await import('/static/js/sketcher.js')).sketchEntities()
"""

CHAT = """
() => [...document.querySelectorAll('#chatLog .msg')]
        .map(e => e.textContent).join(' | ')
"""


def _square_png(path):
    """A plain black square on transparent — 8 traced points, easy to measure."""
    import cv2
    import numpy as np
    size, pad = 400, 30
    img = np.zeros((size, size, 4), np.uint8)
    cv2.rectangle(img, (pad, pad), (size - pad, size - pad),
                  (10, 10, 10, 255), -1)
    assert cv2.imwrite(str(path), img)
    return str(path)


def _trace_onto_the_disc(page, png):
    page.evaluate(BUILD_DISC)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.evaluate(OPEN_FACE_SKETCH)
    page.wait_for_function(SKETCH_ACTIVE, timeout=20000)
    with page.expect_file_chooser(timeout=15000) as fc:
        page.evaluate(TRACE)
    fc.value.set_files(png)
    for _ in range(60):                      # the trace is a round trip
        page.wait_for_timeout(500)
        ents = page.evaluate(ENTS)
        if ents:
            return ents
    raise AssertionError("the trace never reached the sketch")


def test_traced_art_lands_on_a_round_face(page, fresh_doc, server, tmp_path):
    """Every traced point must sit on the 30 mm disc, not beyond its rim."""
    ents = _trace_onto_the_disc(page, _square_png(tmp_path / "sq.png"))
    pts = [(e["x"] + p[0], e["y"] + p[1]) for e in ents for p in e["points"]]
    assert pts, f"the trace produced no points: {ents}"
    far = [(x * x + y * y) ** 0.5 for x, y in pts]
    off = [d for d in far if d > 30.0]
    assert not off, (f"{len(off)} of {len(far)} traced points are off the "
                     f"30 mm disc, the furthest {max(far):.2f} mm from centre")
    assert page.errors == []


def test_the_chat_does_not_call_the_fit_box_the_face(page, fresh_doc, server,
                                                     tmp_path):
    """The number printed is the box the art was fitted INTO — on a 30 mm disc
    it is 42x42, and the face is 60 mm across. Saying "the 42x42mm face" is a
    wrong measurement in the user's chat."""
    _trace_onto_the_disc(page, _square_png(tmp_path / "sq.png"))
    text = page.evaluate(CHAT)
    assert "auto-fitted" in text, f"no trace message in the chat: {text[-400:]}"
    import re
    assert not re.search(r"\d+(\.\d+)?×\d+(\.\d+)?mm face", text), \
        f"the chat calls the fit box a face: {text[-400:]}"
    assert page.errors == []


# ---------------------------------------------------------------------------
# Round two: the tracer's own SENTENCE about the part, and the key it reads.
#
# imgtrace puts a `note` on trace_info for the two things the user has to know
# before they cut: art the weld could not join into one piece, and two parts of
# the art that pass within microns of each other ("the sketch builds, but trace
# it taller if the extrude ever refuses"). /api/trace-png is called from exactly
# one place in the app — traceIntoSketch — and that sentence printed
# width/height/fit/rotated/contours/holes and DROPPED the note, so no user has
# ever seen either warning.
#
# The note is grafted onto the REAL server response here rather than coaxed out
# of a picture: whether imgtrace produces it is its own file's tests (this
# reviewer may not touch imgtrace.py), and the defect under test is that the
# browser throws the field away.
# ---------------------------------------------------------------------------

NOTE = ("two parts of this artwork pass 3.21 microns apart — thinner than "
        "the tracer can open. The sketch builds, but trace it taller if the "
        "extrude ever refuses.")


def _graft(page, mutate):
    """Let /api/trace-png answer for real, then change its trace_info."""
    import json

    def handler(route):
        resp = route.fetch()
        body = resp.json()
        if isinstance(body, dict) and body.get("trace_info") is not None:
            mutate(body["trace_info"])
        route.fulfill(status=resp.status, content_type="application/json",
                      body=json.dumps(body))

    page.route("**/api/trace-png", handler)


def test_the_tracers_note_reaches_the_user(page, fresh_doc, server, tmp_path):
    """A warning about the part they are about to cut must be IN THE CHAT."""
    def add_note(info):
        info["tight_mm"] = 0.00321
        info["note"] = NOTE

    _graft(page, add_note)
    _trace_onto_the_disc(page, _square_png(tmp_path / "sq.png"))
    text = page.evaluate(CHAT)
    assert "microns apart" in text, \
        f"the tracer's note never reached the chat: {text[-600:]}"
    assert "trace it taller" in text, \
        f"the note reached the chat cut short: {text[-600:]}"
    assert page.errors == []


# faceRef is built at TWO places — openSketchOnFace (a fresh pick) and
# editSketch (a sketch reopened from the tree). Round one carried fit_box into
# both; only the first was driven by a test. This is the second door.
REOPEN = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  const { bus } = await import('/static/js/bus.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch_on_face',
      params: { face_center: [0, 0, 5], face_normal: [0, 0, 1], offset: 0,
                entities: [{ kind: 'circle', r: 3, x: 0, y: 0, mode: 'add' }] },
      inputs: ['disc1'] }, 'add');
  await loadMesh(true);
  const f = (await (await fetch('/api/doc')).json()).features.find(x => x.id === 'sk1');
  bus.emit('edit-sketch', f);
}
"""


def test_a_REOPENED_face_sketch_traces_onto_the_material_too(page, fresh_doc,
                                                             server, tmp_path):
    """The same 30 mm disc, but the sketch is reopened from the tree instead of
    picked fresh — editSketch's faceRef must carry the server's box as well."""
    page.evaluate(BUILD_DISC)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.evaluate(REOPEN)
    page.wait_for_function(SKETCH_ACTIVE, timeout=20000)
    page.wait_for_timeout(800)
    before = len(page.evaluate(ENTS))
    with page.expect_file_chooser(timeout=15000) as fc:
        page.evaluate(TRACE)
    fc.value.set_files(_square_png(tmp_path / "sq.png"))
    ents = []
    for _ in range(60):
        page.wait_for_timeout(500)
        ents = page.evaluate(ENTS)
        if len(ents) > before:
            break
    assert len(ents) > before, "the trace never reached the reopened sketch"
    # the reopened sketch already holds its own circle; the traced art is the
    # polygon entities, the ones with points
    pts = [(e["x"] + p[0], e["y"] + p[1])
           for e in ents for p in e.get("points") or []]
    assert pts, f"the trace produced no points: {ents}"
    far = [(x * x + y * y) ** 0.5 for x, y in pts]
    off = [d for d in far if d > 30.0]
    assert not off, (f"{len(off)} of {len(far)} points are off the 30 mm disc, "
                     f"the furthest {max(far):.2f} mm from centre")
    assert page.errors == []


def test_the_fit_sentence_reads_the_servers_fit_mm(page, fresh_doc, server,
                                                   tmp_path):
    """`fit_mm` is the key that means the FITTED RECTANGLE; `face_mm` is the
    old name kept beside it only until the browser moved over. With face_mm
    gone the sentence must be unchanged — that is what lets the server retire
    the old key."""
    def drop_old_key(info):
        info.pop("face_mm", None)

    _graft(page, drop_old_key)
    _trace_onto_the_disc(page, _square_png(tmp_path / "sq.png"))
    text = page.evaluate(CHAT)
    assert "auto-fitted" in text, f"no trace message in the chat: {text[-400:]}"
    # 42 x 42 is the inscribed box of a 30 mm disc (studio._inscribed_box)
    assert "42" in text, \
        f"the fit rectangle is missing from the sentence: {text[-400:]}"
    assert page.errors == []
