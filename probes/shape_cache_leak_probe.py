"""probes/shape_cache_leak_probe.py — does blocks._SHAPE_CACHES ever let go?
(Finding C of the old-module review, 2026-09-08.)

The report: the WeakKeyDictionary keyed on the Part cannot expire, because the
Faces/Edges in its VALUE carry topo_parent back to the Part — a strong ref to
its own key. And the docstring's "an in-place move is a miss too" is wrong in
mechanism: part.move() mutates wrapped in place, so the stored IsEqual check
compares the shape with itself.

SS1 confirm the leak (N throwaway Parts, weakrefs, gc) and its MECHANISM
    (topo_parent identity; the same value without build123d children); the
    in-place-move claim (hash before/after, IsEqual after the move)
SS2 what one retained body COSTS (faces, edges, cached Python objects, bytes)
SS3 the candidate: a BOUNDED OrderedDict keyed on id(shape) holding the shape
    strongly — hit / copy-miss / moved-copy-miss / in-place-move / bound /
    unweakref-able, plus the alternatives
SS4 cost: _face_rows and _edge_topo warm through both caches on a big body
SS5 the callers (grep) — is a bound of 4 safe for each?

Run: PYTHONIOENCODING=utf-8 C:/Python314/python.exe probes/shape_cache_leak_probe.py [--big]
"""
import copy
import gc
import sys
import time
import weakref
from collections import OrderedDict

sys.path.insert(0, ".")
from build123d import Box, Cylinder, Edge, Face, Location, Part, Pos  # noqa: E402
from build123d import fillet as b3d_fillet                    # noqa: E402

import blocks                                   # noqa: E402


def churn(n: int, work) -> list:
    """n throwaway plates, `work` called on each, only weakrefs kept."""
    refs = []
    for _ in range(n):
        p = blocks.plate(40, 30, 20)
        work(p)
        refs.append(weakref.ref(p))
        del p
    gc.collect()
    return refs


def slots_of(part):
    """The part's slot dict, in EITHER cache shape — this probe measured the
    WeakKeyDictionary (`shape -> {slot: (topods, value)}`) and the fix replaced
    it with a bounded id-keyed OrderedDict (`id -> [shape, {slot: (topods,
    hash, value)}]`), so the probe still runs against both. `slot[0]` is the
    stored TopoDS shape either way."""
    ent = blocks._SHAPE_CACHES.get(id(part))
    if isinstance(ent, list):                        # the bounded cache
        return ent[1] if ent[0] is part else None
    return blocks._SHAPE_CACHES.get(part)            # the weak dict


def forget(part):
    blocks._SHAPE_CACHES.pop(id(part), None)
    try:
        blocks._SHAPE_CACHES.pop(part, None)
    except TypeError:
        pass


BOUND = getattr(blocks, "_MAX_SHAPE_CACHES", None)    # None before the fix
N = (BOUND + 4) if BOUND else 8

print("== SS1 does the memo let the Part go?")
print(f"  cache bound: {BOUND if BOUND else 'NONE (unbounded weak dict)'}")
blocks._SHAPE_CACHES.clear()
gc.collect()
print("  start: len(_SHAPE_CACHES) =", len(blocks._SHAPE_CACHES))


def both(p):
    blocks._face_rows(p)
    blocks._edge_faces(p)


refs = churn(N, both)
alive = sum(1 for r in refs if r() is not None)
print(f"  {N} throwaway Parts, _face_rows + _edge_faces on each, strong refs dropped, gc.collect()")
print(f"  -> still alive: {alive}/{N}   len(_SHAPE_CACHES) = {len(blocks._SHAPE_CACHES)}"
      + (f"   (want <= {BOUND})" if BOUND else "   (want: 0 of them)"))

blocks._SHAPE_CACHES.clear()
gc.collect()
print("  after _SHAPE_CACHES.clear() + gc: still alive:",
      sum(1 for r in refs if r() is not None), f"/{N}")

