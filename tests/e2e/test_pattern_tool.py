"""E2E: the Pattern tools (LAUNCH-PLAN.md P4, specs/pattern.md). The steps are
REAL — a click on the hole's row in the tree, the ribbon button, a ring drag, an
arrow drag, a click on a bore's wall — and every geometric claim is checked
against the kernel: the volume the copies take away, the stored seed and axis,
what Cancel put back.
"""
import math
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

PI = math.pi
PLUG = PI * 9 * 12               # one ⌀6 through hole in the 12 mm plate

# an 80 x 80 x 12 plate centred on the origin with a ⌀6 through hole at (20, 0)
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 80, depth: 80, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'hole1', op: 'hole', params: { face: 'top', at: [20, 0], diameter: 6, depth: 1,
      through: true }, inputs: ['b'] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""
# …plus a ⌀10 bore at (-10, 0), with the seed hole moved to (10, 0)
BUILD_BORE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 80, depth: 80, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'hole1', op: 'hole', params: { face: 'top', at: [10, 0], diameter: 6, depth: 1,
      through: true }, inputs: ['b'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'bore', op: 'hole', params: { face: 'top', at: [-10, 0], diameter: 10, depth: 1,
      through: true }, inputs: ['hole1'] }, 'add');
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
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"
RING_AT = "async (deg) => (await import('/static/js/viewport.js')).taperRingPointScreen(deg)"
ARROW = "async () => (await import('/static/js/viewport.js')).extrudeArrowAxisScreen()"
ARROW2 = "async () => (await import('/static/js/viewport.js')).secondArrowAxisScreen()"


def features(server):
    return httpx.get(f"{server}/api/doc", timeout=30).json()["features"]


def feature(server, fid):
    return next((f for f in features(server) if f["id"] == fid), None)


def wait_feature(server, fid, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] in ("ok", "failed"):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid} never finished building")


def wait_volume(server, fid, expected, timeout=25, rel=1e-4):
    t0 = time.time()
    f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] == "ok" and f["volume"] == pytest.approx(expected, rel=rel):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid} never reached volume {expected}: {f}")


def wait_param(server, fid, key, pred, timeout=25):
    t0 = time.time()
    f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] == "ok" and pred(f["params"].get(key)):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid}.{key} never satisfied: {f}")


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def setup(page, build=BUILD):
    page.evaluate(build)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)


def open_on_row(page, fid, op, panel):
    """select-then-command through the TREE: the seed's row, then the button"""
    row(page, fid).locator(".nname").click()
    page.wait_for_function(
        f"async () => (await import('/static/js/state.js')).S.selected === '{fid}'", timeout=5000)
    page.locator("button.tab", has_text="Modify").click()      # the Pattern group lives in Modify
    page.click(f"#ribbon .rbtn[title='{op}']")
    page.wait_for_selector(panel, state="visible", timeout=15000)


def drag_along(page, ax, px):
    """grab an arrow at its middle and push it the way it points on screen"""
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

def test_select_the_hole_row_press_circular_type_a_count_and_ok(page, fresh_doc, server):
    """Honest zero: the ring and the axis line come up, Count 1, nothing built;
    a typed count cuts exactly N plugs on the bolt circle; OK leaves ONE row
    and no combiner (the op eats its body)."""
    setup(page)
    box = feature(server, "b")["volume"]
    open_on_row(page, "hole1", "polar_pattern", "#cpDialog")
    page.wait_for_function("() => window.__vp.gizmos().ring && window.__vp.gizmos().axis", timeout=15000)
    assert page.input_value("#cpCount") == "1" and page.input_value("#cpAngle") == "360"
    assert page.input_value("#cpAxis") == "normal of the top face through its centre"
    assert page.input_value("#cpProfile") == "hole1"
    assert page.input_value("#cpOp") == "new" and not page.is_visible("#cpTargetRow")
    assert feature(server, "polar_pattern1") is None, "opening builds nothing"
    page.fill("#cpCount", "6")
    f = wait_feature(server, "polar_pattern1")
    assert f["op"] == "polar_pattern" and f["status"] == "ok" and f["inputs"] == ["hole1"], f
    assert f["params"]["seed"] == "hole1" and f["params"]["count"] == 6
    assert f["params"]["axis"]["face_normal"] == pytest.approx([0, 0, 1])
    assert f["volume"] == pytest.approx(box - 6 * PLUG, rel=1e-4)
    page.click("#cpOk")
    page.wait_for_selector("#cpDialog", state="hidden")
    page.wait_for_timeout(800)
    assert row(page, "polar_pattern1").count() == 1
    assert not any(x["op"] in ("cut", "fuse") for x in features(server)), "no combiner"
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert not page.evaluate("() => window.__vp.gizmos().ring"), "the ring went with the panel"
    assert page.errors == []


