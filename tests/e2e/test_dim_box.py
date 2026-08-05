"""E2E: the draw-time dimension box (feature-tree workstream step 7, R7).

Fusion behavior locked in: after the first click of a shape, a small input
follows the cursor with the live dimension; typing a number (no click into
the box needed) and pressing Enter commits the EXACT size. Tab hops fields.
"""
import pytest

pytest.importorskip("playwright.sync_api")

OPEN_SKETCH = """
async () => {
  const sk = await import('/static/js/sketcher.js');
  sk.openSketchEditor('XY');
  await new Promise(r => setTimeout(r, 900));   // enter tween
  sk.setSketchTool('%s');
}
"""

CLICK = """
async (args) => {
  const [x, y] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x, y, tol: 1 }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 120));
}
"""

MOVE = """
async (args) => {
  const [x, y] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-move', { x, y, tol: 1, down: false });
  await new Promise(r => setTimeout(r, 120));
}
"""

ENTS = """
async () => (await import('/static/js/sketcher.js')).sketchEntities()
"""


def test_typed_circle_radius(server, page, fresh_doc):
    page.evaluate(OPEN_SKETCH % "circle")
    page.evaluate(CLICK, [0, 0])              # center
    page.evaluate(MOVE, [10, 0])              # live radius (grid-snapped)
    box = page.locator("#skDimDraw")
    assert box.is_visible(), "dimension box must appear after the 1st click"
    assert float(page.input_value("#skDimDraw input")) > 0, "live value shown"

    page.keyboard.type("12.5")                # just start typing (no click)
    page.keyboard.press("Enter")
    page.wait_for_timeout(150)
    ents = page.evaluate(ENTS)
    assert len(ents) == 1 and ents[0]["kind"] == "circle"
    assert abs(ents[0]["r"] - 12.5) < 1e-6, ents[0]
    assert ents[0]["x"] == 0 and ents[0]["y"] == 0
    assert not page.locator("#skDimDraw").is_visible(), "box hides on commit"
    assert not page.errors, page.errors


def test_typed_rectangle_w_tab_h(server, page, fresh_doc):
    page.evaluate(OPEN_SKETCH % "rectangle")
    page.evaluate(CLICK, [0, 0])              # first corner
    page.evaluate(MOVE, [30, 20])             # direction +x +y
    assert page.locator("#skDimDraw").is_visible()

    page.keyboard.type("40")
    page.keyboard.press("Tab")
    page.keyboard.type("25")
    page.keyboard.press("Enter")
    page.wait_for_timeout(150)
    e = page.evaluate(ENTS)[0]
    assert e["kind"] == "rectangle"
    assert abs(e["w"] - 40) < 1e-6 and abs(e["h"] - 25) < 1e-6, e
    # first click is a CORNER: the rect grew toward the cursor (+x +y)
    assert abs(e["x"] - 20) < 1e-6 and abs(e["y"] - 12.5) < 1e-6, e
    assert not page.errors, page.errors


def test_second_click_still_works(server, page, fresh_doc):
    """The box must never break plain mouse drawing."""
    page.evaluate(OPEN_SKETCH % "circle")
    page.evaluate(CLICK, [0, 0])
    page.evaluate(MOVE, [10, 0])
    page.evaluate(CLICK, [10, 0])             # commit by second click
    page.wait_for_timeout(150)
    e = page.evaluate(ENTS)[0]
    assert e["kind"] == "circle" and abs(e["r"] - 10) < 1e-6, e
    assert not page.locator("#skDimDraw").is_visible()
    assert not page.errors, page.errors
