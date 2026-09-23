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


# ---------------------------------------------------------------------------
# Round three's attack on the fix above: the ownership rule had only one half.
# A tool that OPENS takes the shared arrow, and the fix stops the section
# taking it back while the tool holds it — but when the tool ENDS its own
# arrow, that object IS the section's, and nothing gave one back.
#
# Measured 2026-09-19 on the plate: Section on (quad + arrow, ownsArrow true),
# top face picked, Extrude opened (ownsArrow false), Cancel pressed — the model
# stayed cut open on 13 of 13 materials with the gold plane still there and
# gizmos().arrow FALSE. Typing 3 in the offset box moved the plane and still
# produced no arrow; only Axis or Flip, which re-run beginSection, brought one
# back. The section panel's own first sentence is "drag the arrow ... to move
# it" (parity rule 3 — the handle IS the tool).
# ---------------------------------------------------------------------------

def test_the_section_gets_its_handles_back_when_a_tool_lets_them_go(
        page, fresh_doc, server):
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(400)
    assert info(page)["ownsArrow"] and info(page)["ownsQuad"]

    sp = page.evaluate(TO_SCREEN, [22.0, 15.0, 6.0])
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(700)
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    assert not info(page)["ownsArrow"], "the tool did not take the arrow"

    page.click("#exCancel")
    page.wait_for_timeout(1200)
    assert page.evaluate(
        "async () => (await import('/static/js/state.js')).S.modalTool") is None
    i = info(page)
    assert i["on"] and i["clipped"] == i["materials"], f"the section came off: {i}"
    assert page.evaluate("() => window.__vp.gizmos().arrow"), \
        "the section was left cut open with nothing to drag"
    assert i["ownsArrow"] and i["ownsQuad"], \
        f"the handles on screen are not the section's: {i}"

    # and the arrow it got back really drives the plane
    before = i["offset"]
    drag_arrow(page, 60)
    page.wait_for_timeout(400)
    j = info(page)
    assert abs(j["offset"] - before) > 1, (before, j["offset"])
    assert float(page.input_value("#scOffset")) == pytest.approx(j["offset"], abs=0.02)
    assert not page.errors, page.errors


def test_the_handles_come_back_where_the_plane_is_now_not_where_it_was(
        page, fresh_doc, server):
    """The retaken quad and arrow are built from the section as it stands, so
    an offset typed while the tool was open is where they appear — the plane
    never jumps back to where it was when the tool borrowed them."""
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(400)
    sp = page.evaluate(TO_SCREEN, [22.0, 15.0, 6.0])
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(700)
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)

    page.fill("#scOffset", "4")            # the section moves while Extrude is up
    page.wait_for_timeout(500)
    assert info(page)["offset"] == 4

    page.click("#exCancel")
    page.wait_for_timeout(1200)
    i = info(page)
    assert i["on"] and i["offset"] == 4 and i["ownsArrow"], i
    q = page.evaluate("() => window.__vp.planeQuadInfo()")
    assert q["origin"][2] == pytest.approx(4, abs=0.01), \
        f"the gold plane came back at the old offset: {q}"
    assert not page.errors, page.errors


# ---------------------------------------------------------------------------
# Round FOUR's attack on the fix above. `retakeSectionHandles()` gives up when
# `section.handles` is null, and `beginSection(..., handles=false)` set it to
# null — so the one door the section panel keeps open under a tool takes the
# handles away for good. The panel is not modal-guarded (it is a view state),
# so Axis and Flip stay clickable with a tool open, and both re-run
# beginSection, which is where handles=false comes from.
#
# Measured 2026-09-19 on the plate: Section on (quad + arrow, ownsQuad and
# ownsArrow true), the top face picked, Extrude opened (ownsArrow false),
# #scFlip pressed — quad FALSE at once — then Cancel: quad false, arrow false,
# ownsQuad false, ownsArrow false, with the model still cut open on 13 of 13
# materials and the panel still telling the user to drag the arrow. Only
# closing and reopening the whole section brought one back.
# ---------------------------------------------------------------------------

