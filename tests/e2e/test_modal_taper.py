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


def test_the_taper_ring_is_not_capped_below_the_geometric_limit(server, page, fresh_doc):
    """A 40x40 profile extruded 5 mm collapses at atan(20/5) = 76°, so 70° must
    be reachable by DRAGGING the ring — it used to stop dead at 60°."""
    page.evaluate(BUILD_SHALLOW)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    open_edit(page, "ex1")
    page.wait_for_function("() => window.__vp.gizmos().ring", timeout=10000)
    page.wait_for_timeout(300)                # the plan has landed, ring placed
    # the ring is 1.35x the profile, and in this 1200px window its 0° handle
    # lands OFF the canvas (over the chat column) at the fitted zoom — zoom out
    # first, the way a user would (wheel = zoom, positive deltaY = out)
    c = page.evaluate("() => { const r = document.querySelector('canvas')"
                      ".getBoundingClientRect(); return {l:r.left, t:r.top, w:r.width, h:r.height}; }")
    page.mouse.move(c["l"] + c["w"] / 2, c["t"] + c["h"] / 2)
    for _ in range(16):
        page.mouse.wheel(0, 100)
        page.wait_for_timeout(15)
    page.wait_for_timeout(300)
    p0 = ring_point(page, 0)                  # the handle sits at the current 0°
    assert c["l"] < p0["x"] < c["l"] + c["w"] and c["t"] < p0["y"] < c["t"] + c["h"],         f"ring handle still off the canvas: {p0} vs {c}"
    page.mouse.move(p0["x"], p0["y"])
    page.mouse.down()
    for deg in range(-5, -71, -5):            # a real, gradual drag (negative = narrowing)
        p = ring_point(page, deg)
        page.mouse.move(p["x"], p["y"])
        page.wait_for_timeout(20)
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
