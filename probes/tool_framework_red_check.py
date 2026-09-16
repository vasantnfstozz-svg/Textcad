"""Proof that every source-level test in tests/test_tool_framework.py is RED
against the code as it stood before this fix pass (HEAD), without touching the
working tree: the pre-fix files are read straight out of git."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
GIT = r"C:\Program Files\Git\cmd\git.exe"


def at_head(path):
    return subprocess.run([GIT, "show", f"HEAD:{path}"], cwd=HERE,
                          capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


import test_tool_framework as T                                  # noqa: E402

OLD = {n: at_head(f"static/js/{n}.js")
       for n in ("doctabs", "dialogs", "tool", "api")}
T._src = lambda name: OLD[name[:-3]]

CHECKS = [
    ("F1 tab bar behind the modal guard",
     T.test_the_document_tab_bar_refuses_while_a_tool_panel_is_open),
    ("F2 spec dialog stops on bad holes",
     T.test_the_spec_dialog_stops_when_the_holes_box_will_not_parse),
    ("F4 Add Feature reports a bad list",
     T.test_the_add_feature_dialog_says_so_when_a_list_will_not_parse),
    ("F3 every pick outranks a tree row",
     T.test_every_viewport_pick_outranks_a_tree_row),
    ("F5 planRequest reads the HTTP status",
     T.test_plan_request_turns_a_non_200_into_a_sentence),
]

for name, fn in CHECKS:
    try:
        fn()
        print(f"  NOT RED (!)  {name}")
    except AssertionError as e:
        print(f"  RED at HEAD  {name}: {str(e).splitlines()[0][:80]}")

# F6 — the same, for toolplan.py: load the PRE-FIX module from git and plan
import importlib.util                                           # noqa: E402
import tempfile                                                 # noqa: E402

from document import Document                                   # noqa: E402

tmp = os.path.join(tempfile.gettempdir(), "toolplan_head_probe.py")
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write(at_head("toolplan.py"))
spec = importlib.util.spec_from_file_location("toolplan_head", tmp)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

d = Document(name="t")
d.add("s", "sketch", {"plane": "XY", "entities": [
    {"kind": "polygon", "points": [[0, 0], [40, 0], [40, 10],
                                   [10, 10], [10, 30], [0, 30]]}]}, [])
d.rebuild()
p = old.plan(d, {"tool": "extrude", "sketch_id": "s"})
print(f"  F6 at HEAD   L-profile origin {p['origin']} "
      f"(true area centroid 15, 10), ring radius {p['limits']['outer_radius']}")
