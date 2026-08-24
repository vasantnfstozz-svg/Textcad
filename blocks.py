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
import functools
import math
import os
import re
import struct
import tempfile
from pathlib import Path
from build123d import (
    Box, Cylinder, Sphere, Cone, Pos, PolarLocations, Locations,
    BuildSketch, RegularPolygon, BuildLine, Polyline, Spline, make_face,
    trace, extrude, revolve, Axis, Plane, Part, Mesher, Solid, Compound,
    mirror as _b3d_mirror, scale as _b3d_scale,
    fillet as _b3d_fillet, chamfer as _b3d_chamfer, offset as _b3d_offset,
)
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid

_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}
_PLANES = {"XY": Plane.XY, "XZ": Plane.XZ, "YZ": Plane.YZ}


# ---------------------------------------------------------------------------
# Primitive solids
# ---------------------------------------------------------------------------

def plate(width: float, depth: float, thickness: float) -> Part:
    """A rectangular plate centered on the origin (X=width, Y=depth, Z=thickness)."""
    return Box(width, depth, thickness)


def disc(radius: float, thickness: float) -> Part:
    """A solid cylinder (disc) centered on the origin, axis along Z."""
    return Cylinder(radius=radius, height=thickness)


def ball(radius: float) -> Part:
    """A solid sphere centered on the origin. Great for domes (cut in half
    with a box), rounded ends, knobs, and stylized organic shapes."""
    return Sphere(radius=radius)


def cone(bottom_radius: float, top_radius: float, height: float) -> Part:
    """A (truncated) cone centered on the origin, axis along Z — spans
    -height/2 to +height/2. top_radius=0 gives a sharp point. Use for tapers,
    funnels, nose shapes, stylized bodies."""
    return Cone(bottom_radius=bottom_radius, top_radius=top_radius,
                height=height)


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
# Transform / finishing operations (E1) — take a part, return a new part
# ---------------------------------------------------------------------------

def rotate(part: Part, axis: str = "Z", angle_deg: float = 90.0) -> Part:
    """Rotate a part about the X, Y or Z axis (through the origin). The way to
    lay a cylinder on its side: rotate(wheel, "X", 90)."""
    if axis not in _AXES:
        raise ValueError('rotate: axis must be "X", "Y" or "Z"')
    return part.rotate(_AXES[axis], angle_deg)


def mirror_copy(part: Part, plane: str = "YZ") -> Part:
    """The MIRRORED COPY of a part about a principal plane ("XY", "XZ", "YZ").
    Returns only the copy — fuse it with the original for a symmetric pair."""
    if plane not in _PLANES:
        raise ValueError('mirror: plane must be "XY", "XZ" or "YZ"')
    return _b3d_mirror(part, about=_PLANES[plane])


def scale_uniform(part: Part, factor: float) -> Part:
    """Uniformly scale a part about the origin (2 = double size)."""
    if factor <= 0:
        raise ValueError("scale: factor must be positive")
    return _b3d_scale(part, by=factor)


def linear_pattern(feature: Part, count: int, dx: float = 0.0,
                   dy: float = 0.0, dz: float = 0.0) -> Part:
    """Union of `count` copies of a feature stepped by (dx, dy, dz) each time
    (copy 0 stays in place). E.g. a row of 4 wheels: count=4, dx=30."""
    if count < 1:
        raise ValueError("linear_pattern: count must be >= 1")
    parts = [Pos(i * dx, i * dy, i * dz) * feature for i in range(count)]
    while len(parts) > 1:
        parts = [parts[i] + parts[i + 1] if i + 1 < len(parts) else parts[i]
                 for i in range(0, len(parts), 2)]
    return parts[0]


_EDGE_RULES = ("all", "top", "bottom", "vertical", "horizontal")


def _pick_edges(part: Part, which: str):
    edges = part.edges()
    if which == "all":
        return edges
    if which == "top":
        return edges.group_by(Axis.Z)[-1]
    if which == "bottom":
        return edges.group_by(Axis.Z)[0]
    if which == "vertical":
        # edges parallel to Z — the 4 corner edges of a box (round-the-corners)
        picked = edges.filter_by(Axis.Z)
        if not picked:
            raise ValueError('no "vertical" edges (none run parallel to Z)')
        return picked
    if which == "horizontal":
        # edges lying flat (parallel to X or Y) — top+bottom rims
        picked = edges.filter_by(Axis.X) + edges.filter_by(Axis.Y)
        if not picked:
            raise ValueError('no "horizontal" edges (none parallel to X or Y)')
        return picked
    raise ValueError(f'edges must be one of {", ".join(_EDGE_RULES)}')


def fillet_edges(part: Part, radius: float, edges: str = "all") -> Part:
    """Round edges with a radius. `edges`: "all", "top", "bottom", "vertical"
    (the 4 upright corner edges — for rounding the corners of a box/enclosure)
    or "horizontal" (the flat top+bottom rims). The radius must be smaller than
    half the thickness of the adjacent material."""
    return _b3d_fillet(_pick_edges(part, edges), radius=radius)


