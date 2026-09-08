"""probes/feature_faces_newest_probe.py — does provenance.feature_faces need a
"NEWEST WINS" tie-break? (Finding A of the provenance review, 2026-09-08.)

THE CLAIM under test: feature_faces asks only "is this face of the body a
trimmed survivor of a face my output has and my input did not", with no
tie-break, so a face made by a LATER feature that is COPLANAR with and inside
the bbox of an EARLIER feature's face is claimed by BOTH rows. Repro: plate b
-> pocket cut c -> a 6x6 boss sm fused so its top is FLUSH with the plate top
at z=+10, standing inside the pocket.

WHAT CAME BACK (numbers at the bottom of this file):
  SS1  CONFIRMED exactly as reported: feature_faces(doc,'b',tip) = 7 faces
       including the boss's own top (centre (5,0,10), area 36), and the Fillet
       row click lights 20 edges instead of 16.
  SS1b/c the CENTRED variant's "the picked edge … is no longer on the body" is
       a DIFFERENT bug: both tops then have centre (0,0,10) and
       blocks.resolve_face answers (0,0,10) with the 36 mm2 boss top. The
       tie-break does not fix it, and the row 'c' — whose face set never
       changes — fails the same way.
  SS2  "the LAST introducer wins" fixes it, but ONLY scoped to the body's own
       SPINE. Over the whole ancestry pool it also wipes every TOOL-BODY row
       (t, tm, sm, pm) to zero faces, which is worse than the bug. The walk
       needs feature_index ONLY — never _points — because _hosts samples the
       QUERIED face's interior point.
  SS3  Spine-scoped: not one count changes on any case of
       probes/feature_edges_probe.py §2, nor on esp32-remote. The two flush
       bosses and the cut-side twin (a boss milled back to the base face) are
       fixed the same way as the repro.
  SS4  Cheapest equivalent form ("DIP", see new_feature_faces_dip) costs
       +0.6 ms on the repro and +47 ms on esp32-remote's worst row (the base
       body), whose whole plan is 1.6 s warm.

SS1 the repro, the same boss CENTRED in x, and why the centred one raises.
SS2 the candidate rule "the LAST introducer wins", over the whole ancestry POOL
    and over the body's own SPINE.
SS3 no regression: every case of probes/feature_edges_probe.py SS2, plus six
    more coplanar shapes.
SS4 cost: the repro, a 31-feature synthetic tree, and (--big) esp32-remote.

Run: PYTHONIOENCODING=utf-8 C:/Python314/python.exe probes/feature_faces_newest_probe.py [--big]
"""
import sys
import time

sys.path.insert(0, ".")
from build123d import Face          # noqa: E402

import blocks                       # noqa: E402
import provenance                   # noqa: E402
import sketch as sk                 # noqa: E402
import toolplan                     # noqa: E402
from document import Document       # noqa: E402


# --------------------------------------------------------------- the docs ---

def doc_repro(boss_x=5.0):
    """plate 40x30x20 -> 20x12x5 pocket in the top -> a 6x6x5 boss standing in
    the pocket whose TOP is flush with the plate top (z=+10)."""
    d = Document(name="flush")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
    d.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["t"])
    d.add("c", "cut", {}, ["b", "tm"])
    d.add("s", "plate", {"width": 6, "depth": 6, "thickness": 5}, [])
    d.add("sm", "move", {"x": boss_x, "y": 0, "z": 7.5}, ["s"])
    d.add("u", "fuse", {}, ["c", "sm"])
    d.rebuild()
    return d


def doc_pocket():
    d = Document(name="p")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
    d.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["t"])
    d.add("c", "cut", {}, ["b", "tm"])
    d.rebuild()
    return d


def doc_fillet():
    d = Document(name="r")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.add("g1", "fillet", {"radius": 5, "edges": "vertical"}, ["b"])
    d.rebuild()
    return d


def doc_disc_boss():
    d = Document(name="f")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.add("p", "disc", {"radius": 6, "thickness": 5}, [])
    d.add("pm", "move", {"x": 5, "y": 0, "z": 12.5}, ["p"])
    d.add("f", "fuse", {}, ["b", "pm"])
    d.rebuild()
    return d


