"""E2E: Construct > Offset Plane (specs/offset-plane.md).

The user (2026-09-22): "offset plane only: I can just move the plane and draw
sketch whatever I want". Press Offset Plane, pick an origin plane or a flat
face, drag the arrow or type, OK — a construction plane appears as a tree row
and a translucent quad; Create Sketch right after lands on it (the plane is
the selection), or the quad is clicked during any later Create Sketch. The
plane's ✎ reopens the step and every sketch on it follows. Replaces the
sketch-side Offset step and the SKETCH tab's Move Plane of 2026-09-21.

Every number asserted here is the SERVER's: the feature's `plane_frame`, the
sketch plan's frame, the document's feature list.
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
ADD_PLANE = """
async (args) => {
  const [id, params, inputs] = args;
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add', { id, op: 'offset_plane', params, inputs }, 'add');
  await loadMesh(true);
}
"""
OPEN = "async () => (await import('/static/js/sketchplane.js')).openOffsetPlane()"
STAGE = """
async (args) => {
  const [kind, data] = args;
  const sp = await import('/static/js/sketchplane.js');
  await sp.stageOffsetPlane(kind, data);
}
"""
EDIT = """
async (fid) => {
  const sp = await import('/static/js/sketchplane.js');
  const doc = await (await fetch('/api/doc')).json();
  await sp.editOffsetPlane(doc.features.find(f => f.id === fid));
}
"""
STAGE_OPEN = "() => document.getElementById('planeDialog').style.display === 'block'"
STAGE_SHUT = "() => document.getElementById('planeDialog').style.display === 'none'"
PICK_ARMED = "() => document.getElementById('placeHint').style.display === 'block'"
IS_ACTIVE = "async () => (await import('/static/js/sketch3d.js')).sketch3DActive()"
NOT_ACTIVE = "async () => !(await import('/static/js/sketch3d.js')).sketch3DActive()"
TWEEN_DONE = "() => window.__vp.getControls().enabled === true"
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"
SELECTED = "async () => (await import('/static/js/state.js')).S.selected"
GHOST = "() => window.__vp.planeGhostInfo()"
PLANES = "() => window.__vp.constructionPlaneInfo()"
CREATE_SKETCH = "() => document.querySelector('.rbtn[title=\"Create Sketch\"]').click()"
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


def _doc(page):
    return page.evaluate("async () => (await fetch('/api/doc')).json()")


def _ok(page):
    page.click("#plOk")
    page.wait_for_function(STAGE_SHUT, timeout=15000)
    page.wait_for_timeout(600)


def _type(page, value):
    page.fill("#plOffset", value)
    page.dispatch_event("#plOffset", "input")


def _planes(doc):
    return [f for f in doc["features"] if f["op"] == "offset_plane"]


def test_offset_plane_from_xy_is_a_tree_row_drawn_where_it_says(plate):
    page = plate
    page.evaluate(OPEN)
    page.wait_for_function(PICK_ARMED, timeout=15000)
    assert "offset plane" in page.evaluate("document.getElementById('placeHint').textContent")
    page.evaluate(STAGE, ["plane", "XY"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.evaluate("document.getElementById('planeDialog').firstElementChild.textContent") \
        == "▱ Offset Plane"
    assert page.evaluate("document.getElementById('plWhat').textContent") == "the XY plane"
    assert page.evaluate(MODAL) == "Offset Plane", "the step holds the one-command lock"
    _type(page, "20")
    assert page.evaluate(GHOST)["position"][2] == pytest.approx(20, abs=1e-6)
    _ok(page)
    doc = _doc(page)
    ps = _planes(doc)
    assert len(ps) == 1 and ps[0]["id"] == "plane1" and ps[0]["status"] == "ok", ps
    assert ps[0]["params"] == {"plane": "XY", "offset": 20} and ps[0]["inputs"] == []
    assert ps[0]["plane_frame"]["origin"][2] == pytest.approx(20)
    assert doc["bodies"] == 1, "a plane is not a body"
    drawn = page.evaluate(PLANES)
    assert [p["id"] for p in drawn] == ["plane1"]
    assert drawn[0]["position"][2] == pytest.approx(20, abs=1e-6)
    assert drawn[0]["normal"] == pytest.approx([0, 0, 1], abs=1e-9)
    assert page.evaluate(SELECTED) == "plane1", "the new plane is the selection"
    assert page.evaluate(MODAL) is None
    assert page.evaluate(GHOST) is None
    assert page.errors == []


def test_create_sketch_right_after_lands_on_the_new_plane(plate):
    """Select-then-command: the plane Offset Plane just made is selected, so
    Create Sketch opens on it with no second pick; the sketch names the plane
    and an extrude of it stands at the plane's height."""
    page = plate
    page.evaluate(OPEN)
    page.wait_for_function(PICK_ARMED, timeout=15000)
    page.evaluate(STAGE, ["plane", "XY"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    _type(page, "20")
    _ok(page)
    page.evaluate(CREATE_SKETCH)
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    assert page.evaluate(PICK_ARMED) is False, "no pick was asked for"
    target = page.evaluate("window.__vp.getControls().target.toArray()")
    assert target[2] == pytest.approx(20, abs=1e-6), f"the grid must sit on the plane: {target}"
    assert page.evaluate(SELECTED) is None, "the selection was used up"
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    doc = _doc(page)
    s = [f for f in doc["features"] if f["op"] == "sketch"]
    assert len(s) == 1 and s[0]["status"] == "ok", s
    assert s[0]["params"]["plane"] == "plane1" and s[0]["params"]["offset"] == 0, s[0]["params"]
    # the geometry is where the plane is: an extrude of it starts at z = 20
    page.evaluate("""async (sid) => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/feature/add', { id: 'e', op: 'extrude', params: { amount: 5 },
                                           inputs: [sid] }, 'add');
    }""", s[0]["id"])
    doc = _doc(page)
    e = [f for f in doc["features"] if f["id"] == "e"][0]
    assert e["status"] == "ok" and e["volume"] == pytest.approx(20 * 10 * 5), e
    assert page.errors == []


def test_a_plane_off_a_face_goes_into_the_material_and_keeps_the_body(plate):
    page = plate
    page.evaluate(OPEN)
    page.wait_for_function(PICK_ARMED, timeout=15000)
    page.evaluate(STAGE, ["face", TOP_FACE])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.evaluate("document.getElementById('plWhat').textContent") == 'a face of "b"'
    assert page.evaluate("document.getElementById('plInto').textContent") == \
        "negative = into the material"
    _type(page, "-6")
    assert page.evaluate(GHOST)["position"][2] == pytest.approx(4, abs=1e-6)
    _ok(page)
    doc = _doc(page)
    p = _planes(doc)[0]
    assert p["inputs"] == ["b"] and p["params"]["offset"] == -6
    assert p["params"]["face_center"] == [0, 0, 10]
    assert p["plane_frame"]["origin"][2] == pytest.approx(4)
    assert doc["bodies"] == 1 and page.evaluate("window.__vp.bodyCount()") == 1, \
        "the body the plane is measured from stays on screen"
    assert page.errors == []


def test_clicking_the_plane_during_create_sketch_opens_a_sketch_on_it(plate):
    """The later path: a plane made earlier is clicked in the viewport during
    Create Sketch's pick (outside the body's silhouette, as the origin quads
    are — a body face under the cursor wins)."""
    page = plate
    page.evaluate(ADD_PLANE, ["lid", {"plane": "XY", "offset": 20}, []])
    page.wait_for_function("() => window.__vp.constructionPlaneInfo().length === 1", timeout=15000)
    page.evaluate("async () => (await import('/static/js/viewport.js')).setView('top')")
    page.wait_for_timeout(500)
    page.evaluate(CREATE_SKETCH)
    page.wait_for_function(PICK_ARMED, timeout=15000)
    # a point ON the plane, clear of the 60 x 40 plate seen from above (beyond
    # its 20 mm half-depth), and inside the canvas
    pt = page.evaluate("window.__vp.worldToScreen([0, 28, 20])")
    rect = page.evaluate("document.querySelector('#viewer canvas').getBoundingClientRect().toJSON()")
    assert pt and 0 < pt["cx"] < rect["width"] and 0 < pt["cy"] < rect["height"], (pt, rect)
    hits = {q["id"]: q["hits"] for q in page.evaluate("([x, y]) => window.__vp.planeQuadsAt(x, y)",
                                                       [pt["x"], pt["y"]])}
    assert hits["lid"] == 1, hits
    page.mouse.click(pt["x"], pt["y"])
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    target = page.evaluate("window.__vp.getControls().target.toArray()")
    assert target[2] == pytest.approx(20, abs=1e-6), target
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    s = [f for f in _doc(page)["features"] if f["op"] == "sketch"]
    assert len(s) == 1 and s[0]["params"]["plane"] == "lid" and s[0]["status"] == "ok", s
    assert page.errors == []


def test_editing_the_plane_moves_it_and_every_sketch_on_it(plate):
    page = plate
    page.evaluate(ADD_PLANE, ["lid", {"plane": "XY", "offset": 20}, []])
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/feature/add', { id: 's', op: 'sketch',
        params: { plane: 'lid', entities: [{ kind: 'rectangle', mode: 'add', x: 0, y: 0, w: 20, h: 10 }] },
        inputs: [] }, 'add');
      await postJSON('/api/feature/add', { id: 'e', op: 'extrude', params: { amount: 5 },
                                           inputs: ['s'] }, 'add');
    }""")
    page.wait_for_function("() => window.__vp.bodyCount() === 2", timeout=15000)
    page.evaluate(EDIT, "lid")
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert "Edit offset plane" in page.evaluate(
        "document.getElementById('planeDialog').firstElementChild.textContent")
    assert page.input_value("#plOffset") == "20"
    assert page.evaluate(GHOST)["position"][2] == pytest.approx(20, abs=1e-6)
    _type(page, "35")
    _ok(page)
    doc = _doc(page)
    assert _planes(doc)[0]["params"]["offset"] == 35
    assert _planes(doc)[0]["plane_frame"]["origin"][2] == pytest.approx(35)
    e = [f for f in doc["features"] if f["id"] == "e"][0]
    assert e["status"] == "ok" and e["volume"] == pytest.approx(1000)
    plan = page.evaluate("""async () => (await import('/static/js/api.js'))
      .planRequest({ tool: 'sketch', plane: 'lid', offset: 0 })""")
    assert plan["frame"]["origin"][2] == pytest.approx(35), "the sketch plane followed"
    assert page.evaluate(PLANES)[0]["position"][2] == pytest.approx(35, abs=1e-6)
    assert page.errors == []


FORMULA = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/parameters', { name: 'wall', expr: 4 }, 'param');
  await postJSON('/api/feature/add', { id: 'lid', op: 'offset_plane',
    params: { face: 'top', offset: '-wall' }, inputs: ['b'] }, 'add');
  await loadMesh(true);
}
"""