def chamfer_edges(part: Part, length: float, edges: str = "all") -> Part:
    """Cut a flat 45-degree bevel on edges. `edges`: "all", "top", "bottom",
    "vertical" or "horizontal" (see fillet_edges)."""
    return _b3d_chamfer(_pick_edges(part, edges), length=length)


def shell_out(part: Part, thickness: float, open_face: str = "top") -> Part:
    """Hollow a part into walls of `thickness`. open_face "top"/"bottom" removes
    that face (an open container, e.g. a cup); "none" keeps it fully closed."""
    if thickness <= 0:
        raise ValueError("shell: thickness must be positive")
    if open_face == "none":
        return _b3d_offset(part, amount=-thickness)
    if open_face in ("top", "bottom"):
        idx = -1 if open_face == "top" else 0
        face = part.faces().sort_by(Axis.Z)[idx]
        return _b3d_offset(part, amount=-thickness, openings=face)
    raise ValueError('shell: open_face must be "top", "bottom" or "none"')


# ---------------------------------------------------------------------------
# Mesh import (STL from outside sources)
# ---------------------------------------------------------------------------

IMPORTS_DIR = Path(__file__).parent / "imports"   # UI uploads land here
MAX_STL_TRIANGLES = 20_000                        # keeps rebuild + display usable


def _stl_triangles(data: bytes) -> tuple[str, int]:
    """('ascii'|'binary', triangle count) without a full parse. ASCII is
    detected by content, not just the 'solid' prefix — some binary exporters
    put 'solid' in the 80-byte header too, so the size formula decides."""
    head = data[:80].lstrip()
    if head.startswith(b"solid") and b"facet" in data:
        return "ascii", data.count(b"facet normal")
    if len(data) >= 84:
        (n,) = struct.unpack_from("<I", data, 80)
        if len(data) >= 84 + 50 * n:
            return "binary", n
    if head.startswith(b"solid"):
        return "ascii", 0
    raise ValueError("import_stl: not an STL file (neither binary nor ascii STL)")


