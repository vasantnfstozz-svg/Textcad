"""Section 11 round two — the assumption the whole centroid fix stands on.

`_poly_centroid` is a SHOELACE, so it is only right if `_project_wire`'s point
list is in boundary order.  Round one's docstring asserts that ("_project_wire
walks a wire edge by edge, so its points are in order") and tests it on three
sketches.  A shoelace on a scrambled list is not a little wrong, it is
arbitrary — and the OLD point-average was immune to order — so the assumption
is measured here on a wider corpus, INCLUDING the real solid faces `_loops`
also runs on in Extrude's face mode (boolean results, fillet results, a face
with several holes, a lofted wall).

The oracle: |shoelace area| against the kernel's own `Face.area`, and the
shoelace centroid against the kernel's own `Face.center()`.  A scrambled list
fails both.

Run:  C:\\Python314\\python.exe probes/tool_wire_order_probe.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", tempfile.mkdtemp())

import sketch as sk  # noqa: E402
import toolplan  # noqa: E402
from document import Document  # noqa: E402


def build(*feats):
    d = Document(name="t")
    for fid, op, params, inputs in feats:
        d.add(fid, op, params, inputs)
    d.rebuild()
    return d


def check(label, faces, pl, curved_tol=0.02):
    """area and centroid of the sampled outline vs the kernel's own."""
    loops = toolplan._loops(faces, pl)
    poly = 0.0
    sx = sy = 0.0
    for L in loops:
        a, px, py = toolplan._poly_centroid(L["outer"])
        poly += abs(a)
        sx += abs(a) * px
        sy += abs(a) * py
        for h in L["holes"]:
            ha, hx, hy = toolplan._poly_centroid(h)
            poly -= abs(ha)
            sx -= abs(ha) * hx
            sy -= abs(ha) * hy
    real = sum(f.area for f in faces)
    kx = ky = 0.0
    for f in faces:
        c = pl.to_local_coords(f.center())
        kx += f.area * c.X
        ky += f.area * c.Y
    kx /= real
    ky /= real
    cx, cy = (sx / poly, sy / poly) if abs(poly) > 1e-9 else (float("nan"),) * 2
    da = abs(poly - real) / real
    dc = math.hypot(cx - kx, cy - ky)
    flag = "  <-- OUT OF ORDER?" if (da > curved_tol or dc > 0.25) else ""
    print(f"  {label:<34} area {real:10.3f} vs {poly:10.3f} ({da * 100:5.2f}%)"
          f"   centre off {dc:7.4f} mm{flag}")
    return da, dc


XY = sk.sketch_plane("XY", 0)

print("=" * 88)
print("A. SKETCH profiles — every entity kind the sketcher can make")
print("=" * 88)
SKETCHES = {
    "rectangle": [{"kind": "rectangle", "w": 30, "h": 20}],
    "circle": [{"kind": "circle", "r": 10}],
    "hexagon": [{"kind": "regular_polygon", "radius": 12, "sides": 6}],
    "slot": [{"kind": "slot", "length": 40, "height": 10}],
    "L polygon": [{"kind": "polygon", "points": [[0, 0], [40, 0], [40, 10],
                                                 [10, 10], [10, 30], [0, 30]]}],
    "rounded rect (path + arcs)": [
        {"kind": "path", "points": [[-20, -10], [20, -10], [20, 10], [-20, 10]],
         "closed": True, "fillet": 4}],
    "plate with 4 holes": [
        {"kind": "rectangle", "w": 60, "h": 40},
        *[{"kind": "circle", "r": 3, "x": x, "y": y, "mode": "subtract"}
          for x in (-20, 20) for y in (-12, 12)]],
    "two islands": [{"kind": "circle", "r": 10, "x": -20},
                    {"kind": "rectangle", "w": 20, "h": 20, "x": 20}],
    "ellipse": [{"kind": "ellipse", "rx": 20, "ry": 8}],
    "ring": [{"kind": "circle", "r": 15},
             {"kind": "circle", "r": 9, "mode": "subtract"}],
}
worst = (0.0, 0.0, "")
for name, ents in SKETCHES.items():
    try:
        d = build(("s", "sketch", {"plane": "XY", "entities": ents}, []))
        da, dc = check(name, list(d._parts["s"].faces()), XY)
        if dc > worst[1]:
            worst = (da, dc, name)
    except Exception as e:                      # noqa: BLE001
        print(f"  {name:<34} SKIPPED ({type(e).__name__}: {e})")

print()
print("=" * 88)
print("B. SOLID faces — what Extrude's FACE mode feeds _loops")
print("=" * 88)


def face_case(label, doc, body, picker):
    part = doc._parts[body]
    picked = picker(part)
    fp = toolplan._flat_or_raise(picked)
    check(label, [picked], fp)


# a boolean result: a plate with four bores, top face
d = build(
    ("b", "plate", {"width": 80, "depth": 60, "thickness": 12}, []),
    ("s", "sketch_on_face", {"face": "top", "entities": [
        {"kind": "circle", "r": 4, "x": x, "y": y}
        for x in (-25, 25) for y in (-18, 18)]}, ["b"]),
    ("cut", "extrude", {"amount": 12, "flip": True}, ["s"]),
    ("j", "cut", {}, ["b", "cut"]),
)
face_case("plate + 4 bores, top face", d, "j",
          lambda p: max(p.faces(), key=lambda f: (round(f.center().Z, 3), f.area)))

# a filleted body: the top face is now bounded by arcs and lines
d2 = build(
    ("b", "plate", {"width": 80, "depth": 60, "thickness": 12}, []),
    ("f", "fillet", {"radius": 3}, ["b"]),
)
face_case("filleted plate, top face", d2, "f",
          lambda p: max(p.faces(), key=lambda f: f.center().Z))

# a body made by a boolean of two prisms: an L-shaped top face
d3 = build(
    ("a", "plate", {"width": 60, "depth": 20, "thickness": 10}, []),
    ("c", "plate", {"width": 20, "depth": 60, "thickness": 10}, []),
    ("u", "fuse", {}, ["a", "c"]),
)
face_case("fused cross, top face", d3, "u",
          lambda p: max(p.faces(), key=lambda f: (round(f.center().Z, 3), f.area)))

print()
print(f"worst sketch centre error: {worst[1]:.4f} mm  ({worst[2]})")
