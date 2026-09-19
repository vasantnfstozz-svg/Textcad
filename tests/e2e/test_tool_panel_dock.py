"""E2E: an open tool panel covers nothing (LAUNCH-PLAN.md §10, P2).

#extrudeDialog, #measureDialog and the rest were `position: fixed; right: 24px`
— pinned to the WINDOW's right edge, which is where the AI designer column
lives. A failed feature explains itself in that column (rule 7), so the one
place a user must be able to read was the one place the open panel sat on top
of: the click appeared to do nothing and the reason was underneath the panel.

They are a column of `main` now, between the viewport and the chat, so they
take their own space instead of floating over someone else's. This test
measures the boxes at a wide window and a narrow one: the panel may not
overlap the chat, the feature tree, the status bar OR the 3D canvas — the
model's own drag handles are as hideable as the chat is (floating the panel
over the viewport instead put the panel on top of the arrow you are meant to
drag, on a 1200 px window).
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
TO_SCREEN = """
(w) => {
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  const r = cv.getBoundingClientRect();
  const V3 = vp.camera.position.constructor;
  const v = new V3(w[0], w[1], w[2]).project(vp.camera);
  return { x: r.left + (v.x + 1) / 2 * r.width,
           y: r.top + (1 - (v.y + 1) / 2) * r.height };
}
"""
TOP_PICKED = """
async () => {
  const { S } = await import('/static/js/state.js');
  return !!(S.pickedFace && S.pickedFace.normal && S.pickedFace.normal[2] > 0.9);
}
"""
RECTS = """
(id) => {
  const box = e => { const r = e.getBoundingClientRect();
    return { l: r.left, t: r.top, r: r.right, b: r.bottom }; };
  const out = { panel: box(document.getElementById(id)),
                canvas: box(document.querySelector('#viewer canvas')) };
  for (const k of ['viewportPane', 'chatPane', 'treePane', 'statusbar'])
    out[k] = box(document.getElementById(k));
  return out;
}
"""
PT = [10.0, 5.0, 6.0]                              # a point on the plate's top face
SIZES = [(1600, 900), (1150, 700)]                 # a wide window and a narrow one


def overlaps(a, b):
    return not (a["r"] <= b["l"] + 0.5 or a["l"] >= b["r"] - 0.5
                or a["b"] <= b["t"] + 0.5 or a["t"] >= b["b"] - 0.5)


def check_docked(page, panel_id, where):
    rc = page.evaluate(RECTS, panel_id)
    p = rc["panel"]
    assert p["r"] > p["l"] and p["b"] > p["t"], f"{panel_id} has no box at {where}"
    for k in ("chatPane", "treePane", "statusbar", "canvas"):
        assert not overlaps(p, rc[k]), \
            f"{panel_id} covers #{k} at {where}: {p} vs {rc[k]}"
    # ...and the model still has room to be worked on
    assert rc["canvas"]["r"] - rc["canvas"]["l"] >= 180, \
        f"the viewport is {rc['canvas']} at {where} — too little left to drag in"


def setup(page):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(600)


def pick_top(page):
    sp = page.evaluate(TO_SCREEN, PT)
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_function(TOP_PICKED, timeout=15000)


def test_the_hole_panel_stays_off_the_chat_at_every_window_size(page, fresh_doc, server):
    """Hole with a counterbore is the tallest panel there is — the one most
    likely to spill out of the pane it is docked in."""
    setup(page)
    pick_top(page)
    page.click("#ribbon .rbtn[title='hole']")
    page.wait_for_selector("#holeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    page.select_option("#hoKind", "counterbore")
    page.wait_for_timeout(400)
    for w, h in SIZES:
        page.set_viewport_size({"width": w, "height": h})
        page.wait_for_timeout(500)
        check_docked(page, "holeDialog", f"{w}x{h}")
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.errors == []


def test_the_measure_panel_stays_off_the_chat_at_every_window_size(page, fresh_doc, server):
    setup(page)
    pick_top(page)
    page.locator("button.tab", has_text="Inspect").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='Measure']")
    page.wait_for_selector("#measureDialog", state="visible", timeout=15000)
    page.wait_for_timeout(800)
    for w, h in SIZES:
        page.set_viewport_size({"width": w, "height": h})
        page.wait_for_timeout(500)
        check_docked(page, "measureDialog", f"{w}x{h}")
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.errors == []


INSIDE = """
() => { const b = e => { const r = e.getBoundingClientRect();
    return { l: Math.round(r.left), r: Math.round(r.right) }; };
  return { win: window.innerWidth,
           chat: b(document.getElementById('chatPane')),
           send: b(document.getElementById('chatSend')),
           scrollable: document.documentElement.scrollWidth > window.innerWidth
                       && getComputedStyle(document.body).overflow !== 'hidden' }; }
