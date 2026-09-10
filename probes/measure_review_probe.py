"""Probes behind the section 6 review of Measure and drive (2026-09-10).

Every finding in that review was reproduced by measurement before it was
fixed, and this file is that measurement, kept so the next reader does not
have to re-derive it. Run it with C:\\Python314\\python.exe from the repo root.

    §1  mesh mode handed out edge ids that were not part.edges() indices  (P0)
    §2  the verification re-read a face INDEX a rebuild had renumbered   (P1)
    §3  an imported STL answered "click it again" for ever               (P1)
    §4  a tilted face's extents came from the WORLD bounding box         (P2)
    §5  a dimension typed to 4 decimals was written, then reverted       (P2)
    §6  a bore's "centre" was an arbitrary point along its axis          (P3)

§1, §2 and §5 read the user's saved designs, so they are read-only: never
call /api/open here, which pushes an "opened" version into a real history.
"""
import json
import math
import os
import sys

from build123d import Box, Compound, Pos

sys.path.insert(0, ".")
import measure                                         # noqa: E402
import studio                                          # noqa: E402
from document import Document                          # noqa: E402

DESIGNS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "designs")


def load(name):
    with open(os.path.join(DESIGNS, f"{name}.tcad.json"), encoding="utf-8") as fh:
        doc = Document.from_data(json.load(fh))
    doc.rebuild()
    return doc


def s1_edge_ids_in_mesh_mode():
    """A body over MESH_MODE_FACES advertised one id PER ADJACENT FACE, in
    face order, while measure.resolve() indexes part.edges(). Before the fix
    esp32-remote handed out 7176 ids for 3588 real edges and 6517 of them
    resolved to a different edge; isogrid-panel 1641 for 927."""
    part = Compound(children=[Pos(i * 40, 0, 0) * Box(2 + i, 3 + i * 0.5,
                                                      4 + i * 0.25)
                              for i in range(70)])
    tm = studio._tagged_mesh(part, body_id="b")
    real = part.edges()
    wrong = sum(1 for e in tm["edges"]
                if e["id"] >= len(real)
                or abs(round(float(real[e["id"]].length), 2) - e["length"]) > .011)
    print(f"§1 synthetic {len(part.faces())} faces: {len(tm['edges'])} ids for "
          f"{len(real)} edges, {wrong} resolving elsewhere")

    for name in ("esp32-remote", "isogrid-panel", "cam-cover-plaque"):
        doc = load(name)
        part = doc.result()
        tm = studio._tagged_mesh(part, body_id=doc._result_feature().id)
        real = part.edges()
        wrong = sum(1 for e in tm["edges"]
                    if e["id"] >= len(real)
                    or abs(round(float(real[e["id"]].length), 2)
                           - e["length"]) > .011)
        print(f"§1 {name}: {len(part.faces())} faces, {len(tm['edges'])} ids "
              f"for {len(real)} edges, {wrong} resolving elsewhere")


def s2_the_index_a_rebuild_renumbers():
    """x-frame's pad hole: asking a ⌀8 bore for 8.5 really made it 8.5
    (volume 116961.184 -> 116896.394), and the verification then re-read face
    INDEX 17 — a different ⌀8 bore by then — and reverted the whole edit."""
    doc = load("x-frame")
    rid = doc._result_feature().id
    a = {"body": rid, "kind": "face", "id": 17}
    before = measure.measure(doc, a)
    plan = measure.plan_set(doc, a, None, 8.5)
    vol0 = doc.result().volume
    measure.write(doc, plan)
    doc._mark_stale()
    doc.rebuild()
    print(f"§2 x-frame face 17 was {before['label']}; after the write the "
          f"volume is {vol0:.3f} -> {doc.result().volume:.3f}, "
          f"the SAME index reads {measure.measure(doc, a).get('label')}, "
          f"and relocated it reads "
          f"{measure.remeasure(doc, plan, a).get('label')}")


def s3_an_imported_mesh_body():
    """21552 triangles are tagged as ONE mesh pseudo-face, id -1, so every
    click used to answer "face -1 is not on this body any more"."""
    doc = Document(name="probe-stl")
    doc.add("m", "import_stl",
            {"file": "liquid-piston-2-v1.stl", "scale": 1.0}, [])
    doc.rebuild()
    rid = doc._result_feature().id
    tm = studio._tagged_mesh(doc.result(), body_id=rid)
    ids = sorted({f["id"] for f in tm["faces"]})
    print(f"§3 {len(doc.result().faces())} faces, ids handed out: {ids}")
    print("§3 measuring one:",
          measure.measure(doc, {"body": rid, "kind": "face", "id": -1}))


