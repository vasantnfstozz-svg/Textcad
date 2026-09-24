"""E2E: the panels built AFTER the display-unit fix honour it too.

8f25a34 made one rule for length boxes: settings.js writes every label marked
`data-unit`, so no panel can name a unit its box is not read in — "a box
labelled mm that is read as inches is how a 2 becomes 50.8" (static/index.html).

The five Tier 2 tools landed after it. Sweep's Distance and Section view's
Offset are both read in the display unit (`mm()` / `toMm()`), and both spelled
`<span class="unitlabel">(mm)</span>` into the HTML — a class nothing paints.
Measured in a real browser with the app in inches: Extrude said "Distance (in)"
and Fillet "Radius (in)" while Sweep still said "Distance (mm)" and Section
"Offset (mm)". Typing 2 into Sweep's Distance beside a label saying mm sweeps
50.8 mm and stores it.

Section view carries a second one. It is a VIEW STATE, not a command: it takes
no modal lock, so Settings — which modalGuard blocks for every tool panel —
opens while it is on screen, and its `settings-changed` handler re-read the box
under the NEW unit instead of remembering the plane's millimetres. Measured:
the plane at 4 mm, switch to inches, tick Flip — the plane jumped to 101.6 mm
(sectionInfo) with the box still reading 4.
"""
import pytest

pytest.importorskip("playwright.sync_api")

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
# the words printed beside each length box, whatever panel they live in
LABELS = """
(ids) => {
  const out = {};
  for (const id of ids) {
    const el = document.getElementById(id);
    // the ROW the box lives in: its <label> where it has one, otherwise its
    // parent — Measure's Set box is an input, a unit span and a button in a div
    const l = el && (el.closest('label') || el.parentElement);
    out[id] = l ? l.textContent.trim().replace(/\\s+/g, ' ') : '(no label)';
  }
  return out;
}
"""
SECTION = "async () => (await import('/static/js/viewport.js')).sectionInfo()"

# every box that is read as a LENGTH in the display unit
# `meInput` — Measure's Set box — belongs here too and was missing until the
# round-two walk below enumerated the page and found it unclassified. Its own
# markup was already right (a `punit` span with data-unit); only this list,
# which is hand-kept, had the hole. That is the reason for the walk.
LENGTH_BOXES = ["exDist", "exDist2", "flValue", "chValue", "hoDia", "hoDepth",
                "hoCbDia", "hoCbDepth", "hoCsDia", "shThickness",
                "mvX", "mvY", "mvZ", "rpDist", "rpDist2",
                "swDist", "scOffset", "meInput", "plOffset"]


def choose_unit(page, unit):
    page.locator("button.tab", has_text="File").click()
    page.click("#ribbon .rbtn[title='Settings']")
    page.wait_for_selector("#settingsDialog[open]", timeout=10000)
    page.select_option("#setUnit", unit)
    page.click("#setApply")
    page.wait_for_function(
        f"() => document.querySelector('[data-unit]').textContent === '{unit}'",
        timeout=10000)


# ---------------------------------------------------------------------------
# Round two: the WALK. The list above is hand-kept, so a length box added to a
# new panel and left out of it is invisible again — which is exactly how Sweep
# and Section view shipped saying "(mm)" while being read in inches. This walks
# every <input type=number> the page actually has and insists each one is in a
# named class here. A new numeric box fails the test until someone says which
# kind it is, and a LENGTH fails unless settings.js writes its unit.
#
# (The spec editor's boxes are plain text inputs, not numbers, and say "mm" in
# their own labels because a spec is stored in mm. The feature tree's editable
# values and the Parameters panel's cells are neither — see the review report.)
# ---------------------------------------------------------------------------

DEGREES = {"exTaper", "rvAngle", "rvAngle2", "rtAngle", "cpAngle", "hoCsAngle"}
COUNTS = {"cpCount", "rpCount", "rpCount2"}
# a SETTING, in millimetres whatever the screen displays — the grid and the
# snap are properties of the sketch, not readouts of the model
ALWAYS_MM = {"setGrid", "setSnap"}

CLASSIFY = """
() => {
  const out = [];
  for (const inp of document.querySelectorAll('input[type=number]')) {
    const row = inp.closest('label') || inp.parentElement;
    const u = row && row.querySelector('[data-unit]');
    out.push({ id: inp.id,
               unitSpan: u ? u.textContent : null,
               text: (row ? row.textContent : '').replace(/\\s+/g, ' ').trim() });
  }
  return out;
}
"""


