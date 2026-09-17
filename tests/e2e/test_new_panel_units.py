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
    const l = el && el.closest('label');
    out[id] = l ? l.textContent.trim().replace(/\\s+/g, ' ') : '(no label)';
  }
  return out;
}
"""
SECTION = "async () => (await import('/static/js/viewport.js')).sectionInfo()"

# every box that is read as a LENGTH in the display unit
LENGTH_BOXES = ["exDist", "exDist2", "flValue", "chValue", "hoDia", "hoDepth",
                "hoCbDia", "hoCbDepth", "hoCsDia", "shThickness",
                "mvX", "mvY", "mvZ", "rpDist", "rpDist2",
                "swDist", "scOffset"]


def choose_unit(page, unit):
    page.locator("button.tab", has_text="File").click()
    page.click("#ribbon .rbtn[title='Settings']")
    page.wait_for_selector("#settingsDialog[open]", timeout=10000)
    page.select_option("#setUnit", unit)
    page.click("#setApply")
    page.wait_for_function(
        f"() => document.getElementById('sUnit').textContent === '{unit}'",
        timeout=10000)


def test_every_length_box_names_the_display_unit(page, fresh_doc, server):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    choose_unit(page, "in")
    labels = page.evaluate(LABELS, LENGTH_BOXES)
    wrong = {k: v for k, v in labels.items() if "(mm)" in v or "(in)" not in v}
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
