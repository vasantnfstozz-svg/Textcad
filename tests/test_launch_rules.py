"""LAUNCH-PLAN.md acceptance criteria that a grep can hold (R1, R2, R3).

Each was true the day its phase shipped. A red here means a tool has started
to re-derive a backend fact, to refresh the viewport by hand, or to re-type
what the framework inherits — exactly the drift the plan exists to stop.
"""
import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "static" / "js"
FRAMEWORK = "tool.js"
TOOL_FILES = ["extrude.js"]                  # every design tool born on tool.js


def _src(name):
    return (JS / name).read_text(encoding="utf-8")


def test_no_tool_refreshes_the_viewport_by_hand():
    """R3 — the viewport follows the document (viewport.follow on
    'doc-updated'); a tool calling loadMesh() has a second opinion about when
    the scene is stale."""
    for name in [FRAMEWORK, *TOOL_FILES]:
        assert "loadMesh" not in _src(name), f"{name} calls loadMesh()"


def test_the_browser_holds_no_copy_of_the_plane_frames():
    """R1 — build123d's plane frames live in sketch.sketch_plane() and reach
    the browser only through /api/tool/plan {tool: 'sketch'}."""
    literal = re.compile(r"[xyz]_dir:\s*\[")
    gone = ("PLANE_FRAMES", "PLANE_MAP", "CANON_AXES", "canonAxis")
    for p in JS.glob("*.js"):
        src = p.read_text(encoding="utf-8")
        for token in gone:
            assert token not in src, f"{p.name} still has {token}"
        assert not re.search(r"\bPLANE_N\b", src), f"{p.name} still has PLANE_N"
        assert not literal.search(src), f"{p.name} writes a frame vector by hand"


def test_every_tool_is_born_on_the_framework():
    """R2 — a tool declares itself through tool({...}) and does not re-type
    the modal lock, the selection resolver, the preview loop or the isolation."""
    for name in TOOL_FILES:
        src = _src(name)
        assert "tool({" in src, f"{name} does not use the framework"
        for hand_typed in ("S.modalTool", "beginProfilePick", "/api/feature/add",
                           "/api/feature/params", "/api/rollback", "S.pickedFace",
                           "S.selected"):
            assert hand_typed not in src, f"{name} re-types {hand_typed}"
