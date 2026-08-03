"""E2E: sketching snaps to the existing body (S5 of SKETCH-MODE-PLAN.md).

Reported: "when I want to start a sketch at those boxes edges, we need
something for selecting to those edges, like how we do for the origin."

A plate spans z -10..+10, so its four vertical edges pierce the XY plane at
(±30, ±20). Sketching on XY must (a) show those points, (b) lock a sloppy click
onto the exact coordinate, and (c) report the SNAPPED position, not the raw
cursor.
"""
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await loadMesh(true);
}
"""

# hover then click a plane-local point, exactly what a mouse does
ACT = """
async (args) => {
  const [x, y, tol, click] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-move', { x, y, tol, down: false });
  await new Promise(r => setTimeout(r, 100));
  if (click) { bus.emit('sk3d-down', { x, y, tol }); bus.emit('sk3d-up', {}); }
  await new Promise(r => setTimeout(r, 120));
  const snap = document.getElementById('sk3dSnap');
  return { label: snap ? snap.textContent : '',
           coords: document.getElementById('sk3dCoords').textContent };
}
"""


@pytest.fixture()
def sketch_on_xy(page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XY');
    }""")
    page.wait_for_timeout(1800)                  # camera tween + snap fetch
    return page


def test_model_geometry_becomes_snap_targets(sketch_on_xy):
    page = sketch_on_xy
    targets = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchSnapTargets();
    }""")
    pts = {(round(p["x"], 1), round(p["y"], 1)) for p in targets["model"]}
    assert {(30.0, 20.0), (30.0, -20.0), (-30.0, 20.0), (-30.0, -20.0)} <= pts, pts
    assert page.errors == []


def test_sloppy_click_lands_on_the_exact_corner(sketch_on_xy):
    """~2mm off the corner must produce EXACTLY 30x20 from corner to origin —
    that is the whole point of snapping."""
    page = sketch_on_xy
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('rectangle');
    }""")
    page.wait_for_timeout(200)
    hover = page.evaluate(ACT, [28.4, 18.6, 3.0, True])   # near (30, 20)
    assert "model" in hover["label"].lower(), hover
    # the readout must show the SNAPPED point, not the raw cursor (28, 19)
    assert "30" in hover["coords"] and "20" in hover["coords"], hover["coords"]
    page.evaluate(ACT, [0.4, 0.3, 3.0, True])             # near the origin
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1, ents
    e = ents[0]
    assert e["w"] == pytest.approx(30, abs=1e-6), e
    assert e["h"] == pytest.approx(20, abs=1e-6), e
    assert (e["x"], e["y"]) == (pytest.approx(15, abs=1e-6),
                                pytest.approx(10, abs=1e-6)), e
    assert page.errors == []


def test_snap_targets_are_cleared_between_sketches(sketch_on_xy):
    """Stale targets from a previous plane would snap clicks to points that are
    not on THIS plane."""
    page = sketch_on_xy
    assert page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchSnapTargets().model.length;
    }""") > 0
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.cancelSketch();
      sk.openSketchEditor('YZ');            // a plane the plate does not cross
    }""")
    page.wait_for_timeout(1600)
    pts = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchSnapTargets().model;
    }""")
    # the plate spans x -30..30, so YZ (x=0) cuts it: whatever comes back must
    # be from THIS plane, never the XY corners at (±30, ±20)
    bad = [p for p in pts if abs(abs(p["x"]) - 30) < 0.1
           and abs(abs(p["y"]) - 20) < 0.1]
    assert not bad, bad
    assert page.errors == []
