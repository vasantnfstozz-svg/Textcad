"""`Document.edit` carries a `move`'s delta into stored picks. WHICH picks?

`document._shift_face_picks` walks one feature's params and shifts anything
under the key `face_center` - bare, or one level down inside a dict (a Pattern
axis, a Mirror plane). Three other stored picks are NOT shaped like that:

    shell    params["faces"]  = [ {center, normal}, ... ]     a LIST of dicts
    fillet   params["edges"]  = [ {mid, dir, faces:[...]} ]   a LIST of dicts
    chamfer  the same

So the question this probe answers by measurement, not by reading: when a move
under one of those features changes, does the feature still act on the thing
the user picked, or on whatever is now nearest the old place?

Each section builds the same design twice - once with the move at 0 and once
with it moved - and asks what the feature did, so the ANSWER is geometry, not
a claim about the code.
"""
import sys

sys.path.insert(0, ".")
from document import Document                     # noqa: E402

DZ = 8.0


def head(n, title):
    print("")
    print("=" * 78)
    print(f"{n}. {title}")
    print("=" * 78)


def vol(doc):
    doc.rebuild()
    p = doc.result()
    return None if p is None else round(p.volume, 3)


def status(doc):
    return {f.id: (f.status, (f.problems or [None])[0]) for f in doc.features
            if f.status != "ok"}


def stepped(dz, extra):
    """plate 40 x 30 x 10 with a r8 x 5 boss, MOVED by dz, then `extra(doc)`
    hangs the picked feature off the moved body."""
    doc = Document(name="p-carry")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": 0, "y": 0, "z": dz}, inputs=["part"])
    extra(doc)
    doc.rebuild()
    return doc


# ---------------------------------------------------------------------------
head(1, "the control: a FACE pick (params['face_center']) - carried today")


def face_pick(doc):
    doc.add("riser", "extrude_face", {
        "face_center": [0.0, 0.0, 15.0], "face_normal": [0.0, 0.0, 1.0],
        "face_area": 201.06, "amount": 5}, inputs=["placed"])
    doc.add("final", "fuse", {}, inputs=["placed", "riser"])


base = stepped(0.0, face_pick)
print("  at dz = 0 :", vol(base), status(base))
d = stepped(0.0, face_pick)
d.rebuild()
d.edit("placed", "z", DZ)
print(f"  edited to dz = {DZ}:", vol(d), status(d))
print("  stored pick after the edit:", d.get("riser").params["face_center"])

# ---------------------------------------------------------------------------
head(2, "a SHELL opening (params['faces'] = [{center, normal}])")


def shell_pick_maker(area):
    def shell_pick(doc):
        ref = {"center": [0.0, 0.0, 15.0], "normal": [0.0, 0.0, 1.0]}
        if area is not None:
            ref["area"] = area
        doc.add("hollow", "shell", {"thickness": 2.0, "faces": [ref]},
                inputs=["placed"])
    return shell_pick


for label, area in (("no stored size (every design saved before today)", None),
                    ("with the size the click now stores", 201.06)):
    print(f"  -- {label}")
    mk = shell_pick_maker(area)
    base = stepped(0.0, mk)
    d = stepped(0.0, mk)
    d.rebuild()
    d.edit("placed", "z", DZ)
    print("     dz = 0 :", vol(base), status(base))
    print(f"     dz = {DZ}:", vol(d), status(d))

# ---------------------------------------------------------------------------
head(3, "a picked EDGE (params['edges'] = [{mid, dir, faces}])")
import blocks                                     # noqa: E402


def edge_pick_refs():
    probe = stepped(0.0, lambda _d: None)
    part = probe._parts["placed"]
    # the boss's top rim: the circle at z = 15
    e = next(x for x in part.edges()
             if str(x.geom_type).endswith("CIRCLE")
             and abs(float((x @ 0.5).Z) - 15.0) < 1e-6)
    return [blocks.edge_ref(part, e)]


REFS = edge_pick_refs()
print("  the pick:", {k: REFS[0][k] for k in ("mid", "type")},
      "faces:", [f.get("area") for f in REFS[0]["faces"]])


import copy                                       # noqa: E402

BARE = copy.deepcopy(REFS)
for f in BARE[0]["faces"]:
    f.pop("area", None)


def edge_pick_maker(refs):
    def edge_pick(doc):
        doc.add("round", "fillet", {"radius": 1.0, "edges": copy.deepcopy(refs)},
                inputs=["placed"])
    return edge_pick


for label, refs in (("no stored size (every design saved before today)", BARE),
                    ("with the size the click now stores", REFS)):
    print(f"  -- {label}")
    mk = edge_pick_maker(refs)
    base = stepped(0.0, mk)
    d = stepped(0.0, mk)
    d.rebuild()
    d.edit("placed", "z", DZ)
    print("     dz = 0 :", vol(base), status(base))
    print(f"     dz = {DZ}:", vol(d), status(d))
