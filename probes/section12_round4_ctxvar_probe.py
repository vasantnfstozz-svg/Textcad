"""Does a ContextVar set INSIDE a sync FastAPI endpoint stay inside that one
request? (probe-before-you-build for section 12 round four)

The fix wants "one read of the active tab per request", and the cheapest place
to keep that read is a ContextVar: FastAPI runs a sync `def` endpoint through
anyio's worker thread, which runs it in a COPY of the request's context, so a
`.set()` there should be scoped to that call and invisible to the next one.
That is the whole bet — measure it rather than trust the docs.

Run:  C:\\Python314\\python.exe probes/section12_round4_ctxvar_probe.py
"""
import contextvars
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib.metadata as _md          # noqa: E402
import fastapi        # noqa: E402
import starlette      # noqa: E402
from fastapi import FastAPI                      # noqa: E402
from fastapi.testclient import TestClient        # noqa: E402

print(f"fastapi {fastapi.__version__}  starlette {starlette.__version__}  "
      f"anyio {_md.version(chr(97) + chr(110) + chr(121) + chr(105) + chr(111))}")

VAR: contextvars.ContextVar = contextvars.ContextVar("probe", default=None)
app = FastAPI()
seen = []


@app.middleware("http")
async def mw(request, call_next):
    seen.append(("middleware-before", VAR.get()))
    r = await call_next(request)
    seen.append(("middleware-after", VAR.get()))
    return r


@app.post("/sync")
def sync_route(tag: str):
    was = VAR.get()
    VAR.set(tag)
    again = VAR.get()
    return {"was": was, "again": again, "thread": threading.current_thread().name}


@app.get("/async")
async def async_route():
    return {"was": VAR.get()}


c = TestClient(app)
r1 = c.post("/sync?tag=alpha").json()
r2 = c.post("/sync?tag=beta").json()
r3 = c.get("/async").json()
print("request 1:", r1)
print("request 2:", r2)
print("async:    ", r3)
print("middleware saw:", seen)

ok = (r1["was"] is None and r1["again"] == "alpha"
      and r2["was"] is None and r2["again"] == "beta"
      and r3["was"] is None
      and all(v is None for _, v in seen))
print()
print("SET INSIDE THE ENDPOINT IS REQUEST-SCOPED:", ok)
if r1["thread"] == r2["thread"]:
    print("(and both ran on the SAME worker thread, so the isolation is the "
          "context copy, not a fresh thread)")

# --- and what a MAIN-THREAD set does (startup code must never pin) ---------
VAR.set("leaked-from-startup")
r4 = c.post("/sync?tag=gamma").json()
print()
print("after a main-thread .set(), a later request sees:", r4["was"])
print("SO: startup code must not set the var (it WOULD leak):",
      r4["was"] == "leaked-from-startup")

# --- the direction the fix needs: ARMED IN THE MIDDLEWARE, read in the -------
#     endpoint. Starlette's BaseHTTPMiddleware runs the app in a task it
#     spawns, and anyio copies the CURRENT context at spawn, so this should
#     carry FORWARDS even though the reverse (endpoint -> middleware) does not.
ARM: contextvars.ContextVar = contextvars.ContextVar("arm", default="unarmed")
app2 = FastAPI()


@app2.middleware("http")
async def arming(request, call_next):
    ARM.set("armed:" + request.url.path)
    return await call_next(request)


@app2.post("/sync")
def sync2():
    was = ARM.get()
    ARM.set("resolved")
    return {"was": was, "again": ARM.get()}


@app2.get("/plain")
async def plain2():
    return {"was": ARM.get()}


c2 = TestClient(app2)
a = c2.post("/sync").json()
b = c2.post("/sync").json()
d = c2.get("/plain").json()
print()
print("armed in middleware -> sync endpoint:", a)
print("second request (no leak of 'resolved'):", b)
print("armed in middleware -> async endpoint:", d)
print("ARM in the main thread now:", ARM.get())
print("ARMING THROUGH THE MIDDLEWARE WORKS:",
      a["was"] == "armed:/sync" and b["was"] == "armed:/sync"
      and d["was"] == "armed:/plain" and ARM.get() == "unarmed")