"""


def test_the_chat_column_stays_inside_the_window_on_a_small_screen(
        page, fresh_doc, server):
    """The panels are a COLUMN now, so their width comes out of the same row as
    the chat. Every pane has a floor, and when the floors add up to more than
    the window the last one — the AI designer — is simply pushed off the right
    edge. `body { overflow: hidden }`, so there is no scrolling to it: on a
    1024 px window with one panel open the send button sat entirely outside the
    window and a failed feature explained itself where no one could read it —
    the very thing docking the panels was for."""
    setup(page)
    pick_top(page)
    page.locator("button.tab", has_text="Inspect").click()
    page.click("#ribbon .rbtn[title='Section']")
    page.wait_for_selector("#sectionDialog", state="visible", timeout=15000)
    page.wait_for_timeout(400)
    for w, h in [(1120, 760), (1024, 720)]:
        page.set_viewport_size({"width": w, "height": h})
        page.wait_for_timeout(500)
        m = page.evaluate(INSIDE)
        assert m["chat"]["r"] <= m["win"] or m["scrollable"], \
            f"the chat pane ends at {m['chat']['r']} on a {w} px window: {m}"
        assert m["send"]["r"] <= m["win"] or m["scrollable"], \
            f"the chat's send button is off the window at {w}: {m}"
    page.set_viewport_size({"width": 1200, "height": 800})
    page.click("#scClose")
    assert page.errors == []


def test_a_wider_chat_column_still_pushes_the_panel_clear(page, fresh_doc, server):
    """The splitters move the panes and the panel is a column between two of
    them: dragging the chat wider must move the panel, not be covered by it."""
    setup(page)
    pick_top(page)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)
    before = page.evaluate(RECTS, "extrudeDialog")["panel"]["r"]
    bar = page.locator("#splitRight").bounding_box()
    page.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)
    page.mouse.down()
    page.mouse.move(bar["x"] - 200, bar["y"] + bar["height"] / 2, steps=8)
    page.mouse.up()
    page.wait_for_timeout(500)
    after = page.evaluate(RECTS, "extrudeDialog")["panel"]["r"]
    # it moves LEFT with the chat's edge — how far depends on how much room the
    # other panes have left to give (the viewport has a floor of its own)
    assert after < before - 20, f"the panel did not follow the pane: {before} -> {after}"
    check_docked(page, "extrudeDialog", "chat dragged wider")
    assert page.errors == []


# ---------------------------------------------------------------------------
# Round two's attack on the fix above. Lowering the CSS floors (tree 180, chat
# 200) fixes the arithmetic only for a browser that has never touched a
# splitter: splitters.js `apply()` wrote an INLINE `min-width` equal to the
# width the user dragged to ("beat the CSS min-width"), and an inline style
# beats a stylesheet. Once `split-tree` / `split-chat` are in localStorage —
# which one drag, or one double-click reset, is enough for — the two panes
# could no longer give way at all.
#
# Measured at 1024 px with ONE panel open and the saved widths left at their
# own defaults (320 / 330): the chat ran 940..1270 and its send button sat at
# 1214.7..1260 — 236 px outside the window, with body { overflow: hidden } and
# no way to scroll to it. That is the same defect the test above locks out,
# reached through the door the app's own splitters open.
# ---------------------------------------------------------------------------

def test_the_chat_stays_inside_the_window_after_a_splitter_has_been_dragged(
        page, fresh_doc, server):
    setup(page)
    pick_top(page)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)

    # the user nudges the divider — the smallest possible use of the feature
    bar = page.locator("#splitRight").bounding_box()
    page.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)
    page.mouse.down()
    page.mouse.move(bar["x"] + bar["width"] / 2 + 10,
                    bar["y"] + bar["height"] / 2, steps=5)
    page.mouse.up()
    page.wait_for_timeout(400)
    assert page.evaluate("() => !!localStorage.getItem('split-chat')"), \
        "the drag did not register — this test would prove nothing"

    for w, h in [(1120, 760), (1024, 720)]:
        page.set_viewport_size({"width": w, "height": h})
        page.wait_for_timeout(500)
        m = page.evaluate(INSIDE)
        assert m["chat"]["r"] <= m["win"] or m["scrollable"], \
            (f"after one splitter drag the chat ends at {m['chat']['r']} on a "
             f"{w} px window: {m}")
        assert m["send"]["r"] <= m["win"] or m["scrollable"], \
            f"after one splitter drag the send button is off the window at {w}: {m}"
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.errors == []


def test_a_dragged_width_is_still_honoured_when_there_is_room(page, fresh_doc,
                                                              server):
    """The other half of the same rule: a pane may give way on a narrow window,
    but on a wide one the width the user chose is exactly what they get back."""
    setup(page)
    page.set_viewport_size({"width": 1600, "height": 900})
    page.wait_for_timeout(300)
    bar = page.locator("#splitLeft").bounding_box()
    page.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)
    page.mouse.down()
    page.mouse.move(bar["x"] + bar["width"] / 2 + 60,
                    bar["y"] + bar["height"] / 2, steps=8)
    page.mouse.up()
    page.wait_for_timeout(400)
    wide = page.evaluate(
        "() => document.getElementById('treePane').getBoundingClientRect().width")
    assert wide > 360, f"the drag did not widen the tree: {wide}"
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(800)
    back = page.evaluate(
        "() => document.getElementById('treePane').getBoundingClientRect().width")
    assert abs(back - wide) < 2, \
        f"the saved tree width did not come back on reload: {wide} -> {back}"
    page.set_viewport_size({"width": 1200, "height": 800})
