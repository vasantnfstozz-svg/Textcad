"""Trace the bottle_cap_28mm seed-39331 journey: print every request body,
and time each feature's build in the request that blew the box up."""
import json, sys, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import journeys, document

STOP_AT = int(sys.argv[1]) if len(sys.argv) > 1 else 5
j = journeys.Journey("bottle_cap_28mm", ROOT / "designs" / "bottle_cap_28mm.tcad.json",
                     39331, 6, verbose=True)
orig_call = j.call
orig_eval = document.Document._eval

def timed_eval(self, f):
    t0 = time.perf_counter()
    try:
        return orig_eval(self, f)
    finally:
        ms = (time.perf_counter() - t0) * 1000
        if ms > 200 or j.counter >= STOP_AT:
            print(f"      eval {f.id:22s} {f.op:16s} {ms:9.0f} ms  params={json.dumps(f.params)[:150]} inputs={f.inputs}", flush=True)
document.Document._eval = timed_eval

class Stop(Exception):
    pass

def tracing_call(kind, method, url, body=None, mutating=True):
    print(f"    -> #{j.counter + 1} {method} {url} {json.dumps(body)[:300]}", flush=True)
    if j.counter + 1 == STOP_AT:
        print("    DOC BEFORE THE STEP:", flush=True)
        for f in j.doc.features:
            print(f"      {f.id:22s} {f.op:16s} {f.status:7s} vol={f.volume} {json.dumps(f.params)[:160]} {f.inputs}", flush=True)
    resp = orig_call(kind, method, url, body, mutating)
    if j.counter >= STOP_AT:
        raise Stop
    return resp
j.call = tracing_call
try:
    j.run()
except Stop:
    print("stopped after the step", flush=True)
except journeys.Bug as b:
    print("BUG", b, flush=True)
except Exception:
    traceback.print_exc()
