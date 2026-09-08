"""
supervise.py — keeps TextCAD Studio alive across a crash of the geometry kernel.

WHY. OpenCASCADE can segfault: a fillet at radius 2.0 on esp32-remote's 80-edge
top rim dies with 0xC0000005 while 1.95, 2.05 and 4.0 all refuse politely
(probes/fillet_segfault_probe.py). A segfault is not an exception — no
try/except in the server ever sees it, the process is simply gone, and with it
every unsaved tab (LAUNCH-PLAN.md §10 ★P0).

HOW. `python studio.py` runs THIS loop in a light process (no kernel import)
and the real server as a child with TEXTCAD_SERVER_CHILD=1. The session file
already holds every tab as of the LAST COMPLETED request, so the relaunched
child comes back one step behind the crash — and learns from TEXTCAD_RECOVERED
what killed its predecessor, which the UI speaks once.

Relaunch ONLY after a crash the OS reported. A deliberate stop (Ctrl+C,
Stop-Process, taskkill, exit 0) ends the loop — otherwise the user's restart
routine (stop the listener on 8123) would fight the supervisor. Exit codes,
probed 2026-09-05 (Windows 11, Python 3.14):

    access violation          0xC0000005   crash      -> relaunch
    os.abort()                0xC0000409   crash      -> relaunch
    Ctrl+C uncaught           0xC000013A   deliberate -> stop
    Stop-Process              0xFFFFFFFF   deliberate -> stop
    taskkill /F, terminate()  1            deliberate -> stop

POSIX: a negative code is a signal; SIGSEGV/SIGABRT/SIGBUS/SIGILL/SIGFPE
relaunch, SIGINT/SIGTERM stop.

A crash BEFORE the server ever served (the port never answered our poll AND no
request was in flight) means the restored session itself kills the kernel (a
saved design whose rebuild segfaults). The relaunch then runs with
TEXTCAD_SAFE_RESTORE=1: the tabs come back unbuilt (grey dots), an empty tab
is active, and the UI says so. A second startup crash gives up.

A crash NOBODY ASKED FOR repeats by itself and would otherwise relaunch for
ever: the recovered page refetches /api/model, the kernel dies in the same
tessellation, and round it goes. Those are the crashes with no request in
flight, moments after the port opened. The second in a row also relaunches
unbuilt, so there is nothing to draw; the third stops and says where the tabs
are. A fatal step the user RETRIES is not a loop — it leaves an in-flight
marker — and keeps costing exactly one step, however often they retry it.

The child holds the read end of a pipe from this process as its stdin; EOF
(this process died — killed by name, say) makes it exit, so a listener is
never orphaned on the port.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

STUDIO = Path(__file__).resolve().parent / "studio.py"


def session_path(root: Path, port: int) -> Path:
    """The open-tabs checkpoint, PER PORT: a scratch server on another port in
    the same repo must never overwrite (or restore) the main server's tabs."""
    return root / (".studio-session.json" if port == 8123
                   else f".studio-session-{port}.json")


def inflight_path(session: Path) -> Path:
    """The request the server is in the middle of (studio.py writes it before
    a POST and removes it after). Left behind = the process died in it."""
    return session.with_name(session.stem + "-inflight.json")

_CTRL_C = 0xC000013A          # STATUS_CONTROL_C_EXIT: the user, not the kernel
_KILLED = 0xFFFFFFFF          # TerminateProcess(-1): PowerShell Stop-Process
_POSIX_CRASH = {getattr(signal, n, None) for n in
                ("SIGSEGV", "SIGABRT", "SIGBUS", "SIGILL", "SIGFPE")} - {None}


def is_crash(code: int | None) -> bool:
    """Did the OS end the process (relaunch), or did it end on purpose (stop)?"""
    if code is None:
        return False
    if code < 0:                                   # POSIX: -signal
        return -code in _POSIX_CRASH
    if code == _KILLED or code == _CTRL_C:
        return False
    return 0xC0000000 <= code <= 0xCFFFFFFF        # NTSTATUS error severity


LOOP_WINDOW = 60.0        # a child that served this long was not in a loop


def relaunch_plan(loops: int, was_inflight: bool, uptime: float) -> tuple[int, str]:
    """What to do after a crash the server was SERVING when it died.

    `loops` counts the crashes in a row that nobody asked for — no request in
    flight, moments after the port opened. Those repeat by themselves; a fatal
    step the user retries leaves a marker and is not a loop.
    Returns (loops, "restart" | "unbuilt" | "stop")."""
    loops = loops + 1 if not was_inflight and uptime < LOOP_WINDOW else 0
    return loops, ("stop" if loops >= 3 else "unbuilt" if loops >= 2 else "restart")