# ----------------------------------------------------- the candidate rule ---
# introduced_at(L, F): the EXISTING new/not-in-input test, read from the
# queried face F's side — _hosts takes F's own interior point, so the later
# features need only their feature_index, never their _points.

def _introduced_at(doc, fid, stype, key, bb, pt, analytic):
    before_id, after_id = doc.delta_features(fid)
    if doc._parts.get(after_id) is None:
        return False
    if not provenance._hosts(provenance.feature_index(doc, after_id),
                             stype, key, bb, pt, analytic):
        return False
    if before_id and doc._parts.get(before_id) is not None:
        if provenance._hosts(provenance.feature_index(doc, before_id),
                             stype, key, bb, pt, analytic):
            return False
    return True


def _pool(doc, body_id):
    """the body's own history in BUILD ORDER (attribute_face's pool)"""
    anc = provenance._ancestors(doc, body_id)
    return [f for f in provenance._solid_features(doc, upto=body_id) if f in anc]


def _skippable(doc, fid):
    try:
        f = doc.get(fid)
    except KeyError:
        return True
    return f.suppressed or f.op in sk.SKETCH_PRODUCERS


def _walk(doc, body_id, scope):
    pool = _pool(doc, body_id)
    if scope == "spine":
        spine = set(provenance._spine(doc, body_id))
        pool = [f for f in pool if f in spine]
    return [f for f in pool if not _skippable(doc, f)]


def owners(doc, body_id, scope="spine"):
    """{face key: (all introducers in build order, the LAST one)} for the body,
    with the introducer walk limited to `scope`."""
    walk = _walk(doc, body_id, scope)
    out = {}
    for row, pt in zip(provenance.feature_index(doc, body_id),
                       provenance._points(doc, body_id)):
        if pt is None:
            continue
        tf, stype, key, bb, _ = row
        analytic = len(key) > 1
        intro = [fid for fid in walk
                 if _introduced_at(doc, fid, stype, key, bb, pt, analytic)]
        out[hash(tf)] = (intro, intro[-1] if intro else None)
    return out


def new_feature_faces(doc, fid, body_id, scope="spine"):
    """THE CANDIDATE: the old answer, minus every face that a LATER feature in
    the walk also introduced (only when `fid` is itself in the walk — a TOOL
    body's row keeps its own geometry, see SS3)."""
    keys = provenance.feature_faces(doc, fid, body_id)
    walk = _walk(doc, body_id, scope)
    if fid not in walk:
        return set(keys)
    later = walk[walk.index(fid) + 1:]
    if not later:
        return set(keys)
    out = set()
    idx = {hash(r[0]): (r, p) for r, p in
           zip(provenance.feature_index(doc, body_id), provenance._points(doc, body_id))}
    for k in keys:
        row, pt = idx.get(k, (None, None))
        if row is None or pt is None:
            out.add(k)
            continue
        tf, stype, key, bb, _ = row
        analytic = len(key) > 1
        if any(_introduced_at(doc, L, stype, key, bb, pt, analytic) for L in later):
            continue                      # a later feature made it: not this row's
        out.add(k)
    return out


def new_feature_faces_fast(doc, fid, body_id, scope="spine"):
    """The same answer, shaped the way it would SHIP: the later features'
    (before_rows, after_rows) are looked up ONCE, not per face, and
    doc.delta_features (which rebuilds an id map on every call) is not called
    inside the loop."""
    keys = provenance.feature_faces(doc, fid, body_id)
    walk = _walk(doc, body_id, scope)
    if fid not in walk or not keys:
        return set(keys)
    later = []
    for L in walk[walk.index(fid) + 1:]:
        bi, ai = doc.delta_features(L)
        if doc._parts.get(ai) is None:
            continue
        after = provenance.feature_index(doc, ai)
        before = (provenance.feature_index(doc, bi)
                  if bi and doc._parts.get(bi) is not None else None)
        later.append((before, after))
    if not later:
        return set(keys)
    idx = {hash(r[0]): (r, p) for r, p in
           zip(provenance.feature_index(doc, body_id), provenance._points(doc, body_id))}
    out = set()
    for k in keys:
        row, pt = idx.get(k, (None, None))
        if row is None or pt is None:
            out.add(k)
            continue
        _tf, stype, key, bb, _ = row
        analytic = len(key) > 1
        stolen = False
        for before, after in later:
            if provenance._hosts(after, stype, key, bb, pt, analytic) and not (
                    before and provenance._hosts(before, stype, key, bb, pt, analytic)):
                stolen = True
                break
        if not stolen:
            out.add(k)
    return out


