"""Found by the corpus the day the clipped ball joined it (2026-09-12): the
mirror gauntlet's body-joined-with-its-reflection test SEGFAULTS on it. Which
plane? Each case in a child so the parent survives.

    PYTHONPATH=. python probes/mirror_clipped_ball_crash.py
"""
import json
import os
import subprocess
import sys

CHILD = r'''
import sys, json
import pattern
from tests.gauntlet import BODIES, planar_faces
c = json.loads(sys.argv[1])
solid = BODIES["clipped_ball"]()
if c["kind"] == "face":
    idx, face, centre, normal = planar_faces(solid)[c["i"]]
    plane = pattern.stored_face(solid, face)
    print("face", idx, [round(v, 2) for v in centre], [round(v, 2) for v in normal], end=" ", flush=True)
else:
    plane = {"mid": c["axis"]}
    print("mid", c["axis"], end=" ", flush=True)
try:
    out = pattern.mirror(solid, plane, join=c["join"])
    print("-> OK vol=%.2f solids=%d" % (out.volume, len(out.solids())))
except Exception as e:
    print("-> refused:", str(e)[:100])
'''

def run(case):
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", CHILD, json.dumps(case)],
                       capture_output=True, text=True, timeout=300, env=env)
    code = p.returncode & 0xFFFFFFFF
    print(f"{case} {p.stdout.strip()} {'<<< exit %#x' % code if code else ''}")

if __name__ == "__main__" and len(sys.argv) == 1:
    for join in (True, False):
        for i in range(3):
            run(dict(kind="face", i=i, join=join))
        for axis in "XYZ":
            run(dict(kind="mid", axis=axis, join=join))


# ---- §2: is it the FUSE of two halves of ONE surface? and does glue survive it?
CHILD2 = r'''
import sys, json
import build123d as b3d
from tests.gauntlet import BODIES
c = json.loads(sys.argv[1])
if c["body"] == "clipped_ball":
    seed = BODIES["clipped_ball"]()
    pl = b3d.Plane.YZ                                   # its flat face x = 0
elif c["body"] == "half_ball":
    seed = b3d.Part() + (b3d.Solid.make_sphere(32) & b3d.Box(40, 80, 80, align=(b3d.Align.MIN, b3d.Align.CENTER, b3d.Align.CENTER)))
    pl = b3d.Plane.YZ
else:                                                   # a cylinder cut through its axis
    seed = b3d.Part() + (b3d.Cylinder(25, 40) & b3d.Box(40, 80, 80, align=(b3d.Align.MIN, b3d.Align.CENTER, b3d.Align.CENTER)))
    pl = b3d.Plane.YZ
image = b3d.mirror(seed, about=pl)
print("seed %.2f image %.2f" % (seed.volume, image.volume), end=" ", flush=True)
try:
    out = seed.fuse(image, glue=True) if c["glue"] else seed + image
    import inspector
    print("-> vol=%.2f solids=%d health=%s" % (out.volume, len(out.solids()), inspector.health(out)))
except Exception as e:
    print("-> raised:", type(e).__name__, str(e)[:80])
'''

def run2(case):
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", CHILD2, json.dumps(case)],
                       capture_output=True, text=True, timeout=300, env=env)
    code = p.returncode & 0xFFFFFFFF
    print(f"S2 {case} {p.stdout.strip()} {'<<< exit %#x' % code if code else ''}")
    if code and p.stderr.strip():
        print("   ", p.stderr.strip().splitlines()[-1][:160])

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "fuse":
    for body in ("clipped_ball", "half_ball", "half_cyl"):
        for glue in (False, True):
            run2(dict(body=body, glue=glue))


# ---- §3: the class's edges, and the sphere-surface API for the guard
CHILD3 = r'''
import sys, json, math
import build123d as b3d
import pattern
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_SurfaceType
c = json.loads(sys.argv[1])
MIN = (b3d.Align.MIN, b3d.Align.CENTER, b3d.Align.CENTER)
if c["case"] == "full_ball_midX":
    seed, plane = b3d.Part() + b3d.Solid.make_sphere(32), {"mid": "X"}
elif c["case"] == "full_ball_off_centre":       # centre 10 mm off the plane: image overlaps
    seed, plane = b3d.Part() + b3d.Pos(10, 0, 0) * b3d.Solid.make_sphere(32), "YZ"
elif c["case"] == "half_ball_offset5":           # half ball, plane 5 mm beyond its flat face
    seed = b3d.Part() + (b3d.Solid.make_sphere(32) & b3d.Box(40, 80, 80, align=MIN))
    plane = {"origin": [-5, 0, 0], "normal": [1, 0, 0]}
elif c["case"] == "tilted_clip":                 # clipped at 45 deg through the centre, mirrored across YZ
    knife = b3d.Rot(0, 0, 45) * b3d.Box(40, 80, 80, align=MIN)
    seed, plane = b3d.Part() + (b3d.Solid.make_sphere(32) & knife), "YZ"
elif c["case"] == "quarter_ball":
    seed = b3d.Part() + (b3d.Solid.make_sphere(32) & b3d.Box(40, 40, 80, align=(b3d.Align.MIN, b3d.Align.MIN, b3d.Align.CENTER)))
    plane = "YZ"
for f in seed.faces():
    if f.geom_type == b3d.GeomType.SPHERE:
        ad = BRepAdaptor_Surface(f.wrapped)
        sp = ad.Sphere()
        loc = sp.Location()
        print("sphere face: centre (%.2f %.2f %.2f) r=%.2f area/4pir2=%.3f" % (loc.X(), loc.Y(), loc.Z(), sp.Radius(), f.area / (4 * math.pi * sp.Radius() ** 2)), end=" | ", flush=True)
try:
    out = pattern.mirror(seed, plane, join=True)
    import inspector
    print("-> vol=%.2f (seed %.2f) solids=%d health=%s" % (out.volume, seed.volume, len(out.solids()), inspector.health(out)))
except Exception as e:
    print("-> refused:", str(e)[:120])
'''

def run3(case):
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", CHILD3, json.dumps(dict(case=case))],
                       capture_output=True, text=True, timeout=300, env=env)
    code = p.returncode & 0xFFFFFFFF
    print(f"S3 {case}: {p.stdout.strip()} {'<<< exit %#x' % code if code else ''}")
    if code and p.stderr.strip():
        print("   ", p.stderr.strip().splitlines()[-1][:200])

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "edges":
    for case in ("full_ball_midX", "full_ball_off_centre", "half_ball_offset5", "tilted_clip", "quarter_ball"):
        run3(case)


# ---- §4: does the CUT path share the class? a half-ball pocket's image cut from the body
CHILD4 = r'''
import build123d as b3d, inspector
MIN = (b3d.Align.MIN, b3d.Align.CENTER, b3d.Align.CENTER)
tool = b3d.Solid.make_sphere(20) & b3d.Box(40, 80, 80, align=MIN)      # half ball, x >= 0
body = b3d.Part() + b3d.Box(100, 100, 50) - tool
image = b3d.mirror(tool, about=b3d.Plane.YZ)
print("body %.2f" % body.volume, end=" ", flush=True)
out = body - image
print("-> cut vol=%.2f health=%s" % (out.volume, inspector.health(out)))
'''
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "cut":
    env = dict(os.environ, PYTHONPATH=os.getcwd(), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", CHILD4], capture_output=True, text=True, timeout=300, env=env)
    code = p.returncode & 0xFFFFFFFF
    print(f"S4 cut: {p.stdout.strip()} {'<<< exit %#x' % code if code else ''}")
