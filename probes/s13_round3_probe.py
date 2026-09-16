"""Section 13, ROUND THREE — put round two's BASELINE to the measurement.

Round two deleted `lint_tree(only=)` and replaced it with a baseline: what the
tree already broke when the job started is recorded as {key: rank}, and only
what is NEW or WORSE is reported. Replacing a guard wholesale is the sharpest
version of "a fix pass's own new guard has been wrong more often than not", and
this module is the front door for "AI mistakes must never reach the user".

The ONE question: can the baseline swallow a fault the AI itself introduces?

Run:  C:\\Python314\\python.exe probes/s13_round3_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import author                                                    # noqa: E402
from document import Document                                    # noqa: E402


class Scripted:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r)
                        for r in replies]

    def generate(self, messages):
        if not self.replies:
            return json.dumps({"done": True})
        return self.replies.pop(0)


def _base(name="hand-built"):
    """A body, so `body_yet` is true for everything after it."""
    d = Document(name=name)
    d.add("base_sketch", "sketch",
          {"plane": "XY", "offset": 0,
           "entities": [{"kind": "rectangle", "w": 60, "h": 40}]})
    d.add("base", "extrude", {"amount": 10}, inputs=["base_sketch"])
    return d


def _users_floating(d, fid="recess_sketch", offset=10.0):
    d.add(fid, "sketch", {"plane": "XY", "offset": offset,
                          "entities": [{"kind": "circle", "r": 5}]})
    d.add(fid + "_tool", "extrude", {"amount": -3}, inputs=[fid])
    d.add(fid + "_cut", "cut", {}, inputs=["base", fid + "_tool"])
    return d


def run(label, doc, *replies, max_fails=1):
    m = Scripted(*replies)
    before = doc.to_data()
    ok, transcript = author.author_steps(doc, label, m, max_fails=max_fails)
    changed = doc.to_data() != before
    return ok, changed, transcript


def head(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


# ---------------------------------------------------------------- 1. keys ---
head("1. WHAT THE KEY IS MADE OF")
d = _users_floating(_base())
d.add("part_1", "sketch", {"plane": "XY", "offset": 0,
                           "entities": [{"kind": "circle", "r": 2}]})
d.add("art_sketch", "sketch",
      {"plane": "XY", "offset": 0,
       "entities": [{"kind": "circle", "r": 1, "x": -25 + i * 4, "y": 0}
                    for i in range(11)]})
for k, r, t in author._lint_items(d.features):
    print(f"  key={k!r:52}  rank={r}   {t[:44]}...")
print("\n  baseline =", json.dumps(
    {repr(k): v for k, v in author.lint_baseline(d.features).items()}, indent=2))


# --------------------------------- 2. the AI's OWN fault, same rule as theirs
head("2. THE USER ALREADY BREAKS RULE R — CAN THE AI BREAK R TOO?")

cases = []

# 2a OFFSET: their sketch floats at 10.0; the AI adds its own at 12.0
doc = _users_floating(_base())
doc.rebuild()
ok, changed, tr = run(
    "add a pocket", doc,
    {"add": {"id": "ai_sketch", "op": "sketch",
             "params": {"plane": "XY", "offset": 12.0,
                        "entities": [{"kind": "circle", "r": 4}]}}},
    {"done": True})
cases.append(("2a offset, AI's own sketch at a NEW value", not ok,
              tr[0][:150]))

# 2b OFFSET: the AI's own sketch at the SAME value the user's carries
doc = _users_floating(_base())
doc.rebuild()
ok, changed, tr = run(
    "add a pocket", doc,
    {"add": {"id": "ai_sketch", "op": "sketch",
             "params": {"plane": "XY", "offset": 10.0,
                        "entities": [{"kind": "circle", "r": 4}]}}},
    {"done": True})
cases.append(("2b offset, AI's own sketch at the USER'S value 10.0", not ok,
              tr[0][:150]))

# 2c CRAM: the user's sketch already crams 11; the AI adds its own 11
doc = _base()
doc.add("art_sketch", "sketch",
        {"plane": "XY", "offset": 0,
         "entities": [{"kind": "circle", "r": 1, "x": -25 + i * 4, "y": 0}
                      for i in range(11)]})
doc.add("art", "extrude", {"amount": 2}, inputs=["art_sketch"])
doc.rebuild()
ok, changed, tr = run(
    "add more art", doc,
    {"add": {"id": "ai_art_sketch", "op": "sketch_on_face",
             "params": {"face": "top", "offset": 0,
                        "entities": [{"kind": "circle", "r": 1,
                                      "x": -25 + i * 4, "y": 12}
                                     for i in range(11)]},
             "inputs": ["base"]}},
    {"done": True})
# NOTE: this one is LET THROUGH, and it is NOT the baseline's doing — the cram
# rule reads `f.op == "sketch"` and this is a `sketch_on_face`. That gap is a
# product decision already recorded as deferred (section 13 round two); see the
# same case with op "sketch" in probes/s13_round3_probe2.py, where it IS refused.
cases.append(("2c cram, AI's own 11-entity sketch_on_face (DEFERRED gap, "
              "not the baseline)", not ok, tr[0][:150]))

# 2d GENERIC ID: the user already has `part_1`; the AI adds `part_2`
doc = _base()
doc.add("part_1", "sketch", {"plane": "XY", "offset": 0,
                             "entities": [{"kind": "circle", "r": 3}]})
doc.add("part_1_ex", "extrude", {"amount": 2}, inputs=["part_1"])
doc.rebuild()
ok, changed, tr = run(
    "add a boss", doc,
    {"add": {"id": "part_2", "op": "sketch_on_face",
             "params": {"face": "top", "offset": 0,
                        "entities": [{"kind": "circle", "r": 3}]},
             "inputs": ["base"]}},
    {"done": True})
cases.append(("2d generic id, AI's own `part_2`", not ok, tr[0][:150]))

# 2e the SAME generic id class through an id the user ALREADY has: impossible
#    (Document.add refuses a duplicate) — measured, not assumed
doc = _base()
doc.add("part_1", "sketch", {"plane": "XY", "offset": 0,
                             "entities": [{"kind": "circle", "r": 3}]})
try:
    doc.add("part_1", "sketch", {"plane": "XY", "offset": 0, "entities": []})
    dup = "ACCEPTED A DUPLICATE ID"
except Exception as e:                                          # noqa: BLE001
    dup = f"refused: {type(e).__name__}: {e}"
cases.append(("2e a duplicate feature id", "refused" in dup, dup[:150]))

for name, refused, detail in cases:
    print(f"  {'REFUSED  ' if refused else '*** LET THROUGH ***'} {name}")
    print(f"      {detail}")


# ------------------------------------------------- 3. "worse" and the rank ---
head("3. IS `rank` FINE-GRAINED ENOUGH FOR 'WORSE'?")

worse = []

# 3a their sketch at 10 -> the AI moves it to 40 (value is in the key)
doc = _users_floating(_base())
doc.rebuild()
ok, changed, tr = run("lower it", doc,
                      {"edit": {"feature_id": "recess_sketch",
                                "param": "offset", "value": 40.0}},
                      {"done": True})
worse.append(("3a offset 10 -> 40 on the USER's sketch", not ok, tr[0][:120]))

# 3b their crammed sketch 11 -> 12
doc = _base()
ents = [{"kind": "circle", "r": 1, "x": -25 + i * 4, "y": 0} for i in range(11)]
doc.add("art_sketch", "sketch", {"plane": "XY", "offset": 0, "entities": ents})
doc.add("art", "extrude", {"amount": 2}, inputs=["art_sketch"])
doc.rebuild()
ok, changed, tr = run("one more", doc,
                      {"edit": {"feature_id": "art_sketch", "param": "entities",
                                "value": ents + [{"kind": "circle", "r": 1,
                                                  "x": 22, "y": 0}]}},
                      {"done": True})
worse.append(("3b cram 11 -> 12 on the USER's sketch", not ok, tr[0][:120]))

# 3c a HEALTHY sketch of 10 -> 11 (crosses the limit inside the job)
doc = _base()
ents10 = [{"kind": "circle", "r": 1, "x": -22 + i * 4, "y": 0}
          for i in range(10)]
doc.add("art_sketch", "sketch", {"plane": "XY", "offset": 0,
                                 "entities": ents10})
doc.add("art", "extrude", {"amount": 2}, inputs=["art_sketch"])
doc.rebuild()
ok, changed, tr = run("one more", doc,
                      {"edit": {"feature_id": "art_sketch", "param": "entities",
                                "value": ents10 + [{"kind": "circle", "r": 1,
                                                    "x": 22, "y": 0}]}},
                      {"done": True})
worse.append(("3c cram 10 -> 11 on the USER's sketch", not ok, tr[0][:120]))

# 3d their crammed sketch 12 -> 11: FORGIVEN by design (it got better)
doc = _base()
ents12 = [{"kind": "circle", "r": 1, "x": -25 + i * 4, "y": 0}
          for i in range(12)]
doc.add("art_sketch", "sketch", {"plane": "XY", "offset": 0,
                                 "entities": ents12})
doc.add("art", "extrude", {"amount": 2}, inputs=["art_sketch"])
doc.rebuild()
ok, changed, tr = run("one fewer", doc,
                      {"edit": {"feature_id": "art_sketch", "param": "entities",
                                "value": ents12[:11]}},
                      {"done": True})
worse.append(("3d cram 12 -> 11 (should be ALLOWED)", ok, tr[0][:120]))

for name, good, detail in worse:
    print(f"  {'as intended ' if good else '*** WRONG ***'} {name}")
    print(f"      {detail}")


# ------------------------------------------- 4. when is the baseline taken ---
head("4. WHEN IS THE BASELINE TAKEN, AND CAN IT GO STALE?")

src = Path(__file__).resolve().parent.parent / "author.py"
lines = src.read_text(encoding="utf-8").splitlines()
for i, ln in enumerate(lines, 1):
    if "lint_baseline(doc.features)" in ln and "def " not in ln:
        print(f"  author.py:{i}: {ln.strip()}")
        for j in range(i, min(i + 40, len(lines))):
            if "_apply_step" in lines[j] or "for _ in range(max_steps)" in lines[j]:
                print(f"  ...first step at author.py:{j + 1}: {lines[j].strip()}")
                break
        break

# a SECOND job on a tree the first job left: does job 2 forgive job 1's work?
doc = _base()
doc.rebuild()
ok1, _, tr1 = run("make a pocket", doc,
                  {"add": {"id": "pocket_sketch", "op": "sketch_on_face",
                           "params": {"face": "top", "offset": -2,
                                      "entities": [{"kind": "circle", "r": 6}]},
                           "inputs": ["base"]}},
                  {"add": {"id": "pocket_tool", "op": "extrude",
                           "params": {"amount": -4}, "inputs": ["pocket_sketch"]}},
                  {"add": {"id": "pocket", "op": "cut", "params": {},
                           "inputs": ["base", "pocket_tool"]}},
                  {"done": True})
print(f"\n  job 1 finished={ok1}; tree now = {[f.id for f in doc.features]}")
print(f"  job 1 left these lint problems: {author.lint_tree(doc.features)}")
b2 = author.lint_baseline(doc.features)
print(f"  job 2's baseline would be: {list(b2)}")

# can a job that GIVES UP leave a lint problem behind for the next baseline?
doc = Document(name="untitled")
ok3, _, tr3 = run("a logo plate", doc,
                  {"add": {"id": "logo_sketch", "op": "sketch",
                           "params": {"plane": "XY", "offset": 0,
                                      "entities": [
                                          {"kind": "circle", "r": 2,
                                           "x": -12 + i * 3, "y": 0}
                                          for i in range(8)]}}},
                  {"add": {"id": "logo", "op": "extrude",
                           "params": {"amount": 3}, "inputs": ["logo_sketch"]}},
                  {"add": {"id": "nope", "op": "torus", "params": {}}},
                  {"add": {"id": "nope", "op": "torus", "params": {}}},
                  {"add": {"id": "nope", "op": "torus", "params": {}}},
                  max_fails=3)
print(f"\n  a CREATE job that gives up: finished={ok3}, "
      f"tree = {[f.id for f in doc.features]}")
print(f"  lint problems it LEFT behind: {author.lint_tree(doc.features)}")
print(f"  the next job's baseline would forgive: "
      f"{list(author.lint_baseline(doc.features))}")


# ------------------------------------------------ 5. does `remove` bypass? ---
head("5. DOES ANY BRANCH BYPASS `_lint_since`?")
text = src.read_text(encoding="utf-8")
body = text[text.index("def _apply_step"):text.index("def author_steps")]
marks = ['if "add" in step', 'if "edit" in step', 'if "remove" in step',
         'if step.get("done")', "    return False, ('REFUSED: reply with"]
cuts = [body.index(m) for m in marks]
for i, branch in enumerate(marks[:-1]):
    seg = body[cuts[i]:cuts[i + 1]]
    print(f"  {branch:26} -> _lint_since called: {'_lint_since' in seg}")

# ...and can `remove` CREATE a problem that `done` then misses?
doc = _base()
ents = [{"kind": "circle", "r": 2, "x": -12 + i * 3, "y": 0} for i in range(8)]
doc2 = Document(name="two-feature")
doc2.add("art_sketch", "sketch", {"plane": "XY", "offset": 0, "entities": ents})
doc2.add("art", "extrude", {"amount": 3}, inputs=["art_sketch"])
doc2.rebuild()
print(f"\n  a 2-feature user design's baseline: "
      f"{list(author.lint_baseline(doc2.features))}  "
      f"(blob rank {author.lint_baseline(doc2.features).get(('blob',))})")
ok, _, tr = run("add a hole then take it back", doc2,
                {"add": {"id": "hole_sketch", "op": "sketch_on_face",
                         "params": {"face": "top", "offset": 0,
                                    "entities": [{"kind": "circle", "r": 2}]},
                         "inputs": ["art"]}},
                {"remove": "hole_sketch"},
                {"done": True})
print(f"  add-then-remove-then-done: finished={ok}; last = {tr[-1][:110]}")
