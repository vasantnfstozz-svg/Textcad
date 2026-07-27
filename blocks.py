"""
blocks.py — Phase 2: the verified building-block library.

The single biggest source of hallucination is asking the LLM to INVENT geometry
code from scratch. The fix: give it a curated set of small, already-TESTED
helper functions and tell it to COMPOSE from these instead. You cannot
hallucinate an API you are only calling.

Every function here:
  * takes plain numeric parameters,
  * returns a build123d `Part` (a real solid) using only API confirmed on this
    machine (build123d 0.11.1, algebra mode),
  * is exercised in the self-test at the bottom and validated with
    inspector.health(), so the library is guaranteed sound before the LLM ever
    touches it.

Convention: parts are built centered on the origin, extruded along +/-Z, so the
hole/pattern helpers (which cut tall cutters along Z) work regardless of scale.
"""

from __future__ import annotations
import math
from build123d import (
    Box, Cylinder, Pos, PolarLocations, Locations,
    BuildSketch, RegularPolygon, BuildLine, Polyline, Spline, make_face,
    trace, extrude, revolve, Axis, Plane, Part,
)


# ---------------------------------------------------------------------------
# Primitive solids
# ---------------------------------------------------------------------------

def plate(width: float, depth: float, thickness: float) -> Part:
    """A rectangular plate centered on the origin (X=width, Y=depth, Z=thickness)."""
    return Box(width, depth, thickness)


def disc(radius: float, thickness: float) -> Part:
    """A solid cylinder (disc) centered on the origin, axis along Z."""
    return Cylinder(radius=radius, height=thickness)


def tube(outer_radius: float, inner_radius: float, height: float) -> Part:
    """A hollow tube / ring / washer, axis along Z. inner < outer required."""
    if inner_radius >= outer_radius:
        raise ValueError("tube: inner_radius must be < outer_radius")
    return Cylinder(radius=outer_radius, height=height) - Cylinder(
        radius=inner_radius, height=height)


def polygon_plate(sides: int, circumradius: float, thickness: float) -> Part:
    """A regular-polygon prism (hex nut stock, etc.), axis along Z.
    circumradius = distance from center to a corner."""
    with BuildSketch() as sk:
        RegularPolygon(radius=circumradius, side_count=sides)
    return extrude(sk.sketch, amount=thickness)


def hex_plate(across_flats: float, thickness: float) -> Part:
    """A hexagonal plate specified by its across-flats (wrench) size."""
    circumradius = across_flats / math.sqrt(3.0)   # AF = circumradius * sqrt(3)
    return polygon_plate(6, circumradius, thickness)


def revolve_profile(points: list[tuple[float, float]]) -> Part:
    """Revolve a 2D profile 360 deg about the Z axis to make an axisymmetric
    solid (hub, pulley, shaft, shroud). `points` are (radius, z) pairs in the XZ
    plane; the profile is auto-closed. All radii must be >= 0. This is the
    workhorse for turned/turbomachinery-style parts."""
    if len(points) < 3:
        raise ValueError("revolve_profile: need at least 3 points")
    pts = [(float(r), float(z)) for r, z in points]
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
    return revolve(sk.sketch, axis=Axis.Z)


def curved_blade(inner_radius: float, outer_radius: float,
                 inlet_angle_deg: float, exit_angle_deg: float,
                 height: float, thickness: float) -> Part:
    """A real turbomachinery-style curved (backswept) blade, standing on the XY
    plane and extruded up +Z by `height`.

    The blade follows a CAMBER LINE computed by integrating the blade-angle law
    d(theta) = tan(beta)/r * dr, with beta varying linearly from
    `inlet_angle_deg` (at inner_radius) to `exit_angle_deg` (at outer_radius).
    Angles are measured from the radial direction; 0 = straight radial blade,
    positive = backswept. Typical centrifugal impeller: inlet 20-40, exit 40-60.

    The result is intersected with a cylinder of `outer_radius`, so the tip
    radius is EXACT by construction. The inner end sits at `inner_radius` —
    make that SMALLER than the hub's local radius so the blade overlaps into
    the hub and fuses (touching is not enough).
    """
    if inner_radius >= outer_radius:
        raise ValueError("curved_blade: inner_radius must be < outer_radius")
    if thickness <= 0 or height <= 0:
        raise ValueError("curved_blade: height and thickness must be positive")

    # camber line: beta(r) linear, theta integrated with tan(beta)/r
    n = 16
    pts, theta = [], 0.0
    for i in range(n + 1):
        t = i / n
        r = inner_radius + (outer_radius - inner_radius) * t
        pts.append((r * math.cos(theta), r * math.sin(theta)))
        if i < n:
            beta = math.radians(inlet_angle_deg
                                + (exit_angle_deg - inlet_angle_deg) * t)
            theta += math.tan(beta) / r * ((outer_radius - inner_radius) / n)

    with BuildSketch() as sk:
        with BuildLine():
            Spline(*pts)
        trace(line_width=thickness)
    blade = extrude(sk.sketch, amount=height)
    # trim to the exact tip radius (trace() overshoots at the rounded tip)
    return blade & Cylinder(radius=outer_radius, height=4 * height)


