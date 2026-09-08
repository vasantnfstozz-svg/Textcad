"""probes/feature_edges_probe.py — which EDGES of the current body does a
FEATURE own? (Fillet's tree-row and face selection, 2026-09-08.)

The user's ask: "if I am selecting an extrude and pressing Fillet, those
selected face or body edges should be selected". Fusion's Fillet has the same
three selection kinds — edges, faces, features — and a feature means the
edges of the faces it created, as they exist NOW.

The rule under test: a face of the current body belongs to feature F when it
is a trimmed survivor of a face that F's own output has and F's input did
not (provenance's host test: same type, same infinite surface, bbox
containment, interior point). An edge belongs to F when one of the faces it
bounds does.

§1 identity: does hash(face.wrapped) (blocks._shape_key) equal hash(tf) for
   the TopoDS faces provenance indexes? (the edge->faces map is keyed on the
   former, the index rows carry the latter)
§2 the rule on a pocketed box — the cut, the base plate, the tool prism, a
   fillet feature, a fused boss — and what it costs
§3 the face pick's guard: a face of the PREVIEW body (a fillet band) has no
   twin on the input body — resolve_face's nearest-centre answer must be
   refused, a trimmed survivor (the top face) accepted
§4 (--big) what a row click costs on tests/fixtures/esp32-remote through the
   shipped code. FIRST RUN, 2026-09-08: 5-150 SECONDS a click (ring_band's 48
   edges: 55 s). cProfile put 31.5 of 33.7 s in toolplan._expand — not in
   feature_faces (1.5 s cold, cached after) but in RESOLVING the picks:
   blocks.resolve_face measured the centre of all 254 faces for both stored
   faces of every edge (96 calls, 15 s) and tangent_chain rebuilt the vertex
   table from part.edges() per edge (265 ms each, 12.7 s). Both are now
   enumerated once per built Part and kept BESIDE it (blocks._face_rows,
   blocks._edge_topo via blocks._cached — never as an attribute on the shape:
   probes/shape_cache_probe.py); the second run is recorded below the code.

Run: C:\\Python314\\python.exe probes/feature_edges_probe.py [--big]
"""
import sys
import time

sys.path.insert(0, ".")
from build123d import Face   # noqa: E402

import blocks                # noqa: E402
import provenance            # noqa: E402
from document import Document  # noqa: E402


def doc_pocket():
    doc = Document(name="p")
    doc.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    doc.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
    doc.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["t"])
    doc.add("c", "cut", {}, ["b", "tm"])
    doc.rebuild()
    return doc


def feature_faces(doc, fid, body):
    """the faces of `body` that feature `fid` made (candidate rule)"""
    before_id, after_id = doc.delta_features(fid)
    after_rows = provenance.feature_index(doc, after_id)
    before_rows = provenance.feature_index(doc, before_id) if before_id else []
    new_rows = []
    for row in after_rows:
        tf, stype, key, bb, _ = row
        pt = provenance.interior_point(Face(tf))
        if pt is None:
            continue
        if before_rows and provenance._hosts(before_rows, stype, key, bb, pt, len(key) > 1):
            continue                      # F's input had it already: not F's
        new_rows.append(row)
    keys = set()
    for row in provenance.feature_index(doc, body):
        tf, stype, key, bb, _ = row
        pt = provenance.interior_point(Face(tf))
        if pt is not None and provenance._hosts(new_rows, stype, key, bb, pt, len(key) > 1):
            keys.add(hash(tf))
    return keys, len(new_rows)


def feature_edges(doc, fid, body):
    part = doc._parts[body]
    keys, n_new = feature_faces(doc, fid, body)
    by_edge = blocks._edge_faces(part)
    out = [e for e in part.edges()
           if any(blocks._shape_key(f) in keys for f in by_edge.get(blocks._shape_key(e), []))]
    return out, keys, n_new


print("== §1 identity")
doc = doc_pocket()
part = doc._parts["c"]
fs, tfs = part.faces(), provenance.topo_faces(part)
print("faces", len(fs), len(tfs))
print("hash(face.wrapped) == hash(topo face), in order:",
      all(hash(f.wrapped) == hash(tf) for f, tf in zip(fs, tfs)))
print("as sets:", {hash(f.wrapped) for f in fs} == {hash(tf) for tf in tfs})
print("stable across two faces() calls:",
      [hash(f.wrapped) for f in part.faces()] == [hash(f.wrapped) for f in fs])

print("\n== §2 the rule on a pocketed box (body c = 40x30x20 with a 20x12x5 pocket)")
for fid in ("c", "b", "tm", "t"):
    t0 = time.perf_counter()
    edges, keys, n_new = feature_edges(doc, fid, "c")
    dt = (time.perf_counter() - t0) * 1000
    print(f"  {fid:3s}: delta={doc.delta_features(fid)} new faces on its output={n_new} "
          f"faces on c={len(keys)} edges on c={len(edges)}  ({dt:.1f} ms)")
    zs = sorted({round((e @ 0.5).Z, 3) for e in edges})
    print(f"       edge midpoint z levels: {zs}")

