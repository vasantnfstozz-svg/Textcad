"""E2E: Revolve — the first tool born on the framework (LAUNCH-PLAN.md P3,
specs/revolve.md). Real clicks, and every geometric claim checked against the
kernel: the built volume against Pappus, the sweep direction against the
solid's own centre.
"""
import math

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

# a half-profile on XZ entirely at positive x: rectangle 10 x 6 centred (20, 10)
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'p', op: 'sketch',
      params: { plane: 'XZ', offset: 0,
                entities: [{ kind: 'rectangle', w: 10, h: 6, x: 20, y: 10,
                             mode: 'add' }] }, inputs: [] }, 'add');
}
"""
# the same profile centred on the origin: it crosses BOTH in-plane axes — since
# P3b the tool opens about one of its SIDES instead of refusing
BUILD_CENTRED = BUILD.replace("x: 20, y: 10", "x: 0, y: 0")
# a circle centred on the origin: crosses both axes AND has no straight edge
BUILD_CIRCLE_CENTRED = BUILD.replace(
    "{ kind: 'rectangle', w: 10, h: 6, x: 20, y: 10,", "{ kind: 'circle', r: 4, x: 0, y: 0,")
assert "circle" in BUILD_CIRCLE_CENTRED and "x: 0, y: 0" in BUILD_CIRCLE_CENTRED
# a bare box, and its top face picked the way the viewport records a pick
BUILD_BOX = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""
TOP_FACE = """
() => window.__vp.bodyObjsRaw()[0].data.faces.find(f => f.normal && f.normal[2] > 0.9)
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
TOP_PICKED = """
async () => {
  const { S } = await import('/static/js/state.js');
  return !!(S.pickedFace && S.pickedFace.normal && S.pickedFace.normal[2] > 0.9);
}
"""
# a box with a circle sketched on its top face, off the face's centre
BUILD_FACE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 's', op: 'sketch_on_face',
      params: { face: 'top', offset: 0,
                entities: [{ kind: 'circle', r: 4, x: 15, y: 0, mode: 'add' }] },
      inputs: ['b'] }, 'add');
}
"""
ADD_REVOLVE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'rv1', op: 'revolve', params: { axis: 'v' }, inputs: ['p'] }, 'add');   // no angle: the op's full turn
}
"""
BODY_CENTRE = """
() => {
  const b = window.__vp.bodyObjsRaw()[0];
  b.mesh.geometry.computeBoundingBox();
  return b.mesh.geometry.boundingBox.getCenter(b.mesh.position.clone()).toArray();
}
"""


def pappus(r_bar, area, deg):
    return 2 * math.pi * r_bar * area * abs(deg) / 360.0


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def press_revolve(page, fid):
    r = row(page, fid)
    r.hover()
    r.locator("button[title^='revolve this sketch']").click()


def open_revolve(page, fid):
    press_revolve(page, fid)
    page.wait_for_selector("#revolveDialog", state="visible", timeout=15000)


def ring_point(page, deg):
    return page.evaluate(
        "async d => (await import('/static/js/viewport.js')).taperRingPointScreen(d)", deg)


def feature(server, fid):
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    return next((f for f in doc["features"] if f["id"] == fid), None)


def setup(page, build):
    page.evaluate(build)
    page.wait_for_timeout(1500)


def test_open_from_the_tree_row_and_drag_the_ring(page, fresh_doc, server):
    """Honest zero, the gold axis, the ghost sweeping the kernel's way, one
    verified solid on release whose volume is Pappus's."""
    setup(page, BUILD)
    open_revolve(page, "p")
    assert page.input_value("#rvAngle") == "0"
    assert page.eval_on_selector("#rvAxis", "el => el.value") == "v"
    g = page.evaluate("() => window.__vp.gizmos()")
    assert g["axis"] and g["ring"] and g["lathe"], g
    assert page.evaluate("() => window.__vp.bodyCount()") == 0, "opening builds nothing"
    ax = page.evaluate("() => window.__vp.axisLineInfo()")
    for end in (ax["from"], ax["to"]):                    # the world Z axis
        assert abs(end[0]) < 1e-6 and abs(end[1]) < 1e-6, ax

    p0 = ring_point(page, 0)
    page.mouse.move(p0["x"], p0["y"])
    page.mouse.down()
    # a DRAGGED angle lands on round numbers (user 2026-09-07: "it goes to
    # 90.5 — it should recognise 0, 45, 90, 180"): whole degrees away from the
    # marks, and within 3° of a multiple of 45 the mark itself — a hand that
    # stops at 92 gets exactly 90 (viewport.js snapAngle)
    for d in (15, 30, 37.3, 60, 75, 92):
        p = ring_point(page, d)
        page.mouse.move(p["x"], p["y"])
        page.wait_for_timeout(40)
        if d == 37.3:
            assert page.input_value("#rvAngle") == "37", page.input_value("#rvAngle")
    ghost = page.evaluate("() => window.__vp.revolveGhostInfo()")
    assert ghost["visible"] and ghost["angle"] == 90, ghost
    assert ghost["centre"][1] > 0, "a positive sweep goes toward +y, like the kernel"
    page.mouse.up()
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    deg = float(page.input_value("#rvAngle"))
    assert deg == 90, deg
    f = feature(server, "revolve1")
    assert f and f["status"] == "ok", f
    assert f["volume"] == pytest.approx(pappus(20, 60, deg), rel=1e-3)
    centre = page.evaluate(BODY_CENTRE)
    assert centre[1] > 0, f"the solid must sit on the +y side: {centre}"
    assert page.errors == []


