"""PROBE - LAUNCH-PLAN s10 P1: "a suppressed final boolean promotes its TOOL to
the result (viewport shows the cutter)".

Questions asked of the kernel and of document.py, never of memory:

  1. With the last `cut` struck out, WHAT does `Document.result()` hand back,
     and what volume does the status bar therefore print?
  2. Does the same thing happen for `fuse`, for a chain of two cuts, and for
     the ops that are NOT booleans?
  3. The BACKLOG's proposed rule - "prefer the last feature on the result
     body's input[0] spine over any later stray solid" - does it actually
     name the body the user still sees, on every shape below?
  4. What does it do to the designs that DO end on a stray solid on purpose
     (a base plate plus an unfused boss)?

Run under the memory cap:
  python probes/memcap.py --gb 4 --timeout 600 -- python probes/suppressed_result_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import Document       # noqa: E402


def cut_chain():
    """plate 40x30x10  ->  a r6 x 4 prism  ->  cut."""
    doc = Document(name="p-sup")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("tool_sketch", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 6, "x": 0, "y": 0}]})
    doc.add("tool", "extrude", {"amount": -4}, inputs=["tool_sketch"])
    doc.add("pocket", "cut", {}, inputs=["body", "tool"])
    doc._cache = {}
    return doc


def fuse_chain():
    doc = Document(name="p-sup-f")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sketch", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 6, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sketch"])
    doc.add("joined", "fuse", {}, inputs=["body", "boss"])
    doc._cache = {}
    return doc


def two_cuts():
    doc = Document(name="p-sup2")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("s1", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 6, "x": -10, "y": 0}]})
    doc.add("t1", "extrude", {"amount": -4}, inputs=["s1"])
    doc.add("c1", "cut", {}, inputs=["body", "t1"])
    doc.add("s2", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 3, "x": 10, "y": 0}]})
    doc.add("t2", "extrude", {"amount": -4}, inputs=["s2"])
    doc.add("c2", "cut", {}, inputs=["c1", "t2"])
    doc._cache = {}
    return doc


def unfused_boss():
    """A design that legitimately ENDS on a second body: base plate, then a
    boss that was never joined. result() has always been the boss here and
    that is CORRECT - nothing was struck out."""
    doc = Document(name="p-two-bodies")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sketch", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 6, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sketch"])
    doc._cache = {}
    return doc


def report(doc, struck=None, label=""):
    if struck:
        for sid in struck:
            doc.get(sid).suppressed = True
        doc._mark_stale()
    built = doc.rebuild()
    rf = doc._result_feature()
    part = doc.result()
    print("")
    print("--- " + label)
    print("    struck            : %s   rebuild ok=%s" % (struck or "(nothing)", built))
    print("    _result_feature   : %s  (op %s)"
          % (rf.id if rf else None, rf.op if rf else "-"))
    print("    result().volume   : %s"
          % (None if part is None else round(part.volume, 3)))
    print("    status-bar volume : %s" % (rf.volume if rf else None))
    print("    leaf_solid_ids    : %s" % doc.leaf_solid_ids())
    print("    result_bodies vol : %s"
          % [round(p.volume, 3) for p in doc.result_bodies()])
    return doc


print("=" * 78)
print("1. THE BUG, MEASURED")
print("=" * 78)
report(cut_chain(), None, "cut chain, nothing struck (the truth)")
report(cut_chain(), ["pocket"], "cut chain, the FINAL CUT struck out")

print("")
print("  The plate is 40 x 30 x 10 = 12000 mm3.")
print("  The tool prism is pi*6^2*4 = 452.389 mm3.")
print("  Strike the cut and the design is the PLATE again - 12000 mm3.")

print("")
print("=" * 78)
print("2. THE SAME DOOR, OTHER OPS")
print("=" * 78)
report(fuse_chain(), None, "fuse chain, nothing struck")
report(fuse_chain(), ["joined"], "fuse chain, the FINAL FUSE struck out")
report(two_cuts(), ["c2"], "two cuts, the LAST cut struck out")
report(two_cuts(), ["c1", "c2"], "two cuts, BOTH struck out")

print("")
print("=" * 78)
print("3. WHAT MUST NOT CHANGE")
print("=" * 78)
report(unfused_boss(), None, "base plate + unfused boss (result IS the boss)")
report(two_cuts(), None, "two cuts, nothing struck")
report(two_cuts(), ["t2"], "two cuts, the TOOL struck")

print("")
print("=" * 78)
print("4. THE PROPOSED RULE, RUN BY HAND ON THE SAME DOCUMENTS")
print("=" * 78)
print("""  Rule under test: a SUPPRESSED feature is a pass-through to its own
  inputs[0] during rebuild (document.py ~1092), so the tail of the tree does
  not stop existing when it is struck - it becomes whatever it passes
  through. So _result_feature should follow the tail's own SPINE
  (_live_source) instead of scanning sideways for any later solid.""")


def spine_rule(doc):
    """The candidate: same backward scan, but a suppressed feature resolves
    through its inputs[0] chain instead of being skipped over."""
    import sketch as sk
    by_id = {f.id: f for f in doc.features}
    seen_bar = doc.rollback is None
    for f in reversed(doc.features):
        if not seen_bar:
            seen_bar = f.id == doc.rollback
            if not seen_bar:
                continue
        g = by_id.get(doc._live_source(f.id, by_id))
        if g is None:
            continue
        part = doc._parts.get(g.id)
        if (not g.suppressed and part is not None
                and g.op not in sk.SKETCH_PRODUCERS
                and not sk.is_sketch(part)):
            return g
    return None


for label, mk, struck in [
        ("cut chain, cut struck", cut_chain, ["pocket"]),
        ("cut chain, clean", cut_chain, None),
        ("fuse chain, fuse struck", fuse_chain, ["joined"]),
        ("two cuts, last struck", two_cuts, ["c2"]),
        ("two cuts, both struck", two_cuts, ["c1", "c2"]),
        ("two cuts, clean", two_cuts, None),
        ("two cuts, TOOL struck", two_cuts, ["t2"]),
        ("plate + unfused boss", unfused_boss, None)]:
    doc = mk()
    if struck:
        for sid in struck:
            doc.get(sid).suppressed = True
        doc._mark_stale()
    doc.rebuild()
    old = doc._result_feature()
    new = spine_rule(doc)
    ov = doc._parts.get(old.id).volume if old else None
    nv = doc._parts.get(new.id).volume if new else None
    flag = "  <-- CHANGES" if (old and new and old.id != new.id) else ""
    print("    %-30s old %-10s %9s   new %-10s %9s%s"
          % (label, old.id if old else None,
             "-" if ov is None else format(ov, ".3f"),
             new.id if new else None,
             "-" if nv is None else format(nv, ".3f"), flag))