def test_every_numeric_box_in_the_page_is_classified(page, fresh_doc, server):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    choose_unit(page, "in")
    found = page.evaluate(CLASSIFY)
    ids = {b["id"] for b in found}
    known = set(LENGTH_BOXES) | DEGREES | COUNTS | ALWAYS_MM
    assert not ids - known, (
        "these numeric boxes are in no class — say whether each is a length "
        f"(data-unit), an angle, a count or always-mm: {sorted(ids - known)}")
    assert not set(LENGTH_BOXES) - ids, \
        f"LENGTH_BOXES names boxes the page does not have: {sorted(set(LENGTH_BOXES) - ids)}"

    by_id = {b["id"]: b for b in found}
    for i in LENGTH_BOXES:
        b = by_id[i]
        assert b["unitSpan"] == "in", \
            f"{i} is read as a length but its unit reads {b['unitSpan']!r}: {b['text']}"
    for i in DEGREES:
        b = by_id[i]
        assert b["unitSpan"] is None and "°" in b["text"], \
            f"{i} is an angle in degrees: {b}"
    for i in COUNTS:
        b = by_id[i]
        assert b["unitSpan"] is None and "(" not in b["text"], \
            f"{i} is a count and must carry no unit at all: {b}"
    for i in ALWAYS_MM:
        b = by_id[i]
        assert b["unitSpan"] is None and "mm" in b["text"], \
            f"{i} is stored in mm whatever is displayed, and must say so: {b}"
    assert page.errors == []


def test_every_length_box_names_the_display_unit(page, fresh_doc, server):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    choose_unit(page, "in")
    import re
    labels = page.evaluate(LABELS, LENGTH_BOXES)
    # the unit as a WORD: most boxes say "Distance (in)", Measure's Set box
    # puts the word beside the input instead. Either way it may not say mm.
    wrong = {k: v for k, v in labels.items()
             if re.search(r"\bmm\b", v) or not re.search(r"\bin\b", v)}
    assert not wrong, ("these length boxes do not name the unit they are read "
                       f"in while the app is in inches: {wrong}")
    assert page.errors == []


def test_the_section_plane_keeps_its_place_when_the_unit_changes(page, fresh_doc,
                                                                 server):
    """Section takes no modal lock, so Settings opens over it. The plane must
    stay where it is; only the words and the number beside it change."""
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.locator("button.tab", has_text="Inspect").click()
    page.click("#ribbon .rbtn[title='Section']")
    page.wait_for_selector("#sectionDialog", state="visible", timeout=15000)
    page.wait_for_timeout(500)
    page.fill("#scOffset", "4")
    page.wait_for_timeout(500)
    assert abs(page.evaluate(SECTION)["offset"] - 4.0) < 1e-6

    choose_unit(page, "in")
    page.wait_for_timeout(400)
    assert abs(page.evaluate(SECTION)["offset"] - 4.0) < 1e-6, \
        "switching the unit MOVED the section plane"
    shown = float(page.input_value("#scOffset"))
    assert abs(shown - 4.0 / 25.4) < 5e-4, \
        f"the box says {shown} in, and 4 mm is {4/25.4:.4f} in"

    # ...and the next thing the user touches must not move it either. The
    # tolerance is the inch box's own precision (4 dp = 0.00025 mm a step, so
    # 4 mm shows as 0.1575 in and reads back as 4.0005): the bug this guards
    # moved the plane by a FACTOR of 25.4, to 101.6 mm.
    page.locator("button.tab", has_text="Inspect").click()
    page.click("#scFlip")
    page.wait_for_timeout(600)
    after = page.evaluate(SECTION)["offset"]
    assert abs(after - 4.0) < 0.01, \
        f"ticking Flip after the unit change moved the plane to {after} mm"
    assert page.errors == []


# a length the inch grid cannot hold exactly: 12.7183 mm is 0.50072047... in
AWKWARD = 12.7183


def test_a_length_box_does_not_drift_further_on_every_reopen(page, fresh_doc,
                                                             server):
    """mm keeps the number itself; inches quantise it ONCE to the box's own
    precision and then hold it. A tool reopened and OK'd twice must not walk
    the dimension a little further each time."""
    ROUND_TRIP = """
    async (n) => {
      const { setLen, mm } = await import('/static/js/tool.js');
      const out = [];
      let v = n;
      for (let i = 0; i < 4; i++) { setLen('exDist', v); v = mm('exDist'); out.push(v); }
      return out;
    }
    """
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    in_mm = page.evaluate(ROUND_TRIP, AWKWARD)
    assert all(abs(v - AWKWARD) < 1e-9 for v in in_mm), \
        f"millimetres changed the number: {in_mm}"
    choose_unit(page, "in")
    in_inches = page.evaluate(ROUND_TRIP, AWKWARD)
    # one quantisation to 4 dp of an inch (at most 0.00127 mm), then still
    assert abs(in_inches[0] - AWKWARD) < 0.002, \
        f"the first inch round trip moved it too far: {in_inches}"
    assert len(set(in_inches)) == 1, f"it drifts on every reopen: {in_inches}"
    assert page.errors == []


