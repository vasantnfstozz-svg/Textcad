"""E2E: Create Sketch's Offset step — move the sketch plane before drawing.

The user (2026-09-21) could not stack loft sections or draw above a body:
every sketch opened AT the picked plane or face, offset 0, with no way to
move it. Now the pick lands in a step (sketchplane.js): the plane is drawn
where the sketch will open, an arrow along its normal and an Offset box move
it, OK / Enter opens the sketch there, Esc goes back. The offset is the sketch
feature's own `offset` parameter.

Locked in, in a real browser: the ghost and the arrow follow the typed value;
Enter opens sketch mode with the grid AT the offset (the camera target sits on
the shifted plane, the same fact test_origin_planes reads); Finish stores the
offset on the feature — a plane sketch at z = 20, a face sketch 5 mm into the
plate; the step holds the one-command lock and Esc releases it.
"""
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await loadMesh(true);
}
"""
STAGE = """
async (args) => {
  const [kind, data] = args;
  const sp = await import('/static/js/sketchplane.js');
  await sp.stageSketchPlane(kind, data);
}
"""
STAGE_OPEN = "() => document.getElementById('planeDialog').style.display === 'block'"
STAGE_SHUT = "() => document.getElementById('planeDialog').style.display === 'none'"
IS_ACTIVE = "async () => (await import('/static/js/sketch3d.js')).sketch3DActive()"
NOT_ACTIVE = "async () => !(await import('/static/js/sketch3d.js')).sketch3DActive()"
TWEEN_DONE = "() => window.__vp.getControls().enabled === true"
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"
ARROW = "async () => (await import('/static/js/viewport.js')).extrudeArrowDebug()"
DRAW_RECT = """
async (args) => {
  const [ax, ay, bx, by] = args;
  const sk = await import('/static/js/sketcher.js');
  const { bus } = await import('/static/js/bus.js');
  sk.setSketchTool('rectangle');
  bus.emit('sk3d-down', { x: ax, y: ay, tol: 2 }); bus.emit('sk3d-up', {});
  bus.emit('sk3d-down', { x: bx, y: by, tol: 2 }); bus.emit('sk3d-up', {});
  sk.setSketchTool('rectangle');
}
"""
FINISH = "async () => (await import('/static/js/sketcher.js')).finishSketch()"
TOP_FACE = {"center": [0, 0, 10], "normal": [0, 0, 1], "area": 2400, "body": "b"}


@pytest.fixture()
def plate(page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    return page


def _finish_with_a_rectangle(page):
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    return page.evaluate("async () => (await fetch('/api/doc')).json()")


def test_plane_sketch_opens_and_is_stored_at_the_typed_offset(plate):
    page = plate
    page.evaluate(STAGE, ["plane", "XY"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.evaluate(MODAL) == "Sketch plane"
    ghost = page.evaluate("window.__vp.planeGhostInfo()")
    assert ghost["offset"] == 0 and abs(ghost["position"][2]) < 1e-6, ghost
    assert ghost["normal"] == [0, 0, 1] and ghost["lines"] == 0, ghost
    assert page.evaluate(ARROW)["amount"] == 0

    page.fill("#plOffset", "20")                    # typing moves ghost + arrow
    ghost = page.evaluate("window.__vp.planeGhostInfo()")
    assert ghost["position"][2] == pytest.approx(20, abs=1e-6), ghost
    assert page.evaluate(ARROW)["amount"] == 20

    page.press("#plOffset", "Enter")                # Enter = OK
    page.wait_for_function(STAGE_SHUT, timeout=15000)
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    assert page.evaluate(MODAL) is None, "the step must release the lock"
    assert page.evaluate("window.__vp.planeGhostInfo()") is None
    target = page.evaluate("window.__vp.getControls().target.toArray()")
    assert target[2] == pytest.approx(20, abs=1e-6), f"grid must sit at z=20: {target}"

    doc = _finish_with_a_rectangle(page)
    sketches = [f for f in doc["features"] if f["op"] == "sketch"]
    assert len(sketches) == 1, [(f["id"], f["op"]) for f in doc["features"]]
    s = sketches[0]
    assert s["status"] == "ok" and s["params"]["plane"] == "XY", s
    assert s["params"]["offset"] == 20, s["params"]
    assert page.errors == []


def test_face_sketch_carries_the_offset_into_the_material(plate):
    page = plate
    page.evaluate(STAGE, ["face", TOP_FACE])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.evaluate("document.getElementById('plWhat').textContent") == 'a face of "b"'
    assert page.evaluate("document.getElementById('plInto').textContent") == \
        "negative = into the material"
    ghost = page.evaluate("window.__vp.planeGhostInfo()")
    assert ghost["position"][2] == pytest.approx(10, abs=1e-6), ghost   # ON the top face
    assert ghost["lines"] == 1, ghost                                   # the face outline

    page.fill("#plOffset", "-5")
    ghost = page.evaluate("window.__vp.planeGhostInfo()")
    assert ghost["position"][2] == pytest.approx(5, abs=1e-6), ghost
    page.click("#plOk")
    page.wait_for_function(STAGE_SHUT, timeout=15000)

    doc = _finish_with_a_rectangle(page)
    face_sketches = [f for f in doc["features"] if f["op"] == "sketch_on_face"]
    assert len(face_sketches) == 1, [(f["id"], f["op"]) for f in doc["features"]]
    s = face_sketches[0]
    assert s["status"] == "ok" and s["inputs"] == ["b"], s
    assert s["params"]["offset"] == -5, s["params"]
    assert page.errors == []


def test_escape_closes_the_step_and_releases_the_lock(plate):
    page = plate
    page.evaluate(STAGE, ["plane", "XZ"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    # another tool must refuse while the step is open (one command at a time)
    refused = page.evaluate("async () => (await import('/static/js/dialogs.js')).modalGuard()")
    assert refused is True
    page.keyboard.press("Escape")
    page.wait_for_function(STAGE_SHUT, timeout=15000)
    assert page.evaluate(MODAL) is None
    assert page.evaluate(NOT_ACTIVE) is True
    assert page.evaluate("window.__vp.planeGhostInfo()") is None
    assert page.evaluate(ARROW) is None
    assert page.errors == []