print("\n-- the MECHANISM: what is in the value?")
p = blocks.plate(40, 30, 20)
rows = blocks._face_rows(p)
f0 = rows[0][0]
print("  cached Face attrs of interest:",
      [a for a in ("topo_parent", "_topo_parent", "label", "parent") if hasattr(f0, a)])
tp = getattr(f0, "topo_parent", None)
print("  Face.topo_parent is the Part:", tp is p, "| type:", type(tp).__name__)
topo = blocks._edge_topo(p)
e0 = topo["edges"][0]
print("  cached Edge.topo_parent is the Part:", getattr(e0, "topo_parent", None) is p)
del rows, f0, topo, e0, tp

print("\n-- the same weak dict with a value that holds NO build123d children")
d = weakref.WeakKeyDictionary()
q = blocks.plate(40, 30, 20)
d[q] = {"centres": [r[1] for r in blocks._measure_face_rows(q)]}   # plain tuples
wq = weakref.ref(q)
del q
gc.collect()
print("  value = plain float tuples -> Part alive after gc:", wq() is not None,
      "| len(dict):", len(d))
d2 = weakref.WeakKeyDictionary()
r = blocks.plate(40, 30, 20)
d2[r] = {"faces": blocks._measure_face_rows(r)}                    # Face objects
wr = weakref.ref(r)
del r
gc.collect()
print("  value = Face objects       -> Part alive after gc:", wr() is not None,
      "| len(dict):", len(d2))

print("\n-- the docstring's claim: 'an in-place move is a miss too'")
blocks._SHAPE_CACHES.clear()
m = blocks.plate(40, 30, 20)
h_before = hash(m)
kw_before = hash(m.wrapped)
rows_before = blocks._face_rows(m)
stored = slots_of(m)["faces"]
w_id_before = id(m.wrapped)
loc_before = m.wrapped.Location()
top_before = round(max(c[2] for _f, c, _n in rows_before), 3)
m.move(Location((0, 0, 5)))                      # IN PLACE
print(f"  hash(part)    before {h_before}  after {hash(m)}  changed: {hash(m) != h_before}")
print(f"  hash(wrapped) before {kw_before}  after {hash(m.wrapped)}  "
      f"changed: {hash(m.wrapped) != kw_before}")
print("  id(part.wrapped) unchanged (mutated in place):", id(m.wrapped) == w_id_before)
print("  stored TopoDS IS the live one:", stored[0] is m.wrapped,
      "| stored[0].IsEqual(part.wrapped):", stored[0].IsEqual(m.wrapped))
print("  a snapshot of the OLD location still differs:",
      not loc_before.IsEqual(m.wrapped.Location()),
      "(loc snapshot is a copy, not a live ref)")
print("  the entry after the move:",
      "gone (the weak dict ORPHANED it: hash(part) moved)" if slots_of(m) is None
      else "still there, and the stored hash is what makes it a MISS")
print("  len(_SHAPE_CACHES) now:", len(blocks._SHAPE_CACHES))
rows_after = blocks._face_rows(m)
print(f"  top face z: cached before {top_before} -> _face_rows after the move "
      f"{round(max(c[2] for _f, c, _n in rows_after), 3)} "
      f"(the plate is centred: 10.0 + 5 = 15.0, so the answer is FRESH)")
del rows_before, rows_after, stored
wm = weakref.ref(m)
del m
gc.collect()
print("  len(_SHAPE_CACHES) after the rebuild:", len(blocks._SHAPE_CACHES),
      "(the orphan + the new one) | the moved Part alive after gc:", wm() is not None)

print("\n== SS2 what one retained body COSTS")