def new_feature_faces_dip(doc, fid, body_id):
    """THE CHEAP EQUIVALENT. On a SPINE, before_L is always the previous spine
    body (or None), and the tip trivially hosts every face of itself, so
    "some later spine feature introduced F" reduces to "some later spine body
    did NOT host F" — a face that VANISHED from the spine and came back was
    remade. One _hosts per later spine body, breaking at the first miss, and
    doc.delta_features is never called in the walk."""
    keys = provenance.feature_faces(doc, fid, body_id)
    walk = _walk(doc, body_id, "spine")
    if fid not in walk or not keys:
        return set(keys)
    later = [provenance.feature_index(doc, L) for L in walk[walk.index(fid) + 1:]
             if doc._parts.get(L) is not None]
    if not later:
        return set(keys)
    idx = {hash(r[0]): (r, p) for r, p in
           zip(provenance.feature_index(doc, body_id), provenance._points(doc, body_id))}
    out = set()
    for k in keys:
        row, pt = idx.get(k, (None, None))
        if row is None or pt is None:
            out.add(k)
            continue
        _tf, stype, key, bb, _ = row
        analytic = len(key) > 1
        if all(provenance._hosts(rows, stype, key, bb, pt, analytic) for rows in later):
            out.add(k)                      # never left the body: still this row's
    return out


def edges_for_keys(part, keys):
    by_edge = blocks._edge_faces(part)
    es = [e for e in part.edges()
          if any(blocks._shape_key(f) in keys for f in by_edge.get(blocks._shape_key(e), []))]
    return [e for e in es if len(by_edge.get(blocks._shape_key(e), [])) == 2]


def plan_edges(doc, body, row):
    try:
        p = toolplan.plan(doc, {"tool": "fillet", "body_id": body, "edges": [],
                                "feature_toggle": row})
        return len(p.get("edges", [])) if p.get("ok") else "ERR " + str(p.get("error"))
    except Exception as e:
        return "RAISED " + type(e).__name__ + ": " + str(e)


def face_desc(doc, body, k):
    for row in provenance.feature_index(doc, body):
        if hash(row[0]) == k:
            f = Face(row[0])
            c = f.center()
            return (f"{row[1]:9s} c=({c.X:6.2f},{c.Y:6.2f},{c.Z:6.2f}) a={f.area:8.2f}")
    return "?"


def rows_of(doc, body):
    out = []
    for f in doc.features:
        if not _skippable(doc, f.id) and doc._parts.get(f.id) is not None:
            out.append(f.id)
        if f.id == body:
            break
    return out


def compare(doc, body, label, scope="spine"):
    print(f"\n-- {label}: body {body}  (scope={scope})")
    part = doc._parts[body]
    print(f"   {len(part.faces())} faces, {len(part.edges())} edges; "
          f"spine={provenance._spine(doc, body)}  pool={_pool(doc, body)}")
    for row in rows_of(doc, body):
        try:
            old = provenance.feature_faces(doc, row, body)
        except Exception as e:
            print(f"   {row:5s}: old RAISED {e}")
            continue
        new = new_feature_faces(doc, row, body, scope)
        oe, ne = len(edges_for_keys(part, old)), len(edges_for_keys(part, new))
        flag = "  <== CHANGED" if old != new else ""
        if scope == "spine":
            dip = new_feature_faces_dip(doc, row, body)
            if dip != new:
                flag += f"  [DIP DIFFERS: {len(dip)} faces]"
        print(f"   {row:5s}: delta={doc.delta_features(row)}  faces {len(old)} -> {len(new)}"
              f"   edges {oe} -> {ne}   plan(old)={plan_edges(doc, body, row)}{flag}")
        for k in sorted(old - new, key=lambda kk: face_desc(doc, body, kk)):
            print(f"          lost: {face_desc(doc, body, k)}")


