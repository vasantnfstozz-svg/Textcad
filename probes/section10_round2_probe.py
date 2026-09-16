"""ROUND TWO of REVIEW-QUEUE section 10: read 8aa30a2's OWN new code adversarially.

Round one fixed 5 of 5 and rejected none. On this project a fix pass's own new
guard has been wrong more often than not, so every one of its five changes is
attacked here by measurement, not by reading.

  1  resolve_edge's SIZELESS SECOND PASS. The size gate of 1a8d28f exists
     because a sizeless rule picks the wrong same-shaped face; round one added
     a fall-back that DROPS the size. Does the second pass hand back an edge
     the first pass correctly refused? And does the first pass still answer on
     its own for every edge of every corpus body (i.e. is the fall-back rare)?

  2  provenance._area_matches. When nothing matches by area, does it fail open
     to the old answer — for a pick with no area at all (every design saved
     before 2026-09-16), for a tessellated-vs-exact area, and for a face the
     design legitimately resized?

  3  the NEGATIVE face index. Round one dropped `0 <=` from the index guard
     and put an early return above it. Is every negative index really the
     imported-mesh pseudo-face, and does the early return cost any caller an
     answer it used to get?

  4  toolplan._face_of (READ ONLY, another reviewer owns that file). Round one
     flagged that the size gate could move resolve_face's answer to a same-
     sized face elsewhere and make _face_of refuse a legitimate LIVE face
     click. Real, or measured out?
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blocks                                      # noqa: E402
import provenance                                  # noqa: E402
import toolplan                                    # noqa: E402
from document import Document                      # noqa: E402
from tests.gauntlet import BODIES                  # noqa: E402

OUT = []


def say(s=""):
    OUT.append(s)
    print(s)


def key(e):
    return blocks._shape_key(e)


# ---------------------------------------------------------------------------
# §1  the sizeless second pass
# ---------------------------------------------------------------------------
say("== §1 resolve_edge: does the sized pass ever need the fall-back on an "
    "UNCHANGED body?")

need_fallback = 0
checked = 0
wrong = []
for name, make in BODIES.items():
    solid = make()
    part = solid
    by_edge = blocks._edge_faces(part)
    edges = list(part.edges())
    for e in edges[:40]:
        ref = blocks.edge_ref(part, e, by_edge)
        if len(ref["faces"]) != 2:
            continue
        checked += 1
        sized = blocks._shared_edges(part, ref["faces"], True)
        if not sized:
            need_fallback += 1
            bare = blocks._shared_edges(part, ref["faces"], False)
            say(f"   {name}: sized pass EMPTY, sizeless gives {len(bare)}")
        got = blocks.resolve_edge(part, ref)
        if key(got) != key(e):
            wrong.append((name, ref["mid"]))
say(f"   {checked} edges over {len(BODIES)} corpus bodies: "
    f"{need_fallback} needed the fall-back, {len(wrong)} resolved to the "
    f"WRONG edge on an unchanged body")
if wrong:
    say(f"   wrong: {wrong[:5]}")
say()


# ---------------------------------------------------------------------------
# §1b  THE ATTACK: an edge that is genuinely gone. Does the fall-back turn a
#      correct refusal into a silently-wrong edge?
# ---------------------------------------------------------------------------
say("== §1b an edge whose host faces are GONE: refusal, or a wrong edge?")


def two_pads(pad_w=20.0, drop_p=False):
    """round one's own fixture: a plate with two pads whose tops are both
    200 mm2 (20x10 and 25x8). `drop_p` builds it WITHOUT pad P at all, so the
    edge picked on pad P's rim is genuinely gone."""
    doc = Document(name="t-pads")
    doc.add("plate", "plate", {"width": 90, "depth": 40, "thickness": 10})
    last = "plate"
    if not drop_p:
        doc.add("skP", "sketch", {"plane": "XY", "offset": 5, "entities": [
            {"kind": "rectangle", "w": pad_w, "h": 10, "x": -25, "y": 0}]})
        doc.add("padP", "extrude", {"amount": 6}, inputs=["skP"])
        doc.add("joinP", "fuse", {}, inputs=["plate", "padP"])
        last = "joinP"
    doc.add("skQ", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": 25, "h": 8, "x": 25, "y": 0}]})
    doc.add("padQ", "extrude", {"amount": 6}, inputs=["skQ"])
    doc.add("joinQ", "fuse", {}, inputs=[last, "padQ"])
    assert doc.rebuild(), doc.tree()
    return doc._parts["joinQ"]


def pad_p_top_rim(part):
    top = next(f for f in part.faces()
               if abs(f.normal_at(f.center()).Z - 1) < 1e-6
               and abs(f.center().Z - 11) < 1e-6 and f.center().X < 0)
    return max(blocks._face_edges(part, top), key=lambda e: (e @ 0.5).X)


ref = blocks.edge_ref(two_pads(20.0), pad_p_top_rim(two_pads(20.0)))
gone = two_pads(drop_p=True)
say(f"   stored pick: mid={ref['mid']}  areas="
    f"{sorted(f['area'] for f in ref['faces'])}")
say(f"   sized pass  -> {len(blocks._shared_edges(gone, ref['faces'], True))} shared")
say(f"   sizeless    -> {len(blocks._shared_edges(gone, ref['faces'], False))} shared")
try:
    got = blocks.resolve_edge(gone, ref)
    m = got @ 0.5
    say(f"   resolve_edge ANSWERED: ({m.X:.3f}, {m.Y:.3f}, {m.Z:.3f}) "
        f"type={blocks._gtype(got)}   <-- the pad is not on this body at all")
except ValueError as e:
    say(f"   resolve_edge REFUSED: {e}")
say()


# ---------------------------------------------------------------------------
# §1c  the case the size gate was BUILT for, at the edge level: a same-facing
#      neighbour that moves NEARER than the picked face's own. Does the
#      fall-back re-open it?
# ---------------------------------------------------------------------------
say("== §1c HOW OFTEN does the fall-back convert a refusal into an answer, and "
    "is that\n   answer ever one the sized pass was RIGHT to refuse? Every "
    "corpus edge resolved\n   against every OTHER corpus body — the strongest "
    "'the edge is gone' case there is.")

names = list(BODIES)
bodies = {n: BODIES[n]() for n in names}
refs_of = {}
for n in names:
    p = bodies[n]
    be = blocks._edge_faces(p)
    refs_of[n] = [blocks.edge_ref(p, e, be) for e in list(p.edges())[:12]]

both_refuse = sized_only_refuse = sizeless_only_refuse = neither = 0
converted = []
for src in names:
    for dst in names:
        if src == dst:
            continue
        part = bodies[dst]
        for r in refs_of[src]:
            if len(r["faces"]) != 2:
                continue
            s = bool(blocks._shared_edges(part, r["faces"], True))
            b = bool(blocks._shared_edges(part, r["faces"], False))
            if s and b:
                neither += 1
            elif s and not b:
                sizeless_only_refuse += 1
            elif b and not s:
                sized_only_refuse += 1
                converted.append((src, dst, r["mid"]))
            else:
                both_refuse += 1
say(f"   both passes answer          : {neither}")
say(f"   both passes REFUSE          : {both_refuse}")
say(f"   only the sized pass refuses : {sized_only_refuse}  "
    f"<- these are the ones round one's fall-back newly ANSWERS")
say(f"   only the sizeless refuses   : {sizeless_only_refuse}  "
    f"(the sized pass answers; unchanged by round one)")
for c in converted[:6]:
    say(f"      converted: {c[0]} -> {c[1]} at {c[2]}")
say()


# ---------------------------------------------------------------------------
# §1d  the same question with REALISTIC edits: one parameter swept, the stored
#      pick re-resolved at every value. Is the fall-back's answer ever wrong
#      where the sized pass refused?
# ---------------------------------------------------------------------------
say("== §1d a parameter sweep: pad P widened 16 -> 34 mm with the rim pick "
    "stored at 20 mm.\n   TRUE = the +X rim of pad P's own top on that body.")

pick20 = blocks.edge_ref(two_pads(20.0), pad_p_top_rim(two_pads(20.0)))
bad = 0
for w in [16, 18, 19, 20, 21, 22, 24, 26, 28, 30, 32, 34]:
    part = two_pads(float(w))
    truth = pad_p_top_rim(part)
    s = blocks._shared_edges(part, pick20["faces"], True)
    b = blocks._shared_edges(part, pick20["faces"], False)
    try:
        got = blocks.resolve_edge(part, pick20)
        ok = key(got) == key(truth)
        where = f"x={(got @ 0.5).X:+7.3f}"
    except ValueError:
        ok, where = None, "REFUSED"
    tag = "OK " if ok else ("REFUSED" if ok is None else "WRONG")
    if ok is False:
        bad += 1
    say(f"   w={w:2d}  sized={len(s)} sizeless={len(b)}  -> {where:>10s} "
        f"(true x={(truth @ 0.5).X:+7.3f})  {tag}"
        f"{'   <- fall-back answered' if not s and b else ''}")
say(f"   wrong answers: {bad}")
say()


# ---------------------------------------------------------------------------
# §2  provenance._area_matches: fail-open behaviour
# ---------------------------------------------------------------------------
say("== §2 provenance._area_matches")


def pocket_with_a_flush_pad():
    doc = Document(name="t-prov-tie")
    doc.add("plate", "plate", {"width": 60, "depth": 60, "thickness": 20})
    doc.add("pk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 20, "x": 0, "y": 0}]})
    doc.add("pk_tool", "extrude", {"amount": -6}, inputs=["pk"])
    doc.add("pocket", "cut", {}, inputs=["plate", "pk_tool"])
    doc.add("pad", "sketch", {"plane": "XY", "offset": 4, "entities": [
        {"kind": "circle", "r": 6, "x": 0, "y": 0}]})
    doc.add("pad_tool", "extrude", {"amount": 6}, inputs=["pad"])
    doc.add("boss", "fuse", {}, inputs=["pocket", "pad_tool"])
    assert doc.rebuild(), doc.tree()
    return doc


doc = pocket_with_a_flush_pad()
faces = provenance.picked_faces(doc, "boss", doc._parts["boss"])
pad_i = next(i for i, f in enumerate(faces)
             if abs(f.center().Z - 10) < 1e-6 and f.area < 200)
pad = faces[pad_i]
c = pad.center()
vc = [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)]
say(f"   pad top: index {pad_i}, area {pad.area:.2f}, centre {vc}")

cases = [
    ("index right, area right", pad_i, vc, round(pad.area, 2)),
    ("index right, NO area (a pick saved before 2026-09-16)", pad_i, vc, None),
    ("index STALE, area right", len(faces) + 5, vc, round(pad.area, 2)),
    ("index STALE, NO area (pre-2026-09-16 pick)", len(faces) + 5, vc, None),
    ("index STALE, area NOTHING matches", len(faces) + 5, vc, 123456.0),
    ("index right, area nothing matches", pad_i, vc, 123456.0),
    ("index right, area 1.2% off (tessellation)", pad_i, vc,
     round(pad.area * 1.012, 2)),
]
for label, fi, ctr, ar in cases:
    r = provenance.attribute_face(doc, body_id="boss", face_index=fi,
                                  center=ctr, area=ar)
    say(f"   {label:52s} -> origin={r.get('origin')!r:12s} "
        f"feature={r.get('feature')!r:12s} {r.get('reason', '')[:40]}")
say()


# ---------------------------------------------------------------------------
# §3  the negative index
# ---------------------------------------------------------------------------
say("== §3 a negative face index")
for fi in (-1, -2, -7):
    r = provenance.attribute_face(doc, body_id="boss", face_index=fi,
                                  center=vc, area=round(pad.area, 2))
    say(f"   face_index={fi:3d} WITH a good centre+area -> "
        f"feature={r.get('feature')!r} reason={r.get('reason', '')[:70]!r}")
say()


# ---------------------------------------------------------------------------
# §4  toolplan._face_of, READ ONLY
# ---------------------------------------------------------------------------
say("== §4 toolplan._face_of (READ ONLY): the tool's PREVIEW body is what the "
    "user clicks,\n   `part` is the INPUT body. A face the preview TRIMMED "
    "sends a smaller area than\n   the input body's own — so the size gate can "
    "move the answer elsewhere and the\n   'that face is not on <body>' "
    "refusal fires on a face that is sitting right there.")


def browser_pick(face):
    """exactly what studio._tagged_mesh puts in the payload for one face"""
    c = face.center()
    n = face.normal_at(c)
    return {"center": [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)],
            "normal": [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)],
            "area": round(face.area, 2)}


