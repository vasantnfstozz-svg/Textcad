"""Can OpenCASCADE tell us it is still WORKING?

The overnight run turned up two different long waits and they must not get the
same answer: a chamfer on 600 traced edges took 630 s and was CORRECT, while one
/api/edit spun for 3 hours and 6 minutes and was never going to finish. A plain
wall-clock ceiling cannot tell them apart -- it would refuse the user's own
keychain to catch the spin.

OCCT 7.5+ threads a Message_ProgressRange through the heavy algorithms, and
Message_ProgressScope carries a UserBreak. If OCP exposes it, the sidecar child
can report progress while it works and the parent can stall-detect instead of
clock-watching. This probe asks ONLY what exists; it runs no heavy geometry.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

print("=== what OCP exposes")
try:
    import OCP
    print("  OCP", getattr(OCP, "__version__", "(no __version__)"))
except Exception as e:
    print("  no OCP:", e)
    raise SystemExit(1)

for mod in ("Message", "BRepOffsetAPI", "BRepFilletAPI", "BRepAlgoAPI"):
    try:
        m = __import__(f"OCP.{mod}", fromlist=[mod])
        names = [n for n in dir(m) if not n.startswith("_")]
        print(f"\n  OCP.{mod}: {len(names)} names")
        for n in names:
            if "Progress" in n or "Indicator" in n or "Break" in n:
                print(f"      * {n}")
    except Exception as e:
        print(f"  OCP.{mod}: {e}")

print("\n=== Message_ProgressRange / ProgressScope / ProgressIndicator")
try:
    from OCP.Message import (Message_ProgressIndicator, Message_ProgressRange,
                             Message_ProgressScope)
    print("  imported all three")
    print("  ProgressIndicator methods:",
          [n for n in dir(Message_ProgressIndicator) if not n.startswith("_")])
    print("  ProgressScope methods:",
          [n for n in dir(Message_ProgressScope) if not n.startswith("_")])
    print("  ProgressRange methods:",
          [n for n in dir(Message_ProgressRange) if not n.startswith("_")])
except Exception as e:
    print("  NOT available:", type(e).__name__, e)

print("\n=== does Build() take a progress range?")
import inspect
for modname, cls in (("BRepOffsetAPI", "BRepOffsetAPI_MakeThickSolid"),
                     ("BRepFilletAPI", "BRepFilletAPI_MakeFillet"),
                     ("BRepFilletAPI", "BRepFilletAPI_MakeChamfer"),
                     ("BRepAlgoAPI", "BRepAlgoAPI_Cut")):
    try:
        m = __import__(f"OCP.{modname}", fromlist=[modname])
        k = getattr(m, cls)
        b = getattr(k, "Build", None)
        doc = (getattr(b, "__doc__", "") or "").strip().splitlines()
        print(f"\n  {cls}.Build:")
        for line in doc[:6]:
            print("     ", line)
    except Exception as e:
        print(f"  {cls}: {e}")

print("\n=== can we SUBCLASS Message_ProgressIndicator in Python?")
try:
    from OCP.Message import Message_ProgressIndicator

    class Watcher(Message_ProgressIndicator):
        def __init__(self):
            super().__init__()
            self.ticks = 0

        def Show(self, theScope, isForce):          # noqa: N802,N803
            self.ticks += 1

        def UserBreak(self):                        # noqa: N802
            return False

    w = Watcher()
    print("  subclass constructed OK:", w)
    print("  Start() ->", w.Start())
except Exception as e:
    print("  cannot subclass:", type(e).__name__, e)
