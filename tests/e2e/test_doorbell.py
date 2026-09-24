"""E2E: the MCP doorbell — the banner the SERVER owes really reaches the page.

`tests/test_mcp_arrival.py` proves the server's half: `?external=1` leaves a
one-shot marker and `/api/arrival/ack` consumes it. This is the other half,
and it is where a review found the gap: the browser's `noteArrival` hung off
`docSig(d) !== docSig(S.lastDoc)`, so a REDELIVERY of a design whose bytes did
not change — the reused-tab path, which does not rebuild — left name, feature
count, rebuild_ms and `ok` all unchanged, the banner was never spoken, and the
marker sat owed for its whole ten minutes.
"""
import pytest
from fixture_docs import flange

pytest.importorskip("playwright.sync_api")

NAME = "e2e-doorbell"
BANNER = "just arrived"


def _rings(page):
    """Wait for the doorbell line in the chat log, then count how many."""
    page.wait_for_function(
        "n => (document.getElementById('chatLog').innerText.match"
        "(/just arrived/g) || []).length >= n", arg=1, timeout=15000)
    return page.evaluate(
        "() => (document.getElementById('chatLog').innerText.match"
        "(/just arrived/g) || []).length")


@pytest.fixture()
def saved(fresh_doc):
    """A real design file in the library, cleaned up afterwards."""
    import studio
    doc = flange()
    doc.name = NAME
    path = studio.DESIGNS / f"{NAME}.tcad.json"
    doc.save(str(path))
    studio.ARRIVAL = None
    yield NAME
    studio.ARRIVAL = None
    if path.exists():
        path.unlink()


def _deliver(page, name, external=True):
    """What the MCP server's fire-and-forget ping does, from inside the tab."""
    q = "?external=1" if external else ""
    page.evaluate("() => fetch('/api/open/" + name + q + "', "
                  "{ method: 'POST' })")


def test_a_design_arriving_over_mcp_says_so_once(page, saved):
    _deliver(page, saved)
    assert _rings(page) == 1
    # and the server was told, so no later page or reload repeats it
    page.wait_for_function(
        "async () => (await (await fetch('/api/doc')).json()).arrival === null",
        timeout=15000)


def test_a_redelivery_of_an_UNCHANGED_design_still_rings(page, saved):
    """THE BUG. The regenerate loop is 'build the script -> POST /api/open ->
    look at it', so the same design lands in the tab it already owns. When the
    bytes happen to be identical nothing about the document changes, and the
    banner used to be lost with it."""
    _deliver(page, saved)
    assert _rings(page) == 1
    page.wait_for_timeout(3500)                 # the ack has been and gone
    _deliver(page, saved)                       # byte-for-byte the same design
    page.wait_for_function(
        "() => (document.getElementById('chatLog').innerText.match"
        "(/just arrived/g) || []).length === 2", timeout=15000)
    assert not page.errors


def test_the_users_own_open_says_nothing(page, saved):
    """No ?external=1: the user clicked it themselves in the Open dialog."""
    _deliver(page, saved, external=False)
    page.wait_for_timeout(4000)                 # two polls
    assert BANNER not in page.evaluate(
        "() => document.getElementById('chatLog').innerText")
