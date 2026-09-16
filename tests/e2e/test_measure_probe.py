"""E2E: the draggable Measure probe, end to end in a real browser.

User request (2026-08-31): dragging along a flat wall past a curved surface,
"the line should move according to the surface" — the line must stretch to
meet the circle (ACROSS mode), fall back to the nearest distance past its
shadow, and never freeze when the cursor leaves the thin source face.

Run against the e2e suite's OWN server: verifying this on the user's live
instance raced another agent switching tabs mid-drag, and the picks landed on
a different design entirely.
"""

import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  const add = (id, op, params, inputs) =>
    postJSON('/api/feature/add', { id, op, params, inputs }, 'add');
  await add('b', 'plate', { width: 80, depth: 60, thickness: 12 }, []);
  await add('bore', 'with_center_hole', { radius: 5 }, ['b']);
  await loadMesh(true);
  setView('iso');
}
"""

CAM = """
([x, y, z]) => {
  const c = window.__vp.getControls();
  c.object.position.set(x, y, z);
  c.target.set(0, 0, 0);
  c.update();
}
"""


def open_measure(page):
    page.click("#tabstrip button >> text=Inspect")
    page.wait_for_timeout(250)
    page.click("#ribbon button:has-text('Measure')")
    page.wait_for_timeout(400)
    assert page.is_visible("#measureDialog")


def state(page):
    return {
        "A": page.inner_text("#meSelA").strip(),
        "B": page.inner_text("#meSelB").strip(),
        "value": page.inner_text("#meValue").strip(),
        "kind": page.inner_text("#meKind").strip(),
    }


def pick_pair(page):
    """A = the outer -Y wall, B = the bore's inner wall (aimed through the
    mouth from a tilt, well away from the knife-edge rim)."""
    page.evaluate("() => window.__vp.setPickMode(true)")
    page.evaluate(CAM, [0, -220, 120])
    page.wait_for_timeout(700)
    page.evaluate("(c) => window.__vp.pickAtWorld(c)", [0, -30, 0])
    page.wait_for_timeout(900)
    st = state(page)
    assert st["A"] != "—", st
    page.evaluate(CAM, [0, -60, 190])
    page.wait_for_timeout(700)
    # MID-DEPTH on the far wall. The aim is a world POINT, so what decides the
    # pick is where the RAY through it crosses the bore (radius 5), not where
    # the point itself sits: from this camera the ray moves 0.34 mm in y per mm
    # of depth, so the old aim [0, 4.6, -2] pierced the wall 1.9 mm above the
    # BOTTOM rim — three screen pixels from it, inside the 5-pixel edge halo,
    # which then correctly answered with the rim. Through [0, 5, 0] it pierces
    # at z = 0, 6 mm from either rim.
    page.evaluate("(c) => window.__vp.pickAtWorld(c)", [0, 5, 0])
    page.wait_for_timeout(1200)
    st = state(page)
    assert "CYLINDER" in st["B"], f"the bore pick landed on {st['B']}"
    return st


def test_probe_across_then_nearest(page, server, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=bore")
    page.wait_for_timeout(1500)
    open_measure(page)
    st = pick_pair(page)
    assert st["value"].startswith("25.00"), st

    # face the wall for the drag
    page.evaluate(CAM, [0, -200, 150])
    page.wait_for_timeout(800)
    lbl = page.locator("#dimLabel")
    assert "grab" in (lbl.get_attribute("class") or "")
    box = lbl.bounding_box()
    assert box, "the dimension label is not on screen"
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    seen = []
    for wx in (-12, -8, -4, -2, 0, 2, 4, 8, 12):
        sp = page.evaluate("(w) => window.__vp.worldToScreen(w)", [wx, -30, 0])
        if not sp:
            continue
        page.mouse.move(sp["x"], sp["y"])
        page.wait_for_timeout(220)
        st = state(page)
        seen.append((wx, st["value"], st["kind"]))
    page.mouse.up()
    page.wait_for_timeout(300)

    inside = {wx: (v, k) for wx, v, k in seen if abs(wx) <= 4}
    outside = {wx: (v, k) for wx, v, k in seen if abs(wx) >= 8}
    assert inside and outside, seen

    # the flat+round CALIPER (2026-09-01): inside the bore's shadow the value
    # follows the curve — 25.0 facing, 27.0 at x=4 (25+5-3)
    v0 = float(inside[0][0].split()[0])
    assert v0 == pytest.approx(25.0, abs=0.3), seen
    assert "across" in inside[0][1], seen
    v4 = float(inside[4][0].split()[0])
    assert v4 > v0, f"the line did not stretch with the curve: {seen}"
    assert v4 == pytest.approx(27.0, abs=0.4), seen

    # OUTSIDE the shadow both dots clamp at the bore's flank — "the flat side
    # ... should move only till the pillar curve two points" — so the value
    # holds at d0 = 30 and the mode never flips (no dancing, no 'limit' state)
    for wx, (v, k) in outside.items():
        assert "across" in k, seen
        assert float(v.split()[0]) == pytest.approx(30.0, abs=0.3), seen
    assert page.errors == [], page.errors
