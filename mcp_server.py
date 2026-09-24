"""
mcp_server.py — TextCAD as an MCP server: the verified CAD doorbell.

Any MCP client (Claude Desktop, Claude Code, other agents) can now design real,
machine-verified CAD through these tools. The division of labor is deliberate:

  THE CALLING AI DESIGNS, TEXTCAD VERIFIES.

`build_design` takes a feature tree (JSON) authored by the calling model and
runs it through the full verified pipeline: registry validation (unknown ops
rejected by name), per-feature geometry health, spec verification, STEP export.
The caller cannot hallucinate API — it can only compose the operations that
`list_operations` reports, and every claim about the result is measured, not
trusted.

Register (Claude Code):   .mcp.json in this folder (already written)
Register (Claude Desktop): %APPDATA%/Claude/claude_desktop_config.json ->
  "textcad": {"command": "python", "args": ["<this file's absolute path>"]}
"""

from __future__ import annotations
import contextlib
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP


@contextlib.contextmanager
def _quiet():
    """build123d prints notices to stdout; over MCP, stdout IS the protocol.
    Route any library chatter to stderr (which lands in the client's log)."""
    with contextlib.redirect_stdout(sys.stderr):
        yield

import author
import inspector
from document import Document

ROOT = Path(__file__).parent
OUT = ROOT / "designs"
OUT.mkdir(exist_ok=True)

mcp = FastMCP("textcad")


def _safe_name(name: str) -> str:
    import re
    return re.sub(r"[^\w\-]+", "-", name).strip("-") or "design"


# Design names THIS server has written, each against the digest of the recipe
# it wrote. A name in here may be written again — the whole point of the
# doorbell is "regenerate -> POST /api/open/<name> -> look at it in 3D", and
# ten iterations must land in ONE file and ONE tab — but only while the file
# is still the one we wrote. The doorbell opens it in Studio, that tab is
# bound to it, and the section 3 owner guard lets the owning tab save over it:
# the moment the user changes the AI's part and saves, it is their work
# (section 13 round two, 2026-09-17).
_MINE: dict[str, str] = {}


def _digest(name: str) -> str:
    import hashlib
    try:
        return hashlib.sha256(
            (OUT / f"{name}.tcad.json").read_bytes()).hexdigest()
    except OSError:
        return ""                      # no recipe yet: nothing to have changed


def _still_mine(name: str) -> bool:
    return name in _MINE and _digest(name) in (_MINE[name], "")


def _wrote(name: str) -> None:
    """Record what we just put at `name`, so a later call can tell whether the
    file is still ours or the user has made it theirs."""
    _MINE[name] = _digest(name)


def _renamed(asked: str, name: str, mine_before: bool) -> str:
    """Why the file is not the name that was asked for — the SAME sentence at
    both doors. `design_part` had one reason hard-coded ("not mine to
    overwrite"), so the one case round two's own fix created — the AI wrote
    that file and the USER has changed it since — was reported to them as
    somebody else's design (section 13 round three, 2026-09-17)."""
    why = (f"'{asked}' has been changed since I wrote it, so it is the "
           f"user's now" if mine_before else
           f"'{asked}' is already a design in this library")
    return f"{why} and was left untouched; this one is saved as '{name}'"


def _taken(name: str) -> bool:
    return any((OUT / f"{name}{ext}").exists()
               for ext in (".tcad.json", ".step", ".history"))


def _free_name(base: str) -> str:
    """A design name that cannot destroy the user's own work.

    `designs/` is the user's library — 50 designs they machine parts from —
    and `Document.save()` is a plain overwrite: no owner check, no existence
    check, no version tree. The app's own File > Save has refused to land on
    another design since the section 3 review, because doing so destroys that
    file AND (through the doorbell, which POSTs /api/open, which records a
    version) grafts this design onto their version tree. The MCP door had
    none of that, and `build_design(tree)` with no "name" is called
    "untitled" — a real design with a real history in that folder.

    So: a name this server wrote AND still holds unchanged is written again;
    anything else gets the first free "-2", "-3"… and the report says which
    file it is."""
    name = _safe_name(base)
    if _still_mine(name) or not _taken(name):
        _MINE.setdefault(name, "")
        return name
    for n in range(2, 100):
        cand = f"{name}-{n}"
        if _still_mine(cand) or not _taken(cand):
            _MINE.setdefault(cand, "")
            return cand
    import time
    cand = f"{name}-{int(time.time())}"
    _MINE.setdefault(cand, "")
    return cand


def _notify_studio(file_stem: str) -> None:
    """If TextCAD Studio is running locally, ask it to open the new design so
    it pops up live in the browser. Fire-and-forget; silent if Studio is off.

    `external=1` is what makes this the DOORBELL rather than an ordinary open:
    Studio records a one-shot arrival marker and the open page says "X just
    arrived" once. Without it the browser had to guess from the active tab
    moving, and replayed the banner on every reload."""
    import threading
    import urllib.request

    def ping():
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:8123/api/open/{file_stem}?external=1",
                method="POST")
            urllib.request.urlopen(req, timeout=300)
        except Exception:
            pass

    threading.Thread(target=ping, daemon=True).start()


