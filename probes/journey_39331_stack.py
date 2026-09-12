"""Dump the Python stack 20 s into the plate-add request (where does the cut come from?)."""
import faulthandler, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import journeys
j = journeys.Journey("bottle_cap_28mm", ROOT / "designs" / "bottle_cap_28mm.tcad.json", 39331, 6, verbose=False)
orig = j.call
class Stop(Exception): pass
def call(kind, method, url, body=None, mutating=True):
    if j.counter + 1 == 5:
        faulthandler.dump_traceback_later(20, repeat=False, file=sys.stderr, exit=True)
    return orig(kind, method, url, body, mutating)
j.call = call
try:
    j.run()
except Stop:
    pass
