"""E2E: the Mirror tool (LAUNCH-PLAN.md P4, specs/mirror.md). The steps are
REAL — a click on the hole's row in the tree, the ribbon button, a click on an
origin-plane quad, a click on a face of the body, a choice in the Plane box —
and every geometric claim is checked against the kernel: the volume the mirror
image takes away or adds, the stored plane, what Cancel put back.
"""
import math
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

PI = math.pi
PLUG = PI * 9 * 12               # one ⌀6 through hole in the 12 mm plate
BOX = 80 * 80 * 12

# an 80 x 80 x 12 plate centred on the origin with a ⌀6 through hole at (20, 10)
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 80, depth: 80, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'hole1', op: 'hole', params: { face: 'top', at: [20, 10], diameter: 6, depth: 1,
      through: true }, inputs: ['b'] }, 'add');
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
QUADS = "() => window.__vp.originPlaneInfo().map(q => q.plane).sort()"


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


def wait_plane(server, fid, pred, timeout=25):
    t0 = time.time()
    f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] == "ok" and pred(f["params"].get("plane")):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid}.plane never satisfied: {f}")


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def setup(page, build=BUILD):
    page.evaluate(build)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)


def press(page, op="mirror"):
    page.locator("button.tab", has_text="Modify").click()      # Mirror lives in Modify › Transform
    page.click(f"#ribbon .rbtn[title='{op}']")


def open_on_row(page, fid):
    """select-then-command through the TREE: the seed's row, then the button"""
    row(page, fid).locator(".nname").click()
    page.wait_for_function(
        f"async () => (await import('/static/js/state.js')).S.selected === '{fid}'", timeout=5000)
    press(page)
    page.wait_for_selector("#mrDialog", state="visible", timeout=15000)
    # the session pick is armed WITH the three origin quads
    page.wait_for_function("() => window.__vp.gizmos().facePick", timeout=15000)
    assert page.evaluate(QUADS) == ["XY", "XZ", "YZ"]


def click_world(page, pt):
    sp = page.evaluate(TO_SCREEN, pt)
    page.mouse.click(sp["x"], sp["y"])


def cam_signs(page):
    cam = page.evaluate("() => window.__vp.camera.position.toArray()")
    return (1 if cam[0] >= 0 else -1), (1 if cam[1] >= 0 else -1)


def on_plane(page, plane):
    """a point on ONE origin quad that the camera's ray reaches before any other
    quad or the body: high above the plate (z 40 > its top at 6) and on the
    CAMERA's side of the other vertical plane, so the ray never crosses it"""
    sx, sy = cam_signs(page)
    return {"YZ": [0.0, 50.0 * sy, 40.0], "XZ": [50.0 * sx, 0.0, 40.0]}[plane]


def side_face(page):
    """the centre of the x-facing side face the camera sees, and its normal"""
    sx, _sy = cam_signs(page)
    return [40.0 * sx, 0.0, 0.0], [sx, 0, 0]


# ------------------------------------------------------------------ journeys --

