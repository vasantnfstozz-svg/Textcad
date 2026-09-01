"""E2E: the version panel under the feature tree (VERSION-TREE-PLAN.md P3).

What the user asked for: "if i want to go back to that design simply click the
v1 or v2, that model should open in the design tab". These tests click.

The branched history is built through the API — that path is already covered by
tests/test_version_api.py — so what is being checked here is only what the
browser does with it: the shape it draws, the marks it puts on it, and what a
click actually does.
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")

HOLE = {"op": "with_center_hole", "inputs": ["bolts"]}


def _branched(server):
    """v1 → v2, then back to v1 → v3. So v1 has TWO children.

    Tool commits no longer mint versions (2026-09-01: nothing is pushed until
    the user saves), so every version here is an explicit save — and a save
    writes designs/<doc.name>.tcad.json, so the design is a throwaway COPY of
    flange-100 renamed INSIDE the file too: with the embedded name left as
    "flange-100", the saves would overwrite the real tracked library file
    (which is exactly what the first run of this helper did)."""
    import json as jsonlib
    import studio
    src = studio.DESIGNS / "flange-100.tcad.json"
    dst = studio.DESIGNS / "_e2e-versions.tcad.json"
    data = jsonlib.loads(src.read_text(encoding="utf-8"))
    data["name"] = "_e2e-versions"
    dst.write_text(jsonlib.dumps(data), encoding="utf-8")
    try:
        httpx.post(f"{server}/api/open/_e2e-versions", timeout=120)     # v1
        httpx.post(f"{server}/api/feature/add",
                   json={"id": "big", "params": {"radius": 20}, **HOLE},
                   timeout=120)
        httpx.post(f"{server}/api/save", timeout=120)                   # v2
        httpx.post(f"{server}/api/versions/restore", json={"id": "v1"},
                   timeout=120)
        httpx.post(f"{server}/api/feature/add",
                   json={"id": "tiny", "params": {"radius": 4}, **HOLE},
                   timeout=120)
        httpx.post(f"{server}/api/save", timeout=120)                   # v3
        httpx.post(f"{server}/api/versions/star", json={"id": "v2"}, timeout=30)
    finally:
        dst.unlink(missing_ok=True)


def _open_panel(page):
    if "collapsed" in (page.locator("#verPane").get_attribute("class") or ""):
        page.click("#verHead")
    page.wait_for_selector(".vrow", timeout=15000)


def test_the_panel_is_one_line_until_you_open_it(page, server, fresh_doc):
    """It must not steal space from the feature tree — but "which version am I
    on" has to be answerable without opening anything."""
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(1500)

    assert not page.locator("#verBody").is_visible()
    assert page.locator("#verSummary").inner_text().strip() != ""
    _open_panel(page)
    assert page.locator("#verBody").is_visible()


def test_the_panel_draws_the_branch(page, server, fresh_doc):
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    _open_panel(page)

    assert page.locator(".vrow").count() == 3
    ind = {v: page.locator(f'.vrow[data-vid="{v}"]')
                    .evaluate("e => parseInt(e.style.marginLeft) || 0")
           for v in ("v1", "v2", "v3")}
    # v1 -> v2 is a straight line, so v2 stays on the trunk; v3 is v1's SECOND
    # child, so it steps right. Indenting every link instead buried
    # rocky-keychain's linear 24 under 24 levels of margin.
    assert ind["v1"] == 0 == ind["v2"], ind
    assert ind["v3"] > ind["v2"], ind
    assert not page.errors, page.errors


def test_the_current_and_starred_versions_are_marked(page, server, fresh_doc):
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    _open_panel(page)

    assert page.locator(".vrow.cur").count() == 1
    assert page.locator(".vrow.cur .vid").inner_text() == "v3"
    assert page.locator(".vstar.on").count() == 1, "more than one star"
    assert page.locator('.vrow[data-vid="v2"] .vstar').inner_text() == "★"
    assert page.locator('.vrow[data-vid="v1"] .vstar').inner_text() == "☆"
    # the one-line summary says both without being opened
    assert "v3" in page.locator("#verSummary").inner_text()
    assert "v2" in page.locator("#verSummary").inner_text()


