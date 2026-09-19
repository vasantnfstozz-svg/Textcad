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


# ---------------------------------------------------------------------------
# Round three: the panels STACK in ONE column (the user's choice, 2026-09-19).
#
# More than one panel can be open at a time — Section view and the Parameters
# panel are view states, not commands, so they take no modal lock and a tool
# opens on top of both. As a column each, every open panel cost the row another
# 210 px floor: measured 1000 px with one panel, 1210 with two, 1420 with
# three, and at 1024 px with two open the AI designer column was entirely off
# the screen. Stacked, the floor is 1000 px however many are open.
# ---------------------------------------------------------------------------

COL = """
() => {
  const col = document.getElementById('panelCol');
  const cs = getComputedStyle(col);
  const vis = [...col.children].filter(p => p.style.display !== 'none');
  return { display: cs.display, dir: cs.flexDirection,
           open: col.classList.contains('open'),
           wide: col.classList.contains('wide'),
           l: +col.getBoundingClientRect().left.toFixed(2),
           w: +col.getBoundingClientRect().width.toFixed(2),
           scrollH: col.scrollHeight, clientH: col.clientHeight,
           scrollW: col.scrollWidth, clientW: col.clientWidth,
           panels: vis.map(p => { const r = p.getBoundingClientRect();
             return { id: p.id, stacked: p.classList.contains('stacked'),
                      l: +r.left.toFixed(2), r: +r.right.toFixed(2),
                      t: +r.top.toFixed(2), b: +r.bottom.toFixed(2) }; }) };
}
"""

# every cell that has to stay on the screen, named in one place
ONSCREEN = """
() => {
  const ids = ['menubar', 'tabstrip', 'ribbon', 'doctabs', 'statusbar',
               'treePane', 'tree', 'viewportPane', 'panelCol', 'chatPane',
               'chatInput', 'chatSend', 'sBuild'];
  const out = { win: window.innerWidth, off: {} };
  for (const id of ids) {
    const e = document.getElementById(id);
    if (!e) continue;
    const r = e.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.right - window.innerWidth > 0.5)
      out.off[id] = +(r.right - window.innerWidth).toFixed(2);
  }
  return out;
}
"""


def open_params(page):
    page.locator("button.tab", has_text="Modify").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='Parameters']")
    page.wait_for_selector("#paramsDialog", state="visible", timeout=15000)
    page.fill("#pmName", "wall")
    page.fill("#pmExpr", "3")
    page.fill("#pmComment", "outer wall thickness")
    page.click("#pmAdd")
    page.wait_for_timeout(900)


def open_section(page):
    page.locator("button.tab", has_text="Inspect").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='Section']")
    page.wait_for_selector("#sectionDialog", state="visible", timeout=15000)
    page.wait_for_timeout(400)


def open_extrude(page):
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=20000)
    page.wait_for_timeout(400)


def test_three_open_panels_stack_in_one_column(page, fresh_doc, server):
    """One above the other, all at the column's left edge, and the column
    scrolls when they are taller than it. The `flex-direction` assertion is not
    decoration: an unterminated comment above the rule dropped it during
    development and the three panels went straight back to standing side by
    side, which every arithmetic assertion in this file still passed."""
    setup(page)
    open_params(page)
    open_section(page)
    pick_top(page)
    open_extrude(page)
    c = page.evaluate(COL)
    assert c["display"] == "flex" and c["dir"] == "column", \
        f"#panelCol is not a column: {c['display']} / {c['dir']}"
    assert c["open"] and c["wide"], f"the column's classes are wrong: {c}"
    ids = [p["id"] for p in c["panels"]]
    assert ids == ["extrudeDialog", "sectionDialog", "paramsDialog"], ids
    for a, b in zip(c["panels"], c["panels"][1:]):
        assert b["t"] >= a["b"] - 0.5, f"{b['id']} is not below {a['id']}: {c}"
        assert abs(b["l"] - a["l"]) < 0.5, f"{b['id']} is not in the column: {c}"
    assert [p["stacked"] for p in c["panels"]] == [False, True, True], c
    assert c["scrollH"] > c["clientH"], \
        f"three panels should be taller than the column: {c}"
    assert c["scrollW"] <= c["clientW"] + 0.5, \
        f"the column scrolls sideways — something is too wide for it: {c}"
    assert page.errors == []


