"""
assembly.py — Phase 3: decompose -> verify each sub-part -> assemble -> verify.

A complex part is a TREE of sub-parts, not one blob. Building it as one giant
script means one hallucinated line poisons the whole thing and you can't tell
where. This module builds each named sub-part in ISOLATION, health-checks it on
its own, then assembles them and checks the assembly. When something is wrong you
get the exact component name, not a wall of geometry.

Two assembly modes:
  * "fuse" — the sub-parts are meant to become ONE machinable solid (e.g. an
    impeller: hub + blades). Overlap between them is EXPECTED and good. We verify
    the result is a single watertight body — if it comes out in pieces, a
    sub-part is floating (not touching the rest), which we flag by name.
  * "fit" — the sub-parts are distinct bodies that must NOT interpenetrate (e.g.
    a shaft in a bore). Here overlap is a CLASH; we report every interfering pair
    and the overlap volume.

Nothing raises. A sub-part whose builder crashes becomes a localized failure
report, exactly like an engine/inspector error, ready for the repair loop.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from functools import reduce
from typing import Callable
from build123d import Pos
import inspector


# ---------------------------------------------------------------------------
# The tree: a component is a named sub-part with a builder and a place to sit
# ---------------------------------------------------------------------------

@dataclass
class Component:
    """One sub-part of a larger design.

    name    : how it's referred to in every report (e.g. "hub", "blades").
    builder : zero-arg function returning a build123d Part. Kept lazy so a
              crash is caught and localized to THIS component.
    at      : (x, y, z) translation applied to the built part in the assembly.
    spec    : optional per-part inspector.Spec — check the sub-part on its own.
    """
    name: str
    builder: Callable[[], object]
    at: tuple[float, float, float] = (0.0, 0.0, 0.0)
    spec: "inspector.Spec | None" = None


@dataclass
class ComponentReport:
    name: str
    ok: bool
    problems: list[str]
    volume: float | None = None
    part: object | None = None          # positioned part, or None if it failed


@dataclass
class AssemblyReport:
    ok: bool
    mode: str
    components: list[ComponentReport]
    assembly_problems: list[str] = field(default_factory=list)
    part: object | None = None          # the assembled solid, or None

    def all_problems(self) -> list[str]:
        """Flat, human-readable problem list with component names attached."""
        out = []
        for c in self.components:
            out += [f"[{c.name}] {p}" for p in c.problems]
        out += [f"[assembly] {p}" for p in self.assembly_problems]
        return out

    def summary(self) -> str:
        lines = [f"assembly ok={self.ok} mode={self.mode}"]
        for c in self.components:
            tag = "OK  " if c.ok else "FAIL"
            lines.append(f"  {tag} {c.name:16} vol={c.volume}")
            for p in c.problems:
                lines.append(f"         - {p}")
        for p in self.assembly_problems:
            lines.append(f"  [assembly] {p}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Building and checking one sub-part in isolation
# ---------------------------------------------------------------------------

def build_component(comp: Component) -> ComponentReport:
    """Build one sub-part, position it, and health-check it on its own."""
    try:
        raw = comp.builder()
    except Exception as e:
        return ComponentReport(comp.name, ok=False,
                               problems=[f"builder crashed: {e!r}"])
    try:
        part = Pos(*comp.at) * raw if comp.at != (0, 0, 0) else raw
    except Exception as e:
        return ComponentReport(comp.name, ok=False,
                               problems=[f"could not position: {e!r}"])

    problems = list(inspector.health(part))
    if comp.spec is not None:
        problems += inspector.verify(part, comp.spec)

    vol = None
    try:
        vol = round(part.volume, 3)
    except Exception:
        pass

    return ComponentReport(comp.name, ok=not problems, problems=problems,
                           volume=vol, part=part)


# ---------------------------------------------------------------------------
# Assembly-level geometry helpers
# ---------------------------------------------------------------------------

def _union(parts: list) -> object:
    return reduce(lambda a, b: a + b, parts)


def interferences(reports: list[ComponentReport],
                  clash_tol: float = 1e-3) -> list[tuple[str, str, float]]:
    """Every pair of components that overlap by more than clash_tol, as
    (name_a, name_b, overlap_volume)."""
    clashes = []
    live = [r for r in reports if r.part is not None]
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            try:
                v = (live[i].part & live[j].part).volume
            except Exception:
                v = 0.0
            if v > clash_tol:
                clashes.append((live[i].name, live[j].name, round(v, 3)))
    return clashes


# ---------------------------------------------------------------------------
# The orchestrator: decompose -> verify each -> assemble -> verify assembly
# ---------------------------------------------------------------------------

def build_and_verify(components: list[Component], mode: str = "fuse",
                     assembly_spec: "inspector.Spec | None" = None,
                     clash_tol: float = 1e-3) -> AssemblyReport:
    """Full Phase-3 pipeline. mode: 'fuse' (one solid) or 'fit' (distinct bodies)."""
    if mode not in ("fuse", "fit"):
        raise ValueError("mode must be 'fuse' or 'fit'")

    reports = [build_component(c) for c in components]

    # If any sub-part is unsound, stop here — the failure is already localized.
    if any(not r.ok for r in reports):
        return AssemblyReport(ok=False, mode=mode, components=reports,
                              assembly_problems=["one or more sub-parts failed; "
                                                 "fix those before assembling"])

    parts = [r.part for r in reports]
    problems: list[str] = []

    try:
        assembled = _union(parts)
    except Exception as e:
        return AssemblyReport(ok=False, mode=mode, components=reports,
                              assembly_problems=[f"union failed: {e!r}"])

    n_solids = inspector.measure(assembled).get("n_solids")

    if mode == "fuse":
        problems += inspector.health(assembled)
        if n_solids is not None and n_solids > 1:
            problems.append(f"result is in {n_solids} disconnected pieces — a "
                            "sub-part is floating (not touching the rest)")
    else:  # fit
        clashes = interferences(reports, clash_tol)
        for a, b, v in clashes:
            problems.append(f"'{a}' and '{b}' interfere (overlap {v}mm^3) — "
                            "parts must not interpenetrate")

    if assembly_spec is not None:
        problems += inspector.verify(assembled, assembly_spec)

    return AssemblyReport(ok=not problems, mode=mode, components=reports,
                          assembly_problems=problems, part=assembled)


# ---------------------------------------------------------------------------
# Self-test — proves decomposition + localization, no LLM.  python assembly.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from blocks import revolve_profile, polar_pattern
    from build123d import Box

    def hub():
        return revolve_profile([(0, 0), (18, 0), (18, 8), (9, 26), (0, 26)])

    def blades(n, reach=20):
        return polar_pattern(Pos(reach, 0, 4) * Box(28, 3, 8), count=n)

    print("=== CASE 1: healthy 7-blade impeller (fuse) ===")
    spec = inspector.Spec(symmetry=7, n_solids=1)
    r1 = build_and_verify(
        [Component("hub", hub),
         Component("blades", lambda: blades(7))],
        mode="fuse", assembly_spec=spec)
    print(r1.summary())

    print("\n=== CASE 2: a blade group that FLOATS (localized failure) ===")
    r2 = build_and_verify(
        [Component("hub", hub),
         Component("blades", lambda: blades(7), at=(120, 0, 0))],  # moved away
        mode="fuse", assembly_spec=spec)
    print(r2.summary())

    print("\n=== CASE 3: a sub-part whose builder CRASHES (localized) ===")
    r3 = build_and_verify(
        [Component("hub", hub),
         Component("bad_blades", lambda: blades(0))],   # count=0 -> ValueError
        mode="fuse")
    print(r3.summary())

    print("\n=== CASE 4: 'fit' mode — two bodies that CLASH ===")
    r4 = build_and_verify(
        [Component("shaft", lambda: __import__("blocks").disc(10, 40)),
         Component("collar", lambda: __import__("blocks").disc(9, 40),
                   at=(5, 0, 0))],   # overlaps the shaft
        mode="fit")
    print(r4.summary())

    print("\n=== CASE 5: 'fit' mode — same two bodies, spaced apart (OK) ===")
    r5 = build_and_verify(
        [Component("shaft", lambda: __import__("blocks").disc(10, 40)),
         Component("collar", lambda: __import__("blocks").disc(9, 40),
                   at=(40, 0, 0))],
        mode="fit")
    print(r5.summary())
