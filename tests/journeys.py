"""Random journeys: the machine plays the user (LAUNCH-PLAN.md P5b, §6 tier 4).

A plain script, no browser, no AI, no tokens. It opens a design the way the
app does (in-process FastAPI, the same routes the toolbar calls), then plays
random user moves against it — add a body, sketch on a face and extrude,
fillet, shell, pattern, edit a number, undo, strike out, roll back, ask every
tool for its plan — and after EVERY request asks the questions a reviewer
would:

  * did a kernel exception reach the user (an `error` that names an
    exception class, or an HTTP status that is neither 200 nor 400)?
  * did a refused request change the document anyway?
  * is any GREEN body on screen unsound (inspector.health)?
  * does undo really put back what was there before the last step?
  * does strike + restore, and rollback + release, leave the design as it was?
  * does the file round-trip (to_data -> from_data -> to_data)?

Each finding is a folder under bugs/: the document BEFORE the step, the one
request that broke it, the document after, and a plain-words report.md. A
later chat reads the folder and has the repro with no description needed:

    python tests/journeys.py --replay bugs/<folder>

Every journey runs in a CHILD process, because a random step can segfault
OpenCASCADE (exit 0xC0000005, see supervise.py) and that must be a finding,
not the end of the night. The child writes each step to a log BEFORE sending
it, so a crash leaves the recipe behind.

    python tests/journeys.py                     # fixtures + an empty design, until Ctrl+C
    python tests/journeys.py --hours 8           # overnight
    python tests/journeys.py --library           # also the user's live designs/ (read-only)
    python tests/journeys.py --designs pump-impeller --seed 7 --steps 40 --journeys 3

Nothing here ever writes into designs/: designs are read with
Document.from_data, version histories go to a throwaway TEXTCAD_HISTORY_ROOT,
and the runner never calls /api/save.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import kernelguard                    # noqa: E402 — after sys.path, and only for its constants

BUGS = ROOT / "bugs"
FIXTURES = ROOT / "tests" / "fixtures"
DESIGNS = ROOT / "designs"
LOG_NAME = "journeys.log"
EMPTY = "empty"                      # the pseudo-design: start from nothing

EXIT_CLEAN, EXIT_BROKEN, EXIT_BUG, EXIT_DUP = 0, 2, 3, 4
SLOW_MS = 60_000                     # a step slower than this is noted, not a bug
# A request that takes longer than this, or that grows the process by more
# than this, is a FINDING even when it answers 200. On 2026-09-12 one plate
# add on bottle_cap_28mm took 22 minutes and 44 GB (the spec's symmetry
# boolean), the runner logged "200 1351644 ms" and moved on, and the 16 GB
# laptop died fifty minutes later. Under a 6 GB cap the same request took
# 55 s and still answered 200: the time oracle alone would have missed it.
#
# The limit is the PRODUCT'S OWN: kernelguard gives one guarded kernel call
# `DEFAULT_BUDGET` seconds and only then calls it a hang. Under that ceiling
# the app is entitled to be slow — the guard has not reached its own limit,
# and a correct answer there is correct behaviour, not a finding; the runner's
# private 120 s filed three of them on the night of 2026-09-13 alone (a 405 s
# shell, a 164 s pattern, a 135 s chamfer, all answering 200, all triaged by
# hand). Past the budget something the guard should have ended ran on, which
# is a finding whatever it answered — and 2026-09-12's 22-minute plate add is
# still one. A step slower than SLOW_MS is still written down as a note.
HANG_MS = int(kernelguard.DEFAULT_BUDGET * 1000)
MEMORY_BUG_MB = 2048
# ... and the hard backstop: every child runs inside a Windows Job object
# with this much memory, so the kernel refuses the allocation and the CHILD
# dies (a finding) instead of the box. 0 switches it off.
MEM_CAP_GB = 6.0
# ... and the oracle the other two cannot be: HANG_MS is read when a request
# COMES BACK, so a request that never does is invisible to it. On 2026-09-13
# journey 512 (planetary-ring s47276) sat in one /api/edit from 05:09 to
# 08:15 — three hours — and what ended it came from outside the runner, which
# filed it as an exit code nobody could read. The PARENT watches the child's
# step log instead: no new step for this long and the child is killed and the
# stall filed, naming the request it was still in. 0 switches it off.
#
# It sits ABOVE the step limit on purpose. The guard's own timeout is the
# better finding — it comes back as a sentence naming the feature and the op,
# the child files a folder with the document on both sides of it, and the
# `kernel-stalled` oracle reads it. Killing the child first throws all of that
# away for a corpse and an exit code (bugs/20260913-212515-autonomiq-panel-
# s18884-crash was killed at 600 s with the guard's 900 s budget still
# running). So the parent waits out the budget plus the longest a fresh worker
# may take to come up, and only kills when the guard itself has failed to.
STALL_KILL_S = kernelguard.DEFAULT_BUDGET + kernelguard.READY_SECONDS


def awake_s() -> float:
    """Seconds since boot NOT counting the time the machine spent asleep.

    Windows' monotonic clock is QueryPerformanceCounter and it keeps ticking
    through a suspend, so an overnight run times the sleep as work. On
    2026-09-13 one `/api/undo` — a rebuild in memory, its neighbours 23 ms and
    3598 ms, its working set flat at 512 MB — was measured at 29 781 465 ms
    (8 h 16 m) and filed as a hang: the laptop had slept in the middle of it
    (bugs/20260914-065540-autonomiq-sat-panel-s18939-step16). Measured on this
    box in the same hour: 33.08 hours of uptime against 29.48 hours awake
    (probes/awake_clock.py). QueryUnbiasedInterruptTime is the clock that
    stops at suspend. Where it cannot be read, and on Linux and macOS (whose
    monotonic clocks already stop at suspend), `time.monotonic` is the answer.
    """
    try:
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes as wt
            fn = getattr(awake_s, "_fn", None)
            if fn is None:
                fn = ctypes.WinDLL("kernel32").QueryUnbiasedInterruptTime
                fn.argtypes = [ctypes.POINTER(wt.ULARGE_INTEGER)]
                fn.restype = wt.BOOL
                awake_s._fn = fn
            v = wt.ULARGE_INTEGER()
            if fn(ctypes.byref(v)):
                return v.value / 1e7          # 100-ns units -> seconds
    except Exception:                        # noqa: BLE001 — a clock is never worth a crash
        pass
    return time.monotonic()


# Below this the two clocks are merely disagreeing with each other (they read
# within 6 ms over 2 s, measured); a suspend is minutes to hours.
SLEPT_FLOOR_S = 1.0


def awake_elapsed(perf0: float, awake0: float) -> tuple[float, float]:
    """How long something really took, and how much of it was machine sleep.

    Both clocks are read, because they are good at different things:
    `perf_counter` has 100 ns resolution and the awake clock about 9 ms
    (measured), so an ordinary step keeps its millisecond reading and only a
    real suspend is taken off it.
    """
    ran = time.perf_counter() - perf0
    slept = ran - (awake_s() - awake0)
    return (ran - slept, slept) if slept > SLEPT_FLOOR_S else (ran, 0.0)


def peak_mb() -> float:
    """This process's peak working set, MB (0.0 where it cannot be read)."""
    try:
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes as wt

            class _Counters(ctypes.Structure):
                _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            c = _Counters()
            c.cb = ctypes.sizeof(c)
            k32 = ctypes.WinDLL("kernel32")
            # without these the 64-bit pseudo-handle is truncated to a C int
            # and the call fails with ERROR_INVALID_HANDLE (measured)
            k32.GetCurrentProcess.restype = wt.HANDLE
            k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_Counters), wt.DWORD]
            k32.K32GetProcessMemoryInfo.restype = wt.BOOL
            if k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return c.PeakWorkingSetSize / 1024 ** 2
            return 0.0
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss / 1024 if sys.platform != "darwin" else rss / 1024 ** 2
    except Exception:                        # noqa: BLE001 — no reading beats a crash here
        return 0.0


