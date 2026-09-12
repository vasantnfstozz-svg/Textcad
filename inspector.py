"""
inspector.py — Part 4: the scaled verifier (Layer 2, grown up).

check.py proved the idea on flanges: measure a solid, compare to a Spec. But it
only knows bounding box + cylinder-face counting, which says almost nothing about
a twisted blade or any non-prismatic part. The moment geometry gets complex,
that Layer 2 goes blind — and a blind checker lets hallucinations through.

This module is the geometry-AGNOSTIC verifier. It measures facts that are true of
ANY solid (mass, area, center of mass, topology counts, manifold-ness, rotational
symmetry) and compares them to a Spec. It splits verification into two kinds:

  * health(solid)  -> spec-free sanity: is this even a sane, single, watertight
                      solid? (catches broken/degenerate output with NO spec.)
  * verify(..spec) -> health PLUS "is it the RIGHT part?" vs ground truth.

Every mismatch string is meant to be fed straight back into the repair loop,
exactly like an engine error. Nothing here raises; a failed measurement becomes
a reported problem, never a crash.

All API used here is confirmed against build123d 0.11.1 on this machine.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter
import build123d as b3d


# ---------------------------------------------------------------------------
# Spec — ground-truth facts the finished part must satisfy. Every field optional.
# ---------------------------------------------------------------------------

@dataclass
class Spec:
    """What the part MUST be true. Set only the fields you care about.

    size        : expected bounding box (X, Y, Z) mm. None per-axis to skip it.
    volume      : expected volume (mm^3); matched within vol_tol (relative).
    holes       : {radius_mm: count} counted from cylindrical faces.
    n_solids    : expected number of separate solids (usually 1).
    symmetry    : expected N-fold rotational symmetry about Z (e.g. blade count).
    tip_radius  : expected maximum radial reach from the Z axis (mm) — the right
                  way to pin the tip radius of rotating parts. (A bounding box
                  CANNOT express this for odd blade counts: with no blade
                  directly opposite another, bbox < 2*tip_radius. Learned from
                  the first live-model run.)
    com         : expected center of mass (X, Y, Z) mm; None per-axis to skip.
    require_manifold : if True, a non-watertight/non-manifold solid is a failure.
    tol         : absolute tolerance (mm) for size / radius / com.
    vol_tol     : RELATIVE tolerance for volume (0.02 == +/-2%).
    """
    size: tuple[float | None, float | None, float | None] | None = None
    volume: float | None = None
    holes: dict[float, int] = field(default_factory=dict)
    n_solids: int | None = None
    symmetry: int | None = None
    tip_radius: float | None = None
    com: tuple[float | None, float | None, float | None] | None = None
    require_manifold: bool = True
    tol: float = 0.5
    vol_tol: float = 0.02


def spec_from_dict(d: dict) -> Spec:
    """Build a Spec from JSON-safe data (tuples as lists, hole radii as string
    keys). Shared by the document engine and the MCP server."""
    import dataclasses
    d = dict(d)
    for key in ("size", "com"):
        if d.get(key) is not None:
            d[key] = tuple(d[key])
    if d.get("holes"):
        d["holes"] = {float(k): int(v) for k, v in d["holes"].items()}
    known = {f.name for f in dataclasses.fields(Spec)}
    return Spec(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Measurement — geometry-agnostic facts about a solid
# ---------------------------------------------------------------------------

def _as_solid(solid_or_path):
    """Accept either a build123d shape or a path to a STEP file."""
    if isinstance(solid_or_path, str):
        return b3d.import_step(solid_or_path)
    if isinstance(solid_or_path, b3d.BuildPart):
        return solid_or_path.part
    return solid_or_path


def measure(solid) -> dict:
    """Extract checkable facts from a solid. Defensive: never raises."""
    solid = _as_solid(solid)
    m: dict = {}

    try:
        bb = solid.bounding_box()
        m["size"] = (round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3))
    except Exception as e:
        m["size"] = None
        m["size_error"] = repr(e)

    for key, fn in (("volume", lambda: round(solid.volume, 3)),
                    ("area", lambda: round(solid.area, 3)),
                    ("is_valid", lambda: bool(solid.is_valid)),
                    # the same verdict health() gives — build123d's own flag
                    # fails every cone apex and sphere pole (see closed_shell)
                    ("is_manifold", lambda: bool(closed_shell(solid)))):
        try:
            m[key] = fn()
        except Exception as e:
            m[key] = None
            m[key + "_error"] = repr(e)

    try:
        c = solid.center(b3d.CenterOf.MASS)
        m["com"] = (round(c.X, 3), round(c.Y, 3), round(c.Z, 3))
    except Exception as e:
        m["com"] = None
        m["com_error"] = repr(e)

    try:
        faces = solid.faces()
        m["n_solids"] = len(solid.solids())
        m["n_faces"] = len(faces)
        m["n_edges"] = len(solid.edges())
        m["n_vertices"] = len(solid.vertices())
        m["face_types"] = dict(Counter(str(f.geom_type) for f in faces))
        radii: Counter = Counter()
        for f in faces:
            if str(f.geom_type) == "GeomType.CYLINDER":
                try:
                    radii[round(f.radius, 2)] += 1
                except Exception:
                    pass
        m["cylinder_radii"] = dict(radii)
        m["max_radius"] = round(max(
            (v.X ** 2 + v.Y ** 2) ** 0.5 for v in solid.vertices()), 3)
    except Exception as e:
        m["topology_error"] = repr(e)

    return m


# The boolean is the PROOF of symmetry, but it is also unbounded work on
# arbitrary geometry: on 2026-09-12 a random plate added beside the 24-rib
# bottle cap made `compound - rotated compound` run for 22 minutes and take
# 44 GB (ShapeUpgrade_UnifySameDomain on the leftovers), and a 16 GB laptop
# died. Two NECESSARY conditions run first, each a few milliseconds, and a
# shape that fails either is not symmetric — no boolean. A rotation that maps
# the shape onto itself keeps its bounding box, and carries every vertex to a
# point that is still on or inside the shape. Only a shape that passes both
# reaches the boolean, which then runs without the clean pass (the volume of
# the residue is all that is read, and the clean is where the memory went).
_VERTEX_GATE_SAMPLES = 60


def _rotation_keeps_extent(solid, rotated, tol: float) -> bool:
    bb, rb = solid.bounding_box(), rotated.bounding_box()
    return all(abs(a - b) <= tol for a, b in
               zip((bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z),
                   (rb.min.X, rb.min.Y, rb.min.Z, rb.max.X, rb.max.Y, rb.max.Z)))


def _rotation_keeps_vertices(solid, rotated, tol: float) -> bool:
    """Every (sampled) vertex, rotated, lands on the boundary or inside."""
    verts = rotated.vertices()
    step = max(1, len(verts) // _VERTEX_GATE_SAMPLES)
    solids = solid.solids()
    for v in verts[::step]:
        p = v.center()
        if solid.distance_to(p) <= tol:
            continue
        if not any(s.is_inside(p) for s in solids):
            return False
    return True


def _rotation_residual(solid, rotated) -> float:
    """Volume of what the rotation does NOT map onto the shape (the proof).

    `cut`, not `-`: Compound.__sub__ unpacks the tool into its top-level
    members and cuts them one by one, and on a compound whose members
    OVERLAP (the cap with a disc through its wall) that read 6967 mm3 of
    residue on a shape that maps onto itself exactly; `cut` reads 0."""
    with b3d.SkipClean():
        return solid.cut(rotated).volume


def is_rotationally_symmetric(solid, n: int, rel_tol: float = 1e-3) -> bool:
    """Does rotating by 360/n map the solid onto itself? Two cheap gates,
    then ONE boolean op — use this for spec checks; use
    rotational_symmetry_order only when you need to discover the order (it
    costs ~max_n boolean ops)."""
    solid = _as_solid(solid)
    try:
        total = solid.volume
        if total <= 0:
            return False
        rotated = solid.rotate(b3d.Axis.Z, 360.0 / n)
        bb = solid.bounding_box()
        tol = rel_tol * max(bb.size.X, bb.size.Y, bb.size.Z, 1.0)
        if not _rotation_keeps_extent(solid, rotated, tol):
            return False
        if not _rotation_keeps_vertices(solid, rotated, tol):
            return False
        return _rotation_residual(solid, rotated) <= rel_tol * total
    except Exception:
        return False


def rotational_symmetry_order(solid, max_n: int = 24, rel_tol: float = 1e-3) -> int:
    """Largest N (>=1) for which rotating the solid by 360/N about Z maps it onto
    itself. TRUE geometric test: rotate the actual solid and boolean-subtract it
    from the original; if what's left has negligible volume, the two coincide, so
    the part is N-fold symmetric.

    This is how you verify 'blade count' on an impeller without knowing anything
    about blades. Returns 1 if no rotational symmetry is detected. `rel_tol` is
    the leftover-volume threshold as a fraction of total volume.
    """
    solid = _as_solid(solid)
    try:
        total = solid.volume
        if total <= 0:
            return 1
        eps = rel_tol * total
    except Exception:
        return 1

    def symmetric(n: int) -> bool:
        try:
            rotated = solid.rotate(b3d.Axis.Z, 360.0 / n)
            return (solid - rotated).volume <= eps
        except Exception:
            return False

    best = 1
    for n in range(2, max_n + 1):
        if symmetric(n):
            best = n
    return best


# ---------------------------------------------------------------------------
# Health — spec-free sanity. Catches broken output with NO ground truth needed.
# ---------------------------------------------------------------------------

def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def health(solid, require_manifold: bool = True,
           check_valid: bool = True) -> list[str]:
    """Return problems that make a solid inherently unsound. Empty == healthy.

    Computes ONLY the four facts it judges on, rather than calling measure().
    measure() takes a full topology census — every face's geom_type, cylinder
    radii, a max-radius scan over every vertex, area, centre of mass, edge and
    vertex counts — and health looks at none of it. Measured on esp32-remote's
    result solid: measure() costs ~630 ms a call and the parts health actually
    reads cost ~320 ms, and health ran to 14.5 s of a 22.5 s rebuild (65%)
    because the rebuild calls it once per feature.

    `check_valid=False` skips OpenCASCADE's validity analysis, the single most
    expensive check at ~270 ms on a large solid. The rebuild uses it for
    INTERMEDIATE features and keeps the full check for the result — see
    Document.rebuild."""
    solid = _as_solid(solid)
    problems: list[str] = []

    vol = _try(lambda: round(solid.volume, 3))
    if vol is None:
        problems.append("volume could not be measured (degenerate/empty result)")
    elif vol <= 0:
        problems.append(f"non-positive volume ({vol}) — empty solid")

    if check_valid and _try(lambda: bool(solid.is_valid)) is False:
        problems.append("OpenCASCADE reports the solid is invalid")

    if _try(lambda: len(solid.solids()), 1) == 0:
        problems.append("no solid present (empty compound)")

    if require_manifold and _try(lambda: closed_shell(solid)) is not True:
        # NOT build123d's is_manifold: that flag counts the faces on EVERY edge,
        # including DEGENERATED ones — the zero-length edges OCCT puts at a
        # sphere's poles and at the apex of a cone, which belong to one face by
        # construction — so it called every cone, and a revolve whose profile
        # touches the axis at an angle (a hexagon about its own side,
        # probes/revolve_face_probe.py §9), an open shell, while the same
        # sweep about an axis a few microns OFF the edge (a sliver face, no
        # apex) passed. closed_shell is the same census with that one
        # exemption, and one topology map instead of two. (Until 2026-09-05
        # this was the flag plus a sphere-only exemption.)
        problems.append("solid is not manifold/watertight (open shell) — "
                        "not machinable/printable")

    return problems


_APEX_SURFACES = {"CONE", "SPHERE", "REVOLUTION"}   # a pole / apex is a point by nature


def closed_shell(solid) -> bool:
    """THE closed-shell verdict (health and measure both read it): every edge
    of `solid` lies on exactly two faces — a seam counts twice for its one
    face, as it should — EXCEPT a degenerated edge that belongs to exactly ONE
    face of a cone, a sphere or a surface of revolution: its apex or pole, a
    point by nature. A degenerated edge on any other surface, or one shared by
    three or more faces, stays a defect: a fillet too large for the corner it
    wraps pinches its BSPLINE face to a point, OCCT calls that valid, and the
    Fillet tool relies on THIS check to refuse it (tests/test_fillet_tool.py,
    radius 6 on the 5 mm corners)."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    m = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
    if m.Extent() == 0:
        return False
    for i in range(1, m.Extent() + 1):
        faces = m.FindFromIndex(i)
        if faces.Size() == 2:
            continue
        if (faces.Size() == 1
                and BRep_Tool.Degenerated_s(b3d.Edge(m.FindKey(i)).wrapped)
                and b3d.Face(faces.First()).geom_type.name in _APEX_SURFACES):
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Verify — health PLUS "is it the RIGHT part?" vs a Spec
# ---------------------------------------------------------------------------

