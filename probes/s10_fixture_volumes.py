"""probes/s10_fixture_volumes.py — the frozen fixtures rebuilt, feature by
feature, so a change to document.py / blocks.py can be shown to move NOTHING.

Run it before the change and after it and diff the two outputs:

    C:\\Python314\\python.exe probes\\s10_fixture_volumes.py > before.txt

`designs/` is never read here (code tests read tests/fixtures/ only).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from document import Document                            # noqa: E402

FIXTURES = ("tests/fixtures/esp32-remote.tcad.json",
            "tests/fixtures/pump-impeller.tcad.json")

for path in FIXTURES:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    doc = Document.from_data(data)
    ok = doc.rebuild()
    print(f"\n=== {path}  rebuild={ok}  features={len(doc.features)}")
    for f in doc.features:
        print(f"  {f.id:28s} {f.op:16s} {f.status:7s} "
              f"vol={f.volume!r} pieces={f.pieces!r} problems={f.problems}")
    shape = doc.result_shape()
    total = None if shape is None else round(shape.volume, 4)
    print(f"  RESULT volume = {total}")