# ================================================================== SS1 ====
print("== SS1 the repro: plate -> pocket -> FLUSH boss")
d = doc_repro(boss_x=5.0)
for fid in ("b", "c", "sm", "u"):
    p = d._parts[fid]
    bb = p.bounding_box()
    print(f"  {fid:3s} bbox x[{bb.min.X:.2f},{bb.max.X:.2f}] y[{bb.min.Y:.2f},{bb.max.Y:.2f}] "
          f"z[{bb.min.Z:.2f},{bb.max.Z:.2f}]  vol={p.volume:.1f}  faces={len(p.faces())}")
tip = "u"
part = d._parts[tip]
print(f"\n  every face of the tip {tip}:")
for i, f in enumerate(part.faces()):
    c = f.center()
    print(f"    [{i:2d}] {str(f.geom_type).split('.')[-1]:9s} "
          f"c=({c.X:6.2f},{c.Y:6.2f},{c.Z:6.2f}) a={f.area:8.2f}")

print("\n  SHIPPED feature_faces / plan per row:")
claim = {}
for row in rows_of(d, tip):
    keys = provenance.feature_faces(d, row, tip)
    n = plan_edges(d, tip, row)
    print(f"    {row:5s}: delta={d.delta_features(row)}  faces={len(keys)}  "
          f"edges(own)={len(edges_for_keys(part, keys))}  plan={n}")
    for k in keys:
        print(f"           {face_desc(d, tip, k)}")
        claim.setdefault(k, []).append(row)
print("\n  faces claimed by MORE THAN ONE row:")
for k, rs in claim.items():
    if len(rs) > 1:
        print(f"    {face_desc(d, tip, k)}  <- {rs}")

print("\n  == SS1b the same boss CENTRED in x (boss_x=0)")
dc = doc_repro(boss_x=0.0)
pc = dc._parts["u"]
print(f"  tip faces={len(pc.faces())} edges={len(pc.edges())} vol={pc.volume:.1f}")
tops = [f for f in pc.faces() if abs(f.center().Z - 10) < 1e-6]
print("  faces at z=10: " + str([(round(f.area, 2),
                                 round(f.center().X, 2), round(f.center().Y, 2))
                                for f in tops]))
for row in rows_of(dc, "u"):
    keys = provenance.feature_faces(dc, row, "u")
    print(f"    {row:5s}: faces={len(keys)} own_edges={len(edges_for_keys(pc, keys))} "
          f"plan={plan_edges(dc, 'u', row)}")

print("\n  == SS1c WHY the centred case raises (is it the tie-break at all?)")
for want in ([0, 0, 10], [5, 0, 10]):
    got = blocks.resolve_face(pc, want, [0, 0, 1])
    c = got.center()
    print(f"    resolve_face(centred tip, {want}, +Z) -> area {got.area:8.2f} "
          f"c=({c.X:.2f},{c.Y:.2f},{c.Z:.2f})   <- BOTH tops have centre (0,0,10)")
for row in ("b", "c"):
    for label, keys in (("old", provenance.feature_faces(dc, row, "u")),
                        ("new", new_feature_faces(dc, row, "u", "spine"))):
        es = edges_for_keys(pc, keys)
        by = blocks._edge_faces(pc)
        refs = [blocks.edge_ref(pc, e, by) for e in es]
        try:
            n = len(toolplan._expand(pc, refs, True))
            msg = f"{n} edges"
        except Exception as e:
            msg = f"RAISED {e}"
        print(f"    row {row} {label}: {len(keys)} faces, {len(es)} own edges -> _expand: {msg}")

# ================================================================== SS2 ====
print("\n\n== SS2 the candidate: the LAST introducer wins")
print("  owner(F) for every face of the tip, scope=POOL (whole ancestry) and scope=SPINE:")
op = owners(d, tip, "pool")
osp = owners(d, tip, "spine")
for row in provenance.feature_index(d, tip):
    k = hash(row[0])
    ip, lp = op.get(k, ([], None))
    isp, lsp = osp.get(k, ([], None))
    print(f"    {face_desc(d, tip, k)}  pool intro={ip} owner={lp}   "
          f"spine intro={isp} owner={lsp}")