def test_flip_under_a_tool_does_not_cost_the_section_its_handles_for_good(
        page, fresh_doc, server):
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(400)
    assert info(page)["ownsArrow"] and info(page)["ownsQuad"]

    sp = page.evaluate(TO_SCREEN, [22.0, 15.0, 6.0])
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(700)
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    assert not info(page)["ownsArrow"], "the tool did not take the arrow"

    page.click("#scFlip")                  # the panel is live: it takes no lock
    page.wait_for_timeout(600)
    assert info(page)["flip"], "Flip did not reach the plane"
    assert page.evaluate("() => window.__vp.gizmos().arrow"), \
        "Flip left the open tool with no handle"

    page.click("#exCancel")
    page.wait_for_timeout(1200)
    i = info(page)
    assert i["on"] and i["clipped"] == i["materials"], f"the section came off: {i}"
    assert page.evaluate("() => window.__vp.gizmos().arrow"), \
        "after a Flip under the tool the section was left with nothing to drag"
    assert i["ownsArrow"] and i["ownsQuad"], \
        f"the handles on screen are not the section's: {i}"
    assert i["flip"], "the retaken handles lost the flip"

    # ...and the arrow it got back really drives the plane
    before = i["offset"]
    drag_arrow(page, 60)
    page.wait_for_timeout(400)
    j = info(page)
    assert abs(j["offset"] - before) > 1, (before, j["offset"])
    assert not page.errors, page.errors


def test_an_axis_change_under_a_tool_does_not_cost_them_either(
        page, fresh_doc, server):
    """The same door, the other control: Axis re-runs beginSection too."""
    setup(page)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(400)
    sp = page.evaluate(TO_SCREEN, [22.0, 15.0, 6.0])
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(700)
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)

    page.select_option("#scAxis", "Y")
    page.wait_for_timeout(600)
    assert info(page)["axis"] == "Y"

    page.click("#exCancel")
    page.wait_for_timeout(1200)
    i = info(page)
    assert i["on"] and i["axis"] == "Y", i
    assert i["ownsArrow"] and i["ownsQuad"], \
        f"an axis change under the tool cost the section its handles: {i}"
    assert not page.errors, page.errors


def test_esc_cancels_a_pending_plane_pick_and_leaves_the_section(page, fresh_doc, server):
    """Review, 2026-09-23: the section's Escape stood down only for a tool
    holding the modal lock. Create Sketch's plane pick and a half-drawn
    sketch shape own Escape WITHOUT that lock, so one key cancelled the pick
    AND closed the section - the panel's own rule is one Esc, one thing."""
    page.evaluate(BUILD)
    page.wait_for_timeout(1500)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(300)
    assert info(page)["on"]
    page.evaluate("async () => (await import('/static/js/viewport.js')).beginPlanePick(() => {})")
    page.wait_for_timeout(200)
    assert page.is_visible("#placeHint")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.is_visible("#placeHint"), "the pick is cancelled"
    assert info(page)["on"], "one Esc closed the section too"
    page.keyboard.press("Escape")                 # nothing else open: now it closes
    page.wait_for_timeout(300)
    assert not info(page)["on"]
    assert not page.errors, page.errors


def test_esc_ends_a_half_drawn_sketch_shape_and_leaves_the_section(page, fresh_doc, server):
    page.evaluate(BUILD)
    page.wait_for_timeout(1500)
    page.evaluate(TOGGLE)
    page.wait_for_timeout(300)
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XY');
      await new Promise(r => setTimeout(r, 900));
      sk.setSketchTool('rect');
      const { bus } = await import('/static/js/bus.js');
      bus.emit('sk3d-move', { x: 0, y: 0, tol: 1, down: false });
      bus.emit('sk3d-down', { x: 0, y: 0, tol: 1 }); bus.emit('sk3d-up', {});
      await new Promise(r => setTimeout(r, 200));
    }""")
    page.mouse.click(5, 5)                          # focus off the draw box
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert info(page)["on"], "the Esc that dropped the half-drawn rectangle closed the section"
    assert not page.errors, page.errors
