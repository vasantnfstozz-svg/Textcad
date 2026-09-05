"""The UI survives a kernel crash and SAYS so (LAUNCH-PLAN.md §10 ★P0).

Not the shared in-thread e2e server: a real access violation would take pytest
down with it. This test runs `python studio.py` the way the user does (the
supervisor + its server child, tests/test_supervisor.py's _Studio) on a spare
port, opens the page, and lets the page's OWN postJSON — the call every tool
makes — hit the crash endpoint. What the user must then see: one chat line
naming the crash, the design back at the last completed step, no spinner left."""
import pytest

pw_api = pytest.importorskip("playwright.sync_api")

from test_supervisor import PLATE, _Studio, _wait     # tests/ is on sys.path


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