def test_clicking_a_version_opens_it_in_the_design_tab(page, server, fresh_doc):
    """The user's sentence, tested: click v1 and that model is on screen — in
    the SAME tab, with no new tab appearing."""
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    _open_panel(page)
    tabs_before = page.locator("#doctabs .dtab").count()

    def fids():
        return page.locator('.node[data-fid]').evaluate_all(
            'es => es.map(e => e.dataset.fid)')

    # Start from v3, which is v1 plus the "tiny" hole. Asserted
    # BEFORE the click so the check after it cannot pass by
    # finding nothing at all — .prow .pname turned out to be
    # PARAMETER rows (radius, thickness), so the original
    # assertion here was vacuous and passed either way.
    assert 'tiny' in fids(), fids()

    page.click('.vrow[data-vid="v1"]')
    page.wait_for_timeout(4000)

    assert page.locator(".vrow.cur .vid").inner_text() == "v1"
    assert page.locator("#doctabs .dtab").count() == tabs_before, \
        "restoring opened a tab"
    # v1 is the design as opened: neither added hole exists in it
    after = fids()
    assert after == ['body', 'bore', 'bolts'], after

    assert page.locator(".vrow").count() == 3, "a restore lost a version"
    assert not page.errors, page.errors


def test_starring_from_the_panel_moves_the_pin(page, server, fresh_doc):
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    _open_panel(page)

    page.click('.vrow[data-vid="v3"] .vstar')
    page.wait_for_timeout(1500)
    assert page.locator('.vrow[data-vid="v3"] .vstar').inner_text() == "★"
    assert page.locator(".vstar.on").count() == 1, "two versions starred"
    # clicking the star must NOT also restore that version
    assert page.locator(".vrow.cur .vid").inner_text() == "v3"


def test_an_unsaved_design_says_so_rather_than_looking_broken(
        page, server, fresh_doc):
    """A scratch design has no history YET. That must not read like a fault —
    the same lesson as the Examples dialog blaming examples.json for a dead
    server."""
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(1200)
    if "collapsed" in (page.locator("#verPane").get_attribute("class") or ""):
        page.click("#verHead")
    page.wait_for_timeout(1200)

    assert page.locator(".vrow").count() == 0
    assert page.locator(".vprob").count() == 0, "an empty history looked broken"
    note = page.locator(".vnote").inner_text()
    assert "save it once" in note, note
    assert "unsaved" in page.locator("#verSummary").inner_text()


def test_the_ribbon_button_opens_the_panel(page, server, fresh_doc):
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(1200)
    assert "collapsed" in page.locator("#verPane").get_attribute("class")

    page.click("#tabstrip >> text=Inspect")
    page.wait_for_timeout(300)
    page.click('#ribbon button[title="Versions"]')
    page.wait_for_timeout(1500)
    assert "collapsed" not in page.locator("#verPane").get_attribute("class")
    assert page.locator(".vrow").count() == 3


def test_the_diff_button_explains_a_version_without_restoring_it(
        page, server, fresh_doc):
    """The row opens the version; the arrows button only explains it. They must
    not be the same click — losing your place because you asked "what changed?"
    would be its own small betrayal."""
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    _open_panel(page)
    before = page.locator(".vrow.cur .vid").inner_text()

    page.click('.vrow[data-vid="v2"] .vwhy')
    page.wait_for_selector(".vdiff", timeout=15000)
    page.wait_for_timeout(1200)
    text = page.locator(".vdiff").inner_text()
    assert "vs v1" in text, text
    assert "big" in text, text                    # the hole v2 added
    assert page.locator(".vrow.cur .vid").inner_text() == before, \
        "asking what changed restored the version"

    page.click('.vrow[data-vid="v2"] .vwhy')      # toggles shut
    page.wait_for_timeout(600)
    assert page.locator(".vdiff").count() == 0
    assert not page.errors, page.errors


def test_the_first_version_diff_says_there_is_nothing_before_it(
        page, server, fresh_doc):
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    _open_panel(page)
    page.click('.vrow[data-vid="v1"] .vwhy')
    page.wait_for_selector(".vdiff", timeout=15000)
    page.wait_for_timeout(1000)
    assert "nothing before it" in page.locator(".vdiff").inner_text()


