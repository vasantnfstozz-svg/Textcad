"""E2E: the user's REAL journey, end to end — not isolated steps.

User feedback (2026-08-04): "the test case has to test the feature we are
improving... simply drawing a t-washer won't help at all." This file replays
the exact reported workflow through the real UI entry points — ribbon button,
a REAL pixel click on the block's face, grid hovering, drawing, the Finish
button — and asserts the two things that were reported broken:

  1. while drawing, EVERY grid cell corner is recognized (visible pick box /
     hover lock), not just the origin;
  2. after finishing the face sketch and extruding it, the MAIN BODY must
     still be there — it used to vanish.
"""
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""

# world point -> client pixel via the live camera (to click the REAL face)
TO_SCREEN = """
(w) => {
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  const r = cv.getBoundingClientRect();
  const V3 = vp.camera.position.constructor;
  const v = new V3(w[0], w[1], w[2]).project(vp.camera);
  return { x: r.left + (v.x + 1) / 2 * r.width,
           y: r.top + (1 - (v.y + 1) / 2) * r.height };
}
"""

IS_ACTIVE = """
async () => (await import('/static/js/sketch3d.js')).sketch3DActive()
"""
NOT_ACTIVE = """
async () => !(await import('/static/js/sketch3d.js')).sketch3DActive()
"""
TWEEN_DONE = "() => window.__vp.getControls().enabled === true"

HOVER = """
async (args) => {
  const [x, y, tol] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-move', { x, y, tol, down: false });
  await new Promise(r => setTimeout(r, 120));
  const sk = await import('/static/js/sketcher.js');
  return sk.hoverInfo();
}
"""

CLICK = """
async (args) => {
  const [x, y, tol] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x, y, tol }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 120));
}
"""


@pytest.fixture()
def face_sketch_via_real_click(page, fresh_doc):
    """Create Sketch pressed in the ribbon, then a REAL pixel click on the
    block's top face — the entry point a user actually takes (a bus-emitted
    shortcut would bypass the face picker, which has had its own bug)."""
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)
    page.click("#ribbon .rbtn[title='Create Sketch']")
    page.wait_for_timeout(500)
    top = page.evaluate(TO_SCREEN, [5, 3, 10])       # a point on the TOP face
    page.mouse.click(top["x"], top["y"], button="left")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    return page


def test_grid_corners_are_recognized_while_drawing(face_sketch_via_real_click):
    page = face_sketch_via_real_click
    step = page.evaluate(
        "async () => (await import('/static/js/sketch3d.js')).gridStep()")
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('rectangle');
    }""")
    # hovering BETWEEN grid lines, away from any geometry: the cursor must
    # lock onto the nearest cell corner and say so (the Fusion pick box)
    h = page.evaluate(HOVER, [1.46 * step, 0.7 * step, 1.5])
    assert h["snap"] is None, h                       # no geometry nearby
    assert h["grid"] is not None, "grid corner not recognized"
    for v in (h["grid"]["x"], h["grid"]["y"]):
        assert v / step == pytest.approx(round(v / step), abs=1e-6), (h, step)
    # near the origin, the geometry snap must still OUTRANK the grid box
    h0 = page.evaluate(HOVER, [0.4, 0.3, 3.0])
    assert h0["snap"] and "origin" in h0["snap"]["label"], h0
    assert h0["grid"] is None, h0
    assert page.errors == []


def test_extruding_a_face_sketch_keeps_the_main_body(face_sketch_via_real_click):
    """The reported bug, replayed exactly: block -> sketch on its face ->
    draw -> Finish (real button) -> extrude the sketch -> BOTH bodies must
    be real, opaque solids in the scene."""
    page = face_sketch_via_real_click
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('circle');
    }""")
    page.evaluate(CLICK, [10, 10, 1.5])              # centre on a cell corner
    page.evaluate(CLICK, [20, 10, 1.5])              # radius point
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1 and ents[0]["kind"] == "circle", ents

    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    sk_feat = next(f for f in doc["features"] if f["op"] == "sketch_on_face")
    assert sk_feat["status"] == "ok", sk_feat

    page.evaluate("""async (skId) => {
      const { postJSON } = await import('/static/js/api.js');
      const { loadMesh } = await import('/static/js/viewport.js');
      await postJSON('/api/feature/add',
        { id: 'boss', op: 'extrude', params: { amount: 8 },
          inputs: [skId] }, 'extrude');
      await loadMesh(true);
    }""", sk_feat["id"])
    page.wait_for_timeout(800)

    assert page.evaluate("window.__vp.bodyCount()") == 2, \
        "the main body vanished after extruding the face sketch"
    info = page.evaluate("window.__vp.bodyInfo()")
    ids = sorted(x["id"] for x in info)
    assert ids == ["b", "boss"], info
    for x in info:                       # a ghosted body passes DOM checks
        assert x["opacity"] == 1 and not x["transparent"], info
    assert page.errors == []
