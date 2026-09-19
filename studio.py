"""
studio.py — TextCAD Studio: the local web app (API layer).

Run:  python studio.py   ->  opens http://127.0.0.1:8123 in your browser.

The UI lives in static/ (index.html + css/ + js/ modules). This file is the
HTTP API only; the CAD brains live in the core modules (document, blocks,
sketch, inspector, author, meanline, samples).

MULTI-DOCUMENT: the server holds many open designs at once — one per UI tab.
STATE["docs"] maps tab-id -> {doc, ok, rebuild_ms, history}; STATE["active"]
names the tab every /api call operates on. New / Open / Examples / AI-create
all open a NEW tab, so the previous design stays open to switch back to.

Every edit — spoken or clicked — flows through the SAME path:
Document.edit() -> deterministic rebuild through verified blocks -> per-node
health + spec verification. The LLM never regenerates a design during an edit.
"""

from __future__ import annotations
import os
import sys

# `python studio.py` runs the SUPERVISOR (supervise.py -- light, no kernel
# import) and the server itself as its child. The geometry kernel can segfault
# (probes/fillet_segfault_probe.py), and a segfault is not an exception: the
# process is simply gone. The supervisor relaunches it with the tabs as of the
# last completed request, so a crash costs one step, not the session. Tests
# and dev.py IMPORT this module, so they never come through here.
if __name__ == "__main__" and os.environ.get("TEXTCAD_SERVER_CHILD") != "1":
    from supervise import main as _supervise
    raise SystemExit(_supervise())

import base64
import contextlib
import contextvars
import itertools
import json
import math
import re
import threading
import time
from dataclasses import asdict
from pathlib import Path

import supervise                       # session/in-flight file names, shared

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import cv2
import numpy as np
import build123d as b3d
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.TopAbs import TopAbs_Orientation, TopAbs_ShapeEnum
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

import author
import blocks
import imgtrace
import inspector
import kernelguard
import measure as measurelib
import sketch as sketchlib
import toolplan
import sketch_trim as trimlib
import sketch_corner as cornerlib
import sketch_snap as snaplib
from document import Document
from history import History, HistoryError, diff_snapshots, content_hash
import provenance
from samples import SAMPLES, sample_flange, sample_impeller, sample_compressor  # noqa: F401 (re-export for tests)

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
MESH_PATH = ROOT / "_studio_mesh.stl"
# how much a CHAT "delete X" may take before it must be done deliberately in
# the tree instead (a pocket group is 3 features; a whole design is not)
CHAT_DELETE_LIMIT = 6
DESIGNS = ROOT / "designs"
DESIGNS.mkdir(exist_ok=True)
# The bug inbox (LAUNCH-PLAN.md P5b): the Studio bug button and
# tests/journeys.py both file a repro folder here; the chat that fixes one
# deletes its folder.
BUGS = ROOT / "bugs"

app = FastAPI(title="TextCAD Studio")


@app.middleware("http")
async def _no_stale_assets(request, call_next):
    """Serve the UI (index.html + every JS/CSS module) with no-cache so the
    browser NEVER runs a stale mix — a fresh main.js importing cached old
    modules was booting the app half-dead. Local dev app: correctness over
    cache. This removes the need for ?v= cache-busters entirely."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


@app.middleware("http")
async def _never_die(request, call_next):
    """Turn any unhandled endpoint exception into a JSON error.

    An exception escaping an endpoint gives a bare 500 whose body the UI cannot
    read, so the app looks dead even though the server is fine -- and OCP's
    errors derive from Exception, not RuntimeError, so narrow `except` barriers
    elsewhere do not catch them. The rule this project runs on is that a
    failure must be reported, never silent and never fatal.
    """
    try:
        return await call_next(request)
    except Exception as e:                  # noqa: BLE001 - deliberate barrier
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=200, content={
            "error": f"{type(e).__name__}: {e}",
            "where": request.url.path,
            "note": "The server is still running; nothing was changed. "
                    "Undo (Ctrl+Z) if the design looks wrong.",
        })


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ---------------------------------------------------------------------------
# Multi-document state: one entry per open tab
# ---------------------------------------------------------------------------

STATE: dict = {"docs": {}, "active": None, "seq": 0}
MAX_HISTORY = 25
MAX_TABS = 12

# ONE TAB PER REQUEST. STATE["active"] is moved from OTHER THREADS — the MCP
# doorbell posts /api/open/<slug>?external=1 and takes it, a second browser
# window switches tabs — and FastAPI runs every sync endpoint in the
# threadpool, so those moves land BETWEEN two reads inside one request.
# Section 12 round three measured that on /api/export (one design's solid
# written into another design's .step) and on /api/save, and bound those two
# shut by hand. Every other write route has the same seam and reads the tab
# three to six times: _snapshot(), _doc(), _hand_edit(), _rebuild_and_mesh(),
# _doc_json(). Measured 2026-09-16 with a REAL race, nothing patched inside
# studio (probes/section12_round4_probe.py): a traced logo left the design it
# was drawn for and landed in the library design the doorbell had just
# opened — 106 ms of tracing between the snapshot and the add — with the undo
# entry on the OTHER tab, so Ctrl+Z could not take it back.
#
# So a request resolves "which tab am I addressed to" ONCE and every later
# read in that request gets the same answer. The middleware ARMS this
# (value "") and the first _active_tid() resolves it; a context var is what
# makes it per-request — FastAPI's threadpool runs each sync endpoint in a
# COPY of the request's context, measured in
# probes/section12_round4_ctxvar_probe.py. Unarmed (None) means "not in a
# request" — startup and the chat job thread — and behaves exactly as before,
# which matters: a .set() in the MAIN context would pin every later request
# to one tab for the life of the process (also measured).
_ARMED = ""
_REQ_TAB: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "textcad_request_tab", default=None)

# The browser does not send this yet, and the server must not start requiring
# it (every existing client, the MCP included, sends nothing). When it IS
# present and names an OPEN tab, that is the tab the request is addressed to:
# the user clicked in the tab they can see, not in whichever tab a doorbell
# made active a moment ago. A header naming a tab that is no longer open is
# ignored rather than refused — a browser one poll behind is not an error, and
# falling back to the active tab is exactly what happens today.
TAB_HEADER = "x-textcad-tab"


def _addressed_tab(request) -> str | None:
    """The OPEN tab a request names, or None. ONE rule, asked in one place.

    Both middlewares below read this header and they must never answer it
    differently. Round four gave the pin the "must be an open tab" rule and
    left the one-writer guard taking the header as given, and round five
    measured what that gap costs: a page one poll behind — or one that
    outlived a restart, where tab ids start again at t1 — named a tab that is
    not open, the guard asked "is the AI building in t7?" (no), let the write
    through, and the pin then fell back to the ACTIVE tab, which is the tab
    the AI was building in. The write landed there, unrefused."""
    want = request.headers.get(TAB_HEADER)
    return want if want and want in STATE["docs"] else None

# THE DOORBELL'S ONE-SHOT MARKER. A design can arrive from OUTSIDE the browser
# — an AI over MCP posts /api/open/<slug>?external=1 — and the page announces
# it once. Whether something arrived is the SERVER's fact (R1): the browser
# used to infer it from the active tab having changed since the last poll, so
# every page load replayed "X just arrived — loaded it" and reset the view
# long after the design landed, sometimes out from under an open dialog
# (BACKLOG, seen 2026-09-01). The marker is consumed by the first page that
# shows it (POST /api/arrival/ack) and never again, and it lives in memory
# only — a restarted server has no arrivals to replay either.
ARRIVAL: dict | None = None
ARRIVAL_TTL = 600.0     # nobody came to see it for ten minutes: no longer news


def _note_arrival(tid: str, name: str, file: str) -> None:
    """A design arrived from outside the browser: one banner is owed."""
    global ARRIVAL
    ARRIVAL = {"tab": tid, "name": name, "file": file, "at": time.time()}


def _arrival_json() -> dict | None:
    """The arrival still owed a banner, or None. An old one is dropped here
    rather than in the browser, so "is this still news?" stays one rule in one
    place: a page opened hours later must not be told a design JUST arrived."""
    global ARRIVAL
    if ARRIVAL and time.time() - ARRIVAL["at"] > ARRIVAL_TTL:
        ARRIVAL = None
    return ARRIVAL


def _new_tab(doc: Document, source: str | None = None,
             activate: bool = True) -> str:
    """Open a document in a new tab and make it active.

    `source` records WHERE the design came from ("file:esp32-remote",
    "sample:flange") so a later open of the same thing can reuse this tab
    instead of cloning it. Keyed on origin rather than doc.name on purpose:
    two designs can carry the same name, and renaming one must not orphan
    its tab."""
    STATE["seq"] += 1
    tid = f"t{STATE['seq']}"
    STATE["docs"][tid] = {"doc": doc, "ok": False, "rebuild_ms": None,
                          "history": [], "redo": [], "source": source,
                          "hand_edits": 0, "pending": [],
                          # what the doc looked like at the LAST minted version
                          # (or at creation) — the baseline for "dirty"
                          "clean_hash": content_hash(doc.to_data()),
                          "dirty": False}
    if activate:
        _activate(tid)
    return tid


def _find_tab(source: str) -> str | None:
    """The tab already holding this design, or None."""
    for tid, e in STATE["docs"].items():
        if e.get("source") == source:
            return tid
    return None


def _file_owner(slug: str) -> str | None:
    """The tab already bound to designs/<slug>.tcad.json, or None.

    Case-INSENSITIVE, unlike `_find_tab`: this filesystem is, so
    "file:Cam-Cover-Plaque" and "file:cam-cover-plaque" are one file and must
    never end up owned by two tabs (fix-pass review, 2026-09-10)."""
    want = f"file:{slug}".lower()
    for tid, e in STATE["docs"].items():
        if (e.get("source") or "").lower() == want:
            return tid
    return None


def _active_tid() -> str:
    """The tab THIS REQUEST is addressed to — resolved once, then held.

    Inside a request (the middleware armed it) the first call pins the answer
    and every later read returns the same tab, whatever another thread does to
    STATE["active"] meanwhile. Outside one — startup, the chat job thread —
    nothing is pinned and this is the plain active tab, as it always was."""
    pinned = _REQ_TAB.get()
    if pinned and pinned in STATE["docs"]:
        return pinned
    # Degrade gracefully: if no tab is open (fresh import / all tabs closed),
    # auto-create an empty "untitled" document instead of raising KeyError:None
    # (which 500'd /api/doc and left the UI booting half-dead with no guidance).
    # The same branch catches a pinned tab CLOSED under this request.
    if STATE["active"] is None or STATE["active"] not in STATE["docs"]:
        _new_tab(Document(name="untitled"))
    tid = STATE["active"]
    if pinned is not None:            # armed: this request now has its answer
        _REQ_TAB.set(tid)
    return tid


def _activate(tid: str) -> None:
    """Switch to `tid` — and address the REST of this request to it.

    The five routes that move the active tab on purpose (new, switch, close,
    open, sample) go through here, so a deliberate move is never mistaken for
    the doorbell's."""
    STATE["active"] = tid
    if _REQ_TAB.get() is not None:    # only inside a request; never at startup
        _REQ_TAB.set(tid)


def _entry() -> dict:
    return STATE["docs"][_active_tid()]


def _doc() -> Document:
    return _entry()["doc"]


def _snapshot() -> None:
    """Push the active design's intent onto ITS undo stack. Call BEFORE any
    mutation (edit/add/remove/suppress/spec).

    A new edit ends the redo line, exactly as in every editor: once you undo
    three steps and then do something else, the branch you undid is gone. The
    version tree is what keeps that recoverable, not this stack."""
    e = _entry()
    e["history"].append(e["doc"].to_data())
    del e["history"][:-MAX_HISTORY]
    redo = e.setdefault("redo", [])
    e["redo_before"] = list(redo)    # so a REFUSED step can put it back
    redo.clear()
    e["dirty"] = None                # unknown until someone asks (see _dirty)


def _unsnapshot(e: dict | None = None) -> None:
    """Undo the _snapshot() a step took before it was refused.

    Popping the history entry is not enough: _snapshot also ENDS THE REDO LINE,
    and a request that changed nothing must not cost the user their redo. Typo
    a parameter name after two undos and Ctrl+Y was dead — with the multi-param
    route now refusing unknown keys, that door is much wider than it was.
    `e`: the tab to undo it on when it may no longer be the active one."""
    e = e or _entry()
    if e["history"]:
        e["history"].pop()
    prev = e.pop("redo_before", None)
    if prev is not None:               # never WIPE a redo line we did not take
        e["redo"] = prev
    e["dirty"] = None


def _rebuild_and_mesh() -> None:
    """Rebuild the active document. The STL is NOT written here.

    export_stl cost ~400 ms on every rebuild — on every parameter nudge, every
    sketch open and close — and nothing in the UI reads it: the viewport is fed
    by /api/model (JSON). It is written on demand now, when /api/mesh.stl is
    actually asked for."""
    import time
    e = _entry()
    t0 = time.perf_counter()
    with _KERNEL_LOCK:
        e["ok"] = e["doc"].rebuild()
    e["rebuild_ms"] = round((time.perf_counter() - t0) * 1000)
    e["mesh_stale"] = True


def _tabs_json() -> list[dict]:
    # ok: True/False = last rebuild's verdict; None = restored from the last
    # session and not rebuilt yet (rebuilds on first switch) — the UI shows
    # that as a grey "not loaded yet" dot instead of a red "broken" one
    #
    # "active" is the tab THIS ANSWER is about (see _doc_json's active_tab),
    # not whichever tab is live at this instant: the strip must highlight the
    # design whose tree is in the same reply.
    here = _active_tid()
    return [{"id": tid, "name": e["doc"].name,
             "ok": e["ok"] if e["rebuild_ms"] is not None else None,
             "active": tid == here,
             # unsaved-changes marker; the UI asks before closing a dirty tab
             "dirty": _dirty(e)}
            for tid, e in STATE["docs"].items()]


# ---------------------------------------------------------------------------
# Session persistence — the open tabs SURVIVE a server restart
# ---------------------------------------------------------------------------
# Restarting the server (an upgrade, a crash) used to wipe every open tab:
# whatever wasn't saved to designs/ was simply gone (2026-08-31: three tabs
# lost this way — user: "all other designs that I am working on close and
# vanish, do not do that"). So after every mutating request the full intent
# of EVERY open tab — unsaved ones included — is written to one small JSON
# file, and startup reopens exactly those tabs, active one active again.
# Undo stacks and rollback state stay transient; the DESIGNS stay untouched
# (a restored unsaved tab is still unsaved).

SESSION_PATH = ROOT / ".studio-session.json"

# The middleware persists only in a real server run (__main__ flips this on).
# Tests import this module and hammer the POST endpoints via TestClient —
# without the gate, running pytest would overwrite the user's live session.
SESSION_ENABLED = False


def _persist_session() -> None:
    """Every open tab's intent -> SESSION_PATH. A few KB, written atomically
    (tmp + replace) so a kill mid-write can never leave half a session; any
    failure is swallowed — persistence must never break an API reply."""
    try:
        tabs = [{"doc": e["doc"].to_data(), "source": e.get("source"),
                 "active": tid == STATE["active"]}
                for tid, e in STATE["docs"].items()]
        tmp = SESSION_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tabs": tabs}), encoding="utf-8")
        tmp.replace(SESSION_PATH)
    except Exception:
        pass


def _restored_baseline(src: str) -> str | None:
    """The content hash a restored tab's unsaved edits are measured against.

    Three sources, in order of authority, because the first two can both be
    absent: the design's CURRENT VERSION, else the design FILE on disk (a
    design that was never versioned still has a baseline), else — for a
    built-in sample, which has no file at all — the pristine sample.

    None means "nothing to compare against", which `_dirty` reads as DIRTY.
    That is deliberate: the cost of a needless ● is a question the user
    answers in one click, and the cost of a wrong "clean" is their work.
    Both fallbacks were missing (section 3 review, 2026-09-10) — a design
    with no .history/ and every sample tab kept the ALREADY-EDITED restored
    content as their own baseline, so they read clean after a restart and
    closing the tab discarded the edits without asking."""
    if src.startswith("file:"):
        slug = src[5:]
        try:
            h = History.for_design(_history_root(), slug)
            cur = h.current()
            if cur:
                return h.get(cur).hash
        except Exception:
            pass                                   # broken index: try the file
        try:                                       # normalised through Document
            return content_hash(
                Document.load(str(DESIGNS / f"{slug}.tcad.json")).to_data())
        except Exception:
            return None
    if src.startswith("sample:"):
        try:
            return content_hash(SAMPLES[src[7:]]().to_data())
        except Exception:
            return None
    return None


def _restore_session(rebuild: bool = True) -> int:
    """Reopen the previous run's tabs from SESSION_PATH. Only the ACTIVE tab
    is rebuilt here — rebuilding a whole heavy session up front kept the port
    closed for minutes (measured: a 79-feature tab among four). The others
    rebuild lazily on their first switch (see switch_tab); until then their
    tab dot shows grey "not loaded yet", not red. One broken tab never takes
    down the rest. Returns how many tabs came back.

    rebuild=False is the SAFE restore after a startup crash (the supervisor's
    TEXTCAD_SAFE_RESTORE): a tab whose rebuild segfaults the kernel would
    otherwise kill every restart. Nothing is built and no tab is activated;
    the caller opens an empty tab and the user decides which tab to try."""
    if not SESSION_PATH.exists():
        return 0
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    restored, active_tid = 0, None
    # EVERY tab in the file, not the first MAX_TABS of them. MAX_TABS is the
    # cap on OPENING a tab (/api/new, the AI's "create"), but /api/open has
    # none, so a session legitimately holds more — and the slice kept the
    # OLDEST and threw away the newest, which is the tab the user is actually
    # working in. Measured 2026-09-16 (section 12 review): 13 tabs, the 13th
    # active and holding unsaved work, restart, 12 came back and that work was
    # gone with no prompt — the opposite of what this file exists for ("all
    # other designs that I am working on close and vanish, do not do that").
    # Restoring costs nothing per tab: only the active one is rebuilt here.
    for t in data.get("tabs", []):
        try:
            doc = Document.from_data(t["doc"])
            src = t.get("source")
            tid = _new_tab(doc, source=src, activate=False)
            # A restored tab may hold UNSAVED edits (that is the point of the
            # session file), so its dirty baseline is what the design WAS, not
            # whatever intent just came back — otherwise a dirty tab would
            # read clean after every restart and the close prompt would let
            # those edits vanish silently. A None baseline reads DIRTY, which
            # is the safe direction when nothing can be compared against.
            if src and src.startswith(("file:", "sample:")):
                e = STATE["docs"][tid]
                e["clean_hash"] = _restored_baseline(src)
                e["dirty"] = None
            if t.get("active"):
                active_tid = tid
            restored += 1
        except Exception:
            continue
    if restored and rebuild:
        STATE["active"] = active_tid or next(reversed(STATE["docs"]))
        _rebuild_and_mesh()                    # the visible tab only
    return restored


# ---------------------------------------------------------------------------
# Crash recovery — the kernel can take the process down (LAUNCH-PLAN §10 ★P0)
# ---------------------------------------------------------------------------
# The session file above IS the checkpoint: it holds every tab as of the last
# moment NO request was running, so neither the request that segfaults the
# kernel nor anything it half-applied can reach it, and the relaunched server
# (see supervise.py) comes back one whole step behind. Two small things make
# the crash SPEAK instead of looking like a hang: an in-flight marker naming
# the request that was running when the process died, and RECOVERY, the note
# the UI shows once ("the kernel crashed while handling ...; the design is back
# at the last completed step").

RECOVERY: dict | None = None      # set at startup when the previous process crashed


# FastAPI runs every sync endpoint in a threadpool, so POSTs OVERLAP: a tree
# click during an 8-second fillet is a second request INSIDE the first. The
# marker is therefore the SET of POSTs running right now. The file names the
# OLDEST — the slow one a crash is overwhelmingly likely to be in — so a later
# request can never steal it. Under uvicorn every middleware body runs on the
# one event-loop thread, but under fastapi's TestClient each calling thread
# gets its OWN portal and loop (probed), so the set is locked rather than
# trusted to a single writer.
_INFLIGHT: dict[int, dict] = {}
_INFLIGHT_SEQ = itertools.count()
_INFLIGHT_LOCK = threading.Lock()

# OCCT is not thread-safe and FastAPI runs the sync routes in a threadpool.
# Every REBUILD takes this lock — the user's edits through _rebuild_and_mesh
# and the AI's steps in a chat job (P5), which run in their own thread for
# minutes while the user keeps working. Re-entrant: a rebuild may be asked
# for from inside a step. Tessellation (GET /api/model) is still outside it
# (LAUNCH-PLAN §10, the "two requests in the kernel" row).
_KERNEL_LOCK = threading.RLock()