def test_the_rename_and_delete_buttons_work(page, server, fresh_doc):
    """2026-09-01: "add a option where i can delete the version and rename it"
    — rename existed as double-click-the-label and was never found, so both
    are visible buttons now."""
    _branched(server)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    _open_panel(page)

    # rename via the pencil
    page.click('.vrow[data-vid="v3"] .vedit')
    page.wait_for_selector("#askDialog[open]", timeout=15000)
    page.fill("#askInput", "the one for the mill")
    page.click("#askOk")
    page.wait_for_timeout(1500)
    assert page.locator('.vrow[data-vid="v3"] .vlabel').inner_text() == \
        "the one for the mill"

    # delete asks first; cancel changes nothing
    page.click('.vrow[data-vid="v1"] .vdel')
    page.wait_for_selector("#askDialog[open]", timeout=15000)
    assert "for good" in page.locator("#askBody").inner_text()
    page.click("#askCancel")
    page.wait_for_timeout(800)
    assert page.locator(".vrow").count() == 3

    # confirmed delete removes the row; v1's children live on as roots
    # (v2 is starred and v3 is current — the server refuses those two)
    page.click('.vrow[data-vid="v1"] .vdel')
    page.wait_for_selector("#askDialog[open]", timeout=15000)
    page.click("#askOk")
    page.wait_for_timeout(1500)
    assert page.locator(".vrow").count() == 2
    assert page.locator('.vrow[data-vid="v1"]').count() == 0
    assert page.locator('.vrow[data-vid="v2"]').count() == 1
    assert page.locator('.vrow[data-vid="v3"]').count() == 1
    assert not page.errors, page.errors


# ---------------------------------------------------------------------------
# 2026-09-01: edits no longer mint versions on their own. The tab and the
# panel show a ● for unpushed changes, the panel offers the push, and closing
# a dirty tab ASKS — "if i press, the edits i did, no need to be saved".
# ---------------------------------------------------------------------------

def test_unpushed_changes_show_a_dot_and_the_panel_pushes_them(
        page, server, fresh_doc):
    import studio
    _branched(server)
    scratch = studio.DESIGNS / "_e2e-versions.tcad.json"
    try:
        # right after _branched everything is pushed: no dot anywhere
        page.reload()
        page.wait_for_function("() => !!window.__vp", timeout=20000)
        _open_panel(page)
        assert page.locator("#doctabs .dmark").count() == 0
        assert page.locator(".vpending").count() == 0

        httpx.post(f"{server}/api/feature/add",
                   json={"id": "third", "params": {"radius": 6}, **HOLE},
                   timeout=120)
        page.reload()
        page.wait_for_function("() => !!window.__vp", timeout=20000)
        _open_panel(page)
        assert page.locator("#doctabs .dmark").count() == 1
        assert page.locator("#verSummary .vdirty").count() == 1
        page.wait_for_selector(".vpending", timeout=15000)

        page.click(".vpush")                      # the explicit push
        page.wait_for_selector('.vrow[data-vid="v4"]', timeout=15000)
        page.wait_for_timeout(800)
        assert page.locator(".vpending").count() == 0, \
            "the push left the panel still claiming unsaved changes"
        assert page.locator("#doctabs .dmark").count() == 0
        assert not page.errors, page.errors
    finally:
        scratch.unlink(missing_ok=True)           # the push re-wrote the file


def test_closing_a_dirty_tab_asks_and_discard_minted_nothing(
        page, server, fresh_doc):
    import studio
    from history import History
    _branched(server)
    httpx.post(f"{server}/api/feature/add",
               json={"id": "third", "params": {"radius": 6}, **HOLE},
               timeout=120)
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(1500)
    tabs_before = page.locator("#doctabs .dtab").count()

    # Cancel keeps the tab, edits intact
    page.click("#doctabs .dtab.active .x")
    page.wait_for_selector("#askDialog[open]", timeout=15000)
    assert "not saved as a version" in page.locator("#askBody").inner_text()
    page.click("#askCancel")
    page.wait_for_timeout(800)
    assert page.locator("#doctabs .dtab").count() == tabs_before, \
        "cancel still closed the tab"

    # Discard closes it and minted NOTHING — v1..v3 stay exactly as pushed
    page.click("#doctabs .dtab.active .x")
    page.wait_for_selector("#askDialog[open]", timeout=15000)
    page.click("#askAlt")
    page.wait_for_timeout(1500)
    assert page.locator("#doctabs .dtab").count() == tabs_before - 1
    h = History.for_design(studio._history_root(), "_e2e-versions")
    assert [v.id for v in h.versions()] == ["v1", "v2", "v3"]
    assert not (studio.DESIGNS / "_e2e-versions.tcad.json").exists(), \
        "discard wrote the design file"
    assert not page.errors, page.errors