print("\n-- a fillet feature (vertical corners r5) on its own body")
d2 = Document(name="r")
d2.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d2.add("g1", "fillet", {"radius": 5, "edges": "vertical"}, ["b"])
d2.rebuild()
edges, keys, n_new = feature_edges(d2, "g1", "g1")
print(f"  g1: new faces={n_new} faces on g1={len(keys)} edges on g1={len(edges)} "
      f"types={sorted({blocks._gtype(e) for e in edges})}")
edges, keys, n_new = feature_edges(d2, "b", "g1")
print(f"  b on g1: faces={len(keys)} edges={len(edges)} (the plate's faces as they are now)")

print("\n-- a fused boss (disc r6 h5 on the top)")
d3 = Document(name="f")
d3.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d3.add("p", "disc", {"radius": 6, "thickness": 5}, [])
d3.add("pm", "move", {"x": 5, "y": 0, "z": 12.5}, ["p"])
d3.add("f", "fuse", {}, ["b", "pm"])
d3.rebuild()
for fid in ("f", "pm", "b"):
    edges, keys, n_new = feature_edges(d3, fid, "f")
    print(f"  {fid:3s}: delta={d3.delta_features(fid)} new={n_new} faces on f={len(keys)} "
          f"edges on f={len(edges)} types={sorted({blocks._gtype(e) for e in edges})}")

print("\n== §3 the face pick's guard (a click on the PREVIEW body)")
b, g1 = d2._parts["b"], d2._parts["g1"]
band = next(f for f in g1.faces() if blocks._gtype(f) == "CYLINDER")
c = band.center()
near = blocks.resolve_face(b, [c.X, c.Y, c.Z], None)
bb = near.bounding_box()
inside = (bb.min.X - 0.05 <= c.X <= bb.max.X + 0.05 and bb.min.Y - 0.05 <= c.Y <= bb.max.Y + 0.05
          and bb.min.Z - 0.05 <= c.Z <= bb.max.Z + 0.05)
print(f"  band centre {[round(v, 2) for v in (c.X, c.Y, c.Z)]} -> nearest face of b is "
      f"{blocks._gtype(near)} with bbox x[{bb.min.X:.2f},{bb.max.X:.2f}] y[{bb.min.Y:.2f},{bb.max.Y:.2f}]"
      f" -> inside bbox: {inside} (want False: refuse)")
topf = next(f for f in g1.faces() if abs(f.normal_at(f.center()).Z - 1) < 1e-6)
c = topf.center()
near = blocks.resolve_face(b, [c.X, c.Y, c.Z], [0, 0, 1])
bb = near.bounding_box()
inside = (bb.min.X - 0.05 <= c.X <= bb.max.X + 0.05 and bb.min.Y - 0.05 <= c.Y <= bb.max.Y + 0.05
          and bb.min.Z - 0.05 <= c.Z <= bb.max.Z + 0.05)
print(f"  top centre {[round(v, 2) for v in (c.X, c.Y, c.Z)]} -> {blocks._gtype(near)} "
      f"z[{bb.min.Z:.2f},{bb.max.Z:.2f}] -> inside: {inside} (want True: accept), "
      f"edges of that face on b: {len(near.edges())}")

# §4 (opt-in, --big: the fixture rebuilds in 30-45 s): what a tree-row click
# costs on a real design, through the SHIPPED code (provenance.feature_faces
# and toolplan.plan) — first click on a body pays for its interior points,
# every later one is bbox / key arithmetic
if "--big" in sys.argv:
    import toolplan   # noqa: E402
    print("\n== §4 cost on a real design (tests/fixtures/esp32-remote.tcad.json)")
    big = Document.load("tests/fixtures/esp32-remote.tcad.json")
    t0 = time.perf_counter()
    big.rebuild()
    print(f"  rebuild {time.perf_counter() - t0:.1f} s")
    tip = big._result_feature().id
    tpart = big._parts[tip]
    print(f"  tip {tip}: {len(tpart.faces())} faces, {len(tpart.edges())} edges")
    solids = [f.id for f in big.features if f.volume is not None and not f.suppressed]
    for fid in solids[-6:]:
        t0 = time.perf_counter()
        p = toolplan.plan(big, {"tool": "fillet", "body_id": tip, "edges": [], "feature_toggle": fid})
        dt = (time.perf_counter() - t0) * 1000
        n = len(p.get("edges", [])) if p["ok"] else p["error"]
        print(f"  row {fid:28s}: {n!s:>4} edges  {dt:7.0f} ms")
    t0 = time.perf_counter()
    p = toolplan.plan(big, {"tool": "fillet", "body_id": tip, "edges": [], "feature_toggle": solids[0]})
    print(f"  row {solids[0]:28s}: {len(p.get('edges', []))!s:>4} edges  "
          f"{(time.perf_counter() - t0) * 1000:7.0f} ms  (the base body's row)")
    # RECORDED 2026-09-08, ring_band (48 edges), same machine:
    #   before the caches   plan 33.7 s (cProfile: _expand 31.5 s — resolve_face
    #                       15.2 s over 96 calls, tangent_chain 12.7 s over 48)
    #   _face_rows + _edge_topo   cold 5.8 s, warm re-plan 0.94 s (tangent_chain
    #                       0.71 s: 2672 tangents evaluated in the walk)
    #   + end tangents in _edge_topo   warm re-plan 0.37 s (edge_ref 0.13,
    #                       resolve_edge 0.10, edge_polyline 0.06)
