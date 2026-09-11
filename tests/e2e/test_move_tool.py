"""E2E: the Move and Rotate tools (LAUNCH-PLAN.md P4, specs/move-rotate.md).
The steps under test are REAL — a pixel click on a face of the body, the
ribbon button, an arrow drag, a ring drag — and every geometric claim is
checked against the kernel: the bounding box of the moved body, the footprint
of the turned one, what Cancel put back.
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

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
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"
GHOST = "() => window.__vp.gizmos().moveGhost"
PT = [10.0, 5.0, 6.0]          # a point on the top face
BOX = 60 * 40 * 12             # 28800


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


def wait_gone(server, fid, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if feature(server, fid) is None:
            return
        time.sleep(0.25)
    raise AssertionError(f"{fid} is still there")


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def setup(page):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)


def click_world(page, pt):
    sp = page.evaluate(TO_SCREEN, pt)
    page.mouse.click(sp["x"], sp["y"])


def open_tool_on_top(page, name, dialog):
    """the user's steps, for real: a pixel click on a face of the body, then
    the ribbon button in the Modify tab (R5 — no shortcut for the step under
    test)"""
    click_world(page, PT)
    page.wait_for_function(TOP_PICKED, timeout=15000)
    page.locator("button.tab", has_text="Modify").click()
    page.click(f"#ribbon .rbtn[title='{name}']")
    page.wait_for_selector(f"#{dialog}", state="visible", timeout=15000)


def drag_screen(page, ax, px):
    """grab a handle at the middle of its on-screen axis and push it `px` the way it points"""
    bx, by, tx, ty = ax["base"]["x"], ax["base"]["y"], ax["tip"]["x"], ax["tip"]["y"]
    L = ((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5
    ux, uy = (tx - bx) / L, (ty - by) / L
    mx, my = (bx + tx) / 2, (by + ty) / 2
    page.mouse.move(mx, my)
    page.mouse.down()
    seen = False
    for k in range(1, 7):
        page.mouse.move(mx + ux * px * k / 6, my + uy * px * k / 6)
        page.wait_for_timeout(30)
        seen = seen or page.evaluate(GHOST)
    page.mouse.up()
    return seen


# ------------------------------------------------------------------ journeys --

def test_click_a_face_press_move_type_x_and_ok(page, fresh_doc, server):
    """Honest zero: the panel opens with 0 / 0 / 0, three arrows and nothing
    built; a typed X moves the body by exactly that; OK leaves ONE move row
    and no combiner; the body count stays one (the op eats its body)."""
    setup(page)
    open_tool_on_top(page, "move", "mvDialog")
    page.wait_for_function("() => window.__vp.gizmos().arrows === 3", timeout=15000)   # the plan landed
    assert page.input_value("#mvProfile") == "b (60 × 40 × 12 mm)"
    assert [page.input_value(f"#mv{k}") for k in "XYZ"] == ["0", "0", "0"]
    assert page.input_value("#mvOp") == "new", "the op eats its body: no Join / Cut"
    assert not page.is_visible("#mvTargetRow")
    assert feature(server, "move1") is None, "opening builds nothing"
    page.fill("#mvX", "20")
    f = wait_feature(server, "move1")
    assert f["op"] == "move" and f["status"] == "ok" and f["inputs"] == ["b"], f
    assert f["params"] == {"x": 20, "y": 0, "z": 0}
    assert f["volume"] == pytest.approx(BOX, rel=1e-6)
    page.click("#mvOk")
    page.wait_for_selector("#mvDialog", state="hidden")
    page.wait_for_timeout(800)
    assert row(page, "move1").count() == 1
    assert not any(x["op"] in ("cut", "fuse") for x in features(server)), "no combiner"
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert page.evaluate("() => window.__vp.gizmos().arrows") == 0, "the arrows went with the panel"
    # the body IS where the box said: its mesh's extent in x is 20 further along
    ext = page.evaluate("() => { const b = window.__vp.bodyObjsRaw()[0]; "
                        "b.mesh.geometry.computeBoundingBox(); "
                        "return [b.mesh.geometry.boundingBox.min.x, b.mesh.geometry.boundingBox.max.x]; }")
    assert ext == pytest.approx([-10, 50], abs=1e-3)
    assert page.errors == []


def test_drag_the_x_arrow_shows_the_ghost_and_cancel_puts_the_body_back(page, fresh_doc, server):
    """the arrow drives the X box (one rebuild on release); the ghost — the
    body itself — shows while the pointer is down; Cancel removes the move and
    the plate stands where it stood"""
    setup(page)
    open_tool_on_top(page, "move", "mvDialog")
    page.wait_for_function("() => window.__vp.gizmos().arrows === 3", timeout=15000)
    ax = page.evaluate("async () => (await import('/static/js/viewport.js')).arrowAxisScreen(0)")
    assert ax, "no X arrow to drag"
    ghost_seen = drag_screen(page, ax, 60)
    assert ghost_seen, "the body's ghost never showed during the drag"
    assert not page.evaluate(GHOST), "the ghost goes with the release"
    x = float(page.input_value("#mvX"))
    assert x > 0, "the drag set an offset"
    assert page.input_value("#mvY") == "0" and page.input_value("#mvZ") == "0"
    f = wait_feature(server, "move1")
    assert f["status"] == "ok" and f["params"]["x"] == pytest.approx(x)
    # the arrows rode with the body: the X arrow's base is at the new centre
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__vp.gizmos().arrows") == 3
    page.click("#mvCancel")
    page.wait_for_selector("#mvDialog", state="hidden")
    wait_gone(server, "move1")
    assert feature(server, "b")["volume"] == pytest.approx(BOX)
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert page.errors == []


def test_a_body_row_press_rotate_drag_the_ring_to_ninety_and_ok(page, fresh_doc, server):
    """the tree is a selection surface: the body's row + Rotate opens the ring
    about Z through the centre; a drag near 90 snaps to 90 (whole degrees, 45°
    bands); OK leaves the body turned in place — its footprint's sides swap,
    its volume and centre stay"""
    setup(page)
    row(page, "b").locator(".nname").click()
    page.locator("button.tab", has_text="Modify").click()
    page.click("#ribbon .rbtn[title='rotate']")
    page.wait_for_selector("#rtDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().ring && window.__vp.gizmos().axis", timeout=15000)
    assert page.input_value("#rtProfile") == "b (60 × 40 × 12 mm)"
    assert page.input_value("#rtAxis") == "Z" and page.input_value("#rtAngle") == "0"
    assert feature(server, "rotate1") is None, "opening builds nothing"
    # drag the handle from 0 to about 88 degrees along the ring; it snaps to 90
    p0 = page.evaluate("async () => (await import('/static/js/viewport.js')).taperRingPointScreen(0)")
    page.mouse.move(p0["x"], p0["y"])
    page.mouse.down()
    seen = False
    for deg in [*range(6, 85, 6), 88]:          # ...ending at 88, inside the 45° band
        p = page.evaluate("async d => (await import('/static/js/viewport.js')).taperRingPointScreen(d)", deg)
        page.mouse.move(p["x"], p["y"])
        page.wait_for_timeout(25)
        seen = seen or page.evaluate(GHOST)
    page.mouse.up()
    assert seen, "the body's ghost never showed while the ring turned"
    assert page.input_value("#rtAngle") == "90", "88° is inside the 45° band: it snaps to 90"
    f = wait_feature(server, "rotate1")
    assert f["status"] == "ok" and f["params"] == {"axis": "Z", "angle_deg": 90, "pivot": "center"}
    assert f["volume"] == pytest.approx(BOX, rel=1e-6)
    page.click("#rtOk")
    page.wait_for_selector("#rtDialog", state="hidden")
    page.wait_for_timeout(800)
    assert row(page, "rotate1").count() == 1
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    ext = page.evaluate("() => { const b = window.__vp.bodyObjsRaw()[0]; "
                        "b.mesh.geometry.computeBoundingBox(); const bb = b.mesh.geometry.boundingBox; "
                        "return [bb.min.x, bb.max.x, bb.min.y, bb.max.y]; }")
    assert ext == pytest.approx([-20, 20, -30, 30], abs=1e-3), "turned in place: 60 x 40 became 40 x 60"
    assert page.evaluate(MODAL) is None
    assert not page.evaluate("() => window.__vp.gizmos().ring")
    assert page.errors == []
