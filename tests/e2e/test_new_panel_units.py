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
                "swDist", "scOffset", "meInput"]


def choose_unit(page, unit):
    page.locator("button.tab", has_text="File").click()
    page.click("#ribbon .rbtn[title='Settings']")
    page.wait_for_selector("#settingsDialog[open]", timeout=10000)
    page.select_option("#setUnit", unit)
    page.click("#setApply")
    page.wait_for_function(
        f"() => document.getElementById('sUnit').textContent === '{unit}'",
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
