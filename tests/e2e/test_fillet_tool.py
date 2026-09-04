"""E2E: Fillet / Chamfer on picked edges (LAUNCH-PLAN.md P4,
specs/fillet-chamfer.md). Real clicks on real edges, and every geometric claim
checked against the kernel: the volume a round or a bevel removes, the edges a
fillet finds again after its box grows.
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

# a 40 x 30 x 20 box centred on the origin (blocks.plate): top edges at z = +10
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 40, depth: 30, thickness: 20 }, inputs: [] }, 'add');
}
"""
# the same box with its four upright corners rounded: the top rim is a chain of 8
BUILD_ROUNDED = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 40, depth: 30, thickness: 20 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'g1', op: 'fillet', params: { radius: 5, edges: 'vertical' }, inputs: ['b'] }, 'add');
}
"""
# indices of a body's edges in the viewport payload, by a predicate on their points
EDGE_INDICES = """
([body, kind]) => {
  const b = window.__vp.bodyObjsRaw().find(x => x.id === body);
  const zs = b.data.edges.flatMap(e => e.points.map(p => p[2]));
  const zmax = Math.max(...zs);
  return b.data.edges.filter(e => {
    if (kind === 'top') return e.type === 'LINE' && e.points.every(p => Math.abs(p[2] - zmax) < 1e-3);
    if (kind === 'topline') return e.type === 'LINE' && e.points.every(p => Math.abs(p[2] - zmax) < 1e-3);
    if (kind === 'topcircle') return e.type === 'CIRCLE' && e.points.every(p => Math.abs(p[2] - zmax) < 1e-3);
    if (kind === 'vertical') return e.type === 'LINE' && Math.abs(e.points[0][2] - e.points.at(-1)[2]) > 1;
    return false;
  }).map(e => e.id);
}
"""
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"


def feature(server, fid):
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    return next((f for f in doc["features"] if f["id"] == fid), None)


def wait_feature(server, fid, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        if f and f["status"] in ("ok", "failed"):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid} never finished building")


def setup(page, build):
    page.evaluate(build)
    page.wait_for_timeout(1500)


def open_tool(page, name):
    page.locator("button.tab", has_text="Modify").click()
    page.locator(f"#ribbon .rbtn[title='{name}']").click()
    page.wait_for_selector(f"#{'fl' if name == 'fillet' else 'ch'}Dialog", state="visible", timeout=15000)


def glow(page):
    return page.evaluate("() => window.__vp.gizmos()")["glow"]


def click_edge(page, body, idx):
    """click where the USER would: on the drawn line's middle point"""
    s = page.evaluate("([b, i]) => window.__vp.edgeScreen(b, i)", [body, idx])
    assert s, f"edge {idx} of {body} is off screen"
    page.mouse.click(s["x"], s["y"])
    page.wait_for_timeout(700)                 # the plan round trip


def click_visible_edges(page, body, indices, want):
    """click edges until `want` of them glow — a hidden one is refused by the
    viewport (a face sits in front of it), like a real click would be"""
    picked = []
    for i in indices:
        before = glow(page)
        click_edge(page, body, i)
        if glow(page) > before:
            picked.append(i)
        if len(picked) == want:
            return picked
    raise AssertionError(f"only {len(picked)} of {want} edges could be clicked")


