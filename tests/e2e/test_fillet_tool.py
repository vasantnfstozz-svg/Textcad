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
# the box with a 20 x 12 pocket cut 5 deep into its top: the pocket floor's rim
# and its four upright corners are INSIDE corners (the two faces meeting at each
# sit in front of the line from every viewing angle)
BUILD_POCKET = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 40, depth: 30, thickness: 20 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 't', op: 'plate', params: { width: 20, depth: 12, thickness: 10 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'tm', op: 'move', params: { x: 0, y: 0, z: 10 }, inputs: ['t'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'c', op: 'cut', params: {}, inputs: ['b', 'tm'] }, 'add');
}
"""
# indices of a body's edges in the viewport payload, by a predicate on their points
EDGE_INDICES = """
([body, kind]) => {
  const b = window.__vp.bodyObjsRaw().find(x => x.id === body);
  const zs = b.data.edges.flatMap(e => e.points.map(p => p[2]));
  const zmax = Math.max(...zs);
  return b.data.edges.filter(e => {
    if (kind === 'inside') return e.type === 'LINE' &&                    // within the pocket footprint
      e.points.every(p => Math.abs(p[0]) < 15 && Math.abs(p[1]) < 12) &&
      !e.points.every(p => Math.abs(p[2] - zmax) < 1e-3);                // but not its opening rim on top
    if (kind === 'top') return e.type === 'LINE' && e.points.every(p => Math.abs(p[2] - zmax) < 1e-3);
    if (kind === 'topline') return e.type === 'LINE' && e.points.every(p => Math.abs(p[2] - zmax) < 1e-3);
    if (kind === 'topcircle') return e.type === 'CIRCLE' && e.points.every(p => Math.abs(p[2] - zmax) < 1e-3);
    if (kind === 'vertical') return e.type === 'LINE' && Math.abs(e.points[0][2] - e.points.at(-1)[2]) > 1;
    return false;
  }).map(e => e.id);
}
"""
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"
PICKED_EDGE = """async () => {
  const { S } = await import('/static/js/state.js');
  return S.pickedEdge ? S.pickedEdge.id : null;
}"""
PICKED_FACE = "async () => (await import('/static/js/state.js')).S.pickedFace"

# hold every plan request for `ms` in the BROWSER, so the driver stays free to
# click while one is in flight — the only way to queue a second request on purpose
DELAY_PLANS = """
(ms) => {
  const orig = window.fetch;
  window.fetch = (u, o) => (String(u).includes('/api/tool/plan')
    ? new Promise(r => setTimeout(() => r(orig(u, o)), ms))
    : orig(u, o));
}
"""


def wait_modal_free(page, timeout=3):
    """the one-command lock is released when the session's last change lands"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page.evaluate(MODAL) is None:
            return
        page.wait_for_timeout(100)
    raise AssertionError("the tool never released the one-command lock")


def chip(page, side, d):
    return page.locator(f"#flGroups .egchip[data-side='{side}'][data-dir='{d}']")