src = open("provenance.py", encoding="utf-8").read()
body_of_hosts = src.split("def _hosts")[1].split("def _sketch_behind")[0]
print("\n  row fields _hosts reads: " +
      str(sorted(f"row[{i}]" for i in range(5) if f"row[{i}]" in body_of_hosts)) +
      "  -> no interior point of the ROW is ever needed, only the queried face's")
compare(d, tip, "SS2 repro", "spine")
compare(d, tip, "SS2 repro", "pool")

print("\n  == SS2b the INVERSE direction on the same face (attribute_face,"
      " 'Find in Timeline')")
for i, f in enumerate(provenance.picked_faces(d, tip, part)):
    c = f.center()
    if abs(c.Z - 10) < 1e-6:
        a = provenance.attribute_face(d, body_id=tip, face_index=i, area=f.area)
        print(f"    face[{i}] z=10 a={f.area:7.2f} c=({c.X:.2f},{c.Y:.2f}) -> "
              f"feature={a.get('feature')} origin={a.get('origin')} "
              f"applied_by={a.get('applied_by')} conf={a.get('confidence')}")

# ================================================================== SS3 ====
print("\n\n== SS3 no regression (probes/feature_edges_probe.py SS2's cases)")
compare(doc_pocket(), "c", "pocketed box", "spine")
compare(doc_fillet(), "g1", "fillet doc", "spine")
compare(doc_disc_boss(), "f", "fused disc boss", "spine")
print("\n  the same two with scope=POOL (why pool is wrong):")
compare(doc_pocket(), "c", "pocketed box", "pool")
compare(doc_disc_boss(), "f", "fused disc boss", "pool")

print("\n\n== SS3b more coplanar shapes of my own")
d4 = Document(name="two")           # TWO flush bosses in one pocket
d4.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d4.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
d4.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["t"])
d4.add("c", "cut", {}, ["b", "tm"])
d4.add("s1", "plate", {"width": 6, "depth": 6, "thickness": 5}, [])
d4.add("s1m", "move", {"x": 6, "y": 0, "z": 7.5}, ["s1"])
d4.add("u1", "fuse", {}, ["c", "s1m"])
d4.add("s2", "plate", {"width": 6, "depth": 6, "thickness": 5}, [])
d4.add("s2m", "move", {"x": -6, "y": 0, "z": 7.5}, ["s2"])
d4.add("u2", "fuse", {}, ["u1", "s2m"])
d4.rebuild()
compare(d4, "u2", "two flush bosses", "spine")

d5 = Document(name="floor")         # a boss flush with the POCKET FLOOR
d5.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d5.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
d5.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["t"])
d5.add("c", "cut", {}, ["b", "tm"])
d5.add("s", "plate", {"width": 8, "depth": 8, "thickness": 4}, [])
d5.add("sm", "move", {"x": 4, "y": 0, "z": 3}, ["s"])   # z 1..5: top flush with the floor
d5.add("u", "fuse", {}, ["c", "sm"])
d5.rebuild()
compare(d5, "u", "boss buried, top flush with the pocket FLOOR", "spine")

d6 = Document(name="thru")          # a THROUGH pocket
d6.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d6.add("t", "plate", {"width": 20, "depth": 12, "thickness": 30}, [])
d6.add("c", "cut", {}, ["b", "t"])
d6.rebuild()
compare(d6, "c", "through pocket", "spine")

d7 = Document(name="side")          # a boss flush with a SIDE wall
d7.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d7.add("s", "plate", {"width": 10, "depth": 6, "thickness": 6}, [])
d7.add("sm", "move", {"x": 15, "y": 0, "z": 14}, ["s"])  # x 10..20: flush with the x=+20 wall
d7.add("u", "fuse", {}, ["b", "sm"])
d7.rebuild()
compare(d7, "u", "boss flush with the x=+20 side wall", "spine")