def test_drag_the_ring_to_a_half_turn(page, fresh_doc, server):
    """the ring drives the total angle (Full = 360; dragged back it becomes a
    partial angle) — ONE verified rebuild on release, the stored angle follows"""
    setup(page)
    box = feature(server, "b")["volume"]
    open_on_row(page, "hole1", "polar_pattern", "#cpDialog")
    page.wait_for_function("() => window.__vp.gizmos().ring", timeout=15000)
    page.fill("#cpCount", "4")
    wait_volume(server, "polar_pattern1", box - 4 * PLUG)
    p0 = page.evaluate(RING_AT, 0)               # Full: the handle sits at the seed
    page.mouse.move(p0["x"], p0["y"])
    page.mouse.down()
    for deg in (330, 300, 270, 240, 210, 180):   # backwards round the ring: 360 -> 180
        p = page.evaluate(RING_AT, deg)
        page.mouse.move(p["x"], p["y"])
        page.wait_for_timeout(30)
    page.mouse.up()
    angle = float(page.input_value("#cpAngle"))
    assert 150 < angle < 210, angle
    f = wait_param(server, "polar_pattern1", "angle", lambda a: a == pytest.approx(angle, abs=0.2))
    assert f["volume"] == pytest.approx(box - 4 * PLUG, rel=1e-4)   # still 4 copies, spread over the half turn
    page.click("#cpOk")
    page.wait_for_selector("#cpDialog", state="hidden")
    assert page.errors == []


def test_rectangular_arrows_count_and_a_second_direction(page, fresh_doc, server):
    """two arrows from the seed along the face's x and y; the first drags
    Distance 1, the second wakes Direction 2 (Count 2 -> 2); typed counts and
    Extent do what they say"""
    setup(page)
    box = feature(server, "b")["volume"]
    open_on_row(page, "hole1", "linear_pattern", "#rpDialog")
    page.wait_for_function("() => window.__vp.gizmos().arrow && window.__vp.gizmos().arrow2", timeout=15000)
    assert page.input_value("#rpCount") == "2" and page.input_value("#rpDist") == "0"
    assert page.input_value("#rpCount2") == "1" and page.input_value("#rpAlong") == "x"
    assert page.input_value("#rpProfile") == "hole1"
    assert feature(server, "linear_pattern1") is None, "opening builds nothing"
    drag_along(page, page.evaluate(ARROW), -60)      # against the arrow: toward -x, plenty of plate
    dist = float(page.input_value("#rpDist"))
    assert dist < 0, "the drag set a distance"
    f = wait_feature(server, "linear_pattern1")
    assert f["status"] == "ok" and f["params"]["distance"] == pytest.approx(dist, abs=0.06), f
    assert f["params"]["direction"] == pytest.approx([1, 0, 0]) and f["params"]["seed"] == "hole1"
    assert f["volume"] == pytest.approx(box - 2 * PLUG, rel=1e-3)
    page.fill("#rpDist", "-12")
    page.fill("#rpCount", "4")
    wait_volume(server, "linear_pattern1", box - 4 * PLUG)
    drag_along(page, page.evaluate(ARROW2), 60)      # the second arrow wakes Direction 2
    page.wait_for_function("() => document.getElementById('rpCount2').value === '2'", timeout=10000)
    assert float(page.input_value("#rpDist2")) != 0
    page.fill("#rpDist2", "15")
    wait_volume(server, "linear_pattern1", box - 8 * PLUG)
    f = feature(server, "linear_pattern1")
    assert f["params"]["direction2"] == pytest.approx([0, 1, 0]) and f["params"]["count2"] == 2
    page.select_option("#rpDistType", "extent")      # Extent: the four now fit inside 12 (they overlap)
    wait_param(server, "linear_pattern1", "distance_type", lambda t: t == "extent")
    page.fill("#rpDist", "-36")                      # …inside 36: 12 apart again, 8 whole plugs
    wait_volume(server, "linear_pattern1", box - 8 * PLUG)
    page.click("#rpOk")
    page.wait_for_selector("#rpDialog", state="hidden")
    page.wait_for_timeout(800)
    assert row(page, "linear_pattern1").count() == 1
    assert not any(x["op"] in ("cut", "fuse") for x in features(server))
    assert page.evaluate(MODAL) is None
    assert not page.evaluate("() => window.__vp.gizmos().arrow || window.__vp.gizmos().arrow2")
    assert page.errors == []


