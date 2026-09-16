"""Section 11 round three — what a PARTIAL size does to the spec check.

The Spec dialog has three size boxes and sends them as one list as soon as
ANY of them is filled: `if (size.some(v => v !== null)) spec.size = size;`.
Fill only Y and the requirement goes out as [null, 40, null].  Round two
made every box refuse a value Number() cannot read, so this is the one shape
a user can still produce by hand — measured here against the real /api/spec.

Usage:  C:\\Python314\\python.exe probes/spec_partial_size_probe.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

import studio  # noqa: E402

studio.DESIGNS = Path(tempfile.mkdtemp())      # never the user's library


def main() -> int:
    c = TestClient(studio.app)
    c.post("/api/new", json={"name": "sizecheck"})
    c.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    print("the body is 60 x 40 x 20\n")
    for spec in ({"size": [None, 40, None]},
                 {"size": [None, 999, None]},
                 {"size": [60, 40, 20]},
                 {"size": [60, 999, 20]},
                 {"size": [None, None, None]}):
        d = c.post("/api/spec", json={"spec": spec}).json()
        print(f"  sent {str(spec['size']):<22} -> ok={d.get('ok')!s:<6} "
              f"stored={d.get('spec')}  problems={d.get('spec_problems')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
