"""The server survives a crash of the geometry kernel (LAUNCH-PLAN.md §10 ★P0).

OCCT can segfault (probes/fillet_segfault_probe.py: radius 2.0 on esp32-remote's
top rim, exit 0xC0000005) and a segfault is not an exception — the process is
gone, and with it every unsaved tab. `python studio.py` therefore runs
supervise.py, which relaunches the real server after a crash with every tab as
of the last COMPLETED request.

The integration tests here drive the real thing: real processes on a spare
port, a real access violation (TEXTCAD_CRASH_TEST=1 adds POST /api/_crash —
the same 0xC0000005 the fillet gives, without the 8-second fillet), and this
repo's per-port session files, removed afterwards. They cost about a minute."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import studio
import supervise

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "esp32-remote.tcad.json"
PLATE = {"id": "p", "op": "plate", "inputs": [],
         "params": {"width": 60, "depth": 40, "thickness": 10}}


# ---------------------------------------------------------------------------
# the policy and the checkpoint pieces, in process
# ---------------------------------------------------------------------------

def test_only_crashes_relaunch_deliberate_stops_end_the_loop():
    """The user's restart routine stops the listener on 8123 and expects it to
    STAY down; a supervisor that restarted after Stop-Process would fight it."""
    for code in (0xC0000005, 0xC0000409):
        assert supervise.is_crash(code), hex(code)
    for code in (None, 0, 1, 3, 0xC000013A, 0xFFFFFFFF):
        assert not supervise.is_crash(code), code
    assert supervise.is_crash(-11)                  # POSIX SIGSEGV
    assert not supervise.is_crash(-2)               # SIGINT
    assert not supervise.is_crash(-15)              # SIGTERM


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(studio, "SESSION_ENABLED", True)
    monkeypatch.delenv("TEXTCAD_RECOVERED", raising=False)
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    return TestClient(studio.app)


def test_inflight_marker_lives_only_while_a_request_runs(client):
    client.post("/api/new", json={"name": "x"})
    assert studio.SESSION_PATH.exists()             # the checkpoint
    assert not studio._inflight_path().exists()     # cleared with the reply


def test_recovery_note_names_the_request_that_died(client, monkeypatch):
    marker = studio._inflight_path()
    marker.write_text(json.dumps({"method": "POST", "path": "/api/feature/params",
                                  "at": 1.0}), encoding="utf-8")
    monkeypatch.setenv("TEXTCAD_RECOVERED", "0xC0000005")
    note = studio._recovery_note()
    assert note["code"] == "0xC0000005" and note["startup"] is False
    assert note["request"]["path"] == "/api/feature/params"
    assert not marker.exists()                      # consumed
    # a deliberate stop mid-request leaves a marker too: consumed, no note
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("TEXTCAD_RECOVERED")
    assert studio._recovery_note() is None
    assert not marker.exists()
    # a startup crash blames no request
    monkeypatch.setenv("TEXTCAD_RECOVERED", "0xC0000005:startup")
    note = studio._recovery_note()
    assert note["startup"] is True and note["request"] is None
    assert note["code"] == "0xC0000005"


def test_safe_restore_builds_nothing_and_activates_nothing(client):
    client.post("/api/new", json={"name": "risky"})
    client.post("/api/feature/add", json=PLATE)
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    assert studio._restore_session(rebuild=False) == 1
    assert studio.STATE["active"] is None           # the caller opens an empty tab
    (entry,) = studio.STATE["docs"].values()
    assert entry["rebuild_ms"] is None              # never built: grey dot, not red
    assert entry["doc"].name == "risky"             # but the work is there


def test_doc_carries_the_recovery_note(client, monkeypatch):
    monkeypatch.setattr(studio, "RECOVERY", {"code": "0xC0000005", "startup": False,
                                             "request": None, "at": 1.0})
    assert client.get("/api/doc").json()["recovery"]["code"] == "0xC0000005"


# ---------------------------------------------------------------------------
# the real thing: processes, a real access violation, a spare port
# ---------------------------------------------------------------------------

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait(pred, timeout: float, step: float = 0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = pred()
        if r:
            return r
        time.sleep(step)
    return None


class _Studio:
    """`python studio.py` on a spare port, exactly as the user runs it (the
    supervisor, which starts the server as its child)."""

    def __init__(self, tmp_path):
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.files = [ROOT / f".studio-session-{self.port}.json",
                      ROOT / f".studio-session-{self.port}-inflight.json"]
        self.log_path = tmp_path / "server.log"
        self.hist = tmp_path / "hist"
        self.proc = None
        self.log = None

    def start(self, seed: dict | None = None):
        for f in self.files:
            f.unlink(missing_ok=True)
        if seed is not None:                     # a previous run's session
            self.files[0].write_text(json.dumps(seed), encoding="utf-8")
        env = dict(os.environ, TEXTCAD_PORT=str(self.port), TEXTCAD_NO_BROWSER="1",
                   TEXTCAD_CRASH_TEST="1", TEXTCAD_HISTORY_ROOT=str(self.hist))
        self.log = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py")],
                                     cwd=str(ROOT), env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        return self

    def doc(self):
        try:
            r = httpx.get(f"{self.url}/api/doc", timeout=5)
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    def post(self, path, body, timeout=60):
        return httpx.post(f"{self.url}{path}", json=body, timeout=timeout).json()

    def logged(self) -> str:
        self.log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(10)
        _wait(lambda: not supervise.port_answers(self.port), 15)
        if self.log:
            self.log.close()
        for f in self.files:
            f.unlink(missing_ok=True)


@pytest.fixture()
def live(tmp_path):
    s = _Studio(tmp_path)
    try:
        yield s
    finally:
        s.stop()


def test_a_kernel_crash_costs_one_step_not_the_session(live):
    live.start()
    assert _wait(live.doc, 90), "the server never answered:\n" + live.logged()
    live.post("/api/new", {"name": "survivor"})
    live.post("/api/feature/add", PLATE)
    before = live.doc()
    assert before["name"] == "survivor" and len(before["features"]) == 1
    assert before["recovery"] is None

    # the crash: the process is gone mid-request, the caller gets no reply
    with pytest.raises(httpx.HTTPError):
        httpx.post(f"{live.url}/api/_crash", timeout=30)

    # the supervisor brings it back, one step behind, and it says what happened
    after = _wait(lambda: (d := live.doc()) and d.get("recovery") and d, 90)
    assert after, "the supervisor did not bring the server back:\n" + live.logged()
    assert after["recovery"]["code"] == "0xC0000005"
    assert after["recovery"]["startup"] is False
    assert after["recovery"]["request"]["path"] == "/api/_crash"
    assert after["name"] == "survivor"
    assert [f["op"] for f in after["features"]] == ["plate"]
    assert after["ok"] is True
    assert "kernel crashed (0xC0000005)" in live.logged()

    # and no orphan: the supervisor killed by name takes the listener with it
    live.proc.kill()
    live.proc.wait(10)
    assert _wait(lambda: not supervise.port_answers(live.port), 15), \
        "the server child outlived its supervisor"


@pytest.mark.skipif(os.name != "nt",
                    reason="the user's restart routine is PowerShell's Stop-Process")
def test_stopping_the_listener_on_purpose_ends_the_supervisor_too(live):
    live.start()
    assert _wait(live.doc, 90), live.logged()
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-NetTCPConnection -LocalPort {live.port} -State Listen).OwningProcess"],
        capture_output=True, text=True).stdout.split()
    pids = {int(x) for x in out}
    assert len(pids) == 1, f"exactly one listener expected, got {pids}"
    (listener,) = pids
    assert listener != live.proc.pid                # the supervisor never listens
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Stop-Process -Id {listener} -Force"], capture_output=True)
    assert live.proc.wait(20) in (0, 1)             # the loop ENDED: no relaunch
    time.sleep(2)
    assert not supervise.port_answers(live.port)


def test_a_session_that_crashes_on_load_comes_back_unbuilt(live):
    """The user saved the fatal step itself (a fillet whose rebuild segfaults)
    — every restart would die rebuilding it. The supervisor's second launch
    restores the tabs UNBUILT, with an empty tab active, and says so."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["features"].append({"id": "fatal", "op": "fillet",
                             "params": {"radius": 2.0, "edges": "top"},
                             "inputs": [data["features"][-1]["id"]],
                             "suppressed": False})
    live.start(seed={"tabs": [{"doc": data, "source": None, "active": True}]})
    doc = _wait(live.doc, 180)
    assert doc, "no server after a startup crash:\n" + live.logged()
    assert doc["recovery"]["startup"] is True, live.logged()
    assert doc["recovery"]["code"] == "0xC0000005"
    assert doc["name"] == "untitled"                # the user lands on an empty tab
    tabs = {t["name"]: t for t in httpx.get(f"{live.url}/api/tabs").json()["tabs"]}
    assert tabs[data["name"]]["ok"] is None         # open, not built (grey dot)
    assert "before it could answer" in live.logged()
