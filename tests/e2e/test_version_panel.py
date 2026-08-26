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
    """v1 → v2, then back to v1 → v3. So v1 has TWO children."""
    httpx.post(f"{server}/api/open/flange-100", timeout=120)
    httpx.post(f"{server}/api/feature/add",
               json={"id": "big", "params": {"radius": 20}, **HOLE}, timeout=120)
    httpx.post(f"{server}/api/versions/restore", json={"id": "v1"}, timeout=120)
    httpx.post(f"{server}/api/feature/add",
               json={"id": "tiny", "params": {"radius": 4}, **HOLE}, timeout=120)
    httpx.post(f"{server}/api/versions/star", json={"id": "v2"}, timeout=30)


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
