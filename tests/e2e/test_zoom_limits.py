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


def test_zooming_onto_the_part_aims_at_what_is_under_the_cursor(
        page, server, fresh_doc):
    """The half worth keeping: pointing at solid material moves the target ONTO
    that surface, so the dolly approaches it instead of the middle of the
    block. (Dead centre of a flange is its bore — the ray goes through the hole
    and correctly retargets nothing, so aim off-centre.)"""
    _load(page, server, "flange-100")
    _wheel_at(page, 120, 0, n=2)
    assert _drift(page) > 1.0, "the target never moved onto the surface"
    assert not page.errors, page.errors


def test_the_floor_clears_the_near_clip_plane(page, server, fresh_doc):
    """Inside the near plane, faces are clipped away and you see through the
    part — which looks exactly like the bug being prevented."""
    _load(page, server, "flange-100")
    fit = page.evaluate(FIT)
    near = page.evaluate("() => window.__vp.camera.near")
    assert fit["minDistance"] > near, f"minDistance {fit['minDistance']} <= near {near}"


def test_the_floor_scales_with_the_model(page, server, fresh_doc):
    """A keychain and a 200 mm panel must both zoom about as far in
    proportional terms, so the floor cannot be a constant."""
    _load(page, server, "flange-100")
    small = page.evaluate(FIT)
    _load(page, server, "esp32-remote")
    big = page.evaluate(FIT)
    assert big["r"] > small["r"], (small["r"], big["r"])
    assert big["minDistance"] > small["minDistance"], \
        f"floor did not scale: {small['minDistance']} -> {big['minDistance']}"


def test_hard_zooming_never_reaches_the_orbit_target(page, server, fresh_doc):
    """The actual regression: 70 hard scrolls used to end with the camera AT the
    target, i.e. inside the part."""
    _load(page, server, "esp32-remote")
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