# TEST ONLY (TEXTCAD_CRASH_TEST): {"path": "/api/feature/params"} makes the
# next request to that path die WITH its marker written, so a test can put the
# crash inside a tool's own step instead of racing a timer. Empty otherwise.
_CRASH_NEXT: dict = {}


def _inflight_path() -> Path:
    return supervise.inflight_path(SESSION_PATH)


def _write_inflight() -> None:
    """The oldest request still running — or no file at all when none is.
    Call with _INFLIGHT_LOCK held."""
    try:
        oldest = next(iter(_INFLIGHT.values()), None)
        if oldest is None:
            _inflight_path().unlink(missing_ok=True)
        else:
            _inflight_path().write_text(json.dumps(oldest), encoding="utf-8")
    except Exception:
        pass                      # bookkeeping must never break a reply


def _mark_inflight(request) -> int:
    """What we are about to do, in case we never get to say we did it."""
    rid = next(_INFLIGHT_SEQ)
    with _INFLIGHT_LOCK:
        _INFLIGHT[rid] = {"method": request.method, "path": request.url.path,
                          "at": time.time()}
        _write_inflight()
    return rid


def _clear_inflight(rid: int | None = None) -> bool:
    """Forget one request — or, with no argument, whatever a dead process left
    behind. True when nothing is running any more."""
    with _INFLIGHT_LOCK:
        if rid is None:
            _INFLIGHT.clear()
        else:
            _INFLIGHT.pop(rid, None)
        _write_inflight()
        return not _INFLIGHT


def _recovery_note() -> dict | None:
    """Startup: the supervisor's verdict on the previous process
    (TEXTCAD_RECOVERED = "0xC0000005", or "0xC0000005:startup") joined with the
    request it died in (a leftover in-flight marker). The marker is consumed
    either way — a deliberate stop mid-request leaves one too."""
    marker = None
    p = _inflight_path()
    if p.exists():
        try:
            marker = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            marker = None
        _clear_inflight()
    code = os.environ.get("TEXTCAD_RECOVERED")
    if not code:
        return None
    startup = code.endswith(":startup")
    return {"code": code.split(":")[0], "startup": startup,
            # Whether this child skipped the rebuild is the SERVER's to say
            # (R1): the supervisor also asks for an unbuilt restore after a
            # crash LOOP, which is not the same thing as a startup crash.
            "unbuilt": os.environ.get("TEXTCAD_SAFE_RESTORE") == "1",
            "request": None if startup else marker, "at": time.time()}


def _watch_parent() -> None:
    """Child of the supervisor: exit when it goes away (EOF on the pipe it
    holds open as our stdin), so a listener is never orphaned on the port."""
    if os.environ.get("TEXTCAD_SERVER_CHILD") != "1":
        return
    if sys.stdin is None or sys.stdin.isatty():
        return

    def watch():
        try:
            sys.stdin.buffer.read()
        except Exception:
            pass
        os._exit(0)
    threading.Thread(target=watch, daemon=True).start()


if os.environ.get("TEXTCAD_CRASH_TEST") == "1":
    @app.post("/api/_crash")
    def crash_for_test():
        """TEST ONLY (tests/test_supervisor.py): a real access violation, the
        same 0xC0000005 an OCCT segfault gives, without an 8-second fillet."""
        import faulthandler
        faulthandler._read_null()

    class CrashNextReq(BaseModel):
        path: str

    @app.post("/api/_crash_next")
    def crash_next_for_test(req: CrashNextReq):
        """TEST ONLY: die on the NEXT request to `path`. Lets a browser test
        put the crash inside a tool's own step — the case where the answer
        never comes back to the code that asked for it — with no timing luck
        and no 8-second fillet."""
        _CRASH_NEXT["path"] = req.path
        return {"armed": req.path}


# The ONE POST that stays open while a chat job is building in the ACTIVE
# tab: switching tabs is how the user gets AWAY from the job to keep working.
# /api/tool/plan was here too, as "read-only" — but toolplan.plan reads
# doc._parts, and rebuild() CLEARS that at the start of every step, so a plan
# landing between two steps answered a confident sentence about geometry that
# was simply absent ("'base' is a plate, not fillet / chamfer" — measured
# 2026-09-11) while touching OCCT beside the job's own kernel call.
_JOB_OPEN_POSTS = {"/api/tabs/switch",
                   # the bug button reads the design, never writes it — and
                   # "the AI is stuck" is exactly when the user presses it
                   "/api/bug"}


@app.middleware("http")
async def _one_tab_per_request(request, call_next):
    """Arm the per-request tab pin (see _REQ_TAB / _active_tid).

    Nothing is resolved here — the first read inside the endpoint does that,
    and it must be the endpoint's own read so a route that deliberately opens
    or switches a tab still gets the tab it just made. Registered as a
    middleware because that is the one place every request passes through,
    and because a set made HERE reaches the endpoint while the endpoint's own
    set never comes back out (both measured,
    probes/section12_round4_ctxvar_probe.py) — so nothing leaks into the next
    request or into _persist_session."""
    _REQ_TAB.set(_addressed_tab(request) or _ARMED)
    return await call_next(request)


@app.middleware("http")
async def _one_writer_per_tab(request, call_next):
    """While the AI is building in a tab, it is that tab's only writer.

    The busy overlay lives INSIDE the viewport (static/index.html), so the
    ribbon, the feature tree and the tab strip stay clickable while an "add"
    job runs. Measured 2026-09-11: a parameter edit landing between two AI
    steps pushed a second undo entry, and the promised "one Undo takes it all
    back" then left the AI's first feature in the tree and silently reverted
    the user's own edit. The answer carries no document on purpose — the tree
    is mid-change by the job, and the browser is already being handed it,
    read under the kernel lock, by GET /api/chat/job."""
    if request.method != "POST" or request.url.path in _JOB_OPEN_POSTS:
        return await call_next(request)
    try:
        # the tab the request is ADDRESSED to (see TAB_HEADER), else the
        # active one — so a write to a quiet tab is not refused because the AI
        # is busy in another. _addressed_tab, not the raw header: this has to
        # be the SAME question _one_tab_per_request asks, or a header naming a
        # tab that is not open walks past the guard and then falls back to the
        # busy tab anyway (measured, round five).
        busy = _job_on(_addressed_tab(request) or STATE["active"]) is not None
    except Exception:        # noqa: BLE001 — a broken guard FAILS OPEN
        # This middleware is registered after _never_die, so Starlette puts it
        # OUTSIDE that barrier and anything it raises is a bare 500 — plain
        # text the browser reads as "the server restarted" (measured). The
        # request it was guarding is worth more than the guard: let it through.
        busy = False
    if not busy:
        return await call_next(request)
    return JSONResponse(status_code=400, content={
        "error": "the AI is still building in this design — wait for it to "
                 "finish, or switch to another tab to keep working"})


@app.middleware("http")
async def _session_autosave(request, call_next):
    if not (SESSION_ENABLED and request.method == "POST"):
        return await call_next(request)
    rid = _mark_inflight(request)
    if _CRASH_NEXT and request.url.path == _CRASH_NEXT.get("path"):
        import faulthandler                    # TEST ONLY: see _CRASH_NEXT
        faulthandler._read_null()              # dies here, marker written
    try:
        response = await call_next(request)
    except BaseException:
        _clear_inflight(rid)      # a disconnect must not strand the marker
        raise
    if _clear_inflight(rid):
        # Alone again: every POST has finished, so the tabs are a whole step.
        # While another one is still running the state holds ITS half-applied
        # edit — edit_params writes the new value into the feature BEFORE the
        # kernel is asked — and a checkpoint taken now would hand the
        # relaunched server the very value that crashed it.
        _persist_session()
    return response


# ---------------------------------------------------------------------------
# Version history — VERSION-TREE-PLAN.md P2
# ---------------------------------------------------------------------------
# NAMING TRAP: a tab entry's "history" key is the UNDO stack — in memory, per
# tab, capped, gone on restart. The VERSION tree below is a different thing
# living on disk under designs/<slug>.history/. Undo is for the last few
# keystrokes; versions are for putting v3 back on screen next week. Nothing
# here touches the undo stack.

def _slug_of_active(e: dict | None = None) -> str | None:
    """The library slug of the active tab, or None for anything unsaved.

    A version tree is keyed to a file, so an untitled scratch design has no
    history until it is saved — "no history dir until first version".

    Pass the tab ENTRY when the caller has already read it and the two facts
    must belong to the same design: /api/export takes the document from one
    read of STATE["active"] and the file name from this one, and the active
    tab moves from OTHER THREADS — the MCP doorbell posts
    /api/open/<slug>?external=1 and takes it (round three, 2026-09-16)."""
    src = ((_entry() if e is None else e).get("source") or "")
    return src[5:] if src.startswith("file:") else None


HISTORY_ROOT_ENV = "TEXTCAD_HISTORY_ROOT"


def _history_root() -> Path:
    """Where version histories live: beside the designs they belong to, unless
    overridden.

    The override is not a nicety. /api/open now creates <slug>.history/ as a
    side effect, so a test that merely opens flange-100 would leave a directory
    behind inside designs/ — which is tracked USER WORK. tests/conftest.py
    points this at a throwaway path for every test."""
    override = os.environ.get(HISTORY_ROOT_ENV)
    return Path(override) if override else DESIGNS


def _saved_versions_exist(slug: str) -> bool:
    """True when designs/<slug>.history/ already holds someone's versions.

    The design FILE is not the only thing a save can land on: the version
    tree outlives it, and grafting one design onto another's tree is the P0
    the section 3 review measured. Snapshots count even when the index is
    unreadable — that is data, and a save must not build on top of it."""
    h = History.for_design(_history_root(), slug)
    return bool(h.versions()) or bool(h.snapshot_files())


def _vhistory() -> History | None:
    slug = _slug_of_active()
    return History.for_design(_history_root(), slug) if slug else None


def _measured(e: dict) -> dict:
    """Cheap facts about the build, stored with the version so two versions can
    be compared later without rebuilding either. Nothing here may cost geometry
    work — it runs on every recorded version."""
    out: dict = {"features": len(e["doc"].features), "ok": bool(e.get("ok"))}
    try:
        f = e["doc"]._result_feature()
        if f is not None and f.volume is not None:
            out["volume"] = f.volume
    except Exception:                       # never break a save over metadata
        pass
    return out


def _hand_edit() -> None:
    """Mark that the USER changed this design by hand.

    Counted rather than flagged so the version can say how much: "manual
    changes (7 edits)" is a far better label than "saved" when the point is to
    tell the AI's work apart from the user's."""
    _entry()["hand_edits"] = _entry().get("hand_edits", 0) + 1


def _pending(label: str, kind: str, e: dict | None = None) -> None:
    """Note a change that will ride into the NEXT saved version.

    User (2026-09-01): "do not push it as a version until i want to do" — a
    tool commit / import / AI edit no longer mints a version of its own. The
    note is kept so the eventual save can say what it holds ("hole added; AI
    set bore.radius = 9") instead of a bare "saved". `kind` is "tool" or "ai",
    for attributing the version to whoever actually did the work. `e` names
    a tab other than the active one (a chat job building in its own tab)."""
    e = e or _entry()
    p = e.setdefault("pending", [])
    p.append({"label": label, "kind": kind})
    del p[:-30]                       # a label needs the gist, not a full log


def _mark_clean() -> None:
    """The doc on screen now equals the design's current version."""
    e = _entry()
    e["clean_hash"] = content_hash(e["doc"].to_data())
    e["dirty"] = False


def _dirty(e: dict) -> bool:
    """Does this tab hold changes that are not yet pushed as a version?

    Hash-based, not flag-based, so five tweaks followed by five undos read as
    CLEAN — the close prompt must never cry wolf. The hash costs ~8 ms on the
    biggest design, so it is cached per tab and recomputed only after a
    mutation (_snapshot / undo / redo set it back to None); read-only requests
    never pay for it. A design that never had a file (untitled, AI-created) is
    dirty the moment it has any features: closing that tab loses them."""
    src = e.get("source") or ""
    if not src.startswith(("file:", "sample:")):
        return bool(e["doc"].features)
    if e.get("dirty") is None:
        e["dirty"] = content_hash(e["doc"].to_data()) != e.get("clean_hash")
    return bool(e["dirty"])


def _record_version(label: str, source: str) -> dict:
    """Mint a version of the active design — ONLY when the user pushes one.

    Originally wired to every "meaningful moment" (tool commit, import, AI
    edit); the user overruled that on 2026-09-01: "whatever i am adding its
    going as new version, it should not be like that". Now the only minting
    moments are an explicit SAVE and open/reload-from-disk (the baseline a
    discard falls back to). Everything else — tool commits, imports, AI edits,
    parameter nudges — accumulates as the tab's dirty state (see _dirty) and
    rides into the next save together, labelled by its _pending notes.

    Never raises into an endpoint. The design change already succeeded; a
    sidecar file that cannot be written must not make it look otherwise, so the
    fault is reported alongside the result instead."""
    h = _vhistory()
    if h is None:
        return {}
    e = _entry()
    hand = e.get("hand_edits", 0)
    pending = e.get("pending", [])
    # A save carries everything done since the last version, so its label and
    # author must say so — the work is whoever's it actually was, not "saved".
    if source == "save" and (pending or hand):
        if pending:
            bits = [p["label"] for p in pending]
            if hand:
                bits.append(f"{hand} tweak{'' if hand == 1 else 's'}")
            label = "; ".join(bits[:3])
            if len(bits) > 3:
                label += f" +{len(bits) - 3} more"
        else:
            label = f"manual changes ({hand} edit{'' if hand == 1 else 's'})"
        source = ("ai" if pending and not hand
                  and all(p["kind"] == "ai" for p in pending) else "manual")
    try:
        h.init(_slug_of_active() or "")
        v = h.append(e["doc"].to_data(), label=label, source=source,
                     rebuildable=bool(e.get("ok")), spec=_measured(e))
        # the doc IS the current version now, whatever triggered the mint —
        # and on open/reload the outgoing edits were replaced, so the notes
        # about them must not leak into a later save's label
        e["hand_edits"] = 0
        e["pending"] = []
        _mark_clean()
        return {"version": v.id}
    except HistoryError as ex:
        return {"history_error": str(ex)}


def _refused(e, message: str | None = None,
             extra: dict | None = None) -> JSONResponse:
    """A request the document turned down: the sentence, the UNCHANGED
    document, and HTTP 400 -- so a script or the MCP that reads the status
    sees the refusal. `ok` in the body is the BUILD's health, not the
    request's: an edit that changed nothing must not paint the tree red.

    `message` replaces the exception's own text; `extra` carries a route's
    own payload (the measure plan's reason codes) alongside it. EVERY refusal
    of a request goes through here -- a route that answers a refusal with 200
    is telling a script the opposite of what happened."""
    return JSONResponse(status_code=400, content=jsonable_encoder(
        {**(extra or {}), "error": message or str(e), **_doc_json()}))


def _doc_json() -> dict:
    e = _entry()
    doc = e["doc"]
    rf = doc._result_feature()
    return {
        "name": doc.name,
        "ok": e["ok"],
        "rebuild_ms": e["rebuild_ms"],
        "dirty": _dirty(e),        # changes not yet pushed as a version
        "can_undo": len(e["history"]) > 0,
        "can_redo": len(e.get("redo") or []) > 0,
        "rollback": doc.rollback,
        "geom_version": getattr(doc, "_geom_version", ""),
        # lumps in the displayed result: 2 means the design is not one part
        "result_pieces": rf.pieces if rf else None,
        # the status bar's volume. The tree used to pick "the last
        # non-suppressed feature" in JS, which on a design ending in a sketch
        # (designs/spiderman-logo) has no volume at all, and where the last
        # row is a separate tool body reported THAT body's volume as the
        # design's. The document already knows which feature is the result
        # (R1: never re-derive a backend fact in the frontend).
        "result_volume": rf.volume if rf else None,
        # separate BODIES on screen (Fusion's Bodies folder), counted properly
        # instead of inferred from how many warnings happen to exist
        "bodies": len(doc.leaf_solid_ids()),
        "spec": doc.spec,
        "spec_problems": doc.spec_problems,
        # whether the check RAN — a parked rollback bar means it could not,
        # which is not a failure. The browser must never work this out from
        # the wording of a problem line (R1).
        "spec_checked": doc.spec_checked,
        "warnings": doc.warnings,
        # named parameters: name, formula, value, comment, who uses it, a problem
        "parameters": doc.parameters_json(),
        "tabs": _tabs_json(),
        # THE TAB THIS ANSWER IS ABOUT — never the live active tab. The
        # browser stores the whole reply as S.lastDoc and api.js sends
        # S.lastDoc.active_tab back as the next request's X-TextCAD-Tab, so a
        # reply that carries one design's tree under another design's label
        # points the NEXT click at the wrong design. Measured, round five
        # (probes/section12_round5_hammer.py): a poll answered about the
        # user's own tab came back labelled the tab an MCP doorbell had just
        # made active, and the next edit — typed against the tree on screen —
        # set the ARRIVING design's base.thickness to 41 while the design on
        # screen kept its 5. The per-request pin held for exactly one request
        # and this line gave the next one away. A design arriving from outside
        # is still followed, deliberately, off the `arrival` marker below.
        "active_tab": _active_tid(),
        "recovery": RECOVERY,      # the previous process crashed: what, when
        # a design that arrived from outside the browser and has not been
        # announced yet — one banner, consumed by whoever shows it
        "arrival": _arrival_json(),
        "features": [{
            "id": f.id, "op": f.op, "params": f.params, "inputs": f.inputs,
            "status": f.status, "problems": f.problems, "volume": f.volume,
            "suppressed": f.suppressed, "pieces": f.pieces,
            "notes": getattr(f, "notes", []),
            # a PATH sketch (open lines for Sweep, area 0): the tools offer it
            # as a path and never as a profile — a fact the server states (R1)
            "path_sketch": (f.op in sketchlib.SKETCH_PRODUCERS
                            and sketchlib.is_path_sketch((f.params or {}).get("entities"))),
            # {param: value} for every FORMULA this feature holds, so the tree
            # can show `wall*2 = 6` (a formula that does not work out: null)
            "resolved": doc.resolved_json(f),
        } for f in doc.features],
    }


# ---------------------------------------------------------------------------
# Chat intent — the LLM's ONLY power here is pointing at (feature, param, value)
# ---------------------------------------------------------------------------

def _user_env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    try:                                   # VS Code's env may predate setx
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


INTENT_PROMPT = """You are the edit assistant inside TextCAD Studio, a
parametric CAD tool. You will be given the current design's feature tree as
JSON and a user message. Respond with ONLY a JSON object, no prose:

To edit one parameter: {"action":"edit","feature_id":"...","param":"...","value":<number-or-list>}
To delete a feature:   {"action":"delete","feature_id":"..."}
To ADD features to the CURRENT design (a hole, a boss, a pocket, a fillet, a
pattern... on the part already in the tree): {"action":"add","description":"<the user's requirement, restated precisely, with every number>"}
To design a NEW object from scratch (user describes something to create, not a
change to the current one): {"action":"create","description":"<the user's full requirement, restated precisely>"}
To answer a question:  {"action":"answer","text":"..."}

NEVER refuse or answer that an object cannot be designed — ANY object request
(a car, a rocket, a chair, a cartoon character) routes to "create"; the design
engine will build a stylized approximation if the shape is organic/complex.

Rules:
- "feature_id" MUST be exactly one of the "id" values in the tree, and "param"
  MUST be a key of that feature's "params". NEVER invent names.
- Map the user's vocabulary onto the actual tree. E.g. if the user says "bore"
  and the tree has a with_center_hole feature named "hub", the bore is
  hub.radius. "Blade count" is usually a polar_pattern's "count".
- All lengths are mm, angles deg; convert if the user implies otherwise.
- "delete" is for "remove/delete/get rid of <feature>". Pick the feature the
  user MEANS: a pocket the user names is usually the cut/extrude feature, not
  its sketch. Dependent features are repaired automatically, so never refuse a
  delete because something downstream uses it.
- "add" is for anything that puts NEW geometry on the design in the tree
  (when the tree is empty, "create"). "edit" is for changing a number that
  already exists. If the request is none of these, explain briefly via
  "answer"."""


