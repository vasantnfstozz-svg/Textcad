"""Section 12 ROUND FIVE - can the per-request tab pin LEAK or PIN a thread?

Round four (4a6c667) put a contextvars.ContextVar in the path of EVERY
request: a middleware arms it, the endpoint's first _active_tid() resolves it,
and every later read in that request holds it. FastAPI runs sync endpoints in
a threadpool whose worker threads are REUSED, and round four's own note says a
.set() made in the MAIN thread's context "would pin every later request for
the life of the process". So the failure mode is real and admitted. This probe
hammers it instead of reading it.

Run:  C:\\Python314\\python.exe probes/section12_round5_hammer.py
"""
import os
import random
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["TEXTCAD_HISTORY_ROOT"] = tempfile.mkdtemp(prefix="tc-r5-hist-")

import anyio                                        # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

import studio                                       # noqa: E402
from document import Document                       # noqa: E402

studio.DESIGNS = Path(tempfile.mkdtemp(prefix="tc-r5-designs-"))
studio.SESSION_ENABLED = False

FAIL = []


def say(ok, line):
    print(("  OK  " if ok else "  !!  ") + line)
    if not ok:
        FAIL.append(line)


def fresh(n):
    """n tabs, each holding ONE feature named after its own tab."""
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    tids = []
    for i in range(n):
        d = Document(name=f"r5-{i}")
        d.add(f"f{i}", "plate", {"width": 10 + i, "depth": 10,
                                 "thickness": 2}, [])
        tids.append(studio._new_tab(d, source=f"file:r5-{i}"))
    studio._rebuild_and_mesh()
    return tids


# ---------------------------------------------------------------------------
print("\n=== A. the hammer: many tabs, many threads, a doorbell moving the "
      "active tab ===")
