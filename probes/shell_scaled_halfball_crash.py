"""Reproduce bugs/20260912-175819-isogrid-panel-s9016-crash: a CLOSED shell
(t = 1.8, inside) of a box-clipped half-ball scaled by 0.8 SEGFAULTS OCCT
(0xC0000005) inside b3d.offset(). Built with the project's own ops, the way the
journey built it; each case runs in a CHILD so the parent survives and reports
the exit code.

    PYTHONPATH=. python probes/shell_scaled_halfball_crash.py [case ...]
"""
import json
import os
import subprocess
import sys

CASES = {
    # the journey's exact chain: YZ rect 6 x 10.4 extruded 8.9, & ball r3.2 rotated 180 Z, scale 0.8
    "journey":         dict(box=(6.0, 10.4, 8.9), r=3.2, scale=0.8, t=1.8, openings=None),
    "journey_open":    dict(box=(6.0, 10.4, 8.9), r=3.2, scale=0.8, t=1.8, openings=["-x"]),
    "journey_noscale": dict(box=(6.0, 10.4, 8.9), r=3.2, scale=1.0, t=1.8, openings=None),
    "journey_t1":      dict(box=(6.0, 10.4, 8.9), r=3.2, scale=0.8, t=1.0, openings=None),
    "journey_t05":     dict(box=(6.0, 10.4, 8.9), r=3.2, scale=0.8, t=0.5, openings=None),
    "journey_t2":      dict(box=(6.0, 10.4, 8.9), r=3.2, scale=0.8, t=2.0, openings=None),
    "journey_t3":      dict(box=(6.0, 10.4, 8.9), r=3.2, scale=0.8, t=3.0, openings=None),
    "halfball":        dict(box=(20, 20, 20), r=3.2, scale=1.0, t=1.8, openings=None),
    "halfball_t3":     dict(box=(20, 20, 20), r=3.2, scale=1.0, t=3.0, openings=None),
    "ball_t5":         dict(box=None, r=3.2, scale=1.0, t=5.0, openings=None),
    # the same shape ten times bigger (the corpus size class): does it crash the same way?
    "x10_t18":         dict(box=(60, 104, 89), r=32, scale=1.0, t=18, openings=None),
    "x10_t2":          dict(box=(60, 104, 89), r=32, scale=1.0, t=2, openings=None),
    "x10_t10":         dict(box=(60, 104, 89), r=32, scale=1.0, t=10, openings=None),
    "x10_t12":         dict(box=(60, 104, 89), r=32, scale=1.0, t=12, openings=None),
    "x10_t2_open":     dict(box=(60, 104, 89), r=32, scale=1.0, t=2, openings=["-x"]),
    "x10_t2_outside":  dict(box=(60, 104, 89), r=32, scale=1.0, t=2, openings=None, direction="outside"),
}

CHILD = r'''
import sys, json
import blocks, sketch as sk
c = json.loads(sys.argv[1])
ball = blocks.rotate(blocks.ball(c["r"]), "Z", 180, pivot="center")
if c["box"]:
    w, h, amt = c["box"]
    s = sk.make_sketch("YZ", 0, [dict(kind="rectangle", mode="add", x=0, y=0, rotation=0, w=w, h=h)])
    prism = sk.extrude_sketch(s, amount=amt, both=False)
    body = prism & ball
else:
    body = ball
if c["scale"] != 1.0:
    body = blocks.scale_uniform(body, c["scale"])
bb = body.bounding_box()
print("in: vol=%.3f solids=%d size=%.3f x %.3f x %.3f" % (body.volume, len(body.solids()), bb.size.X, bb.size.Y, bb.size.Z), flush=True)
print("faces:", [f.geom_type.name for f in body.faces()], flush=True)
try:
    out = sk.shell(body, c["t"], c["openings"], c.get("direction", "inside"))
    print("shell ok: vol=%.3f solids=%d" % (out.volume, len(out.solids())), flush=True)
except Exception as e:
    print("refused:", type(e).__name__, str(e)[:200], flush=True)
'''

if __name__ == "__main__":
    only = sys.argv[1:] or list(CASES)
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    for name in only:
        c = CASES[name]
        p = subprocess.run([sys.executable, "-c", CHILD, json.dumps(c)],
                           capture_output=True, text=True, timeout=300, env=env)
        code = p.returncode & 0xFFFFFFFF
        print(f"== {name}: exit {code:#x}" if code else f"== {name}: exit 0")
        print(p.stdout.strip())
        if p.stderr.strip() and code:
            print("stderr:", p.stderr.strip()[-500:])
