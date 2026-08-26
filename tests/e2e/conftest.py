"""Shared E2E fixtures: ONE uvicorn + ONE browser for the whole e2e run.

Launching a server and a chromium per test file is the difference between a
~30s and a ~90s suite, and E2E tests only stay useful while they are cheap
enough to run every time.

The port is private on purpose — never the dev server. Several processes can
LISTEN on one port on Windows, and then responses come from whichever bound
last, which makes results meaningless (see the debug-studio skill).
"""
import threading
import time

import pytest

pw_api = pytest.importorskip("playwright.sync_api")

PORT = 8136
URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="session")
def server():
    import uvicorn
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    cfg = uvicorn.Config(studio.app, host="127.0.0.1", port=PORT,
                         log_level="warning")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    import httpx
    for _ in range(80):
        try:
            httpx.get(f"{URL}/api/doc", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    yield URL
    srv.should_exit = True


@pytest.fixture(scope="session")
def browser():
    with pw_api.sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def fresh_doc(server):
    """Empty document before a test that builds geometry. STATE is global to
    the server process, so tests must not rely on each other's leftovers."""
    import studio
    from document import Document
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(Document(name="e2e"))
    studio._rebuild_and_mesh()
    return studio


@pytest.fixture()
def page(server, browser):
    pg = browser.new_page(viewport={"width": 1200, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console",
          lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(server)
    pg.wait_for_function("() => !!window.__vp", timeout=20000)
    pg.wait_for_timeout(1200)                      # first render
    pg.errors = errs
    yield pg
    pg.close()


# ---------------------------------------------------------------------------
# The app no longer uses window.confirm()/prompt(): a native dialog steals OS
# focus, freezes the page and cannot be styled, so every one of them is now an
# in-app <dialog id="askDialog"> (static/js/ask.js). Tests have to CLICK it
# rather than register page.on("dialog"), which would now wait forever.
# ---------------------------------------------------------------------------

def ask_text(page, timeout=15000):
    """Wait for the ask dialog and return the question it is showing."""
    page.wait_for_selector("#askDialog[open]", timeout=timeout)
    return (page.locator("#askTitle").inner_text() + " "
            + page.locator("#askBody").inner_text())


def ask_ok(page, timeout=15000):
    """Accept the in-app confirm (the old d.accept())."""
    msg = ask_text(page, timeout)
    page.click("#askOk")
    page.wait_for_function("() => !document.getElementById('askDialog').open",
                           timeout=timeout)
    return msg


def ask_cancel(page, timeout=15000):
    """Dismiss the in-app confirm (the old d.dismiss())."""
    msg = ask_text(page, timeout)
    page.click("#askCancel")
    page.wait_for_function("() => !document.getElementById('askDialog').open",
                           timeout=timeout)
    return msg