def test_ok_without_a_change_keeps_a_formula_offset(plate):
    """The rule the sketch-plane review proved (2026-09-22): a formula parameter
    is destroyed by any editor that reads it as a number and writes the number
    back. The box opens at the resolved -4; OK untouched must write nothing."""
    page = plate
    page.evaluate(FORMULA)
    page.wait_for_function("() => window.__vp.constructionPlaneInfo().length === 1", timeout=15000)
    assert _planes(_doc(page))[0]["plane_frame"]["origin"][2] == pytest.approx(6)
    page.evaluate(EDIT, "lid")
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    assert page.input_value("#plOffset") == "-4"
    _ok(page)
    assert _planes(_doc(page))[0]["params"]["offset"] == "-wall"
    # ...and in inches, where the box shows -0.1575 and would read back -4.0005
    page.evaluate("async () => { const s = await import('/static/js/settings.js');"
                  " s.SETTINGS.unit = 'in'; }")
    try:
        page.evaluate(EDIT, "lid")
        page.wait_for_function(STAGE_OPEN, timeout=15000)
        assert page.input_value("#plOffset") == "-0.1575", "not the inch view"
        _ok(page)
    finally:
        page.evaluate("async () => { const s = await import('/static/js/settings.js');"
                      " s.SETTINGS.unit = 'mm'; }")
    assert _planes(_doc(page))[0]["params"]["offset"] == "-wall"
    # a REAL move replaces the formula with the number, and the plane moves
    page.evaluate(EDIT, "lid")
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    _type(page, "-8")
    _ok(page)
    p = _planes(_doc(page))[0]
    assert p["params"]["offset"] == -8 and p["plane_frame"]["origin"][2] == pytest.approx(2)
    assert page.errors == []