def test_full_turn_then_ok_commits_one_revolve(page, fresh_doc, server):
    setup(page, BUILD)
    open_revolve(page, "p")
    page.click("#rvFull")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    assert page.input_value("#rvAngle") == "360"
    page.click("#rvOk")
    page.wait_for_selector("#revolveDialog", state="hidden")
    page.wait_for_timeout(800)
    f = feature(server, "revolve1")
    assert f["status"] == "ok" and f["params"]["axis"] == "v"
    assert f["volume"] == pytest.approx(pappus(20, 60, 360), rel=1e-4)
    assert "Revolve created" in page.text_content("#chatLog")
    assert page.errors == []


def test_edit_reopens_at_the_stored_angle_and_cancel_restores(page, fresh_doc, server):
    setup(page, BUILD)
    page.evaluate(ADD_REVOLVE)
    page.wait_for_timeout(1200)
    r = row(page, "rv1")
    r.hover()
    r.locator("button[title^='edit this revolve']").click()
    page.wait_for_selector("#revolveDialog", state="visible")
    assert "Edit rv1" in page.text_content("#revolveDialog .exhead")
    assert page.input_value("#rvAngle") == "360"
    assert page.evaluate("() => window.__vp.gizmos().ring")
    page.fill("#rvAngle", "90")
    page.wait_for_timeout(1800)
    assert feature(server, "rv1")["volume"] == pytest.approx(pappus(20, 60, 90), rel=1e-4)
    page.click("#rvCancel")
    page.wait_for_selector("#revolveDialog", state="hidden")
    page.wait_for_timeout(1800)
    f = feature(server, "rv1")
    assert f["status"] == "ok" and f["params"].get("angle", 360) == 360
    assert f["volume"] == pytest.approx(pappus(20, 60, 360), rel=1e-4)
    assert page.errors == []


def test_a_profile_across_the_axis_is_refused_with_a_sentence(page, fresh_doc, server):
    """A centred CIRCLE: it crosses both axes and has no straight edge to turn
    about (a centred rectangle opens about a side since P3b — below)."""
    setup(page, BUILD_CIRCLE_CENTRED)
    press_revolve(page, "p")
    page.wait_for_timeout(1200)
    assert page.locator("#revolveDialog").is_hidden(), "the tool must not open"
    chat = page.text_content("#chatLog")
    assert "cannot be revolved" in chat and "crosses" in chat and "one side" in chat
    assert "no straight edge" in chat
    # the gizmos this refusal must leave behind: none. Named one by one, not as
    # the whole dict — that hook grows a key every time a tool adds a handle
    # (P4 added glow/edgePick and broke this assertion, caught 2026-09-04).
    g = page.evaluate("() => window.__vp.gizmos()")
    assert not any(g[k] for k in ("arrow", "ghost", "ring", "axis", "lathe")), g
    assert page.errors == []


def test_cut_into_the_body_the_sketch_sits_on(page, fresh_doc, server):
    """A circle on the box's top face, revolved a full turn as a Cut: the
    default target is the box, the groove takes material, one body remains."""
    setup(page, BUILD_FACE)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    plate = feature(server, "b")["volume"]
    open_revolve(page, "s")
    page.select_option("#rvOp", "cut")
    page.wait_for_timeout(400)
    assert page.eval_on_selector("#rvTarget", "el => el.value") == "b"
    page.click("#rvFull")
    for _ in range(80):
        doc = httpx.get(f"{server}/api/doc", timeout=30).json()
        cuts = [f for f in doc["features"] if f["op"] == "cut"]
        if cuts and cuts[0]["status"] in ("ok", "failed"):
            break
        page.wait_for_timeout(250)
    page.click("#rvOk")
    page.wait_for_selector("#revolveDialog", state="hidden")
    page.wait_for_timeout(1000)
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    cut = next(f for f in doc["features"] if f["op"] == "cut")
    assert cut["status"] == "ok", cut
    assert cut["inputs"][0] == "b"
    assert cut["volume"] < plate
    assert (doc["result_pieces"] or 1) == 1
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.errors == []


# ------------------------------------------------------------------- P3b ---