def cache_cost(part) -> dict:
    """the Python objects one part's two memo slots hold, and their own bytes
    (Python-side only: the OCCT TShape/TopoDS memory is NOT counted here)."""
    forget(part)
    rows = blocks._face_rows(part)
    topo = blocks._edge_topo(part)
    seen, objs, byts = set(), 0, 0

    def walk(o, depth=0):
        nonlocal objs, byts
        if id(o) in seen or depth > 8:
            return
        seen.add(id(o))
        objs += 1
        try:
            byts += sys.getsizeof(o)
        except TypeError:
            pass
        if isinstance(o, dict):
            for k, v in o.items():
                walk(k, depth + 1)
                walk(v, depth + 1)
        elif isinstance(o, (list, tuple, set, frozenset)):
            for v in o:
                walk(v, depth + 1)
        elif hasattr(o, "__dict__"):
            walk(o.__dict__, depth + 1)

    walk(rows)
    walk(topo)
    return {"faces": len(part.faces()), "edges": len(part.edges()),
            "rows": len(rows), "topo_edges": len(topo["edges"]),
            "topo_ends": len(topo["ends"]), "objs": objs, "kb": byts / 1024.0}


def show(name, part):
    c = cache_cost(part)
    print(f"  {name:26s} faces={c['faces']:4d} edges={c['edges']:4d} "
          f"| memo: rows={c['rows']:4d} topo edges={c['topo_edges']:4d} "
          f"vertices={c['topo_ends']:4d} | {c['objs']:6d} python objects, "
          f"{c['kb']:8.1f} KB of python headers")
    return c


small = blocks.plate(40, 30, 20)
show("plate 40x30x20 (6 faces)", small)


def big_part(nx=14, ny=14):
    """a plate with a grid of holes — 200+ faces without a 40 s fixture rebuild"""
    base = Part() + Box(200, 200, 10)
    cyls = [Pos(-90 + 13.8 * i, -90 + 13.8 * j, 0) * Cylinder(3, 20)
            for i in range(nx) for j in range(ny)]
    t0 = time.perf_counter()
    try:
        res = base - cyls
        how = "one cut, list tool"
    except Exception as exc:
        print("   (list subtraction refused:", type(exc).__name__, exc, "- looping)")
        res = base
        for c in cyls:
            res = res - c
        how = "loop"
    print(f"  built via {how} in {time.perf_counter() - t0:.1f} s")
    return res


big = big_part()
show("plate + 196 holes", big)


print("\n== SS3 the candidate: a BOUNDED cache keyed on id(shape), holding it STRONGLY")
_MAX = 4
_CAND = OrderedDict()          # id(shape) -> [shape, {slot: (topods, shape_key, value)}]
_STATS = {"hit": 0, "miss": 0, "evict": 0}


def cand(shape, slot: str, build, guard_hash=True):
    """the candidate _cached. `guard_hash=False` is the review's literal
    proposal (IsEqual only); True adds the stored hash(wrapped) guard."""
    key = id(shape)
    ent = _CAND.get(key)
    if ent is None or ent[0] is not shape:
        ent = [shape, {}]
        _CAND[key] = ent
    else:
        hit = ent[1].get(slot)
        if hit is not None and hit[0].IsEqual(shape.wrapped) \
                and (not guard_hash or hit[1] == hash(shape.wrapped)):
            _CAND.move_to_end(key)
            _STATS["hit"] += 1
            return hit[2]
    value = build()
    ent[1][slot] = (shape.wrapped, hash(shape.wrapped), value)
    _CAND.move_to_end(key)
    _STATS["miss"] += 1
    while len(_CAND) > _MAX:
        _CAND.popitem(last=False)
        _STATS["evict"] += 1
    return value


def c_rows(part, **kw):
    return cand(part, "faces", lambda: blocks._measure_face_rows(part), **kw)


def c_topo(part, **kw):
    return cand(part, "edges", lambda: blocks._build_edge_topo(part), **kw)


def topz(rows):
    return round(max(c[2] for _f, c, _n in rows), 3)