# ---------------------------------------------------------------------------
# Round three's attack on the walk above: it is `querySelectorAll` over the page
# AT REST, and three numeric boxes do not exist then. They are built by JS while
# the user is working:
#
#   placement.js:68     the place-a-primitive popup's dimension and position
#                       boxes (Create ▸ Box, then a click on the ground)
#   sketcher.js:1941    the sketch's dimension editor beside a selected shape
#   sketcher.js:2017    the sketch's draw-time dimension box
#
# Measured with the app in inches: the walk at rest found 29 boxes and none of
# these. The two sketch ones are right — `toMm()` in, `unitLabel()` on the
# label. The placement popup hard-writes "(mm)" and reads the number as
# millimetres, so it is TRUTHFUL but it is the one model dimension in the app
# that does not follow Settings ▸ Length unit: with the app in inches, a plate
# placed at "width (mm) 40" is 40 mm while every other box is inches. Recorded
# as an open item rather than changed here — it needs its own `settings-changed`
# handler, which is a fourth one, and it is the same class as the feature
# tree's raw-millimetre rows.
#
# This test walks the page again with each of those boxes actually on screen,
# so the next runtime box cannot hide the way Sweep and Section did.
# ---------------------------------------------------------------------------

OPEN_SKETCH = """
async (tool) => {
  const sk = await import('/static/js/sketcher.js');
  sk.openSketchEditor('XY');
  await new Promise(r => setTimeout(r, 900));
  sk.setSketchTool(tool);
}
"""
SK = """
async (a) => {
  const [kind, x, y] = a;
  const { bus } = await import('/static/js/bus.js');
  if (kind === 'down') { bus.emit('sk3d-down', { x, y, tol: 1 }); bus.emit('sk3d-up', {}); }
  else bus.emit('sk3d-move', { x, y, tol: 1, down: false });
  await new Promise(r => setTimeout(r, 150));
}
"""

# Every numeric box on the page RIGHT NOW, named so an id-less one still has a
# stable key, with the unit exactly as the user reads it beside the box.
WALK = """
() => {
  const out = [];
  for (const inp of document.querySelectorAll('input[type=number]')) {
    const row = inp.closest('label') || inp.parentElement;
    const text = (row ? row.textContent : '').replace(/\\s+/g, ' ').trim();
    const host = inp.closest('[id]');
    const key = inp.id || ((host ? host.id : '?') + ':' +
                           (inp.dataset.dim || text.split(/[\\s(]/)[0] || '?'));
    const span = row && (row.querySelector('[data-unit]') || row.querySelector('.dimunit'));
    const paren = text.match(/\\(([^)]*)\\)/);
    out.push({ key, text,
               unit: span ? span.textContent.trim() : (paren ? paren[1].trim() : null) });
  }
  return out;
}
"""

# the runtime boxes, by the key above, and what each one is.
#
# ROUND FOUR: the placement popup follows Settings ▸ Length unit now, like
# every other model dimension. It used to hard-write "(mm)" and read the
# numbers as millimetres — truthful, but with the app in inches a plate placed
# at "width (mm) 40" was 40 mm while every other box on the screen was inches.
RUNTIME_LENGTHS = {"skDimDraw:r", "skDimEdit3d:r",                  # toMm()
                   "placePopup:width", "placePopup:depth", "placePopup:thickness",
                   "placePopup:circumradius"}
# `sides` is polygon_plate's side COUNT and the popup labelled it "sides (mm)",
# which is the same lie the other way round — and reading 6 as 6 inches would
# have made a 152-sided plate.
RUNTIME_COUNTS = {"placePopup:sides"}
# the three position boxes are labelled plain x / y / z under ONE heading, so
# the heading is what has to name the unit
RUNTIME_HEADED_LENGTHS = {"placePopup:x", "placePopup:y", "placePopup:z"}


