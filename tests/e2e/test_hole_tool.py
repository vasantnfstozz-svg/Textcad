"""E2E: the Hole tool (LAUNCH-PLAN.md P4, specs/hole.md). The steps under test
are REAL — a pixel click on the face where the hole goes, the ribbon button,
the arrow drag — and every geometric claim is checked against the kernel: the
volume a hole takes away, where its centre landed, what Cancel put back.
"""
import math
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

PI = math.pi

# a 60 x 40 x 12 plate centred on the origin (blocks.plate): top face at z = +6
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
  return !!(S.pickedFace && S.pickedFace.normal && S.pickedFace.normal[2] > 0.9
            && S.pickedFace.point);
}
"""
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"
PT = [10.0, 5.0, 6.0]            # where the user clicks the top face: 10 right, 5 up of its centre


def features(server):
    return httpx.get(f"{server}/api/doc", timeout=30).json()["features"]


def feature(server, fid):
    return next((f for f in features(server) if f["id"] == fid), None)


def wait_feature(server, fid, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] in ("ok", "failed"):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid} never finished building")


def wait_volume(server, fid, expected, timeout=20, rel=1e-4):
    """poll until the feature's kernel-measured volume is `expected`"""
    t0 = time.time()
    f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] == "ok" and f["volume"] == pytest.approx(expected, rel=rel):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid} never reached volume {expected}: {f}")


def wait_at(server, fid, at, timeout=20):
    t0 = time.time()
    f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] == "ok" and f["params"].get("at") == pytest.approx(at, abs=1e-3):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid} never moved to {at}: {f}")


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def setup(page):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)


def open_hole_at(page, pt):
    """the user's steps, for real: a pixel click on the face where the hole
    goes, then the Hole button in the ribbon (R5 — no shortcut for the step
    under test: the face pick now carries the point, and that is what is tested)"""
    sp = page.evaluate(TO_SCREEN, pt)
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_function(TOP_PICKED, timeout=15000)
    page.click("#ribbon .rbtn[title='hole']")
    page.wait_for_selector("#holeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().hole", timeout=15000)   # the plan landed


