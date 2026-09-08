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


def test_modify_tab_scale_routes_a_sketch_into_drag_scale(page, fresh_doc,
                                                          server):
    """Reported 2026-08-21: clicking Modify->Scale with a traced logo opened
    the generic factor dialog ('still i am getting the same box'). With a
    sketch as the obvious target it must open the editor IN drag-scale."""
    httpx.post(f"{server}/api/feature/add", json={
        "id": "logo", "op": "sketch",
        "params": {"plane": "XY", "offset": 0, "entities": [
            {"kind": "rectangle", "mode": "add", "x": 5, "y": 5,
             "w": 20, "h": 10}]},
        "inputs": []}, timeout=60)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.click("#tabstrip >> text=Modify")
    page.wait_for_timeout(300)
    page.click("#ribbon .rbtn[title='scale']")
    page.wait_for_function(
        "async () => (await import('/static/js/sketch3d.js')).sketch3DActive()",
        timeout=20000)
    page.wait_for_timeout(800)
    # GRAB the vertical arrow (rect bbox -5..15 x 0..10 -> ruler at x=18),
    # drag +40mm = x2, release, then click away to finish the scale
    page.evaluate(EMIT := """
    async (args) => {
      const [kind, x, y] = args;
      const { bus } = await import('/static/js/bus.js');
      bus.emit(kind, x === null ? {} : { x, y, tol: 2.0 });
      await new Promise(r => setTimeout(r, 120));
    }
    """, ["sk3d-down", 18, 5])
    page.evaluate(EMIT, ["sk3d-move", 18, 45])
    assert page.text_content("#sk3dCoords").startswith("scale")
    page.evaluate(EMIT, ["sk3d-up", None, None])
    page.evaluate(EMIT, ["sk3d-down", -40, -30])       # away = finish
    page.evaluate(EMIT, ["sk3d-up", None, None])
    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function(
        "async () => !(await import('/static/js/sketch3d.js')).sketch3DActive()",
        timeout=20000)
    page.wait_for_timeout(500)
    ents = _entities(server)
    assert ents["rectangle"]["w"] == pytest.approx(40, abs=0.01)
    assert ents["rectangle"]["h"] == pytest.approx(20, abs=0.01)
    assert page.errors == []


def test_scale_in_empty_new_sketch_jumps_to_the_real_one(page, fresh_doc,
                                                         server):
    """Reported 2026-08-21: user pressed Scale inside a NEW (empty) sketch
    while the traced logo was visible -> 'the sketch is empty'. With exactly
    one committed sketch in the doc, Scale must jump into IT and arm the
    drag."""
    httpx.post(f"{server}/api/feature/add", json={
        "id": "logo", "op": "sketch",
        "params": {"plane": "XY", "offset": 0, "entities": [
            {"kind": "rectangle", "mode": "add", "x": 0, "y": 0,
             "w": 30, "h": 12}]},
        "inputs": []}, timeout=60)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.click("#ribbon .rbtn[title='Create Sketch']")
    page.wait_for_timeout(800)
    q = page.evaluate("""() => {
      const vp = window.__vp;
      const info = vp.originPlaneInfo().find(x => x.plane === 'XY');
      const cv = document.querySelector('#viewer canvas');
      const r = cv.getBoundingClientRect();
      const V3 = vp.camera.position.constructor;
      const v = new V3(...info.position).project(vp.camera);
      return { x: r.left + (v.x + 1) / 2 * r.width,
               y: r.top + (1 - (v.y + 1) / 2) * r.height };
    }""")
    page.mouse.click(q["x"], q["y"])
    page.wait_for_function(
        "async () => (await import('/static/js/sketch3d.js')).sketch3DActive()",
        timeout=20000)
    page.wait_for_timeout(1000)
    page.click("#ribbon .rbtn[title='Scale']")     # empty sketch -> must jump
    page.wait_for_timeout(2500)
    EMIT = """
    async (args) => {
      const [kind, x, y] = args;
      const { bus } = await import('/static/js/bus.js');
      bus.emit(kind, x === null ? {} : { x, y, tol: 2.0 });
      await new Promise(r => setTimeout(r, 120));
    }
    """
    # rect bbox -15..15 x -6..6 -> vertical ruler at x=18, mid y=0:
    # grab it, drag +40mm = x2, release, click away to finish
    page.evaluate(EMIT, ["sk3d-move", -30, 20])    # hover must NOT scale
    page.evaluate(EMIT, ["sk3d-down", 18, 0])
    page.evaluate(EMIT, ["sk3d-move", 18, 40])
    assert page.text_content("#sk3dCoords").startswith("scale")
    page.evaluate(EMIT, ["sk3d-up", None, None])
    page.evaluate(EMIT, ["sk3d-down", -40, -30])
    page.evaluate(EMIT, ["sk3d-up", None, None])
    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function(
        "async () => !(await import('/static/js/sketch3d.js')).sketch3DActive()",
        timeout=20000)
    page.wait_for_timeout(500)
    ents = _entities(server)
    assert ents["rectangle"]["w"] == pytest.approx(60, abs=0.01)
    assert ents["rectangle"]["h"] == pytest.approx(24, abs=0.01)
    assert page.errors == []


def test_scale_all_then_scale_selected(top_face_sketch, server):
    page = top_face_sketch
    # draw: rectangle (0,0)-(20,10) and circle centre (30,5) r 5
    page.evaluate(SET_TOOL, "rectangle")
    page.evaluate(CLICK, [0, 0, 1.0])
    page.evaluate(CLICK, [20, 10, 1.0])
    page.evaluate(SET_TOOL, "circle")
    page.evaluate(CLICK, [30, 5, 1.0])
    page.evaluate(CLICK, [35, 5, 1.0])

    EMIT = """
    async (args) => {
      const [kind, x, y] = args;
      const { bus } = await import('/static/js/bus.js');
      bus.emit(kind, x === null ? {} : { x, y, tol: 2.0 });
      await new Promise(r => setTimeout(r, 90));
    }
    """
    # 1) NOTHING selected -> grab the vertical arrow, drag +80mm = x4.
    #    bbox is 0..35 x 0..10 -> ruler at x=38, mid y=5.
    page.evaluate(SET_TOOL, None)                 # tool pick deselects
    page.evaluate(SCALE)
    page.evaluate(EMIT, ["sk3d-down", 38, 5])     # grab
    page.evaluate(EMIT, ["sk3d-move", 38, 85])    # x4, live
    page.evaluate(EMIT, ["sk3d-up", None, None])  # release: value stays
    page.evaluate(EMIT, ["sk3d-down", -20, -20])  # click away = finish
    page.evaluate(EMIT, ["sk3d-up", None, None])
    page.wait_for_timeout(200)

    # 2) SELECT the rectangle (click its left edge; now 80x40 at (40,20))
    #    -> grab its arrow (bbox 0..80 x 0..40 -> ruler x=83.2, mid y=20)
    #    and drag -40mm = x0.5 in place.
    page.evaluate(CLICK, [0, 20, 2.0])
    page.evaluate(SCALE)
    page.evaluate(EMIT, ["sk3d-down", 83, 20])    # grab
    page.evaluate(EMIT, ["sk3d-move", 83, -20])   # x0.5, live
    page.evaluate(EMIT, ["sk3d-up", None, None])
    page.evaluate(EMIT, ["sk3d-down", -30, 70])   # away = finish
    page.evaluate(EMIT, ["sk3d-up", None, None])
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