def wait_glow(page, n, timeout=4):
    """poll until `n` edges are gold — a chip's plan queues behind the previous
    one, so a fixed sleep races the round trip"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if glow(page) == n:
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"gold stayed at {glow(page)}, expected {n}")


def chip_state(page, side, d):
    cls = chip(page, side, d).get_attribute("class") or ""
    return "on" if " on" in f" {cls}" else "part" if "part" in cls else "off"


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
    """click where the USER would: on the drawn line's middle point — then wait
    for the plan's answer (the gold count changing), up to 3 s. A fixed 700 ms
    was a race: clicks now queue instead of dropping the one in flight, so a
    late answer landed on the NEXT assertion (4 gold after 3 clicks)."""
    s = page.evaluate("([b, i]) => window.__vp.edgeScreen(b, i)", [body, idx])
    assert s, f"edge {idx} of {body} is off screen"
    before = glow(page)
    page.mouse.click(s["x"], s["y"])
    t0 = time.time()
    while time.time() - t0 < 3:                # a refused / hidden edge takes the whole wait
        page.wait_for_timeout(100)
        if glow(page) != before:
            page.wait_for_timeout(200)         # the handles settle
            return


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


def test_an_inside_corner_can_be_picked_and_rounded(page, fresh_doc, server):
    """The user's grid of triangular pockets (2026-09-07): every inside corner
    refused the click, because the picker rejected an edge whenever a face was
    a hair nearer — and the two walls meeting at an inside corner always are.
    A pocket floor's rim and its upright corners pick like outside edges, and
    the round ADDS material there (the kernel's number, not ours)."""
    setup(page, BUILD_POCKET)
    open_tool(page, "fillet")
    inside = page.evaluate(EDGE_INDICES, ["c", "inside"])
    assert len(inside) == 8, inside                  # 4 floor edges + 4 upright corners
    click_visible_edges(page, "c", inside, 2)
    assert glow(page) == 2, "sharp pocket corners: no chain, two picks are two edges"
    v0 = feature(server, "c")["volume"]
    assert v0 == pytest.approx(24000 - 20 * 12 * 5)
    page.fill("#flValue", "2")
    page.wait_for_timeout(1500)
    f = wait_feature(server, "fillet1")
    assert f["status"] == "ok", f
    assert f["volume"] > v0 + 1, "an inside round adds material"
    assert page.errors == []


def test_group_chips_pick_whole_sets_in_one_click(page, fresh_doc, server):
    """The user's ask (2026-09-07): "select all the vertical or horizontal edges
    by clicking one option". A chip adds a whole group and shows its state (lit /
    part / dim, all from the plan); clicking it again takes the group out; the
    chat says how many; the round on the inside group ADDS material (the
    kernel's number, not ours)."""
    setup(page, BUILD_POCKET)
    v0 = feature(server, "c")["volume"]
    open_tool(page, "fillet")
    page.wait_for_function(
        "() => !document.querySelector(\"#flGroups .egchip[data-side='inside'][data-dir='vertical']\").disabled",
        timeout=15000)
    assert chip(page, "outside", "vertical").is_enabled()
    chip(page, "inside", "vertical").click()
    wait_glow(page, 4)
    assert chip_state(page, "inside", "vertical") == "on"
    assert chip_state(page, "inside", "all") == "part"
    assert "added 4 edges" in page.text_content("#chatLog")
    chip(page, "inside", "horizontal").click()
    wait_glow(page, 8)
    assert chip_state(page, "inside", "all") == "on"
    # the whole group out again
    chip(page, "inside", "vertical").click()
    wait_glow(page, 4)
    assert chip_state(page, "inside", "vertical") == "off"
    assert "released 4 edges" in page.text_content("#chatLog")
    page.fill("#flValue", "1.5")
    page.wait_for_timeout(2500)
    f = wait_feature(server, "fillet1")
    assert f["status"] == "ok", f
    assert f["volume"] > v0 + 1, "4 inside floor rounds add material"
    assert len(f["params"]["edges"]) == 4
    assert page.errors == []


def test_select_mode_picks_an_inside_corner_and_fillet_takes_it(page, fresh_doc, server):
    """The user's report ON the fix (2026-09-07): in SELECT mode a click on an
    inside upright edge still selected the WALL — pickAt had its own copy of the
    old depth-only rule. Both pickers now share visibleEdgeHit. And
    select-then-command: the picked edge enters Fillet as its first click
    (fusion-parity rule 2), so the tool opens with one edge gold."""
    setup(page, BUILD_POCKET)
    inside = page.evaluate(EDGE_INDICES, ["c", "inside"])
    picked = None
    for i in inside:
        s = page.evaluate("([b, i]) => window.__vp.edgeScreen(b, i)", ["c", i])
        if not s:
            continue
        page.mouse.click(s["x"], s["y"])
        page.wait_for_timeout(300)
        if page.evaluate(PICKED_EDGE) == i:
            picked = i
            break
    assert picked is not None, "no inside edge could be selected in Select mode"
    assert page.evaluate(PICKED_FACE) is None, "the wall must not win over its own edge"
    open_tool(page, "fillet")
    page.wait_for_timeout(1200)
    assert glow(page) == 1, "the selected edge is the tool's first click"
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


def test_a_queued_chip_click_belongs_to_the_session_it_was_made_in(page, fresh_doc, server):
    """A plan request that WAITS its turn still belongs to the session it was
    made in. Two chips clicked in a row queue the second one; Cancel (or OK)
    does not drain that queue — `settled()` waits for rebuilds, not for plans —
    so the queued click used to run against whatever session was open by the
    time it got its turn, and its group landed there: gold edges nobody picked
    in a fresh session, and, when the new session is an EDIT, the stored edges
    of that feature rewritten with a group the user never chose for it.
    """
    setup(page, BUILD_POCKET)
    open_tool(page, "fillet")
    page.wait_for_function(
        "() => { const c = document.querySelector(\"#flGroups .egchip"
        "[data-side='inside'][data-dir='vertical']\"); return c && !c.disabled; }",
        timeout=15000)
    page.evaluate(DELAY_PLANS, 3000)        # the round trip is slow: the queue is real
    chip(page, "inside", "vertical").click()      # in flight
    chip(page, "inside", "horizontal").click()    # queued behind it
    page.click("#flCancel")
    page.wait_for_selector("#flDialog", state="hidden")
    wait_modal_free(page)
    open_tool(page, "fillet")               # a NEW session: nothing is picked in it
    page.wait_for_timeout(9000)             # both delayed plans land
    assert glow(page) == 0, "a queued chip click landed on the session opened after it"
    assert chip_state(page, "inside", "horizontal") == "off"
    assert page.errors == []


# aim the camera exactly (direction from the target, distance) so a picking rule
# can be measured at a chosen zoom instead of at whatever the fit left behind
AIM = """
([dir, dist]) => {
  const c = window.__vp.camera, ctl = window.__vp.getControls();
  const L = Math.hypot(...dir);
  ctl.target.set(0, 0, 0);
  c.position.set(dir[0] / L * dist, dir[1] / L * dist, dir[2] / L * dist);
  c.lookAt(ctl.target); ctl.update(); c.updateMatrixWorld(true);
}
"""
EDGE_MIDS = """
(body) => {
  const b = window.__vp.bodyObjsRaw().find(x => x.id === body);
  return b.data.edges.map(e => {
    const P = e.points, n = P.length;
    return { id: e.id,
             mid: n % 2 === 0 ? [0, 1, 2].map(k => (P[n / 2 - 1][k] + P[n / 2][k]) / 2)
                              : P[Math.floor(n / 2)],
             zs: P.map(p => p[2]) };
  });
}
"""


def test_a_face_hit_far_from_the_line_is_not_beside_it(page, fresh_doc, server):
    """An edge whose own face is nearer than it can still be picked — an inside
    corner's line sits a hair behind its two faces, and without that escape no
    concave edge could be filleted (4f15f66). The escape has to be BOUNDED or
    an edge is pickable through the material in front of it.

    The bound was 4x the click reach, and the reach is a world length that
    grows with zoom: at a 400 mm view that is 11.5 mm, so a face hit 9.9 mm
    along the face from the line counted as "right beside" it and the edge
    behind it was picked (probes/own_face_reach_probe.py, 853 samples: a
    legitimate click's face hit lands within 1.1x the reach, p90). Measured
    here on the real body, through the rule itself: nothing 6 mm from the line
    is beside it at any of these zooms.

    (The review of 2026-09-07 proposed comparing in PIXELS instead. The probe
    measured that too: every own-face hit is inside the 5 px pick threshold by
    construction — max 4.02 px over all 853 samples — so a pixel bound accepts
    every one of them and guards nothing at all.)"""
    setup(page, BUILD_POCKET)
    edges = page.evaluate(EDGE_MIDS, "c")
    inside = [e for e in edges
              if abs(e["mid"][0]) < 11 and abs(e["mid"][1]) < 7 and min(e["zs"]) > 4.9]
    assert len(inside) == 12, inside     # 4 uprights, 4 floor rims, 4 opening rims
    far, near = [], []
    for direction in ([1, 1, 0.9], [-1, -1, 0.9], [1, 0.12, 0.06]):
        for dist in (60, 160, 400):
            page.evaluate(AIM, [direction, dist])
            page.wait_for_timeout(60)
            for e in inside:
                s = page.evaluate("(p) => window.__vp.worldToScreen(p)", e["mid"])
                if not s:
                    continue
                for dx, dy in ((0, 0), (3, 0), (-3, 0), (0, 3), (0, -3), (4, 1)):
                    rep = page.evaluate("([x, y]) => window.__vp.edgeHitReport(x, y)",
                                        [s["cx"] + dx, s["cy"] + dy])
                    for h in rep["hits"]:
                        if not h["own"] or h["behind"] is None or h["behind"] <= 1e-3:
                            continue        # already in front: the escape is not consulted
                        # 6 mm on a 40 x 30 x 20 body is 15% of its width:
                        # unambiguously NOT "right beside the line"
                        (far if h["world"] > 6 else near).append((dist, dx, dy, h))
    assert near, "no click reached the escape at all — the sweep proves nothing"
    assert far, "no far-from-the-line sample was produced — the sweep proves nothing"
    bad = [f for f in far if f[3]["beside"]]
    assert not bad, ("a face hit millimetres from the line counted as beside it: "
                     + str(bad[:3]))
    # ...and the escape still does its job: a click ON an inside corner is beside it
    assert any(h["beside"] for _, _, _, h in near), "no inside corner survived the bound"
    assert page.errors == []
