"""Zooming must never put the camera inside the solid.

User report with a screenshot (2026-08-27): "when i am zooming the design it
completely goes like that" — the whole viewport a smooth grey wash with no
geometry, no grid, no edges. That is the inside of the shell: the camera had
dollied through the material and was looking at the far interior wall.

Cause: OrbitControls dollies toward its TARGET, which sits at the model's
centre, and `minDistance` was never set (default 0) — so the wheel walked the
camera straight into the part.

`minDistance` alone cannot fix it. esp32-remote is 12 mm thick, so its centre is
6 mm from either face: any small distance from the target is still inside the
material. The target has to move onto the surface being pointed at, with
`minDistance` as the floor that stops the camera reaching it.

OrbitControls' own `zoomToCursor` was tried first and REVERTED the same day: it
has no idea whether the cursor is over anything, so with the pointer on empty
background it slid the target off into space — measured at 47 mm of drift from a
model of radius 70 after five small scrolls, which swings the part out of frame
("when i am zooming little bit, the whole sketch vanish"). We raycast first and
only retarget on a real hit.
"""
import pytest

pytest.importorskip("playwright.sync_api")

FIT = "() => window.__vp.getFit()"
DIST = ("() => { const c = window.__vp.getControls();"
        " return window.__vp.camera.position.distanceTo(c.target); }")


def _load(page, server, slug):
    import httpx
    httpx.post(f"{server}/api/open/{slug}", timeout=180)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=25000)
    page.wait_for_function("() => window.__vp.bodyCount() > 0", timeout=60000)
    page.wait_for_timeout(1500)


def test_zoom_is_clamped_and_does_not_use_orbitcontrols_zoomtocursor(
        page, server, fresh_doc):
    _load(page, server, "flange-100")
    fit = page.evaluate(FIT)
    assert fit["minDistance"] > 0, "minDistance is 0 — the camera can reach the target"
    assert fit["zoomToCursor"] is False,         "OrbitControls' zoomToCursor drifts the target over empty space"


def _wheel_at(page, dx, dy, n=1, out=False):
    box = page.locator("#viewer").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    for _ in range(n):
        page.mouse.move(cx + dx, cy + dy)
        page.mouse.wheel(0, 300 if out else -300)
        page.wait_for_timeout(120)


def _drift(page):
    return page.evaluate("""() => {
      const c = window.__vp.getControls(), f = window.__vp.getFit();
      return Math.hypot(c.target.x - f.c[0], c.target.y - f.c[1],
                        c.target.z - f.c[2]);
    }""")


def test_zooming_over_empty_space_does_not_drag_the_model_out_of_frame(
        page, server, fresh_doc):
    """THE REGRESSION. zoomToCursor drifted the target 47 mm in five scrolls
    with the pointer on the background, and the part left the screen."""
    _load(page, server, "flange-100")
    assert _drift(page) < 1e-6
    _wheel_at(page, -420, -260, n=6)          # a corner: nothing under the cursor
    assert _drift(page) < 1e-6,         f"the orbit target wandered {_drift(page):.1f} mm over empty space"
    assert not page.errors, page.errors


WHEEL = """([dy, mode]) => document.querySelector('#viewer canvas').dispatchEvent(
  new WheelEvent('wheel', {deltaY: -dy, deltaMode: mode, clientX: 400,
                           clientY: 400, bubbles: true, cancelable: true}))"""
DIST_N = ("() => +window.__vp.camera.position"
          ".distanceTo(window.__vp.getControls().target).toFixed(4)")


def _one_notch(page, dy=100, mode=0):
    page.click("#vFit")
    page.wait_for_timeout(800)
    before = page.evaluate(DIST_N)
    page.evaluate(WHEEL, [dy, mode])
    page.wait_for_timeout(300)
    return page.evaluate(DIST_N) / before


def test_one_wheel_click_is_one_notch_whatever_the_device_reports(
        page, server, fresh_doc):
    """three r160 scales its zoom by the RAW deltaY and ignores deltaMode, so
    the same physical click zoomed differently on every mouse: measured x0.95 /
    x0.88 / x0.86 for devices reporting 100 / 240 / 400, and Firefox's LINE
    mode (deltaY 3) barely moved at all."""
    _load(page, server, "flange-100")
    for dy, mode in ((100, 0), (120, 0), (240, 0), (400, 0), (3, 1)):
        r = _one_notch(page, dy, mode)
        assert abs(r - 0.95) < 0.002, f"deltaY={dy} mode={mode} gave {r:.4f}"


def test_a_trackpads_fine_scrolling_still_scales_down(page, server, fresh_doc):
    """Capping at one notch must not turn a trackpad's small deltas into full
    clicks — that would make it unusable."""
    _load(page, server, "flange-100")
    assert _one_notch(page, 8, 0) > 0.99, "a tiny trackpad delta zoomed a full notch"
    assert _one_notch(page, 1, 1) > 0.97