def _ascii_stl_to_binary(data: bytes) -> bytes:
    """lib3mf's STL reader only accepts BINARY STL — ascii files fail with a
    cryptic 'Reading from a stream was not possible'. Convert up front."""
    verts = re.findall(
        rb"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", data)
    if not verts or len(verts) % 3:
        raise ValueError("import_stl: malformed ascii STL "
                         "(vertex count is not a multiple of 3)")
    out = bytearray(b"\0" * 80)
    out += struct.pack("<I", len(verts) // 3)
    for i in range(0, len(verts), 3):
        out += struct.pack("<3f", 0.0, 0.0, 0.0)   # normals recomputed on read
        for v in verts[i:i + 3]:
            out += struct.pack("<3f", float(v[0]), float(v[1]), float(v[2]))
        out += struct.pack("<H", 0)
    return bytes(out)


def _stl_bytes_to_solids(data: bytes) -> tuple[list, int]:
    """One binary STL through lib3mf into closed Solids. Returns
    (solids, open_shell_count). A shape that is already a valid positive
    Solid is taken AS-IS — exploding it per shell would split a hollow part
    into an outer solid plus a phantom cavity solid."""
    tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        try:
            shapes = Mesher().read(tmp.name)
        except Exception as e:   # lib3mf errors do NOT derive from RuntimeError
            raise ValueError(f"import_stl: could not read the STL ({e})") from e
    finally:
        tmp.close()
        os.unlink(tmp.name)

    solids, open_shells = [], 0
    for shp in shapes:
        try:
            if isinstance(shp, Solid) and shp.volume > 0 and shp.is_valid():
                solids.append(shp)
                continue
        except Exception:
            pass
        for sh in shp.shells():
            if not BRep_Tool.IsClosed_s(sh.wrapped):
                open_shells += 1
                continue
            sol = Solid(BRepBuilderAPI_MakeSolid(sh.wrapped).Solid())
            if sol.volume < 0:               # inverted winding — flip it
                sol = Solid(sol.wrapped.Reversed())
            solids.append(sol)
    return solids, open_shells


@functools.lru_cache(maxsize=8)
def _read_stl_solids(path_str: str, mtime_ns: int, size: int) -> tuple:
    """Read (+ auto-repair) an STL into (tuple of closed Solids, report dict).
    Cached on (path, mtime, size): Document.rebuild() re-evaluates every
    feature on every edit, and re-parsing a big mesh each time would crawl.
    Downstream ops never mutate OCCT shapes, so sharing the cached Solids
    across rebuilds is safe.

    Clean meshes under MAX_STL_TRIANGLES go straight to the kernel. Anything
    dirty (duplicated interface walls, pinched edges, too dense) goes through
    meshrepair's heal/split/remesh/decimate pipeline first — feeding a broken
    mesh straight to OCCT produced a 6-minute read returning an EMPTY invalid
    solid (probed on a real Fusion assembly export)."""
    import meshrepair

    data = Path(path_str).read_bytes()
    fmt, ntri = _stl_triangles(data)
    if ntri == 0:
        raise ValueError("import_stl: the file contains no triangles")
    if ntri > meshrepair.MAX_INPUT_TRIANGLES:
        raise ValueError(
            f"import_stl: mesh has {ntri:,} triangles — beyond the "
            f"{meshrepair.MAX_INPUT_TRIANGLES:,} import limit even for "
            "auto-repair. Decimate it in a mesh tool (Blender/MeshLab) "
            "and re-export.")
    if fmt == "ascii":
        data = _ascii_stl_to_binary(data)

    verts, faces = meshrepair.parse_binary_stl(data)
    boundary, overshared = meshrepair.edge_counts(faces)
    dupes = bool(meshrepair.duplicate_triangles(faces).any())
    report = {"input_triangles": ntri, "output_triangles": ntri,
              "healed_wall_triangles": 0, "remeshed_bodies": 0,
              "repaired": False}

    if ntri <= MAX_STL_TRIANGLES and not (boundary or overshared or dupes):
        pieces = [data]
    else:
        try:
            pieces, rep = meshrepair.repair_stl_mesh(data)
        except ValueError as e:
            raise ValueError(f"import_stl: {e}") from e
        report.update(rep)
        report["repaired"] = True

    solids, open_shells = [], 0
    for piece in pieces:
        s, o = _stl_bytes_to_solids(piece)
        solids.extend(s)
        open_shells += o
    if open_shells:
        raise ValueError(
            f"import_stl: the mesh is not watertight ({open_shells} open "
            f"shell(s), {len(solids)} closed) — a solid needs a fully closed "
            "surface. Repair it in a mesh tool and re-export.")
    if not solids:
        raise ValueError("import_stl: no solid found in the mesh")
    report["bodies"] = len(solids)
    return tuple(solids), report


def _resolve_stl_path(file: str) -> Path:
    if not isinstance(file, str) or not file.strip():
        raise ValueError("import_stl: file must be a filename or path")
    path = Path(file)
    if not path.is_absolute():
        path = IMPORTS_DIR / file
    if not path.is_file():
        raise ValueError(f"import_stl: file not found: {path}")
    return path


def import_stl(file: str, scale: float = 1.0) -> Part:
    """Import an external STL mesh file as a solid body. `file` is an absolute
    path, or the name of a file in the imports/ folder (where UI uploads
    land). The triangles become a faceted solid; broken meshes (duplicated
    interface walls, pinched edges, too dense) are auto-repaired via
    meshrepair — meshes with actual holes are refused. STL units are read as
    mm; `scale` resizes on import (e.g. 25.4 for a file modeled in inches)."""
    if not isinstance(scale, (int, float)) or scale <= 0:
        raise ValueError("import_stl: scale must be a positive number")
    path = _resolve_stl_path(file)
    st = path.stat()
    solids, _report = _read_stl_solids(str(path), st.st_mtime_ns, st.st_size)
    # NOTE: Part(solid.wrapped) reports volume 0 (probed) — never wrap that
    # way. Multi-body imports become a Compound, NOT a fuse: assembly exports
    # overlap/touch, and fusing two 10k-triangle meshes can hang the kernel.
    part = solids[0] if len(solids) == 1 else Compound(children=list(solids))
    if scale != 1.0:
        part = _b3d_scale(part, by=float(scale))
    return part


def import_stl_report(file: str) -> dict:
    """The repair/import report for an STL (free: served from the same cache
    as import_stl). Keys: input_triangles, output_triangles, bodies,
    healed_wall_triangles, remeshed_bodies, repaired."""
    path = _resolve_stl_path(file)
    st = path.stat()
    return _read_stl_solids(str(path), st.st_mtime_ns, st.st_size)[1]


# ---------------------------------------------------------------------------
# Registry — the exact names exposed to the LLM's script namespace
# ---------------------------------------------------------------------------

EXPORTS = {
    "plate": plate,
    "disc": disc,
    "ball": ball,
    "cone": cone,
    "tube": tube,
    "polygon_plate": polygon_plate,
    "hex_plate": hex_plate,
    "revolve_profile": revolve_profile,
    "curved_blade": curved_blade,
    "with_center_hole": with_center_hole,
    "with_bolt_circle": with_bolt_circle,
    "polar_pattern": polar_pattern,
    "rotate": rotate,
    "mirror": mirror_copy,
    "scale": scale_uniform,
    "linear_pattern": linear_pattern,
    "fillet": fillet_edges,
    "chamfer": chamfer_edges,
    "shell": shell_out,
    "import_stl": import_stl,
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
    from build123d import export_stl as _export_stl

    # import_stl needs a real file: round-trip a box through STL
    _selftest_stl = Path(tempfile.gettempdir()) / "_blocks_selftest.stl"
    _export_stl(Box(20, 10, 5), str(_selftest_stl))

    cases = {
        "import_stl (box roundtrip)": import_stl(str(_selftest_stl)),
        "plate":        plate(40, 30, 5),
        "disc":         disc(20, 8),
        "ball":         ball(15),
        "cone":         cone(20, 8, 25),
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
