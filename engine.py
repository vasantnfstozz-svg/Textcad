"""
engine.py — the geometry oracle for the text-to-CAD pipeline.

This is the ground-truth core. An LLM writes a build123d script as a STRING;
this module executes it in a controlled namespace and returns a structured
result. It NEVER lets a bad shape through silently — that is the whole point.

Failure tiers (from our design discussion):
  tier 1  "exec"      -> code crashed (bad API, syntax, wrong name)
  tier 2  "geometry"  -> code ran but produced an invalid / empty solid
  ok                  -> valid solid, STEP written

The `error` field on a failure is meant to be fed straight back to the LLM
for the repair loop.
"""

from __future__ import annotations
from dataclasses import dataclass
import traceback
import build123d as b3d


# The script must assign its final solid to a variable named `result`.
CONTRACT = "result"


@dataclass
class RunResult:
    ok: bool
    stage: str            # "ok" | "exec" | "geometry"
    error: str | None = None
    volume: float | None = None
    step_path: str | None = None


def run_script(code: str, step_path: str | None = None,
               extra_globals: dict | None = None) -> RunResult:
    """Execute an LLM-written build123d script string. Never raises.

    extra_globals: optional extra names to expose to the script (e.g. the
    verified block library from blocks.py). Backward compatible — omit for the
    original behavior of exposing only the build123d API.
    """
    namespace: dict = {}
    # give the script the full build123d API, nothing else surprising
    exec("from build123d import *", namespace)
    # optionally add verified helper blocks the model can compose from
    if extra_globals:
        namespace.update(extra_globals)

    # ---- tier 1: execution ------------------------------------------------
    try:
        exec(code, namespace)
    except Exception:
        return RunResult(ok=False, stage="exec", error=traceback.format_exc())

    if CONTRACT not in namespace:
        return RunResult(
            ok=False, stage="exec",
            error=f"Script did not assign a `{CONTRACT}` variable.",
        )

    result = namespace[CONTRACT]

    # a BuildPart context is common — pull the .part out of it
    if isinstance(result, b3d.BuildPart):
        result = result.part

    # ---- tier 2: geometry -------------------------------------------------
    try:
        if not isinstance(result, (b3d.Part, b3d.Solid, b3d.Compound, b3d.Shape)):
            return RunResult(
                ok=False, stage="geometry",
                error=f"`result` is a {type(result).__name__}, not a solid.",
            )
        vol = result.volume
        if vol <= 0:
            return RunResult(ok=False, stage="geometry",
                             error="Solid has zero/negative volume (empty result).")
        if not result.is_valid:
            return RunResult(ok=False, stage="geometry",
                             error="OpenCASCADE reports the solid is invalid.")
    except Exception:
        return RunResult(ok=False, stage="geometry", error=traceback.format_exc())

    # ---- success: export STEP --------------------------------------------
    path = step_path or "out.step"
    b3d.export_step(result, path)
    return RunResult(ok=True, stage="ok", volume=round(vol, 2), step_path=path)


if __name__ == "__main__":
    good = """
with BuildPart() as p:
    Cylinder(radius=50, height=10)
    with PolarLocations(radius=38, count=6):
        Hole(radius=4)
result = p
"""
    broken_api = """
with BuildPart() as p:
    Cylinder(radius=50, height=10)
    p.part.is_valid()          # hallucinated: is_valid is a property
result = p
"""
    bad_geometry = """
# subtract a bigger block from a smaller one -> empty solid
with BuildPart() as p:
    Box(10, 10, 10)
    Box(50, 50, 50, mode=Mode.SUBTRACT)
result = p
"""

    for name, code in [("good", good), ("broken_api", broken_api),
                       ("bad_geometry", bad_geometry)]:
        r = run_script(code, step_path=f"{name}.step")
        head = r.error.strip().splitlines()[-1] if r.error else ""
        print(f"{name:12} ok={r.ok!s:5} stage={r.stage:9} vol={r.volume} {head}")
