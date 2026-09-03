"""E2E: one-command-at-a-time (R13) + taper-to-flat (R12).

R13 (user mandate, applies to every future tool): while the Extrude panel is
open, other design tools must REFUSE (chat message + panel flash) until OK or
Cancel — the user must never land in sketch mode with a tool panel floating.
R12: a hole-less profile may narrow its taper practically to full collapse
(Fusion's "until it becomes flat"), not stop at the old 0.92 barrier.
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch',
      params: { plane: 'XY', offset: 0,
                entities: [{ kind: 'rectangle', w: 20, h: 30, x: 0, y: 0,
                             mode: 'add' }] }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'ex1', op: 'extrude', params: { amount: 10 }, inputs: ['sk1'] },
    'add');
  await loadMesh(true);
}
"""

SKETCH_ACTIVE = """
async () => (await import('/static/js/sketch3d.js')).sketch3DActive()
"""


def row(page, fid):
    return page.locator("#tree .nrow",
                        has=page.locator(".nname", has_text=fid))


def open_edit(page, fid):
    r = row(page, fid)
    r.hover()
    r.locator("button[title^='edit this extrude']").click()
    page.wait_for_selector("#extrudeDialog", state="visible")


def blocks(page):
    return page.text_content("#chatLog").count("Finish the Extrude")


