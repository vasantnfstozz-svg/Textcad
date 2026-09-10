"""E2E: the Shell tool (LAUNCH-PLAN.md P4, specs/shell.md). The steps under test
are REAL — a pixel click on the face that opens, the ribbon button, the arrow
drag, a click on a second face while the panel is open — and every geometric
claim is checked against the kernel: the walls' volume, what Cancel put back.
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
ADD_SHELL = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'shell1', op: 'shell', params: { thickness: 3, faces: ['top'] }, inputs: ['b'] }, 'add');
  await loadMesh(true);
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
PT = [10.0, 5.0, 6.0]          # a point on the top face
SIDE = [30.0, 18.5, 0.0]       # a point on the +x face, ON the wall band (y 17..20) so the
                               # click lands on material even once that face is open
BOX = 60 * 40 * 12                                 # 28800
TOP_OPEN = BOX - 54 * 34 * 9                       # 12276: 3 mm walls, top open
TOP_AND_SIDE = BOX - 57 * 34 * 9                   # 11358: top and +x open
OUTSIDE_TOP = 66 * 46 * 15 - BOX                   # 16740: walls added around, top open


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


def open_shell_on_top(page):
    """the user's steps, for real: a pixel click on the face that should be
    open, then the Shell button in the ribbon (R5 — no shortcut for the step
    under test)"""
    click_world(page, PT)
    page.wait_for_function(TOP_PICKED, timeout=15000)
    page.locator("button.tab", has_text="Modify").click()      # Shell lives in the Modify tab
    page.click("#ribbon .rbtn[title='shell']")
    page.wait_for_selector("#shellDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)   # the plan landed


def wait_faces(page, words, timeout=15000):
    page.wait_for_function(
        "w => document.getElementById('shProfile').value === w", arg=words, timeout=timeout)


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

def test_click_the_top_press_shell_type_a_thickness_and_ok(page, fresh_doc, server):
    """Honest zero: the panel opens naming the one open face, the arrow up,
    thickness 0 and nothing built; a typed thickness leaves walls of exactly
    that thickness; OK leaves ONE shell row and no combiner."""
    setup(page)
    open_shell_on_top(page)
    assert page.input_value("#shProfile") == "1 face open of b"
    assert page.input_value("#shThickness") == "0"
    assert page.input_value("#shDirection") == "inside"
    assert page.input_value("#shOp") == "new", "the op eats its body: no Join / Cut"
    assert not page.is_visible("#shTargetRow")
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert feature(server, "shell1") is None, "opening builds nothing"
    page.fill("#shThickness", "3")
    f = wait_feature(server, "shell1")
    assert f["op"] == "shell" and f["status"] == "ok" and f["inputs"] == ["b"], f
    assert f["volume"] == pytest.approx(TOP_OPEN, rel=1e-4)
    assert len(f["params"]["faces"]) == 1 and f["params"]["direction"] == "inside"
    page.click("#shOk")
    page.wait_for_selector("#shellDialog", state="hidden")
    page.wait_for_timeout(800)
    assert row(page, "shell1").count() == 1
    assert not any(x["op"] in ("cut", "fuse") for x in features(server)), "no combiner"
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert not page.evaluate("() => window.__vp.gizmos().arrow"), "the arrow went with the panel"
    assert page.errors == []


def test_drag_the_arrow_then_open_and_close_a_side_face_then_cancel(page, fresh_doc, server):
    """the arrow drives the thickness (one rebuild on release); a click on a
    second face of the body opens it too, a click on an open face closes it
    again — the server decides; Cancel removes the preview and leaves the plate"""
    setup(page)
    open_shell_on_top(page)
    drag_arrow(page, 40)
    t = float(page.input_value("#shThickness"))
    assert t > 0, "the drag set a thickness"
    f = wait_feature(server, "shell1")
    if f["status"] == "ok":                    # a drag past the plate's room is refused and reverted
        assert f["volume"] == pytest.approx(BOX - (60 - 2 * t) * (40 - 2 * t) * (12 - t), rel=1e-3)
    page.fill("#shThickness", "3")
    wait_volume(server, "shell1", TOP_OPEN)
    click_world(page, SIDE)
    wait_faces(page, "2 faces open of b")
    f = wait_volume(server, "shell1", TOP_AND_SIDE)
    assert len(f["params"]["faces"]) == 2
    click_world(page, SIDE)
    wait_faces(page, "1 face open of b")
    wait_volume(server, "shell1", TOP_OPEN)
    page.click("#shCancel")
    page.wait_for_selector("#shellDialog", state="hidden")
    wait_gone(server, "shell1")
    assert feature(server, "b")["volume"] == pytest.approx(BOX)
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert page.errors == []


def test_a_body_row_in_the_tree_opens_a_closed_hollow(page, fresh_doc, server):
    """the tree is a selection surface (parity rule 2): a body's row selected,
    Shell pressed — the tool opens on that body with no face open, and a
    thickness makes a closed hollow (walls all round, two shells, one solid)"""
    setup(page)
    row(page, "b").click()
    page.wait_for_function("async () => (await import('/static/js/state.js')).S.selected === 'b'",
                           timeout=10000)
    page.locator("button.tab", has_text="Modify").click()
    page.click("#ribbon .rbtn[title='shell']")
    page.wait_for_selector("#shellDialog", state="visible", timeout=15000)
    wait_faces(page, "no face open — a closed hollow body")
    assert page.evaluate("() => window.__vp.gizmos().arrow"), "the arrow sits on the body itself"
    page.fill("#shThickness", "3")
    f = wait_volume(server, "shell1", BOX - 54 * 34 * 6)
    assert f["params"]["faces"] == []
    page.click("#shOk")
    page.wait_for_selector("#shellDialog", state="hidden")
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.errors == []


def test_edit_reopens_on_the_stored_faces_outside_flips_and_cancel_restores(page, fresh_doc, server):
    setup(page)
    page.evaluate(ADD_SHELL)
    wait_volume(server, "shell1", TOP_OPEN)
    page.wait_for_timeout(800)
    r = row(page, "shell1")
    r.hover()
    r.locator("button[title^='edit this shell']").click()
    page.wait_for_selector("#shellDialog", state="visible", timeout=15000)
    assert "Edit shell1" in page.text_content("#shellDialog .exhead")
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    wait_faces(page, "1 face open of b")
    assert page.input_value("#shThickness") == "3"
    assert page.input_value("#shDirection") == "inside"
    page.select_option("#shDirection", "outside")
    f = wait_volume(server, "shell1", OUTSIDE_TOP)
    assert f["params"]["direction"] == "outside"
    page.click("#shCancel")
    page.wait_for_selector("#shellDialog", state="hidden")
    f = wait_volume(server, "shell1", TOP_OPEN)
    assert f["params"]["faces"] == ["top"], "the stored name survives an edit that was cancelled"
    assert page.evaluate(MODAL) is None
    assert page.errors == []