def s4_a_tilted_face():
    """The world bbox of a 6 mm 45° chamfer is 6.00 across; the face is
    6*sqrt(2) = 8.485. studio._tagged_mesh already projected into the plane
    frame and said 8.49 for the SAME face."""
    doc = Document(name="probe-chamfer")
    doc.add("b", "plate", {"width": 100, "depth": 60, "thickness": 20})
    doc.add("ch", "chamfer", {"length": 6, "edges": "top"}, inputs=["b"])
    doc.rebuild()
    rid = doc._result_feature().id
    fi = next(i for i, f in enumerate(doc.result().faces())
              if 0.01 < abs(f.normal_at(f.center()).Z) < 0.99)
    rows = dict(measure.measure(doc, {"body": rid, "kind": "face",
                                      "id": fi})["rows"])
    meta = next(m for m in studio._tagged_mesh(doc.result(), body_id=rid)["faces"]
                if m["id"] == fi)
    print(f"§4 Measure says extents {rows.get('extents')!r}; the pick panel "
          f"says {meta.get('extents')}; 6*sqrt(2) = {6 * math.sqrt(2):.4f}")


def s5_four_decimals():
    """A readout is rounded to 3 dp for display. Comparing that against the
    RAW request threw away every inch size: 5/16" = 7.9375, 7/16" = 11.1125."""
    doc = Document(name="probe-inch")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    doc.add("sk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "mode": "add",
                           "x": 15, "y": 0, "r": 9}]}, inputs=["b"])
    doc.add("tool", "extrude", {"amount": -5}, inputs=["sk"])
    doc.add("pk", "cut", {}, inputs=["b", "tool"])
    doc.rebuild()
    rid = doc._result_feature().id
    a = {"body": rid, "kind": "face", "id":
         next(i for i, f in enumerate(doc.result().faces())
              if "CYLINDER" in str(f.geom_type) and abs(f.radius - 9) < 1e-9)}
    for want in (18.0, 7.9375, 11.1125, 12.3456):
        plan = measure.plan_set(doc, a, None, want)
        probe = Document.from_data(json.loads(json.dumps(doc.to_data())))
        probe.rebuild()
        measure.write(probe, plan)
        probe._mark_stale()
        probe.rebuild()
        got = measure.remeasure(probe, plan, a).get("value")
        print(f"§5 asked {want}: param {plan['param']}, re-measured {got}, "
              f"raw compare {abs(float(got) - want) <= 1e-4}, "
              f"rounded compare {abs(float(got) - measure._r(want)) <= 1e-4}")


def s6_a_bore_centre():
    """axis_of_rotation.position is arbitrary ALONG the axis: for a 5 mm
    pocket in a 12 mm plate OCCT hands back the mouth, z=6, not z=3.5."""
    doc = Document(name="probe-centre")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    doc.add("sk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "mode": "add",
                           "x": 15, "y": 0, "r": 9}]}, inputs=["b"])
    doc.add("tool", "extrude", {"amount": -5}, inputs=["sk"])
    doc.add("pk", "cut", {}, inputs=["b", "tool"])
    doc.rebuild()
    rid = doc._result_feature().id
    fi = next(i for i, f in enumerate(doc.result().faces())
              if "CYLINDER" in str(f.geom_type) and abs(f.radius - 9) < 1e-9)
    bb = doc.result().faces()[fi].bounding_box()
    rows = dict(measure.measure(doc, {"body": rid, "kind": "face",
                                      "id": fi})["rows"])
    print(f"§6 the wall spans z {bb.min.Z}..{bb.max.Z} (middle "
          f"{(bb.min.Z + bb.max.Z) / 2}); the panel says centre "
          f"{rows.get('centre')!r}")


if __name__ == "__main__":
    for fn in (s1_edge_ids_in_mesh_mode, s2_the_index_a_rebuild_renumbers,
               s3_an_imported_mesh_body, s4_a_tilted_face, s5_four_decimals,
               s6_a_bore_centre):
        print(f"\n--- {fn.__name__} ---")
        fn()
