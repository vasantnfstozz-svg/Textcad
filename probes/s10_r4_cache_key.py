"""Round FOUR, attack on round three's `_fail_key` (document.py:673).

Round three keyed a REFUSAL by `f"{sig}!{f.id}<{','.join(f.inputs)}"` so a
second design's failing row could no longer read the FIRST design's feature
name. Four questions the brief asks of that fix, each answered by MEASURING
two documents that differ only in the names:

  1. does a refusal still cross documents?            (the fix's own claim)
  2. does a document now MISS a cached rebuild?       (silent cost)
  3. can the key COLLIDE?                             (two names, one key)
  4. can a document get another document's GEOMETRY?  (the worst case)

Run: C:\\Python314\\python.exe probes/s10_r4_cache_key.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import document as docmod                                          # noqa: E402
from document import Document                                      # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def line(to):
    return {"kind": "line", "to": list(to)}


def path_ents(segments, start=(0, 0)):
    return [{"kind": "path", "closed": False, "start": list(start),
             "segments": segments}]


def fresh():
    docmod._SHARED_CACHE.clear()


def hr(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


# --- 1. a refusal across two documents that differ only in the names ---------
hr("1. two documents, identical geometry, DIFFERENT feature names")
fresh()


def failing(fid, sid="s1"):
    d = Document(name="d-" + fid)
    d.add(sid, "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add(fid, "extrude", {"amount": None}, [sid])
    d.rebuild()
    return " ".join(d.get(fid).problems)


a = failing("boss_height")
b = failing("rib_depth")
print("design 1 (boss_height):", a)
print("design 2 (rib_depth)  :", b)
print("LEAK" if "boss_height" in b else "clean")

# the other name a refusal says out loud: the INPUT
hr("1b. the same, through the input's name")
fresh()


def failing_input(sid):
    d = Document(name="d-" + sid)
    d.add(sid, "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("f1", "fillet", {"radius": 1}, [sid])
    d.rebuild()
    return " ".join(d.get("f1").problems)


a = failing_input("flat_profile")
b = failing_input("lid_outline")
print("design 1:", a)
print("design 2:", b)
print("LEAK" if "flat_profile" in b else "clean")


# --- 2. does a document MISS a cached rebuild it should have had? ------------
hr("2. cache occupancy: how many entries two identical designs cost")
fresh()
failing("same_name")
n1 = len(docmod._SHARED_CACHE)
failing("same_name")
n2 = len(docmod._SHARED_CACHE)
failing("other_name")
n3 = len(docmod._SHARED_CACHE)
print(f"one design: {n1} entries; the SAME design again: {n2} "
      f"({'no growth' if n2 == n1 else 'GREW'})")
print(f"a second design with a different name: {n3} "
      f"(+{n3 - n1} — the refusal is kept per name, by design)")

hr("2b. does the SUCCESS cache still cross documents?")
fresh()


def plate_doc(fid):
    d = Document(name="p-" + fid)
    d.add(fid, "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.rebuild()
    return d


plate_doc("base")
before = len(docmod._SHARED_CACHE)
d2 = plate_doc("stock")          # SAME geometry, different name
after = len(docmod._SHARED_CACHE)
print(f"entries {before} -> {after} "
      f"({'shared' if after == before else 'NOT shared'}); "
      f"volume {d2.get('stock').volume}")


# --- 3. can the key COLLIDE? -------------------------------------------------
hr("3. collision: '<' and ',' are the key's own separators")
print("key form:", repr("{sig}!{f.id}<{','.join(f.inputs)}"))
fresh()


def collide(fid, sid):
    d = Document(name="c-" + fid)
    d.add(sid, "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add(fid, "extrude", {"amount": None}, [sid])
    d.rebuild()
    key = docmod._fail_key(d._sigs[fid], d.get(fid))
    return key, " ".join(d.get(fid).problems)


# design A: feature "a<b" whose input is "c"      -> "...!a<b<c"
# design B: feature "a"   whose input is "b<c"    -> "...!a<b<c"
ka, pa = collide("a<b", "c")
kb, pb = collide("a", "b<c")
print("A key:", ka)
print("B key:", kb)
print("SAME KEY" if ka == kb else "different keys")
print("A says:", pa)
print("B says:", pb)
if ka == kb:
    print("LEAK" if "a<b" in pb else "same key, but the sentence survived")


# --- 4. another document's GEOMETRY through a REF param ----------------------
hr("4. a sweep names its path in `params`, never in `inputs`")
print("REF_PARAMS:", docmod.REF_PARAMS)
fresh()


def swept(path_segments, name):
    d = Document(name=name)
    d.add("prof", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("rail", "sketch",
          {"entities": path_ents(path_segments), "plane": "XZ", "offset": 0.0}, [])
    d.add("sw", "sweep", {"path": "rail", "full": True}, ["prof"])
    ok = d.rebuild()
    f = d.get("sw")
    return d, ok, f.volume, f.problems


d1, ok1, v1, p1 = swept([line((0, 20))], "doc-A")             # a 20 mm rail
print(f"doc A  rail = 20 mm      -> ok={ok1} volume={v1} {p1}")
d2, ok2, v2, p2 = swept([line((0, 40))], "doc-B")             # a 40 mm rail
print(f"doc B  rail = 40 mm      -> ok={ok2} volume={v2} {p2}")
print(f"signatures equal: {d1._sigs['sw'] == d2._sigs['sw']}")
exp1, exp2 = 3.141592653589793 * 25 * 20, 3.141592653589793 * 25 * 40
print(f"expected A ~{exp1:.2f}, B ~{exp2:.2f}")
if v1 is not None and v2 is not None and abs(v1 - v2) < 1e-6:
    print("*** doc B GOT doc A's SOLID ***")

hr("4b. the same seam inside ONE document: edit the path, keep the sweep")
fresh()
d = Document(name="edit-path")
d.add("prof", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
d.add("rail", "sketch",
      {"entities": path_ents([line((0, 20))]), "plane": "XZ", "offset": 0.0}, [])
d.add("sw", "sweep", {"path": "rail", "full": True}, ["prof"])
d.rebuild()
print(f"rail 20 mm -> sweep volume {d.get('sw').volume} (expect ~{exp1:.2f})")
sig_before = d._sigs["sw"]
d.edit("rail", "entities", path_ents([line((0, 40))]))
d.rebuild()
sig_after = d._sigs["sw"]
print(f"rail 40 mm -> sweep volume {d.get('sw').volume} (expect ~{exp2:.2f})")
print(f"sweep signature changed: {sig_before != sig_after}")