def test_select_the_hole_row_press_mirror_click_the_yz_plane_and_ok(page, fresh_doc, server):
    """Honest zero: the panel opens with no plane and the quads up, nothing
    built; a click on the YZ quad builds the mirror image (exactly one more
    plug on the other side); OK leaves ONE row and no combiner."""
    setup(page)
    open_on_row(page, "hole1")
    assert page.input_value("#mrPlane") == ""
    assert page.locator("#mrPlane option").count() == 7            # the placeholder + 3 origin + 3 mid
    assert page.input_value("#mrProfile") == "hole1"
    assert not page.evaluate("() => window.__vp.gizmos().plane"), "no plane yet: no quad"
    assert feature(server, "mirror1") is None, "opening builds nothing"
    click_world(page, on_plane(page, "YZ"))
    f = wait_volume(server, "mirror1", BOX - 2 * PLUG)
    assert f["op"] == "mirror" and f["inputs"] == ["hole1"], f
    # join is a BODY mirror's business; this is a hole's (P0 of the P4 review)
    assert f["params"] == {"seed": "hole1", "plane": "YZ", "join": False}
    page.wait_for_function("() => document.getElementById('mrPlane').value === 'yz'", timeout=10000)
    # the blank is the NO-PLANE state only: with YZ in force there is nothing to
    # fall back to, so the box can never read "no plane" over a built mirror
    # while the gold quad and the feature still hold one (P4 review)
    assert page.locator("#mrPlane option[value='']").count() == 0
    assert page.locator("#mrPlane option").count() == 6            # 3 origin + 3 mid, no placeholder
    page.wait_for_function("() => window.__vp.gizmos().plane", timeout=10000)
    q = page.evaluate("() => window.__vp.planeQuadInfo()")
    assert q["normal"] == pytest.approx([1, 0, 0], abs=1e-6) and q["origin"] == pytest.approx([0, 0, 0], abs=1e-3)
    page.click("#mrOk")
    page.wait_for_selector("#mrDialog", state="hidden")
    page.wait_for_timeout(800)
    assert row(page, "mirror1").count() == 1
    assert not any(x["op"] in ("cut", "fuse") for x in features(server)), "no combiner"
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert not page.evaluate("() => window.__vp.gizmos().plane"), "the quad went with the panel"
    assert page.evaluate(QUADS) == [], "the origin quads went with the pick"
    assert "Mirror created" in page.text_content("#chatLog")
    assert page.errors == []