def pair_from(doc, body_id, rad, edge_pick):
    doc.add("rnd", "fillet", {"radius": rad, "edges": [edge_pick]},
            inputs=[body_id])
    ok = doc.rebuild()
    return ok, doc._parts.get(body_id), doc._parts.get("rnd")


def bracket(pad_w=20.0):
    """a plate with two pads and a rib — a normal little part with enough
    faces that a 2 per cent window has neighbours in it"""
    doc = Document(name="t-bracket")
    doc.add("plate", "plate", {"width": 90, "depth": 40, "thickness": 10})
    doc.add("skP", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": pad_w, "h": 10, "x": -25, "y": 0}]})
    doc.add("padP", "extrude", {"amount": 6}, inputs=["skP"])
    doc.add("joinP", "fuse", {}, inputs=["plate", "padP"])
    doc.add("skQ", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": 25, "h": 8, "x": 25, "y": 0}]})
    doc.add("padQ", "extrude", {"amount": 6}, inputs=["skQ"])
    doc.add("joinQ", "fuse", {}, inputs=["joinP", "padQ"])
    return doc, "joinQ"


cases = []
for rad in (0.5, 1.0, 2.0, 3.0):
    d, bid = bracket()
    part0 = None
    d.rebuild()
    part0 = d._parts[bid]
    top = next(f for f in part0.faces()
               if abs(f.center().Z - 11) < 1e-6 and f.center().X < 0)
    rim = blocks.edge_ref(part0, blocks._face_edges(part0, top)[0])
    ok, inp, prev = pair_from(d, bid, rad, rim)
    if not ok or prev is None:
        say(f"   r={rad}: fillet failed, skipped")
        continue
    cases.append((f"bracket r={rad}", inp, prev))

refused = same = moved = 0
examples = []
for label, inp, prev in cases:
    for f in prev.faces():
        if str(f.geom_type).split(".")[-1] != "PLANE":
            continue
        pick = browser_pick(f)
        try:
            with_area = toolplan._face_of(inp, pick, "joinQ")
            wa = f"area {with_area.area:.2f}"
        except ValueError:
            wa = "REFUSED"
        try:
            no_area = toolplan._face_of(inp, {**pick, "area": None}, "joinQ")
            na = f"area {no_area.area:.2f}"
        except ValueError:
            na = "REFUSED"
        if wa == na:
            same += 1
        elif wa == "REFUSED":
            refused += 1
            examples.append((label, pick["center"], pick["area"], na))
        else:
            moved += 1
            examples.append((label, pick["center"], pick["area"], f"{wa} vs {na}"))
say(f"   {same + refused + moved} planar preview faces clicked: {same} same, "
    f"{refused} REFUSED only because of the stored size, {moved} moved")
for e in examples[:8]:
    say(f"      {e[0]}: centre {e[1]} area {e[2]} -> sizeless {e[3]}")
say()

say("== §4c ...so does the mechanism exist AT ALL? Give the second pad the area "
    "the\n   fillet leaves pad P's top at, and click pad P's top on the PREVIEW.")

d, bid = bracket()
d.rebuild()
p0 = d._parts[bid]
topP = next(f for f in p0.faces()
            if abs(f.center().Z - 11) < 1e-6 and f.center().X < 0)
rimP = blocks._face_edges(p0, topP)[0]
ok, inp, prev = pair_from(d, bid, 2.0, blocks.edge_ref(p0, rimP))
trimmed = next(f for f in prev.faces()
               if abs(f.center().Z - 11) < 1e-6 and f.center().X < -10)
say(f"   pad P top: {topP.area:.2f} mm2 on the input body, "
    f"{trimmed.area:.2f} on the preview (r=2 fillet on one rim)")


def bracket_matched(q_area):
    """the same bracket, but pad Q's top is the area the preview reports for
    pad P's — the coincidence round one's own P1 fixture also needed"""
    w = 25.0
    h = q_area / w
    doc = Document(name="t-bracket2")
    doc.add("plate", "plate", {"width": 90, "depth": 40, "thickness": 10})
    doc.add("skP", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": 20, "h": 10, "x": -25, "y": 0}]})
    doc.add("padP", "extrude", {"amount": 6}, inputs=["skP"])
    doc.add("joinP", "fuse", {}, inputs=["plate", "padP"])
    doc.add("skQ", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": w, "h": h, "x": 25, "y": 0}]})
    doc.add("padQ", "extrude", {"amount": 6}, inputs=["skQ"])
    doc.add("joinQ", "fuse", {}, inputs=["joinP", "padQ"])
    assert doc.rebuild(), doc.tree()
    return doc


d3 = bracket_matched(trimmed.area)
inp3 = d3._parts["joinQ"]
say("   input body's +Z pad tops: " + ", ".join(
    f"x={f.center().X:+.1f} area={f.area:.2f}" for f in inp3.faces()
    if abs(f.center().Z - 11) < 1e-6))
pick = browser_pick(trimmed)          # what the PREVIEW mesh sends for pad P
say(f"   the click the browser sends: centre {pick['center']} "
    f"area {pick['area']}")
for label, pk in (("today (the size travels)", pick),
                  ("pre-1a8d28f (no size)", {**pick, "area": None})):
    try:
        got = toolplan._face_of(inp3, pk, "joinQ")
        gc = got.center()
        say(f"   {label:28s} -> face at x={gc.X:+6.2f}, area {got.area:.2f}")
    except ValueError as e:
        say(f"   {label:28s} -> REFUSED: {e}")
say()

say("== §4d the same coincidence with the two pads at DIFFERENT heights — now "
    "the clicked\n   point is not on the other pad's plane either, so the "
    "refusal round one predicted\n   is what comes out.")


def bracket_matched_high(q_area, q_z=8.0):
    w = 25.0
    doc = Document(name="t-bracket3")
    doc.add("plate", "plate", {"width": 90, "depth": 40, "thickness": 10})
    doc.add("skP", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": 20, "h": 10, "x": -25, "y": 0}]})
    doc.add("padP", "extrude", {"amount": 6}, inputs=["skP"])
    doc.add("joinP", "fuse", {}, inputs=["plate", "padP"])
    doc.add("skQ", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": w, "h": q_area / w, "x": 25, "y": 0}]})
    doc.add("padQ", "extrude", {"amount": q_z}, inputs=["skQ"])
    doc.add("joinQ", "fuse", {}, inputs=["joinP", "padQ"])
    assert doc.rebuild(), doc.tree()
    return doc


d4 = bracket_matched_high(trimmed.area, 8.0)
inp4 = d4._parts["joinQ"]
say("   input body's pad tops: " + ", ".join(
    f"x={f.center().X:+.1f} z={f.center().Z:.1f} area={f.area:.2f}"
    for f in inp4.faces()
    if abs(f.normal_at(f.center()).Z - 1) < 1e-6 and f.center().Z > 6))
for label, pk in (("today (the size travels)", pick),
                  ("pre-1a8d28f (no size)", {**pick, "area": None})):
    try:
        got = toolplan._face_of(inp4, pk, "joinQ")
        gc = got.center()
        say(f"   {label:28s} -> face at x={gc.X:+6.2f} z={gc.Z:.2f}, "
            f"area {got.area:.2f}")
    except ValueError as e:
        say(f"   {label:28s} -> REFUSED: {e}")
say()