def verify(solid_or_path, spec: Spec) -> list[str]:
    """Return every mismatch (health + spec). Empty list == part is correct."""
    solid = _as_solid(solid_or_path)
    fails = health(solid, require_manifold=spec.require_manifold)
    m = measure(solid)

    if spec.size and m.get("size"):
        for axis, expected, got in zip("XYZ", spec.size, m["size"]):
            if expected is not None and abs(expected - got) > spec.tol:
                fails.append(f"{axis} dimension is {got}mm, expected {expected}mm")

    if spec.volume is not None and m.get("volume") is not None:
        if abs(m["volume"] - spec.volume) > spec.vol_tol * spec.volume:
            fails.append(f"volume is {m['volume']}mm^3, expected "
                         f"~{spec.volume}mm^3 (+/-{spec.vol_tol*100:.0f}%)")

    for radius, count in spec.holes.items():
        got = sum(n for r, n in m.get("cylinder_radii", {}).items()
                  if abs(r - radius) <= spec.tol)
        if got != count:
            fails.append(f"holes of radius {radius}mm: found {got}, expected {count}")

    if spec.n_solids is not None and m.get("n_solids") is not None:
        if m["n_solids"] != spec.n_solids:
            msg = (f"part has {m['n_solids']} separate solids, "
                   f"expected {spec.n_solids}")
            if m["n_solids"] > spec.n_solids:
                msg += (" — the pieces do not physically OVERLAP. Merely "
                        "touching at a face/edge is not enough to fuse; extend "
                        "each attached feature INTO the body it joins (e.g. a "
                        "blade's inner edge must reach a radius smaller than "
                        "the hub's local radius over its full height)")
            fails.append(msg)

    if spec.symmetry is not None:
        if not is_rotationally_symmetric(solid, spec.symmetry):
            fails.append(f"part is not {spec.symmetry}-fold rotationally "
                         f"symmetric about Z (wrong feature count or "
                         f"unevenly placed features)")

    if spec.tip_radius is not None and m.get("max_radius") is not None:
        if abs(m["max_radius"] - spec.tip_radius) > spec.tol:
            fails.append(f"maximum radial reach (tip radius) is "
                         f"{m['max_radius']}mm, expected {spec.tip_radius}mm")

    if spec.com and m.get("com"):
        for axis, expected, got in zip("XYZ", spec.com, m["com"]):
            if expected is not None and abs(expected - got) > spec.tol:
                fails.append(f"center of mass {axis} is {got}mm, expected {expected}mm")

    return fails


