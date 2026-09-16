"""probes/mcp_overwrite_probe.py — section 13 F1, measured on the code AS IT
WAS (git show HEAD:mcp_server.py, loaded from the scratchpad).

The MCP `build_design` door wrote into designs/ with a plain Document.save().
This puts a design of the "user's" in a throwaway library and asks the OLD
build_design to build an unrelated part under the same name.

Run:  python probes/mcp_overwrite_probe.py <path to the old mcp_server.py>
"""
from __future__ import annotations
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TREE = {"name": "untitled",
        "features": [{"id": "base_plate", "op": "plate",
                      "params": {"width": 20, "depth": 10, "thickness": 3}}],
        "spec": {"n_solids": 1}}

MINE = {"name": "untitled", "features": [
    {"id": "hand_built", "op": "disc",
     "params": {"radius": 9, "thickness": 2}, "inputs": []}], "spec": {}}


def load(path: str):
    spec = importlib.util.spec_from_file_location("mcp_old", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(path: str):
    mod = load(path)
    tmp = Path(tempfile.mkdtemp(prefix="tcad-mcp-"))
    try:
        mod.OUT = tmp
        mod._notify_studio = lambda stem: print(f"  doorbell -> /api/open/{stem}"
                                                f"?external=1  (would push a "
                                                f"version into its .history/)")
        f = tmp / "untitled.tcad.json"
        f.write_text(json.dumps(MINE), encoding="utf-8")
        (tmp / "untitled.history").mkdir()
        print(f"  the user's design before: {json.loads(f.read_text())['features']}")
        rep = mod.build_design(dict(TREE))
        print(f"  build_design(tree) -> verified={rep.get('verified')} "
              f"recipe={rep.get('recipe_path')}")
        after = json.loads(f.read_text(encoding="utf-8"))
        print(f"  the user's design after : {after['features']}")
        print("  DESTROYED" if after != MINE else "  intact")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1])
