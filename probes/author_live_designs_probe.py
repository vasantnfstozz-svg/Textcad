"""probes/author_live_designs_probe.py — can the AI add anything at all to the
user's OWN saved designs?

`/api/chat` "add" runs author.author_steps on the live document, and every
`add` step runs `lint_tree(doc.features, final=False)` over the WHOLE tree —
the user's hand-built features included. This puts ONE correct first step
(a sketch_on_face on the current body) to each of the 50 saved designs and
records whether it is refused, and by whose feature.

Read-only: nothing is written into designs/.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import author                      # noqa: E402
from document import Document      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DESIGNS = ROOT / "designs"

# `--old`: ask the question the way the loop asked it before the section 13
# fix — the WHOLE tree in scope, the user's own features included.
OLD = "--old" in sys.argv


def main():
    blocked, fine, skipped = [], [], []
    for p in sorted(DESIGNS.glob("*.tcad.json")):
        try:
            doc = Document.from_data(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:                        # noqa: BLE001
            skipped.append((p.stem, str(e)[:60]))
            continue
        protected = frozenset(f.id for f in doc.features)
        body = next((f.id for f in reversed(doc.features)
                     if f.op not in ("sketch", "sketch_on_face")), None)
        if body is None:
            skipped.append((p.stem, "no body feature"))
            continue
        step = {"add": {"id": "ai_probe_sketch", "op": "sketch_on_face",
                        "params": {"face": "top", "offset": 0,
                                   "entities": [{"kind": "circle", "r": 2}]},
                        "inputs": [body]}}
        before = doc.to_data()
        # `authored` empty = a job that has written nothing yet, which is
        # exactly where /api/chat "add" starts. Pass None for the behaviour
        # as it was before the section 13 fix (the whole tree in scope).
        ok, text, _ = author._apply_step(doc, step, protected, True,
                                         None if OLD else set())
        if not ok and doc.to_data() != before:
            a = {f["id"]: f for f in before["features"]}
            b = {f["id"]: f for f in doc.to_data()["features"]}
            diff = [(k, a.get(k), b.get(k)) for k in set(a) | set(b)
                    if a.get(k) != b.get(k)]
            print(f"  !! {p.stem}: a REFUSED step changed the tree: "
                  f"{str(diff)[:300]}")
        if ok:
            fine.append(p.stem)
        else:
            blocked.append((p.stem, text[:120]))
    print("BLOCKED — the AI's first correct step is refused:")
    for stem, why in blocked:
        print(f"  {stem}\n      {why}")
    print(f"\n  blocked {len(blocked)} / accepted {len(fine)} / "
          f"skipped {len(skipped)}")
    lint_only = [s for s, why in blocked if "history lint" in why]
    print(f"  refused by the HISTORY LINT (a rule about the user's own "
          f"features): {len(lint_only)}")


if __name__ == "__main__":
    main()