def drag_arrow(page, px):
    ax = page.evaluate(
        "async () => (await import('/static/js/viewport.js')).extrudeArrowAxisScreen()")
    assert ax, "no arrow to drag"
    bx, by, tx, ty = ax["base"]["x"], ax["base"]["y"], ax["tip"]["x"], ax["tip"]["y"]
    L = ((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5
    ux, uy = (tx - bx) / L, (ty - by) / L
    mx, my = (bx + tx) / 2, (by + ty) / 2
    page.mouse.move(mx, my)
    page.mouse.down()
    for k in range(1, 7):
        page.mouse.move(mx + ux * px * k / 6, my + uy * px * k / 6)
        page.wait_for_timeout(30)
    page.mouse.up()


def edge_len(page, body, idx):
    return page.evaluate("([b, i]) => window.__vp.bodyObjsRaw().find(x => x.id === b).data.edges[i].length",
                         [body, idx])


def round_removed(length, r):
    """volume a fillet of radius r takes off ONE straight 90-degree edge"""
    return length * r * r * (1 - 3.141592653589793 / 4)


# ------------------------------------------------------------------ journeys --

def test_pick_a_top_edge_drag_and_type(page, fresh_doc, server):
    """Honest zero, the hint, one edge gold, the arrow into the material, one
    verified solid on release; a typed 5 removes exactly the kernel's volume."""
    setup(page, BUILD)
    open_tool(page, "fillet")
    assert page.input_value("#flValue") == "0"
    assert page.is_visible("#placeHint") and "edges" in page.text_content("#placeHint")
    assert glow(page) == 0 and feature(server, "fillet1") is None
    tops = page.evaluate(EDGE_INDICES, ["b", "top"])
    assert len(tops) == 4
    picked = click_visible_edges(page, "b", tops, 1)
    L = edge_len(page, "b", picked[0])
    g = page.evaluate("() => window.__vp.gizmos()")
    assert g["glow"] == 1 and g["arrow"], g
    assert feature(server, "fillet1") is None, "picking builds nothing"
    assert "1 edge of b" in page.eval_on_selector("#flProfile", "el => el.value")

    drag_arrow(page, 20)
    page.wait_for_timeout(1500)
    f = wait_feature(server, "fillet1")
    r = float(page.input_value("#flValue"))
    assert r > 0.5 and f["status"] == "ok", (r, f)
    assert r == pytest.approx(f["params"]["radius"]), "the box shows what was built"
    assert f["volume"] == pytest.approx(24000 - round_removed(L, r), rel=2e-3)

    page.fill("#flValue", "5")
    page.wait_for_timeout(1500)
    f = wait_feature(server, "fillet1")
    assert f["volume"] == pytest.approx(24000 - round_removed(L, 5), rel=1e-4)
    assert len(f["params"]["edges"]) == 1 and len(f["params"]["edges"][0]["faces"]) == 2
    assert page.errors == []


def test_tangent_chain_selects_the_rim_and_a_second_click_releases_it(page, fresh_doc, server):
    setup(page, BUILD_ROUNDED)
    open_tool(page, "fillet")
    lines = page.evaluate(EDGE_INDICES, ["g1", "topline"])
    assert len(lines) == 4
    click_visible_edges(page, "g1", lines, 1)
    assert glow(page) == 8, "one click on a smooth rim selects all 8 edges"
    page.uncheck("#flChain")
    page.wait_for_timeout(700)
    assert glow(page) == 1
    page.check("#flChain")
    page.wait_for_timeout(700)
    assert glow(page) == 8
    # clicking a CIRCLE of the selected chain takes the chain out again
    circles = page.evaluate(EDGE_INDICES, ["g1", "topcircle"])
    for i in circles:
        click_edge(page, "g1", i)
        if glow(page) == 0:
            break
    assert glow(page) == 0 and page.is_visible("#flDialog"), "the panel stays open"
    page.fill("#flValue", "2")
    page.wait_for_timeout(800)
    assert feature(server, "fillet1") is None, "no edges: nothing is built"
    page.click("#flOk")
    page.wait_for_selector("#flDialog", state="hidden")
    assert "Nothing rounded" in page.text_content("#chatLog")
    assert page.errors == []


def test_add_and_remove_edges_ok_then_edit_and_cancel(page, fresh_doc, server):
    setup(page, BUILD)
    open_tool(page, "fillet")
    tops = page.evaluate(EDGE_INDICES, ["b", "top"])
    picked = click_visible_edges(page, "b", tops, 3)
    assert glow(page) == 3
    click_edge(page, "b", picked[-1])          # again: released
    assert glow(page) == 2
    # lengths BEFORE the build: once fillet1 exists the viewport shows ITS body
    gone = sum(round_removed(edge_len(page, "b", i), 3) for i in picked[:2])
    page.fill("#flValue", "3")
    f = wait_feature(server, "fillet1")
    assert f["status"] == "ok" and len(f["params"]["edges"]) == 2
    assert f["volume"] == pytest.approx(24000 - gone, rel=1e-3)
    page.click("#flOk")
    page.wait_for_selector("#flDialog", state="hidden")
    assert "Fillet created" in page.text_content("#chatLog")
    stored = feature(server, "fillet1")["params"]
    assert page.evaluate(MODAL) is None

    # edit: the tree row's pencil reopens the tool with the edges gold
    r = page.locator("#tree .nrow", has=page.locator(".nname", has_text="fillet1"))
    r.hover()
    r.locator("button[title^='edit this fillet']").click()
    page.wait_for_selector("#flDialog", state="visible")
    page.wait_for_timeout(900)
    assert "Edit fillet1" in page.text_content("#flDialog .exhead")
    assert page.input_value("#flValue") == "3" and glow(page) == 2
    page.fill("#flValue", "1")
    page.wait_for_timeout(1500)
    assert feature(server, "fillet1")["params"]["radius"] == 1
    page.click("#flCancel")
    page.wait_for_selector("#flDialog", state="hidden")
    page.wait_for_timeout(1200)
    assert feature(server, "fillet1")["params"] == stored, "Cancel restores verbatim"
    assert page.errors == []


def test_too_large_radius_says_why_and_keeps_the_last_one_that_built(page, fresh_doc, server):
    """checklist step 5: 50 does not fit on a 20 mm tall box — the chat says so
    in the op's own words, and the body keeps the radius that did build. The
    tool never searches for what WOULD fit: that means filleting at values
    nobody typed, and one of those segfaulted OCCT on a real design."""
    setup(page, BUILD)
    open_tool(page, "fillet")
    tops = page.evaluate(EDGE_INDICES, ["b", "top"])
    picked = click_visible_edges(page, "b", tops, 1)
    L = edge_len(page, "b", picked[0])
    page.fill("#flValue", "5")
    f = wait_feature(server, "fillet1")
    assert f["status"] == "ok"
    page.fill("#flValue", "50")
    page.wait_for_timeout(4000)                 # the refused build + the bisection + the settle
    f = wait_feature(server, "fillet1")
    log = page.text_content("#chatLog")
    assert "radius 50 mm does not fit" in log, log
    assert "the kernel could not build it there" in log, log
    assert "Reverted to radius 5" in log, log
    assert f["status"] == "ok" and f["params"]["radius"] == 5
    assert f["volume"] == pytest.approx(24000 - round_removed(L, 5), rel=1e-4)
    assert page.input_value("#flValue") == "5"
    assert page.errors == []


def test_chamfer_rides_along_when_the_box_grows(page, fresh_doc, server):
    """checklist step 4: bevel upright edges, then make the box taller — the
    stored edges are geometry, so the chamfer finds them on the taller box"""
    setup(page, BUILD)
    open_tool(page, "chamfer")
    verts = page.evaluate(EDGE_INDICES, ["b", "vertical"])
    assert len(verts) == 4
    click_visible_edges(page, "b", verts, 2)
    page.fill("#chValue", "2")
    f = wait_feature(server, "chamfer1")
    assert f["status"] == "ok"
    assert f["volume"] == pytest.approx(24000 - 2 * (2 * 2 / 2) * 20, rel=1e-4)
    page.click("#chOk")
    page.wait_for_selector("#chDialog", state="hidden")
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/feature/params', { feature_id: 'b', params: { thickness: 30 } });
    }""")
    f = wait_feature(server, "chamfer1")
    assert f["status"] == "ok", f["problems"]
    assert f["volume"] == pytest.approx(36000 - 2 * (2 * 2 / 2) * 30, rel=1e-4)
    assert page.errors == []


def test_esc_cancels_the_open_tool(page, fresh_doc, server):
    setup(page, BUILD)
    open_tool(page, "fillet")
    tops = page.evaluate(EDGE_INDICES, ["b", "top"])
    click_visible_edges(page, "b", tops, 1)
    assert page.evaluate(MODAL) == "Fillet"
    page.keyboard.press("Escape")
    page.wait_for_selector("#flDialog", state="hidden")
    page.wait_for_timeout(500)
    assert page.evaluate(MODAL) is None and glow(page) == 0
    assert not page.evaluate("() => window.__vp.gizmos()")["edgePick"]
    assert feature(server, "fillet1") is None
    assert page.errors == []