print("-- (1) the same object twice is a HIT, and the memo is really reused")
_CAND.clear()
_STATS.update(hit=0, miss=0, evict=0)
t0 = time.perf_counter()
r1 = c_rows(big)
cold = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
r2 = c_rows(big)
warm = (time.perf_counter() - t0) * 1000
print(f"  _face_rows on the 202-face body: cold {cold:.1f} ms, warm {warm:.3f} ms "
      f"({cold / max(warm, 1e-6):.0f}x) | same list object: {r1 is r2} | {_STATS}")
t0 = time.perf_counter()
c_topo(big)
cold_e = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
c_topo(big)
warm_e = (time.perf_counter() - t0) * 1000
print(f"  _edge_topo  same body:            cold {cold_e:.1f} ms, warm {warm_e:.3f} ms "
      f"({cold_e / max(warm_e, 1e-6):.0f}x)")

print("-- (2) a COPY and a MOVED COPY must MISS (the deepcopy trap)")
base = blocks.plate(40, 30, 20)
b_rows = c_rows(base)
n0 = _STATS["miss"]
dc = copy.deepcopy(base)
mv = base.moved(Location((0, 0, 100)))
pm = Pos(0, 0, 200) * base
print(f"  top z: base {topz(b_rows)} | deepcopy {topz(c_rows(dc))} "
      f"| moved() {topz(c_rows(mv))} | Pos*part {topz(c_rows(pm))}  "
      f"(want 10.0 / 10.0 / 110.0 / 210.0)")
print(f"  misses caused by the three copies: {_STATS['miss'] - n0} (want 3) "
      f"| id(base) in cache: {id(base) in _CAND} | ids all distinct: "
      f"{len({id(base), id(dc), id(mv), id(pm)}) == 4}")
print(f"  hash(wrapped): base==deepcopy {hash(base.wrapped) == hash(dc.wrapped)} "
      f"base==moved {hash(base.wrapped) == hash(mv.wrapped)}")

print("-- (3) an IN-PLACE part.move()")
for guard in (False, True):
    _CAND.clear()
    z = blocks.plate(40, 30, 20)
    before = topz(c_rows(z, guard_hash=guard))
    z.move(Location((0, 0, 5)))
    after = topz(c_rows(z, guard_hash=guard))
    print(f"  guard_hash={guard!s:5s}: cached top z {before} -> after the move {after} "
          f"(truth 15.0) -> {'STALE' if after != 15.0 else 'fresh'}")
z = blocks.plate(40, 30, 20)
w0, k0 = z.wrapped, hash(z.wrapped)
z.move(Location((0, 0, 5)))
print(f"  why: id(z) is unchanged, and IsEqual compares the shape with ITSELF "
      f"-> {w0.IsEqual(z.wrapped)}; only hash(wrapped) moved: {k0} -> {hash(z.wrapped)}")

print("-- (4) BOUNDED: MAX+4 throwaway parts")
_CAND.clear()
gc.collect()
crefs = []
for _ in range(_MAX + 4):
    pp = blocks.plate(40, 30, 20)
    c_rows(pp)
    c_topo(pp)
    crefs.append(weakref.ref(pp))
    del pp
gc.collect()
print(f"  8 parts through the candidate -> alive {sum(1 for r in crefs if r() is not None)}/8 "
      f"(want {_MAX}) | len(cache) {len(_CAND)} | evictions so far, cumulative over "
      f"SS3: {_STATS['evict']}")
_CAND.clear()
gc.collect()
print("  after cache.clear() + gc: alive", sum(1 for r in crefs if r() is not None), "/8")

print("-- (5) a shape that cannot be weak-referenced")
for name, obj in (("Part", big), ("Face", big.faces()[0]), ("Edge", big.edges()[0]),
                  ("TopoDS_Shape (part.wrapped)", big.wrapped)):
    try:
        weakref.ref(obj)
        ok = "weakref OK"
    except TypeError as exc:
        ok = f"TypeError: {exc}"
    print(f"  {name:28s} {ok}")