d9 = Document(name="milled")        # THE CUT-SIDE TWIN: a boss milled back to
d9.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])   # the base face
d9.add("s", "plate", {"width": 20, "depth": 12, "thickness": 5}, [])
d9.add("sm", "move", {"x": 0, "y": 0, "z": 12.5}, ["s"])   # boss z 10..15 on the top
d9.add("u", "fuse", {}, ["b", "sm"])
d9.add("t2", "plate", {"width": 8, "depth": 6, "thickness": 5}, [])
d9.add("t2m", "move", {"x": 0, "y": 0, "z": 12.5}, ["t2"])  # cuts z 10..15: floor AT z=10
d9.add("c2", "cut", {}, ["u", "t2m"])
d9.rebuild()
compare(d9, "c2", "boss milled back to the base face (floor coplanar with the plate top)",
        "spine")

d10 = Document(name="moved")        # the WHOLE BODY moved after its features
d10.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d10.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
d10.add("tm", "move", {"x": 0, "y": 0, "z": 10}, ["t"])
d10.add("c", "cut", {}, ["b", "tm"])
d10.add("mv", "move", {"x": 100, "y": 0, "z": 0}, ["c"])
d10.rebuild()
compare(d10, "mv", "the whole body MOVED after its features", "spine")

print("\n  and the same two flush bosses with scope=POOL, for the record:")
compare(d4, "u2", "two flush bosses", "pool")

# ================================================================== SS4 ====
print("\n\n== SS4 cost")


def timeit(fn, n=5):
    fn()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    return min(ts), sum(ts) / len(ts)


for label, dd, body, row in (("repro b", d, "u", "b"), ("repro u", d, "u", "u"),
                             ("repro c", d, "u", "c")):
    assert new_feature_faces(dd, row, body) == new_feature_faces_fast(dd, row, body)
    o = timeit(lambda: provenance.feature_faces(dd, row, body))
    nn = timeit(lambda: new_feature_faces(dd, row, body, "spine"))
    nf = timeit(lambda: new_feature_faces_fast(dd, row, body, "spine"))
    nd = timeit(lambda: new_feature_faces_dip(dd, row, body))
    print(f"  {label:10s} old {o[0]:7.2f}/{o[1]:7.2f}   naive {nn[0]:7.2f}/{nn[1]:7.2f}   "
          f"delta {nf[0]:7.2f}/{nf[1]:7.2f}   DIP {nd[0]:7.2f}/{nd[1]:7.2f} ms  (min/avg 5)")

print("\n  a synthetic tree of 31 features (a plate + 10 folded pockets)")
d8 = Document(name="syn")
d8.add("b", "plate", {"width": 120, "depth": 80, "thickness": 20}, [])
prev = "b"
for i in range(10):
    d8.add(f"t{i}", "plate", {"width": 6, "depth": 6, "thickness": 10}, [])
    d8.add(f"t{i}m", "move", {"x": -50 + 10 * i, "y": 0, "z": 12}, [f"t{i}"])
    d8.add(f"c{i}", "cut", {}, [prev, f"t{i}m"])
    prev = f"c{i}"
d8.rebuild()
print(f"  features={len(d8.features)} tip={prev} faces={len(d8._parts[prev].faces())} "
      f"spine={len(provenance._spine(d8, prev))} pool={len(_pool(d8, prev))}")
for row in ("b", "c0", "c9"):
    ko = provenance.feature_faces(d8, row, prev)
    kn = new_feature_faces(d8, row, prev, "spine")
    assert kn == new_feature_faces_fast(d8, row, prev, "spine")
    o = timeit(lambda: provenance.feature_faces(d8, row, prev))
    nn = timeit(lambda: new_feature_faces(d8, row, prev, "spine"))
    nf = timeit(lambda: new_feature_faces_fast(d8, row, prev, "spine"))
    nd = timeit(lambda: new_feature_faces_dip(d8, row, prev))
    print(f"  row {row:4s} faces {len(ko)} -> {len(kn)} (dip "
          f"{len(new_feature_faces_dip(d8, row, prev))})   old {o[0]:7.2f}/{o[1]:7.2f}   "
          f"naive {nn[0]:7.2f}/{nn[1]:7.2f}   delta {nf[0]:7.2f}/{nf[1]:7.2f}   "
          f"DIP {nd[0]:7.2f}/{nd[1]:7.2f} ms")

