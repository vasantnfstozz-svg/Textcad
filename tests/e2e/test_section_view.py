"""E2E: Section view (Tier 2, specs/section-view.md) — a clipping plane on
every body material, display only. Real clicks and keys; what is asserted is
the plane as three.js applies it (viewport.sectionInfo) and the materials it
sits on.
"""
import os

import pytest

pytest.importorskip("playwright.sync_api")

# a plate with a round pocket in its top: something to look into
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 's', op: 'sketch_on_face',
      params: { face: 'top', offset: 0, entities: [{ kind: 'circle', r: 10, mode: 'add' }] },
      inputs: ['b'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'e', op: 'extrude', params: { amount: -6 }, inputs: ['s'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'cut1', op: 'cut', params: {}, inputs: ['b', 'e'] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""
ADD_BODY = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'd', op: 'disc', params: { radius: 8, thickness: 30 }, inputs: [] }, 'add');
  await loadMesh(true);
}
"""
INFO = "async () => (await import('/static/js/viewport.js')).sectionInfo()"
TOGGLE = "async () => (await import('/static/js/section.js')).toggleSection()"


def info(page):
    return page.evaluate(INFO)


def drag_arrow(page, pixels=60):
    ax = page.evaluate("""async () => {
      const vp = await import('/static/js/viewport.js');
      return vp.extrudeArrowAxisScreen();
    }""")
    bx, by = ax["base"]["x"], ax["base"]["y"]
    tx, ty = ax["tip"]["x"], ax["tip"]["y"]
    L = ((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5
    ux, uy = (tx - bx) / L, (ty - by) / L
    gx, gy = bx + ux * L * 0.5, by + uy * L * 0.5
    page.mouse.move(gx, gy)
    page.mouse.down()
    for i in range(1, 6):
        page.mouse.move(gx + ux * pixels * i / 5, gy + uy * pixels * i / 5)
        page.wait_for_timeout(30)
    page.mouse.up()


def setup(page):
    page.evaluate(BUILD)
    page.wait_for_timeout(1500)


def test_toggle_on_clips_every_body_material_and_the_panel_drives_the_plane(page, fresh_doc, server):
    setup(page)
    assert info(page) == {"on": False, "clipped": 0}
    # the Inspect tab carries the button, and the button opens it
    page.locator("#tabstrip button", has_text="Inspect").click()
    page.wait_for_timeout(200)
    btn = page.locator("#ribbon button[title='Section']")
    assert btn.count() == 1
    btn.click()
    page.wait_for_timeout(300)
    assert page.is_visible("#sectionDialog")
    i = info(page)
    assert i["on"] and i["axis"] == "Z" and i["flip"] is False, i
    assert i["materials"] >= 2 and i["clipped"] == i["materials"], "every body mesh and edge is clipped"
    assert i["quad"] and i["arrow"]
    assert i["offset"] == pytest.approx(0, abs=0.5), "the model's centre along Z"
    assert i["normal"] == pytest.approx([0, 0, -1]) and i["constant"] == pytest.approx(i["offset"])
    assert page.evaluate("() => window.__vp.gizmos()")["section"]
    # a typed offset moves the plane
    page.fill("#scOffset", "3")
    page.wait_for_timeout(400)
    i = info(page)
    assert i["offset"] == 3 and i["constant"] == pytest.approx(3)
    # Flip hides the other side: the normal reverses, the plane stays put
    page.check("#scFlip")
    page.wait_for_timeout(300)
    i = info(page)
    assert i["flip"] and i["normal"] == pytest.approx([0, 0, 1]) and i["constant"] == pytest.approx(-3)
    # another axis starts at the model's centre along it
    page.select_option("#scAxis", "Y")
    page.wait_for_timeout(300)
    i = info(page)
    assert i["axis"] == "Y" and i["normal"] == pytest.approx([0, 1, 0]) and abs(i["offset"]) < 0.5
    shot = os.path.join(os.path.dirname(__file__), "..", "..", "probes", "_section_view.png")
    page.screenshot(path=shot)
    # Close puts the model back whole
    page.click("#scClose")
    page.wait_for_timeout(300)
    assert info(page) == {"on": False, "clipped": 0}
    assert not page.is_visible("#sectionDialog")
    assert not page.evaluate("() => window.__vp.gizmos()")["plane"]
    assert not page.errors, page.errors


def test_the_arrow_drags_the_plane_and_the_box_follows(page, fresh_doc, server):
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(300)
    before = info(page)["offset"]
    drag_arrow(page, 60)
    page.wait_for_timeout(300)
    i = info(page)
    assert i["on"] and abs(i["offset"] - before) > 1, (before, i["offset"])
    assert float(page.input_value("#scOffset")) == pytest.approx(i["offset"], abs=0.02)
    assert i["clipped"] == i["materials"]
    assert not page.errors, page.errors


def test_a_body_added_while_cut_is_cut_and_esc_cancels_a_tool_first(page, fresh_doc, server):
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(300)
    n0 = info(page)["materials"]
    page.evaluate(ADD_BODY)
    page.wait_for_timeout(1500)
    i = info(page)
    assert i["materials"] > n0 and i["clipped"] == i["materials"], i
    # a tool holds the modal lock: Esc cancels IT and leaves the section on
    page.evaluate("async () => (await import('/static/js/measure.js')).openMeasure()")
    page.wait_for_timeout(300)
    assert page.evaluate("async () => (await import('/static/js/state.js')).S.modalTool") == "Measure"
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert page.evaluate("async () => (await import('/static/js/state.js')).S.modalTool") is None
    assert info(page)["on"], "Esc cancelled the tool, not the section"
    # nothing open: Esc closes the section
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert info(page) == {"on": False, "clipped": 0}
    assert not page.errors, page.errors


# ---------------------------------------------------------------------------
# Section takes no modal lock on purpose, so a tool opens while the model is
# cut — and viewport.js says so: "a tool that opens takes them [the gold quad
# and the arrow] for its session, the clipping stays on the materials". The
# reverse was not handled. Section's own Close button is not modal-guarded
# either, so it can be pressed with a tool still open, and endSection() called
# endPlaneQuad() + endExtrudeArrow() unconditionally — deleting the handle the
# open tool is meant to be dragged by (parity rule 3: numbers come from
# dragging handles, the panel is only the value box).
#
# Measured 2026-09-19 on the plate: Section on, top face picked, Extrude
# opened, #scClose pressed — gizmos().arrow went true -> false while
# S.modalTool was still 'Extrude', the Extrude panel was still on screen and
# its taper ring and ghost were still up.
# ---------------------------------------------------------------------------

TO_SCREEN = """
(w) => { const vp = window.__vp; const cv = document.querySelector('#viewer canvas');
  const r = cv.getBoundingClientRect(); const V3 = vp.camera.position.constructor;
  const v = new V3(w[0], w[1], w[2]).project(vp.camera);
  return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - (v.y + 1) / 2) * r.height }; }
