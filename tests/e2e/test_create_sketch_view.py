"""E2E: Create Sketch's plane pick opens on ONE fixed, framed view.

The user (2026-09-24): "when I press Create Sketch and choose the plane ... the
position is different sometimes, not aligned. When I click Create Sketch it has
to go to a proper fixed position, a correct zoomed mid position, every time."

Two causes, both locked in here:
1. The pick opened wherever the camera happened to be. It now flies to the
   home (iso) direction, aimed at the middle of the plane squares and the
   bodies, backed off just far enough for all of them to fit on screen.
2. A design with no body kept the LAST design's centre and size, so after a
   part far from the origin, an empty design drew its squares where that part
   had been. The fit is the current document's now; an empty one is the origin.
"""
import math

import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async (shift) => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 }, inputs: [] }, 'add');
  if (shift) await postJSON('/api/feature/add',
    { id: 'shift', op: 'move', params: { x: shift[0], y: shift[1], z: shift[2] },
      inputs: ['b'] }, 'add');
  await loadMesh(true);
}
"""
CREATE_SKETCH = "() => document.querySelector('.rbtn[title=\"Create Sketch\"]').click()"
PICK_ARMED = "() => document.getElementById('placeHint').style.display === 'block'"
PICK_OVER = "() => document.getElementById('placeHint').style.display === 'none'"
TWEEN_DONE = "() => window.__vp.getControls().enabled === true"
POSE = """() => ({ pos: window.__vp.camera.position.toArray(),
                   target: window.__vp.getControls().target.toArray() })"""
ISO = [0.7, -0.7, 0.55]
# the in-plane half-axes of each origin square: XY spans x,y; XZ x,z; YZ y,z
SPAN = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}


@pytest.fixture()
def plate(page, fresh_doc):
    page.evaluate(BUILD, None)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    return page


def _open_pick(page):
    page.evaluate(CREATE_SKETCH)
    page.wait_for_function(PICK_ARMED, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    return page.evaluate(POSE)


def _close_pick(page):
    page.keyboard.press("Escape")
    page.wait_for_function(PICK_OVER, timeout=15000)


def _square_corners(page):
    out = []
    for q in page.evaluate("window.__vp.originPlaneInfo()"):
        a, b = SPAN[q["plane"]]
        h = q["size"] / 2
        for sa in (-h, h):
            for sb in (-h, h):
                c = list(q["position"])
                c[a] += sa
                c[b] += sb
                out.append(c)
    return out


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def test_the_pick_opens_on_the_same_view_whatever_the_view_before(plate):
    page = plate
    starts = [
        "async () => (await import('/static/js/viewport.js')).setView('top')",
        "async () => (await import('/static/js/viewport.js')).setView('front')",
        # zoomed into one corner and turned round behind the part
        """() => { window.__vp.camera.position.set(-40, 90, -25);
                   window.__vp.getControls().target.set(25, 15, 5); }""",
    ]
    poses = []
    for start in starts:
        page.evaluate(start)
        page.wait_for_timeout(300)
        poses.append(_open_pick(page))
        _close_pick(page)
    for p in poses[1:]:
        assert p["pos"] == pytest.approx(poses[0]["pos"], abs=1e-6), poses
        assert p["target"] == pytest.approx(poses[0]["target"], abs=1e-6), poses
    look = _unit([a - b for a, b in zip(poses[0]["pos"], poses[0]["target"])])
    assert look == pytest.approx(_unit(ISO), abs=1e-6), "the home (iso) direction"
    assert page.errors == []


def test_the_pick_view_is_zoomed_to_fit_every_plane_square_and_the_part(plate):
    page = plate
    pose = _open_pick(page)
    rect = page.evaluate("document.querySelector('#viewer canvas').getBoundingClientRect().toJSON()")
    fit = page.evaluate("window.__vp.getFit()")
    # the plate's corners: a 60 x 40 x 20 box around the fit centre
    c = fit["c"]
    body = [[c[0] + sx * 30, c[1] + sy * 20, c[2] + sz * 10]
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    corners = _square_corners(page)
    assert len(corners) == 12
    ndc = []
    for w in corners + body:
        s = page.evaluate("(w) => window.__vp.worldToScreen(w)", w)
        assert s, f"{w} is behind the camera"
        ndc.append(max(abs(s["cx"] / rect["width"] * 2 - 1), abs(s["cy"] / rect["height"] * 2 - 1)))
    assert max(ndc) <= 0.9, f"a square runs off the screen: {max(ndc):.3f}"
    assert max(ndc) >= 0.8, f"zoomed out too far - the squares fill only {max(ndc):.3f}"
    # aimed at the middle of the squares
    mid = [(min(p[i] for p in corners) + max(p[i] for p in corners)) / 2 for i in range(3)]
    assert pose["target"] == pytest.approx(mid, abs=1e-6)
    _close_pick(page)
    assert page.errors == []


def test_an_empty_design_after_a_far_part_picks_at_the_origin(page, fresh_doc):
    page.evaluate(BUILD, [300, 200, 50])
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    far = page.evaluate("window.__vp.getFit()")
    assert far["c"][0] > 250, far
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/new', { name: 'empty-after-far' });
    }""")
    page.wait_for_function(
        "() => { const f = window.__vp.getFit(); return f.r === 100 && f.c.every(v => v === 0); }",
        timeout=15000)
    pose = _open_pick(page)
    squares = page.evaluate("window.__vp.originPlaneInfo()")
    assert {q["plane"] for q in squares} == {"XY", "XZ", "YZ"}
    for q in squares:
        assert q["position"] == pytest.approx([0, 0, 0], abs=1e-9), \
            f"{q['plane']} square drawn where the last design's part was: {q}"
        assert q["size"] == pytest.approx(230), q
    assert pose["target"] == pytest.approx([0, 0, 0], abs=1e-6)
    _close_pick(page)
    assert page.errors == []


