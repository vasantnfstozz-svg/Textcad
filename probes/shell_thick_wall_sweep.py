"""Sweep: does a CLOSED inside shell segfault exactly when the wall is thicker
than half the body's smallest extent? The journey body at many t, and every
gauntlet corpus body at 0.45 / 0.55 / 1.0 of half its smallest extent, inside
AND outside. Children, so the parent survives.

    PYTHONPATH=. python probes/shell_thick_wall_sweep.py
"""
import json
import os
import subprocess
import sys

CHILD = r'''
import sys, json
import blocks, sketch as sk
from tests.gauntlet import BODIES
c = json.loads(sys.argv[1])
if c["body"] == "journey":
    ball = blocks.rotate(blocks.ball(3.2), "Z", 180, pivot="center")
    s = sk.make_sketch("YZ", 0, [dict(kind="rectangle", mode="add", x=0, y=0, rotation=0, w=6.0, h=10.4)])
    body = blocks.scale_uniform(sk.extrude_sketch(s, amount=8.9, both=False) & ball, 0.8)
else:
    body = BODIES[c["body"]]()
bb = body.bounding_box().size
dmin = min(bb.X, bb.Y, bb.Z)
t = c["t"] if c["t"] else round(c["frac"] * dmin / 2, 3)
print("dmin=%.3f t=%.3f" % (dmin, t), end=" ", flush=True)
try:
    out = sk.shell(body, t, None, c["direction"])
    print("OK vol %.3f/%.3f" % (out.volume, body.volume))
except Exception as e:
    print("refused:", str(e)[:90])
'''

def run(case):
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", CHILD, json.dumps(case)],
                       capture_output=True, text=True, timeout=300, env=env)
    code = p.returncode & 0xFFFFFFFF
    tag = f"exit {code:#x}" if code else ""
    print(f"{case['body']:>22} {case['direction']:>7} frac={case.get('frac')} t={case.get('t')}: {p.stdout.strip()} {tag}")
    return code

if __name__ == "__main__":
    from tests.gauntlet import BODIES
    crashes = []
    for t in [0.2, 0.6, 1.0, 1.2, 1.27, 1.29, 1.4, 1.8, 2.5, 3.0]:
        for d in ("inside", "outside"):
            if run(dict(body="journey", t=t, frac=None, direction=d)):
                crashes.append(("journey", d, t))
    for name in sorted(BODIES):
        for frac in (0.45, 0.55, 1.0):
            for d in ("inside", "outside"):
                if run(dict(body=name, t=None, frac=frac, direction=d)):
                    crashes.append((name, d, frac))
    print("CRASHES:", crashes)
