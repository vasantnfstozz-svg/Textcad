"""Section 12 ROUND FOUR - is round three's single-read fix a point repair?

Round three fixed /api/export and /api/save by reading the tab entry ONCE.
This probe asks the obvious next question: how many OTHER endpoints reach the
active tab more than once in one request, and can a tab move between those
reads put the user's work in ANOTHER DESIGN?

Run:  C:\\Python314\\python.exe probes/section12_round4_probe.py
"""
import base64
import io
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMPH = tempfile.mkdtemp(prefix="tc-r4-hist-")
os.environ["TEXTCAD_HISTORY_ROOT"] = TMPH

import numpy as np          # noqa: E402
from PIL import Image       # noqa: E402

import studio               # noqa: E402
from document import Document   # noqa: E402

LIB = Path(tempfile.mkdtemp(prefix="tc-r4-designs-"))
studio.DESIGNS = LIB
studio.SESSION_ENABLED = False


def plate(name, thickness=5.0):
    d = Document(name=name)
    d.add("base", "plate",
          {"width": 20, "depth": 20, "thickness": thickness}, [])
    return d


def logo_png(n=1400):
    """A real, busy image so the trace costs what a user's logo costs."""
    a = np.zeros((n, n, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - n / 2, xx - n / 2)
    ring = (r < n * 0.45) & (r > n * 0.18)
    spokes = ((np.arctan2(yy - n / 2, xx - n / 2) * 8) % 2) < 1.0
    a[ring | (spokes & (r < n * 0.45))] = (0, 0, 0, 255)
    buf = io.BytesIO()
    Image.fromarray(a, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def fresh_two():
    """Tab MINE (active) + tab OTHER, each bound to its own library file."""
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    plate("r4-other", 9).save(str(LIB / "r4-other.tcad.json"))
    plate("r4-mine", 5).save(str(LIB / "r4-mine.tcad.json"))
    other = studio._new_tab(Document.load(str(LIB / "r4-other.tcad.json")),
                            source="file:r4-other")
    mine = studio._new_tab(Document.load(str(LIB / "r4-mine.tcad.json")),
                           source="file:r4-mine")
    studio._rebuild_and_mesh()
    return mine, other


class Req:
    """A TracePngReq stand-in with the fields trace_png reads."""
    def __init__(self, b64):
        self.entities_only = False
        self.png_base64 = b64
        self.feature_id = "logo"
        self.height_mm = 40.0
        self.tol_mm = 0.2
        self.min_channel_mm = 0.4
        self.connect_pieces = True
        self.fit_margin = 0.9
        self.fit_box = None
        self.face_center = None
        self.face_normal = None
        self.face_area = None
        self.offset = 0.0
        self.plane = "XY"


# ---------------------------------------------------------------- part 1 ---
print("=" * 72)
print("1. HOW WIDE IS THE WINDOW in /api/trace-png?")
print("   (between _snapshot() on one tab and _doc().add() on another)")
png = logo_png()
b64 = base64.b64encode(png).decode()
mine, other = fresh_two()

marks = {}
real_snapshot = studio._snapshot
real_doc = studio._doc


def timed_snapshot():
    marks["snap"] = time.perf_counter()
    return real_snapshot()


def timed_doc():
    marks.setdefault("first_doc_after", time.perf_counter())
    return real_doc()


studio._snapshot = timed_snapshot
studio._doc = timed_doc
studio.trace_png(Req(b64))
studio._snapshot = real_snapshot
studio._doc = real_doc
width = marks["first_doc_after"] - marks["snap"]
print(f"   window = {width * 1000:.0f} ms of pure tracing between the two "
      f"reads of the active tab")

# ---------------------------------------------------------------- part 2 ---
print()
print("=" * 72)
print("2. A REAL RACE - no monkeypatch inside the window.")
print("   Thread A: POST /api/trace-png on tab MINE (r4-mine, 20x20x5)")
print("   Thread B: the MCP doorbell, POST /api/open/r4-other?external=1")
mine, other = fresh_two()
before_mine = len(studio.STATE["docs"][mine]["doc"].features)
before_other = len(studio.STATE["docs"][other]["doc"].features)
fired = {}


go = threading.Event()


def doorbell():
    """No patch of studio's own code: the thread is told WHEN the request
    starts and waits to land inside the window measured above. A DIRECT call,
    so no middleware runs — which is exactly the code as it stood."""
    go.wait()
    time.sleep(width * 0.4)
    fired["t"] = time.perf_counter()
    studio.open_design("r4-other", external=True)     # what the MCP posts


t = threading.Thread(target=doorbell)
t.start()
go.set()
studio.trace_png(Req(b64))
t.join()

after_mine = studio.STATE["docs"][mine]["doc"]
after_other = studio.STATE["docs"][other]["doc"]
print(f"   r4-mine  features: {before_mine} -> {len(after_mine.features)} "
      f"{[f.id for f in after_mine.features]}")
print(f"   r4-other features: {before_other} -> {len(after_other.features)} "
      f"{[f.id for f in after_other.features]}")
landed_wrong = any(f.id.startswith("logo") for f in after_other.features)
print(f"   >>> the traced logo landed in the OTHER design: {landed_wrong}")
if landed_wrong:
    print("   >>> and r4-mine's undo stack holds the snapshot, so Ctrl+Z on "
          "r4-other does NOT take it back")
    print(f"   >>> r4-other undo depth = "
          f"{len(studio.STATE['docs'][other]['history'])}, "
          f"r4-mine undo depth = {len(studio.STATE['docs'][mine]['history'])}")

# ---------------------------------------------------------------- part 3 ---
print()
print("=" * 72)
print("3. THE SAME SEAM on the ordinary write routes (forced move, as round")
print("   three forced its export race).")


def forced(route, call, move_at):
    """Move the active tab when `move_at` is next called, then run `call`."""
    mine, other = fresh_two()
    real = getattr(studio, move_at)
    state = {"done": False}

    def moved(*a, **kw):
        if not state["done"]:
            state["done"] = True
            studio.STATE["active"] = other       # ...from another thread
        return real(*a, **kw)

    setattr(studio, move_at, moved)
    try:
        call()
    except Exception as ex:                       # noqa: BLE001
        print(f"   {route}: raised {type(ex).__name__}: {ex}")
    finally:
        setattr(studio, move_at, real)
    m = studio.STATE["docs"][mine]["doc"]
    o = studio.STATE["docs"][other]["doc"]
    return m, o, mine, other


class FeatureReq:
    id = "boss"
    op = "plate"
    params = {"width": 4, "depth": 4, "thickness": 1}
    inputs = []


m, o, mid, oid = forced("/api/feature/add",
                        lambda: studio.add_feature(FeatureReq()), "_doc")
print(f"   /api/feature/add   -> mine {[f.id for f in m.features]}  "
      f"other {[f.id for f in o.features]}")
print(f"      the feature is in the OTHER design: "
      f"{any(f.id == 'boss' for f in o.features)}; "
      f"its undo entry is on MINE: "
      f"{len(studio.STATE['docs'][mid]['history'])}")


class EditReq:
    feature_id = "base"
    param = "thickness"
    value = 99.0


m, o, mid, oid = forced("/api/edit", lambda: studio.edit(EditReq()), "_doc")
print(f"   /api/edit          -> mine base.thickness="
      f"{m.features[0].params['thickness']}  other base.thickness="
      f"{o.features[0].params['thickness']}")

# undo: the entry is read once, but the REBUILD is a second read
m, o, mid, oid = forced("/api/undo", lambda: studio.undo(),
                        "_rebuild_and_mesh")
print(f"   /api/undo          -> rebuilt tab ok flags: mine="
      f"{studio.STATE['docs'][mid]['rebuild_ms']} "
      f"other={studio.STATE['docs'][oid]['rebuild_ms']}")


class RollbackReq:
    feature_id = "base"


m, o, mid, oid = forced("/api/rollback",
                        lambda: studio.rollback(RollbackReq()),
                        "_rebuild_and_mesh")
print(f"   /api/rollback      -> mine.rollback={m.rollback!r} "
      f"other.rollback={o.rollback!r}; the rebuild went to the other tab")

# ---------------------------------------------------------------- part 4 ---
# Everything above calls the endpoint FUNCTIONS, which is what FastAPI's
# threadpool does — but it skips the middleware, and the middleware is where
# the fix arms the per-request tab pin. So the same real race again, this time
# through the HTTP door the browser and the MCP actually use.
print()
print("=" * 72)
print("4. THE SAME REAL RACE, through the HTTP door (the fix's own path).")
from fastapi.testclient import TestClient      # noqa: E402

def http_race(delay_ms, headers=None):
    """POST /api/trace-png while the doorbell lands `delay_ms` into it.

    `_snapshot` is only TIMED here, never changed — the probe has to be able
    to say which side of the request's first read of the tab the doorbell
    fell on, because that is the whole difference between the half the server
    can fix and the half the browser must."""
    mine, other = fresh_two()
    client = TestClient(studio.app)
    seen = {}
    real = studio._snapshot

    def timed():
        seen.setdefault("pin", time.perf_counter())
        return real()

    studio._snapshot = timed
    go = threading.Event()

    def doorbell2():
        go.wait()
        # sleep, NOT a spin: a spin loop holds the GIL and starves the very
        # request it is trying to interrupt (measured — every ring landed 3
        # to 12 ms before the endpoint had even started)
        time.sleep(delay_ms / 1000.0)
        seen["ring"] = time.perf_counter()
        studio.open_design("r4-other", external=True)

    t = threading.Thread(target=doorbell2)
    t.start()
    go.set()
    r = client.post("/api/trace-png", headers=headers or {}, json={
        "png_base64": "data:image/png;base64," + b64,
        "feature_id": "logo", "height_mm": 40})
    t.join()
    studio._snapshot = real
    mine_ids = [f.id for f in studio.STATE["docs"][mine]["doc"].features]
    other_ids = [f.id for f in studio.STATE["docs"][other]["doc"].features]
    when = (seen["ring"] - seen["pin"]) * 1000 if "pin" in seen else None
    kept = ("logo" in mine_ids
            and not any(f.startswith("logo") for f in other_ids))
    print(f"   doorbell at +{delay_ms} ms "
          f"({'AFTER' if when and when > 0 else 'BEFORE'} the request's first "
          f"read of the tab, {when:+.0f} ms)"
          + (f" header={headers}" if headers else ""))
    print(f"      status {r.status_code}; r4-mine {mine_ids}  "
          f"r4-other {other_ids}")
    print(f"      >>> the logo stayed where it was drawn: {kept}")
    return mine, other


# A sweep, because the HTTP door costs ~45 ms of its own (JSON + pydantic on
# a 1.4 MP base64 body) before the endpoint ever runs: early rings land BEFORE
# the request's first read of the tab, late ones land inside the window.
for ms in (20, 60, 90, 120):
    http_race(ms)
# before the request ever read the tab: the doorbell moved it FIRST, so the
# request was honestly addressed to the arriving tab and the server has no way
# to know better — this is the half the browser closes by naming its tab
mine, other = fresh_two()
studio.STATE["active"] = other
print("   doorbell BEFORE the request (the active tab was already moved):")
c = TestClient(studio.app)
c.post("/api/trace-png", json={"png_base64": "data:image/png;base64," + b64,
                               "feature_id": "logo", "height_mm": 40})
print(f"      without a header -> r4-other "
      f"{[f.id for f in studio.STATE['docs'][other]['doc'].features]}")
mine, other = fresh_two()
studio.STATE["active"] = other
c = TestClient(studio.app)
c.post("/api/trace-png", headers={"X-TextCAD-Tab": mine},
       json={"png_base64": "data:image/png;base64," + b64,
             "feature_id": "logo", "height_mm": 40})
print(f"      WITH X-TextCAD-Tab -> r4-mine "
      f"{[f.id for f in studio.STATE['docs'][mine]['doc'].features]}  "
      f"r4-other {[f.id for f in studio.STATE['docs'][other]['doc'].features]}")

print()
print("designs dir used:", LIB)