def test_the_walk_also_sees_the_boxes_that_are_built_while_you_work(
        page, fresh_doc, server):
    choose_unit(page, "in")
    at_rest = {b["key"] for b in page.evaluate(WALK)}

    # --- the placement popup: Create ▸ Box, then a click on the ground ---
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(250)
    page.click("#ribbon .rbtn[title='plate']")
    page.wait_for_timeout(400)
    cv = page.locator("#viewer canvas").bounding_box()
    page.mouse.click(cv["x"] + cv["width"] * 0.5, cv["y"] + cv["height"] * 0.62)
    page.wait_for_selector("#placePopup", state="visible", timeout=20000)
    page.wait_for_timeout(600)
    walked = page.evaluate(WALK)
    place = {b["key"] for b in walked} - at_rest
    assert place, "the placement popup put no numeric box on the page"
    known = RUNTIME_LENGTHS | RUNTIME_COUNTS | RUNTIME_HEADED_LENGTHS
    assert not place - known, \
        ("the placement popup has numeric boxes in no class — say what each is: "
         f"{sorted(place - known)}")
    for b in walked:
        if b["key"] in RUNTIME_LENGTHS:
            assert b["unit"] == "in", \
                (f"{b['key']} is read with toMm() while the app is in inches "
                 f"and says {b['unit']!r}: {b}")
    assert "position (in)" in page.inner_text("#placePopup").lower(), \
        "the position boxes are labelled plain x / y / z — only this heading " \
        "tells the user which unit they are typed in"
    page.click("#placePopup .pp-foot button")
    page.wait_for_timeout(400)

    # --- the polygon's SIDE COUNT is not a length and must carry no unit ---
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(250)
    page.click("#ribbon .rbtn[title='polygon_plate']")
    page.wait_for_timeout(400)
    cv = page.locator("#viewer canvas").bounding_box()
    page.mouse.click(cv["x"] + cv["width"] * 0.5, cv["y"] + cv["height"] * 0.42)
    page.wait_for_selector("#placePopup", state="visible", timeout=20000)
    page.wait_for_timeout(600)
    poly = page.evaluate(WALK)
    got = {b["key"] for b in poly} - at_rest
    assert not got - known, f"the polygon popup has boxes in no class: {sorted(got - known)}"
    for b in poly:
        if b["key"] in RUNTIME_COUNTS:
            assert b["unit"] is None and "(" not in b["text"], \
                f"{b['key']} is a count and must carry no unit at all: {b}"
        if b["key"] in RUNTIME_LENGTHS:
            assert b["unit"] == "in", f"{b['key']} does not name the display unit: {b}"
    page.click("#placePopup .pp-foot button")
    page.wait_for_timeout(400)

    # --- the sketch's draw-time box and its dimension editor ---
    page.evaluate(OPEN_SKETCH, "circle")
    page.evaluate(SK, ["down", 0, 0])
    page.evaluate(SK, ["move", 10, 0])
    page.wait_for_selector("#skDimDraw", state="visible", timeout=10000)
    drawing = page.evaluate(WALK)
    drew = {b["key"] for b in drawing} - at_rest
    assert drew, "the draw-time dimension box put no numeric box on the page"
    assert not drew - RUNTIME_LENGTHS - RUNTIME_COUNTS, \
        ("the sketch's draw-time boxes are in no class: "
         f"{sorted(drew - RUNTIME_LENGTHS - RUNTIME_COUNTS)}")

    page.keyboard.type("12.5")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    # setSketchTool toggles, so this puts the draw tool away; then a click on
    # the circle SELECTS it and its dimension editor appears beside it
    page.evaluate("async () => (await import('/static/js/sketcher.js'))"
                  ".setSketchTool('circle')")
    page.wait_for_timeout(250)
    page.evaluate(SK, ["down", 0, 0])
    page.wait_for_selector("#skDimEdit3d", state="visible", timeout=10000)
    editing = page.evaluate(WALK)
    edited = {b["key"] for b in editing} - at_rest
    assert edited, "the dimension editor put no numeric box on the page"
    assert not edited - RUNTIME_LENGTHS - RUNTIME_COUNTS, \
        f"the sketch's dimension editor is in no class: {sorted(edited)}"

    # every runtime LENGTH says the unit it is read in, like every other box
    for b in drawing + editing:
        if b["key"] in RUNTIME_LENGTHS:
            assert b["unit"] == "in", \
                (f"{b['key']} is read with toMm() while the app is in inches "
                 f"and says {b['unit']!r}: {b}")
    assert page.errors == []


# ---------------------------------------------------------------------------
# Round four: the placement popup FOLLOWS the display unit now, and the proof
# is what the SERVER stored. The user has already chosen, for the tool panels,
# that a box is typed in the unit on the screen; this was the one model
# dimension left reading millimetres whatever the app said.
# ---------------------------------------------------------------------------

DOC = "async () => await (await fetch('/api/doc')).json()"