def _make_model():
    key = _user_env("OPENROUTER_API_KEY")
    if not key:
        return None
    from generate import OpenRouterModel
    return OpenRouterModel(
        api_key=key,
        model=_user_env("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.5")


def chat_intent(message: str, feedback: str | None = None) -> dict:
    doc_json = json.dumps(_doc_json()["features"])
    model = _make_model()
    if model:
        try:
            user = f"FEATURE TREE:\n{doc_json}\n\nUSER: {message}"
            if feedback:
                user += (f"\n\nYour previous intent FAILED: {feedback}\n"
                         "Pick a feature_id and param that actually exist above.")
            raw = model.generate([
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": user},
            ])
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            return json.loads(raw)
        except Exception as e:
            return {"action": "answer",
                    "text": f"(model unavailable: {e}) Try clicking a value "
                            f"in the tree to edit it directly."}
    # offline fallback: "set <feature> <param> to <value>"
    m = re.search(r"(?:set|change|make)\s+(\w+)[ .](\w+)\s+(?:to\s+)?(-?[\d.]+)",
                  message, re.I)
    if m:
        return {"action": "edit", "feature_id": m.group(1),
                "param": m.group(2), "value": float(m.group(3))}
    return {"action": "answer",
            "text": "No API key found — use: set <feature> <param> to <value>, "
                    "or click a value in the tree."}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class VersionReq(BaseModel):
    id: str | None = None            # None = unpin, for the star


class LabelReq(BaseModel):
    id: str
    label: str = ""


class EditReq(BaseModel):
    feature_id: str
    param: str
    value: object


class ParamSetReq(BaseModel):          # named parameters (specs/named-parameters.md)
    name: str
    expr: object                       # "3" | "wall*2" | a number
    comment: str | None = None


class ParamRenameReq(BaseModel):
    old: str
    new: str


class ParamRemoveReq(BaseModel):
    name: str


class ParamsReq(BaseModel):
    feature_id: str
    params: dict           # set several params at once, one rebuild


class FaceReq(BaseModel):
    # a face is named EITHER by geometry (a real pick) or by direction (the
    # authoring path — face="top"/"bottom"/"+x"/...); requiring face_center
    # made every named-face sketch un-editable (422 before the JSON was read)
    face_center: list | None = None
    face_normal: list | None = None
    face_area: float | None = None      # how big the face was when it was clicked
    face: str | None = None
    offset: float = 0.0                 # the sketch plane's offset off the face
    feature_id: str | None = None       # which BODY the face belongs to


class ToolPlanReq(BaseModel):
    # LAUNCH-PLAN.md R1: the tool's input, ONE of the three ways (see toolplan)
    tool: str = "extrude"
    sketch_id: str | None = None        # a sketch / sketch_on_face profile
    body_id: str | None = None          # face mode: the body the face was picked from
    face_center: list | None = None
    face_normal: list | None = None
    face_area: float | None = None      # how big that face was when it was clicked
    feature_id: str | None = None       # edit mode: an existing extrude / extrude_face
    plane: str | None = None            # tool "sketch": the principal plane a new
    offset: float = 0.0                 #   plane sketch is drawn on, and its offset
    axis: str | list | None = None      # tool "revolve": the axis to plan for — "u"/"v",
                                        #   a world name (mapped onto u/v when they coincide),
                                        #   or a line [[u1, v1], [u2, v2]] in the sketch plane
    edges: list | None = None           # tools "fillet"/"chamfer": picked edges of body_id
    chain: bool | None = None           #   (edge_ref dicts or [x, y, z] midpoints); tangent chain on/off
    toggle: dict | None = None          #   one clicked edge to add to / remove from `edges`
    face_toggle: dict | None = None     #   a clicked FACE ({center, normal}): every edge of it, added / taken out
    feature_toggle: str | None = None   #   a TREE ROW: the edges of the faces that feature made, added / taken out
    face_point: list | None = None      # tool "hole": where the face was clicked (world) — the hole's centre
    faces: list | None = None           # tool "shell": the openings as the last plan stored them; a
                                        #   list (even []) IS the selection, face_center only opens
    direction: str | None = None        #   "inside" / "outside" — which side the arrow points
    path_id: str | None = None          # tool "sweep": the PATH sketch to follow (default: the newest one)
    sketch_ids: list | None = None      # tool "loft": the profile sketches, in the order picked
    seed_id: str | None = None          # tools "polar_pattern" / "linear_pattern" / "mirror": the tree row to repeat
    own_id: str | None = None           #   the feature THIS session built: a replan is about it (P4 review)
    axis_pick: dict | None = None       #   circular: a face clicked while the panel is open — its axis
    along: str | None = None            #   rectangular: which alternative is direction 1 ("x" / "y" / "z")
    plane_pick: dict | None = None      #   mirror: a face ({center, normal}) or an origin plane ({world})
                                        #   clicked while the panel is open — the mirror plane; `plane`
                                        #   (above) names an alternative chosen in the panel
    # measure where a narrowing taper's walls meet, per face (18 kernel offsets
    # per face — asked for lazily, the first time the tool needs a taper limit)
    measure_collapse: bool = False
    # tool "hole": measure the material under the point (an Edge ∩ Solid
    # boolean, 250-510 ms on a real body) — asked for the first time a BLIND
    # depth needs the advisory, never for a through hole
    measure_material: bool = False


class TrimReq(BaseModel):
    entities: list
    piece: str | None = None


class SnapReq(BaseModel):
    plane: str = "XY"
    offset: float = 0.0
    # a FACE sketch's world frame ({origin, x_dir, z_dir}, offset baked in) —
    # when present it IS the plane and plane/offset are ignored
    frame: dict | None = None


class ArcRadiusReq(BaseModel):
    entities: list
    entity: int          # index into entities (must be a path)
    segment: int         # index into that path's segments (must be an arc)
    radius: float


class ChatReq(BaseModel):
    message: str


class NewReq(BaseModel):
    name: str = "untitled"


class FeatureReq(BaseModel):
    id: str
    op: str
    params: dict = {}
    inputs: list[str] = []


class TracePngReq(BaseModel):
    png_base64: str                  # data-URL or bare base64 of a PNG/JPG
    feature_id: str = "traced-image"
    height_mm: float = 50.0
    plane: str = "XY"
    offset: float = 0.0
    tol_mm: float = 0.15
    min_channel_mm: float = 0.0      # end-mill pre-fill; 0 = off
    connect_pieces: bool = False     # weld disjoint art into one piece
    # fit-to-face: when a face was picked, the trace lands ON it as a
    # sketch_on_face, auto-scaled to fit — height_mm is then ignored
    face_center: list[float] | None = None
    face_normal: list[float] | None = None
    face_area: float | None = None       # how big that face was when it was clicked
    body_feature_id: str | None = None   # the feature the face was picked from
    fit_margin: float = 0.9          # fraction of the face bbox the art fills
    # entities-only: the sketcher inserting art into the OPEN sketch — return
    # the traced entities without creating any feature. fit_box = [w, h, cx,
    # cy] in the sketch plane's own coords (a face sketch sends its face bbox)
    entities_only: bool = False
    fit_box: list[float] | None = None


class ImportStlReq(BaseModel):
    stl_base64: str                  # data-URL or bare base64 of the .stl
    feature_id: str = "imported-stl"
    scale: float = 1.0               # 1 = STL units are mm


class FaceFeatureReq(BaseModel):
    """A face the user picked in the viewport, as the tagged mesh describes it.
    `face` is the face's index on that body (the mesh's faceId), `center`+`area`
    let the backend notice a stale index after a rebuild, `point` is the raycast
    hit (the best interior sample)."""
    body: str | None = None
    face: int | None = None
    point: list | None = None
    center: list | None = None
    area: float | None = None


class MeasureSel(BaseModel):
    """One viewport selection: a face or edge index on a body, as the tagged
    mesh handed them out."""
    body: str | None = None
    kind: str = "face"
    id: int | None = None


class MeasureReq(BaseModel):
    """Measure one selection (`b` omitted) or between two."""
    a: MeasureSel
    b: MeasureSel | None = None


class MeasureProbeReq(MeasureReq):
    """A dimension-line drag: `point` rides selection `on` (a raycast hit on
    its face) and the answer is the live distance to the other selection."""
    point: list
    on: str = "a"


class MeasureSetReq(MeasureReq):
    """Drive the geometry FROM the measured number: make this dimension
    `value`.

    A DRIVEN dimension (a diameter) writes its one param. A DERIVED one (the
    gap between two independent features) is changed by MOVING one side, and
    `side` says which: "auto" lets tree order decide (the later feature moves,
    because the earlier one is almost always stock or a datum), "a"/"b" is the
    user's explicit choice."""
    value: float
    side: str = "auto"


class RemoveReq(BaseModel):
    feature_id: str
    mode: str = "auto"          # auto (repair the history) | cascade | strict
    dry_run: bool = False       # just report the plan, change nothing


class RenameReq(BaseModel):
    feature_id: str
    name: str


class SuppressReq(BaseModel):
    feature_id: str
    suppressed: bool


class StrikeReq(BaseModel):
    feature_id: str
    restore: bool = False    # True = un-strike (bring the geometry back)


class SpecReq(BaseModel):
    spec: dict


class RollbackReq(BaseModel):
    feature_id: str | None = None


class TabReq(BaseModel):
    id: str


# ---------------------------------------------------------------------------
# Pages + document data
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/doc")
def get_doc():
    return _doc_json()


class ArrivalAckReq(BaseModel):
    at: float


@app.post("/api/arrival/ack")
def ack_arrival(req: ArrivalAckReq):
    """A page has SHOWN the doorbell banner: nobody says it again.

    `at` names the marker the page actually saw. A bare "clear it" would let a
    slow page swallow an arrival that landed in the three seconds between its
    poll and this call — the design loop is "regenerate → POST /api/open →
    look at it", so the doorbell really does ring twice that fast."""
    global ARRIVAL
    if ARRIVAL and ARRIVAL["at"] == req.at:
        ARRIVAL = None
        return {"consumed": True}
    return {"consumed": False}


# ---------------------------------------------------------------------------
# Document tabs
# ---------------------------------------------------------------------------

@app.get("/api/tabs")
def get_tabs():
    return {"tabs": _tabs_json(), "active_tab": _active_tid()}


@app.post("/api/tabs/switch")
def switch_tab(req: TabReq):
    if req.id not in STATE["docs"]:
        return _refused(None, f"no tab '{req.id}'")
    _activate(req.id)
    # geometry is cached inside the Document — no rebuild needed on switch —
    # EXCEPT a tab restored from the last session, which holds only its intent
    # until someone actually looks at it (rebuild_ms None = never built)
    if _entry()["rebuild_ms"] is None:
        _rebuild_and_mesh()
    _entry()["mesh_stale"] = True
    return _doc_json()


@app.post("/api/tabs/close")
def close_tab(req: TabReq):
    if req.id not in STATE["docs"]:
        return _refused(None, f"no tab '{req.id}'")
    # A "create" job builds in a tab that is NOT the active one, so the
    # one-writer rule above never sees it: closing that tab would leave the
    # job building into a document with nowhere to be shown.
    if _job_on(req.id) is not None:
        return _refused(None, "the AI is still building in that tab — wait "
                              "for it to finish before closing it")
    del STATE["docs"][req.id]
    if not STATE["docs"]:                       # never zero tabs
        _new_tab(Document(name="untitled"))
        _rebuild_and_mesh()
    elif STATE["active"] == req.id or STATE["active"] not in STATE["docs"]:
        _activate(next(reversed(STATE["docs"])))
    return _doc_json()


@app.post("/api/new")
def new_design(req: NewReq):
    """New design = a NEW TAB; the current design stays open."""
    if len(STATE["docs"]) >= MAX_TABS:
        return _refused(None, f"too many open tabs (max {MAX_TABS}) — "
                              f"close some")
    _new_tab(Document(name=req.name or "untitled"))
    _rebuild_and_mesh()
    if MESH_PATH.exists():
        MESH_PATH.unlink()
    return _doc_json()


# ---------------------------------------------------------------------------
# Geometry for the viewport
# ---------------------------------------------------------------------------

def _ensure_mesh_file() -> bool:
    """Write _studio_mesh.stl if the current result has not been exported yet."""
    e = _entry()
    if not e.get("mesh_stale", True) and MESH_PATH.exists():
        return True
    part = e["doc"].result()
    if part is None:
        return False
    try:
        b3d.export_stl(part, str(MESH_PATH))
        e["mesh_stale"] = False
        return True
    except Exception:
        return False


@app.get("/api/mesh.stl")
def get_mesh():
    if _ensure_mesh_file() and MESH_PATH.exists():
        return Response(MESH_PATH.read_bytes(), media_type="model/stl")
    return Response(status_code=404)


def _sketch_mesh_data(p) -> dict | None:
    """Tessellation of one built Sketch: triangle fill + edge outlines."""
    positions, indices = [], []
    base = 0
    try:
        for face in p.faces():
            verts, tris = face.tessellate(0.3)
            for v in verts:
                positions += [round(v.X, 4), round(v.Y, 4), round(v.Z, 4)]
            for t in tris:
                indices += [base + t[0], base + t[1], base + t[2]]
            base += len(verts)
        outlines = []
        for edge in p.edges():
            gt = str(edge.geom_type).replace("GeomType.", "")
            n = 2 if gt == "LINE" else 24
            pts = [edge @ (i / n) for i in range(n + 1)]
            outlines.append([[round(q.X, 4), round(q.Y, 4), round(q.Z, 4)]
                             for q in pts])
    except Exception:
        return None
    return {"positions": positions, "indices": indices, "outlines": outlines}


def _sketches_json(doc: Document) -> list[dict]:
    """Unconsumed sketches, tessellated so the viewport can SHOW them as
    floating 2D profiles (like Fusion). Consumed sketches (already extruded /
    revolved / lofted) are hidden to keep the view clean. Same consumed rule
    as the bodies (Document.consumed_ids): a SUPPRESSED consumer does not
    count — striking out a failed extrude must bring its sketch back on
    screen so it can be picked and extruded again (2026-09-01)."""
    consumed = doc.consumed_ids()
    out = []
    for f in doc.features:
        if f.suppressed or f.id in consumed:
            continue
        p = doc._parts.get(f.id)
        if p is None or not sketchlib.is_sketch(p):
            continue
        m = _sketch_mesh_data(p)
        if m is None:
            continue
        out.append({"id": f.id, **m})
    return out


def _plain_mesh(part, tol: float) -> dict:
    """Bare position/index mesh of a solid (no face tagging). Kept for callers
    that only need a silhouette; bodies in /api/model are fully tagged now."""
    positions, indices, base = [], [], 0
    for face in part.faces():
        try:
            verts, tris = face.tessellate(tol)
        except Exception:
            continue
        for v in verts:
            positions += [round(v.X, 3), round(v.Y, 3), round(v.Z, 3)]
        for t in tris:
            indices += [base + t[0], base + t[1], base + t[2]]
        base += len(verts)
    return {"positions": positions, "indices": indices}


def _mesh_tol(part, denom: float = 900.0, floor: float = 0.05) -> float:
    try:
        bb = part.bounding_box()
        return max((bb.size.X + bb.size.Y + bb.size.Z) / denom, floor)
    except Exception:
        return 0.2


# Bodies with more faces than this are treated as imported triangle meshes:
# their raw triangle faces merge into ONE pickable "MESH" face (id -1) and
# skip BRepMesh entirely. Probed on a 10k-triangle sphere: the classic
# per-face path takes 25-50s PER REQUEST vs ~2s for the fast path — and 10k
# individual face-meta entries are useless for picking anyway. Real BREP
# faces on such a body (e.g. a cylinder wall cut into an imported mesh) still
# get the classic individually-tagged treatment.
# One triangulation for the whole solid, instead of meshing every face on its
# own. Per-face tessellation cost 8.8 s on esp32-remote's 254 faces and
# 2.5 s more to sample its edges; the shared mesh does both in well under a
# second AND is better geometry: independently meshed faces do not share the
# nodes along their common edges, so the shell is full of hairline cracks.
MESH_LINEAR_TOL = None          # set per part by _mesh_tol()
MESH_ANGULAR_TOL = 0.35         # rad; ~37 segments around the smallest hole in
                                # esp32-remote, measured, not guessed

MESH_MODE_FACES = 400

# Tessellation cache, process-wide. Triangulating esp32-remote's result body
# costs ~2.2 s; the Part objects themselves are shared by the document rebuild
# cache, so the same geometry reaching a second tab (or the same design opened
# twice) is the SAME shape and must not be re-triangulated. Keyed by the OCCT
# shape, and the entry keeps the Part alive so the key cannot be recycled.
_MESH_CACHE: dict = {}
_MESH_CACHE_MAX = 24
MESH_FACE_ID = -1


def _triangle_pts(face) -> list | None:
    """The 3 corner points of a pure-triangle face wound to its OUTWARD
    normal, or None for anything richer. Pure OCP — no BRepMesh.

    Winding must come from the plane axis + orientation flag: the raw vertex
    walk order is NOT reliable (probed on a lib3mf sphere: 296 of 1258
    triangles came out inverted, which backface-culls them into holes)."""
    pts, seen = [], set()
    vexp = TopExp_Explorer(face.wrapped, TopAbs_ShapeEnum.TopAbs_VERTEX)
    while vexp.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vexp.Current()))
        key = (round(p.X(), 6), round(p.Y(), 6), round(p.Z(), 6))
        if key not in seen:
            if len(pts) == 3:
                return None
            seen.add(key)
            pts.append(key)
        vexp.Next()
    if len(pts) != 3:
        return None
    surf = BRepAdaptor_Surface(face.wrapped)
    if surf.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        return None                # 3-vertex CURVED face — classic path
    ax = surf.Plane().Axis().Direction()
    nx, ny, nz = ax.X(), ax.Y(), ax.Z()
    if face.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        nx, ny, nz = -nx, -ny, -nz
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
    cx = (y1 - y0) * (z2 - z0) - (z1 - z0) * (y2 - y0)
    cy = (z1 - z0) * (x2 - x0) - (x1 - x0) * (z2 - z0)
    cz = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    if cx * nx + cy * ny + cz * nz < 0:
        pts = [pts[0], pts[2], pts[1]]
    return pts


def _shape_key(shape):
    """Identity of a TopoDS shape, usable as a dict key.

    hash() of a TopoDS_Shape is its underlying TShape, which is exactly the
    identity we want and costs 1.5 us. (The first version also appended
    `TShape().This()` for safety: that call takes 1.3 MILLIseconds, and the
    1218 of them were 2.3 of the 3.2 s this function spent. Probed on
    esp32-remote: the hash alone is unique across all 609 edges of a part and
    stable across re-queries, and the key is only ever used within one part.)"""
    return hash(getattr(shape, "wrapped", shape))


def _face_triangles(face, tol):
    """(vertices, triangles) for one face out of the SHARED triangulation.

    Falls back to meshing the face alone if it has no triangulation (a face
    BRepMesh refused). Triangle winding follows the face's orientation: a
    REVERSED face's nodes wind the other way, and getting this wrong turns the
    part inside out under backface culling."""
    tf = face.wrapped
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(tf, loc)
    if tri is None:
        try:
            verts, tris = face.tessellate(tol)
            return [(v.X, v.Y, v.Z) for v in verts], tris
        except Exception:
            return None, None
    trsf = loc.Transformation()
    ident = loc.IsIdentity()
    verts = []
    for i in range(1, tri.NbNodes() + 1):
        p = tri.Node(i)
        if not ident:
            p = p.Transformed(trsf)
        verts.append((p.X(), p.Y(), p.Z()))
    reversed_face = tf.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
    tris = []
    for i in range(1, tri.NbTriangles() + 1):
        a, b, c = tri.Triangle(i).Get()
        if reversed_face:
            b, c = c, b
        tris.append((a - 1, b - 1, c - 1))
    return verts, tris


def _edge_polylines(part) -> tuple[dict, dict]:
    """Every edge's polyline, taken from the shared triangulation — and, keyed
    the same way, the faces each edge bounds (their shape keys), read off the
    same ancestor map: the picker's own-face rule needs them, and a separate
    face.edges() pass cost 6.6% of the mesh (probes/tagged_mesh_hosts_timing_probe.py).

    Sampling each edge's curve instead cost 2.5 s on esp32-remote (609 edges,
    41 points each); this is the mesh's own discretisation, already computed."""
    out, faces_of = {}, {}
    try:
        emap = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(part.wrapped,
                                       TopAbs_ShapeEnum.TopAbs_EDGE,
                                       TopAbs_ShapeEnum.TopAbs_FACE, emap)
    except Exception:
        return out, faces_of
    for i in range(1, emap.Extent() + 1):
        edge = TopoDS.Edge_s(emap.FindKey(i))
        hosts = emap.FindFromIndex(i)
        picks = [hosts.First()] if hosts.Extent() == 1 else [hosts.First(),
                                                             hosts.Last()]
        # a SEAM edge lists its one round face twice in the ancestor map
        faces_of[_shape_key(edge)] = list(dict.fromkeys(_shape_key(p) for p in picks))
        for pick in picks:
            try:
                f = TopoDS.Face_s(pick)
                loc = TopLoc_Location()
                tri = BRep_Tool.Triangulation_s(f, loc)
                if tri is None:
                    continue
                pot = BRep_Tool.PolygonOnTriangulation_s(edge, tri, loc)
                if pot is None:
                    continue
                trsf, ident = loc.Transformation(), loc.IsIdentity()
                nodes = pot.Nodes()
                poly = []
                for k in range(1, nodes.Length() + 1):
                    p = tri.Node(nodes.Value(k))
                    if not ident:
                        p = p.Transformed(trsf)
                    poly.append([round(p.X(), 4), round(p.Y(), 4),
                                 round(p.Z(), 4)])
                if len(poly) >= 2:
                    out[_shape_key(edge)] = poly
                break
            except Exception:
                continue
    return out, faces_of