def test_the_window_needs_no_more_room_for_three_panels_than_for_one(
        page, fresh_doc, server):
    """The measured reason for stacking. With a column each, 1024 px was not
    enough for two panels: the chat ran 247 px past the right edge and its send
    button with it, under `body { overflow: hidden }` and no way to scroll."""
    setup(page)
    pick_top(page)
    for n, opener in ((1, open_params), (2, open_section), (3, open_extrude)):
        opener(page)
        for w in (1024, 1100, 1200, 1280, 1600):
            page.set_viewport_size({"width": w, "height": 760})
            page.wait_for_timeout(450)
            m = page.evaluate(ONSCREEN)
            assert m["off"] == {}, \
                f"with {n} panel(s) open at {w} px, off the right edge: {m['off']}"
        page.set_viewport_size({"width": 1600, "height": 900})
        page.wait_for_timeout(300)
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.errors == []


def test_opening_a_panel_never_closes_another_one(page, fresh_doc, server):
    """Nothing closes itself: a panel the user opened stays open. Closing
    Parameters when a tool opens was one of the rejected candidates — it fixed
    only one of the three combinations anyway."""
    setup(page)
    open_params(page)
    open_section(page)
    pick_top(page)
    open_extrude(page)
    for pid in ("paramsDialog", "sectionDialog", "extrudeDialog"):
        assert page.locator(f"#{pid}").is_visible(), f"#{pid} closed itself"
    page.click("#exCancel")
    page.wait_for_timeout(800)
    for pid in ("paramsDialog", "sectionDialog"):
        assert page.locator(f"#{pid}").is_visible(), \
            f"#{pid} went away when the tool was cancelled"
    assert page.errors == []


def test_the_column_is_gone_again_when_the_last_panel_closes(
        page, fresh_doc, server):
    setup(page)
    open_params(page)
    open_section(page)
    page.click("#scClose")
    page.wait_for_timeout(400)
    page.click("#pmClose")
    page.wait_for_timeout(400)
    c = page.evaluate(COL)
    assert c["w"] == 0 and not c["open"] and not c["wide"], \
        f"the empty column is still taking room: {c}"
    assert page.errors == []


def test_the_refusal_flash_is_scrolled_to_before_it_flashes(
        page, fresh_doc, server):
    """`modalGuard` says "flashing on the right". Stacked, the panel holding
    the lock can be scrolled out of sight under another one, and a flash nobody
    can see is the same as no answer at all."""
    setup(page)
    open_params(page)
    pick_top(page)
    page.locator("button.tab", has_text="Create").click()
    page.wait_for_timeout(200)
    page.click("#ribbon .rbtn[title='hole']")           # sits below Parameters
    page.wait_for_selector("#holeDialog", state="visible", timeout=20000)
    page.select_option("#hoKind", "counterbore")
    page.wait_for_timeout(500)
    page.evaluate("() => { document.getElementById('panelCol').scrollTop = 0; }")
    page.wait_for_timeout(300)
    col_b = page.evaluate(
        "() => document.getElementById('panelCol').getBoundingClientRect().bottom")
    hole = [p for p in page.evaluate(COL)["panels"] if p["id"] == "holeDialog"][0]
    assert hole["b"] > col_b + 1, \
        f"the hole panel is already fully visible — this proves nothing: {hole}"
    page.click("#ribbon .rbtn[title='extrude']")        # refused: Hole holds it
    page.wait_for_timeout(350)
    after = page.evaluate(COL)
    hole = [p for p in after["panels"] if p["id"] == "holeDialog"][0]
    assert hole["b"] <= col_b + 1, \
        f"the flashing panel was never scrolled to: {hole} in {after}"
    assert page.locator("#holeDialog.modalflash").count() == 1, \
        "the panel did not flash"
    page.click("#hoCancel")
    page.wait_for_timeout(700)
    assert page.errors == []