def test_tools_refuse_while_extrude_open(server, page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    open_edit(page, "ex1")

    page.click("#ribbon .rbtn[title='Create Sketch']")     # must refuse
    page.wait_for_timeout(300)
    assert blocks(page) == 1, "refusal must SAY why in chat"
    assert page.is_visible("#extrudeDialog"), "panel must stay open"
    assert not page.evaluate(SKETCH_ACTIVE), "must NOT land in sketch mode"

    sk = row(page, "sk1")                                   # tree ✎ too
    sk.hover()
    sk.locator("button[title^='edit this sketch']").click()
    page.wait_for_timeout(300)
    assert blocks(page) == 2
    assert not page.evaluate(SKETCH_ACTIVE)

    page.click("#exOk")                                     # release
    page.wait_for_selector("#extrudeDialog", state="hidden")
    page.click("#ribbon .rbtn[title='Create Sketch']")      # now allowed
    page.wait_for_timeout(300)
    assert blocks(page) == 2, "no refusal after OK"
    assert not page.errors, page.errors


def test_taper_ring_narrows_to_flat(server, page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    open_edit(page, "ex1")
    page.wait_for_timeout(1000)              # ghost fetch sets safeR/hasHoles

    # rect 20x30, amount 10: inradius 10 -> collapse at 45 deg. The old 0.92
    # barrier stopped at 42.6; Fusion (and now we) allow essentially flat.
    page.fill("#exTaper", "-44.5")               # Fusion sign: negative narrows
    deadline = time.time() + 15
    f = None
    while time.time() < deadline:
        doc = httpx.get(f"{server}/api/doc", timeout=5).json()
        f = next(x for x in doc["features"] if x["id"] == "ex1")
        if (abs(float(f["params"].get("taper", 0)) + 44.5) < 0.05
                and f["status"] == "ok"):
            break
        time.sleep(0.2)
    assert abs(float(f["params"]["taper"]) + 44.5) < 0.05, \
        f"-44.5deg must survive the clamp (old barrier was 42.6): {f['params']}"
    assert f["status"] == "ok"
    assert f["volume"] < 3500, f"nearly-collapsed wedge expected: {f['volume']}"
    page.click("#exCancel")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    assert not page.errors, page.errors


# --------------------------------------------------------------------------
# User 2026-09-03: "if I extrude the body, I can make it narrow or wider using
# the circle option, but after some point it is not narrowing — in Fusion it
# goes until the circle has merged". The ring had a hard ±60° cap in
# viewport.js. Fusion has no fixed cap: its limit is geometric (the walls
# meet), which is exactly what clampFn already models.

BUILD_SHALLOW = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch',
      params: { plane: 'XY', offset: 0,
                entities: [{ kind: 'rectangle', w: 40, h: 40, x: 0, y: 0,
                             mode: 'add' }] }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'ex1', op: 'extrude', params: { amount: 5 }, inputs: ['sk1'] },
    'add');
  await loadMesh(true);
}
"""


def ring_point(page, deg):
    return page.evaluate(
        "async d => (await import('/static/js/viewport.js')).taperRingPointScreen(d)",
        deg)



def drag_ring_to(page, deg):
    """Grab the taper ring's handle (at the current 0°) and drag it, in real
    5° mouse steps, to `deg` — leaving the button DOWN so the caller can read
    the live value before releasing.

    The ring is 1.35x the profile, and in this 1200px window its 0° handle
    lands OFF the canvas (over the chat column) at the fitted zoom — so zoom
    out first, the way a user would (wheel = zoom, positive deltaY = out).
    (LAUNCH-PLAN.md §10 P3 tracks clamping the ring to the viewport.)"""
    c = page.evaluate("() => { const r = document.querySelector('canvas')"
                      ".getBoundingClientRect(); return {l:r.left, t:r.top, w:r.width, h:r.height}; }")
    page.mouse.move(c["l"] + c["w"] / 2, c["t"] + c["h"] / 2)
    for _ in range(16):
        page.mouse.wheel(0, 100)
        page.wait_for_timeout(15)
    page.wait_for_timeout(300)
    p0 = ring_point(page, 0)                  # the handle sits at the current 0°
    assert c["l"] < p0["x"] < c["l"] + c["w"] and c["t"] < p0["y"] < c["t"] + c["h"], \
        f"ring handle still off the canvas: {p0} vs {c}"
    page.mouse.move(p0["x"], p0["y"])
    page.mouse.down()
    step = -5 if deg < 0 else 5
    for d in range(step, deg + step, step):
        p = ring_point(page, d)
        page.mouse.move(p["x"], p["y"])
        page.wait_for_timeout(20)


def test_the_taper_ring_is_not_capped_below_the_geometric_limit(server, page, fresh_doc):
    """A 40x40 profile extruded 5 mm collapses at atan(20/5) = 76°, so 70° must
    be reachable by DRAGGING the ring — it used to stop dead at 60°."""
    page.evaluate(BUILD_SHALLOW)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    open_edit(page, "ex1")
    page.wait_for_function("() => window.__vp.gizmos().ring", timeout=10000)
    page.wait_for_timeout(300)                # the plan has landed, ring placed
    drag_ring_to(page, -70)                   # still holding the mouse
    live = float(page.input_value("#exTaper"))
    assert live < -60, f"the ring stopped at {live} deg while dragging (old cap)"
    page.mouse.up()                           # one verified rebuild
    deadline = time.time() + 15
    f = None
    while time.time() < deadline:
        doc = httpx.get(f"{server}/api/doc", timeout=5).json()
        f = next(x for x in doc["features"] if x["id"] == "ex1")
        if f["status"] == "ok" and float(f["params"].get("taper", 0)) < -60:
            break
        time.sleep(0.2)
    assert abs(float(f["params"]["taper"]) + 70) < 1.5, f["params"]
    assert f["status"] == "ok"
    assert not page.errors, page.errors


def test_past_the_meeting_angle_the_solid_ends_at_the_tip(server, page, fresh_doc):
    """Fusion semantics (user 2026-09-03: "in Fusion they go until -90, until
    flat as the sketch"). Drag the ring to -85 on the 40x40 profile extruded
    5 mm: the walls meet at 76 deg, so the built solid is a low pyramid
    0.999*20/tan(85) = 1.75 mm tall, NOT a 5 mm frustum — and the chat said so."""
    import math
    page.evaluate(BUILD_SHALLOW)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    open_edit(page, "ex1")
    page.wait_for_function("() => window.__vp.gizmos().ring", timeout=10000)
    page.wait_for_timeout(300)
    drag_ring_to(page, -85)                   # still holding the mouse
    live = float(page.input_value("#exTaper"))
    assert live < -80, f"the ring stopped at {live} deg — there must be no barrier"
    page.mouse.up()
    deadline = time.time() + 20
    f = None
    while time.time() < deadline:
        doc = httpx.get(f"{server}/api/doc", timeout=5).json()
        f = next(x for x in doc["features"] if x["id"] == "ex1")
        if f["status"] == "ok" and float(f["params"].get("taper", 0)) < -80:
            break
        time.sleep(0.2)
    t = float(f["params"]["taper"])
    assert abs(t + 85) < 1.5 and f["status"] == "ok", f
    assert float(f["params"]["amount"]) == 5, "the distance box keeps the user's maximum"
    h = 0.999 * 20 / math.tan(math.radians(-t))         # where the walls meet
    top = 40 - 2 * h * math.tan(math.radians(-t))
    frustum = h / 3 * (1600 + top * top + 40 * top)
    assert abs(f["volume"] - frustum) / frustum < 0.02, (f["volume"], frustum, h)
    assert f["volume"] < 1200, "a 5 mm frustum would be ~6000 mm3 — the solid must end at the tip"
    assert "walls meet" in page.text_content("#chatLog")
    assert not page.errors, page.errors


BUILD_TWO_CIRCLES = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch',
      params: { plane: 'XY', offset: 0,
                entities: [{ kind: 'circle', r: 5, x: 0, y: 0, mode: 'add' },
                           { kind: 'circle', r: 15, x: 40, y: 0, mode: 'add' }] },
      inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'ex1', op: 'extrude', params: { amount: 10 }, inputs: ['sk1'] },
    'add');
  await loadMesh(true);
}
"""


def test_the_ghost_tapers_each_outline_toward_its_own_centre(server, page, fresh_doc):
    """User 2026-09-03: "two circles with different diameters — when tapering,
    the ghost goes inclined, not a straight cone". The ghost shrank every
    outline toward the profile's COMMON centroid. Now each outline is its own
    cone: its top stays over its own base, and it ends at its own tip (the r5
    circle at -40 deg meets at 0.999*5/tan40 = 5.95 mm, the r15 one would meet
    at 17.9 so it keeps the full 10)."""
    import math
    page.evaluate(BUILD_TWO_CIRCLES)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    open_edit(page, "ex1")
    page.wait_for_function("() => window.__vp.gizmos().ring", timeout=10000)
    page.wait_for_timeout(300)
    drag_ring_to(page, -40)                   # still holding the mouse
    page.wait_for_timeout(700)                # the per-face meeting depths arrive (lazy fetch)
    p = ring_point(page, -41)                 # one more step re-draws the ghost with them
    page.mouse.move(p["x"], p["y"])
    page.wait_for_timeout(100)
    tops = page.evaluate("() => window.__vp.ghostLoopTops()")
    assert tops and len(tops) == 2, tops
    for t in tops:
        assert abs(t["top"][0] - t["base"][0]) < 0.05 and abs(t["top"][1] - t["base"][1]) < 0.05, \
            ("an outline's ghost leans", t)
    heights = sorted(t["height"] for t in tops)
    deg = -float(page.input_value("#exTaper"))
    assert abs(heights[0] - 0.999 * 5 / math.tan(math.radians(deg))) < 0.15, (heights, deg)
    assert abs(heights[1] - 10) < 0.01, heights
    page.mouse.up()
    assert not page.errors, page.errors