def _tagged_mesh(part, body_id: str | None = None) -> dict:
    """Face-tagged mesh of ONE solid: triangles carry the index of the OCCT
    face they came from, plus per-face and per-edge metadata for picking.

    Every visible body goes through this, not just the displayed result — a
    body you can see but cannot click is a trap (and a body rendered as a grey
    ghost reads as "it disappeared", which is exactly what users report)."""
    tol = _mesh_tol(part)
    positions, indices, face_ids, faces_meta = [], [], [], []
    base = 0
    all_faces = part.faces()
    mesh_mode = len(all_faces) > MESH_MODE_FACES
    rich_faces = list(enumerate(all_faces))     # faces that get full tagging

    if mesh_mode:
        rich_faces, tri_count = [], 0
        for fi, face in enumerate(all_faces):
            pts = _triangle_pts(face)
            if pts is None:
                rich_faces.append((fi, face))
                continue
            for p in pts:
                positions += [round(p[0], 4), round(p[1], 4), round(p[2], 4)]
                face_ids.append(MESH_FACE_ID)
            indices += [base, base + 1, base + 2]
            base += 3
            tri_count += 1
        if tri_count:
            try:
                area = round(part.area, 2)
            except Exception:
                area = None
            info = {"id": MESH_FACE_ID, "type": "MESH", "planar": False,
                    "area": area, "triangles": tri_count}
            if body_id is not None:
                info["body"] = body_id
            faces_meta.append(info)

    # Triangulate the whole solid ONCE; every face then reads its own slice of
    # that mesh. Faces keep their own vertex ranges (face_ids stays per-vertex,
    # which is what picking needs) but the triangles come from a single
    # consistent mesh.
    if rich_faces:
        try:
            BRepMesh_IncrementalMesh(part.wrapped, tol, False,
                                     MESH_ANGULAR_TOL, True)
        except Exception:
            pass

    for fi, face in rich_faces:
        verts, tris = _face_triangles(face, tol)
        if verts is None:
            continue
        for v in verts:
            positions += [round(v[0], 4), round(v[1], 4), round(v[2], 4)]
            face_ids.append(fi)
        for t in tris:
            indices += [base + t[0], base + t[1], base + t[2]]
        base += len(verts)
        gt = str(face.geom_type).replace("GeomType.", "")
        info = {"id": fi, "type": gt, "area": round(face.area, 2)}
        if body_id is not None:
            info["body"] = body_id          # which body this face belongs to
        # FLAT test is geometric, not by surface type: taper/loft/sweep make dead-
        # flat walls stored as BSPLINE/BEZIER/EXTRUSION that are still sketchable
        # and extrudable. `planar` drives face selection in the UI.
        try:
            info["planar"] = gt == "PLANE" or sketchlib.face_plane(face) is not None
        except Exception:
            info["planar"] = gt == "PLANE"
        try:
            c = face.center()
            info["center"] = [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)]
            n = face.normal_at(c)
            info["normal"] = [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)]
        except Exception:
            pass
        if gt == "CYLINDER":
            try:
                info["radius"] = round(face.radius, 2)
            except Exception:
                pass
            # The AXIS, not center(): a cylinder's center() lies ON the surface
            # (probed 2026-08-27 — a r=5 bore at the origin reports x=-5), so
            # labelling a hole's position from it is wrong by one radius.
            try:
                ax = face.axis_of_rotation
                info["axis"] = [round(ax.direction.X, 4),
                                round(ax.direction.Y, 4),
                                round(ax.direction.Z, 4)]
                info["axis_at"] = [round(ax.position.X, 4),
                                   round(ax.position.Y, 4),
                                   round(ax.position.Z, 4)]
            except Exception:
                pass
        # PER-TYPE DIMENSIONS (user request 2026-08-31: "add this feature for
        # every shape or surface — for a selected box surface show the length
        # and width, if i am selecting a curve show the radius or dia"). All
        # from the TESSELLATION verts, not topological vertices — a disc's top
        # face has no corners at all, and a rotated face's world bbox lies
        # (probed: 23.32 for a 20-wide face at 30°; the plane-frame projection
        # reads 20.00 exactly).
        try:
            if info.get("planar") and verts:
                pl = sketchlib.face_plane(face)
                if pl is not None:
                    ox, oy, oz = pl.origin.X, pl.origin.Y, pl.origin.Z
                    xd = (pl.x_dir.X, pl.x_dir.Y, pl.x_dir.Z)
                    yd = (pl.y_dir.X, pl.y_dir.Y, pl.y_dir.Z)
                    us = [xd[0]*(v[0]-ox) + xd[1]*(v[1]-oy) + xd[2]*(v[2]-oz)
                          for v in verts]
                    vs = [yd[0]*(v[0]-ox) + yd[1]*(v[1]-oy) + yd[2]*(v[2]-oz)
                          for v in verts]
                    ext = sorted((max(us) - min(us), max(vs) - min(vs)),
                                 reverse=True)
                    info["extents"] = [round(ext[0], 2), round(ext[1], 2)]
            elif gt in ("CYLINDER", "CONE") and verts:
                if gt == "CYLINDER":
                    ax = face.axis_of_rotation
                    px, py, pz = ax.position.X, ax.position.Y, ax.position.Z
                    dx, dy, dz = (ax.direction.X, ax.direction.Y,
                                  ax.direction.Z)
                else:
                    co = BRepAdaptor_Surface(face.wrapped).Cone()
                    loc, dirn = co.Axis().Location(), co.Axis().Direction()
                    px, py, pz = loc.X(), loc.Y(), loc.Z()
                    dx, dy, dz = dirn.X(), dirn.Y(), dirn.Z()
                    info["cone_angle"] = round(
                        abs(math.degrees(co.SemiAngle())), 2)
                ss, rr = [], []
                for v in verts:
                    wx, wy, wz = v[0]-px, v[1]-py, v[2]-pz
                    s_ = wx*dx + wy*dy + wz*dz
                    ss.append(s_)
                    qx, qy, qz = wx - s_*dx, wy - s_*dy, wz - s_*dz
                    rr.append((qx*qx + qy*qy + qz*qz) ** 0.5)
                info["height"] = round(max(ss) - min(ss), 2)
                if gt == "CONE":
                    info["cone_d"] = [round(2*min(rr), 2), round(2*max(rr), 2)]
            elif gt == "SPHERE":
                info["radius"] = round(float(face.radius), 4)
            elif gt == "TORUS":
                to = BRepAdaptor_Surface(face.wrapped).Torus()
                info["torus"] = [round(to.MajorRadius(), 4),
                                 round(to.MinorRadius(), 4)]
        except Exception:
            pass                        # a face with no dimensions is still a face
        # FULL circular boundaries of this face, largest first — an annular
        # face's outer and inner radii, a hole's rim on a floor. The user reads
        # a washer face as "outer dia / inner dia" (request 2026-08-31), not as
        # an area. Corner-fillet arcs are PARTIAL circles and excluded: someone
        # asking "what is this bore" does not mean the corner radius.
        try:
            radii = []
            for fe in face.edges():
                if str(fe.geom_type).replace("GeomType.", "") != "CIRCLE":
                    continue
                r = float(fe.radius)
                if abs(float(fe.length) - 2 * math.pi * r) > max(1e-6, 1e-4 * r):
                    continue                     # an arc, not a full circle
                if not any(abs(r - q) < 1e-6 for q in radii):
                    radii.append(r)
            if radii:
                info["circles"] = sorted((round(r, 4) for r in radii),
                                         reverse=True)
        except Exception:
            pass
        faces_meta.append(info)

    # In mesh mode, sampling 15k+ triangle edges would choke both server and
    # viewer (wireframe soup) — only the rich faces' edges are outlines.
    #
    # But an edge's id MUST stay its index into part.edges(), because that is
    # what a pick resolves through (measure.resolve). Concatenating each
    # face's own edges handed out face-order ids instead, so on any body over
    # MESH_MODE_FACES every edge click measured a DIFFERENT edge — silently,
    # because the highlight looks the edge up BY ID and drew the right one.
    # Measured in the section 6 review (2026-09-10): esp32-remote advertised
    # 7176 ids for 3588 real edges, 6760 of them resolving elsewhere, and on
    # isogrid-panel a straight 210 mm edge read "⌀4.50 mm" AND offered an edit
    # box driving corner_hole_sketch's circle. Twelve of the 50 saved designs
    # are over 400 faces.
    #
    # So filter part.edges() down to the rich faces' edges under their TRUE
    # index, which also drops the once-per-face duplicates. part.edges() costs
    # 245 ms on the biggest saved design (cam-cover-plaque, 1552 faces) and is
    # skipped entirely for a triangle-soup body, which has no rich faces.
    if mesh_mode:
        if rich_faces:
            keep = {_shape_key(e) for _, face in rich_faces
                    for e in face.edges()}
            edge_list = [(i, e) for i, e in enumerate(part.edges())
                         if _shape_key(e) in keep]
        else:
            edge_list = []
    else:
        edge_list = list(enumerate(part.edges()))

    edges_meta = []
    edge_polys, edge_hosts = _edge_polylines(part) if not mesh_mode else ({}, {})
    # the ids of the faces each edge bounds — the picker's occlusion rule needs
    # them: an inside corner's line sits a hair BEHIND the two walls that meet
    # there from every viewing angle, and only its own faces may not hide it
    face_index = {_shape_key(face): fi for fi, face in rich_faces}
    for ei, edge in edge_list:
        gt = str(edge.geom_type).replace("GeomType.", "")
        # the polyline the shared mesh already computed for this edge: it costs
        # nothing and follows the triangles exactly, so outlines sit on the
        # silhouette instead of floating beside it
        poly = edge_polys.get(_shape_key(edge))
        if poly is None:
            try:
                poly = toolplan.edge_polyline(edge)
            except Exception:
                continue
        em = {"id": ei, "type": gt, "length": round(edge.length, 2),
              "points": poly,
              "faces": [face_index[k] for k in edge_hosts.get(_shape_key(edge), [])
                        if k in face_index]}
        # a round edge carries its DIAMETER, so clicking the line of a circle
        # can read one out with no round trip. arc_center only: edge.center()
        # is a point on the circle, not its centre (probed 2026-08-27).
        if gt == "CIRCLE":
            try:
                em["radius"] = round(edge.radius, 4)
                c = edge.arc_center
                em["arc_center"] = [round(c.X, 4), round(c.Y, 4), round(c.Z, 4)]
            except Exception:
                pass
        if body_id is not None:
            em["body"] = body_id
        edges_meta.append(em)

    return {"positions": positions, "indices": indices, "faceId": face_ids,
            "faces": faces_meta, "edges": edges_meta}


@app.get("/api/model")
def get_model():
    """EVERY visible body, each face-tagged for picking, plus unconsumed
    sketches as 2D profiles.

    `bodies` lists every unconsumed solid — including the displayed result,
    flagged `result: true` — so the viewport can draw them all as real solids.
    They used to be drawn as translucent grey ghosts with only the result
    solid: extruding a second sketch made the FIRST body a ghost, which reads
    exactly like "my box went blank / disappeared". Fusion shows every body in
    the Bodies folder as a real, clickable solid.

    The top-level positions/indices/faceId/faces/edges keys still describe the
    RESULT body, so older callers keep working."""
    e = _entry()
    doc = e["doc"]
    # The response is 3+ MB of triangles; re-serialising it for a viewport that
    # already has this exact geometry is pure waste. Keyed by the document's
    # geometry fingerprint, so any real change misses the cache.
    version = getattr(doc, "_geom_version", "")
    cached = e.get("model_json")
    if version and cached and cached[0] == version:
        return Response(content=cached[1], media_type="application/json")

    sketches = _sketches_json(doc)
    part = doc.result()
    result_id = doc._result_feature().id if doc._result_feature() else None

    # Tessellation is the single most expensive thing in a viewport refresh
    # (2.3-3.2 s for esp32-remote). The document's rebuild cache hands back the
    # SAME Part object when a feature's inputs did not change, so identity is a
    # sound cache key: same object -> same triangles.
    bodies = []
    for fid in doc.leaf_solid_ids():
        gp = doc._parts.get(fid)
        if gp is None:
            continue
        key = (fid, hash(gp.wrapped))
        hit = _MESH_CACHE.get(key)
        if hit is not None and hit[0].wrapped.IsSame(gp.wrapped):
            tagged = hit[1]
        else:
            try:
                tagged = _tagged_mesh(gp, body_id=fid)
            except Exception:
                continue
            _MESH_CACHE[key] = (gp, tagged)
            while len(_MESH_CACHE) > _MESH_CACHE_MAX:
                _MESH_CACHE.pop(next(iter(_MESH_CACHE)))
        bodies.append({"id": fid, "result": fid == result_id, **tagged})

    result_mesh = next((b for b in bodies if b["result"]), None)
    if result_mesh is None and part is not None:
        # a result that is not a leaf (shouldn't happen) — tag it anyway
        try:
            result_mesh = {"id": result_id, "result": True,
                           **_tagged_mesh(part, body_id=result_id)}
            bodies.append(result_mesh)
        except Exception:
            result_mesh = None
    if result_mesh is None:
        payload = {"positions": [], "indices": [], "faceId": [], "faces": [],
                   "edges": [], "sketches": sketches, "bodies": bodies}
    else:
        payload = {"positions": result_mesh["positions"],
                   "indices": result_mesh["indices"],
                   "faceId": result_mesh["faceId"],
                   "faces": result_mesh["faces"],
                   "edges": result_mesh["edges"],
                   "sketches": sketches,
                   "bodies": bodies}
    body = json.dumps(payload).encode("utf-8")
    if version:
        e["model_json"] = (version, body)
    return Response(content=body, media_type="application/json")


@app.get("/api/sketch-mesh/{feature_id}")
def get_sketch_mesh(feature_id: str):
    """Tessellation of ONE sketch feature — consumed or not — so the tree can
    highlight a selected sketch in the viewport (feature-mesh only does
    solids; a consumed sketch isn't in /api/model's sketches at all)."""
    p = _doc()._parts.get(feature_id)
    if p is None or not sketchlib.is_sketch(p):
        return {"error": "not a built sketch"}
    m = _sketch_mesh_data(p)
    if m is None:
        return {"error": "tessellation failed"}
    return {"id": feature_id, **m}


@app.get("/api/feature-mesh/{feature_id}.stl")
def get_feature_mesh(feature_id: str):
    """Mesh of ONE feature's own solid — lets the UI highlight in 3D what a
    selected tree node actually contributes.

    A STRUCK-OUT feature contributes nothing, and its slot in `_parts` holds
    its first input's solid (rebuild resolves a suppressed node to its
    pass-through). Serving that made clicking a struck fillet or cut light up
    the whole upstream body as if it were the feature's own — the 2026-08-26
    "the whole body is being selected" complaint, back through the struck
    rows (section 2 review, 2026-09-10). 404 is what viewport.js already
    expects here for a feature that is not built."""
    doc = _doc()
    f = next((x for x in doc.features if x.id == feature_id), None)
    if f is not None and f.suppressed:
        return Response(status_code=404)
    part = doc._parts.get(feature_id)
    if part is None:
        return Response(status_code=404)
    path = ROOT / "_studio_feature.stl"
    try:
        b3d.export_stl(part, str(path))
        return Response(path.read_bytes(), media_type="model/stl")
    except Exception:
        return Response(status_code=404)


# ---------------------------------------------------------------------------
# Editing the active design
# ---------------------------------------------------------------------------

@app.post("/api/edit")
def edit(req: EditReq):
    _snapshot()
    try:
        _doc().edit(req.feature_id, req.param, req.value)
    except (KeyError, ValueError) as e:
        _unsnapshot()
        return _refused(e)
    _hand_edit()              # AFTER it lands: a refusal is not a hand edit
    _rebuild_and_mesh()
    return _doc_json()


def _param_change(fn) -> JSONResponse | dict:
    """One named-parameter change: a snapshot for undo, the document's own
    sentence on refusal (nothing half-applied), one rebuild — the same shape
    as /api/edit, because a parameter IS an edit of every feature that names
    it (specs/named-parameters.md)."""
    _snapshot()
    try:
        fn(_doc())
    except (KeyError, ValueError) as e:
        _unsnapshot()
        return _refused(e)
    _hand_edit()
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/parameters")
def set_parameter(req: ParamSetReq):
    """Create or change a parameter: `wall = 3`, `depth = wall*2`."""
    return _param_change(lambda d: d.set_parameter(req.name, req.expr, req.comment))


@app.post("/api/parameters/rename")
def rename_parameter(req: ParamRenameReq):
    """Rename a parameter everywhere it is referred to — by name token."""
    return _param_change(lambda d: d.rename_parameter(req.old, req.new))


@app.post("/api/parameters/remove")
def remove_parameter(req: ParamRemoveReq):
    """Delete a parameter nothing uses; otherwise the sentence names its users."""
    return _param_change(lambda d: d.remove_parameter(req.name))


_FIT_CELLS = 160          # grid across the face's long side (0.4 mm at 60 mm)


def _biggest_all_true_block(mask):
    """(area, i0, i1, j0, j1) of the largest all-true axis-aligned block of a
    2D boolean array — the classic per-row histogram sweep."""
    gh, gw = mask.shape
    heights = np.zeros(gw + 1, np.int32)
    best = (0, 0, -1, 0, -1)
    for j in range(gh):
        heights[:gw] = np.where(mask[j], heights[:gw] + 1, 0)
        stack = []
        for i in range(gw + 1):
            start = i
            while stack and stack[-1][1] >= heights[i]:
                s, hgt = stack.pop()
                if hgt * (i - s) > best[0]:
                    best = (hgt * (i - s), s, i - 1, j - hgt + 1, j)
                start = s
            stack.append((start, int(heights[i])))
    return best


def _inscribed_box(outer) -> list[float]:
    """The biggest axis-aligned rectangle that fits INSIDE a face's outline,
    as [w, h, cx, cy] in the face's own 2D — the box traced art is fitted
    into.

    The fit box used to be the face's BOUNDING box, which is the face only
    when the face is a rectangle. Measured 2026-09-17 on a disc of radius
    30.00 mm: square art auto-fitted to "the 60x60mm face" put all 8 of its
    points OUTSIDE the disc, the furthest 37.96 mm from the centre, with the
    feature green (probes/imgtrace_inscribed_box_probe.py). An L-shaped face
    put 2 points up to 11.68 mm off the material.

    Rasterised rather than solved: the outline is filled onto a grid
    `_FIT_CELLS` across its long side, eroded by one cell so a rectangle of
    grid points cannot bulge out between them, and the largest all-inside
    block is read off. Probed against geometry with a known answer in
    `probes/imgtrace_inscribed_algo_probe.py` — a circle of radius r holds a
    square of side r*sqrt(2) and this reads 42.00 of 42.43 mm at r = 30,
    always INSIDE (worst clearance +0.301 mm, never negative) — and a
    RECTANGLE returns its own bbox exactly, by an early exit, so every flat
    plate face behaves as it always did and costs nothing.

    HOLES are deliberately ignored: art crossing a bolt hole is ordinary
    (the extrude simply has nothing to cut there), while art off the face
    edge is the bug. Round five measured the alternatives on seven faces
    (probes/imgtrace_r5_fitbox_holes.py): punching the holes out costs a
    120x80 plate with a 90x55 pocket 4156 -> 1244 mm2 of drawable material
    and a 100x100 cover with a d30 bore 8949 -> 3271 mm2, and the rule with
    no threshold to calibrate — the rectangle holding the most MATERIAL —
    picks this same box on every one of the seven, washer included.

    A face THINNER than the grid used to fall back to the bounding box, which
    is the bug this function exists to stop: measured 2026-09-17, a 2 mm
    crescent of radius 60 handed back its whole 38.98 x 111.84 mm bbox, 7.3%
    of it on the face, and a 2 mm strip at 45 degrees handed back
    161.41 x 161.41 mm, 2.0% of it on the face. So the grid is retried finer,
    and a face that holds no box at all gets a ZERO one — `_trace_face_fit`
    turns that into "that face is too thin to fit artwork onto", which is the
    honest answer."""
    xs = [float(p[0]) for p in outer]
    ys = [float(p[1]) for p in outer]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    box = [bw, bh, (x0 + x1) / 2, (y0 + y1) / 2]
    if bw <= 0 or bh <= 0:
        return box
    for cells in (_FIT_CELLS, 4 * _FIT_CELLS):
        cell = max(bw, bh) / float(cells)
        pts = np.array([[[round((x - x0) / cell), round((y - y0) / cell)]
                         for x, y in zip(xs, ys)]], np.int32)
        grid = np.zeros((max(1, round(bh / cell)) + 1,
                         max(1, round(bw / cell)) + 1), np.uint8)
        cv2.fillPoly(grid, pts, 1)
        if int(grid.sum()) == grid.size:
            return box                      # the face IS its bounding box
        inside = cv2.erode(grid, np.ones((3, 3), np.uint8),
                           borderType=cv2.BORDER_CONSTANT, borderValue=0)
        area, i0, i1, j0, j1 = _biggest_all_true_block(inside.astype(bool))
        if area <= 0:
            continue                        # too thin for THIS grid
        ax0, ax1 = x0 + i0 * cell, x0 + i1 * cell
        ay0, ay1 = y0 + j0 * cell, y0 + j1 * cell
        if ax1 > ax0 and ay1 > ay0:
            return [ax1 - ax0, ay1 - ay0, (ax0 + ax1) / 2, (ay0 + ay1) / 2]
    return [0.0, 0.0, (x0 + x1) / 2, (y0 + y1) / 2]