def port_answers(port: int, timeout: float = 0.4) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def _quiet_crash_dialogs() -> None:
    """Windows: no 'python.exe has stopped working' box keeping a dead child
    alive. The error mode is inherited by the children we start."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        except Exception:
            pass


def _stop(child: subprocess.Popen) -> None:
    try:
        child.stdin.close()                        # EOF: the child exits itself
    except Exception:
        pass
    try:
        child.wait(5)
    except subprocess.TimeoutExpired:
        child.terminate()
        child.wait(5)


def main() -> int:
    port = int(os.environ.get("TEXTCAD_PORT", "8123"))
    url = f"http://127.0.0.1:{port}"

    # Refuse to start a SECOND server on a port that already answers. On
    # Windows two processes can both bind one port and replies then come from
    # whichever bound last, which makes the app behave at random -- reads as
    # "the server crashed" while a stale process quietly serves old code.
    if port_answers(port):
        print(f"Something is already serving {url}.")
        print("That is probably TextCAD Studio -- just open the tab.")
        print("If it is stuck, close it first, or pick another port:")
        print("  set TEXTCAD_PORT=8124 && python studio.py")
        return 3

    _quiet_crash_dialogs()
    session = session_path(STUDIO.parent, port)
    inflight = inflight_path(session)
    opened = False
    recovered: str | None = None          # what killed the last child, for the next
    safe = False                          # restore without rebuilding (nothing to draw)
    loops = 0                             # crashes in a row nobody asked for
    while True:
        env = dict(os.environ, TEXTCAD_SERVER_CHILD="1")
        env.pop("TEXTCAD_RECOVERED", None)
        env.pop("TEXTCAD_SAFE_RESTORE", None)
        if recovered:
            env["TEXTCAD_RECOVERED"] = recovered
        if safe:
            env["TEXTCAD_SAFE_RESTORE"] = "1"
        child = subprocess.Popen([sys.executable, str(STUDIO)],
                                 stdin=subprocess.PIPE, env=env,
                                 cwd=str(STUDIO.parent))
        ready, ready_at = False, 0.0
        try:
            while child.poll() is None:
                if not ready and port_answers(port):
                    ready, ready_at = True, time.time()
                    if not opened:
                        opened = True
                        print(f"TextCAD Studio -> {url}", flush=True)
                        # new=2 asks for a TAB in the existing window (user:
                        # "always keep one webbrowser, just open a new tab");
                        # TEXTCAD_NO_BROWSER=1 is for automated runs only.
                        if os.environ.get("TEXTCAD_NO_BROWSER") != "1":
                            try:
                                webbrowser.open(url, new=2)
                            except Exception:
                                pass
                time.sleep(0.25)
        except KeyboardInterrupt:
            _stop(child)
            return 0

        code = child.returncode
        if not is_crash(code):         # a deliberate stop, or the child's own verdict
            return code if 0 <= code < 256 else 1   # 0xFFFFFFFF etc. are not exit codes
        hexcode = f"0x{code & 0xFFFFFFFF:08X}"
        was_inflight = inflight.exists()
        served = ready or was_inflight          # a request in flight = it was serving
        if served:
            loops, plan = relaunch_plan(loops, was_inflight, time.time() - ready_at)
            if plan == "stop":
                print(f"Studio crashed ({hexcode}) three times over without being "
                      f"asked to do anything, so it is not restarting again — a "
                      f"restart would land in the same place. Nothing is lost: "
                      f"your open tabs are saved in {session.name}. Rename that "
                      f"file to start Studio empty; it still holds every tab.",
                      flush=True)
                return 1
            recovered, safe = hexcode, plan == "unbuilt"
            print(f"The geometry kernel crashed ({hexcode}). Restarting Studio"
                  + (" without rebuilding the tabs — it keeps crashing on its own."
                     if safe else
                     "; the tabs come back as of the last completed step."),
                  flush=True)
        elif not safe:
            recovered, safe = hexcode + ":startup", True
            print(f"Studio crashed ({hexcode}) before it could answer. Restarting "
                  f"without rebuilding the restored tabs.", flush=True)
        else:
            print(f"Studio crashed again ({hexcode}) at startup. Giving up.",
                  flush=True)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
