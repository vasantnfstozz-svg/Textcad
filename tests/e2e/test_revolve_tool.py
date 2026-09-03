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
# the same profile centred on the origin: it crosses BOTH in-plane axes
BUILD_CENTRED = BUILD.replace("x: 20, y: 10", "x: 0, y: 0")
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
    { id: 'rv1', op: 'revolve', params: { axis: 'v', angle: 360 }, inputs: ['p'] }, 'add');
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
    for d in (15, 30, 45, 60, 75, 90):
        p = ring_point(page, d)
        page.mouse.move(p["x"], p["y"])
        page.wait_for_timeout(40)
    ghost = page.evaluate("() => window.__vp.revolveGhostInfo()")
    assert ghost["visible"] and 80 < ghost["angle"] < 100, ghost
    assert ghost["centre"][1] > 0, "a positive sweep goes toward +y, like the kernel"
    page.mouse.up()
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    deg = float(page.input_value("#rvAngle"))
    assert 80 <= deg <= 100, deg
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
    assert f["params"]["angle"] == 360
    assert f["volume"] == pytest.approx(pappus(20, 60, 360), rel=1e-4)
    assert page.errors == []


def test_a_profile_across_the_axis_is_refused_with_a_sentence(page, fresh_doc, server):
    setup(page, BUILD_CENTRED)
    press_revolve(page, "p")
    page.wait_for_timeout(1200)
    assert page.locator("#revolveDialog").is_hidden(), "the tool must not open"
    chat = page.text_content("#chatLog")
    assert "cannot be revolved" in chat and "crosses" in chat and "one side" in chat
    assert page.evaluate("() => window.__vp.gizmos()") == {
        "arrow": False, "ghost": False, "ring": False, "axis": False, "lathe": False}
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