print("-- the ALTERNATIVES")
print("  (A) keep the WeakKeyDictionary, store RAW TopoDS and re-wrap on read")
da = weakref.WeakKeyDictionary()
a = blocks.plate(40, 30, 20)
da[a] = [f.wrapped for f in a.faces()]
wa = weakref.ref(a)
del a
gc.collect()
print("      raw TopoDS in the value -> Part alive after gc:", wa() is not None,
      "| len(dict):", len(da), "(so the leak is gone)")
raw_f = [f.wrapped for f in big.faces()]
raw_e = [e.wrapped for e in big.edges()]
t0 = time.perf_counter()
rf = [Face(t) for t in raw_f]
t_f = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
re_ = [Edge(t) for t in raw_e]
t_e = (time.perf_counter() - t0) * 1000
print(f"      re-wrap cost per READ: {len(rf)} faces {t_f:.1f} ms + {len(re_)} edges "
      f"{t_e:.1f} ms = {t_f + t_e:.1f} ms (a warm hit costs {warm + warm_e:.3f} ms today)")
print("      re-wrapped Edge.topo_parent:", getattr(re_[0], "topo_parent", "n/a"))
try:
    b3d_fillet(re_[:1], radius=0.5)
    print("      build123d fillet on a re-wrapped edge: BUILT (no parent needed)")
except Exception as exc:
    print(f"      build123d fillet on a re-wrapped edge: {type(exc).__name__}: {exc}")

print("  (B) keep the weak key, CLEAR topo_parent on the cached children")
blocks._SHAPE_CACHES.clear()
b = blocks.plate(40, 30, 20)
topo_b = blocks._edge_topo(b)
rows_b = blocks._face_rows(b)
for e in topo_b["edges"]:
    e.topo_parent = None
for f, _c, _n in rows_b:
    f.topo_parent = None
wb = weakref.ref(b)
one = topo_b["edges"][0]
del b
gc.collect()
print("      cleared on rows + topo['edges'] only -> Part alive after gc:", wb() is not None,
      "(the Faces inside edge_faces / face_edges are OTHER objects and still hold it)")
n_left = 0
for holder in (topo_b["edge_faces"], topo_b["face_edges"]):
    for lst in holder.values():
        for sh in lst:
            if getattr(sh, "topo_parent", None) is not None:
                sh.topo_parent = None
                n_left += 1
for lst in topo_b["ends"].values():
    for sh, _t in lst:
        if getattr(sh, "topo_parent", None) is not None:
            sh.topo_parent = None
            n_left += 1
del topo_b, rows_b
gc.collect()
print(f"      {n_left} MORE children had to be cleared (every nested one) -> "
      f"Part alive after gc: {wb() is not None}")
try:
    b3d_fillet([one], radius=1.0)
    print("      build123d fillet on a parentless CACHED edge: BUILT")
except Exception as exc:
    print(f"      build123d fillet on a parentless CACHED edge: {type(exc).__name__}: {exc}")
print("      (blocks.fillet_edges / chamfer_edges pass exactly these cached edges to build123d,")
print("       and operations_generic.py:321 does target = object_list[0].topo_parent)")
del one
gc.collect()

print("\n== SS4 cost: the memo must stay as fast as it is now (202-face body)")
blocks._SHAPE_CACHES.clear()
_CAND.clear()
t0 = time.perf_counter()
blocks._face_rows(big)
cur_cold_f = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
blocks._edge_topo(big)
cur_cold_e = (time.perf_counter() - t0) * 1000
c_rows(big)
c_topo(big)
N = 2000


def timeit(fn, n=N):
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n * 1e6      # us per call


print(f"  cold build (both caches call the same builder): faces {cur_cold_f:.1f} ms, "
      f"edges {cur_cold_e:.1f} ms")
