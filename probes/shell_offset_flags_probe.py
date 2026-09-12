"""Does ANY flag combination of OCCT's thick-solid offset REFUSE the clipped
ball instead of segfaulting? build123d's offset_3d calls
MakeThickSolidByJoin(Intersection=True, RemoveIntEdges=True, Join=...).
Tried here on the crash body (outside 1.2 / 1.8, inside 1.8) and on the
50 x 50 x 30 box (t = 2, both directions: volumes must match the exact
sharp-cornered shell). Children, so the parent survives.

    PYTHONPATH=. python probes/shell_offset_flags_probe.py
"""
import json
import os
import subprocess
import sys

CHILD = r'''
import sys, json
import build123d as b3d
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid, BRepOffsetAPI_MakeOffsetShape
from OCP.TopTools import TopTools_ListOfShape
from OCP.GeomAbs import GeomAbs_JoinType
from OCP.BRepOffset import BRepOffset_Mode
from tests.test_shell_tool import clipped_ball
c = json.loads(sys.argv[1])
body = clipped_ball() if c["body"] == "ball" else b3d.Part() + b3d.Box(50, 50, 30)
join = GeomAbs_JoinType.GeomAbs_Intersection if c["join"] == "int" else GeomAbs_JoinType.GeomAbs_Arc
try:
    if c["api"] == "thick":
        bld = BRepOffsetAPI_MakeThickSolid()
        bld.MakeThickSolidByJoin(body.wrapped, TopTools_ListOfShape(), c["t"], 1e-4,
                                 BRepOffset_Mode.BRepOffset_Skin, c["inter"], False, join, c["rm"])
    else:
        bld = BRepOffsetAPI_MakeOffsetShape()
        bld.PerformByJoin(body.wrapped, c["t"], 1e-4, BRepOffset_Mode.BRepOffset_Skin, c["inter"], False, join, c["rm"])
    bld.Build()
    if not bld.IsDone():
        print("not done (clean)"); sys.exit(0)
    off = b3d.Solid(bld.Shape())
    v = abs(off.volume)
    print("built vol=%.3f" % v)
except Exception as e:
    print("raised (clean):", type(e).__name__, str(e)[:80])
'''

def run(case):
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", CHILD, json.dumps(case)],
                       capture_output=True, text=True, timeout=300, env=env)
    code = p.returncode & 0xFFFFFFFF
    tag = f"  <<< exit {code:#x}" if code else ""
    print(f"{case['body']:>4} {case['api']:>5} inter={case['inter']!s:5} rm={case['rm']!s:5} join={case['join']} t={case['t']:>5}: {p.stdout.strip()}{tag}")

if __name__ == "__main__":
    for api in ("thick", "shape"):
        for inter in (True, False):
            for rm in (True, False):
                for join in ("int",):
                    for body, t in (("box", 2), ("box", -2), ("ball", 1.2), ("ball", 1.8), ("ball", -1.8)):
                        run(dict(api=api, inter=inter, rm=rm, join=join, body=body, t=t))
    for body, t in (("ball", 1.2), ("ball", 1.8), ("ball", -1.8)):
        run(dict(api="thick", inter=True, rm=True, join="arc", body=body, t=t))