def drag_arrow(page, px):
    """grab the arrow at its middle and push it the way it points on screen"""
    ax = page.evaluate(
        "async () => (await import('/static/js/viewport.js')).extrudeArrowAxisScreen()")
    assert ax, "no arrow to drag"
    bx, by, tx, ty = ax["base"]["x"], ax["base"]["y"], ax["tip"]["x"], ax["tip"]["y"]
    L = ((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5
    ux, uy = (tx - bx) / L, (ty - by) / L
    mx, my = (bx + tx) / 2, (by + ty) / 2
    page.mouse.move(mx, my)
    page.mouse.down()
    for k in range(1, 7):
        page.mouse.move(mx + ux * px * k / 6, my + uy * px * k / 6)
        page.wait_for_timeout(30)
    page.mouse.up()


# ------------------------------------------------------------------ journeys --

def test_click_the_face_press_hole_type_a_depth_and_ok(page, fresh_doc, server):
    """Honest zero: the panel opens with the circle where the face was clicked,
    the arrow into the plate, depth 0 and nothing built; a typed depth cuts
    exactly a cylinder; OK leaves ONE hole row and no combiner."""
    setup(page)
    box = feature(server, "b")["volume"]
    open_hole_at(page, PT)
    assert page.input_value("#hoProfile") == "(selected face)"
    assert page.input_value("#hoDepth") == "0" and page.input_value("#hoDia") == "6"
    assert page.input_value("#hoOp") == "new", "the op eats its body: no Join / Cut"
    assert not page.is_visible("#hoTargetRow")
    m = page.evaluate("() => window.__vp.holeMarkerInfo()")
    assert m["centre"] == pytest.approx(PT, abs=0.05) and m["radius"] == pytest.approx(3)
    assert page.evaluate("() => window.__vp.gizmos().arrow"), "the depth arrow is up"
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert feature(server, "hole1") is None, "opening builds nothing"
    page.fill("#hoDepth", "8")
    f = wait_feature(server, "hole1")
    assert f["op"] == "hole" and f["status"] == "ok" and f["inputs"] == ["b"], f
    assert f["volume"] == pytest.approx(box - PI * 9 * 8, rel=1e-4)
    assert f["params"]["at"] == pytest.approx([10, 5], abs=1e-3)
    page.click("#hoOk")
    page.wait_for_selector("#holeDialog", state="hidden")
    page.wait_for_timeout(800)
    assert row(page, "hole1").count() == 1
    assert not any(x["op"] in ("cut", "fuse") for x in features(server)), "no combiner"
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert not page.evaluate("() => window.__vp.gizmos().hole"), "the marker went with the panel"
    assert page.errors == []


def test_drag_the_arrow_into_the_plate_then_through_all(page, fresh_doc, server):
    """the arrow drives the depth INTO the material (one rebuild on release);
    Through all takes the arrow away and runs the hole out the far side"""
    setup(page)
    box = feature(server, "b")["volume"]
    open_hole_at(page, PT)
    drag_arrow(page, 60)
    f = wait_feature(server, "hole1")
    depth = float(page.input_value("#hoDepth"))
    assert depth > 0, "the drag set a depth"
    assert f["status"] == "ok" and f["params"]["depth"] == pytest.approx(depth, abs=0.06)
    assert f["volume"] == pytest.approx(box - PI * 9 * min(depth, 12), rel=1e-3)
    page.check("#hoThrough")
    page.wait_for_function("() => !window.__vp.gizmos().arrow", timeout=10000)
    wait_volume(server, "hole1", box - PI * 9 * 12)
    assert page.eval_on_selector("#hoDepth", "el => el.disabled")
    page.uncheck("#hoThrough")
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=10000)
    wait_volume(server, "hole1", box - PI * 9 * min(depth, 12))
    page.click("#hoOk")
    page.wait_for_selector("#holeDialog", state="hidden")
    assert page.errors == []


def test_counterbore_then_edit_and_cancel_restores(page, fresh_doc, server):
    setup(page)
    box = feature(server, "b")["volume"]
    open_hole_at(page, PT)
    page.select_option("#hoKind", "counterbore")
    assert page.is_visible("#hoCbDiaRow") and not page.is_visible("#hoCsDiaRow")
    page.fill("#hoCbDia", "10")
    page.fill("#hoCbDepth", "3")
    page.fill("#hoDepth", "8")
    expected = box - PI * 9 * 8 - PI * (25 - 9) * 3
    wait_volume(server, "hole1", expected)
    page.click("#hoOk")
    page.wait_for_selector("#holeDialog", state="hidden")
    page.wait_for_timeout(800)
    # edit: the tree row's pencil reopens the tool with the circle and arrow at the stored hole
    r = row(page, "hole1")
    r.hover()
    r.locator("button[title^='edit this hole']").click()
    page.wait_for_selector("#holeDialog", state="visible", timeout=15000)
    assert "Edit hole1" in page.text_content("#holeDialog .exhead")
    assert page.input_value("#hoKind") == "counterbore"
    assert page.input_value("#hoCbDia") == "10" and page.input_value("#hoDepth") == "8"
    page.wait_for_function("() => window.__vp.gizmos().hole && window.__vp.gizmos().arrow",
                           timeout=15000)
    m = page.evaluate("() => window.__vp.holeMarkerInfo()")
    assert m["centre"] == pytest.approx(PT, abs=1e-3) and m["radius"] == pytest.approx(3)
    page.fill("#hoDia", "8")
    wait_volume(server, "hole1", box - PI * 16 * 8 - PI * (25 - 16) * 3)
    assert page.evaluate("() => window.__vp.holeMarkerInfo().radius") == pytest.approx(4)
    page.click("#hoCancel")
    page.wait_for_selector("#holeDialog", state="hidden")
    f = wait_volume(server, "hole1", expected)
    assert f["params"]["diameter"] == 6 and f["params"]["kind"] == "counterbore"
    assert page.errors == []


def test_a_second_click_on_the_face_moves_the_hole(page, fresh_doc, server):
    """while the panel is open the face pick stays armed: clicking another point
    of the body's face puts the hole there (the plan is asked again, the
    feature follows), and the volume is the same hole elsewhere"""
    setup(page)
    box = feature(server, "b")["volume"]
    open_hole_at(page, PT)
    page.fill("#hoDepth", "5")
    f = wait_feature(server, "hole1")
    assert f["params"]["at"] == pytest.approx([10, 5], abs=1e-3)
    assert page.evaluate("() => window.__vp.gizmos().facePick"), "the re-pick is armed"
    pt2 = [-10.0, -5.0, 6.0]
    sp = page.evaluate(TO_SCREEN, pt2)
    page.mouse.click(sp["x"], sp["y"])
    f = wait_at(server, "hole1", [-10, -5])
    assert f["volume"] == pytest.approx(box - PI * 9 * 5, rel=1e-4)
    m = page.evaluate("() => window.__vp.holeMarkerInfo()")
    assert m["centre"] == pytest.approx(pt2, abs=0.05)
    assert page.evaluate("() => window.__vp.gizmos().facePick"), "armed again for the next click"
    page.click("#hoOk")
    page.wait_for_selector("#holeDialog", state="hidden")
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.errors == []