if "--big" in sys.argv:
    print("\n  == SS4b tests/fixtures/esp32-remote.tcad.json (rebuilt ONCE)")
    big = Document.load("tests/fixtures/esp32-remote.tcad.json")
    t0 = time.perf_counter()
    big.rebuild()
    print(f"  rebuild {time.perf_counter() - t0:.1f} s")
    btip = big._result_feature().id
    bpart = big._parts[btip]
    print(f"  tip {btip}: {len(bpart.faces())} faces, {len(bpart.edges())} edges, "
          f"spine={len(provenance._spine(big, btip))}, pool={len(_pool(big, btip))}, "
          f"walk={len(_walk(big, btip, 'spine'))}")
    solids = [f.id for f in big.features if f.volume is not None and not f.suppressed]
    picks = solids[:1] + solids[-5:]
    for fid in picks:
        try:
            t0 = time.perf_counter()
            ko = provenance.feature_faces(big, fid, btip)
            told_cold = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            kn = new_feature_faces_dip(big, fid, btip)
            tnew_cold = (time.perf_counter() - t0) * 1000
            kd = new_feature_faces_fast(big, fid, btip, "spine")
            o = timeit(lambda: provenance.feature_faces(big, fid, btip), 3)
            nf = timeit(lambda: new_feature_faces_fast(big, fid, btip, "spine"), 3)
            nd = timeit(lambda: new_feature_faces_dip(big, fid, btip), 3)
            t0 = time.perf_counter()
            pe = plan_edges(big, btip, fid)
            tplan = (time.perf_counter() - t0) * 1000
            tplan2 = timeit(lambda: plan_edges(big, btip, fid), 3)
            print(f"  row {fid:26s} faces {len(ko):3d} -> delta {len(kd):3d} dip {len(kn):3d}  "
                  f"cold dip {tnew_cold:7.0f} ms  warm old {o[0]:6.1f} delta {nf[0]:6.1f} "
                  f"DIP {nd[0]:6.1f} ms  plan(old)={pe!s:>5} cold {tplan:7.0f} "
                  f"warm {tplan2[0]:7.0f} ms")
        except Exception as e:
            print(f"  row {fid:26s} RAISED {type(e).__name__}: {e}")

