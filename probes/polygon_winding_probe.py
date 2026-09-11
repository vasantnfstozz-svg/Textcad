"""Probe: what does OCCT do with a CLOCKWISE sketch polygon? (2026-09-05)

House rule 1 — never call a build123d/OCCT API from memory. The fix in
sketch.py:_entity rests on three claims that were measured here, not assumed:

  1. Polygon() takes the POINT ORDER as the face's orientation, so a clockwise
     ring is a face whose normal points -Z.
  2. Adding that face to a normal one does NOT fail -- it silently yields TWO
     overlapping faces, which extrude into a self-intersecting solid. This is
     the banned failure mode (rule 5): a "successful" invalid solid.
  3. A `path` entity is NOT affected: make_face() orients it, so a clockwise
     path already comes back +Z. That is why the fix touches polygons only.

And the case the first fix missed, added here as claim 4:

  4. A ring that encloses NOTHING (collinear points, or a bow-tie whose lobes
     cancel) has signed area 0, so a sign test never sees it. OCCT builds it
     anyway, as a face of area -0.0.

Run:  python probes/polygon_winding_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sketch as sk                                        # noqa: E402

CCW = {"kind": "polygon", "points": [[0, 0], [20, 0], [20, 20], [0, 20]]}
CW = {"kind": "polygon", "points": [[10, 10], [10, 30], [30, 30], [30, 10]]}
CW_PATH = {"kind": "path", "start": [10, 10], "segments": [
    {"type": "line", "to": [10, 30]},
    {"type": "line", "to": [30, 30]},
    {"type": "line", "to": [30, 10]}]}
BOWTIE = {"kind": "polygon", "points": [[0, 0], [20, 20], [20, 0], [0, 20]]}


def normal_of(entity):
    (face,) = entity.faces()
    return tuple(round(v) for v in face.normal_at())


def raw_polygon(pts):
    """Polygon() with the points EXACTLY as given (no winding fix)."""
    from build123d import Polygon
    return Polygon(*[tuple(p) for p in pts])


def main():
    print("1. orientation follows the point order")
    print("   CCW polygon normal:", normal_of(sk._entity(CCW)))
    print("   CW  polygon, raw   :", tuple(round(v) for v in
                                           raw_polygon(CW["points"]).faces()[0].normal_at()))
    print("   CW  polygon, fixed :", normal_of(sk._entity(CW)))

    print("2. a raw CW face does not FAIL when added -- it duplicates")
    raw_sum = raw_polygon(CCW["points"]) + raw_polygon(CW["points"])
    print("   faces after add:", len(raw_sum.faces()),
          "areas:", sorted(round(f.area, 1) for f in raw_sum.faces()))
    fixed = sk.compose([CCW, CW])
    print("   with the fix   :", len(fixed.faces()),
          "areas:", [round(f.area, 1) for f in fixed.faces()], "(expect one, 700)")

    print("3. a path is already oriented by make_face() -- no fix needed")
    print("   CW path normal:", normal_of(sk._entity(CW_PATH)))
    print("   CCW polygon + CW path faces:",
          len(sk.compose([CCW, CW_PATH]).faces()), "(expect 1)")

    print("4. a ring enclosing nothing has signed area 0 -- a sign test misses it")
    pts = [tuple(p) for p in BOWTIE["points"]]
    print("   bow-tie signed area:", sk._signed_area(pts))
    print("   OCCT builds it anyway, area:",
          [round(f.area, 6) for f in raw_polygon(BOWTIE["points"]).faces()])
    try:
        sk._entity(BOWTIE)
        print("   sketch.py accepted it  <-- would be the bug")
    except ValueError as e:
        print("   sketch.py refuses it:", e)


if __name__ == "__main__":
    main()
