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


MOVE = "async () => (await import('/static/js/sketchplane.js')).moveSketchPlane()"
ENTS = "async () => (await import('/static/js/sketcher.js')).sketchEntities()"


def test_move_plane_inside_an_open_sketch_keeps_the_shapes(plate):
    """The user's follow-up: shapes drawn, THEN the plane has to move. The
    SKETCH tab's Move Plane re-planes the open sketch at the new offset; the
    entities are plane-local so they ride along, and Finish stores the new
    offset."""
    page = plate
    page.evaluate("async () => (await import('/static/js/sketcher.js')).openSketchEditor('XY')")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    assert len(page.evaluate(ENTS)) == 1

    page.evaluate(MOVE)
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.evaluate("document.getElementById('planeDialog').firstElementChild.textContent") \
        == "✎ Move sketch plane"
    assert page.evaluate(IS_ACTIVE) is True, "the sketch stays open under the step"
    page.fill("#plOffset", "15")
    assert page.evaluate("window.__vp.planeGhostInfo()")["position"][2] == pytest.approx(15, abs=1e-6)
    page.press("#plOffset", "Enter")
    page.wait_for_function(STAGE_SHUT, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    assert page.evaluate(IS_ACTIVE) is True
    target = page.evaluate("window.__vp.getControls().target.toArray()")
    assert target[2] == pytest.approx(15, abs=1e-6), f"grid must now sit at z=15: {target}"
    ents = page.evaluate(ENTS)
    assert len(ents) == 1 and ents[0]["w"] == pytest.approx(20) and ents[0]["h"] == pytest.approx(10), ents

    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    s = [f for f in doc["features"] if f["op"] == "sketch"]
    assert len(s) == 1 and s[0]["status"] == "ok", s
    assert s[0]["params"]["offset"] == 15, s[0]["params"]
    assert page.errors == []


def test_move_plane_while_editing_a_face_sketch_updates_its_offset(plate):
    """An existing face sketch reopened from the tree, its plane moved 4 mm
    into the plate, Finish: the feature's offset changes and it rebuilds."""
    page = plate
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      const { loadMesh } = await import('/static/js/viewport.js');
      await postJSON('/api/feature/add', { id: 'fs', op: 'sketch_on_face',
        params: { face: 'top', offset: 0,
                  entities: [{ kind: 'rectangle', x: 0, y: 0, w: 20, h: 10, mode: 'add' }] },
        inputs: ['b'] }, 'add');
      await loadMesh(true);
    }""")
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      const { S } = await import('/static/js/state.js');
      const doc = await (await fetch('/api/doc')).json();
      S.lastDoc = doc;
      await sk.editSketch(doc.features.find(f => f.id === 'fs'));
    }""")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.evaluate(MOVE)
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.evaluate("document.getElementById('plInto').textContent") == \
        "negative = into the material"
    page.fill("#plOffset", "-4")
    page.click("#plOk")
    page.wait_for_function(STAGE_SHUT, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(800)
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    fs = next(f for f in doc["features"] if f["id"] == "fs")
    assert fs["status"] == "ok", fs
    assert fs["params"]["offset"] == -4, fs["params"]
    assert len(fs["params"]["entities"]) == 1, fs["params"]
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


# ---- the review pass of 2026-09-22 (range 1c77d9f..bc136be) added from here:
# the flows the build's own tests did not drive, and the two findings it made
GHOST = "() => window.__vp.planeGhostInfo()"
SECTION = "async () => (await import('/static/js/viewport.js')).sectionInfo()"


def _ok(page):
    page.click("#plOk")
    page.wait_for_function(STAGE_SHUT, timeout=15000)


def _doc(page):
    return page.evaluate("async () => (await fetch('/api/doc')).json()")


def test_move_plane_on_a_new_face_sketch(plate):
    """Create Sketch on the top face at 0, draw, then Move Plane to -6: the
    sketch that is CREATED must carry offset -6."""
    page = plate
    page.evaluate(STAGE, ["face", TOP_FACE])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    _ok(page)                                   # open it at 0, the old flow
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    assert len(page.evaluate(ENTS)) == 1

    page.evaluate(MOVE)
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.evaluate("document.getElementById('plWhat').textContent") == 'a face of "b"'
    assert page.evaluate("document.getElementById('plInto').textContent") == \
        "negative = into the material"
    page.fill("#plOffset", "-6")
    page.dispatch_event("#plOffset", "input")
    assert page.evaluate(GHOST)["position"][2] == pytest.approx(4, abs=1e-6)
    _ok(page)
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(300)
    assert len(page.evaluate(ENTS)) == 1, "the rectangle must ride along"

    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    doc = _doc(page)
    fs = [f for f in doc["features"] if f["op"] == "sketch_on_face"]
    assert len(fs) == 1, [(f["id"], f["op"]) for f in doc["features"]]
    assert fs[0]["params"]["offset"] == -6, fs[0]["params"]
    assert fs[0]["status"] == "ok", fs[0]
    assert page.errors == []


def test_move_plane_twice_in_one_sketch(plate):
    page = plate
    page.evaluate(STAGE, ["plane", "XY"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    _ok(page)
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])

    for value in ("12", "4"):
        page.evaluate(MOVE)
        page.wait_for_function(STAGE_OPEN, timeout=15000)
        page.fill("#plOffset", value)
        page.dispatch_event("#plOffset", "input")
        _ok(page)
        page.wait_for_function(IS_ACTIVE, timeout=15000)
        page.wait_for_function(TWEEN_DONE, timeout=15000)
        page.wait_for_timeout(300)
        assert len(page.evaluate(ENTS)) == 1, f"shapes lost at {value}"

    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    sk = [f for f in _doc(page)["features"] if f["op"] == "sketch"]
    assert len(sk) == 1 and sk[0]["params"]["offset"] == 4, sk
    assert page.errors == []


def test_section_view_gets_its_arrow_back_after_the_step(plate):
    page = plate
    page.evaluate("async () => (await import('/static/js/section.js')).openSection()")
    page.wait_for_timeout(400)
    before = page.evaluate(SECTION)
    assert before and before["ownsArrow"], before

    page.evaluate(STAGE, ["plane", "XY"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    during = page.evaluate(SECTION)
    page.keyboard.press("Escape")
    page.wait_for_function(STAGE_SHUT, timeout=15000)
    page.wait_for_timeout(300)
    after = page.evaluate(SECTION)
    assert page.evaluate(MODAL) is None
    assert after and after["ownsArrow"], f"before={before} during={during} after={after}"
    assert page.evaluate(
        "async () => (await import('/static/js/section.js')).isSectionOn()") is True
    assert page.errors == []


def test_the_arrow_is_draggable_and_its_value_is_what_is_stored(plate):
    page = plate
    page.evaluate(STAGE, ["plane", "XY"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    axis = page.evaluate(
        "async () => (await import('/static/js/viewport.js')).extrudeArrowAxisScreen()")
    assert axis, "no arrow to grab"
    mid = {"x": (axis["base"]["x"] + axis["tip"]["x"]) / 2,
           "y": (axis["base"]["y"] + axis["tip"]["y"]) / 2}
    page.mouse.move(mid["x"], mid["y"])
    page.mouse.down()
    page.mouse.move(mid["x"] + (axis["tip"]["x"] - axis["base"]["x"]) * 1.5,
                    mid["y"] + (axis["tip"]["y"] - axis["base"]["y"]) * 1.5, steps=8)
    page.mouse.up()
    box = float(page.input_value("#plOffset"))
    ghost = page.evaluate(GHOST)
    assert box != 0, "the drag moved nothing"
    assert ghost["position"][2] == pytest.approx(box, abs=1e-6), (box, ghost)
    _ok(page)
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    sk = [f for f in _doc(page)["features"] if f["op"] == "sketch"]
    assert sk[0]["params"]["offset"] == pytest.approx(box, abs=1e-9), (sk[0]["params"], box)
    assert page.errors == []


FORMULA_BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await postJSON('/api/parameters', { name: 'wall', expr: 4 }, 'param');
  await postJSON('/api/feature/add',
    { id: 'fs', op: 'sketch_on_face',
      params: { face: 'top', offset: '-wall',
                entities: [{ kind: 'circle', mode: 'add', x: 0, y: 0, r: 6 }] },
      inputs: ['b'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'boss', op: 'extrude', params: { amount: 6 }, inputs: ['fs'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'j', op: 'fuse', params: {}, inputs: ['b', 'boss'] }, 'add');
  await loadMesh(true);
}
"""
EDIT = """
async (fid) => {
  const { bus } = await import('/static/js/bus.js');
  const doc = await (await fetch('/api/doc')).json();
  bus.emit('edit-sketch', doc.features.find(f => f.id === fid));
}
"""


def test_finishing_a_formula_offset_sketch_keeps_the_formula(page, fresh_doc):
    """A sketch whose `offset` is a NAMED-PARAMETER formula ("-wall"): opening
    it to look at it and pressing Finish Sketch must not turn the formula into
    a number, and must not move the sketch plane."""
    page.evaluate(FORMULA_BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    doc0 = _doc(page)
    before = [f for f in doc0["features"] if f["id"] == "fs"][0]
    assert before["params"]["offset"] == "-wall", before["params"]
    vol0 = doc0["result_volume"]

    page.evaluate(EDIT, "fs")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(300)
    page.evaluate(FINISH)                      # nothing changed
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(800)

    doc1 = _doc(page)
    after = [f for f in doc1["features"] if f["id"] == "fs"][0]
    assert doc1["result_volume"] == pytest.approx(vol0, rel=1e-9), (
        f"the part changed shape: {vol0} -> {doc1['result_volume']} mm3")
    assert after["params"]["offset"] == "-wall", (
        f"the formula was replaced by {after['params']['offset']!r} — "
        f"the sketch plane moved from -4 mm to that")
    assert page.errors == []


def test_the_offset_step_refuses_while_another_tool_holds_the_lock(plate):
    """Create Sketch leaves a plane PICK pending; opening Measure does not
    cancel it (and the viewport routes a click to the pick before its own
    picking), so the pick can land while Measure holds the one-command lock.
    The step must refuse, not take the lock off the tool that owns it."""
    page = plate
    page.evaluate("async () => (await import('/static/js/measure.js')).openMeasure()")
    page.wait_for_timeout(200)
    assert page.evaluate(MODAL) == "Measure"

    page.evaluate(STAGE, ["plane", "XY"])
    page.wait_for_timeout(400)
    assert page.evaluate(STAGE_SHUT), "the Offset step opened over Measure"
    assert page.evaluate(MODAL) == "Measure", "Measure lost its lock"
    assert page.evaluate(
        "() => document.getElementById('measureDialog').style.display") == "block"
    assert page.errors == []


def test_move_plane_ok_without_a_change_keeps_the_formula(page, fresh_doc):
    """Move Plane opened on a formula-offset sketch shows the RESOLVED number
    (-4). Pressing OK without touching it is a no-op, and a no-op must not
    turn the formula into that number."""
    page.evaluate(FORMULA_BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.evaluate(EDIT, "fs")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(300)

    page.evaluate(MOVE)
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert float(page.input_value("#plOffset")) == pytest.approx(-4),         "the box must open at the RESOLVED value of the formula"
    _ok(page)                                   # OK, nothing changed
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(300)
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(800)

    after = [f for f in _doc(page)["features"] if f["id"] == "fs"][0]
    assert after["params"]["offset"] == "-wall", after["params"]
    assert page.errors == []