def test_escape_adds_nothing_and_releases_the_lock(plate):
    page = plate
    page.evaluate(OPEN)
    page.wait_for_function(PICK_ARMED, timeout=15000)
    page.evaluate(STAGE, ["plane", "XZ"])
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    _type(page, "12")
    page.keyboard.press("Escape")
    page.wait_for_function(STAGE_SHUT, timeout=15000)
    assert page.evaluate(MODAL) is None
    assert page.evaluate(GHOST) is None
    assert _planes(_doc(page)) == []
    assert page.evaluate(PLANES) == []
    assert page.errors == []


def test_the_sketch_tab_has_no_move_plane_and_the_create_tab_has_offset_plane(plate):
    page = plate
    titles = page.evaluate("[...document.querySelectorAll('.rbtn')].map(b => b.title)")
    assert "Offset Plane" in titles and "Move Plane" not in titles, titles
    page.evaluate("async () => (await import('/static/js/sketcher.js')).openSketchEditor('XY')")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    titles = page.evaluate("[...document.querySelectorAll('.rbtn')].map(b => b.title)")
    assert "Move Plane" not in titles and "Finish Sketch" in titles, titles
    page.keyboard.press("Escape")
    assert page.errors == []


def test_the_extrude_TOOL_opens_on_a_sketch_drawn_on_a_plane(plate):
    """The user (2026-09-23): "I draw something on xz or yz plane, I cannot
    extrude that shape, but revolve is working". `toolplan._profile` asked
    `sketch.sketch_plane` for the profile's plane, which only knows the three
    principal names, so the Extrude TOOL refused every sketch on a plane row
    with `sketch: plane must be "XY", "XZ" or "YZ"`.

    The eight tests above never caught it because the one that extrudes does
    it through `/api/feature/add` — the op, not the tool. This one presses the
    tool the user presses, and takes it all the way to a body."""
    page = plate
    page.evaluate(OPEN)
    page.wait_for_function(PICK_ARMED, timeout=15000)
    page.evaluate(STAGE, ["plane", "XZ"])          # the plane the user named
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    _type(page, "20")
    _ok(page)
    page.evaluate(CREATE_SKETCH)
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    sid = [f for f in _doc(page)["features"] if f["op"] == "sketch"][0]["id"]

    # the TOOL, not the op: this is the press that used to answer a sentence
    page.evaluate("""async (sid) => {
      const m = await import('/static/js/extrude.js');
      await m.openExtrude(sid);
    }""", sid)
    page.wait_for_selector("#exOk", state="visible", timeout=15000)
    page.wait_for_timeout(800)
    page.fill("#exDist", "5")
    page.dispatch_event("#exDist", "input")
    page.wait_for_timeout(400)
    page.click("#exOk")
    page.wait_for_timeout(1500)

    doc = _doc(page)
    ext = [f for f in doc["features"] if f["op"] == "extrude"]
    assert len(ext) == 1, doc["features"]
    assert ext[0]["status"] == "ok", ext[0]["problems"]
    assert ext[0]["volume"] == pytest.approx(20 * 10 * 5, rel=1e-3), ext[0]["volume"]
    assert page.errors == []