@app.post("/api/face-outline")
def face_outline(req: FaceReq):
    """The picked face's boundary (outer + holes) projected into its plane's
    local 2D — so the sketch editor can show the selected surface as reference
    geometry. Resolves the face by GEOMETRY on the body it was picked from
    (feature_id), falling back to the result solid; with several bodies visible
    the result is not necessarily the one you clicked.

    `fit_box` ([w, h, cx, cy]) is the biggest rectangle that fits INSIDE that
    outline — the box anything auto-fitted onto the face belongs in. It is a
    server fact, not a browser one (LAUNCH-PLAN R1): the sketcher takes the
    min/max of `outer` itself, which is the face only when the face is a
    rectangle."""
    part = None
    if req.feature_id:
        part = _doc()._parts.get(req.feature_id)
    if part is None:
        part = _doc().result()
    if part is None:
        return {"outer": [], "holes": [], "planar": False,
                "error": "no solid to sketch on"}
    try:
        out = sketchlib.face_outline_2d(part, req.face_center, req.face_normal,
                                        face=req.face, offset=req.offset,
                                        face_area=req.face_area)
    except Exception as e:
        return {"outer": [], "holes": [], "planar": False, "error": str(e)}
    if out.get("planar") and out.get("outer"):
        out["fit_box"] = [round(v, 3) for v in _inscribed_box(out["outer"])]
    return out


@app.post("/api/tool/plan")
def tool_plan(req: ToolPlanReq):
    """ONE geometry authority for the tools (LAUNCH-PLAN.md R1, P1): the axis,
    origin, frame, outline, limits, default target and into-the-material sign
    a tool needs to draw its handles. The browser draws what this says and
    computes nothing, so the arrow, the ghost and the solid cannot disagree.
    Read-only: no snapshot, no rebuild, no version. Never raises — a failure
    is {"ok": false, "error": <sentence>}."""
    return toolplan.plan(_doc(), req.model_dump())


@app.post("/api/sketch/snap")
def sketch_snap_points(req: SnapReq):
    """Geometry of the visible bodies that is COINCIDENT with the sketch plane,
    in the plane's own 2D coords: corners / edge midpoints / circle centres /
    where an edge pierces the plane, plus the in-plane edges as polylines so
    the sketcher can draw what is snappable. Fetched once when a sketch opens."""
    doc = _doc()
    parts = {fid: doc._parts.get(fid) for fid in doc.leaf_solid_ids()}
    try:
        return snaplib.snap_geometry(parts, req.plane, req.offset,
                                     frame=req.frame)
    except (KeyError, ValueError) as e:
        return {"points": [], "edges": [], "error": str(e)}


@app.post("/api/sketch/outline")
def sketch_outline(req: TrimReq):
    """The loops of each entity the browser cannot draw itself (a text
    entity's glyphs — a font lives in the kernel, not in JS; R1). Stateless:
    the entity list the open sketch editor sends, one list of loops per
    entity, in the sketch's local 2D. A kind the browser draws itself gets
    []; an entity that will not build gets its sentence in `errors`."""
    out, errors = [], {}
    for i, e in enumerate(req.entities or []):
        if not isinstance(e, dict) or e.get("kind") not in ("text",):
            out.append([])
            continue
        try:
            out.append(sketchlib.entity_outlines(e))
        except (KeyError, ValueError, TypeError) as ex:
            out.append([])
            errors[str(i)] = str(ex)
    return {"outlines": out, "errors": errors}


@app.post("/api/sketch/trim/pieces")
def sketch_trim_pieces(req: TrimReq):
    """Split every entity outline at its crossings with the others — the
    hoverable trim segments. Stateless: works on the entity list sent by the
    open sketch editor, not on the document."""
    try:
        return {"pieces": trimlib.trim_pieces(req.entities)}
    except (KeyError, ValueError) as e:
        return {"pieces": [], "error": str(e)}


@app.post("/api/sketch/path-arcs")
def sketch_path_arcs(req: TrimReq):
    """Every arc of every path in the entity list, each labelled `corner` (a
    round between two straight edges, which a radius edit keeps tangent) or
    `arc` (a free bulge between fixed endpoints).

    R1: the tree used to work this out in JS and got a CLOSED path wrong —
    it read segment 0's predecessor as the auto-close line when the real
    neighbour is the last segment, so two arcs meeting at the start were both
    promised a tangent round they do not get. `path_arcs` is the same answer
    `set_arc_radius` acts on, so the row and the edit cannot disagree.
    -> {"arcs": {"<entity index>": [{"segment", "kind", "r"}, ...]}}
    """
    out: dict[str, list] = {}
    for i, e in enumerate(req.entities or []):
        if not isinstance(e, dict) or e.get("kind") != "path":
            continue
        try:
            arcs = cornerlib.path_arcs(e)
        except (KeyError, ValueError, TypeError):
            continue                      # a half-drawn path has no rows yet
        if arcs:
            out[str(i)] = arcs
    return {"arcs": out}


@app.post("/api/sketch/arc-radius")
def sketch_arc_radius(req: ArcRadiusReq):
    """Rewrite one path arc to a given radius (stateless, like trim): a
    corner arc re-fillets tangent to its neighbouring lines, a free arc
    re-bulges between its fixed endpoints. The UI applies the returned
    entities through /api/edit, so undo and the rebuild come for free."""
    try:
        return {"entities": cornerlib.set_arc_radius(
            req.entities, req.entity, req.segment, req.radius)}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": str(e)}


@app.post("/api/sketch/trim/apply")
def sketch_trim_apply(req: TrimReq):
    """Delete one trim piece and return the rebuilt entity list."""
    try:
        return trimlib.trim_apply(req.entities, req.piece or "")
    except (KeyError, ValueError) as e:
        return {"error": str(e)}


@app.post("/api/feature/params")
def edit_params(req: ParamsReq):
    """Set several params of one feature in a single rebuild — used by the
    sketch editor (reopen a committed sketch, redraw, save all entities)."""
    _snapshot()
    try:
        _doc().edit_many(req.feature_id, req.params)
    except (KeyError, ValueError) as e:
        _unsnapshot()
        return _refused(e)
    _hand_edit()              # AFTER it lands: a refusal is not a hand edit
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/feature/add")
def add_feature(req: FeatureReq):
    _snapshot()
    try:
        # strict: a param the op cannot take is a sentence NOW, not a
        # TypeError at the next rebuild with the bad key already stored
        _doc().add(req.id, req.op, req.params, req.inputs, strict=True)
    except ValueError as e:
        _unsnapshot()
        return _refused(e)
    _rebuild_and_mesh()
    _pending(f"{req.op} added", "tool")
    return _doc_json()


def _trace_face_fit(req: TracePngReq):
    """The box traced art is fitted into on the picked face, in the sketch
    frame — the biggest rectangle INSIDE the face's outline, not its bounding
    box. -> (body_feature_id, fit_w, fit_h, fit_cx, fit_cy)

    The bounding box is the face only when the face is a rectangle: on a disc
    of radius 30.00 mm, square art "auto-fitted to the 60x60mm face" put all 8
    of its points off the disc, 37.96 mm out (measured 2026-09-17, see
    `_inscribed_box`)."""
    body_id = req.body_feature_id
    if not body_id or not any(f.id == body_id for f in _doc().features):
        body_id = (_doc().leaf_solid_ids() or [None])[-1]
    part = _doc()._parts.get(body_id) if body_id else None
    if part is None:
        raise ValueError("no solid to fit the logo onto — build a body "
                         "first, or trace without a face selected")
    outline = sketchlib.face_outline_2d(part, req.face_center, req.face_normal,
                                        face_area=req.face_area)
    if not outline.get("planar") or not outline.get("outer"):
        raise ValueError("that face is curved — pick a FLAT face to put "
                         "the logo on")
    w, h, cx, cy = _inscribed_box(outline["outer"])
    if w <= 0 or h <= 0:
        raise ValueError("that face is too thin to fit artwork onto — pick "
                         "a bigger face, or trace without a face selected")
    return (body_id, w, h, cx, cy)


def _trace_fit_height(data: bytes, m_w: float, m_h: float, rounds: int = 5,
                      min_channel_mm: float = 0.0,
                      connect_pieces: bool = False):
    """The trace height and the 90° rotate for art fitted into an
    `m_w` × `m_h` box — from the artwork's aspect measured AT the height the
    art will actually be traced at. -> (height_mm, rotated).

    The aspect is not a constant of the picture. `imgtrace`'s speckle floor is
    a physical 0.25 mm at the FINAL scale, so a smaller target drops more
    pieces and the artwork's own bounding box changes shape with it. Asking
    once at the default 50 mm and then tracing at the fitted height is the
    out-of-step bug the shared `_traceable()` was written to close, through
    the fit door: measured 2026-09-17, one picture reads aspect 1.3467 with
    3 pieces at 50 mm and 0.3333 with 1 piece at 13.4 mm, and that number
    sets BOTH the height and the rotate.

    Re-deriving ONCE is not enough — it oscillates. That same picture on a
    12 × 14 mm face runs 50 → 9.356 → 12.600 → 9.356 for ever, because the
    ornaments come back at one size and go away again at the other
    (`probes/imgtrace_fit_height_probe.py`). So every height that is tried is
    measured at its OWN size, and the winner is the biggest tried height
    whose own measured artwork really fits the box — a choice over a finite
    set, which terminates whether or not the iteration settles. Measured on
    that 12 × 14 face: the shipped rule lays the art down at 9.36 × 3.12 mm,
    this one stands it up at 4.20 × 12.60 mm.

    The aspect is asked with the SAME knobs the trace will run with. The
    bridges and the channel absorb both add material, and adding material
    changes which contours clear the area gate: measured 2026-09-17 (round
    six, `probes/imgtrace_r6_gates.py`) a disc beside five loose 1 px
    hairlines reads aspect 1.0000 for art `connect_pieces` really draws at
    2.1144, and on a 20 × 60 mm face this laid it down at 18.00 × 8.50 mm —
    153 mm2 of the 684 standing it up gives."""
    tried: list[tuple[float, float]] = []
    height = 50.0                     # imgtrace's own default: the bootstrap
    for _ in range(max(1, rounds)):
        if tried:
            try:
                aspect = imgtrace.artwork_aspect(data, height, min_channel_mm,
                                                 connect_pieces)
            except ValueError:
                break                 # too small at THIS size — keep what we
        else:                         # have; the trace re-raises if it must
            aspect = imgtrace.artwork_aspect(data, height, min_channel_mm,
                                             connect_pieces)
        tried.append((height, aspect))
        h0 = min(m_h, m_w / aspect)                    # as-is
        h90 = min(m_w, m_h / aspect)                   # long side along Y
        nxt = max(1.0, min(1000.0, h90 if h90 > h0 * 1.001 else h0))
        if any(abs(nxt - h) <= 1e-6 * h for h, _ in tried):
            break                     # settled, or a cycle we cannot settle
        height = nxt
    best = None
    for h, aspect in tried:
        tol = 1.0 + 1e-9
        fits = (False if h <= m_h * tol and h * aspect <= m_w * tol else
                True if h <= m_w * tol and h * aspect <= m_h * tol else None)
        if fits is not None and (best is None or h > best[0]):
            best = (h, fits)
    if best is None:
        # Nothing tried fits: for this box the picture has no height at which
        # it measures itself the same, so one of them has to be traced and
        # then SHRUNK by `_trace_fitted`'s residual rescale. The least bad is
        # the one that needs the least shrinking — its fidelity floors ran
        # closest to the size the art ends up at.
        #
        # It used to take the SMALLEST tried height, which is the worst of
        # them: that is the size at which the most of the artwork has already
        # been thrown away, so its aspect is the most extreme and the rescale
        # bites hardest. Measured 2026-09-17: a bar with a ladder of ornaments
        # above it, on a 12 x 14 mm face, traced at 2.530 mm where only the
        # bar survives (aspect 24.41) and came back 0.50 x 12.60 mm — a
        # hairline, against 7.27 x 12.60 for this rule and 10.80 x 6.22 for
        # the one-shot rule it replaced (probes/imgtrace_fit_height_attack.py).
        pick = None
        for h, aspect in sorted(tried):          # ties keep the smaller trace
            for rot in (False, True):            # ... and the unrotated one
                w, hh = (h, h * aspect) if rot else (h * aspect, h)
                if w <= 0 or hh <= 0:
                    continue
                s = min(m_w / w, m_h / hh)
                if pick is None or s > pick[0] * 1.001:
                    pick = (s, h, rot)
        best = (pick[1], pick[2]) if pick else (min(tried)[0], False)
    return best


def _trace_fitted(data: bytes, req: TracePngReq,
                  box: tuple[float, float, float, float] | None):
    """Trace `data`; with a fit box (w, h, cx, cy in the sketch plane's own
    coords) the art is scaled to fit_margin × the box and centred on it —
    otherwise it traces at req.height_mm, bbox-centred on the origin.

    Orientation is part of the fit (user report 2026-09-01: a wide logo on
    a tall face came in "vertical position, its no use" — it fitted the
    narrow way at 23mm instead of running along the face): the art is tried
    at 0° AND rotated 90°, and whichever lets it come out BIGGER wins. The
    rotation is +90° (CCW), so rotated text reads bottom-to-top — the
    drawing convention; two sketch Mirrors flip it 180° if wanted."""
    height = req.height_mm
    rotated = False
    if box:
        fw, fh, fcx, fcy = (float(v) for v in box)
        if fw <= 0 or fh <= 0:
            # the SAME sentence `_trace_face_fit` gives, because this is the
            # SAME situation reached through the sketcher's door: the browser
            # sends the server's own `fit_box`, and a face that holds no
            # rectangle sends a zero one. Measured 2026-09-17 (round six,
            # probes/imgtrace_r6_fitbox.py): a 400 x 0.5 mm sliver face at 45
            # degrees does hold no box, and this door answered "the fit box
            # needs a positive width and height" — an internal thing, in the
            # user's chat, at the only door the browser has.
            raise ValueError("that face is too thin to fit artwork onto — "
                             "pick a bigger face, or trace without a face "
                             "selected")
        # pick the trace height so the art fits the box both ways — measured
        # at the height it will BE traced at, because imgtrace's fidelity
        # floors run at the real scale and change which pieces exist
        height, rotated = _trace_fit_height(
            data, req.fit_margin * fw, req.fit_margin * fh,
            min_channel_mm=req.min_channel_mm,
            connect_pieces=req.connect_pieces)
    ents, info = imgtrace.image_to_entities(
        data, height, req.tol_mm, req.min_channel_mm,
        connect_pieces=req.connect_pieces)
    if box:
        if rotated:
            # +90° about the origin — position AND local points (rotation is
            # linear, so rotating both composes exactly)
            for e in ents:
                e["x"], e["y"] = round(-e["y"], 3), round(e["x"], 3)
                e["points"] = [[round(-py, 3), round(px, 3)]
                               for px, py in e["points"]]
            # width_mm/height_mm now mean the FRAME X/Y extents
            info["width_mm"], info["height_mm"] = (info["height_mm"],
                                                   info["width_mm"])
        # residual exact-fit rescale (the traced bbox can differ a hair
        # from the mask bbox after speckle removal / smoothing), then
        # centre on the box. Scale points AND x/y — the entities are
        # bbox-centred, so scaling one without the other silently no-ops.
        s = min([1.0]
                + ([req.fit_margin * fw / info["width_mm"]]
                   if info["width_mm"] > req.fit_margin * fw else [])
                + ([req.fit_margin * fh / info["height_mm"]]
                   if info["height_mm"] > req.fit_margin * fh else []))
        for e in ents:
            if s < 1.0:
                e["x"] = round(e["x"] * s, 3)
                e["y"] = round(e["y"] * s, 3)
                e["points"] = [[round(px * s, 3), round(py * s, 3)]
                               for px, py in e["points"]]
            e["x"] = round(e["x"] + fcx, 3)
            e["y"] = round(e["y"] + fcy, 3)
        info["width_mm"] = round(info["width_mm"] * s, 2)
        info["height_mm"] = round(info["height_mm"] * s, 2)
        # the FIT BOX, not the face: on a 30 mm disc the face is 60 x 60 and
        # this is 42 x 42. `face_mm` is kept beside it so a browser mid-flight
        # keeps working; static/js/sketcher.js must move to `fit_mm` and the
        # old key then goes.
        info["fit_mm"] = info["face_mm"] = [round(fw, 2), round(fh, 2)]
        info["rotated"] = rotated
    return ents, info


@app.post("/api/trace-png")
def trace_png(req: TracePngReq):
    """Upload an image, get a SKETCH feature holding its traced outline —
    then Extrude / Revolve / Cut it like any hand-drawn sketch. With a
    face_center (a real face pick) the sketch lands ON that face instead,
    auto-scaled to fit it (fit_margin × the face bbox) and centred. With
    entities_only the traced entities come back WITHOUT creating a feature
    — the sketcher inserts them into the sketch that is open right now."""
    if req.entities_only:
        try:
            data = base64.b64decode(req.png_base64.split(",")[-1])
            ents, info = _trace_fitted(data, req, tuple(req.fit_box)
                                       if req.fit_box else None)
        except Exception as e:
            return {"error": str(e)}
        return {"entities": ents, "trace_info": info}
    _snapshot()
    try:
        data = base64.b64decode(req.png_base64.split(",")[-1])
        fit = None
        if req.face_center is not None:
            fit = _trace_face_fit(req)
            body_id, fw, fh, fcx, fcy = fit
            ents, info = _trace_fitted(data, req, (fw, fh, fcx, fcy))
        else:
            ents, info = _trace_fitted(data, req, None)
        fid, n = req.feature_id, 2
        while any(f.id == fid for f in _doc().features):
            fid = f"{req.feature_id}-{n}"
            n += 1
        if fit:
            _doc().add(fid, "sketch_on_face",
                       {"face_center": req.face_center,
                        "face_normal": req.face_normal,
                        "face_area": req.face_area,
                        "offset": req.offset, "entities": ents}, [body_id])
        else:
            _doc().add(fid, "sketch",
                       {"plane": req.plane, "offset": req.offset,
                        "entities": ents}, [])
    except Exception as e:        # decode/trace errors -> honest message
        _unsnapshot()
        return _refused(e)
    _rebuild_and_mesh()
    _pending(f"traced {fid}", "tool")
    return {**_doc_json(), "trace_info": {**info, "feature_id": fid}}


class ImportStepReq(BaseModel):
    step_base64: str
    feature_id: str = "imported-step"
    scale: float = 1.0


