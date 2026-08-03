"""E2E: the origin planes tell the truth (S2 of SKETCH-MODE-PLAN.md).

Reported as "the coordinate planes are not aligned with the design". The quads
were centred on the model's bounding-sphere centre, so for a part sitting at
z=60 the "XY" quad floated at z=60 — while clicking it starts a sketch on the
TRUE XY plane at z=0. The quad was wrong by exactly the model's offset.

Locked in: each quad lies IN the plane it names (its normal component is 0)
while still sitting under the part in-plane, and entering a sketch frames the
camera on the PART rather than staring at the world origin.
"""
import pytest

pytest.importorskip("playwright.sync_api")

# a box far from the origin AND lifted in z — worst case for the old code
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 40, depth: 30, thickness: 20 },
      inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'shift', op: 'move', params: { x: 160, y: 90, z: 60 },
      inputs: ['b'] }, 'add');
  await loadMesh(true);
}
"""

NORMAL_AXIS = {"XY": 2, "XZ": 1, "YZ": 0}


@pytest.fixture()
def offset_box(page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    return page


def test_each_quad_lies_in_the_plane_it_names(offset_box):
    page = offset_box
    fit = page.evaluate("window.__vp.getFit()")
    assert abs(fit["c"][2]) > 10, f"model must be off-plane for this test: {fit}"

    page.evaluate("""async () => {
      const vp = await import('/static/js/viewport.js');
      vp.beginPlanePick(() => {});
    }""")
    page.wait_for_timeout(400)
    quads = {q["plane"]: q["position"]
             for q in page.evaluate("window.__vp.originPlaneInfo()")}
    assert set(quads) == {"XY", "XZ", "YZ"}, quads
    for plane, pos in quads.items():
        axis = NORMAL_AXIS[plane]
        assert abs(pos[axis]) < 1e-9, (
            f"{plane} quad is {pos[axis]}mm off its own plane: {pos}")
    # ...and still centred under the part in the two IN-plane axes
    assert quads["XY"][0] == pytest.approx(fit["c"][0], abs=1e-6)
    assert quads["XY"][1] == pytest.approx(fit["c"][1], abs=1e-6)
    page.evaluate("""async () => {
      (await import('/static/js/viewport.js')).cancelPlanePick();
    }""")
    assert page.errors == []


def test_sketch_lands_on_the_plane_and_frames_the_part(offset_box):
    """The grid must coincide with z=0 for an XY sketch (that IS where the
    geometry will go), and the camera must look at the part — it used to focus
    on (0,0) and leave a distant part off-screen."""
    page = offset_box
    fit = page.evaluate("window.__vp.getFit()")
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XY');
    }""")
    page.wait_for_timeout(1600)                 # camera tween settles
    target = page.evaluate("window.__vp.getControls().target.toArray()")
    assert abs(target[2]) < 1e-6, f"XY sketch grid must sit at z=0: {target}"
    assert target[0] == pytest.approx(fit["c"][0], abs=5)
    assert target[1] == pytest.approx(fit["c"][1], abs=5)
    page.evaluate("""async () => {
      (await import('/static/js/sketcher.js')).cancelSketch();
    }""")
    assert page.errors == []