print(f"  warm _face_rows : current (WeakKeyDict) {timeit(lambda: blocks._face_rows(big)):7.2f} us "
      f"| candidate (OrderedDict/id) {timeit(lambda: c_rows(big)):7.2f} us")
print(f"  warm _edge_topo : current {timeit(lambda: blocks._edge_topo(big)):7.2f} us "
      f"| candidate {timeit(lambda: c_topo(big)):7.2f} us")
print(f"  the key itself  : hash(part) {timeit(lambda: hash(big)):7.2f} us "
      f"| id(part) {timeit(lambda: id(big)):7.2f} us "
      f"| IsEqual {timeit(lambda: big.wrapped.IsEqual(big.wrapped)):7.2f} us")


print("\n== SS5 the callers — is a bound of 4 safe?")
import toolplan                                        # noqa: E402
from document import Document                           # noqa: E402

_real_cached = blocks._cached
SEEN = {"ids": [], "calls": 0}


def counting_cached(shape, slot, build):
    SEEN["calls"] += 1
    tag = (id(shape), slot)
    if tag not in SEEN["ids"]:
        SEEN["ids"].append(tag)
    return _real_cached(shape, slot, build)


blocks._cached = counting_cached
d2 = Document(name="r")
d2.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
d2.add("g1", "fillet", {"radius": 5, "edges": "vertical"}, ["b"])
d2.rebuild()
for label, req in (("feature_toggle b", {"tool": "fillet", "body_id": "g1", "edges": [],
                                         "feature_toggle": "b"}),
                   ("face_toggle top", None),
                   ("edge toggle", None)):
    if req is None:
        continue
    SEEN.update(ids=[], calls=0)
    p = toolplan.plan(d2, req)
    shapes = {i for i, _s in SEEN["ids"]}
    print(f"  ONE plan ({label}): ok={p['ok']} edges={len(p.get('edges', []))} | "
          f"_cached called {SEEN['calls']}x over {len(shapes)} distinct shapes, "
          f"{len(SEEN['ids'])} (shape, slot) pairs")
SEEN.update(ids=[], calls=0)
top = d2._parts["g1"].faces().sort_by()[-1]
c = top.center()
p = toolplan.plan(d2, {"tool": "fillet", "body_id": "g1", "edges": [],
                       "face_toggle": {"center": [c.X, c.Y, c.Z], "normal": [0, 0, 1]}})
print(f"  ONE plan (face_toggle): ok={p['ok']} edges={len(p.get('edges', []))} | "
      f"_cached called {SEEN['calls']}x over {len({i for i, _s in SEEN['ids']})} distinct shapes")
blocks._cached = _real_cached

print("  -- does any caller need the cached objects' IDENTITY across calls?")
blocks._SHAPE_CACHES.clear()
r1 = blocks._face_rows(big)
k1 = [blocks._shape_key(f) for f, _c, _n in r1]
t1 = blocks._edge_topo(big)
blocks._SHAPE_CACHES.clear()                            # simulate an eviction
r2 = blocks._face_rows(big)
t2 = blocks._edge_topo(big)
print(f"      after an eviction + rebuild: same Face objects: "
      f"{r1[0][0] is r2[0][0]} | same _shape_key list: "
      f"{k1 == [blocks._shape_key(f) for f, _c, _n in r2]} | same edge keys: "
      f"{[blocks._shape_key(e) for e in t1['edges']] == [blocks._shape_key(e) for e in t2['edges']]}")
print(f"      centres identical: "
      f"{[c for _f, c, _n in r1] == [c for _f, c, _n in r2]} | "
      f"face_edges keys identical: {set(t1['face_edges']) == set(t2['face_edges'])}")
del r1, r2, t1, t2