def _report(doc: Document, ok: bool) -> dict:
    rep = {
        "verified": ok,
        "features": [{"id": f.id, "op": f.op, "status": f.status,
                      "problems": f.problems, "volume": f.volume}
                     for f in doc.features],
        "spec": doc.spec,
        "spec_problems": doc.spec_problems,
    }
    # the WHOLE design, not just the tree's tail: a multi-body design measured
    # through result() reported one body's volume and size, so the caller (an
    # AI, usually) believed a fraction of the part was the part (2026-09-07)
    shape = doc.result_shape()
    if shape is not None:
        rep["measured"] = inspector.measure(shape)
        rep["bodies"] = len(doc.result_bodies())
    return rep


@mcp.tool()
def list_operations() -> dict:
    """The complete catalog of legal CAD operations for build_design feature
    trees, plus the authoring conventions. Call this FIRST before designing.
    Any op not in this catalog will be rejected by name."""
    # TREE_PROMPT, not AUTHOR_PROMPT: build_design takes a WHOLE tree, and the
    # step-loop prompt told the caller to answer one feature at a time — a
    # protocol this door rejects outright (section 13 review, 2026-09-16).
    return {"operations": author.op_catalog(),
            "conventions": author.TREE_PROMPT}


@mcp.tool()
def build_design(tree: dict, export_name: str = "") -> dict:
    """Build and machine-verify a CAD design from a feature tree you author.

    `tree` format: {"name": str, "features": [{"id","op","params","inputs"}...],
    "spec": {...}} — exactly as documented by list_operations. The tree is
    validated against the op registry, every feature's geometry is
    health-checked, and the final solid is verified against the spec. On
    success a STEP file (machinable) and a .tcad.json (editable recipe, opens
    in TextCAD Studio) are written. Returns per-feature status, measured facts
    (volume, size, symmetry-relevant data), and file paths. Nothing is trusted;
    everything is measured."""
    with _quiet():
        try:
            doc = author._to_document(tree)
        # TypeError too: a "feature" that is not an object raises "string
        # indices must be integers" out of f["id"], and it used to leave this
        # door as an MCP protocol error instead of the sentence every other
        # malformed tree gets (the step door has caught it since P5).
        except (ValueError, KeyError, TypeError) as e:
            return {"verified": False, "rejected_before_build": str(e)}
        ok = doc.rebuild()
        rep = _report(doc, ok)
        if ok:
            asked = _safe_name(export_name or doc.name)
            mine_before = asked in _MINE
            name = _free_name(export_name or doc.name)
            step = OUT / f"{name}.step"
            doc.to_step(str(step))
            recipe = OUT / f"{name}.tcad.json"
            doc.save(str(recipe))
            _wrote(name)
            rep["design_name"] = name
            rep["step_path"] = str(step)
            rep["recipe_path"] = str(recipe)
            if name != asked:
                rep["renamed"] = _renamed(asked, name, mine_before)
            _notify_studio(name)
        return rep


@mcp.tool()
def design_part(description: str) -> dict:
    """Fully-automatic text-to-CAD: TextCAD's own authoring loop designs the
    part from a natural-language description (needs OPENROUTER_API_KEY on this
    machine), verifies it, and exports STEP. Prefer build_design if YOU can
    author the tree — it is faster and uses no extra API calls."""
    import studio
    model = studio._make_model()
    if model is None:
        return {"verified": False,
                "error": "no OPENROUTER_API_KEY on this machine — author the "
                         "tree yourself and call build_design instead"}
    with _quiet():
        doc, transcript = author.author_design(description, model)
        if doc is None:
            return {"verified": False, "transcript": transcript}
        rep = _report(doc, True)
        asked = _safe_name(doc.name)
        mine_before = asked in _MINE
        name = _free_name(doc.name)        # never over a design of the user's
        step = OUT / f"{name}.step"
        doc.to_step(str(step))
        recipe = OUT / f"{name}.tcad.json"
        doc.save(str(recipe))
        _wrote(name)
        rep["design_name"] = name
        rep["step_path"] = str(step)
        rep["recipe_path"] = str(recipe)
        if name != asked:                  # the report must name the FILE
            rep["renamed"] = _renamed(asked, name, mine_before)
        rep["transcript"] = transcript
        _notify_studio(name)
        return rep


@mcp.tool()
def measure_step(step_path: str) -> dict:
    """Measure an existing STEP file: volume, area, bounding box, center of
    mass, face/edge counts, cylindrical-hole radii, max radial reach,
    watertightness. Works on files from ANY CAD system, not just TextCAD."""
    with _quiet():
        return inspector.measure(step_path)


@mcp.tool()
def verify_step(step_path: str, spec: dict) -> dict:
    """Verify an existing STEP file against ground-truth requirements.
    spec fields (all optional): size [x,y,z each or null], volume (mm^3),
    holes {"radius_mm": count}, n_solids, symmetry (int, N-fold about Z),
    tip_radius (max radial reach, mm), com [x,y,z], require_manifold (bool),
    tol (mm), vol_tol (relative). Returns every mismatch; empty list means the
    part provably matches."""
    with _quiet():
        try:
            # author.checked_spec first: spec_from_dict DROPS a key it does
            # not know, so a spec of {"size": [...], "wall_thickness": 2} was
            # answered "matches_spec": true with the wall thickness never
            # measured — and this tool's own docstring calls an empty
            # mismatch list a proof. One rule, both doors.
            spec_obj = inspector.spec_from_dict(author.checked_spec(spec))
        except Exception as e:
            return {"error": f"malformed spec: {e}"}
        fails = inspector.verify(step_path, spec_obj)
        return {"matches_spec": not fails, "mismatches": fails,
                "measured": inspector.measure(step_path)}


if __name__ == "__main__":
    mcp.run()