@app.post("/api/import-step")
def import_step_file(req: ImportStepReq):
    """Upload a STEP file, get an import_step feature holding it as exact BREP
    bodies. The point (user request 2026-08-31): a design EXPORTED from here
    must come back in losslessly — cylinders stay round, no mesh, no repair.
    Same shape as /api/import-stl: the file lands in imports/ so the tree
    stays a small JSON recipe that rebuilds from disk."""
    _snapshot()
    saved_new = None
    try:
        data = base64.b64decode(req.step_base64.split(",")[-1])
        blocks.IMPORTS_DIR.mkdir(exist_ok=True)
        stem = re.sub(r"[^\w-]+", "-", req.feature_id).strip("-")[:40] or "imported"
        fname, n = f"{stem}.step", 2
        # same name + same bytes -> reuse the file; different bytes -> suffix
        while (blocks.IMPORTS_DIR / fname).exists()                 and (blocks.IMPORTS_DIR / fname).read_bytes() != data:
            fname, n = f"{stem}-{n}.step", n + 1
        if not (blocks.IMPORTS_DIR / fname).exists():
            (blocks.IMPORTS_DIR / fname).write_bytes(data)
            saved_new = blocks.IMPORTS_DIR / fname
        # validate BEFORE adding a feature — a bad file must not leave a
        # broken node in the tree
        part = blocks.import_step(fname, req.scale)
        fid, n = req.feature_id, 2
        while any(f.id == fid for f in _doc().features):
            fid = f"{req.feature_id}-{n}"
            n += 1
        _doc().add(fid, "import_step", {"file": fname, "scale": req.scale}, [])
    except Exception as e:        # decode/read errors -> honest message
        _unsnapshot()
        if saved_new is not None:
            try:
                saved_new.unlink()
            except OSError:
                pass
        return _refused(e)
    _rebuild_and_mesh()
    bb = part.bounding_box()
    solids = part.solids()
    _pending(f"imported {fname}", "tool")
    return {**_doc_json(), "import_info": {
        "feature_id": fid, "file": fname, "bodies": len(solids),
        "size_mm": [round(bb.size.X, 2), round(bb.size.Y, 2),
                    round(bb.size.Z, 2)],
        "volume_mm3": round(part.volume, 1)}}


@app.post("/api/import-stl")
def import_stl_file(req: ImportStlReq):
    """Upload an STL from an outside source, get an import_stl feature holding
    it as a solid body — then Move / Cut / Fuse it like any other body. The
    file is saved into imports/ so the feature tree stays a small JSON recipe
    that rebuilds from disk."""
    _snapshot()
    saved_new = None
    try:
        data = base64.b64decode(req.stl_base64.split(",")[-1])
        blocks.IMPORTS_DIR.mkdir(exist_ok=True)
        stem = re.sub(r"[^\w-]+", "-", req.feature_id).strip("-")[:40] or "imported"
        fname, n = f"{stem}.stl", 2
        # same name + same bytes -> reuse the file; different bytes -> suffix
        while (blocks.IMPORTS_DIR / fname).exists() \
                and (blocks.IMPORTS_DIR / fname).read_bytes() != data:
            fname, n = f"{stem}-{n}.stl", n + 1
        if not (blocks.IMPORTS_DIR / fname).exists():
            (blocks.IMPORTS_DIR / fname).write_bytes(data)
            saved_new = blocks.IMPORTS_DIR / fname
        # validate BEFORE adding a feature — a bad file must not leave a
        # broken node in the tree (this also primes the read cache)
        part = blocks.import_stl(fname, req.scale)
        fid, n = req.feature_id, 2
        while any(f.id == fid for f in _doc().features):
            fid = f"{req.feature_id}-{n}"
            n += 1
        _doc().add(fid, "import_stl", {"file": fname, "scale": req.scale}, [])
    except Exception as e:        # decode/read/mesh errors -> honest message
        _unsnapshot()
        if saved_new is not None:
            try:
                saved_new.unlink()
            except OSError:
                pass
        return _refused(e)
    _rebuild_and_mesh()
    rep = blocks.import_stl_report(fname)
    repair_note = None
    if rep.get("repaired"):
        steps = []
        if rep.get("healed_wall_triangles"):
            steps.append(f"merged {rep['healed_wall_triangles']} coincident "
                         "wall triangles")
        if rep.get("remeshed_bodies"):
            steps.append(f"remeshed {rep['remeshed_bodies']} defective "
                         "bod" + ("y" if rep["remeshed_bodies"] == 1 else "ies"))
            # the remesh rebuilds a whole body on a voxel grid; say how far it
            # moved, since nothing else in this sentence hints that it did
            # (section 8 review: a 0.6 mm plate came back 8.7% light, silently)
            if rep.get("remesh_drift_pct", 0) >= 1.0:
                steps.append(f"which changed that body's volume by "
                             f"{rep['remesh_drift_pct']:.1f}% — check it")
        if rep["output_triangles"] < rep["input_triangles"]:
            steps.append(f"decimated {rep['input_triangles']:,} → "
                         f"{rep['output_triangles']:,} triangles")
        repair_note = "auto-repaired: " + ", ".join(steps) if steps else None
    bb = part.bounding_box()
    _pending(f"imported {fname}", "tool")
    return {**_doc_json(), "import_info": {
        "feature_id": fid, "file": fname,
        "triangles": rep["output_triangles"], "bodies": rep.get("bodies"),
        "repair": repair_note,
        "size_mm": [round(bb.size.X, 2), round(bb.size.Y, 2),
                    round(bb.size.Z, 2)],
        "volume_mm3": round(part.volume, 1)}}


@app.post("/api/face-feature")
def face_feature(req: FaceFeatureReq):
    """WHICH FEATURE MADE THIS FACE (Fusion's Find in Timeline).

    Read-only: no snapshot, no rebuild, no document mutation — it walks the
    per-feature solids already cached from the last rebuild. Deliberately does
    NOT return the document (a 79-feature payload per click is waste); the
    frontend only needs the attribution."""
    try:
        return provenance.attribute_face(
            _doc(), body_id=req.body, face_index=req.face, point=req.point,
            center=req.center, area=req.area)
    except Exception as e:                  # OCP errors are NOT RuntimeError
        return {"feature": None, "reason": f"attribution failed: {e!r}"}


@app.post("/api/measure")
def measure_selection(req: MeasureReq):
    """HOW WIDE / HOW FAR / HOW THICK (Fusion's Measure).

    Read-only, like /api/face-feature: no snapshot, no rebuild, no document
    mutation — it measures the solids already cached from the last rebuild, and
    deliberately does NOT return the document (the payload per click would be
    the whole tree). Errors come back as {"error": ...} rather than a 500, so
    the readout can say why instead of going blank (rule 7)."""
    return measurelib.measure(_doc(), req.a.model_dump(),
                              req.b.model_dump() if req.b else None)


def _revert_last() -> bool:
    """Undo the snapshot this request pushed, without touching the redo stack.

    Used when a measure-driven edit fails its own verification: the user asked
    for a dimension and did not get it, so the design goes back exactly as it
    was rather than being left mid-change. Deliberately NOT the /api/undo path,
    because this was never a state the user chose to be in — offering to redo
    into it would be offering to redo into a mistake."""
    e = _entry()
    if not e["history"]:
        return False
    data = e["history"].pop()
    old = e["doc"]
    try:
        e["doc"] = Document.from_data(data)
    except ValueError:
        e["history"].append(data)      # put it back; better than losing it
        return False
    e["doc"]._cache = old._cache
    e["doc"]._spec_cache = old._spec_cache
    _rebuild_and_mesh()
    return True


@app.post("/api/measure/probe")
def measure_probe(req: MeasureProbeReq):
    """SLIDE THE MEASUREMENT (the draggable dimension line).

    Read-only like /api/measure — a probe per pointermove must never snapshot,
    rebuild, or touch the document. The value is the kernel's own minimum
    distance from the dragged point to the other selection, so the live number
    is exact, not a mesh approximation."""
    if req.b is None:
        return {"error": "probing needs two selections"}
    return measurelib.probe(_doc(), req.a.model_dump(), req.b.model_dump(),
                            req.point, req.on)


@app.post("/api/measure/set")
def measure_set(req: MeasureSetReq):
    """TYPE A DIMENSION AND THE MODEL FOLLOWS (the editable half of Measure).

    Two kinds of change, and never a guess between them:

      * a DRIVEN dimension — one that maps to a single param, like a bore's
        diameter mapping to a circle entity's radius — writes that param;
      * a DERIVED one — the gap between two independent features, a number
        stored nowhere — is changed by MOVING one side, with `side` naming
        which. Tree order picks the default (the later feature moves; the
        earlier is almost always stock or a datum) and the user can override
        it. Anything that is neither is refused with a reason.

    The write is planned before anything is touched, so a refusal leaves the
    document byte-identical. Afterwards the SAME selection is measured again and
    the achieved value reported next to the requested one: house rule 3, never
    trust, always measure. Writing a param is not proof the geometry moved."""
    plan = measurelib.plan_set(_doc(), req.a.model_dump(),
                               req.b.model_dump() if req.b else None,
                               req.value, req.side)
    if "error" in plan:
        return _refused(None, plan["error"], extra=plan)
    # what BUILDS today, so a dimension that breaks a feature can be put back
    was_ok = {f.id for f in _doc().features if f.status == "ok"}
    _snapshot()
    try:
        measurelib.write(_doc(), plan)
        _doc()._mark_stale()
    except (KeyError, ValueError, IndexError, TypeError) as e:
        _unsnapshot()          # the plan never landed
        return _refused(e, f"could not apply that: {e}")
    _hand_edit()              # AFTER it lands: a refusal is not a hand edit
    _rebuild_and_mesh()
    # VERIFY: re-measure the same PICK and say what the model actually became.
    #
    # "The same pick" cannot mean "the same index": those are array positions
    # and a rebuild reorders them, so this used to compare the requested value
    # against whatever face had inherited the number and revert a CORRECT
    # edit (section 6 review, 2026-09-10 — 7 of the 81 editable diameters
    # across eight saved designs, and the move path too). measurelib.remeasure
    # re-finds each pick by its own geometry first; `picks` names where they
    # went, so the panel can go on talking about the same two faces.
    after = measurelib.remeasure(_doc(), plan, req.a.model_dump(),
                                 req.b.model_dump() if req.b else None)
    achieved = after.get("value")
    # A pick that cannot be re-found keeps its old index, so the kind check
    # still earns its keep: measuring a different KIND of thing means this
    # verification is about some other geometry entirely.
    same_kind = after.get("kind") == plan.get("kind")
    # Compare on the grid the readout uses. `achieved` comes back rounded for
    # display (3 dp), so a raw request of 7.9375 — 5/16", and every other inch
    # size — was written PERFECTLY and then reverted for missing itself by
    # 5e-4. Round the request the same way and the comparison is honest again.
    want = measurelib._r(float(req.value))
    ok = (achieved is not None and same_kind
          and abs(float(achieved) - want) <= 1e-4)
    # A dimension is not "achieved" at the price of the design. Translating a
    # profile far enough can push it off the body it cuts, and then a feature
    # that built a moment ago stops building. That is the wreck the revert
    # below was written for; it used to be caught only by accident, because a
    # wrecked part also renumbered the faces (see remeasure). Name it.
    broke = [f.id for f in _doc().features
             if f.id in was_ok and f.status == "failed"]
    if broke:
        ok = False
    out = {k: plan[k] for k in
           ("driver", "move", "requested", "param", "was") if k in plan}
    # `picks` is where the two selections ended up in the REBUILT body, for
    # the panel to keep talking about the same faces. It is only true while
    # that body stands: the revert below puts the previous one back, ids and
    # all, so the picks must go with it (round two of the section 6 review).
    out.update({"achieved": achieved, "verified": ok})
    if ok:
        out["picks"] = after.get("picks")
    if not ok:
        # REVERT. The requested dimension is not what the model came out as, so
        # the edit did something other than what was asked — most often because
        # translating a profile that far pushes it outside the part and changes
        # the topology. Leaving that behind with only a warning means handing
        # the user a wrecked part and hoping they read the note, which is the
        # opposite of this project's whole point. Put it back and say so.
        why = (f"it would stop {broke[0]} from building" if broke else
               "the same pick now reads as "
               f"{after.get('kind') or 'nothing measurable'} instead of "
               f"{plan.get('kind')}"
               if not same_kind else
               "the model came out at "
               + (f"{achieved:g} mm" if achieved is not None else "something else"))
        out["reverted"] = _revert_last()
        out["warning"] = (
            f"asked for {req.value:g} mm but {why} — "
            + ("nothing was changed" if out["reverted"] else
               "the edit could not be undone automatically; press Ctrl+Z"))
    return {**out, **_doc_json()}


@app.post("/api/feature/remove")
def remove_feature(req: RemoveReq):
    """Delete a feature. `dry_run` returns the PLAN only, so the UI can show
    what else goes with it and ask first; the same call without dry_run then
    applies exactly that plan. The returned "remove_plan" is what the user is
    told -- a delete never quietly takes more than the node they clicked."""
    if req.dry_run:
        try:
            plan = _doc().remove_plan(req.feature_id, req.mode)
        except (KeyError, ValueError) as e:
            return _refused(e)
        return {**_doc_json(), "remove_plan": plan}
    _snapshot()
    try:
        plan = _doc().remove(req.feature_id, req.mode)
    except (KeyError, ValueError) as e:
        _unsnapshot()
        return _refused(e)
    _rebuild_and_mesh()
    if not _doc().features and MESH_PATH.exists():
        MESH_PATH.unlink()                  # last feature gone -> empty viewport
    _pending(f"deleted {req.feature_id}", "tool")
    return {**_doc_json(), "remove_plan": plan}


@app.post("/api/feature/rename")
def rename_feature(req: RenameReq):
    """Fusion's browser rename: the id is rewritten everywhere it is
    referenced (inputs, rollback bar, part cache). Geometry is untouched,
    so no rebuild — the snapshot still makes it undoable."""
    _snapshot()
    try:
        _doc().rename(req.feature_id, req.name)
    except (KeyError, ValueError) as e:
        _unsnapshot()
        return _refused(e)
    _hand_edit()              # AFTER it lands: a refusal is not a hand edit
    return _doc_json()


@app.post("/api/feature/suppress")
def suppress_feature(req: SuppressReq):
    _snapshot()
    try:
        # set_suppressed, not the flag by hand: it also drops what the last ✕
        # recorded, which another hand on this flag makes untrue (P5b review)
        _doc().set_suppressed(req.feature_id, req.suppressed)
    except KeyError as e:
        _unsnapshot()
        return _refused(e)
    _hand_edit()              # AFTER it lands: a refusal is not a hand edit
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/feature/strike")
def strike_feature(req: StrikeReq):
    """Soft delete / restore (the tree's ✕ and ↩): the geometry goes or comes
    back exactly as delete would do it, but the rows stay, struck out, and
    nothing is rewired — one click undoes it. Also a single Ctrl+Z step."""
    _snapshot()
    try:
        plan = (_doc().unstrike if req.restore else _doc().strike)(req.feature_id)
    except (KeyError, ValueError) as e:
        _unsnapshot()
        return _refused(e)
    _hand_edit()              # AFTER it lands: a refusal is not a hand edit
    _rebuild_and_mesh()
    verb = "restored" if req.restore else "struck out"
    _pending(f"{verb} {req.feature_id}", "tool")
    return {**_doc_json(), "strike_plan": plan}