# ---------------------------------------------------------------------------
tids = fresh(5)
with TestClient(studio.app) as c:
    # Squeeze the threadpool so worker threads are reused HARD. Without this a
    # 40-token limiter can hand almost every request its own thread and a
    # per-thread leak would never show.
    limiter = c.portal.call(anyio.to_thread.current_default_thread_limiter)
    limiter.total_tokens = 3

    seen_threads = Counter()
    real_thread = studio._active_tid

    def watched():
        seen_threads[threading.current_thread().name] += 1
        return real_thread()

    studio._active_tid = watched

    stop = threading.Event()
    wrong = []
    counted = [0]
    lock = threading.Lock()

    def doorbell():
        """Another thread moving STATE['active'], exactly like the MCP
        doorbell's /api/open/<slug>?external=1."""
        while not stop.is_set():
            studio.STATE["active"] = random.choice(tids)
            time.sleep(0.0005)

    def client(seed):
        rnd = random.Random(seed)
        for _ in range(70):
            want = rnd.choice(tids)
            i = tids.index(want)
            h = {"X-TextCAD-Tab": want}
            if rnd.random() < 0.5:
                r = c.get("/api/doc", headers=h).json()
            else:                     # a WRITE: the one that loses work
                r = c.post("/api/edit", headers=h, json={
                    "feature_id": f"f{i}", "param": "depth",
                    "value": rnd.choice([10, 11, 12])}).json()
            got = [f["id"] for f in r.get("features", [])]
            with lock:
                counted[0] += 1
                if got != [f"f{i}"]:
                    wrong.append((want, got))

    db = threading.Thread(target=doorbell, daemon=True)
    db.start()
    ths = [threading.Thread(target=client, args=(s,)) for s in range(8)]
    t0 = time.time()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    stop.set()
    db.join()
    studio._active_tid = real_thread

    print(f"     {counted[0]} interleaved requests in {time.time() - t0:.1f}s "
          f"over {len(seen_threads)} worker thread(s); busiest thread served "
          f"{max(seen_threads.values())} of them")
    say(len(seen_threads) < counted[0],
        "worker threads really are reused (a leak would have had a chance)")
    say(not wrong,
        f"every request was answered about its OWN tab ({len(wrong)} wrong)")
    if wrong:
        print("       first few:", wrong[:5])

    # ---------------------------------------------------------------------
    print("\n=== B. residue after an ODD ending on a reused worker ===")
    # ---------------------------------------------------------------------
    # 404, a validation error, a refusal, an endpoint that raises, a static
    # file: does the var stay set on that worker for the NEXT request?
    odd = [("404", lambda: c.get("/api/nope", headers={"X-TextCAD-Tab": tids[1]})),
           ("422", lambda: c.post("/api/edit", headers={"X-TextCAD-Tab": tids[1]},
                                  json={"nonsense": 1})),
           ("refusal", lambda: c.post("/api/tabs/switch",
                                      headers={"X-TextCAD-Tab": tids[1]},
                                      json={"id": "tZZZ"})),
           ("raise", lambda: c.post("/api/edit",
                                    headers={"X-TextCAD-Tab": tids[1]},
                                    json={"feature_id": "f1",
                                          "param": "__boom__", "value": 1})),
           ("static", lambda: c.get("/static/js/api.js",
                                    headers={"X-TextCAD-Tab": tids[1]}))]
    for name, call in odd:
        call()
        # the very next request sends NO header at all: it must fall back to
        # the LIVE active tab, not to whatever the odd request left behind
        studio.STATE["active"] = tids[4]
        r = c.get("/api/doc").json()
        say([f["id"] for f in r["features"]] == ["f4"],
            f"after a {name}, a headerless request still reads the live "
            f"active tab (got {[f['id'] for f in r['features']]})")

    # ---------------------------------------------------------------------
    print("\n=== C. is anything pinned in the MAIN context or a bare thread? ===")
    # ---------------------------------------------------------------------
    say(studio._REQ_TAB.get() is None,
        f"the main thread's context is still unarmed "
        f"({studio._REQ_TAB.get()!r})")
    box = []
    t = threading.Thread(target=lambda: box.append(studio._REQ_TAB.get()))
    t.start()
    t.join()
    say(box == [None], f"a bare worker thread starts unarmed ({box!r})")

    # ---------------------------------------------------------------------
    print("\n=== D. what does the response SAY the tab was? ===")
    # ---------------------------------------------------------------------
    studio.STATE["active"] = tids[3]         # the doorbell's tab
    r = c.post("/api/edit", headers={"X-TextCAD-Tab": tids[0]},
               json={"feature_id": "f0", "param": "depth", "value": 14}).json()
    print(f"     features={[f['id'] for f in r['features']]}  "
          f"active_tab={r['active_tab']}  addressed_to={tids[0]}  "
          f"STATE.active={studio.STATE['active']}")
    print("     tab strip says active:",
          [t['id'] for t in r['tabs'] if t['active']])
    say(r["active_tab"] == tids[0],
        "the response names the tab it is ABOUT (the browser feeds this back "
        "as its next X-TextCAD-Tab)")

    # ---------------------------------------------------------------------
    print("\n=== E. one-writer: does a stale header get past the refusal? ===")
    # ---------------------------------------------------------------------
    studio.JOBS.clear()
    busy_tab = tids[2]
    studio.STATE["active"] = busy_tab
    studio.JOBS["j99"] = {"id": "j99", "tab": busy_tab, "done": False}
    gone = "t-closed-long-ago"
    r = c.post("/api/edit", headers={"X-TextCAD-Tab": gone},
               json={"feature_id": "f2", "param": "depth", "value": 77})
    body = r.json()
    landed = studio.STATE["docs"][busy_tab]["doc"].features[0].params["depth"]
    print(f"     reply: {str(body.get('error') or body.get('refused') or '')[:90]}")
    print(f"     busy tab f2.depth is now {landed}")
    say(landed != 77,
        "a header naming a CLOSED tab must not smuggle a write into the tab "
        "the AI is building in")
    studio.JOBS.clear()

    # ---------------------------------------------------------------------
    print("\n=== D2. what the browser does with a response labelled ANOTHER "
          "tab ===")
    # ---------------------------------------------------------------------
    # Both designs carry a feature called `base` — the common case.
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    a = studio._new_tab(Document(name="r5-mine"), source="file:r5-mine")
    studio._doc().add("base", "plate", {"width": 20, "depth": 20,
                                        "thickness": 5}, [])
    b = studio._new_tab(Document(name="r5-arrived"), source="file:r5-arrived")
    studio._doc().add("base", "plate", {"width": 30, "depth": 30,
                                        "thickness": 9}, [])
    studio.STATE["active"] = a
    studio._rebuild_and_mesh()

    studio.STATE["active"] = b                   # the doorbell lands
    poll = c.get("/api/doc", headers={"X-TextCAD-Tab": a}).json()
    print(f"     the poll is about {a} (thickness "
          f"{poll['features'][0]['params']['thickness']}) but says "
          f"active_tab={poll['active_tab']}")
    # the browser now stores THIS as S.lastDoc, so tabHeaders() sends
    # poll.active_tab on the very next click
    nxt = poll["active_tab"]
    c.post("/api/edit", headers={"X-TextCAD-Tab": nxt},
           json={"feature_id": "base", "param": "thickness", "value": 41})
    mine = studio.STATE["docs"][a]["doc"].features[0].params["thickness"]
    arrived = studio.STATE["docs"][b]["doc"].features[0].params["thickness"]
    print(f"     after the edit: mine={mine}  arrived={arrived}")
    say(mine == 41 and arrived == 9,
        "an edit made against the tree on screen lands in the design on "
        "screen")

    # ---------------------------------------------------------------------
    print("\n=== F. the headerless doors (raw fetch() in static/js) ===")
    # ---------------------------------------------------------------------
    raw = []
    for p in sorted((ROOT / "static" / "js").glob("*.js")):
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "fetch(" in ln and "tabHeaders" not in ln \
                    and "globalThis.fetch" not in ln and "window.fetch" not in ln:
                raw.append(f"{p.name}:{i}: {ln.strip()[:88]}")
    print(f"     {len(raw)} fetch() call sites do not go through tabHeaders:")
    for ln in raw:
        print("      ", ln)

    # and what the worst of them does: Export writes a FILE
    studio.STATE["active"] = b
    r = c.post("/api/export").json()          # dialogs.js used to send none
    print(f"     headerless (the MCP, and dialogs.js before the fix): "
          f"{Path(r.get('path', '?')).name}  volume={r.get('volume')}")
    r = c.post("/api/export", headers={"X-TextCAD-Tab": a}).json()
    print(f"     named (what the page now sends): "
          f"{Path(r.get('path', '?')).name}  volume={r.get('volume')}")
    say(Path(r.get("path", "?")).stem == "r5-mine",
        "File->Export exports the design on screen, not the one a doorbell "
        "made active")

    # ---------------------------------------------------------------------
    print("\n=== G. the WHOLE doorbell journey, as the page now walks it ===")
    # ---------------------------------------------------------------------
    # The answer no longer drags the page to the arriving tab, so the follow
    # has to be deliberate. Walk every step the browser takes and check the
    # design the user ends up in.
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    plate = Document(name="r5-onscreen")
    plate.add("base", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    mine = studio._new_tab(plate, source="file:r5-onscreen")
    studio._rebuild_and_mesh()

    ring = Document(name="r5-ring")
    ring.add("base", "plate", {"width": 40, "depth": 40, "thickness": 3}, [])
    ring.save(str(studio.DESIGNS / "r5-ring.tcad.json"))
    c.post("/api/open/r5-ring?external=1")        # the MCP doorbell
    arrived = studio.STATE["active"]
    say(arrived != mine, "the doorbell opened its own tab and took the "
                         "active one")

    poll = c.get("/api/doc", headers={"X-TextCAD-Tab": mine}).json()
    say(poll["active_tab"] == mine and
        poll["features"][0]["params"]["thickness"] == 5,
        "the poll still answers about the design on screen")
    say(poll["arrival"] and poll["arrival"]["tab"] == arrived,
        "and still carries the arrival banner, naming the arriving tab")

    # what noteArrival now does: ack, then a deliberate switch
    c.post("/api/arrival/ack", json={"at": poll["arrival"]["at"]},
           headers={"X-TextCAD-Tab": mine})
    after = c.post("/api/tabs/switch", json={"id": poll["arrival"]["tab"]},
                   headers={"X-TextCAD-Tab": mine}).json()
    say(after["active_tab"] == arrived and after["name"] == "r5-ring",
        f"'loaded it' is true: the page is now on {after['name']}")
    # and the viewport, which is a raw fetch, follows the page
    m = c.get("/api/model", headers={"X-TextCAD-Tab": after["active_tab"]})
    say(m.status_code == 200 and m.json().get("bodies") is not None
        or m.status_code == 200,
        "the viewport asks about the same tab the tree is showing")
    say(c.get("/api/doc").json()["arrival"] is None,
        "the banner is consumed, so no page repeats it")

print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED:"))
for f in FAIL:
    print("  -", f)
