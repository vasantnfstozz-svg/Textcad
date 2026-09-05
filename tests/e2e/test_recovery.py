"""The UI survives a kernel crash and SAYS so (LAUNCH-PLAN.md §10 ★P0).

Not the shared in-thread e2e server: a real access violation would take pytest
down with it. This test runs `python studio.py` the way the user does (the
supervisor + its server child, tests/test_supervisor.py's _Studio) on a spare
port, opens the page, and lets the page's OWN postJSON — the call every tool
makes — hit the crash endpoint. What the user must then see: one chat line
naming the crash, the design back at the last completed step, no spinner left."""
import pytest

pw_api = pytest.importorskip("playwright.sync_api")

import httpx

from test_supervisor import PLATE, _Studio, _wait     # tests/ is on sys.path
from test_fillet_tool import (BUILD, EDGE_INDICES, MODAL, click_visible_edges,
                              open_tool, wait_feature)


@pytest.fixture()
def crashy(tmp_path):
    s = _Studio(tmp_path).start()
    try:
        assert _wait(s.doc, 90), "the server never answered:\n" + s.logged()
        yield s
    finally:
        s.stop()


def test_a_kernel_crash_is_spoken_once_and_the_design_comes_back(crashy, browser):
    crashy.post("/api/new", {"name": "survivor"})
    crashy.post("/api/feature/add", PLATE)

    pg = browser.new_page(viewport={"width": 1200, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(crashy.url)
    pg.wait_for_function("() => !!window.__vp", timeout=20000)
    pg.wait_for_timeout(1200)
    assert pg.locator("#tree .nrow", has=pg.locator(".nname", has_text="p")).count() == 1
    assert "kernel crashed" not in pg.text_content("#chatLog")

    # the next step kills the kernel — through the page's own request path
    pg.evaluate("() => { import('/static/js/api.js')"
                ".then(m => m.postJSON('/api/_crash', {}, 'rounding…')); }")

    pg.wait_for_function(
        "() => document.getElementById('chatLog').innerText.includes('kernel crashed')",
        timeout=90000)
    pg.wait_for_timeout(3500)                    # a watcher tick goes by too
    log = pg.text_content("#chatLog")
    assert "0xC0000005" in log and "/api/_crash" in log
    assert "last completed step" in log
    assert log.count("kernel crashed") == 1      # spoken ONCE, whoever saw it first
    # the design is back, the spinner is gone, nothing blew up in the page
    assert pg.locator("#tree .nrow", has=pg.locator(".nname", has_text="p")).count() == 1
    assert pg.evaluate("() => document.getElementById('busy').style.display") == "none"
    assert not errs, errs
    pg.close()


def test_a_crash_inside_a_tools_own_step_closes_the_panel(crashy, browser):
    """The case the whole commit exists for: the kernel dies inside the step a
    TOOL asked for, so the answer never comes back to the code waiting for it.
    The panel must let go, the modal lock must release, the crash must be
    spoken — and nothing may throw in the page while that happens."""
    pg = browser.new_page(viewport={"width": 1200, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    # A dead server refuses every fetch until the supervisor is done — that is
    # the CONDITION under test, not a fault, so only real script errors count.
    pg.on("console", lambda m: errs.append(m.text)
          if m.type == "error" and "ERR_CONNECTION_REFUSED" not in m.text else None)
    pg.goto(crashy.url)
    pg.wait_for_function("() => !!window.__vp", timeout=20000)
    pg.wait_for_timeout(1200)

    pg.evaluate(BUILD)                       # a 40 x 30 x 20 box
    pg.wait_for_timeout(1500)
    open_tool(pg, "fillet")
    tops = pg.evaluate(EDGE_INDICES, ["b", "top"])
    click_visible_edges(pg, "b", tops, 1)
    pg.fill("#flValue", "3")                 # creates fillet1 — this one lands
    f = wait_feature(crashy.url, "fillet1")
    assert f["status"] == "ok" and f["params"]["radius"] == 3

    # the NEXT value the tool pushes kills the kernel — the fillet radius 2.0
    # story, without waiting 8 s for OCCT to get there
    httpx.post(f"{crashy.url}/api/_crash_next",
               json={"path": "/api/feature/params"}, timeout=10)
    pg.fill("#flValue", "5")

    pg.wait_for_function(
        "() => document.getElementById('chatLog').innerText.includes('kernel crashed')",
        timeout=120000)
    pg.wait_for_timeout(3500)                # a watcher tick goes by too
    log = pg.text_content("#chatLog")
    assert "0xC0000005" in log and "/api/feature/params" in log
    assert "try a different value" in log
    assert log.count("kernel crashed") == 1

    # the panel let go, the lock with it, and the page did not throw
    pg.wait_for_selector("#flDialog", state="hidden", timeout=15000)
    assert pg.evaluate(MODAL) is None
    assert not errs, errs

    # and the design is the last completed step: radius 3, not the fatal 5
    back = httpx.get(f"{crashy.url}/api/doc", timeout=30).json()
    fillet = next(x for x in back["features"] if x["id"] == "fillet1")
    assert fillet["params"]["radius"] == 3 and fillet["status"] == "ok"
    pg.close()
