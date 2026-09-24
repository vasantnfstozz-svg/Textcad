"""The MCP doorbell rings ONCE (LAUNCH-PLAN.md section 10, P1).

A design can arrive from outside the browser: mcp_server._notify_studio posts
/api/open/<slug>?external=1 and the open page says "X just arrived — loaded
it". The browser used to work out that something had arrived by comparing the
active tab against its previous poll, which is a backend fact re-derived in
JavaScript (R1) — so EVERY page load replayed the banner and reset the view,
long after the design landed and sometimes from under an open dialog (seen
2026-09-01).

The marker is the server's now, and it is consumed the moment a page shows it.
These tests are the server half: who sets it, who clears it, and the two ways
it must not be cleared — by an ack for a DIFFERENT arrival, and by nothing at
all when a page merely reloads.
"""
import pytest
from fastapi.testclient import TestClient

import studio
from fixture_docs import flange

TMP_NAME = "_test-mcp-arrival"
TMP_NAME_2 = "_test-mcp-arrival-two"


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio.ARRIVAL = None                 # no doorbell left over from a peer
    studio._new_tab(flange())
    studio._rebuild_and_mesh()
    yield TestClient(studio.app)
    studio.ARRIVAL = None
    # designs/ is the user's tracked library — never leave test files in it
    for n in (TMP_NAME, TMP_NAME_2):
        p = studio.DESIGNS / f"{n}.tcad.json"
        if p.exists():
            p.unlink()


@pytest.fixture()
def saved(client):
    """A real design file in the library, cleaned up afterwards."""
    doc = flange()
    doc.name = TMP_NAME
    doc.save(str(studio.DESIGNS / f"{TMP_NAME}.tcad.json"))
    return TMP_NAME


@pytest.fixture()
def saved2(client):
    doc = flange()
    doc.name = TMP_NAME_2
    doc.save(str(studio.DESIGNS / f"{TMP_NAME_2}.tcad.json"))
    return TMP_NAME_2


def _arrival(c):
    return c.get("/api/doc").json()["arrival"]


# --------------------------------------------------------- who rings it ---

def test_the_users_own_open_is_not_an_arrival(client, saved):
    """Clicking a design in the library dialog must not tell the user it
    arrived from somewhere. Only ?external=1 is the doorbell."""
    client.post(f"/api/open/{saved}")
    assert _arrival(client) is None


def test_an_external_open_rings_the_doorbell(client, saved):
    client.post(f"/api/open/{saved}?external=1")
    a = _arrival(client)
    assert a is not None, "a design arriving over MCP left no marker"
    assert a["file"] == saved
    assert a["name"] == TMP_NAME
    # the banner names a design the user can actually switch to
    assert a["tab"] == studio.STATE["active"]


def test_a_second_delivery_into_the_same_tab_rings_again(client, saved):
    """The design loop is regenerate -> POST /api/open -> look at it, so the
    same design arrives over and over into the tab it already owns. That
    branch reuses the tab and used to fall straight past the marker."""
    client.post(f"/api/open/{saved}?external=1")
    first = _arrival(client)
    client.post("/api/arrival/ack", json={"at": first["at"]})
    client.post(f"/api/open/{saved}?external=1")           # the reused-tab path
    again = _arrival(client)
    assert again is not None, "a redelivery into the open tab said nothing"
    assert again["at"] > first["at"]


# ------------------------------------------------------ consumed ONCE ---

def test_the_banner_is_not_replayed_on_every_page_load(client, saved):
    """THE BUG. A page shows the banner, acks it, and every later load — the
    F5, the second window, tomorrow morning — is told nothing."""
    client.post(f"/api/open/{saved}?external=1")
    a = _arrival(client)                                   # the page shows it
    r = client.post("/api/arrival/ack", json={"at": a["at"]}).json()
    assert r["consumed"] is True
    for _ in range(3):                                     # reload, reload, reload
        assert _arrival(client) is None


def test_a_page_that_never_acks_leaves_the_banner_owed(client, saved):
    """Reading /api/doc must NOT consume it: the page that fetched the
    document may be gone before it painted anything, and an arrival nobody
    was told about is worse than one told twice."""
    client.post(f"/api/open/{saved}?external=1")
    assert _arrival(client) is not None
    assert _arrival(client) is not None


def test_a_stale_ack_never_swallows_a_newer_arrival(client, saved, saved2):
    """The doorbell can ring twice inside the browser's 3 s poll. An ack
    carries the timestamp the page actually saw, so the late one only clears
    what it was about."""
    client.post(f"/api/open/{saved}?external=1")
    first = _arrival(client)
    client.post(f"/api/open/{saved2}?external=1")           # lands meanwhile
    r = client.post("/api/arrival/ack", json={"at": first["at"]}).json()
    assert r["consumed"] is False
    still = _arrival(client)
    assert still is not None and still["file"] == saved2


def test_acking_an_empty_doorbell_is_harmless(client):
    r = client.post("/api/arrival/ack", json={"at": 1.0}).json()
    assert r["consumed"] is False


# ------------------------------------------------------------- staleness ---

def test_an_arrival_nobody_came_for_stops_being_news(client, saved):
    """No page was open when it landed and none opened for ten minutes. The
    SERVER drops it, so the browser never has to decide what "just" means."""
    client.post(f"/api/open/{saved}?external=1")
    studio.ARRIVAL["at"] -= studio.ARRIVAL_TTL + 1
    assert _arrival(client) is None
    assert studio.ARRIVAL is None, "the stale marker was left lying around"
