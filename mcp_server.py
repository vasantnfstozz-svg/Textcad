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
import meanline
from document import Document

ROOT = Path(__file__).parent
OUT = ROOT / "designs"
OUT.mkdir(exist_ok=True)

mcp = FastMCP("textcad")


def _report(doc: Document, ok: bool) -> dict:
    rep = {
        "verified": ok,
        "features": [{"id": f.id, "op": f.op, "status": f.status,
                      "problems": f.problems, "volume": f.volume}
                     for f in doc.features],
        "spec": doc.spec,
        "spec_problems": doc.spec_problems,
    }
    part = doc.result()
    if part is not None:
        rep["measured"] = inspector.measure(part)
    return rep


@mcp.tool()
def list_operations() -> dict:
    """The complete catalog of legal CAD operations for build_design feature
    trees, plus the authoring conventions. Call this FIRST before designing.
    Any op not in this catalog will be rejected by name."""
    return {"operations": author.op_catalog(),
            "conventions": author.AUTHOR_PROMPT}


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
        except (ValueError, KeyError) as e:
            return {"verified": False, "rejected_before_build": str(e)}
        ok = doc.rebuild()
        rep = _report(doc, ok)
        if ok:
            name = export_name or doc.name or "design"
            step = OUT / f"{name}.step"
            doc.to_step(str(step))
            recipe = OUT / f"{name}.tcad.json"
            doc.save(str(recipe))
            rep["step_path"] = str(step)
            rep["recipe_path"] = str(recipe)
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
        step = OUT / f"{doc.name}.step"
        doc.to_step(str(step))
        doc.save(str(OUT / f"{doc.name}.tcad.json"))
        rep["step_path"] = str(step)
        rep["transcript"] = transcript
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
            spec_obj = inspector.spec_from_dict(spec)
        except Exception as e:
            return {"error": f"malformed spec: {e!r}"}
        fails = inspector.verify(step_path, spec_obj)
        return {"matches_spec": not fails, "mismatches": fails,
                "measured": inspector.measure(step_path)}


@mcp.tool()
def design_compressor(mass_flow_kg_s: float, pressure_ratio: float,
                      rpm: float, backsweep_deg: float = 35.0) -> dict:
    """Design a centrifugal compressor impeller from its DUTY using first-order
    meanline physics (Euler work, Wiesner slip, velocity triangles), build the
    geometry, independently verify it (blade count symmetry, tip radius,
    watertight), and export STEP. Slow: the build takes 1-2 minutes."""
    with _quiet():
        return _design_compressor(mass_flow_kg_s, pressure_ratio, rpm,
                                  backsweep_deg)


def _design_compressor(mass_flow_kg_s, pressure_ratio, rpm, backsweep_deg):
    duty = meanline.Duty(mass_flow=mass_flow_kg_s,
                         pressure_ratio=pressure_ratio, rpm=rpm,
                         backsweep_deg=backsweep_deg)
    d = meanline.design(duty)
    rep_design = {
        "tip_radius_mm": d.tip_radius, "tip_speed_m_s": round(d.tip_speed, 1),
        "blade_count": d.blade_count, "exit_width_mm": d.exit_width,
        "beta1_deg": d.beta1_deg, "beta2_deg": d.beta2_deg,
        "inducer_shroud_radius_mm": d.inducer_shroud_radius,
        "axial_length_mm": d.axial_length, "power_kw": round(d.power_kw, 1),
        "slip_factor": round(d.slip_factor, 3),
    }
    build = meanline.build_from_design(d)
    if not build.ok or build.part is None:
        return {"verified": False, "design": rep_design,
                "problems": build.all_problems()}
    import build123d as b3d
    m = inspector.measure(build.part)
    sym_ok = inspector.is_rotationally_symmetric(build.part, d.blade_count)
    step = OUT / f"compressor-PR{pressure_ratio}-{d.blade_count}blades.step"
    b3d.export_step(build.part, str(step))
    return {"verified": sym_ok and m.get("is_manifold", False),
            "design": rep_design,
            "measured": {"volume": m["volume"], "size": m["size"],
                         "tip_radius": m.get("max_radius"),
                         "blade_symmetry_confirmed": sym_ok,
                         "watertight": m.get("is_manifold")},
            "step_path": str(step)}


if __name__ == "__main__":
    mcp.run()