def test_zoom_does_not_explode_when_devicepixelratio_is_below_one(
        browser, server, fresh_doc):
    """THE BUG, and it is three's, not ours.

        Math.pow(0.95, zoomSpeed * |delta| / (100 * (devicePixelRatio | 0)))

    `| 0` TRUNCATES, so at any DPR under 1 — an ordinary browser zoomed out
    below 100% — the divisor is 0 and it divides by zero. Reproduced at DPR
    0.8 before the fix: one notch in went 192.44 -> 2.12 and one notch out
    2.12 -> 6018.43, straight to both clamps. That is also the original
    "the whole screen goes grey" report: with no floor, one click put the
    camera exactly ON the target, inside the solid.
    """
    from fixture_docs import flange
    fresh_doc._new_tab(flange())          # fresh_doc is the studio module
    fresh_doc._rebuild_and_mesh()
    ctx = browser.new_context(viewport={"width": 1100, "height": 760},
                              device_scale_factor=0.8)
    page = ctx.new_page()
    try:
        page.goto(server)
        page.wait_for_function("() => !!window.__vp", timeout=25000)
        page.wait_for_function("() => window.__vp.bodyCount() > 0", timeout=60000)
        page.wait_for_timeout(1500)
        assert page.evaluate("() => window.devicePixelRatio | 0") == 0,             "this test needs a sub-1 DPR to mean anything"

        page.click("#vFit")
        page.wait_for_timeout(800)
        before = page.evaluate(DIST_N)
        page.evaluate(WHEEL, [100, 0])
        page.wait_for_timeout(300)
        r = page.evaluate(DIST_N) / before
        assert abs(r - 0.95) < 0.002, f"one notch at DPR 0.8 gave {r:.4f}"

        floor = page.evaluate("() => window.__vp.getFit().minDistance")
        assert page.evaluate(DIST_N) > floor * 5, "a single notch hit the clamp"
    finally:
        ctx.close()


def test_the_wheel_is_ours_not_orbitcontrols(page, server, fresh_doc):
    _load(page, server, "flange-100")
    assert page.evaluate(FIT)["ownWheel"] is True,         "OrbitControls is handling the wheel again — its scaling is device-dependent"


def test_the_floor_clears_the_near_clip_plane(page, server, fresh_doc):
    """Inside the near plane, faces are clipped away and you see through the
    part — which looks exactly like the bug being prevented."""
    _load(page, server, "flange-100")
    fit = page.evaluate(FIT)
    near = page.evaluate("() => window.__vp.camera.near")
    assert fit["minDistance"] > near, f"minDistance {fit['minDistance']} <= near {near}"


def test_the_floor_scales_with_the_model(page, server, fresh_doc):
    """A keychain and a 200 mm panel must both zoom about as far in
    proportional terms, so the floor cannot be a constant.

    The big part is wing-rib (220x120x12, 11 features), NOT esp32-remote:
    that file is live dogfooding WIP that grew to 79 features and blew the
    open timeout mid-suite (2026-08-31). Tests must load designs whose
    committed state is stable."""
    _load(page, server, "flange-100")
    small = page.evaluate(FIT)
    _load(page, server, "wing-rib")
    big = page.evaluate(FIT)
    assert big["r"] > small["r"], (small["r"], big["r"])
    assert big["minDistance"] > small["minDistance"], \
        f"floor did not scale: {small['minDistance']} -> {big['minDistance']}"


def test_hard_zooming_never_reaches_the_orbit_target(page, server, fresh_doc):
    """The actual regression: 70 hard scrolls used to end with the camera AT the
    target, i.e. inside the part. wing-rib is the same shape class as the
    original esp32-remote report — a thin 12 mm plate whose centre is 6 mm
    from either face — without esp32's mutable-WIP open cost."""
    _load(page, server, "wing-rib")
    floor = page.evaluate(FIT)["minDistance"]
    box = page.locator("#viewer").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    for _ in range(70):
        page.mouse.move(cx, cy)
        page.mouse.wheel(0, -400)
    page.wait_for_timeout(1200)

    dist = page.evaluate(DIST)
    assert dist >= floor - 1e-6, f"camera got to {dist}, floor is {floor}"
    assert dist > 0.5, "camera collapsed onto the target"
    assert not page.errors, page.errors


def test_zooming_all_the_way_out_still_shows_the_model(page, server, fresh_doc):
    """The other end: past the far plane everything clips to a black void, which
    reads as a crash. maxDistance already guarded that — keep it guarded."""
    _load(page, server, "flange-100")
    box = page.locator("#viewer").bounding_box()
    for _ in range(80):
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.wheel(0, 400)
    page.wait_for_timeout(1000)
    far = page.evaluate("() => window.__vp.camera.far")
    assert page.evaluate(DIST) < far, "dollied past the far clip plane"
    assert not page.errors, page.errors