# ===========================================================================
# MEASURED 2026-09-08 (C:/Python314, this machine). Everything below is a
# number this file printed.
#
# SS1  CONFIRMED. tip u = 16 faces / 36 edges; the boss's own top is
#      PLANE c=(5.00, 0.00, 10.00) a=36.00.
#        row b : faces 7  own edges 20  plan 20     <- WRONG, 6 / 16 / 16 is right
#        row c : faces 5  own edges 16  plan 16
#        row sm: faces 5  own edges 12  plan 12
#        row u : faces 5  own edges 12  plan 12
#      claimed by more than one row: the boss top by ['b', 'sm', 'u'];
#      (the pocket faces by ['t','tm','c'] and the boss sides by ['sm','u'] —
#      TOOL-BODY rows, by design, not the bug).
# SS1b boss CENTRED in x: rows b, tm AND c all fail with "the picked edge at
#      (…) is no longer on the body". SS1c shows why, and it is NOT this
#      finding: both tops have centre (0,0,10), and
#        blocks.resolve_face(tip, [0,0,10], +Z) -> area 36.00   (the BOSS top)
#        blocks.resolve_face(tip, [5,0,10], +Z) -> area 960.00  (the plate top)
#      so resolve_edge's two stored face centres land on the wrong faces and
#      no shared edge is found. With the tie-break applied, row b still
#      raises (16 edges instead of 20, same sentence) and row c — whose face
#      set does not change at all — raises either way. SEPARATE BUG.
# SS2  owner(F), whole ancestry POOL vs the body's own SPINE:
#        boss top  pool intro=['b','sm','u'] owner=u | spine intro=['b','u'] owner=u
#        boss sides pool intro=['sm','u'] owner=u    | spine intro=['u'] owner=u
#        pocket    pool intro=['t','tm','c'] owner=c | spine intro=['c'] owner=c
#      _hosts reads row[0..4] only (tface, type, key, bbox, lazy OnFace) — the
#      interior point is the QUERIED face's, so the walk needs feature_index
#      and NEVER _points.
# SS2b the INVERSE direction is wrong on the SAME face, and says so with high
#      confidence — attribute_face takes the EARLIEST hosting ancestor:
#        face[15] z=10 a=36.00 c=(5.00,0.00) -> feature=b origin=b
#                                               applied_by=b conf=high
#      (face[2], the real plate top a=960.00, correctly reports b). So "Find
#      in Timeline" on the boss's own top names the base plate. Same root
#      cause, second symptom.
#      scope=SPINE on the repro: b 7->6 faces, 20->16 edges; t/tm/c/sm/u all
#      unchanged.  scope=POOL: b 7->6 BUT t 1->0, tm 5->0, sm 5->0 — the
#      tool-body rows are wiped, so POOL is wrong.
# SS3  spine scope, old -> new, every case of probes/feature_edges_probe.py §2:
#        pocketed box  c: b 6/16, t 1/4,  tm 5/12, c 5/12   ALL UNCHANGED
#        fillet doc   g1: b 6/24, g1 4/16                   ALL UNCHANGED
#        fused disc    f: b 6/13, p 0/0, pm 2/2, f 2/2       ALL UNCHANGED
#      POOL on the same: t 1->0, tm 5->0 (pocketed box), pm 2->0 (disc boss).
# SS3b my own coplanar shapes (spine scope):
#        two flush bosses  u2: b 8->6 faces, 24->16 edges (both boss tops go
#                              to u1 / u2); every other row unchanged   RIGHT
#        boss flush with the pocket FLOOR: the fuse is absorbed (11 faces,
#                              vol unchanged) — sm/u already 0; no change
#        through pocket     c: b 6/20, t 4/12, c 4/12       UNCHANGED
#        boss flush with the x=+20 side wall: b 6/12, sm 6/12, u 6/12
#                              UNCHANGED (the boss face sticks out of the
#                              wall's bbox, so it was never mis-claimed)
#        THE CUT-SIDE TWIN — a 20x12x5 boss milled back to the base face, so
#        the pocket FLOOR is coplanar with and inside the plate top:
#                           b 7->6 faces, 20->16 edges      RIGHT (same bug,
#                              made by a CUT instead of a fuse)
#        the whole body MOVED after its features: b/t/tm/c were ALREADY 0
#                              old and new — a pre-existing limitation, not a
#                              regression of this fix
# SS4  cost (min/avg of 5, warm; "delta" = the delta_features form, "DIP" =
#      the cheap equivalent — the two agreed on EVERY case above):
#        repro row b            old 0.32  naive 1.58  delta 1.39  DIP 0.90 ms
#        repro row u            old 0.67  naive 1.39  delta 1.40  DIP 1.36 ms
#        31-feature tree, row b old 0.51  naive 5.58  delta 4.92  DIP 3.53 ms
#        31-feature tree, c0    old 0.62  naive 5.53  delta 4.01  DIP 2.43 ms
#      esp32-remote (rebuild 12.1 s once; tip 254 faces / 609 edges,
#      spine 25, pool 50, spine walk 22) — NO face count changes at all:
#        row body        23 -> 23  warm old  4.7  delta 96.0  DIP 51.8 ms
#                                  plan(old) 112 edges  cold 2782  warm 1612 ms
#        row strap_pilots 4 ->  4  warm old 14.8  delta 16.4  DIP 17.4 ms
#        row ringA_tool  17 -> 17  warm old  1.8  delta  2.3  DIP  2.3 ms
#        row ringB_tool  16 -> 16  warm old  2.3  delta  2.9  DIP  2.8 ms
#        row ring_band   16 -> 16  warm old  2.3  delta  3.2  DIP  3.2 ms
#        row esp32_remote 33 -> 33 warm old 24.8  delta 24.9  DIP 39.5 ms
#      cold DIP on the base-body row 865 ms (it pays for the tip's interior
#      points, which the old code pays for too). The worst warm add is +47 ms
#      on the base-body row, against a 1612 ms plan for that row — under 3%.