print("\n== SS6 what a real editing session accumulates (6 radius edits)")
blocks._SHAPE_CACHES.clear()
gc.collect()
d3 = Document(name="s")
d3._cache = {}                                   # not the process-wide rebuild cache
d3.add("b", "plate", {"width": 200, "depth": 200, "thickness": 10}, [])
d3.add("g", "fillet", {"radius": 1, "edges": "vertical"}, ["b"])
d3.rebuild()
seen_parts = []
for radius in range(1, 7):
    d3.edit("g", "radius", float(radius))
    d3.rebuild()
    part = d3._parts["g"]
    blocks._face_rows(part)
    blocks._edge_topo(part)
    seen_parts.append(weakref.ref(part))
    del part
gc.collect()
held_by_doc = sum(1 for r in seen_parts if r() is not None)
print(f"  with the Document still open: {held_by_doc}/6 superseded bodies alive "
      f"(document._cache is an LRU of {__import__('document').CACHE_MAX} and holds them too)")
d3._cache.clear()
d3._parts.clear()
del d3
gc.collect()
alive = sum(1 for r in seen_parts if r() is not None)
print(f"  Document dropped, its own caches cleared -> still alive {alive}/6, "
      f"held by nothing but _SHAPE_CACHES (len {len(blocks._SHAPE_CACHES)})")
tot = 0
for k in list(blocks._SHAPE_CACHES.keys()):
    ent = blocks._SHAPE_CACHES[k]
    slots = ent[1] if isinstance(ent, list) else ent      # either cache shape
    hit = slots.get("edges")
    tot += len(hit[-1]["edges"]) if hit else 0            # value is the LAST field
print(f"  cached edge objects held across those entries: {tot}")
del slots, ent, hit, k                           # the probe's own last references
                                                 # (a weak dict's KEYS are the Parts)
blocks._SHAPE_CACHES.clear()
gc.collect()
print("  after clear + gc: superseded bodies alive",
      sum(1 for r in seen_parts if r() is not None), "/6")


print("\n== SS7 does the BOUND break the shipped test? "
      "(test_a_moved_copy_does_not_inherit_its_parents_faces, replayed)")


def replay(bound: int) -> str:
    """the shipped test's own sequence, through the candidate: b, a moved copy,
    an in-place-moved deepcopy, then b again ('the memo does hold for the same,
    unmoved body': _edge_faces(b) IS the first dict)."""
    global _MAX
    _MAX, keep = bound, _MAX
    _CAND.clear()
    b = blocks.plate(40, 30, 20)
    by_edge = c_topo(b)["edge_faces"]
    mv = Pos(100, 50, 0) * b
    c_topo(mv)
    c_rows(mv)
    r = copy.deepcopy(b)
    c_rows(r)
    r.move(Location((0, 0, 5)))
    zr = topz(c_rows(r))
    same = c_topo(b)["edge_faces"] is by_edge
    _MAX = keep
    return (f"  _MAX={bound}: distinct shapes touched 3 | in-place-moved top z {zr} (want 15.0) "
            f"| 'the memo holds for the same body' (b is b): {same}")


print(replay(2))
print(replay(4))
print(replay(8))