def test_a_parameter_can_still_be_typed_into_the_add_row(page, fresh_doc, server):
    """`.exbtn` is the full-width button every tool panel uses, and inside the
    Add row its `width: 100%` became the button's flex BASE while the three
    boxes are `flex: 1` — basis 0, so they got what was left, which was
    nothing. Measured at a 420 px column: Add 349 px and name / formula / note
    8 px EACH, at every window size."""
    setup(page)
    page.set_viewport_size({"width": 1600, "height": 900})
    page.wait_for_timeout(300)
    open_params(page)
    w = page.evaluate("""
    () => { const b = id => +document.getElementById(id)
              .getBoundingClientRect().width.toFixed(2);
      return { name: b('pmName'), expr: b('pmExpr'),
               comment: b('pmComment'), add: b('pmAdd') }; }""")
    for k in ("name", "expr", "comment"):
        assert w[k] >= 60, f"the {k} box is {w[k]} px wide — unusable: {w}"
    assert w["add"] < 120, f"the Add button is taking the whole row: {w}"
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.errors == []


def test_the_parameters_table_keeps_every_column_in_a_narrow_one(
        page, fresh_doc, server):
    """At the column's floor six columns leave about 30 px each and every cell
    is an ellipsis. The row wraps onto two lines instead — and nothing is
    dropped: the note and the "used" count are still there, still editable by
    the same click."""
    setup(page)
    open_params(page)
    open_section(page)
    page.set_viewport_size({"width": 1024, "height": 760})
    page.wait_for_timeout(600)
    m = page.evaluate("""
    () => { const r = document.querySelector('#pmRows .pmrow');
      const out = { col: +document.getElementById('panelCol')
                          .getBoundingClientRect().width.toFixed(2) };
      for (const c of ['pmname', 'pmexpr', 'pmval', 'pmcomment', 'pmusers']) {
        const e = r.querySelector('.' + c);
        const b = e && e.getBoundingClientRect();
        out[c] = b ? +b.width.toFixed(2) : 0;
      }
      return out; }""")
    assert m["col"] < 320, f"this is not the narrow case: {m}"
    for c in ("pmname", "pmexpr", "pmval", "pmcomment", "pmusers"):
        assert m[c] > 30, f"{c} is {m[c]} px wide in a {m['col']} px column: {m}"
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.errors == []


def test_three_panels_and_both_splitters_at_their_widest_still_fit(
        page, fresh_doc, server):
    """The worst case round two's fix has to survive, now with the column
    holding three panels: both panes saved at the LIMITS maximum (640 each),
    which is the widest a drag can ever store. The saved width is a preference,
    so it gives way — and it is still there when the window is wide again."""
    page.evaluate("() => { localStorage.setItem('split-tree', '640');"
                  " localStorage.setItem('split-chat', '640'); }")
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(1000)
    setup(page)
    pick_top(page)
    open_params(page)
    open_section(page)
    open_extrude(page)
    for w in (1600, 1280, 1100, 1024):
        page.set_viewport_size({"width": w, "height": 760})
        page.wait_for_timeout(500)
        m = page.evaluate(ONSCREEN)
        assert m["off"] == {}, \
            f"at {w} px with both splitters at 640 and three panels: {m['off']}"
    page.set_viewport_size({"width": 1920, "height": 900})
    page.wait_for_timeout(600)
    saved = page.evaluate("() => [localStorage.getItem('split-tree'),"
                          " localStorage.getItem('split-chat')]")
    assert saved == ["640", "640"], \
        f"giving way threw the user's own widths away: {saved}"
    wide = page.evaluate(
        "() => document.getElementById('treePane').getBoundingClientRect().width")
    assert wide > 500, f"the tree did not grow back on a wide window: {wide}"
    page.evaluate("() => localStorage.clear()")
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.errors == []
