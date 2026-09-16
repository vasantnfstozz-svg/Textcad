"""Section 10 review probe, part two.

3  A body over MESH_MODE_FACES faces is drawn as ONE pseudo-face (id -1, no
   centre), so every face click asks the provenance panel about face -1.
4  resolve_face's new SIZE GATE can move a stored edge's host face onto a
   same-sized neighbour, and resolve_edge then REFUSES an edge that is still
   on the body.
"""

import blocks
import studio
from document import Document


def section3():
    print("== 3 a body past MESH_MODE_FACES has no pickable faces ==")
    doc = Document(name="p-mesh")
    doc.add("plate", "plate", {"width": 60, "depth": 60, "thickness": 10})
    doc.add("bolts", "with_bolt_circle",
            {"count": 210, "bolt_radius": 0.6, "pitch_circle_dia": 50},
            inputs=["plate"])
    assert doc.rebuild(), doc.tree()
    part = doc.result()
    n = len(part.faces())
    print(f"  faces on the body: {n}   MESH_MODE_FACES={studio.MESH_MODE_FACES}")
    payload = studio._tagged_mesh(part, body_id="bolts")
    ids = sorted({f["id"] for f in payload["faces"]})
    print(f"  distinct face ids in the payload: {len(ids)} -> {ids[:6]}")
    for f in payload["faces"][:3]:
        print(f"   {f}")
    # what the provenance panel is asked, and what it answers
    import provenance as P
    ans = P.attribute_face(doc, body_id="bolts",
                           face_index=studio.MESH_FACE_ID,
                           center=None, area=payload["faces"][0].get("area"))
    print(f"  attribute_face(face=-1, center=None) -> {ans}")


def pads_doc(w_p=20.0):
    """A plate with TWO pads on top whose tops are the SAME area."""
    doc = Document(name="p-pads")
    doc.add("plate", "plate", {"width": 90, "depth": 40, "thickness": 10})
    doc.add("skP", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": w_p, "h": 10, "x": -25, "y": 0}]})
    doc.add("padP", "extrude", {"amount": 6}, inputs=["skP"])
    doc.add("joinP", "fuse", {}, inputs=["plate", "padP"])
    doc.add("skQ", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": 25, "h": 8, "x": 25, "y": 0}]})
    doc.add("padQ", "extrude", {"amount": 6}, inputs=["skQ"])
    doc.add("joinQ", "fuse", {}, inputs=["joinP", "padQ"])
    assert doc.rebuild(), doc.tree()
    return doc


def section4():
    print()
    print("== 4 the size gate can REFUSE an edge that is still on the body ==")
    doc = pads_doc(20.0)
    part = doc.result()
    for i, f in enumerate(part.faces()):
        c = f.center()
        n = f.normal_at(c)
        print(f"  face {i:2d} area={f.area:8.3f} centre=({c.X:7.2f},{c.Y:6.2f},{c.Z:6.2f})"
              f" n=({n.X:5.2f},{n.Y:5.2f},{n.Z:5.2f})")
    # the edge between pad P's top and pad P's +X wall
    top = [f for f in part.faces()
           if abs(f.normal_at(f.center()).Z - 1) < 1e-6
           and abs(f.center().Z - 11) < 1e-6 and f.center().X < 0]
    print(f"  pad P tops found: {len(top)} area={[round(f.area, 3) for f in top]}")
    tp = top[0]
    cand = [e for e in blocks._face_edges(part, tp)]
    # pick the edge on the +X side of pad P
    e = max(cand, key=lambda e: (e @ 0.5).X)
    ref = blocks.edge_ref(part, e)
    print(f"  stored edge ref: mid={ref['mid']} faces="
          f"{[(f['center'], f['area']) for f in ref['faces']]}")
    got = blocks.resolve_edge(part, ref)
    print(f"  resolves on the SAME body: mid={[round(v, 3) for v in (got @ 0.5).to_tuple()]}")

    # now the upstream edit: pad P gets wider
    doc2 = pads_doc(24.0)
    part2 = doc2.result()
    print("  -- after the pad P width edit 20 -> 24 --")
    for i, f in enumerate(part2.faces()):
        c = f.center()
        n = f.normal_at(c)
        if abs(n.Z - 1) < 1e-6:
            print(f"   +Z face {i:2d} area={f.area:8.3f} centre=({c.X:7.2f},{c.Y:6.2f},{c.Z:6.2f})")
    for label, r in (("WITH the stored size", ref),
                     ("WITHOUT it (yesterday's rule)",
                      {**ref, "faces": [{k: v for k, v in f.items() if k != "area"}
                                        for f in ref["faces"]]})):
        try:
            g = blocks.resolve_edge(part2, r)
            m = g @ 0.5
            print(f"   {label}: edge at ({m.X:.3f}, {m.Y:.3f}, {m.Z:.3f})")
        except Exception as exc:
            print(f"   {label}: REFUSED -- {exc}")


if __name__ == "__main__":
    section3()
    section4()