def params_of(page, op):
    """The params of the one feature with this op — the id is auto-numbered
    from whatever the browser already had, so it is not a stable handle."""
    doc = page.evaluate(DOC)
    f = next((f for f in doc["features"] if f["op"] == op), None)
    assert f, f"no {op} in {[(x['id'], x['op']) for x in doc['features']]}"
    return f["params"]


def place_a_plate(page):
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(250)
    page.click("#ribbon .rbtn[title='plate']")
    page.wait_for_timeout(400)
    cv = page.locator("#viewer canvas").bounding_box()
    page.mouse.click(cv["x"] + cv["width"] * 0.5, cv["y"] + cv["height"] * 0.62)
    page.wait_for_selector("#placePopup", state="visible", timeout=20000)
    page.wait_for_timeout(600)


def test_a_dimension_typed_in_the_placement_popup_is_stored_in_that_unit(
        page, fresh_doc, server):
    """40 in the popup with the app in inches is 40 INCHES — 1016 mm in the
    document — not 40 mm sitting under a label that says inches."""
    choose_unit(page, "in")
    place_a_plate(page)
    # it opens on the DEFAULTS in the display unit: 40 mm is 1.5748 in
    started = float(page.evaluate(
        "() => [...document.querySelectorAll('#placePopup .pp-field')]"
        ".find(f => f.textContent.trim().startsWith('width')).querySelector('input').value"))
    assert abs(started - 40 / 25.4) < 5e-4, \
        f"the popup opened showing {started} for a 40 mm plate in inches"

    page.evaluate("""
      () => { const f = [...document.querySelectorAll('#placePopup .pp-field')]
                .find(f => f.textContent.trim().startsWith('thickness'));
              const i = f.querySelector('input');
              i.value = '2'; i.dispatchEvent(new Event('input', { bubbles: true })); }""")
    page.wait_for_timeout(1500)
    p = params_of(page, "plate")
    assert abs(p["thickness"] - 50.8) < 1e-6, \
        f"2 in was stored as {p['thickness']} mm — the box is labelled in: {p}"
    assert abs(p["width"] - 40) < 1e-6 and abs(p["depth"] - 40) < 1e-6, \
        f"the boxes the user did not touch moved: {p}"
    page.click("#placePopup .pp-foot button")
    assert page.errors == []


def test_the_open_placement_popup_follows_a_unit_change(page, fresh_doc, server):
    """It takes no modal lock, so Settings opens over it — the one other panel
    (Section view) whose numbers have to be rewritten under the user's hands.
    The millimetres are the STATE's: re-reading the box under the new unit
    would leave the number alone and silently multiply what it means."""
    place_a_plate(page)                                  # in mm
    def width():
        return float(page.evaluate(
            "() => [...document.querySelectorAll('#placePopup .pp-field')]"
            ".find(f => f.textContent.trim().startsWith('width'))"
            ".querySelector('input').value"))
    assert width() == 40
    choose_unit(page, "in")
    page.wait_for_timeout(400)
    assert abs(width() - 40 / 25.4) < 5e-4, \
        f"the open popup still reads {width()} after switching to inches"
    assert "width (in)" in page.inner_text("#placePopup").lower(), \
        "the label did not follow the unit"
    p = params_of(page, "plate")
    assert abs(p["width"] - 40) < 1e-6, \
        f"switching the unit RESIZED the plate: {p}"
    page.click("#placePopup .pp-foot button")
    assert page.errors == []


def test_the_polygons_side_count_is_never_converted(page, fresh_doc, server):
    """`sides` is the one param in DEFAULTS that is not a length. Read as a
    length in inches, 6 would become 152."""
    choose_unit(page, "in")
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(250)
    page.click("#ribbon .rbtn[title='polygon_plate']")
    page.wait_for_timeout(400)
    cv = page.locator("#viewer canvas").bounding_box()
    page.mouse.click(cv["x"] + cv["width"] * 0.5, cv["y"] + cv["height"] * 0.62)
    page.wait_for_selector("#placePopup", state="visible", timeout=20000)
    page.wait_for_timeout(600)
    assert params_of(page, "polygon_plate")["sides"] == 6
    page.evaluate("""
      () => { const f = [...document.querySelectorAll('#placePopup .pp-field')]
                .find(f => f.textContent.trim().startsWith('sides'));
              const i = f.querySelector('input');
              i.value = '8'; i.dispatchEvent(new Event('input', { bubbles: true })); }""")
    page.wait_for_timeout(1500)
    p = params_of(page, "polygon_plate")
    assert p["sides"] == 8, f"the side count went through the unit: {p}"
    assert abs(p["circumradius"] - 20) < 1e-6, p
    page.click("#placePopup .pp-foot button")
    assert page.errors == []
