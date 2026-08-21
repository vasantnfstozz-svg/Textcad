"""E2E: the sketch Scale tool — INTERACTIVE drag with a live mm readout.

User request (2026-08-21, v2): "just move the arrow up to increase, down to
decrease... a virtual scale for knowing the height and width... instead of
putting number". Locked in here:

  1. pressing Scale enters drag mode: cursor up/down resizes LIVE, factor
     2^(dy/40); a click commits, the readout shows W × H in mm;
  2. with NOTHING selected it scales EVERY entity about the sketch origin —
     positions AND dimensions — so multi-piece art (a traced logo's outline
     + holes) stays registered;
  3. with a shape SELECTED it scales just that shape in place (centre stays).
"""
import httpx
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

CLICK = """
async (args) => {
  const [x, y, tol] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x, y, tol }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 120));
}
"""

SET_TOOL = """
async (t) => {
  const sk = await import('/static/js/sketcher.js');
  sk.setSketchTool(t);
}
"""

SCALE = """
async () => {
  const sk = await import('/static/js/sketcher.js');
  sk.sketchModify('scale');
}
"""


@pytest.fixture()
def top_face_sketch(page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)
    page.click("#ribbon .rbtn[title='Create Sketch']")
    page.wait_for_timeout(500)
    top = page.evaluate(TO_SCREEN, [5, 3, 20])
    page.mouse.click(top["x"], top["y"], button="left")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    return page


def _entities(server):
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    sk = [f for f in doc["features"] if f["op"] == "sketch"][-1]
    return {e["kind"]: e for e in sk["params"]["entities"]}


def test_scale_all_then_scale_selected(top_face_sketch, server):
    page = top_face_sketch
    # draw: rectangle (0,0)-(20,10) and circle centre (30,5) r 5
    page.evaluate(SET_TOOL, "rectangle")
    page.evaluate(CLICK, [0, 0, 1.0])
    page.evaluate(CLICK, [20, 10, 1.0])
    page.evaluate(SET_TOOL, "circle")
    page.evaluate(CLICK, [30, 5, 1.0])
    page.evaluate(CLICK, [35, 5, 1.0])

    MOVE = """
    async (args) => {
      const [x, y, tol] = args;
      const { bus } = await import('/static/js/bus.js');
      bus.emit('sk3d-move', { x, y, tol });
      await new Promise(r => setTimeout(r, 80));
    }
    """
    # 1) NOTHING selected -> drag scales everything about the sketch origin.
    #    first move anchors the drag; +80mm up = factor 2^(80/40) = 4.
    page.evaluate(SET_TOOL, None)                 # tool pick deselects
    page.evaluate(SCALE)
    page.evaluate(MOVE, [0, 0, 1.0])              # anchor
    page.evaluate(MOVE, [0, 80, 1.0])             # x4, live
    page.evaluate(CLICK, [0, 80, 1.0])            # click commits
    page.wait_for_timeout(200)

    # 2) SELECT the rectangle (click its left edge) -> drag halves it in
    #    place: -40mm down = factor 2^(-40/40) = 0.5.
    page.evaluate(CLICK, [0, 20, 2.0])
    page.evaluate(SCALE)
    page.evaluate(MOVE, [0, 0, 1.0])              # anchor
    page.evaluate(MOVE, [0, -40, 1.0])            # x0.5, live
    page.evaluate(CLICK, [0, -40, 1.0])           # commit
    page.wait_for_timeout(200)

    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function(NOT_ACTIVE, timeout=20000)
    page.wait_for_timeout(500)

    ents = _entities(server)
    rect, circ = ents["rectangle"], ents["circle"]
    # circle: scaled by the ALL pass only — position AND radius x4
    assert circ["x"] == pytest.approx(120, abs=0.01)
    assert circ["y"] == pytest.approx(20, abs=0.01)
    assert circ["r"] == pytest.approx(20, abs=0.01)
    # rectangle: x4 (all) then x0.5 IN PLACE — centre stays, dims halve
    assert rect["x"] == pytest.approx(40, abs=0.01)
    assert rect["y"] == pytest.approx(20, abs=0.01)
    assert rect["w"] == pytest.approx(40, abs=0.01)
    assert rect["h"] == pytest.approx(20, abs=0.01)
    assert page.errors == []
