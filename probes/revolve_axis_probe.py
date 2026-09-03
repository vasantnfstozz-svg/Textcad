"""Probe for the Revolve tool (LAUNCH-PLAN.md P3, textcad-dev rule 1): what the
kernel does with the things the tool will lean on, BEFORE any code assumes it.

    1. revolve about an ARBITRARY axis line (origin + direction) that lies in
       the sketch plane — the tool's u/v axes through the sketch origin, also
       on an offset plane and on a face sketch's canonical plane
    2. a profile straddling the axis: which exception, derived from what
    3. an axis perpendicular to the plane: exception or zero-volume "success"
    4. the sweep DIRECTION of a positive revolution_arc (right-handed about the
       axis?) — the ring gizmo must turn the same way
    5. Pappus: V = 2*pi*r_centroid*A*theta/360 for a rectangle and a circle
    6. negative angles and |angle| > 360
    7. can a build123d Sketch carry a Python attribute (the plane it was drawn
       in), so the op can resolve "u"/"v" without a second source of truth

Run: PYTHONIOENCODING=utf-8 C:\\Python314\\python.exe probes\\revolve_axis_probe.py
"""
import math

import build123d as b3d
from build123d import Axis, Plane, Vector, revolve

import sketch as sk
from document import Document


def show(label, fn):
    try:
        r = fn()
        print(f"{label}: {r}")
    except Exception as e:
        print(f"{label}: {type(e).__module__}.{type(e).__name__} "
              f"(RuntimeError? {isinstance(e, RuntimeError)}): {str(e)[:90]}")


def rect(plane="XZ", x=20.0, y=10.0, w=10.0, h=6.0, offset=0.0):
    return sk.make_sketch(plane=plane, offset=offset, entities=[
        {"kind": "rectangle", "w": w, "h": h, "x": x, "y": y, "mode": "add"}])


# 1. arbitrary in-plane axis: XZ plane, the plane's y (world Z) through origin
s = rect("XZ", x=20, y=10)
pl = sk.sketch_plane("XZ", 0)
u = Axis(pl.origin, pl.x_dir)          # plane's x
v = Axis(pl.origin, pl.y_dir)          # plane's y (= world Z on XZ)
show("1a full turn about v (=Z), volume", lambda: round(revolve(s, axis=v, revolution_arc=360).volume, 4))
show("1b full turn about u (=X), volume", lambda: round(revolve(s, axis=u, revolution_arc=360).volume, 4))
# offset plane: XZ at offset 7 -> y = -7; the plane's own axes through ITS origin
pl7 = sk.sketch_plane("XZ", 7)
s7 = rect("XZ", x=20, y=10, offset=7)
v7 = Axis(pl7.origin, pl7.y_dir)
show("1c offset plane, own axis through (0,-7,0)", lambda: round(revolve(s7, axis=v7, revolution_arc=360).volume, 4))
show("1c' same profile about the WORLD Z (not in its plane)", lambda: round(revolve(s7, axis=Axis.Z, revolution_arc=360).volume, 4))

# 2. straddling profile
s0 = rect("XZ", x=0, y=10)             # centred on x=0: crosses v
show("2 straddling v", lambda: revolve(s0, axis=v, revolution_arc=360).volume)

# 3. axis perpendicular to the plane (XZ's normal is -Y)
show("3 axis perpendicular (Y)", lambda: revolve(s, axis=Axis.Y, revolution_arc=360).volume)

# 4. sweep direction: profile at +x on XZ; 90 deg about Z -> centroid at +y (right-handed) or -y?
q = revolve(s, axis=v, revolution_arc=90)
c = q.center()
print(f"4 +90 about v(Z): centroid x={c.X:.2f} y={c.Y:.2f} z={c.Z:.2f}  -> "
      f"{'right-handed (+y)' if c.Y > 0 else 'LEFT-handed (-y)'}")
qn = revolve(s, axis=v, revolution_arc=-90)
cn = qn.center()
print(f"6a -90 about v(Z): volume={qn.volume:.3f} centroid y={cn.Y:.2f}")

# 5. Pappus
A = 10 * 6
r_bar = 20.0                            # rectangle centred at x=20
for ang in (360, 90, 180):
    vol = revolve(s, axis=v, revolution_arc=ang).volume
    pappus = 2 * math.pi * r_bar * A * ang / 360
    print(f"5 rect angle {ang}: kernel {vol:.4f} pappus {pappus:.4f} "
          f"ratio {vol / pappus:.6f}")
circ = sk.make_sketch(plane="XZ", entities=[{"kind": "circle", "r": 4, "x": 15, "y": 0}])
vol = revolve(circ, axis=v, revolution_arc=360).volume
print(f"5 circle torus: kernel {vol:.4f} pappus {2 * math.pi * 15 * math.pi * 16:.4f}")

# 6. over 360
show("6b angle 400", lambda: round(revolve(s, axis=v, revolution_arc=400).volume, 4))
show("6c angle 0", lambda: revolve(s, axis=v, revolution_arc=0).volume)

# 7. attribute on a Sketch
try:
    s._tc_plane = pl
    print("7 Sketch accepts an attribute:", s._tc_plane is pl, type(s).__name__)
except Exception as e:
    print("7 Sketch attribute FAILED:", type(e).__name__, e)

# 8. a face sketch's plane, via the Document (what the tool will actually see)
d = Document(name="probe")
d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
d.add("s", "sketch_on_face", {"face": "top", "offset": 0,
                              "entities": [{"kind": "rectangle", "w": 10, "h": 6, "x": 20, "y": 0}]}, ["b"])
d.rebuild()
fs = d._parts["s"]
print("8 face sketch type", type(fs).__name__, "faces", len(fs.faces()),
      "normal", [round(c, 3) for c in fs.faces()[0].normal_at()],
      "has _tc_plane?", hasattr(fs, "_tc_plane"))
# revolve the face-sketch about the top plane's y axis through its origin (0,0,12)
top = Plane.XY.offset(12)
show("8b face sketch about its own v axis", lambda: round(revolve(fs, axis=Axis(top.origin, top.y_dir), revolution_arc=360).volume, 4))
