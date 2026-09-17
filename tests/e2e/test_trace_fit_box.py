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