def test_edit_reopens_on_the_stored_values_and_cancel_restores(page, fresh_doc, server):
    setup(page)
    box = feature(server, "b")["volume"]
    open_on_row(page, "hole1", "polar_pattern", "#cpDialog")
    page.wait_for_function("() => window.__vp.gizmos().ring", timeout=15000)
    page.fill("#cpCount", "4")
    wait_volume(server, "polar_pattern1", box - 4 * PLUG)
    page.click("#cpOk")
    page.wait_for_selector("#cpDialog", state="hidden")
    page.wait_for_timeout(800)
    row(page, "polar_pattern1").dblclick()
    page.wait_for_selector("#cpDialog", state="visible", timeout=15000)
    assert "Edit polar_pattern1" in page.text_content("#cpDialog .exhead")
    assert page.input_value("#cpCount") == "4" and page.input_value("#cpAngle") == "360"
    page.wait_for_function("() => window.__vp.gizmos().ring && window.__vp.gizmos().axis", timeout=15000)
    assert page.input_value("#cpAxis") == "normal of the top face through its centre"
    page.fill("#cpCount", "6")
    wait_volume(server, "polar_pattern1", box - 6 * PLUG)
    page.click("#cpCancel")
    page.wait_for_selector("#cpDialog", state="hidden")
    f = wait_volume(server, "polar_pattern1", box - 4 * PLUG)
    assert f["params"]["count"] == 4
    assert page.evaluate(MODAL) is None
    assert page.errors == []


def test_a_click_on_a_bore_re_aims_the_ring(page, fresh_doc, server):
    """while the panel is open a click on a cylindrical face puts the axis on
    that bore's axis (the framework's repick, meaning the AXIS here)"""
    setup(page, BUILD_BORE)
    box = feature(server, "b")["volume"]
    bore_plug = PI * 25 * 12
    open_on_row(page, "hole1", "polar_pattern", "#cpDialog")
    page.wait_for_function("() => window.__vp.gizmos().ring && window.__vp.gizmos().facePick", timeout=15000)
    assert page.input_value("#cpAxis") == "normal of the top face through its centre"
    assert page.input_value("#cpProfile") == "hole1 (on bore)"       # the pattern goes on the body's current state
    # the bore's INNER wall on the side away from the camera is what an iso view
    # shows through the opening: click it 3 mm below the top (deeper, the ray
    # meets the top face before it reaches the wall — the iso camera sits ~28° up)
    cam = page.evaluate("() => window.__vp.camera.position.toArray()")
    dx, dy = cam[0] + 10, cam[1]
    L = (dx * dx + dy * dy) ** 0.5
    pt = [-10 - 5 * dx / L, -5 * dy / L, 3.0]
    sp = page.evaluate(TO_SCREEN, pt)
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_function(
        "() => document.getElementById('cpAxis').value === 'axis of the ⌀10 bore'", timeout=15000)
    page.fill("#cpCount", "2")                    # 180° about x = -10: the copy lands at (-30, 0)
    f = wait_volume(server, "polar_pattern1", box - bore_plug - 2 * PLUG)
    assert "face_center" in f["params"]["axis"] and f["params"]["axis"]["face_center"][0] == pytest.approx(-10, abs=6)
    assert f["inputs"] == ["bore"]
    page.click("#cpOk")
    page.wait_for_selector("#cpDialog", state="hidden")
    assert page.errors == []
