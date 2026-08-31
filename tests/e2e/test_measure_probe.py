"""E2E: the draggable Measure probe, end to end in a real browser.

User request (2026-08-31): dragging along a flat wall past a curved surface,
"the line should move according to the surface" — the line must stretch to
meet the circle (ACROSS mode), fall back to the nearest distance past its
shadow, and never freeze when the cursor leaves the thin source face.

Run against the e2e suite's OWN server: verifying this on the user's live
instance raced another agent switching tabs mid-drag, and the picks landed on
a different design entirely.
"""
import re

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
    page.evaluate("(c) => window.__vp.pickAtWorld(c)", [0, 4.6, -2])
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
    entering = {wx: (v, k) for wx, v, k in seen if wx <= -8}
    leaving = {wx: (v, k) for wx, v, k in seen if wx >= 8}
    assert inside and entering and leaving, seen

    # approaching from outside, before any across exists: honest nearest
    for wx, (v, k) in entering.items():
        assert "nearest" in k, seen

    # ACROSS inside the bore's shadow: the line stretches with the circle —
    # 25.0 at centre, longer off-centre — and says which mode it is in
    v0 = float(inside[0][0].split()[0])
    assert v0 == pytest.approx(25.0, abs=0.3), seen
    assert "across" in inside[0][1], seen
    v4 = float(inside[4][0].split()[0])
    assert v4 > v0, f"the line did not stretch with the curve: {seen}"
    # at x=4 the ray meets the r=5 circle at y=-sqrt(25-16)=-3: 25+5-3 = 27
    assert v4 == pytest.approx(27.0, abs=0.4), seen

    # past the curve's extreme the line CLAMPS at its last real crossing —
    # flipping to nearest teleported the far dot on every micro-move (user
    # report: "the line is dancing or vibrating"); "that is the limit …
    # after that no need to move"
    for wx, (v, k) in leaving.items():
        assert "limit" in k, seen
        assert float(v.split()[0]) == pytest.approx(v4, abs=1e-6),             f"the clamp did not hold the last crossing: {seen}"
    assert page.errors == [], page.errors