# how deep the squares' furthest corner sits along the view, against the far plane
DEPTHS = """() => {
  const vp = window.__vp, cam = vp.camera, t = vp.getControls().target;
  const V3 = cam.position.constructor;
  const view = new V3().subVectors(t, cam.position).normalize();
  const SPAN = { XY: [0, 1], XZ: [0, 2], YZ: [1, 2] };
  let deepest = 0;
  for (const q of vp.originPlaneInfo()) {
    const [a, b] = SPAN[q.plane], h = q.size / 2;
    for (const sa of [-h, h]) for (const sb of [-h, h]) {
      const c = [...q.position]; c[a] += sa; c[b] += sb;
      deepest = Math.max(deepest, new V3(...c).sub(cam.position).dot(view));
    }
  }
  return { deepest, dist: cam.position.distanceTo(t), far: cam.far };
}"""


def test_the_far_plane_reaches_the_squares_furthest_back(plate):
    """Review of 1294f7a (F4): the pick pushed the far clip plane out only when
    the camera's DISTANCE passed the zoom limit (0.85 of the far plane), but the
    squares' far corners stand up to 0.4 of that distance further back. A fit
    leaves far = 100 x the fit radius, so a sketch whose fit radius is near 2 mm
    (a 3 mm circle) opened the pick with those corners cut off. The pick view is
    the same for every part that small, so the far plane is set here to a value
    inside that gap, the way such a fit leaves it."""
    page = plate
    _open_pick(page)
    m = page.evaluate(DEPTHS)
    _close_pick(page)
    assert m["deepest"] > m["dist"] / 0.85 * 1.02, f"no gap to test in: {m}"
    far = (m["dist"] / 0.85 + m["deepest"]) / 2
    page.evaluate("""(far) => { const vp = window.__vp;
      vp.camera.far = far; vp.camera.updateProjectionMatrix();
      vp.getControls().maxDistance = far * 0.85; }""", far)
    _open_pick(page)
    m2 = page.evaluate(DEPTHS)
    assert m2["deepest"] == pytest.approx(m["deepest"], rel=1e-6), "the same fixed view"
    assert m2["far"] > m2["deepest"], f"the squares' far corners are clipped: {m2}"
    _close_pick(page)
    assert page.errors == []


def test_measure_opened_while_the_pick_waits_takes_the_next_click(plate):
    """Review of 1294f7a (F1): Measure opened while Create Sketch's pick waited.
    The pick stayed armed under Measure's lock and took the first click: a click
    on the top face went to the pick, which refused to open a sketch under
    Measure, and Measure never saw it."""
    page = plate
    _open_pick(page)
    page.evaluate("async () => (await import('/static/js/measure.js')).openMeasure()")
    page.wait_for_selector("#measureDialog", state="visible", timeout=15000)
    assert page.evaluate(PICK_OVER), "Measure replaced the pick"
    top = page.evaluate("(w) => window.__vp.worldToScreen(w)", [5, 3, 10])
    page.mouse.click(top["x"], top["y"])
    page.wait_for_function("() => !document.getElementById('meSelA').classList.contains('empty')",
                           timeout=15000)
    assert page.evaluate("document.getElementById('meSelA').textContent").startswith("Face")
    page.evaluate("async () => (await import('/static/js/measure.js')).cancelMeasure()")
    assert page.errors == []