def test_a_sketch_opened_after_the_plane_moved_draws_at_its_NEW_height(plate):
    """The browser caches a plane's frame under `${plane}|${offset}`, and that
    key was a pure function of the frame only while `plane` could name nothing
    but XY / XZ / YZ. A construction plane MOVES: open a sketch on it once,
    press ✎ on its row, and the second sketch opened on it drew on the frame
    the plane had BEFORE the edit — the grid, the model snaps and every click
    (the pointer ray is cast at that plane) 30 mm away from where make_sketch
    would build. Server-side the same cache keyed on a name that no longer
    decides the answer was the second half of the round-two review; this is the
    browser's copy of it (code review 2026-09-23)."""
    page = plate
    page.evaluate(ADD_PLANE, ["lid", {"plane": "XY", "offset": 20}, []])
    page.wait_for_function("() => window.__vp.constructionPlaneInfo().length === 1", timeout=15000)

    # open a sketch on the plane once — this is what fills the browser's cache
    page.evaluate("async () => (await import('/static/js/sketcher.js')).openSketchEditor('lid', 0)")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    assert page.evaluate("window.__vp.getControls().target.toArray()")[2] == pytest.approx(20, abs=1e-6)
    page.evaluate("async () => (await import('/static/js/sketcher.js')).cancelSketch()")
    page.wait_for_function(NOT_ACTIVE, timeout=15000)

    # move the plane with its own ✎, the way the user does
    page.evaluate(EDIT, "lid")
    page.wait_for_function(STAGE_OPEN, timeout=15000)
    _type(page, "50")
    _ok(page)
    assert _planes(_doc(page))[0]["plane_frame"]["origin"][2] == pytest.approx(50)
    page.wait_for_function(
        "() => Math.abs(window.__vp.constructionPlaneInfo()[0].position[2] - 50) < 1e-6",
        timeout=15000)

    # open a sketch on it again: the grid must be at 50, where the kernel builds
    page.evaluate("async () => (await import('/static/js/sketcher.js')).openSketchEditor('lid', 0)")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    target = page.evaluate("window.__vp.getControls().target.toArray()")
    assert target[2] == pytest.approx(50, abs=1e-6), \
        f"the sketch grid is at z {target[2]} but the plane it names is at 50"

    # and what is drawn on it lands there
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT, [-10, -5, 10, 5])
    page.evaluate(FINISH)
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    s = [f for f in _doc(page)["features"] if f["op"] == "sketch"]
    assert len(s) == 1 and s[0]["params"]["plane"] == "lid" and s[0]["status"] == "ok", s
    assert page.errors == []
