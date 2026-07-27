"""
check.py — Part 3: the domain checker (the "valid but wrong" catcher).

engine.py catches broken code and invalid geometry. But it CANNOT catch a part
that is a perfectly good solid yet not what you asked for — a flange with 5 bolt
holes instead of 6 is a valid solid, so the engine passes it.

This module closes that gap. You give it a `Spec` — the ground-truth facts the
part MUST satisfy (the numbers YOU know, from a request or from your compressor
calculations) — and it measures the finished solid and reports every mismatch.
Those mismatch strings are meant to be fed back into the repair loop, exactly
like an engine error, so the model corrects itself.

It reads the STEP file the engine already wrote, so engine.py is not touched.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter
import build123d as b3d


@dataclass
class Spec:
    """Ground-truth facts the finished part must satisfy. Every field optional.

    size  : expected bounding box (X, Y, Z) in mm. Use None for any axis you
            don't want to check, e.g. size=(100, 100, 10).
    holes : expected holes as {radius_mm: count}, e.g. {4: 6} means "six holes
            of radius 4mm". Counted from the part's cylindrical faces.
    tol   : absolute tolerance (mm) for size and radius matching.
    """
    size: tuple[float | None, float | None, float | None] | None = None
    holes: dict[float, int] = field(default_factory=dict)
    tol: float = 0.5


def measure(solid) -> dict:
    """Extract checkable facts from a solid."""
    bb = solid.bounding_box()
    radii: Counter = Counter()
    for f in solid.faces():
        if str(f.geom_type) == "GeomType.CYLINDER":
            try:
                radii[round(f.radius, 2)] += 1
            except Exception:
                pass
    return {
        "size": (round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)),
        "volume": round(solid.volume, 2),
        "cylinder_radii": dict(radii),
    }


def verify(step_path: str, spec: Spec) -> list[str]:
    """Return a list of human-readable mismatches. Empty list == part is correct."""
    solid = b3d.import_step(step_path)
    m = measure(solid)
    fails: list[str] = []

    if spec.size:
        for axis, expected, got in zip("XYZ", spec.size, m["size"]):
            if expected is not None and abs(expected - got) > spec.tol:
                fails.append(f"{axis} dimension is {got}mm, expected {expected}mm")

    for radius, count in spec.holes.items():
        got = sum(n for r, n in m["cylinder_radii"].items()
                  if abs(r - radius) <= spec.tol)
        if got != count:
            fails.append(
                f"holes of radius {radius}mm: found {got}, expected {count}"
            )

    return fails


if __name__ == "__main__":
    from build123d import (BuildPart, Cylinder, Locations, Hole,
                           PolarLocations, export_step)

    def build_flange(bolt_count):
        with BuildPart() as p:
            Cylinder(radius=50, height=10)
            with Locations((0, 0)):
                Hole(radius=15)
            with PolarLocations(radius=38, count=bolt_count):
                Hole(radius=4)
        return p.part

    # the spec we asked for: 100x100x10 envelope, six 4mm bolt holes
    spec = Spec(size=(100, 100, 10), holes={4: 6}, tol=0.5)

    # CORRECT part
    export_step(build_flange(6), "check_correct.step")
    print("correct part ->", verify("check_correct.step", spec) or "PASS")

    # WRONG part: only 5 bolt holes — a valid solid, but not the spec
    export_step(build_flange(5), "check_wrong.step")
    print("wrong part   ->", verify("check_wrong.step", spec) or "PASS")