def test_a_second_click_re_aims_the_plane_and_a_bad_face_is_refused_and_reverted(page, fresh_doc, server):
    """the pick stays armed: the XZ quad moves the image across THAT plane; a
    face whose plane throws the image off the body is refused with a sentence
    and the feature keeps the plane that built"""
    setup(page)
    open_on_row(page, "hole1")
    click_world(page, on_plane(page, "YZ"))
    wait_plane(server, "mirror1", lambda p: p == "YZ")
    # the viewport reloads the doubled body after that build and the origin quads
    # go with it; a click sent before they are back lands on empty space and is
    # silently dropped (this journey failed here about one run in two)
    page.wait_for_function("() => window.__vp.originPlaneInfo().length === 3", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().facePick", timeout=15000)
    click_world(page, on_plane(page, "XZ"))
    f = wait_plane(server, "mirror1", lambda p: p == "XZ")
    assert f["volume"] == pytest.approx(BOX - 2 * PLUG, rel=1e-4)
    page.wait_for_function("() => document.getElementById('mrPlane').value === 'xz'", timeout=10000)
    click_world(page, side_face(page)[0])                         # a side face: the image lands off the plate
    page.wait_for_function(
        "() => document.getElementById('chatLog').textContent.includes('lands off the body')", timeout=15000)
    page.wait_for_function("() => document.getElementById('mrPlane').value === 'xz'", timeout=15000)
    f = wait_plane(server, "mirror1", lambda p: p == "XZ")        # reverted to the plane that built
    assert f["status"] == "ok"
    # ... and a SECOND refused face still reverts to the plane that BUILT. The
    # revert used to re-read the params from the still-refused plan and record
    # THAT as lastGood, so the next revert fell back to a plane that never built
    # and left the feature failed under a sentence naming it (P4 review).
    click_world(page, side_face(page)[0])
    page.wait_for_function(
        "() => (document.getElementById('chatLog').textContent.match(/lands off the body/g) || []).length >= 2",
        timeout=15000)
    f = wait_plane(server, "mirror1", lambda p: p == "XZ")
    said = page.text_content("#chatLog")
    assert "Reverted to the mirror across the picked face" not in said
    # the revert sentence names the plane in the PLAN's words (R1), not in words made in JS
    assert "Reverted to the mirror across the XZ plane (through the origin)" in said, said
    page.click("#mrOk")
    page.wait_for_selector("#mrDialog", state="hidden")
    assert page.errors == []


# ...plus a ⍠10 bore at (-20, -20): clear of the YZ image of hole1 at (-20, 10)
# by 30 mm, so the mirror stays a healthy solid and only the CLICK is on trial
BUILD_BORE = BUILD.replace("  await loadMesh(true);", """  await postJSON('/api/feature/add',
    { id: 'bore', op: 'hole', params: { face: 'top', at: [-20, -20], diameter: 10, depth: 1,
      through: true }, inputs: ['hole1'] }, 'add');
  await loadMesh(true);""")


def test_a_curved_face_is_refused_by_the_viewport_before_the_server(page, fresh_doc, server):
    """The PLANE re-pick takes a FLAT face: a click on the bore's cylindrical
    wall is refused on the spot, in the words the hover already promised (it
    shows not-allowed over that face), and the mirror keeps the plane that
    built. Mirror used to carry `anyFace` — which flags the RE-PICK, not the
    seed pick — so the wall round-tripped to a server refusal instead, and the
    refusal named only "a flat face" while three origin quads were on screen
    (P4 review)."""
    setup(page, build=BUILD_BORE)
    open_on_row(page, "hole1")
    click_world(page, on_plane(page, "YZ"))
    wait_plane(server, "mirror1", lambda p: p == "YZ")
    before = page.text_content("#chatLog")
    # the bore's INNER wall on the side away from the camera, 3 mm below the top
    # (the recipe of the Pattern journey: deeper and the ray meets the top face)
    cam = page.evaluate("() => window.__vp.camera.position.toArray()")
    dx, dy = cam[0] + 20, cam[1] + 20
    L = (dx * dx + dy * dy) ** 0.5
    click_world(page, [-20 - 5 * dx / L, -20 - 5 * dy / L, 3.0])
    page.wait_for_function(
        "() => document.getElementById('chatLog').textContent.includes('(curved)')", timeout=15000)
    said = page.text_content("#chatLog")[len(before):]
    # the sentence names EVERY next action, not half of them
    assert "needs a flat face or an origin plane" in said, said
    assert "the picked face is CYLINDER" not in said, "the server was asked after all"
    # the pick stays armed and the plane that built is untouched
    assert page.evaluate("() => window.__vp.gizmos().facePick")
    assert wait_plane(server, "mirror1", lambda p: p == "YZ")["status"] == "ok"
    page.click("#mrCancel")
    page.wait_for_selector("#mrDialog", state="hidden")
    assert page.errors == []


def test_the_plane_box_chooses_a_mid_plane(page, fresh_doc, server):
    setup(page)
    open_on_row(page, "hole1")
    page.select_option("#mrPlane", "midy")
    f = wait_plane(server, "mirror1", lambda p: p == {"mid": "Y"})
    assert f["volume"] == pytest.approx(BOX - 2 * PLUG, rel=1e-4)
    page.wait_for_function("() => window.__vp.gizmos().plane", timeout=10000)
    assert page.evaluate("() => window.__vp.planeQuadInfo()")["normal"] == pytest.approx([0, 1, 0], abs=1e-6)
    page.select_option("#mrPlane", "midx")
    wait_plane(server, "mirror1", lambda p: p == {"mid": "X"})
    page.click("#mrOk")
    page.wait_for_selector("#mrDialog", state="hidden")
    assert feature(server, "mirror1")["params"]["plane"] == {"mid": "X"}
    # the tree shows the stored plane by its parts, not as "[object Object]" (P4 review)
    page.wait_for_function(
        "() => (document.querySelector('#tree .node[data-fid=\"mirror1\"] .nbody') || {}).textContent"
        ".includes('mid X')", timeout=10000)
    assert "[object Object]" not in page.text_content("#tree")
    assert page.errors == []


def test_a_body_seed_doubles_across_its_face_and_cancel_restores(page, fresh_doc, server):
    """click the plate's plain top face, press Mirror: the seed is the BODY;
    a click on its +x face fuses the reflection on — one solid, twice the
    volume; Cancel takes it away"""
    setup(page)
    click_world(page, [-10.0, -10.0, 6.0])                         # the top face, away from the hole
    page.wait_for_function(
        "async () => { const { S } = await import('/static/js/state.js'); "
        "return !!(S.pickedFace && S.pickedFace.normal && S.pickedFace.normal[2] > 0.9); }", timeout=5000)
    press(page)
    page.wait_for_selector("#mrDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().facePick", timeout=15000)
    assert page.input_value("#mrProfile") == "the body hole1"
    size0 = page.evaluate("() => window.__vp.originPlaneInfo()[0].size")
    pt, normal = side_face(page)
    click_world(page, pt)                                          # a side face the camera sees
    f = wait_volume(server, "mirror1", 2 * (BOX - PLUG))
    assert f["params"]["seed"] is None and f["params"]["join"] is True
    assert f["params"]["plane"]["face_normal"] == pytest.approx(normal, abs=1e-3)
    assert f["pieces"] == 1
    # the origin quads follow the body: built once at arm time they kept the
    # size and centre of HALF the doubled plate (P4 review)
    page.wait_for_function(
        f"() => window.__vp.originPlaneInfo().length === 3 && window.__vp.originPlaneInfo()[0].size > {size0} * 1.3",
        timeout=15000)
    page.click("#mrCancel")
    page.wait_for_selector("#mrDialog", state="hidden")
    page.wait_for_timeout(800)
    assert feature(server, "mirror1") is None
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.evaluate(MODAL) is None
    assert page.errors == []


def test_edit_reopens_on_the_stored_plane_and_cancel_restores(page, fresh_doc, server):
    setup(page)
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/feature/add', { id: 'mirror1', op: 'mirror',
        params: { seed: 'hole1', plane: 'XZ', join: true }, inputs: ['hole1'] }, 'add');
    }""")
    wait_volume(server, "mirror1", BOX - 2 * PLUG)
    page.wait_for_timeout(800)
    row(page, "mirror1").dblclick()
    page.wait_for_selector("#mrDialog", state="visible", timeout=15000)
    assert "Edit mirror1" in page.text_content("#mrDialog .exhead")
    page.wait_for_function("() => document.getElementById('mrPlane').value === 'xz'", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().plane", timeout=10000)
    assert page.evaluate("() => window.__vp.planeQuadInfo()")["normal"] == pytest.approx([0, 1, 0], abs=1e-6)
    page.select_option("#mrPlane", "yz")
    wait_plane(server, "mirror1", lambda p: p == "YZ")
    page.click("#mrCancel")
    page.wait_for_selector("#mrDialog", state="hidden")
    f = wait_plane(server, "mirror1", lambda p: p == "XZ")
    assert f["params"] == {"seed": "hole1", "plane": "XZ", "join": True}
    assert page.evaluate(MODAL) is None
    assert page.errors == []


def test_ok_without_a_plane_adds_no_row_and_says_so(page, fresh_doc, server):
    setup(page)
    open_on_row(page, "hole1")
    page.click("#mrOk")
    page.wait_for_selector("#mrDialog", state="hidden")
    page.wait_for_timeout(500)
    assert feature(server, "mirror1") is None
    assert "Nothing mirrored" in page.text_content("#chatLog")
    assert page.evaluate(MODAL) is None and page.evaluate(QUADS) == []
    assert page.errors == []


def test_a_first_plane_the_kernel_refuses_is_not_reported_as_created(page, fresh_doc, server):
    """the FIRST plane of a new mirror throws the image off the plate: there is
    nothing good to revert to, the row is red — and OK says so instead of
    "Mirror created" (P4 review; the framework's sentence, so every tool's)"""
    setup(page)
    open_on_row(page, "hole1")
    click_world(page, side_face(page)[0])                          # a side face: the image lands off the plate
    f = wait_feature(server, "mirror1")
    assert f["status"] == "failed" and "lands off the body" in " ".join(f["problems"]), f
    page.click("#mrOk")
    page.wait_for_selector("#mrDialog", state="hidden")
    page.wait_for_timeout(500)
    said = page.text_content("#chatLog")
    assert "Mirror was NOT built" in said and "lands off the body" in said, said
    assert "Mirror created" not in said
    assert page.evaluate(MODAL) is None
    assert page.errors == []