"""


def test_closing_the_section_leaves_an_open_tools_handles_alone(page, fresh_doc,
                                                                server):
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(400)
    assert info(page)["on"]

    sp = page.evaluate(TO_SCREEN, [22.0, 15.0, 6.0])   # the plate's top, clear of the pocket
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(700)
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)

    page.click("#scClose")
    page.wait_for_timeout(600)
    assert not info(page)["on"], "the section did not close"
    assert page.evaluate(
        "async () => (await import('/static/js/state.js')).S.modalTool") == "Extrude", \
        "closing the section cancelled the open tool"
    assert page.evaluate("() => window.__vp.gizmos().arrow"), \
        "closing the section deleted the open tool's drag arrow"
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    assert not page.errors, page.errors


def test_flipping_the_section_does_not_take_an_open_tools_arrow_back(
        page, fresh_doc, server):
    """The same rule the other way round: the section is the LOWER-priority
    owner of the two shared gizmos, so Axis / Flip pressed with a tool open
    move the clipping and leave the tool's handle where it is."""
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(400)
    assert info(page)["ownsArrow"], "the section did not make its own arrow"

    sp = page.evaluate(TO_SCREEN, [22.0, 15.0, 6.0])
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(700)
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    assert not info(page)["ownsArrow"], "the tool did not take the arrow"

    page.click("#scFlip")                    # the section moves while Extrude is open
    page.wait_for_timeout(600)
    i = info(page)
    assert i["on"] and i["flip"], f"Flip did not reach the plane: {i}"
    assert i["clipped"] == i["materials"], f"Flip lost the clipping: {i}"
    assert not i["ownsArrow"], "Flip took the open tool's arrow back"
    assert page.evaluate("() => window.__vp.gizmos().arrow"), \
        "Flip left the open tool with no handle at all"
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    assert not page.errors, page.errors


def test_closing_the_section_with_no_tool_open_takes_its_own_handles_away(
        page, fresh_doc, server):
    """The other half: with nothing else using them, Close must leave no gold
    plane and no arrow behind."""
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(400)
    assert page.evaluate("() => window.__vp.gizmos().arrow")
    assert page.evaluate("() => window.__vp.gizmos().plane")
    page.click("#scClose")
    page.wait_for_timeout(500)
    g = page.evaluate("() => window.__vp.gizmos()")
    assert not g["arrow"] and not g["plane"], f"the section left its handles up: {g}"
    assert not info(page)["on"]
    assert not page.errors, page.errors