def _num(v) -> bool:
    """A number inspector.verify can actually do arithmetic on.

    Not just "is it a number": round two of this review (2026-09-16) measured
    {"volume": 10**400} — a JSON integer no float can hold — walking straight
    through the type check below, because it IS an int. /api/spec answered 200
    with "OverflowError: int too large to convert to float", the value stayed
    in the document, and every later /api/edit answered the same thing: F3's
    own brick, through a shape F3's guard admitted."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except (OverflowError, TypeError):   # int too large to convert to float
        return False


def _spec_problem(key: str, v) -> str | None:
    """Why this requirement cannot be checked, as a sentence — or None.

    The endpoint used to filter the KEY set and nothing else, so a value of
    the wrong type went straight into the document and then into
    inspector.verify, which does plain arithmetic on it. Measured 2026-09-16
    (section 12 review): {"volume": "50"} answered 200 with "TypeError:
    unsupported operand type(s) for -: 'float' and 'str'", STAYED in the
    document so every later /api/edit raised the same TypeError, and was
    written into the design file by the next save — a design nothing in the
    app could open and edit again. A degenerate value must be refused where
    the mistake is (shared rule 5)."""
    if key in ("volume", "tip_radius", "tol", "vol_tol"):
        return None if _num(v) else f"'{key}' must be a number, not {v!r}"
    if key in ("n_solids", "symmetry"):
        return (None if isinstance(v, int) and not isinstance(v, bool)
                else f"'{key}' must be a whole number, not {v!r}")
    if key == "require_manifold":
        return None if isinstance(v, bool) else \
            f"'require_manifold' must be true or false, not {v!r}"
    if key in ("size", "com"):
        if not isinstance(v, (list, tuple)) or len(v) != 3:
            return (f"'{key}' must be three values (X, Y, Z), not {v!r} — "
                    f"leave an axis empty to skip it")
        bad = [a for a, x in zip("XYZ", v) if x is not None and not _num(x)]
        return (f"'{key}' {'/'.join(bad)} must be a number or empty"
                if bad else None)
    if key == "holes":
        if not isinstance(v, dict):
            return ('"holes" must be a table of radius to count, like '
                    f'{{"4": 6}} — not {v!r}')
        for r, n in v.items():
            # OverflowError too, and isfinite on both halves: "int too large
            # to convert to float" is raised BY THE CHECK on 10**400 and by
            # inspector.verify on the value it let through (round two).
            try:
                if not math.isfinite(float(r)):
                    raise ValueError
                if int(n) != float(n):
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                return ('"holes" must be a table of radius to count, like '
                        f'{{"4": 6}} — {r!r}: {n!r} is not')
    return None


@app.post("/api/spec")
def set_spec(req: SpecReq):
    """Edit the design's requirements — the legitimate way to change intent
    (e.g. actually wanting 9 blades) instead of fighting the verifier."""
    known = {"size", "volume", "holes", "n_solids", "symmetry", "tip_radius",
             "com", "require_manifold", "tol", "vol_tol"}
    spec = {k: v for k, v in req.spec.items() if k in known and v is not None}
    for k, v in spec.items():
        problem = _spec_problem(k, v)
        if problem:
            return _refused(None, f"that requirement cannot be checked: "
                                  f"{problem}")
    _hand_edit()
    _snapshot()
    doc = _doc()
    doc.spec = spec
    doc._mark_stale()
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/undo")
def undo():
    e = _entry()
    if not e["history"]:
        return {"error": "nothing to undo", **_doc_json()}
    data = e["history"].pop()
    old_doc = e["doc"]
    try:
        rebuilt = Document.from_data(data)
    except ValueError as err:
        return {"error": f"undo failed: {err}", **_doc_json()}
    # what we are leaving becomes the thing redo puts back
    e.setdefault("redo", []).append(old_doc.to_data())
    del e["redo"][:-MAX_HISTORY]
    e["doc"] = rebuilt
    e["dirty"] = None              # undoing back to the version = clean again
    # The rebuild cache is process-wide (content-addressed), so the restored
    # document already inherits it; this keeps the link explicit for a document
    # that was given a private cache.
    e["doc"]._cache = old_doc._cache
    e["doc"]._spec_cache = old_doc._spec_cache
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/redo")
def redo():
    """Step forward again after an undo.

    User (2026-08-26): "whatever i am doing in that manual design, it can be
    easily undo and redo in that feature tree". Undo alone makes trying
    something out a one-way trip -- you can retreat but not return, so people
    stop experimenting."""
    e = _entry()
    if not e.get("redo"):
        return {"error": "nothing to redo", **_doc_json()}
    data = e["redo"].pop()
    old_doc = e["doc"]
    try:
        rebuilt = Document.from_data(data)
    except ValueError as err:
        return {"error": f"redo failed: {err}", **_doc_json()}
    e["history"].append(old_doc.to_data())      # ...and redo is undoable again
    del e["history"][:-MAX_HISTORY]
    e["doc"] = rebuilt
    e["dirty"] = None
    e["doc"]._cache = old_doc._cache
    e["doc"]._spec_cache = old_doc._spec_cache
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/rollback")
def rollback(req: RollbackReq):
    """Drag the rollback bar: feature_id = build only up to there;
    null = back to full build. A view, not an edit — no history entry."""
    doc = _doc()
    doc.rollback = req.feature_id
    doc._mark_stale()
    _rebuild_and_mesh()
    return _doc_json()


# ---------------------------------------------------------------------------
# Library, samples, export
# ---------------------------------------------------------------------------

def _design_slug(name: str) -> str:
    """The library file name a design goes under — ONE rule for every file
    written into designs/ under a design's name.

    The save has always used it; `mcp_server._safe_name` is the same rule; the
    STEP export used the RAW name until the section 12 review (2026-09-16), so
    a design called "cam cover plaque" saved as cam-cover-plaque.tcad.json and
    exported as "cam cover plaque.step" while the MCP, exporting the very same
    design, wrote cam-cover-plaque.step — the twin-file trap the export exists
    to avoid."""
    return re.sub(r"[^\w\-]+", "-", name).strip("-") or "untitled"


def _name_clash(slug: str, deed: str) -> str | None:
    """The sentence refusing to write designs/<slug>.* on the ACTIVE tab's
    behalf, or None when this tab owns that name.

    A write must never land on SOMEONE ELSE'S design. File > New accepts any
    name, and the slug rule collapses a natural one onto an existing file
    without any exact typing ("cam cover plaque" -> cam-cover-plaque; this
    filesystem is case-insensitive, so "Cam Cover Plaque" hits it too). For the
    SAVE that overwrote the other design's .tcad.json AND appended this content
    to its version tree (section 3 review, 2026-09-10, measured); for the
    EXPORT it replaced the other design's .step outright — measured
    2026-09-16, a 68455.304 mm3 flange file came back holding a 200.0 mm3
    plate, announced as a successful export (section 12 review). The tab that
    is ALREADY bound to this file may of course keep writing over it.

    `deed` is the gerund the sentence uses ("saving", "exporting")."""
    owner = _file_owner(slug)
    # _active_tid(), not STATE["active"]: this guard is the REST of /api/save
    # and /api/export, and round three bound those two to one read of the tab
    # while this — their shared clash check, which also calls _entry() and
    # _doc() below — went on asking the live state. Measured 2026-09-16: with
    # the doorbell landing here, a save of tab A under a name tab B owns
    # passed all three doors (owner == the tab that had just become active,
    # and the source read on the next line was B's) and wrote A's document
    # over B's design file and into B's version tree.
    if owner is not None and owner != _active_tid():
        # 1. another TAB already owns this file. One tab per design is an
        # invariant everywhere else — /api/open reuses the tab instead of
        # cloning it — and this was the one place that broke it: a save of
        # identical content bound a SECOND tab to the file, after which either
        # tab's save silently overwrote the other's and hung its version off
        # the other's latest (measured: bore.radius 11 -> 44, and v3 parented
        # to a v2 it never came out of).
        return (f"'{slug}' is already open in another tab. Two tabs cannot "
                f"share one design file — switch to that tab and work there, "
                f"or give this design another name.")
    if (_entry().get("source") or "").lower() == f"file:{slug}".lower():
        return None
    path = DESIGNS / f"{slug}.tcad.json"
    if path.exists():
        # 2. a DIFFERENT design already holds the name. Content that is
        # exactly what the file holds is still fine — nothing can be lost that
        # way, and that is how a sample tab writes itself into the library.
        try:
            same = content_hash(json.loads(
                path.read_text(encoding="utf-8"))) == content_hash(
                    _doc().to_data())
        except Exception:
            same = False               # unreadable: assume it is someone's work
        if not same:
            return (f"There is already a different design called '{slug}', "
                    f"and {deed} here would replace it. Give this one another "
                    f"name first — or, if you meant to work on that design, "
                    f"open it from the library and make your changes in its "
                    f"tab.")
    return None


@app.post("/api/save")
def save_design():
    # ONE read of the active tab, as /api/export takes it (round three,
    # 2026-09-16). This endpoint decides a FILE NAME from the document and
    # then BINDS THE TAB to it, and each of those went to STATE["active"]
    # separately — which other threads move (the MCP doorbell's
    # /api/open/<slug>?external=1). A tab that arrives in between is left
    # pointing at a design file that is not its own; its next save then
    # overwrites that design and /api/open comes back to the wrong tab, which
    # is the section 3 P0 through a new door. Measured with a red test.
    e = _entry()
    doc = e["doc"]
    safe = _design_slug(doc.name)
    path = DESIGNS / f"{safe}.tcad.json"
    # THREE doors lead onto someone else's design; the first two are shared
    # with the export (_name_clash), the third is the version tree's own.
    clash = _name_clash(safe, "saving")
    if clash:
        return _refused(None, message=clash)
    if (e.get("source") or "").lower() != f"file:{safe}".lower():
        if not path.exists() and _saved_versions_exist(safe):
            # 3. the FILE is gone but the version tree is NOT. There is no
            # in-app delete, so a design removed in Explorer leaves
            # <slug>.history/ behind — and a new design of the same name then
            # appended itself to that tree as a child of its last version,
            # under its design_id and its name (measured: a 1-feature disc
            # became v3 of a 3-feature flange).
            return _refused(None, message=(
                f"There is no design file called '{safe}' any more, but its "
                f"saved versions are still in designs/{safe}.history/ — "
                f"saving here would add this design to that history as though "
                f"it grew out of it. Give this one another name, or delete "
                f"that folder if those versions are no longer wanted."))
    doc.save(str(path))
    # bind this tab to the file it just wrote (it may not have had a source, or
    # may have been saved under a new name) so opening that design later comes
    # back HERE instead of cloning the tab
    e["source"] = f"file:{safe}"
    # AFTER the source is bound, so a first-ever save starts the history under
    # the name it was just written as
    return {"saved": safe, **_record_version("saved", "save"), **_doc_json()}


@app.get("/api/versions")
def get_versions():
    """The design's version tree. Separate from /api/doc on purpose: the index
    grows with every version and /api/doc is answered on every keystroke."""
    h = _vhistory()
    if h is None:
        return {"versions": [], "current": None, "starred": None,
                "problems": [], "unsaved": True, "dirty": _dirty(_entry()),
                "note": "this design has no history yet — save it once and its "
                        "versions start being recorded"}
    return {"versions": [asdict(v) for v in h.versions()],
            "current": h.current(), "starred": h.starred(),
            "problems": h.problems(), "design_id": h.design_id,
            "name": h.name, "tree": h.tree_lines(), "unsaved": False,
            "dirty": _dirty(_entry()),
            # so the push button can say "push v16" BEFORE the user commits
            "next_id": h.next_id(),
            # the index is unusable but the versions themselves survive: the
            # panel offers the rebuild. The SERVER decides this (R1) — the
            # browser must not go parsing the problem sentences for it.
            "can_repair": h.can_repair()}


@app.get("/api/versions/diff")
def version_diff(target: str, base: str | None = None):
    """What changed in one version, against its parent by default.

    On demand rather than precomputed for the whole list: answering it means
    decompressing two snapshots, and the panel refreshes whenever the document
    changes. The same reason problems() is shallow."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    try:
        v = h.get(target)
        frm = base or v.parent
        if frm is None:
            return {"target": target, "base": None, "added": [], "removed": [],
                    "changed": [], "spec_changed": False, "renamed": None,
                    "summary": "the first version — nothing before it to "
                               "compare against"}
        out = diff_snapshots(h.snapshot(frm), h.snapshot(target))
    except HistoryError as e:
        return {"error": str(e)}
    return {"target": target, "base": frm, **out}


@app.post("/api/versions/restore")
def restore_version(req: VersionReq):
    """Put an old version back on screen, in THIS tab.

    Three things it deliberately does not do:
      * it does not write designs/<slug>.tcad.json — the user's saved design
        stays as it is until they explicitly save (their decision);
      * it does not truncate the tree — set_current() moves the marker, so the
        NEXT edit branches off this version and v4..v10 survive;
      * it does not lose what was on screen — the outgoing state goes on the
        undo stack, so restoring is undoable like anything else.
    """
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first",
                **_doc_json()}
    if not req.id:
        return {"error": "which version? pass an id like 'v3'", **_doc_json()}
    e = _entry()
    # Fast path: the tab already HOLDS this content (clicking the version you
    # are on, or an identical A->B->A node). Rebuilding the esp32 case for
    # ~30 s to arrive exactly where you already are is absurd (user,
    # 2026-09-01) — just move the current marker and say so. Compared by
    # hash, not by id, so a stale panel can never skip a real restore.
    try:
        target = h.get(req.id)
    except HistoryError as ex:
        return {"error": str(ex), **_doc_json()}
    if target.hash == content_hash(e["doc"].to_data()):
        out = {"restored": req.id, "already": True}
        try:
            h.set_current(req.id)
            e["hand_edits"] = 0
            e["pending"] = []
            _mark_clean()
        except HistoryError as ex:
            out["history_error"] = str(ex)
        return {**out, **_doc_json()}
    try:
        snap = h.snapshot(req.id)
    except HistoryError as e:
        return _refused(e)
    try:
        fresh = Document.from_data(snap)
    except Exception as e:
        # A version recorded before an op was renamed cannot be rebuilt by this
        # build. It STAYS in the tree as a record: refusing to open it is far
        # better than dropping it, and far better than a 500.
        return _refused(e, f"{req.id} was recorded by an older build and this "
                           f"one cannot open it ({e}). It is still in the "
                           f"history — nothing was changed.")
    e = _entry()
    _snapshot()                                  # restoring is undoable
    e["doc"] = fresh
    _rebuild_and_mesh()
    out = {"restored": req.id}
    try:
        h.set_current(req.id)
        # the doc on screen IS that version now — not dirty — and any pending
        # notes described edits that just went onto the undo stack
        e["hand_edits"] = 0
        e["pending"] = []
        _mark_clean()
    except HistoryError as ex:
        out["history_error"] = str(ex)
    return {**out, **_doc_json()}


@app.post("/api/versions/star")
def star_version(req: VersionReq):
    """Pin the one version the user actually means, or unpin with id=null.

    This is the answer to "we do not know which is my intended design".
    Recency cannot answer it — v10 is not automatically better than v7 — so
    exactly one version per design carries the mark."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    try:
        h.star(req.id)
    except HistoryError as e:
        return {"error": str(e)}
    return {"starred": h.starred()}


@app.post("/api/versions/amend")
def amend_version():
    """Save the tab's changes INTO the current version — no new version.

    The user's choice when a round of edits is done (2026-09-01): "i can
    decide whether i want to save those changes [into v15], or push the
    changed design to new version v16". This is the first option: the design
    file is written and the current version's snapshot is rewritten in place.
    history.amend() refuses a version that has children (rewriting it would
    change what every child's diff means) and names the way out."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once "
                         "first", **_doc_json()}
    e = _entry()
    doc = e["doc"]
    try:
        v = h.amend(doc.to_data(), spec=_measured(e),
                    rebuildable=bool(e.get("ok")))
    except HistoryError as ex:
        return {"error": str(ex), **_doc_json()}
    # the amend is the risky half; only now touch the design file
    slug = _slug_of_active()
    doc.save(str(DESIGNS / f"{slug}.tcad.json"))
    e["hand_edits"] = 0
    e["pending"] = []
    _mark_clean()
    return {"amended": v.id, "saved": slug, **_doc_json()}


@app.post("/api/versions/delete_after")
def delete_after_version(req: VersionReq):
    """Delete every version that descends from req.id — "keep v15, the rest
    I don't need". One confirmed click instead of thirty refused ones; the
    guard rails (current/starred below the cut) live in history.delete_after
    and each names its way out. Resets the numbering so the next push
    continues from what remains (v15 -> v16)."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    if not req.id:
        return {"error": "which version? pass an id like 'v15'"}
    try:
        return h.delete_after(req.id)
    except HistoryError as e:
        return {"error": str(e)}


@app.post("/api/versions/delete")
def delete_version(req: VersionReq):
    """Permanently remove one version — the user's explicit click.

    history.delete() carries the guard rails: the current and the starred
    version are refused with the way out named, children of the deleted node
    are re-pointed at its parent (nothing is orphaned), and the id is never
    reused. The DESIGN is untouched — this edits the record, not the part."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    if not req.id:
        return {"error": "which version? pass an id like 'v3'"}
    try:
        return h.delete(req.id)
    except HistoryError as e:
        return {"error": str(e)}


