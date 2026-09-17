"""E2E: the tool panels honour Settings ▸ Length unit (LAUNCH-PLAN.md §10, P2).

Settings said the unit "changes how lengths are displayed", and the status bar,
the tree and the sketcher honoured it — but every tool panel spelled "(mm)"
into the HTML and read its box with no conversion. Choose inches and the
readouts converted while the boxes did not: typing 2 into Extrude sent 2 mm,
a twelfth of what the user asked for, with the label beside it still saying mm.
Silent wrong geometry, by typing.

Each journey below chooses INCHES through the real Settings dialog, types a
value into a real panel box, and checks what the SERVER stored — millimetres,
25.4 to the inch. The last one checks the other half: a pattern COUNT and a
taper ANGLE are not lengths and must come through untouched.
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

IN = 25.4                                          # one inch, in millimetres

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
# a plate with a Ø10 bore straight through it, for Measure: the bore's wall is
# a diameter the sketch circle DRIVES, so the panel offers its Set box
BUILD_BORE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  const add = (id, op, params, inputs) =>
    postJSON('/api/feature/add', { id, op, params, inputs }, 'add');
  await add('outline', 'sketch', { plane: 'XY', offset: 0, entities: [
    { kind: 'rectangle', w: 60, h: 40, x: 0, y: 0, mode: 'add' }] }, []);
  await add('body', 'extrude', { amount: 12 }, ['outline']);
  await add('bore_sketch', 'sketch', { plane: 'XY', offset: 14, entities: [
    { kind: 'circle', r: 5, x: 0, y: 0, mode: 'add' }] }, []);
  await add('bore_tool', 'extrude', { amount: -20 }, ['bore_sketch']);
  await add('bore', 'cut', {}, ['body', 'bore_tool']);
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
# the viewport's own pick event, exactly as a click on that face emits it —
# Measure's picking is proven in test_measure_picks.py; the step under test
# here is what its box does with the number
PICK = """
async (sel) => {
  const { bus } = await import('/static/js/bus.js');
  bus.emit('pick', { kind: 'face', id: sel.id, body: sel.body, info: sel });
}
"""
PT = [10.0, 5.0, 6.0]                              # a point on the plate's top face


# ---------------------------------------------------------------- helpers --

def features(server):
    return httpx.get(f"{server}/api/doc", timeout=30).json()["features"]


def feature(server, fid):
    return next((f for f in features(server) if f["id"] == fid), None)


def wait_params(server, fid, timeout=60):
    """poll until the feature exists and has finished a build"""
    t0 = time.time()
    f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] in ("ok", "failed"):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid} never finished building: {f}")


def wait_param(server, fid, key, want, timeout=60, tol=1e-6):
    """poll until one stored param reaches `want` — the value the SERVER has —
    AND that value has finished building (a row is `stale` for as long as the
    rebuild it asked for is still running — which on a loaded machine can be
    half a minute for one fillet, hence the patient timeout)"""
    t0 = time.time()
    got = f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        got = f and f["params"].get(key)
        if (got is not None and abs(float(got) - want) <= tol
                and f["status"] in ("ok", "failed")):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid}.{key} is {got!r}, not {want} ({f})")


def setup(page):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(600)


def choose_inches(page):
    """Settings ▸ Length unit ▸ Inches, through the real dialog"""
    page.locator("button.tab", has_text="File").click()
    page.click("#ribbon .rbtn[title='Settings']")
    page.wait_for_selector("#settingsDialog[open]", timeout=10000)
    page.select_option("#setUnit", "in")
    page.click("#setApply")
    page.wait_for_function(
        "() => document.getElementById('sUnit').textContent === 'in'", timeout=10000)


def tool_button(page, tab, title):
    page.locator("button.tab", has_text=tab).click()
    page.wait_for_timeout(150)
    page.click(f"#ribbon .rbtn[title='{title}']")


def click_world(page, pt):
    sp = page.evaluate(TO_SCREEN, pt)
    page.mouse.click(sp["x"], sp["y"])


def pick_top(page):
    click_world(page, PT)
    page.wait_for_function(TOP_PICKED, timeout=15000)


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def select_row(page, fid):
    row(page, fid).click()
    page.wait_for_function(
        "async (id) => (await import('/static/js/state.js')).S.selected === id",
        arg=fid, timeout=10000)


# ----------------------------------------------------------- the journeys --

def test_every_length_label_names_the_display_unit(page, fresh_doc, server):
    """The labels are written by settings.js, not by the HTML: a box that says
    mm while it is read as inches is the bug itself."""
    setup(page)
    labels = "() => [...document.querySelectorAll('[data-unit]')].map(e => e.textContent)"
    assert set(page.evaluate(labels)) == {"mm"}, "millimetres by default"
    choose_inches(page)
    said = page.evaluate(labels)
    assert said and set(said) == {"in"}, said
    # the panels the defect named, each one checked by its own box's label
    for box in ("exDist", "flValue", "chValue", "hoDia", "hoDepth",
                "shThickness", "mvX", "rpDist"):
        txt = page.locator(f"label:has(#{box})").first.text_content()
        assert "(in)" in txt or "in" in txt, f"{box}: {txt!r}"
    # ...and an ANGLE box is not a length: it keeps its degrees
    assert "(°)" in page.locator("label:has(#exTaper)").first.text_content()
    assert "(°)" in page.locator("label:has(#rtAngle)").first.text_content()
    assert page.errors == []


def test_extrude_a_distance_typed_in_inches_is_sent_in_mm(page, fresh_doc, server):
    setup(page)
    choose_inches(page)
    pick_top(page)
    tool_button(page, "Create", "extrude")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    assert page.input_value("#exDist") == "0", "opening builds nothing"
    page.fill("#exDist", "1")                       # one inch
    f = wait_param(server, "extrude1", "amount", IN)
    assert f["op"] == "extrude_face" and f["status"] == "ok", f
    page.click("#exOk")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    assert feature(server, "extrude1")["params"]["amount"] == pytest.approx(IN)
    assert page.errors == []


def test_hole_diameter_and_depth_typed_in_inches_are_sent_in_mm(page, fresh_doc, server):
    setup(page)
    choose_inches(page)
    pick_top(page)
    tool_button(page, "Create", "hole")
    page.wait_for_selector("#holeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    page.fill("#hoDia", "0.25")                     # 6.35 mm
    page.fill("#hoDepth", "0.2")                    # 5.08 mm
    f = wait_param(server, "hole1", "depth", 0.2 * IN)
    assert f["params"]["diameter"] == pytest.approx(0.25 * IN), f["params"]
    assert f["status"] == "ok", f
    assert page.errors == []


def test_fillet_radius_typed_in_inches_is_sent_in_mm(page, fresh_doc, server):
    setup(page)
    choose_inches(page)
    pick_top(page)                                  # a face = every edge of it
    tool_button(page, "Modify", "fillet")
    page.wait_for_selector("#flDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    page.fill("#flValue", "0.1")                    # 2.54 mm
    f = wait_param(server, "fillet1", "radius", 0.1 * IN)
    assert f["status"] == "ok", f
    assert page.errors == []


def test_shell_thickness_typed_in_inches_is_sent_in_mm(page, fresh_doc, server):
    setup(page)
    choose_inches(page)
    pick_top(page)
    tool_button(page, "Modify", "shell")
    page.wait_for_selector("#shellDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    page.fill("#shThickness", "0.1")                # 2.54 mm walls
    f = wait_param(server, "shell1", "thickness", 0.1 * IN)
    assert f["status"] == "ok", f
    assert page.errors == []


def test_move_offsets_typed_in_inches_are_sent_in_mm(page, fresh_doc, server):
    setup(page)
    choose_inches(page)
    select_row(page, "b")                           # the tree is a selection surface
    tool_button(page, "Modify", "move")
    page.wait_for_selector("#mvDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrows", timeout=15000)
    page.fill("#mvX", "1")                          # 25.4 mm
    f = wait_param(server, "move1", "x", IN)
    assert f["params"]["y"] == 0 and f["params"]["z"] == 0, f["params"]
    assert f["status"] == "ok", f
    assert page.errors == []


def test_a_pattern_distance_converts_but_its_COUNT_does_not(page, fresh_doc, server):
    """The other half of the fix: a count is a number of copies and an angle is
    degrees — converting either one would be its own silent wrong geometry."""
    setup(page)
    choose_inches(page)
    select_row(page, "b")
    tool_button(page, "Modify", "linear_pattern")
    page.wait_for_selector("#rpDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    page.fill("#rpCount", "3")
    page.fill("#rpDist", "3")                       # 76.2 mm apart
    f = wait_param(server, "linear_pattern1", "distance", 3 * IN)
    assert f["params"]["count"] == 3, f["params"]["count"]
    assert f["status"] == "ok", f
    assert page.errors == []


def test_measure_sets_a_diameter_typed_in_inches_in_mm(page, fresh_doc, server):
    """Measure's Set box: the readout and the box are both in the display unit,
    and /api/measure/set is in millimetres. Typing 0.5 on a Ø10 bore must leave
    a Ø12.7 mm bore — not Ø0.5 mm."""
    page.evaluate(BUILD_BORE)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=25000)
    page.wait_for_timeout(600)
    choose_inches(page)
    model = httpx.get(f"{server}/api/model", timeout=60).json()
    body = next(b for b in model["bodies"] if b["result"])
    wall = next(f for f in body["faces"] if f["type"] == "CYLINDER")
    tool_button(page, "Inspect", "Measure")     # an ACTION: its title is its name
    page.wait_for_selector("#measureDialog", state="visible", timeout=15000)
    page.evaluate(PICK, {**wall, "body": body.get("id", wall.get("body"))})
    page.wait_for_selector("#meEdit", state="visible", timeout=15000)
    assert page.text_content(".punit") == "in"
    # Ø10 mm read in inches, and the box holds the same number
    assert float(page.input_value("#meInput")) == pytest.approx(10 / IN, abs=5e-4)
    assert "in" in page.text_content("#meValue")
    page.fill("#meInput", "0.5")                    # half an inch across = 12.7 mm
    page.click("#meApply")
    t0 = time.time()
    r = None
    while time.time() - t0 < 25:
        sk = feature(server, "bore_sketch")
        r = sk and sk["params"]["entities"][0]["r"]
        if r is not None and abs(float(r) - 0.25 * IN) < 1e-6:
            break
        time.sleep(0.25)
    assert r == pytest.approx(0.25 * IN), f"the circle is r={r}, not {0.25 * IN}"
    assert page.errors == []
