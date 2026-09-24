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