# =====================================================================
# MEASURED 2026-09-08 (C:/Python314, this machine). Finding C CONFIRMED.
#
# SS1  8 throwaway Parts, _face_rows + _edge_faces on each, strong refs dropped,
#      gc.collect() -> STILL ALIVE 8/8, len(_SHAPE_CACHES) 8. _SHAPE_CACHES.clear()
#      + gc -> 0/8, so the memo is the only thing holding them.
#      MECHANISM: every cached Face and Edge has .topo_parent, and it IS the Part
#      (identity True) — a strong ref from the weak dict's VALUE to its own KEY.
#      The same weak dict with a value of plain float tuples: Part collected
#      (alive False, len 0); with Face objects: alive True, len 1.
# SS1  the docstring's "an in-place move is a miss too" is right in EFFECT, wrong
#      in MECHANISM: part.move() mutates the same TopoDS (id(part.wrapped)
#      unchanged), so the stored shape IS the live one and IsEqual returns TRUE.
#      What saves the answer is that hash(part) changes (2206076564091169798 ->
#      321037331428317198), so the lookup misses — the OLD entry is ORPHANED
#      (get(part) -> None) and a SECOND immortal entry is inserted: len 1 -> 2,
#      and the moved Part is alive after gc.
# SS2  cost of one retained body: 6-face plate = 524 python objects / 31.6 KB;
#      202-face, 600-edge plate (196 holes) = 21877 python objects / 1318.4 KB
#      of python headers alone (the OCCT TShapes are on top of that).
# SS6  6 radius edits of one fillet -> 6 entries; with the Document dropped and
#      its own caches cleared, 6/6 superseded bodies are still alive, held by
#      nothing but _SHAPE_CACHES (144 cached Edge objects). document._cache is an
#      LRU of 400 and lets go; _SHAPE_CACHES has no bound at all.
#
# SS3  the CANDIDATE (OrderedDict keyed on id(shape), shape held strongly,
#      _MAX 4): (1) HIT for the same object — _face_rows cold 96.4 ms -> warm
#      0.040 ms (2387x), _edge_topo cold 533.0 ms -> warm 0.029 ms (18255x), and
#      the hit is the same list object. (2) deepcopy / moved() / Pos*part all
#      MISS (3 misses, ids distinct) and answer at their own positions
#      (10.0 / 110.0 / 210.0). (3) an IN-PLACE move is a STALE HIT with the
#      review's literal guard (IsEqual only: top z 10.0, truth 15.0) because
#      IsEqual compares the shape with itself; adding the stored
#      hash(shape.wrapped) — which the move DOES change — makes it fresh (15.0).
#      (4) bounded: 8 throwaway parts -> 4 alive, len 4. (5) nothing tested
#      REFUSES a weakref (Part, Face, Edge, even a raw TopoDS_Shape), so the
#      TypeError branch is dead code; keyed on id() the question disappears.
# SS3  alternatives, both REJECTED by measurement:
#      (A) weak key + raw TopoDS values: the leak does go (Part collected), but
#          re-wrapping costs 24.1 ms per READ (202 Faces 7.8 + 600 Edges 16.3)
#          against a 0.070 ms warm hit today — 340x worse, and a re-wrapped Edge
#          has topo_parent None, so build123d refuses: "ValueError: Nothing to
#          fillet".
#      (B) clearing topo_parent on the cached children: partial clearing does not
#          even work (30 MORE nested Faces in a 6-face plate's edge_faces /
#          face_edges / ends still hold the Part), and a parentless CACHED edge
#          breaks the tools that consume it — build123d's fillet does
#          target = object_list[0].topo_parent (operations_generic.py:321) and
#          raises "ValueError: Nothing to fillet".
# SS4  the memo stays as fast: warm _face_rows 27.06 us (current) -> 11.56 us
#      (candidate); warm _edge_topo 30.05 -> 14.78 us. The key is why:
#      hash(part) 5.57 us vs id(part) 0.23 us, IsEqual 6.87 us.
# SS5  ONE fillet plan touches exactly 1 shape / 2 slots (241 _cached calls for a
#      feature_toggle, 82 for a face_toggle), so a bound of 4 is never hit inside
#      a request. No caller needs the cached objects' IDENTITY: after an eviction
#      and rebuild the Face objects differ but every _shape_key, every centre and
#      every face_edges key is identical.
# SS7  the bound must not be 2: replaying the shipped test
#      (test_a_moved_copy_does_not_inherit_its_parents_faces) through the
#      candidate, its last assertion "the memo does hold for the same, unmoved
#      body" is False at _MAX=2 and True at 4 and 8 (3 shapes in flight).
#      Recommended _MAX_SHAPE_CACHES = 8: 8 x 1.3 MB worst case, and an eviction
#      costs a cold rebuild (0.10 s + 0.57 s here, 5.8 s on esp32-remote).