class JobCap:
    """A Windows Job object with a hard memory ceiling for one child.

    `start(cmd, ...)` launches the child SUSPENDED, puts it in the job, then
    lets it run, so not one allocation escapes the cap. `peak_gb()` is what
    the job reached; `hit` says whether it reached the ceiling. On other
    platforms there is no cap (`available` is False) and the child simply runs.
    Measured on the toy that asks for 4 GB under a 1 GB cap: MemoryError at
    1.18 GB, box untouched (probes/memcap.py)."""
    available = sys.platform == "win32"

    def __init__(self, gb: float):
        self.gb = float(gb or 0)
        self.job = None
        if self.gb <= 0 or not self.available:
            return
        import ctypes
        import ctypes.wintypes as wt
        self._ct, self._wt = ctypes, wt
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", wt.LARGE_INTEGER),
                        ("PerJobUserTimeLimit", wt.LARGE_INTEGER),
                        ("LimitFlags", wt.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wt.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wt.DWORD),
                        ("SchedulingClass", wt.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        self._Extended = Extended
        self.job = self.k32.CreateJobObjectW(None, None)
        if not self.job:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x200 | 0x2000   # JOB_MEMORY | KILL_ON_JOB_CLOSE
        info.JobMemoryLimit = int(self.gb * 1024 ** 3)
        if not self.k32.SetInformationJobObject(self.job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())

    def start(self, cmd: list[str], **popen_kw) -> subprocess.Popen:
        if self.job is None:
            return subprocess.Popen(cmd, **popen_kw)
        proc = subprocess.Popen(cmd, creationflags=0x4, **popen_kw)      # CREATE_SUSPENDED
        h = self._wt.HANDLE(proc._handle)
        if not self.k32.AssignProcessToJobObject(self.job, h):
            proc.kill()
            raise self._ct.WinError(self._ct.get_last_error())
        self._ct.WinDLL("ntdll").NtResumeProcess(h)
        return proc

    def peak_gb(self) -> float:
        if self.job is None:
            return 0.0
        info = self._Extended()
        self.k32.QueryInformationJobObject(self.job, 9, self._ct.byref(info),
                                           self._ct.sizeof(info), None)
        return info.PeakJobMemoryUsed / 1024 ** 3

    @property
    def hit(self) -> bool:
        return self.job is not None and self.peak_gb() >= self.gb * 0.95

# An `error` sentence the app meant to say ("the radius must be smaller than
# half the wall") versus one the _never_die barrier wrote from an exception
# ("KeyError: 'face'", "Standard_ConstructionError: ..."). Only the second is
# a finding: the first is the product working.
#
# _never_die writes f"{type(e).__name__}: {e}", so the classifier has to know
# the class NAMES the app can raise. Most end in Error/Exception; OpenCASCADE
# has two families and only Standard_* was listed, so a leaked
# `StdFail_NotDone: BRep_API: command not done` — the commonest kernel
# exception there is — read as the product working (P5b review, 2026-09-12).
# The suffix-less builtins are enumerated for the same reason: a `next()` over
# an empty generator raises StopIteration, whose name carries no suffix at all.
# test_journeys.py walks OCP and the builtins and asserts every one is known.
_UNHANDLED = re.compile(
    r"^(?:[A-Za-z_][\w.]*\.)?[A-Z]\w*(?:Error|Exception|Failure|Fault)\b\s*:"
    r"|Standard_\w+|StdFail_\w+"
    r"|^Traceback \(most recent")

# ... and the names that fit no pattern at all (Exception, ExceptionGroup,
# StopIteration, StopAsyncIteration, _IncompleteInputError,
# KeyboardInterrupt) are ASKED FOR rather than guessed at: every exception
# class in builtins and in OpenCASCADE's two families. A sentence of the
# product's own that happens to start "Word: " is still not a leak, because
# "Word" is not one of them.
_CLASS_COLON = re.compile(r"^(?:[A-Za-z_][\w.]*\.)?([A-Za-z_]\w*)\s*:")
_LEAK_NAMES: frozenset | None = None


def _leak_names() -> frozenset:
    """Every exception class name the app can put in front of a colon."""
    global _LEAK_NAMES
    if _LEAK_NAMES is None:
        import builtins
        names = {n for n, o in vars(builtins).items()
                 if isinstance(o, type) and issubclass(o, BaseException)
                 and not issubclass(o, Warning)}
        for mod in ("Standard", "StdFail"):
            try:
                m = __import__(f"OCP.{mod}", fromlist=["*"])
            except Exception:                    # noqa: BLE001 — no OCP: skip it
                continue
            names |= {n for n in dir(m)
                      if isinstance(getattr(m, n, None), type)
                      and issubclass(getattr(m, n), BaseException)}
        _LEAK_NAMES = frozenset(names)
    return _LEAK_NAMES

# The tools that ask the server for a plan (toolplan._PLANNERS).
PLAN_TOOLS = ("extrude", "revolve", "sketch", "fillet", "hole", "pattern",
              "mirror", "shell", "move", "rotate")


def unhandled(error) -> bool:
    """True when an `error` string is an exception that leaked, not a sentence."""
    text = str(error).strip() if error else ""
    if not text:
        return False
    if _UNHANDLED.search(text):
        return True
    m = _CLASS_COLON.match(text)
    return bool(m and m.group(1) in _leak_names())


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "untitled"


def signature(kind: str, op: str | None, detail: str) -> str:
    """One bug, one folder: the same failure class on the same op with the
    same wording (numbers masked) is a repeat, not a second finding."""
    text = re.sub(r"-?\d+(?:\.\d+)?", "#", str(detail))[:80]
    return f"{kind}|{op or '-'}|{text}"


# --------------------------------------------------------------------------
# The in-process server
# --------------------------------------------------------------------------

def make_client(history_root: str | None = None):
    """The app in this process, on a throwaway history root. -> (studio, client)"""
    root = history_root or tempfile.mkdtemp(prefix="journey-hist-")
    os.environ["TEXTCAD_HISTORY_ROOT"] = root
    os.environ.setdefault("TEXTCAD_NO_BROWSER", "1")
    import studio
    from fastapi.testclient import TestClient
    # The viewport's STL lives at ROOT/_studio_mesh.stl, and /api/new and a
    # remove that empties the design DELETE it — the user's own Studio, open on
    # this checkout while the runner plays overnight, would lose the file under
    # its feet. Point it at the throwaway root instead (P5b review).
    studio.MESH_PATH = Path(root) / "_studio_mesh.stl"
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    # raise_server_exceptions=False: a leak past _never_die must come back
    # as a status code the checks can see, not kill the journey
    return studio, TestClient(studio.app, raise_server_exceptions=False)


def sources(library: bool = False, only: list[str] | None = None) -> list[tuple[str, Path | None]]:
    """(name, path) pairs to play: the empty design, the frozen fixtures and,
    opt-in, the live library — never written, only read."""
    out: list[tuple[str, Path | None]] = [(EMPTY, None)]
    out += [(design_name(p), p) for p in sorted(FIXTURES.glob("*.tcad.json"))]
    if library:
        out += [(design_name(p), p) for p in sorted(DESIGNS.glob("*.tcad.json"))]
    if only:
        want = {o.lower() for o in only}
        out = [s for s in out if s[0].lower() in want]
        missing = want - {s[0].lower() for s in out}
        if missing:
            raise SystemExit(f"no such design(s): {', '.join(sorted(missing))}")
    return out


def design_name(path: Path) -> str:
    """designs/pump-impeller.tcad.json -> pump-impeller (Path.stem keeps .tcad)."""
    return path.name[:-len(".tcad.json")] if path.name.endswith(".tcad.json") else path.stem


def load_document(path: Path | None):
    from document import Document
    if path is None:
        return Document(name="journey-empty")
    return Document.from_data(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# One journey
# --------------------------------------------------------------------------

class Bug(Exception):
    """A finding, with everything a repro needs.

    `before` and `replay` exist because half the oracles judge a PAIR of
    requests, not one: strike + restore, rollback + release, edit + undo. The
    document they compare against is the one from before the FIRST of the
    pair, and resending only the last one puts the second half against a
    document that has already had the first — which passed, so the folder's
    own `--replay` line printed "the step passes now" for a bug that is still
    there every single time (P5b review, 2026-09-12). A move that judges a
    pair hands over its own baseline and the whole sequence."""

    def __init__(self, kind: str, detail: str, request: dict | None,
                 response: dict | None, before: dict | None = None,
                 replay: list[dict] | None = None):
        super().__init__(f"{kind}: {detail}")
        self.kind, self.detail = kind, detail
        self.request, self.response = request, response
        self.before = before
        self.replay = list(replay) if replay is not None else (
            [request] if request and request.get("url") else [])


class Journey:
    """Plays `steps` random moves on one design and checks after each one."""

    def __init__(self, name: str, path: Path | None, seed: int, steps: int,
                 log_path: Path | None = None, verbose: bool = True,
                 client=None, studio=None):
        self.name, self.path, self.seed, self.n_steps = name, path, seed, steps
        self.rng = random.Random(seed)
        self.log_path = log_path
        self.verbose = verbose
        self.steps: list[dict] = []          # every request, in order
        self.notes: list[str] = []           # slow steps and other non-bugs
        self.counter = 0
        if client is None:
            studio, client = make_client()
        self.studio, self.client = studio, client
        import inspector
        import kernelguard
        self.inspector = inspector
        self.kernelguard = kernelguard

    # -- helpers ------------------------------------------------------------

    @property
    def doc(self):
        return self.studio._doc()

    def data(self) -> dict:
        return self.doc.to_data()

    def volumes(self) -> dict:
        out = {}
        for fid in self.doc.leaf_solid_ids():
            p = self.doc._parts.get(fid)
            try:
                out[fid] = round(float(p.volume), 3)
            except Exception:                 # noqa: BLE001 — measured below
                out[fid] = None
        return out

    def say(self, text: str):
        if self.verbose:
            print(f"  [{self.name} s{self.seed} #{self.counter}] {text}"[:160],
                  flush=True)

    def fresh_id(self, op: str) -> str:
        self.counter_ids = getattr(self, "counter_ids", 0) + 1
        return f"j{self.counter_ids}_{op}"

    def features(self, live=True):
        return [f for f in self.doc.features if not (live and f.suppressed)]

    def solids(self) -> list[str]:
        return list(self.doc.leaf_solid_ids())

    def faces(self, body: str | None = None) -> list[dict]:
        """Planar faces the viewport would let the user click, from /api/model."""
        r = self.client.get("/api/model")
        if r.status_code != 200:
            return []
        try:
            faces = r.json().get("faces") or []
        except ValueError:
            return []
        out = [f for f in faces if f.get("planar") and f.get("center")
               and f.get("normal") and (body is None or f.get("body") == body)]
        return out

    # -- the one request path, with every check -----------------------------

    def call(self, kind: str, method: str, url: str, body: dict | None = None,
             mutating: bool = True) -> dict:
        """Send one request and run the checks. Raises Bug."""
        self.counter += 1
        op = (body or {}).get("op") or (body or {}).get("tool")
        before = self.data() if mutating else None
        rec = {"n": self.counter, "kind": kind, "method": method, "url": url,
               "body": body, "op": op}
        self.steps.append(rec)
        self._flush_log()
        mem0 = peak_mb()
        t0, awake0 = time.perf_counter(), awake_s()
        if method == "GET":
            r = self.client.get(url)
        else:
            r = self.client.post(url, json=body or {})
        ran, slept = awake_elapsed(t0, awake0)
        rec["ms"] = round(ran * 1000)
        if slept:
            # said out loud, not quietly subtracted: the reading is no longer
            # the wall clock and the log has to be able to say why
            rec["slept_s"] = round(slept)
            self.notes.append(f"step {self.counter} ran while the machine slept "
                              f"for {slept / 60:.0f} min (not counted)")
        rec["peak_mb"] = round(peak_mb())
        rec["grew_mb"] = round(rec["peak_mb"] - mem0)
        rec["status"] = r.status_code
        try:
            resp = r.json()
        except ValueError:
            resp = {"_raw": r.text[:500]}
        if not isinstance(resp, dict):
            resp = {"_list": True}
        rec["error"] = resp.get("error")
        self._flush_log()
        if rec["ms"] > SLOW_MS:
            self.notes.append(f"step {self.counter} ({kind} {op or ''}) took {rec['ms']} ms")
        self.say(f"{kind:14s} {op or '':16s} -> {r.status_code} {rec['ms']} ms"
                 + (f"  {rec['error']}" if rec["error"] else ""))
        # 1. the two banned failures: a leaked exception, an unexpected status
        if r.status_code not in (200, 400):
            raise Bug("http-status", f"HTTP {r.status_code}: {r.text[:300]}", rec, resp)
        if unhandled(resp.get("error")):
            raise Bug("unhandled-error", str(resp["error"]), rec, resp)
        # 2. a refusal leaves the document exactly as it was
        if mutating and r.status_code == 400 and self.data() != before:
            raise Bug("refusal-changed-doc",
                      f"a 400 ({resp.get('error')}) changed the document", rec, resp,
                      before=before)
        # 2b. a DRY RUN is a question ("what would deleting this take with
        # it?"), answered before anything is snapshotted — so a dry run that
        # wrote would be a change with no undo step behind it. The move sends
        # one with mutating=True for exactly this check.
        if mutating and (body or {}).get("dry_run") and self.data() != before:
            raise Bug("dry-run-changed-doc",
                      f"a dry run of {url} changed the document", rec, resp,
                      before=before)
        # 3. every green body on screen is sound
        if mutating and r.status_code == 200:
            self.check_bodies(rec, resp)
        # 4. the machine is part of the product: a request that runs away in
        # time or memory is a finding whatever it answered (see HANG_MS).
        # LAST, after the document and geometry oracles: a slow request can
        # also hand back a broken body, and a Bug ends the journey — raising
        # the clock first filed autonomiq-panel's 1195 s shell as a "hang"
        # and never asked what it had built (review of 53f5653, 2026-09-13).
        if rec["ms"] > HANG_MS:
            raise Bug("hang", f"{kind} {op or ''} took {rec['ms'] / 1000:.0f} s "
                      f"(the limit is {HANG_MS // 1000} s) and answered {r.status_code}",
                      rec, resp)
        if rec["grew_mb"] > MEMORY_BUG_MB:
            raise Bug("memory", f"{kind} {op or ''} grew the server by {rec['grew_mb']} MB "
                      f"in one request (the limit is {MEMORY_BUG_MB} MB) and answered "
                      f"{r.status_code}", rec, resp)
        return resp

    def check_bodies(self, rec, resp):
        doc = self.doc
        for fid in doc.leaf_solid_ids():
            f = doc.get(fid)
            if f.status != "ok" or f.suppressed:
                continue
            part = doc._parts.get(fid)
            if part is None:
                raise Bug("green-without-part", f"'{fid}' ({f.op}) is ok but has no shape", rec, resp)
            problems = self.inspector.health(part)
            if problems:
                raise Bug("green-but-unsound",
                          f"'{fid}' ({f.op}) is green but: " + "; ".join(problems), rec, resp)
        for f in doc.features:
            if f.suppressed:
                continue
            if f.status == "failed" and not f.problems:
                raise Bug("red-without-sentence", f"'{f.id}' ({f.op}) is red with no problem text", rec, resp)
            # A kernel crash used to end this child, and the runner filed it by
            # reading the corpse. Since kernelguard.py it is a polite sentence
            # in a red row and the process walks on — which is the point, and
            # would also make every FUTURE crash invisible here. So the phrase
            # the guard puts in that sentence is an oracle of its own.
            for said in (f.problems or ()):
                if self.kernelguard.CRASH_PHRASE in said:
                    raise Bug("kernel-crash", f"'{f.id}' ({f.op}): {said}", rec, resp)
                if self.kernelguard.STOPPED_PHRASE in said:
                    raise Bug("kernel-stalled", f"'{f.id}' ({f.op}): {said}", rec, resp)

    def _flush_log(self):
        if self.log_path is None:
            return
        self.log_path.write_text(json.dumps({
            "design": self.name, "file": str(self.path) if self.path else None,
            "seed": self.seed, "steps": self.steps}, indent=1, default=str),
            encoding="utf-8")

    # -- random values --------------------------------------------------------

    def num(self, lo, hi, digits=1):
        return round(self.rng.uniform(lo, hi), digits)

    def pick(self, items):
        return self.rng.choice(list(items))

    # -- the moves ------------------------------------------------------------

    def move_add_creator(self):
        op = self.pick(["plate", "disc", "ball", "cone", "tube", "polygon_plate", "hex_plate"])
        t = self.num(2, 15)
        params = {
            "plate": {"width": self.num(10, 80), "depth": self.num(10, 60), "thickness": t},
            "disc": {"radius": self.num(5, 40), "thickness": t},
            "ball": {"radius": self.num(3, 20)},
            "cone": {"bottom_radius": self.num(5, 30), "top_radius": self.num(0, 20), "height": self.num(5, 40)},
            "tube": {"outer_radius": self.num(8, 30), "inner_radius": self.num(1, 7), "height": self.num(5, 40)},
            "polygon_plate": {"sides": self.rng.randint(3, 8), "circumradius": self.num(5, 40), "thickness": t},
            "hex_plate": {"across_flats": self.num(8, 60), "thickness": t},
        }[op]
        self.add(op, params, [])

    def add(self, op, params, inputs):
        fid = self.fresh_id(op)
        return self.call("add", "POST", "/api/feature/add",
                         {"id": fid, "op": op, "params": params, "inputs": inputs}), fid

    def entities(self, span: float):
        """One closed profile: a circle or a rectangle inside a `span` box."""
        if self.rng.random() < 0.5:
            return [{"kind": "circle", "mode": "add", "x": 0, "y": 0,
                     "r": self.num(max(1.0, span * 0.05), max(1.5, span * 0.3))}]
        return [{"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "rotation": 0,
                 "w": self.num(max(2.0, span * 0.1), max(3.0, span * 0.6)),
                 "h": self.num(max(2.0, span * 0.1), max(3.0, span * 0.6))}]

    def move_base_sketch_extrude(self):
        resp, sid = self.add("sketch", {"plane": self.pick(["XY", "XZ", "YZ"]), "offset": 0,
                                        "entities": self.entities(40)}, [])
        if resp.get("error"):
            return
        self.add("extrude", {"amount": self.num(2, 30), "both": self.rng.random() < 0.2}, [sid])

    def move_face_sketch_extrude(self):
        solids = self.solids()
        if not solids:
            return self.move_base_sketch_extrude()
        body = self.pick(solids)
        faces = self.faces(body)
        if not faces:
            return self.move_modifier()
        face = self.pick(faces)
        span = min(face.get("extents") or [20, 20]) if face.get("extents") else 20
        params = {"face_center": face["center"], "face_normal": face["normal"],
                  "entities": self.entities(span), "offset": 0}
        resp, sid = self.add("sketch_on_face", params, [body])
        if resp.get("error"):
            return
        amount = self.num(1, 12)
        flip = self.rng.random() < 0.5         # into the body = a cut
        self.add("extrude", {"amount": amount, "flip": flip,
                             "through": flip and self.rng.random() < 0.3}, [sid])

    def move_modifier(self):
        solids = self.solids()
        if not solids:
            return self.move_add_creator()
        body = self.pick(solids)
        op = self.pick(["fillet", "chamfer", "shell", "mirror", "move", "rotate", "scale",
                        "polar_pattern", "linear_pattern", "hole", "extrude_face",
                        "with_center_hole", "with_bolt_circle"])
        rule = self.pick(["all", "top", "bottom", "vertical", "horizontal"])
        params = {
            "fillet": {"radius": self.num(0.3, 3), "edges": rule},
            "chamfer": {"length": self.num(0.3, 3), "edges": rule},
            "shell": {"thickness": self.num(0.8, 3), "open_face": self.pick(["top", "bottom", "none"])},
            "mirror": {"plane": self.pick(["XY", "XZ", "YZ", {"mid": "X"}, {"mid": "Y"}]),
                       "join": self.rng.random() < 0.5},
            "move": {"x": self.num(-20, 20), "y": self.num(-20, 20), "z": self.num(-10, 10)},
            "rotate": {"axis": self.pick(["X", "Y", "Z"]), "angle_deg": self.pick([30, 45, 90, 180]),
                       "pivot": self.pick(["center", None])},
            "scale": {"factor": self.pick([0.5, 0.8, 1.5, 2])},
            "polar_pattern": {"count": self.rng.randint(2, 6), "axis": self.pick(["X", "Y", "Z"]),
                              "angle": self.pick([360, 180, 90])},
            "linear_pattern": {"count": self.rng.randint(2, 4), "dx": self.num(0, 40),
                               "dy": self.num(0, 40), "dz": 0},
            "hole": {"face": self.pick(["top", "bottom"]), "at": [self.num(-5, 5), self.num(-5, 5)],
                     "diameter": self.num(1.5, 8), "depth": self.num(1, 10),
                     "through": self.rng.random() < 0.4},
            "with_center_hole": {"radius": self.num(1, 6)},
            "with_bolt_circle": {"count": self.rng.randint(3, 8), "bolt_radius": self.num(1, 3),
                                 "pitch_circle_dia": self.num(15, 50)},
        }.get(op)
        if op == "extrude_face":
            faces = self.faces(body)
            if not faces:
                return
            face = self.pick(faces)
            params = {"face_center": face["center"], "face_normal": face["normal"],
                      "amount": self.num(1, 10), "flip": self.rng.random() < 0.5}
        if params.get("pivot", 0) is None:
            del params["pivot"]
        self.add(op, params, [body])

    def move_combiner(self):
        solids = self.solids()
        if len(solids) < 2:
            return self.move_add_creator()
        a, b = self.rng.sample(solids, 2)
        self.add(self.pick(["fuse", "cut", "intersect"]), {}, [a, b])

    def move_edit(self):
        feats = [f for f in self.features() if self.doc.numeric_params(f.op) & set(f.params)]
        if not feats:
            return self.move_add_creator()
        f = self.pick(feats)
        param = self.pick(sorted(self.doc.numeric_params(f.op) & set(f.params)))
        cur = f.params[param]
        if not isinstance(cur, (int, float)) or isinstance(cur, bool):
            return
        roll = self.rng.random()
        if roll < 0.1:
            value = 0
        elif roll < 0.2:
            value = -abs(cur) or -1
        else:
            value = round(cur * self.pick([0.5, 0.8, 0.9, 1.1, 1.25, 2]), 3)
            if isinstance(cur, int):
                value = max(0, int(round(value)))
        before, n0 = self.data(), len(self.steps)
        resp = self.call("edit", "POST", "/api/edit",
                         {"feature_id": f.id, "param": param, "value": value})
        if resp.get("error") or before == self.data():
            return
        # one Undo takes back exactly one step
        self.call("undo", "POST", "/api/undo")
        if self.data() != before:
            raise Bug("undo-mismatch", f"undo after editing '{f.id}.{param}' did not restore the document",
                      self.steps[-1], resp, before=before, replay=self.steps[n0:])
        self.call("redo", "POST", "/api/redo")

    def move_undo_add(self):
        """Add something, then undo: the document must be exactly as before."""
        before = self.data()
        n0 = len(self.steps)
        self.move_add_creator() if self.rng.random() < 0.5 else self.move_modifier()
        added = [s for s in self.steps[n0:] if s["kind"] == "add" and s["status"] == 200]
        if not added:
            return
        for _ in added:
            self.call("undo", "POST", "/api/undo")
        if self.data() != before:
            raise Bug("undo-mismatch", f"undo after {len(added)} add step(s) did not restore the document",
                      self.steps[-1], None, before=before, replay=self.steps[n0:])

    def move_strike_restore(self):
        feats = self.features()
        if not feats:
            return self.move_add_creator()
        f = self.pick(feats)
        before, vols, n0 = self.data(), self.volumes(), len(self.steps)
        resp = self.call("strike", "POST", "/api/feature/strike", {"feature_id": f.id})
        if resp.get("error"):
            return
        resp = self.call("restore", "POST", "/api/feature/strike",
                         {"feature_id": f.id, "restore": True})
        if resp.get("error"):
            return
        if self.data() != before:
            raise Bug("strike-restore-mismatch",
                      f"strike + restore of '{f.id}' left a different document", self.steps[-1], resp,
                      before=before, replay=self.steps[n0:])
        if self.volumes() != vols:
            raise Bug("strike-restore-volume",
                      f"strike + restore of '{f.id}' changed a body volume: {vols} -> {self.volumes()}",
                      self.steps[-1], resp, before=before, replay=self.steps[n0:])

    def move_rollback(self):
        feats = self.features()
        if len(feats) < 2:
            return self.move_add_creator()
        f = self.pick(feats[:-1])
        before, vols, n0 = self.data(), self.volumes(), len(self.steps)
        self.call("rollback", "POST", "/api/rollback", {"feature_id": f.id})
        self.call("plan", "POST", "/api/tool/plan", {"tool": "extrude", "body_id": f.id}, mutating=False)
        self.call("rollback", "POST", "/api/rollback", {"feature_id": None})
        if self.data() != before:
            raise Bug("rollback-mismatch", f"rollback to '{f.id}' and release changed the document",
                      self.steps[-1], None, before=before, replay=self.steps[n0:])
        if self.volumes() != vols:
            raise Bug("rollback-volume", f"rollback to '{f.id}' and release changed a body: {vols} -> {self.volumes()}",
                      self.steps[-1], None, before=before, replay=self.steps[n0:])

    def move_remove(self):
        feats = self.features()
        if len(feats) < 2:
            return self.move_add_creator()
        f = self.pick(feats)
        mode = self.pick(["auto", "auto", "cascade", "strict"])
        self.call("remove-plan", "POST", "/api/feature/remove",
                  {"feature_id": f.id, "mode": mode, "dry_run": True}, mutating=True)
        self.call("remove", "POST", "/api/feature/remove", {"feature_id": f.id, "mode": mode})

    def move_plan(self):
        tool = self.pick(PLAN_TOOLS)
        body = {"tool": tool}
        solids = self.solids()
        sketches = [f.id for f in self.features() if f.op in ("sketch", "sketch_on_face")]
        roll = self.rng.random()
        if tool == "sketch":
            body.update(plane=self.pick(["XY", "XZ", "YZ"]), offset=self.num(-10, 10))
        elif sketches and roll < 0.4:
            body["sketch_id"] = self.pick(sketches)
        elif solids:
            b = self.pick(solids)
            body["body_id"] = b
            faces = self.faces(b)
            if faces and roll < 0.8:
                face = self.pick(faces)
                body.update(face_center=face["center"], face_normal=face["normal"])
        else:
            feats = self.features()
            if feats:
                body["feature_id"] = self.pick(feats).id
        self.call("plan", "POST", "/api/tool/plan", body, mutating=False)

    def move_tabs(self):
        before, n0 = self.data(), len(self.steps)
        active = self.studio.STATE["active"]
        r = self.call("tab-new", "POST", "/api/new", {"name": "journey-scratch"})
        tid = r.get("active_tab")
        self.move_add_creator()
        self.call("tab-switch", "POST", "/api/tabs/switch", {"id": active}, mutating=False)
        if self.data() != before:
            raise Bug("tab-leak", "switching to a new tab and back changed the first tab's document",
                      self.steps[-1], None, before=before, replay=self.steps[n0:])
        if tid:
            self.call("tab-close", "POST", "/api/tabs/close", {"id": tid}, mutating=False)
        self.call("tab-switch", "POST", "/api/tabs/switch", {"id": active}, mutating=False)

    def move_misc(self):
        feats = self.features()
        roll = self.rng.random()
        if roll < 0.3:
            self.call("spec", "POST", "/api/spec",
                      {"spec": {"n_solids": max(1, len(self.solids())), "tol": 0.5}})
        elif roll < 0.6 and feats:
            f = self.pick(feats)
            new = f.id + "_r"
            r = self.call("rename", "POST", "/api/feature/rename", {"feature_id": f.id, "name": new})
            if not r.get("error"):
                self.call("rename", "POST", "/api/feature/rename", {"feature_id": new, "name": f.id})
        elif feats:
            f = self.pick(feats)
            self.call("suppress", "POST", "/api/feature/suppress", {"feature_id": f.id, "suppressed": True})
            self.call("suppress", "POST", "/api/feature/suppress", {"feature_id": f.id, "suppressed": False})
        self.call("doc", "GET", "/api/doc", mutating=False)

    def check_roundtrip(self):
        from document import Document
        data = self.data()
        again = Document.from_data(data).to_data()
        if again != data:
            # the DOCUMENT is the repro here, not a request: replay opens it
            # and asks the same question again
            raise Bug("roundtrip", "to_data -> from_data -> to_data is not the identity",
                      self.steps[-1] if self.steps else None, None,
                      before=data, replay=[])

    MOVES = [
        ("creator", 2, move_add_creator),
        ("base-sketch", 2, move_base_sketch_extrude),
        ("face-sketch", 4, move_face_sketch_extrude),
        ("modifier", 5, move_modifier),
        ("combiner", 2, move_combiner),
        ("edit", 4, move_edit),
        ("undo-add", 2, move_undo_add),
        ("strike", 2, move_strike_restore),
        ("rollback", 1, move_rollback),
        ("remove", 1, move_remove),
        ("plan", 3, move_plan),
        ("tabs", 1, move_tabs),
        ("misc", 1, move_misc),
    ]

    def run(self) -> dict:
        """-> {"result": "clean" | "bug", "bug": Bug | None, "requests": n, "notes": [...]}"""
        doc = load_document(self.path)
        self.studio._new_tab(doc, source=f"journey:{self.name}")
        self.studio._rebuild_and_mesh()
        self.say(f"opened: {len(doc.features)} features, {len(self.solids())} bodies")
        bug = None
        try:
            rec = {"n": 0, "kind": "open", "op": None}
            self.check_bodies(rec, None)
            self.check_roundtrip()
            names, weights, fns = zip(*self.MOVES)
            for i in range(self.n_steps):
                fn = self.rng.choices(fns, weights=weights)[0]
                fn(self)
                if i % 10 == 9:
                    self.check_roundtrip()
        except Bug as b:
            bug = b
        return {"result": "bug" if bug else "clean", "bug": bug,
                "requests": len(self.steps), "notes": self.notes}


# --------------------------------------------------------------------------
# Bug folders
# --------------------------------------------------------------------------

# The oracles that assert a SEQUENCE is the identity: replaying them means
# sending the whole recorded sequence and asking the same question again.
_IDENTITY_BUGS = {"strike-restore-mismatch", "strike-restore-volume",
                  "rollback-mismatch", "rollback-volume", "undo-mismatch"}
# ... and the ones a fresh server cannot re-ask: tab ids are minted per run,
# and a process that died left no document behind.
_REPLAY_BLIND = {"tab-leak", "process-died"}


def existing_signatures(bugs_dir: Path = BUGS) -> dict[str, str]:
    out = {}
    for j in sorted(bugs_dir.glob("*/journey.json")):
        try:
            sig = json.loads(j.read_text(encoding="utf-8")).get("signature")
        except (ValueError, OSError):
            continue
        if sig:
            out.setdefault(sig, j.parent.name)
    return out


def write_bug(journey: Journey, bug: Bug, before: dict | None, after: dict | None,
              bugs_dir: Path = BUGS, stamp: str | None = None) -> tuple[Path | None, str | None]:
    """Save the repro. -> (folder, None) or (None, name of the folder that
    already holds this signature)."""
    sig = signature(bug.kind, (bug.request or {}).get("op"), bug.detail)
    dup = existing_signatures(bugs_dir).get(sig)
    if dup:
        return None, dup
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    n = (bug.request or {}).get("n", len(journey.steps))
    d = bugs_dir / f"{stamp}-{_slug(journey.name)}-s{journey.seed}-step{n}"
    d.mkdir(parents=True, exist_ok=True)
    record = {"signature": sig, "kind": bug.kind, "detail": bug.detail,
              "design": journey.name, "file": str(journey.path) if journey.path else None,
              "seed": journey.seed, "failing_step": n, "request": bug.request,
              # what --replay resends against before.tcad.json, and whether the
              # question it asks is "did this sequence leave the document alone"
              "replay": bug.replay, "identity": bug.kind in _IDENTITY_BUGS,
              "response_error": (bug.response or {}).get("error") if bug.response else None,
              "steps": journey.steps, "notes": journey.notes,
              "found": time.strftime("%Y-%m-%d %H:%M:%S")}
    (d / "journey.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    if before is not None:
        (d / "before.tcad.json").write_text(json.dumps(before, indent=1), encoding="utf-8")
    if after is not None:
        (d / "after.tcad.json").write_text(json.dumps(after, indent=1), encoding="utf-8")
    seq = [s for s in bug.replay if isinstance(s, dict) and s.get("url")]
    head = ("## The step that broke it" if len(seq) <= 1 else
            f"## The {len(seq)} steps that broke it, in order")
    lines = [f"# {bug.kind}: {journey.name}, seed {journey.seed}, step {n}", "",
             bug.detail, "", head, ""]
    for s in (seq or [bug.request or {}]):
        lines += [f"`{s.get('method', '?')} {s.get('url', '?')}`", "",
                  "```json", json.dumps(s.get("body"), indent=1), "```", ""]
    if bug.response and bug.response.get("error"):
        lines += ["The server answered:", "", f"> {bug.response['error']}", ""]
    what = ("sends the step above" if len(seq) <= 1 else
            f"sends those {len(seq)} steps in order")
    asks = (" and then asks the same question this finding asks: did that "
            "sequence leave the document exactly as it was?"
            if bug.kind in _IDENTITY_BUGS else " and runs the same checks.")
    lines += ["## Reproduce", "",
              "`before.tcad.json` is the design this finding was measured "
              "against; `after.tcad.json` (if present) is what it became.", "",
              f"    python tests/journeys.py --replay bugs/{d.name}", "",
              f"That opens `before.tcad.json` in a fresh in-process server, {what}"
              + asks + " The whole journey is in `journey.json` (`steps`), in order.", ""]
    if journey.notes:
        lines += ["## Notes (not bugs)", ""] + [f"- {t}" for t in journey.notes] + [""]
    (d / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return d, None


def append_log(line: str, bugs_dir: Path = BUGS):
    bugs_dir.mkdir(parents=True, exist_ok=True)
    with open(bugs_dir / LOG_NAME, "a", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")


# --------------------------------------------------------------------------
# Child: one journey in this process
# --------------------------------------------------------------------------

def run_one(name: str, path: Path | None, seed: int, steps: int, log_path: Path | None,
            bugs_dir: Path = BUGS, verbose: bool = True, client=None, studio=None) -> dict:
    """Play one journey and file its finding, if any. -> summary dict with
    "exit" set to one of EXIT_CLEAN / EXIT_BUG / EXIT_DUP."""
    j = Journey(name, path, seed, steps, log_path=log_path, verbose=verbose,
                client=client, studio=studio)
    before = None
    # the document before each request is what a repro needs; keep the last
    orig_call = j.call

    def remembering_call(kind, method, url, body=None, mutating=True):
        nonlocal before
        if mutating:
            before = j.data()
        return orig_call(kind, method, url, body, mutating)
    j.call = remembering_call
    out = j.run()
    out["design"], out["seed"] = name, seed
    if out["bug"] is None:
        out["exit"] = EXIT_CLEAN
        append_log(f"clean  {name} s{seed} {out['requests']} requests"
                   + (f"  notes: {'; '.join(out['notes'])}" if out["notes"] else ""), bugs_dir)
        return out
    bug = out["bug"]
    try:
        after = j.data()
    except Exception:                    # noqa: BLE001 — the doc may be broken; that IS the bug
        after = None
    # a move that judged a PAIR of requests carries its own baseline; for a
    # single request the one remembered above is that baseline
    folder, dup = write_bug(j, bug, bug.before if bug.before is not None else before,
                            after, bugs_dir)
    if folder:
        out["exit"], out["folder"] = EXIT_BUG, str(folder)
        append_log(f"BUG    {name} s{seed} step {(bug.request or {}).get('n')}: {bug.kind} -> {folder.name}", bugs_dir)
    else:
        out["exit"], out["folder"] = EXIT_DUP, dup
        append_log(f"dup    {name} s{seed}: {bug.kind} (already in {dup})", bugs_dir)
    return out


def replay(folder: Path, verbose: bool = True) -> dict:
    """Open a bug folder's before-document and send its failing request again."""
    folder = Path(folder)
    rec = json.loads((folder / "journey.json").read_text(encoding="utf-8")) \
        if (folder / "journey.json").exists() else {}
    src = next((folder / n for n in ("before.tcad.json", "doc.tcad.json",
                                     "after.tcad.json")
                if (folder / n).exists()), None)
    if src is None:
        # a finding made by the OPENING check has no `before` — the document it
        # was measured on is the one the folder calls after.tcad.json
        raise SystemExit(f"{folder} holds no before/doc/after.tcad.json")
    j = Journey(rec.get("design") or folder.name, src, rec.get("seed", 0), 0, verbose=verbose)
    doc = load_document(src)
    j.studio._new_tab(doc, source=f"replay:{folder.name}")
    j.studio._rebuild_and_mesh()
    reds = [f"{f.id} ({f.op}): {'; '.join(f.problems)}" for f in doc.features
            if f.status != "ok" and not f.suppressed]
    print(f"opened {src.name}: {len(doc.features)} features, {len(j.solids())} bodies"
          + (f", red: {reds}" if reds else ""), flush=True)
    steps = rec.get("replay")
    if steps is None:                        # a folder written before P5b's fix
        req = rec.get("request") or {}
        steps = [req] if req.get("url") else []
    steps = [s for s in steps if isinstance(s, dict) and s.get("url")]
    if not steps:
        try:
            j.check_bodies({"n": 0, "kind": "open"}, None)
            j.check_roundtrip()
            print("no failing request recorded; the opened design passes the checks")
            return {"result": "clean"}
        except Bug as b:
            print(f"STILL THERE: {b}")
            return {"result": "bug", "bug": b}
    base, vols = j.data(), j.volumes()
    try:
        for s in steps:
            j.call(s.get("kind", "replay"), s.get("method", "POST"), s["url"],
                   s.get("body"), mutating=s.get("method", "POST") != "GET")
    except Bug as b:
        print(f"STILL THERE: {b}")
        return {"result": "bug", "bug": b}
    # The pair oracles all assert one thing: the sequence left the document
    # exactly as it was. Sending the steps is not enough — the question has to
    # be asked again, or a live bug replays as "passes now" (P5b review).
    if rec.get("identity"):
        if j.data() != base or j.volumes() != vols:
            b = Bug(rec.get("kind") or "identity", "the replayed sequence did not "
                    "leave the document as it was", steps[-1], None, before=base,
                    replay=steps)
            print(f"STILL THERE: {b}")
            return {"result": "bug", "bug": b}
    elif rec.get("kind") in _REPLAY_BLIND:
        print(f"a '{rec.get('kind')}' cannot be re-asked in a fresh server "
              "(tab ids are minted per run) — read `steps` in journey.json")
        return {"result": "clean"}
    print("the step passes now (fixed, or not deterministic)")
    return {"result": "clean"}


# --------------------------------------------------------------------------
# Parent: the overnight loop
# --------------------------------------------------------------------------

# The machine giving up is not the product failing. Measured 2026-09-12: a
# 20-journey run beside a full pytest run put the box out of memory, and two
# children died — one with a STACK OVERFLOW (0xC00000FD) mid-`ball`, one with
# a MemoryError importing sklearn through build123d — and both were filed as
# "the server process died", with the console evidence kept nowhere.
_MACHINE_GAVE_UP = re.compile(
    r"MemoryError|std::bad_alloc|Cannot allocate memory|"
    r"OpenBLAS error: Memory allocation|unable to allocate")


def machine_gave_up(child_output: str) -> bool:
    """True when the child died because the BOX ran out, not the product."""
    return bool(child_output) and bool(_MACHINE_GAVE_UP.search(child_output))


def write_crash(name: str, seed: int, code: int, steps_rec: dict, err: str,
                bugs_dir: Path, stamp: str | None = None,
                verdict_on: str | None = None,
                cap_hit_gb: float | None = None,
                stalled_s: float | None = None) -> tuple[Path | None, str | None]:
    """File a process-died folder. -> (folder, None), (None, dup name), or
    (None, None) when the machine, not the product, gave up.

    `err` is what the folder keeps (a tail); `verdict_on` is what the verdict
    is read from (the whole of it), so truncating the display can never turn
    the box's failure back into the product's. `cap_hit_gb` set means the
    child ran into ITS OWN memory ceiling (JobCap): then an out-of-memory
    death is the product eating the box, and is filed as one."""
    ran_out = machine_gave_up(verdict_on if verdict_on is not None else err)
    if ran_out and cap_hit_gb is None:
        return None, None
    last = (steps_rec.get("steps") or [{}])[-1]
    hexcode = f"0x{code & 0xFFFFFFFF:08X}"
    if stalled_s is not None:
        what = f"longer than {stalled_s:g} s without answering (the runner killed it)"
    elif cap_hit_gb is not None:
        what = f"more than {cap_hit_gb:g} GB of memory (the child's ceiling)"
    elif (code & 0xFFFFFFFF) == 0xC0000005:
        what = "OpenCASCADE access violation (segfault)"
    else:
        what = f"exit code {code}"
    kind = ("hang" if stalled_s is not None else
            "memory" if cap_hit_gb is not None else "process-died")
    # a hang and a memory death are about the REQUEST, not the exit code the
    # OS happened to give the corpse
    sig = signature(kind, last.get("op"),
                    f"{hexcode} {last.get('kind')} {last.get('op')}"
                    if cap_hit_gb is None and stalled_s is None
                    else f"{last.get('kind')} {last.get('op')}")
    dup = existing_signatures(bugs_dir).get(sig)
    if dup:
        return None, dup
    d = bugs_dir / f"{stamp or time.strftime('%Y%m%d-%H%M%S')}-{_slug(name)}-s{seed}-crash"
    d.mkdir(parents=True, exist_ok=True)
    steps_rec.update(signature=sig, kind=kind, detail=f"{what} during step {last.get('n')}",
                     failing_step=last.get("n"), request=last, replay=[], identity=False,
                     found=time.strftime("%Y-%m-%d %H:%M:%S"))
    (d / "journey.json").write_text(json.dumps(steps_rec, indent=1, default=str), encoding="utf-8")
    lines = [f"# {kind}: {name}, seed {seed}, step {last.get('n')}", "",
             (f"The server process took {what} while handling:"
              if kind in ("memory", "hang") else
              f"The server process died with {what} ({hexcode}) while handling:"), "",
             f"`{last.get('method', '?')} {last.get('url', '?')}`", "",
             "```json", json.dumps(last.get("body"), indent=1), "```", ""]
    if err:
        (d / "child-output.txt").write_text(err, encoding="utf-8")
        lines += ["## What the child said before it went", "",
                  "```", err[-1500:].strip(), "```", "",
                  "(the whole tail is in `child-output.txt`)", ""]
    # a live design needs --library or the runner says "no such design"
    # (the first crash folder's recipe failed exactly that way, 2026-09-12)
    src = steps_rec.get("file")
    lib = "" if not src or Path(str(src)).parent.resolve() == FIXTURES.resolve() else "--library "
    lines += ["## Reproduce", "",
              f"    python tests/journeys.py {lib}--designs {name} --seed {seed} "
              f"--steps {len(steps_rec.get('steps') or [])} --journeys 1", "",
              "There is no before.tcad.json: the process was gone before it could be "
              "written. `journey.json` holds every step from the start of the design, "
              "in order; replaying them (`steps`) rebuilds the state. In the app this "
              "is what the crash supervisor (supervise.py) recovers from.", ""]
    (d / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return d, None


def steps_taken(log: str) -> int:
    """How many requests the child has written to its step log (-1 = unreadable
    right now, which a half-written file is; the caller treats it as no news)."""
    try:
        return len(json.loads(Path(log).read_text(encoding="utf-8")).get("steps") or [])
    except Exception:                        # noqa: BLE001 — mid-write is normal
        return -1


def wait_or_kill_a_stalled_child(proc, log: str, stall_s: float) -> bool:
    """Wait for the child, killing it if it stops taking steps. -> was it killed.

    `Journey._flush_log` writes the log BEFORE each request, so the count rising
    is the child making progress and the last entry is the request it is in.

    The wait is counted on the awake clock: a child that took no step because
    the LID WAS SHUT has not stalled, and killing it would file the sleep as
    the product hanging (see `awake_s`)."""
    if not stall_s or stall_s <= 0:
        proc.wait()
        return False
    seen, since = steps_taken(log), awake_s()
    while proc.poll() is None:
        time.sleep(2.0)
        now = steps_taken(log)
        if now != seen and now >= 0:
            seen, since = now, awake_s()
        elif awake_s() - since > stall_s:
            proc.kill()
            proc.wait()
            return True
    return False


def spawn(name: str, path: Path | None, seed: int, steps: int, bugs_dir: Path,
          mem_gb: float = MEM_CAP_GB, stall_s: float = STALL_KILL_S) -> dict:
    """One journey in a child process, so a kernel crash is a finding — and
    under a memory ceiling (`mem_gb`) and a stall ceiling (`stall_s`), so a
    runaway op is one too whether it ends in memory, in time, or never."""
    bugs_dir.mkdir(parents=True, exist_ok=True)
    fd, log = tempfile.mkstemp(prefix=f"journey-{_slug(name)}-s{seed}-", suffix=".json")
    os.close(fd)
    cmd = [sys.executable, str(Path(__file__).resolve()), "--one", name, "--seed", str(seed),
           "--steps", str(steps), "--log", log, "--bugs-dir", str(bugs_dir)]
    if path is not None:
        cmd += ["--file", str(path)]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "TEXTCAD_NO_BROWSER": "1"}
    t0, awake0 = time.perf_counter(), awake_s()
    # stdout stays live (the per-step lines are what an overnight run is
    # watched by); stderr is kept, because that is where a traceback and a
    # MemoryError go and a crash folder needs to say WHY the child went
    cap = JobCap(mem_gb)
    proc = cap.start(cmd, env=env, cwd=str(ROOT), stderr=subprocess.PIPE,
                     text=True, errors="replace")
    # stderr is drained on a thread so the watchdog can watch the step log:
    # communicate() would block until the child ends, which is the one case
    # a stall never reaches
    drained: dict = {}
    reader = threading.Thread(
        target=lambda: drained.update(err=proc.communicate()[1]), daemon=True)
    reader.start()
    stalled = wait_or_kill_a_stalled_child(proc, log, stall_s)
    reader.join(30)
    full_err = drained.get('err')
    secs = round(awake_elapsed(t0, awake0)[0])
    code = proc.returncode
    # the WHOLE stderr decides whether the machine gave up; only the tail is
    # kept for the folder, and a display cut must not change the verdict
    full_err = full_err or ""
    err = full_err[-8000:]
    out = {"design": name, "seed": seed, "exit": code, "secs": secs,
           "peak_gb": round(cap.peak_gb(), 2)}
    if code in (EXIT_CLEAN, EXIT_BUG, EXIT_DUP) and not stalled:
        Path(log).unlink(missing_ok=True)
        return out
    if err:
        print(err, end="" if err.endswith("\n") else "\n", flush=True)
    if code == EXIT_BROKEN:
        # the RUNNER (or an import) raised: our fault, printed above — not a
        # finding about the product, so no folder
        Path(log).unlink(missing_ok=True)
        append_log(f"broken {name} s{seed}: the runner itself raised (see the console)", bugs_dir)
        return out
    # the child died: exit code from the OS, not from us
    try:
        steps_rec = json.loads(Path(log).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        steps_rec = {"steps": []}
    Path(log).unlink(missing_ok=True)
    d, dup = write_crash(name, seed, code, steps_rec, err, bugs_dir,
                         verdict_on=full_err, cap_hit_gb=cap.gb if cap.hit else None,
                         stalled_s=stall_s if stalled else None)
    hexcode = f"0x{code & 0xFFFFFFFF:08X}"
    if dup:
        append_log(f"dup    {name} s{seed}: process died {hexcode} (already in {dup})", bugs_dir)
        out["folder"] = dup
    elif d is None:
        out["exit"] = EXIT_BROKEN          # the box gave up, not the product
        append_log(f"broken {name} s{seed}: the machine ran out ({hexcode}) — "
                   "not a finding, run fewer things at once", bugs_dir)
    else:
        last = (steps_rec.get("steps") or [{}])[-1]
        what = (f"answered nothing for {stall_s:g} s" if stalled else
                f"ate the {cap.gb:g} GB ceiling" if cap.hit else hexcode)
        append_log(f"CRASH  {name} s{seed} step {last.get('n')}: {what} -> {d.name}", bugs_dir)
        out["folder"] = str(d)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--library", action="store_true", help="also play the live designs/ (read-only)")
    p.add_argument("--designs", help="comma-separated names to play (default: all)")
    p.add_argument("--seed", type=int, default=None, help="first seed (default: from the clock)")
    p.add_argument("--steps", type=int, default=30, help="moves per journey")
    p.add_argument("--journeys", type=int, default=0, help="how many journeys (0 = until --hours / Ctrl+C)")
    p.add_argument("--hours", type=float, default=0, help="stop starting new journeys after this long")
    p.add_argument("--in-process", action="store_true", help="no child processes (a crash ends the run)")
    p.add_argument("--mem-gb", type=float, default=MEM_CAP_GB,
                   help=f"memory ceiling per child, GB (default {MEM_CAP_GB:g}; 0 = none)")
    p.add_argument("--stall-secs", type=float, default=STALL_KILL_S,
                   help=f"kill a child that takes no new step for this long "
                        f"(default {STALL_KILL_S:g}; 0 = never)")
    p.add_argument("--bugs-dir", default=str(BUGS))
    p.add_argument("--replay", help="a bugs/<folder>: open its before-document and resend the failing step")
    # child mode
    p.add_argument("--one", help=argparse.SUPPRESS)
    p.add_argument("--file", help=argparse.SUPPRESS)
    p.add_argument("--log", help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    bugs_dir = Path(a.bugs_dir)

    if a.replay:
        return 0 if replay(Path(a.replay))["result"] == "clean" else EXIT_BUG

    if a.one:
        path = Path(a.file) if a.file else None
        try:
            out = run_one(a.one, path, a.seed or 0, a.steps, Path(a.log) if a.log else None, bugs_dir)
        except Exception:                # noqa: BLE001 — the runner itself broke: say so loudly
            traceback.print_exc()
            return EXIT_BROKEN
        return out["exit"]

    srcs = sources(a.library, a.designs.split(",") if a.designs else None)
    seed = a.seed if a.seed is not None else int(time.time()) % 100_000
    deadline = time.time() + a.hours * 3600 if a.hours else None
    cap_note = (f"{a.mem_gb:g} GB per child" if a.mem_gb and JobCap.available
                else "NO memory ceiling" + ("" if JobCap.available else " (not Windows)"))
    cap_note += (f"; killed after {a.stall_secs:g} s with no new step"
                 if a.stall_secs else "; NO stall ceiling")
    print(f"journeys over {', '.join(n for n, _ in srcs)}; {a.steps} steps each; first seed {seed}; "
          f"{cap_note}; findings -> {bugs_dir}", flush=True)
    counts = {"clean": 0, "bug": 0, "dup": 0, "crash": 0, "broken": 0}
    n = 0
    try:
        while True:
            if a.journeys and n >= a.journeys:
                break
            if deadline and time.time() >= deadline:
                break
            name, path = srcs[n % len(srcs)]
            print(f"-- journey {n + 1}: {name} seed {seed + n}", flush=True)
            if a.in_process:
                out = run_one(name, path, seed + n, a.steps, None, bugs_dir)
                code = out["exit"]
            else:
                out = spawn(name, path, seed + n, a.steps, bugs_dir, a.mem_gb,
                            a.stall_secs)
                code = out["exit"]
            key = {EXIT_CLEAN: "clean", EXIT_BUG: "bug", EXIT_DUP: "dup", EXIT_BROKEN: "broken"}.get(code, "crash")
            counts[key] += 1
            print(f"   {key}" + (f"  -> {out['folder']}" if out.get("folder") else ""), flush=True)
            n += 1
    except KeyboardInterrupt:
        print("stopped", flush=True)
    print(f"{n} journeys: {counts}", flush=True)
    append_log(f"run over: {n} journeys {counts}", bugs_dir)
    return 0 if counts["bug"] == counts["crash"] == counts["broken"] == 0 else EXIT_BUG


if __name__ == "__main__":
    sys.exit(main())
