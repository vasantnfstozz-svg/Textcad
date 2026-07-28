---
name: e2e-test
description: How to write Playwright end-to-end tests for TextCAD Studio (tests/e2e/) — real browser against a real server, locking in UI flows like sketch→extrude→verify. Use when adding E2E coverage or when a UI regression needs a permanent test.
---

# E2E tests — browser-level regression protection

API tests (FastAPI TestClient) prove endpoints; E2E tests prove the UI wiring:
button → dialog → POST → rebuild → tree/viewport update. Every UI regression we
fix should leave one behind.

## Layout & running

- Tests live in `tests/e2e/test_*.py` (pytest + playwright sync API).
- Run: `C:\Python314\python.exe -m pytest tests/e2e -q` (slower than unit tests —
  keep them OUT of the default `tests` run only if they exceed ~60s total;
  otherwise run everything).
- Skip cleanly when the browser is unavailable:

```python
pw = pytest.importorskip("playwright.sync_api")
```

## Server fixture — do NOT reuse the dev server

`python studio.py` hardcodes port 8123 and auto-opens the user's browser.
Tests must run their own uvicorn on a different port, importing the app directly:

```python
import threading, uvicorn, pytest

@pytest.fixture(scope="session")
def server_url():
    import studio
    config = uvicorn.Config(studio.app, host="127.0.0.1", port=8124,
                            log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    import time, httpx
    for _ in range(50):                      # wait until it answers
        try:
            httpx.get("http://127.0.0.1:8124/api/doc", timeout=1); break
        except Exception: time.sleep(0.2)
    yield "http://127.0.0.1:8124"
    server.should_exit = True
```

Caveats (probe before trusting):
- `studio.STATE` is global — reset it in a fixture like the API tests do, and
  don't run E2E in parallel with anything else touching STATE.
- First rebuild imports build123d — the first test may need a generous timeout.

## Test style

- One test = one user story, asserted at the UI level:
  "load flange sample → click bore value → type 8 → Enter → PASS badge shows".
- Assert on visible text/classes (`expect(page.locator(...)).to_have_text(...)`),
  not on internal JS state.
- Always attach a console-error listener; assert the error list is empty at the end.
- Screenshot on failure into the scratchpad for diagnosis.
- WebGL/three.js renders in headless Chromium but needs settle time — prefer
  waiting for a DOM signal (status bar volume text, busy overlay hidden) over
  fixed sleeps.

## Priority flows to cover first (from BACKLOG.md)

1. Load sample → edit tree param → rebuild → spec PASS badge.
2. Sketch on plane → draw rect → extrude → volume in status bar.
3. Face pick → "Sketch on this face" → boss join → single solid.
4. Undo (Ctrl+Z) restores previous doc; tabs switch without rebuild.
