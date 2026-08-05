"""E2E: even-odd holes (R10 — "two circles must make a WASHER"), drag-resize
handles (step 8, R6), and the mm unit label (R9).

The washer test replays the user's exact report: draw an outer circle and an
inner circle, extrude, and the result must be a RING — not a merged solid.
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

OPEN_SKETCH = """
async () => {
  const sk = await import('/static/js/sketcher.js');
  sk.openSketchEditor('XY');
  await new Promise(r => setTimeout(r, 900));
  sk.setSketchTool('%s');
}
"""

TOGGLE_TOOL = """
async () => (await import('/static/js/sketcher.js')).setSketchTool('%s')
"""

CLICK = """
async (args) => {
  const [x, y] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x, y, tol: 1 }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 100));
}
"""

DRAG = """
async (args) => {
  const [x0, y0, x1, y1] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x: x0, y: y0, tol: 1 });
  bus.emit('sk3d-move', { x: x1, y: y1, tol: 1, down: true });
  bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 100));
}
"""

ENTS = """
async () => (await import('/static/js/sketcher.js')).sketchEntities()
"""

FINISH = """
async () => (await import('/static/js/sketcher.js')).finishSketch()
"""


def feat(url, fid, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        doc = httpx.get(f"{url}/api/doc", timeout=5).json()
        f = next((x for x in doc["features"] if x["id"] == fid), None)
        if f and f["status"] == "ok":
            return f
        time.sleep(0.2)
    raise AssertionError(f"{fid} never became ok")


def test_inner_circle_makes_washer(server, page, fresh_doc):
    page.evaluate(OPEN_SKETCH % "circle")
    page.evaluate(CLICK, [0, 0]); page.evaluate(CLICK, [20, 0])   # outer r20
    page.evaluate(CLICK, [0, 0]); page.evaluate(CLICK, [10, 0])   # inner r10
    ents = page.evaluate(ENTS)
    assert ents[0]["mode"] == "add" and ents[1]["mode"] == "subtract", \
        f"inner circle must become a HOLE (even-odd): {ents}"
    page.evaluate(FINISH)
    # the auto-name counts sketches in whatever doc the PAGE booted with (the
    # page fixture loads before fresh_doc resets), so resolve the real id
    sk_id = None
    deadline = time.time() + 20
    while time.time() < deadline and not sk_id:
        doc = httpx.get(f"{server}/api/doc", timeout=5).json()
        sk_id = next((f["id"] for f in doc["features"] if f["op"] == "sketch"),
                     None)
        if not sk_id:
            time.sleep(0.3)
    assert sk_id, "finished sketch never arrived at the server"

    r = httpx.post(f"{server}/api/feature/add", json={
        "id": "ring", "op": "extrude", "params": {"amount": 5},
        "inputs": [sk_id]}, timeout=60).json()
    assert "error" not in r or not r["error"]
    f = feat(server, "ring")
    import math
    expect = math.pi * (20**2 - 10**2) * 5
    assert abs(f["volume"] - expect) / expect < 0.01, \
        f"expected a washer (~{expect:.0f}mm3), got {f['volume']}"
    assert not page.errors, page.errors


def test_drag_circle_rim_resizes(server, page, fresh_doc):
    page.evaluate(OPEN_SKETCH % "circle")
    page.evaluate(CLICK, [0, 0]); page.evaluate(CLICK, [10, 0])   # r10
    page.evaluate(TOGGLE_TOOL % "circle")                          # -> select
    page.evaluate(CLICK, [5, 5])                                   # select it
    page.evaluate(DRAG, [10, 0, 15, 0])                            # pull rim
    e = page.evaluate(ENTS)[0]
    assert abs(e["r"] - 15) < 1e-6, e
    assert e["x"] == 0 and e["y"] == 0, "center must not move on rim drag"
    assert not page.errors, page.errors


def test_drag_rect_corner_resizes_about_opposite(server, page, fresh_doc):
    page.evaluate(OPEN_SKETCH % "rectangle")
    page.evaluate(CLICK, [0, 0]); page.evaluate(CLICK, [20, 10])
    page.evaluate(TOGGLE_TOOL % "rectangle")
    page.evaluate(CLICK, [10, 5])                                  # select
    page.evaluate(DRAG, [20, 10, 30, 20])                          # pull corner
    e = page.evaluate(ENTS)[0]
    assert abs(e["w"] - 30) < 1e-6 and abs(e["h"] - 20) < 1e-6, e
    assert abs(e["x"] - 15) < 1e-6 and abs(e["y"] - 10) < 1e-6, \
        f"opposite corner (0,0) must stay put: {e}"
    assert not page.errors, page.errors


def test_dim_editor_fields_follow_the_shape(server, page, fresh_doc):
    """User report 2026-08-05: 'for circle i am getting w and h box'. The
    floating dim editor cached its inputs BY INDEX — delete a rectangle and
    a circle inheriting index 0 kept the rectangle's W/H fields."""
    page.evaluate(OPEN_SKETCH % "rectangle")
    page.evaluate(CLICK, [0, 0]); page.evaluate(CLICK, [20, 10])
    page.evaluate(TOGGLE_TOOL % "rectangle")           # -> select mode
    page.evaluate(CLICK, [10, 5])                      # select rect: W/H box
    assert page.locator("#skDimEdit3d input").count() == 2
    page.keyboard.press("Delete")                      # rect gone
    page.evaluate(TOGGLE_TOOL % "circle")
    page.evaluate(CLICK, [0, 0]); page.evaluate(CLICK, [10, 0])
    page.evaluate(TOGGLE_TOOL % "circle")              # -> select mode
    page.evaluate(CLICK, [3, 3])                       # select the circle
    labels = page.locator("#skDimEdit3d label span").all_text_contents()
    assert page.locator("#skDimEdit3d input").count() == 1, \
        f"a circle has ONE dimension, got fields {labels}"
    assert labels[0] == "R", labels
    assert not page.errors, page.errors


def test_dim_box_shows_unit(server, page, fresh_doc):
    page.evaluate(OPEN_SKETCH % "circle")
    page.evaluate(CLICK, [0, 0])
    page.evaluate("""async () => {
      const { bus } = await import('/static/js/bus.js');
      bus.emit('sk3d-move', { x: 10, y: 0, tol: 1, down: false });
      await new Promise(r => setTimeout(r, 150));
    }""")
    assert page.locator("#skDimDraw").is_visible()
    assert page.text_content("#skDimDraw .dimunit").strip() == "mm"
    assert not page.errors, page.errors
