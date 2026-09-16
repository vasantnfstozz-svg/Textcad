"""Section 10 review probe: the picking rules, measured.

1  A dead-flat wall that OCCT types BSPLINE/EXTRUSION: is it `planar` in the
   viewport payload, and is it sketchable?  (viewport.planePickAt tests
   `info.type === 'PLANE'` where every other picker tests `info.planar`.)
2  attribute_face's stale-index fallback: it is handed the picked face's AREA
   and does not use it.
"""

import sketch as sk
import studio
import provenance as P
from document import Document


def taper_doc():
    doc = Document(name="p-taper")
    doc.add("prof", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 20, "taper": 12}, inputs=["prof"])
    assert doc.rebuild(), doc.tree()
    return doc


def section1():
    doc = taper_doc()
    part = doc.result()
    print("== 1 dead-flat walls that are not typed PLANE ==")
    rows = []
    for i, f in enumerate(part.faces()):
        gt = str(f.geom_type).replace("GeomType.", "")
        flat = sk.face_plane(f) is not None
        rows.append((i, gt, flat, round(f.area, 2)))
        print(f"  face {i:2d}  type={gt:12s} face_plane={flat}  area={f.area:9.2f}")
    odd = [r for r in rows if r[2] and r[1] != "PLANE"]
    print(f"  flat-but-not-PLANE faces: {len(odd)} -> {odd}")
    payload = studio._tagged_mesh(part, body_id="body")
    for fi in [r[0] for r in odd]:
        info = next((x for x in payload["faces"] if x["id"] == fi), None)
        print(f"  payload face {fi}: type={info['type']} planar={info['planar']} "
              f"area={info['area']} center={info.get('center')}")
    if odd:
        f = part.faces()[odd[0][0]]
        c = f.center()
        try:
            out = sk.face_outline_2d(part, [c.X, c.Y, c.Z],
                                     list(f.normal_at(c)),
                                     face_area=round(f.area, 2))
            print(f"  face_outline_2d on it: planar={out.get('planar')} "
                  f"outer_pts={len(out.get('outer') or [])}")
        except Exception as e:
            print(f"  face_outline_2d RAISED {e}")


def pocket_pad_doc():
    """A round pocket with a flush round pad standing in it: two +Z faces whose
    centroids coincide."""
    doc = Document(name="p-tie")
    doc.add("plate", "plate", {"width": 60, "depth": 60, "thickness": 20})
    doc.add("pk", "sketch", {"plane": "XY", "offset": 10,
                             "entities": [{"kind": "circle", "r": 20, "x": 0, "y": 0}]})
    doc.add("pk_tool", "extrude", {"amount": -6}, inputs=["pk"])
    doc.add("pocket", "cut", {}, inputs=["plate", "pk_tool"])
    doc.add("pad", "sketch", {"plane": "XY", "offset": 4,
                              "entities": [{"kind": "circle", "r": 6, "x": 0, "y": 0}]})
    doc.add("pad_tool", "extrude", {"amount": 6}, inputs=["pad"])
    doc.add("boss", "fuse", {}, inputs=["pocket", "pad_tool"])
    assert doc.rebuild(), doc.tree()
    return doc


def section2():
    print()
    print("== 2 attribute_face: the stale-index fallback ignores the area ==")
    doc = pocket_pad_doc()
    rf = doc._result_feature()
    part = doc.result()
    faces = part.faces()
    for i, f in enumerate(faces):
        c = f.center()
        print(f"  face {i:2d} type={str(f.geom_type).split('.')[-1]:10s} "
              f"area={f.area:9.3f} centre=({c.X:.3f}, {c.Y:.3f}, {c.Z:.3f})")
    # the two faces that share a centroid
    from collections import defaultdict
    by_c = defaultdict(list)
    for i, f in enumerate(faces):
        c = f.center()
        by_c[(round(c.X, 3), round(c.Y, 3), round(c.Z, 3))].append(i)
    ties = {k: v for k, v in by_c.items() if len(v) > 1}
    print(f"  coincident centroids: {ties}")
    for centre, idxs in ties.items():
        for i in idxs:
            got = P.attribute_face(doc, body_id=rf.id, face_index=i,
                                   area=faces[i].area)
            print(f"   index {i} (area {faces[i].area:.3f}) -> {got.get('feature')}")
        # now the STALE-INDEX case: the index no longer names that face
        for i in idxs:
            stale = P.attribute_face(doc, body_id=rf.id, face_index=len(faces) + 5,
                                     center=list(centre), area=faces[i].area)
            print(f"   stale index, centre {centre}, area {faces[i].area:.3f}"
                  f" -> {stale.get('feature')} "
                  f"(face {stale.get('face')})")


if __name__ == "__main__":
    section1()
    section2()