def test_a_rectangle_across_the_axis_opens_about_its_own_side(page, fresh_doc, server):
    """P3 refused this profile. Now the Axis list greys u and v (with the
    reason) and opens on the longest side; a full turn is a solid cylinder."""
    setup(page, BUILD_CENTRED)
    open_revolve(page, "p")
    axis = page.eval_on_selector("#rvAxis", "el => el.value")
    assert axis.startswith("e"), axis
    opts = page.eval_on_selector_all("#rvAxis option",
                                     "os => os.map(o => [o.value, o.disabled, o.title])")
    by = {v: (d, t) for v, d, t in opts}
    assert by["u"][0] and "crosses u" in by["u"][1] and by["v"][0] and "crosses v" in by["v"][1]
    assert page.evaluate("() => window.__vp.bodyCount()") == 0, "opening builds nothing"
    page.click("#rvFull")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.click("#rvOk")
    page.wait_for_selector("#revolveDialog", state="hidden")
    page.wait_for_timeout(800)
    f = feature(server, "revolve1")
    assert f["status"] == "ok", f
    assert isinstance(f["params"]["axis"], list), "an edge axis is stored as a line"
    # the 10 x 6 rectangle about a 10 mm side: centroid 3 mm off it, area 60
    assert f["volume"] == pytest.approx(pappus(3, 60, 360), rel=1e-4)
    assert page.errors == []


def test_a_picked_face_revolves_about_its_edge_and_joins_the_body(page, fresh_doc, server):
    """Fusion's gap the user hit: click a flat face, press Revolve. The panel
    opens in face mode on the face's longest edge, Join targets the body, a
    typed quarter turn builds the Pappus volume and fuses into ONE body. The
    two steps under test are REAL: a pixel click on the face in the viewport
    and the Revolve button in the ribbon (R5 — no shortcut for the step
    under test; the face picker has had its own bugs)."""
    setup(page, BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)
    box = feature(server, "b")["volume"]
    top = page.evaluate(TOP_FACE)
    sp = page.evaluate(TO_SCREEN, top["center"])
    page.mouse.click(sp["x"], sp["y"])                      # the user's pick
    page.wait_for_function(TOP_PICKED, timeout=15000)
    page.click("#ribbon .rbtn[title='revolve']")            # the user's button
    page.wait_for_selector("#revolveDialog", state="visible", timeout=15000)
    assert page.eval_on_selector("#rvProfile", "el => el.value") == "(selected face)"
    assert page.eval_on_selector("#rvOp", "el => el.value") == "join"
    assert page.eval_on_selector("#rvTarget", "el => el.value") == "b"
    page.wait_for_function("() => document.querySelector('#rvAxis').value === 'e1'", timeout=15000)
    label = page.eval_on_selector("#rvAxis", "el => el.selectedOptions[0].textContent")
    assert "60 mm" in label, label
    assert page.evaluate("() => window.__vp.gizmos().axis"), "the gold line is on the edge"
    page.fill("#rvAngle", "90")
    fuse = lambda: next((f for f in httpx.get(f"{server}/api/doc", timeout=30).json()["features"]
                         if f["op"] == "fuse"), None)
    for _ in range(80):
        j = fuse()
        if j and j["status"] in ("ok", "failed"):
            break
        page.wait_for_timeout(250)
    page.click("#rvOk")
    page.wait_for_selector("#revolveDialog", state="hidden")
    page.wait_for_timeout(1000)
    f = feature(server, "revolve1")               # the framework names features after the TOOL
    assert f["op"] == "revolve_face" and f["status"] == "ok" and f["inputs"] == ["b"], f
    # the 60 x 40 face about its 60 mm side: centroid 20 mm off it, area 2400
    assert f["volume"] == pytest.approx(pappus(20, 2400, 90), rel=1e-4)
    join = fuse()
    assert join and join["status"] == "ok" and set(join["inputs"]) == {"b", "revolve1"}, join
    assert join["volume"] > box
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.errors == []


def test_symmetric_and_two_sides_sweep_the_other_way_too(page, fresh_doc, server):
    setup(page, BUILD)
    open_revolve(page, "p")
    page.select_option("#rvDir", "sym")
    assert page.locator("#rvAngle2Row").is_hidden()
    page.fill("#rvAngle", "45")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(600)
    f = feature(server, "revolve1")
    assert f["params"]["both"] is True
    assert f["volume"] == pytest.approx(pappus(20, 60, 90), rel=1e-4)    # 45 EACH side
    centre = page.evaluate(BODY_CENTRE)
    assert abs(centre[1]) < 0.05, f"symmetric: centred on the sketch plane, got {centre}"
    page.select_option("#rvDir", "two")
    assert page.locator("#rvAngle2Row").is_visible()
    page.fill("#rvAngle2", "90")
    page.wait_for_timeout(1800)
    f = feature(server, "revolve1")
    assert f["params"]["angle2"] == 90 and f["params"]["both"] is False
    assert f["volume"] == pytest.approx(pappus(20, 60, 135), rel=1e-4)
    centre = page.evaluate(BODY_CENTRE)
    assert centre[1] < 0, f"the bigger second side pulls the body to -y: {centre}"
    page.click("#rvFull")                                    # a full turn is one side, 360
    page.wait_for_timeout(1800)
    assert page.eval_on_selector("#rvDir", "el => el.value") == "one"
    f = feature(server, "revolve1")
    assert f["volume"] == pytest.approx(pappus(20, 60, 360), rel=1e-4)
    assert page.errors == []