# ---------------------------------------------------------------------------
# Self-test — proves each check WITHOUT an LLM. Run: python inspector.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from build123d import (BuildPart, Cylinder, Box, Locations, Hole,
                           PolarLocations, Mode)

    def flange(bolt_count):
        with BuildPart() as p:
            Cylinder(radius=50, height=10)
            with Locations((0, 0)):
                Hole(radius=15)
            with PolarLocations(radius=38, count=bolt_count):
                Hole(radius=4)
        return p.part

    print("=== health checks (spec-free) ===")
    good = flange(6)
    print("good flange   ->", health(good) or "HEALTHY")

    with BuildPart() as bp:
        Box(10, 10, 10)
        Box(50, 50, 50, mode=Mode.SUBTRACT)   # empty result
    print("empty solid   ->", health(bp) or "HEALTHY (unexpected!)")

    print("\n=== symmetry detection (the 'blade count' test) ===")
    print("6-bolt flange symmetry order ->", rotational_symmetry_order(flange(6)))
    print("5-bolt flange symmetry order ->", rotational_symmetry_order(flange(5)))
    print("8-bolt flange symmetry order ->", rotational_symmetry_order(flange(8)))

    print("\n=== full verify vs Spec ===")
    spec = Spec(size=(100, 100, 10), holes={4: 6}, n_solids=1, symmetry=6, tol=0.5)
    print("correct 6-hole ->", verify(flange(6), spec) or "PASS")
    print("wrong 5-hole   ->", verify(flange(5), spec) or "PASS")

    print("\n=== measurement dump (6-hole flange) ===")
    for k, v in measure(flange(6)).items():
        print(f"  {k:16} {v}")