# ---------------------------------------------------------------------------
# Feature operations (take a part, return a modified part)
# ---------------------------------------------------------------------------

def _tall_cutter(radius: float, span: float = 1.0e5) -> Part:
    """A cylinder tall enough to cut clean through any reasonably-sized part."""
    return Cylinder(radius=radius, height=span)


def with_center_hole(part: Part, radius: float) -> Part:
    """Drill a through-hole on the Z axis at the origin."""
    return part - _tall_cutter(radius)


def with_bolt_circle(part: Part, count: int, bolt_radius: float,
                     pitch_circle_dia: float) -> Part:
    """Drill `count` through-holes evenly on a bolt circle of the given pitch
    circle diameter (PCD), centered on the origin, axis along Z."""
    if count < 1:
        raise ValueError("with_bolt_circle: count must be >= 1")
    cutter = _tall_cutter(bolt_radius)
    result = part
    for loc in PolarLocations(radius=pitch_circle_dia / 2.0, count=count):
        result = result - (loc * cutter)
    return result


def polar_pattern(feature: Part, count: int) -> Part:
    """Return the union of `count` copies of `feature`, evenly rotated about Z.
    Use to build N-fold symmetric parts (e.g. impeller blades) from ONE feature —
    guarantees the symmetry the inspector will check for."""
    if count < 1:
        raise ValueError("polar_pattern: count must be >= 1")
    parts = [feature.rotate(Axis.Z, 360.0 * i / count) for i in range(count)]
    # pairwise tree union: far cheaper than a chain for high counts
    while len(parts) > 1:
        parts = [parts[i] + parts[i + 1] if i + 1 < len(parts) else parts[i]
                 for i in range(0, len(parts), 2)]
    return parts[0]


# ---------------------------------------------------------------------------
# Registry — the exact names exposed to the LLM's script namespace
# ---------------------------------------------------------------------------

EXPORTS = {
    "plate": plate,
    "disc": disc,
    "tube": tube,
    "polygon_plate": polygon_plate,
    "hex_plate": hex_plate,
    "revolve_profile": revolve_profile,
    "curved_blade": curved_blade,
    "with_center_hole": with_center_hole,
    "with_bolt_circle": with_bolt_circle,
    "polar_pattern": polar_pattern,
}


def api_summary() -> str:
    """A compact, copy-pasteable list of the blocks, for the system prompt."""
    return "\n".join(
        f"  {name}{_signature(fn)}" for name, fn in EXPORTS.items())


def _signature(fn) -> str:
    import inspect
    return str(inspect.signature(fn))


# ---------------------------------------------------------------------------
# Self-test — build every block and validate it with the inspector. No LLM.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import inspector

    cases = {
        "plate":        plate(40, 30, 5),
        "disc":         disc(20, 8),
        "tube":         tube(20, 12, 6),
        "polygon_plate": polygon_plate(5, 25, 8),
        "hex_plate":    hex_plate(across_flats=30, thickness=8),
        "revolve_profile (pulley)":
            revolve_profile([(0, 0), (30, 0), (30, 6), (18, 12),
                             (18, 20), (0, 20)]),
        "curved_blade (backswept)":
            curved_blade(inner_radius=10, outer_radius=40,
                         inlet_angle_deg=25, exit_angle_deg=55,
                         height=20, thickness=2.5),
        "with_center_hole": with_center_hole(disc(20, 8), 6),
        "with_bolt_circle (6)":
            with_bolt_circle(disc(50, 10), count=6, bolt_radius=4,
                             pitch_circle_dia=76),
        "polar_pattern (blades x8)":
            polar_pattern(Pos(20, 0, 0) * Box(24, 3, 10), count=8),
    }

    print("=== block library self-test (validated by inspector.health) ===")
    all_ok = True
    for name, part in cases.items():
        problems = inspector.health(part)
        status = "OK   " if not problems else "FAIL "
        if problems:
            all_ok = False
        vol = round(part.volume, 1)
        sym = inspector.rotational_symmetry_order(part)
        extra = f"vol={vol:<10} sym={sym}"
        print(f"  {status}{name:28} {extra}  {problems if problems else ''}")

    print("\nALL BLOCKS HEALTHY" if all_ok else "\nSOME BLOCKS FAILED — fix before use")

    print("\n=== api_summary (goes into the LLM system prompt) ===")
    print(api_summary())