@app.post("/api/versions/repair")
def repair_history():
    """Rebuild a lost or unreadable version index from the snapshots.

    The recovery existed but nothing could reach it: when index.json goes,
    the panel said "History.repair() rebuilds an index from them" — a Python
    method, to a user who does not write Python, for data that really is
    recoverable (section 3 review, 2026-09-10). Now it is a button.

    Refused on a healthy history, because repair GUESSES: the real parent
    links died with the index, so it rebuilds one straight line with
    "(recovered)" labels and no star. Running it on a working tree would
    throw away information nothing can get back."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    # Two very different noes, and giving the wrong one is worse than giving
    # none: the tree is FINE, or it is unusable in a way a rebuild cannot
    # help (an index from a NEWER build; no snapshots left). Only the first is
    # answered here; the second is `repair()`'s own refusal, which names the
    # actual fault. Answering both with "your version list is readable" was
    # the opposite of the truth (fix-pass review, 2026-09-10).
    if h.exists():
        return {"error": "nothing to repair — this design's version list is "
                         "readable. (Rebuilding can only guess a straight "
                         "line of versions, so it never runs on a working "
                         "history.)"}
    try:
        notes = h.repair()
    except HistoryError as e:
        return {"error": str(e)}
    return {"repaired": True, "recovered": len(h.versions()), "notes": notes}


@app.post("/api/versions/label")
def label_version(req: LabelReq):
    """Rename a version. Auto-labels say what happened ("saved", "extrude
    added"); this is how a version gets called "the one for the mill"."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    try:
        h.relabel(req.id, req.label)
    except HistoryError as e:
        return {"error": str(e)}
    return {"labelled": req.id, "label": req.label}


class BugReq(BaseModel):
    note: str = ""                   # the user's one line, may be empty
    screenshot: str | None = None    # data-URL PNG of the viewport canvas
    requests: list = []              # the tab's last calls: method, url, body, status, ms
    console: list = []               # window errors + the warnings the chat showed
    ui_build: str = ""               # the tab's "ui vN" stamp


def _bug_report_lines(d: Path, req: BugReq, doc: Document, e: dict, files: list[str]) -> list[str]:
    reds = [f"- '{f.id}' ({f.op}): " + ("; ".join(f.problems) or "no problem text")
            for f in doc.features if f.status != "ok" and not f.suppressed]
    lines = [f"# Bug report: {doc.name}", "", f"Filed from the app at {time.strftime('%Y-%m-%d %H:%M:%S')}"
             + (f", tab running {req.ui_build}" if req.ui_build else "") + ".", ""]
    lines += ["## What the user said", "", f"> {req.note.strip() or '(no note)'}", ""]
    lines += ["## The design", "",
              f"{len(doc.features)} features, {len(doc.leaf_solid_ids())} bodies on screen, "
              f"{'healthy' if e.get('ok') else 'with red features'}; opened from "
              f"{e.get('source') or 'nothing (a new design)'}; {len(e.get('history') or [])} undo steps.", ""]
    if reds:
        lines += ["Red features:", "", *reds, ""]
    if req.requests:
        # NOT every request: bugreport.js drops a read that succeeded, or the
        # 3-second live watcher's GET /api/doc would be the whole ring within
        # two minutes and the step being reported would be gone (P5b review
        # round one). So this is the ACTIONS, plus any read that failed —
        # saying "every request" would invite the wrong conclusion from a tab
        # that looks like it never loaded a mesh.
        lines += ["## The last things this tab did (oldest first; a read that "
                  "succeeded is not kept)", ""]
        for r in req.requests[-15:]:
            if not isinstance(r, dict):
                continue
            body = r.get("body")
            body = (str(body)[:160]) if body else ""
            lines.append(f"- `{r.get('method', '?')} {r.get('url', '?')}` -> {r.get('status', '?')} "
                         f"in {r.get('ms', '?')} ms" + (f"  `{body}`" if body else ""))
        lines.append("")
    if req.console:
        lines += ["## What the browser reported", ""]
        lines += [f"- {str(c.get('text') if isinstance(c, dict) else c)[:300]}" for c in req.console[-15:]]
        lines.append("")
    lines += ["## Files", "", *[f"- `{f}`" for f in files], "",
              "## Reproduce", "",
              f"    python tests/journeys.py --replay bugs/{d.name}", "",
              "That opens `doc.tcad.json` in a fresh in-process server and runs the body "
              "checks; `state.json` carries the tree with every status and problem sentence "
              "as the user saw it. Open the design in Studio to look at it in 3D.", ""]
    return lines


@app.post("/api/bug")
def report_bug(req: BugReq):
    """The bug button (LAUNCH-PLAN.md P5b): ONE click saves the open design,
    the tab's last requests, what the browser reported and a screenshot
    under bugs/, and the user keeps designing. A later chat reads the folder
    and has the repro without a description. Reads the document, never
    writes it — no snapshot, no rebuild, no version."""
    e = _entry()
    doc = e["doc"]
    d = BUGS / f"{time.strftime('%Y%m%d-%H%M%S')}-button-{re.sub(r'[^\w\-]+', '-', doc.name).strip('-').lower()[:40] or 'untitled'}"
    d.mkdir(parents=True, exist_ok=True)
    files = ["doc.tcad.json", "state.json", "report.md"]
    (d / "doc.tcad.json").write_text(json.dumps(doc.to_data(), indent=1), encoding="utf-8")
    skipped = None
    if req.screenshot:
        try:
            raw = base64.b64decode(req.screenshot.split(",", 1)[-1], validate=False)
            if raw[:8] == b"\x89PNG\r\n\x1a\n":
                (d / "screenshot.png").write_bytes(raw)
                files.append("screenshot.png")
            else:
                skipped = "the screenshot was not a PNG"
        except (ValueError, TypeError) as ex:
            skipped = f"the screenshot could not be decoded: {ex}"
    state = {"note": req.note, "when": time.strftime("%Y-%m-%d %H:%M:%S"),
             "ui_build": req.ui_build, "source": e.get("source"),
             "undo_depth": len(e.get("history") or []), "screenshot_skipped": skipped,
             "doc": _doc_json(), "requests": req.requests[-40:], "console": req.console[-40:]}
    (d / "state.json").write_text(json.dumps(jsonable_encoder(state), indent=1, default=str),
                                  encoding="utf-8")
    (d / "report.md").write_text("\n".join(_bug_report_lines(d, req, doc, e, files)), encoding="utf-8")
    saved = d.relative_to(ROOT).as_posix() if d.is_relative_to(ROOT) else d.as_posix()
    return {"saved": saved, "files": files, "screenshot_skipped": skipped}


@app.get("/api/examples")
def get_examples():
    """The curated gallery: the designs actually built in this tool, grouped.

    Read from designs/examples.json so the list is data, not code — adding a
    design to the gallery is an edit to that file. Entries whose .tcad.json has
    gone are dropped rather than shown as dead tiles, and the feature count is
    taken from the file itself so it cannot drift from the catalog."""
    cat = DESIGNS / "examples.json"
    if not cat.exists():
        return {"groups": []}
    try:
        data = json.loads(cat.read_text(encoding="utf-8"))
    except Exception as e:
        return {"groups": [], "error": f"examples.json is malformed: {e}"}
    groups = []
    for g in data.get("groups", []):
        designs = []
        for d in g.get("designs", []):
            path = DESIGNS / f"{d.get('file', '')}.tcad.json"
            if not path.exists():
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                feats = doc.get("features", [])
            except Exception:
                continue
            designs.append({**d,
                            "name": doc.get("name", d["file"]),
                            "features": len(feats),
                            "preview": (DESIGNS /
                                        f"{d['file']}-preview.png").exists()})
        if designs:
            groups.append({"group": g.get("group", ""),
                           "blurb": g.get("blurb", ""), "designs": designs})
    return {"groups": groups}


@app.get("/api/design-preview/{file}")
def design_preview(file: str):
    """Thumbnail for a gallery tile. designs/ is not statically served (it holds
    the user's work, not web assets), so previews come through here."""
    safe = re.sub(r"[^\w\-]", "", file)
    png = DESIGNS / f"{safe}-preview.png"
    if not png.exists():
        return Response(status_code=404)
    return Response(content=png.read_bytes(), media_type="image/png")


@app.get("/api/designs")
def list_designs():
    out = []
    for p in sorted(DESIGNS.glob("*.tcad.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({"file": p.stem.replace(".tcad", ""),
                        "name": data.get("name", p.stem),
                        "features": len(data.get("features", []))})
        except Exception:
            continue
    return out


@app.post("/api/open/{file}")
def open_design(file: str, external: bool = False):
    """Open from the library, REUSING this design's tab if it already has one.

    `external=1` marks the call as the MCP doorbell — a design that arrived
    from outside the browser, which the open page announces ONCE (see ARRIVAL).
    The UI's own Open dialog leaves it off: the user who clicked the design
    does not need to be told it arrived.

    This used to make a new tab every time, unconditionally. The design loop is
    "regenerate the script -> POST /api/open/<name> -> look at it in 3D", so ten
    iterations left ten identically-named tabs and no way to tell which was
    which (user, 2026-08-26: "we do not know which is my intended design").

    The FILE is the source of truth here, so a tab whose design has moved on is
    reloaded rather than left stale — that refresh is the entire point of the
    loop. The state the tab held is pushed onto its undo stack first, so
    reloading can never silently discard unsaved work.

    If the file matches what the tab already shows, only the switch happens: a
    97-feature design costs ~45 s to rebuild and it would buy nothing."""
    path = DESIGNS / f"{file}.tcad.json"
    if not path.exists():
        return {"error": f"no saved design '{file}'"}
    fresh = Document.load(str(path))
    tid = _find_tab(f"file:{file}")
    if tid is None:
        tid = _new_tab(fresh, source=f"file:{file}")
        if external:
            _note_arrival(tid, fresh.name, file)
        _rebuild_and_mesh()
        return {"tab_reused": False, "reloaded": False,
                **_record_version(f"opened {file}", "open"), **_doc_json()}
    e = STATE["docs"][tid]
    _activate(tid)
    if external:
        _note_arrival(tid, fresh.name, file)
    if e["doc"].to_data() == fresh.to_data():
        e["mesh_stale"] = True
        return {"tab_reused": True, "reloaded": False, **_doc_json()}
    e["history"].append(e["doc"].to_data())
    del e["history"][:-MAX_HISTORY]
    e["doc"] = fresh
    e["dirty"] = None            # doc replaced; recompute if the mint fails
    _rebuild_and_mesh()
    # the OUTGOING tab state is deliberately NOT recorded: it was never saved,
    # the undo stack already holds it, and minting versions for scratch states
    # is the version-explosion the user ruled out
    return {"tab_reused": True, "reloaded": True,
            **_record_version("reloaded from disk", "open"), **_doc_json()}


@app.post("/api/sample/{name}")
def load_sample(name: str):
    """Open a built-in example, reusing its tab if it is already open.

    No reload branch here, unlike a library design: a sample has no file that
    can move on, so an already-open one is simply switched to, edits and all.
    Clicking Flange twice must not give you two flanges, and must not throw
    away what you did to the first one either. File > New gets a clean one."""
    if name not in SAMPLES:
        return _refused(None, f"unknown sample '{name}'")
    tid = _find_tab(f"sample:{name}")
    if tid is not None:
        _activate(tid)
        STATE["docs"][tid]["mesh_stale"] = True
        return {"tab_reused": True, **_doc_json()}
    _new_tab(SAMPLES[name](), source=f"sample:{name}")
    _rebuild_and_mesh()
    return {"tab_reused": False, **_doc_json()}


@app.get("/api/sketch/kinds")
def sketch_kinds():
    """Which dimensions each sketch shape has, so the feature tree can offer
    real editable fields (width/height/diameter) instead of a JSON blob."""
    return sketchlib.entity_schema()


@app.get("/api/ops")
def get_ops():
    """The legal operation catalog — feeds the UI's Add Feature dialog."""
    return author.op_catalog()


@app.post("/api/export")
def export_step():
    """Export the ACTIVE design as STEP and PROVE what was written.

    The file goes to designs/<slug>.step — the same canonical place the MCP
    builds write (`mcp_server._safe_name` is `_design_slug`) — so a design has
    ONE .step on disk, not a root copy and a designs/ copy quietly diverging
    (2026-08-31: the stale twin of that pair is what a CAM import picked up).
    The name is the design's SLUG, and the same two collision doors the save
    has apply: until the section 12 review (2026-09-16) this used the raw
    doc.name, so "cam cover plaque" exported beside the MCP's own
    cam-cover-plaque.step, and a second design carrying a name already in the
    library replaced that design's .step outright — measured: a 68455.304 mm3
    flange file came back holding a 200.0 mm3 plate, announced as a
    successful export. After writing, the file itself is
    measured and the facts returned, so the UI can show what the reader of
    this file will actually get: never trust, always measure — exports
    included. A parked rollback bar or a failed body is handled/refused in
    Document.to_step rather than silently exporting an intermediate body.

    The readback measures the WHOLE file — every body in it — so `n_solids`
    is the count a CAM tool will see and `is_valid`/`is_manifold` cover all
    of them, not just the tree's tail (2026-09-07: bodies other than the
    tail never reached the file at all). rebuild() now validates every body
    of the design too, so this readback is the second, independent proof —
    taken from the written FILE rather than from the shapes in memory.
    """
    # ONE read of the active tab, for BOTH halves of "which design is this".
    # The endpoint used to call _doc() and then _slug_of_active(), and each
    # goes to STATE["active"] on its own — while the active tab is moved from
    # other threads (the MCP doorbell's /api/open/<slug>?external=1, a second
    # browser window). Two reads means the geometry can come from one design
    # and the file name from another: designs/beta.step holding alpha's
    # solid, announced as a successful export. The window is a scheduler
    # slot, not a user action — this binds it shut rather than betting on it
    # (round three, 2026-09-16).
    e = _entry()
    doc = e["doc"]
    # The FILE this design already lives in, when it has one. A design opened
    # from the library is bound to designs/<stem>.tcad.json and its one .step
    # belongs beside it; only a tab with no file of its own (untitled, a
    # sample, an AI's new design) is named by what it is CALLED.
    #
    # Round one of this review keyed it off doc.name alone, and the two drift:
    # measured over the user's own 50 designs (round two, 2026-09-16,
    # probes/section12_round2_export_probe.py), FOUR carry a name that does not
    # slug to their own stem — and on two of them Export was then REFUSED
    # outright, because designs/esp32-remote-live-t2.tcad.json is named
    # "esp32-remote" and a DIFFERENT design already holds that name. The other
    # two exported beside their own design file under another spelling
    # (bottle_cap_28mm.tcad.json -> bottle-cap-28mm.step), which is the
    # twin-file trap this export exists to avoid.
    slug = _slug_of_active(e) or _design_slug(doc.name)
    clash = _name_clash(slug, "exporting")
    if clash:
        return _refused(None, message=f"{clash} (designs/{slug}.step is that "
                                      f"design's export.)")
    path = str(DESIGNS / f"{slug}.step")
    # to_step REBUILDS (twice, when an editor has the rollback bar parked) and
    # the readback reads a STEP file: four OCCT calls, none of which used to
    # take this lock. The one-writer middleware does not cover them — an AI
    # "create" job builds in a tab of its OWN, so it is not the ACTIVE tab and
    # Export stays clickable throughout (section 12 review, 2026-09-16).
    with _KERNEL_LOCK:
        try:
            doc.to_step(path)
        except Exception as e:                   # noqa: BLE001 - OCP too
            return _refused(e)
        m = inspector.measure(path)
    return {"path": path, "n_solids": m.get("n_solids"),
            "volume": m.get("volume"), "size": m.get("size"),
            "is_valid": m.get("is_valid"),
            "is_manifold": m.get("is_manifold"),
            # what to_step WROTE, counted inside it while the rollback bar was
            # released. Counting here instead reported the parked build state:
            # with an editor open the file held every body and the response
            # said "1", so the sentence about them never appeared.
            "bodies": doc.exported_bodies}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Chat jobs — the AI uses the tools, one verified step at a time (P5)
# ---------------------------------------------------------------------------
# A "create" or "add" request is a JOB: the step loop (author.author_steps)
# runs in its own thread for as long as the model needs, the browser follows
# it through GET /api/chat/job/<id>, and every step lands in the tree as it
# is verified. Each kernel step takes the kernel lock and an in-flight
# marker, so a crash inside it is attributed and no session checkpoint holds
# a half-applied feature (the rule the POST middleware follows).

JOBS: dict[str, dict] = {}
_JOB_SEQ = itertools.count(1)
JOB_THREADS = True          # tests set False: the job runs before the reply


@contextlib.contextmanager
def _step_guard(job: dict):
    job["step"] += 1
    rid = next(_INFLIGHT_SEQ)
    with _INFLIGHT_LOCK:
        _INFLIGHT[rid] = {"method": "AI", "path": f"/api/chat step {job['step']}",
                          "at": time.time()}
        _write_inflight()
    try:
        with _KERNEL_LOCK:
            yield
    finally:
        if _clear_inflight(rid) and SESSION_ENABLED:
            _persist_session()


def _start_job(kind: str, description: str, tid: str, model,
               before: dict | None = None) -> dict:
    job = {"id": f"j{next(_JOB_SEQ)}", "kind": kind, "description": description,
           "tab": tid, "model": model, "before": before, "step": 0,
           "log": [], "done": False, "reply": None}
    JOBS[job["id"]] = job
    del_ids = list(JOBS)[:-20]          # a handful of finished jobs is enough
    for k in del_ids:
        if JOBS[k]["done"]:
            del JOBS[k]
    if JOB_THREADS:
        threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    else:
        _run_job(job)
    return job


def _job_on(tid: str | None) -> dict | None:
    """The unfinished chat job building in this tab, if any.

    Over a SNAPSHOT of the registry: this is called from the event loop
    (the one-writer middleware) while _start_job prunes JOBS in a request
    thread, and "dictionary changed size during iteration" there is a bare
    500 the browser cannot read (measured 2026-09-11)."""
    if tid is None:
        return None
    return next((j for j in list(JOBS.values())
                 if not j["done"] and j["tab"] == tid), None)


def _changed_params(before: dict, doc: Document) -> list[str]:
    """'base.width' for every parameter the job rewrote on a feature that was
    already there — so the reply can name what it actually did."""
    old = {f["id"]: (f.get("params") or {}) for f in before["features"]}
    out = []
    for f in doc.features:
        was = old.get(f.id)
        if was is not None and was != f.params:
            out += [f"{f.id}.{k}" for k in f.params if was.get(k) != f.params.get(k)]
    return out


def _run_job(job: dict) -> None:
    """Run one chat job and ALWAYS finish it.

    A thread that died without setting `done` left GET /api/chat/job
    answering done=False for ever, and the browser's follow loop has no way
    of knowing: an "add" job holds the busy overlay while it polls, so one
    unhandled exception locked the viewport until a reload (measured
    2026-09-11). Everything the job does now sits inside this barrier."""
    try:
        job["reply"] = _job_steps(job)
    except Exception as ex:               # noqa: BLE001 — deliberate barrier
        import traceback
        traceback.print_exc()
        job["log"].append(f"the AI step loop stopped: {ex}")
        job["reply"] = (f"The AI step loop stopped: {type(ex).__name__}: {ex}. "
                        f"Nothing further was changed — Undo (Ctrl+Z) if the "
                        f"design looks wrong.")
    finally:
        job["done"] = True
        if SESSION_ENABLED and not _INFLIGHT:
            _persist_session()


def _job_steps(job: dict) -> str:
    e = STATE["docs"].get(job["tab"])
    if e is None:                # closed in the blink before the thread ran
        return ("That design's tab was closed before I could start — nothing "
                "was built.")
    doc = e["doc"]

    def on_step(ev):
        job["log"].append(ev["text"])
        e["ok"] = ev["ok"]

    try:
        finished, transcript = author.author_steps(
            doc, job["description"], job["model"], on_step=on_step,
            guard=lambda: _step_guard(job),
            max_seconds=author.MAX_SECONDS)   # the tab is read-only meanwhile
    except Exception as ex:      # the model's transport; kernel trouble is a sentence
        finished, transcript = False, [f"the model failed: {ex}"]
        job["log"].append(transcript[-1])
    n = len(doc.features)
    why = transcript[-1] if transcript else "no reply from the model"
    if job["kind"] == "create":
        if finished:
            reply = (f'Designed "{doc.name}" — {n} features, each verified as it '
                     f'was added. It is waiting in its own tab; your current '
                     f'design is untouched. Click the "{doc.name}" tab when you '
                     f'want it.')
        elif n:
            reply = (f'I could not finish "{doc.name}": {why} The {n} verified '
                     f'feature(s) so far are in its own tab — finish it by hand '
                     f'or ask again. Your current design is untouched.')
        else:
            # Nothing was built, so there is nothing to keep: the tab is the
            # job's own, was never activated, and an empty "designing…" left
            # on the strip is litter the user has to tidy (measured). It stays
            # if the user has SWITCHED to it — closing the tab somebody is
            # looking at is not ours to do — and the sentence then has to say
            # so: round three said "I have closed the empty tab" either way,
            # with the tab still on the strip (measured 2026-09-11).
            closed = (job["tab"] in STATE["docs"] and job["tab"] != STATE["active"]
                      and len(STATE["docs"]) > 1)
            if closed:
                del STATE["docs"][job["tab"]]
            return (f'I could not design it: {why} Nothing was built, so '
                    + ("I have closed the empty tab."
                       if closed else "its tab is empty — close it when you "
                                      "like.")
                    + " Your current design is untouched.")
        _pending(f"AI designed {doc.name}", "ai", e)
    elif finished and doc.to_data() == job["before"]:
        _unsnapshot(e)                    # nothing changed: no undo step either
        reply = (f'I finished without changing "{doc.name}" — the last thing the '
                 f'steps said: {why}')
    elif finished:
        # What it ACTUALLY did, by comparing the trees. Counting from the tail
        # ("everything after feature N") called a deleted feature "one or more
        # parameters" (measured 2026-09-11) — the report has to be a diff.
        was = [f["id"] for f in job["before"]["features"]]
        now = [f.id for f in doc.features]
        added = [i for i in now if i not in was]
        gone = [i for i in was if i not in now]
        edits = _changed_params(job["before"], doc)
        bits = []
        if added:
            bits.append(f'{len(added)} feature(s), each verified as it landed: '
                        f'{", ".join(added)}')
        if edits:
            bits.append("changed " + ", ".join(edits[:6]))
        if gone:
            bits.append("removed " + ", ".join(gone))
        reply = (f'Added {"; ".join(bits) or "nothing I can name"} to '
                 f'"{doc.name}". One Undo (Ctrl+Z) takes it all back.')
        if doc.spec_problems:
            # Their own recorded requirement, and the change they asked for may
            # honestly have broken it. Never silent, never the AI's to rewrite.
            reply += (" Note: the design no longer meets the spec it records — "
                      + "; ".join(doc.spec_problems) + ".")
        _pending(f"AI added {', '.join(added) or 'edits'}", "ai", e)
    else:
        # The user's design is not left half-changed: back to the snapshot,
        # IN PLACE. Replacing e["doc"] wholesale dropped a parked rollback bar
        # (to_data does not carry it) and handed the tab a different object
        # (measured 2026-09-11).
        with _KERNEL_LOCK:
            e["ok"] = author._restore(doc, job["before"])
        _unsnapshot(e)
        reply = (f'I did NOT change "{doc.name}": {why} Try naming the face, '
                 f'the position and the size more precisely.')
    # The tab has been built and checked; say so, or its dot stays the grey
    # "not loaded yet" for ever and switching to it rebuilds the whole tree.
    t0 = time.perf_counter()
    with _KERNEL_LOCK:
        e["ok"] = e["doc"].rebuild()
    e["rebuild_ms"] = round((time.perf_counter() - t0) * 1000)
    e["mesh_stale"] = True
    return reply


@app.get("/api/chat/job/{jid}")
def chat_job(jid: str):
    """Where a step-by-step chat job stands: its log so far, whether it is
    done, its closing sentence — and the active document, read between
    steps so the browser never sees a half-rebuilt tree."""
    job = JOBS.get(jid)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "no such job"})
    with _KERNEL_LOCK:
        doc_json = _doc_json()
    return {"job": jid, "kind": job["kind"], "tab": job["tab"],
            "done": job["done"], "log": list(job["log"]), "reply": job["reply"],
            **doc_json}


@app.post("/api/chat")
def chat(req: ChatReq):
    intent = chat_intent(req.message)

    if intent.get("action") in ("create", "add"):
        model = _make_model()
        if model is None:
            return {"reply": "Designing needs an API key (OPENROUTER_API_KEY).",
                    **_doc_json()}
        desc = intent.get("description") or req.message
        if intent["action"] == "create" and len(STATE["docs"]) >= MAX_TABS:
            # /api/new has always refused here; the AI door did not, so asking
            # for designs opened tab 13, 14, 15... (measured 2026-09-11).
            return {"reply": f"There are already {MAX_TABS} tabs open — close "
                             f"one and ask again, and I will design it in a "
                             f"tab of its own.", **_doc_json()}
        if intent["action"] == "create":
            # A NEW design goes in a NEW tab and must NOT steal the one the
            # user is working in (user, 2026-08-26: "even my current tab is
            # being taken for that design ... that should not disturb other
            # tabs"). The tab is opened first, so the tree grows in it while
            # the job runs; the user switches to it when they choose.
            tid = _new_tab(Document(name="designing…"), activate=False)
            job = _start_job("create", desc, tid, model)
            reply = ("Designing it step by step in its own tab — every feature "
                     "shows here as it is verified; your current design is "
                     "untouched. Click the new tab to watch it grow.")
        else:
            # ADD to the design on screen: one snapshot, so a single Undo
            # takes the whole AI change back; a job that gives up restores it.
            _snapshot()
            e = _entry()
            tid = _active_tid()       # the tab _snapshot() just pushed onto
            job = _start_job("add", desc, tid, model, before=e["history"][-1])
            reply = ("Adding to this design step by step — every feature is "
                     "verified as it lands. One Undo takes it all back.")
        return {"reply": job["reply"] or reply, "job": job["id"],
                "job_done": job["done"],
                "new_tab": tid if intent["action"] == "create" else None,
                **_doc_json()}

    if intent.get("action") == "delete":
        fid = intent.get("feature_id")
        if not fid:
            return {"reply": "Which feature should I delete? Name it as it "
                             "appears in the tree.", **_doc_json()}
        try:                                 # look before leaping (dry run)
            plan = _doc().remove_plan(fid)
        except (KeyError, ValueError) as e:
            return {"reply": f"I could not delete that: {e}", **_doc_json()}
        if len(plan["deleted"]) > CHAT_DELETE_LIMIT:
            # a chat message is a poor place to approve a demolition: show the
            # damage and make the user do it deliberately in the tree
            return {"reply": f"I did NOT touch the design: '{fid}' is holding "
                             f"up most of it. {plan['summary']} If you really "
                             f"want that, click the x on '{fid}' in the tree "
                             f"and confirm.",
                    "remove_plan": plan, **_doc_json()}
        _snapshot()
        try:
            plan = _doc().remove(fid)
        except (KeyError, ValueError) as e:
            _unsnapshot()
            return {"reply": f"I could not delete that: {e}", **_doc_json()}
        _rebuild_and_mesh()
        state = "PASS" if _entry()["ok"] else "FAILED verification"
        said = plan["summary"].replace("Delete ", "Deleted ", 1)
        _pending(f"AI deleted {fid}", "ai")
        return {"reply": f"{said} Rebuilt: {state}. Undo (Ctrl+Z) "
                         f"puts it all back.",
                "remove_plan": plan, **_doc_json()}

    for _ in range(2):                       # one repair retry, same philosophy
        if intent.get("action") != "edit":
            return {"reply": intent.get("text", "…"), **_doc_json()}
        _snapshot()
        try:
            _doc().edit(intent["feature_id"], intent["param"], intent["value"])
        except (KeyError, ValueError) as e:
            _unsnapshot()
            intent = chat_intent(req.message, feedback=str(e))
            continue
        _rebuild_and_mesh()
        state = "PASS" if _entry()["ok"] else "FAILED verification"
        _pending(f"AI set {intent['feature_id']}.{intent['param']}"
                 f" = {intent['value']}", "ai")
        return {"reply": f"Set {intent['feature_id']}.{intent['param']} = "
                         f"{intent['value']} — rebuilt: {state}.",
                **_doc_json()}
    return {"reply": "I couldn't map that to an editable parameter — click "
                     "the value in the tree instead.", **_doc_json()}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("TEXTCAD_PORT", "8123"))

    # Bring back the tabs of the previous run (user mandate 2026-08-31: a
    # restart must not close the designs being worked on). With no session
    # to restore, start EMPTY (user mandate 2026-08-05: the demo flange
    # forced a "disc with bolts" on every launch). Samples stay available
    # under File -> Examples; saved work under File -> Open.
    SESSION_PATH = supervise.session_path(ROOT, port)      # per port
    SESSION_ENABLED = True
    RECOVERY = _recovery_note()
    if RECOVERY:
        print(f"Recovered from a crash of the previous server ({RECOVERY['code']}).")
    # After a STARTUP crash the tabs come back unbuilt (see _restore_session)
    # and the empty tab opened below is the one the user lands on.
    restored = _restore_session(
        rebuild=os.environ.get("TEXTCAD_SAFE_RESTORE") != "1")
    if restored:
        print(f"Restored {restored} open tab(s) from the last session.")
    if STATE["active"] is None:
        _new_tab(Document(name="untitled"))
        _rebuild_and_mesh()

    # Warm the kernel worker NOW, on a background thread, so the first fillet,
    # chamfer or shell of the session does not pay for it. Measured on the live
    # server: the first blend took 7.3 s and the shell after it 116 ms -- the
    # whole difference is `import build123d` in a fresh python (10-30 s cold).
    # An unexplained seven-second wait on the first click is the same complaint
    # the busy overlay was just taught to answer, so it is better not to have
    # it. Here and not at import: a test process that never touches geometry
    # must not spawn a worker, and the e2e tier runs `app` in a thread.
    kernelguard.warm_up()

    # The port check, the browser tab and the restart-after-crash loop live in
    # supervise.py -- what `python studio.py` actually runs.
    _watch_parent()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
