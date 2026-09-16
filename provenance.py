"""
provenance.py — "which feature made this face?"

Fusion's *Find in Timeline*: right-click a face, and the browser jumps to the
feature that created it. TextCAD had only the forward direction (select a
feature -> highlight its geometry); this is the inverse, and on an AI-authored
tree it is the difference between a design you can read and one you can only
stare at. Click the floor of a pocket on a 73-feature remote shell and the tree
tells you: this came from `keypad_recess_sketch`, extruded by
`keypad_recess_tool`, applied by the cut `keypad_recess`.

HOW (all four rules were established by probing, not by reasoning):

  A face is a trimmed survivor. Later features can only ever TRIM a face, never
  grow it, so the feature that created a face is the EARLIEST one whose own
  solid already had a face that
     1. is the same surface type,
     2. lies on the same infinite surface (orientation-free key: a cutting
        tool's cylinder and the hole it leaves share one key),
     3. whose bounding box CONTAINS the queried face's bounding box, and
     4. actually contains an interior point of the queried face.
  Rule 3 is what separates "this face is a trimmed survivor of that one" from
  "that face merely shares my plane" — a design like esp32-remote has 490
  coplanar planar faces, so 1+2+4 alone is not an identity.

We answer with TWO features, because both are true and the user needs both:
  * origin      — where the GEOMETRY came from. For a pocket that is the tool
                  prism's extrude, whose sketch is the profile the user drew.
  * applied_by  — the feature that put it in THIS body (the cut/fuse). This is
                  what gets revealed in the tree, matching Fusion.

Cost (measured on esp32-remote, 79 features / 52 solids / 11180 faces):
enumerating and keying every intermediate face is ~0.6-1.8 s ONCE, so the
per-feature face index is cached on the Document and thrown away when the tree
goes stale. A query then costs milliseconds. Rebuilding that design takes
32-46 s, so the cache is not optional.
"""

from __future__ import annotations
import math

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.GeomAbs import GeomAbs_SurfaceType as ST
from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCP.ShapeAnalysis import ShapeAnalysis_Surface
from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_State
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt
from build123d import Face

import sketch as sk

ND = 4          # position/offset rounding (mm) for surface keys
NV = 5          # unit-vector component rounding
PAD = 1e-3      # bounding-box slack (mm): tessellation and boolean noise
TOL = 1e-5      # point-on-face tolerance (mm)


# ---------------------------------------------------------------------------
# Face enumeration + the surface key
#
# Shape.faces() is NOT cached and costs ~100 us/face; a raw TopExp_Explorer is
# 10-17x cheaper (1126 ms -> 105 ms over esp32-remote's 11180 faces). Bulk
# scanning uses the explorer; the PICKED face is resolved with part.faces() so
# its index matches the tagged mesh the viewport picked from.
# ---------------------------------------------------------------------------

def topo_faces(shape):
    """Every TopoDS_Face of a shape, cheaply."""
    exp = TopExp_Explorer(getattr(shape, "wrapped", shape),
                          TopAbs_ShapeEnum.TopAbs_FACE)
    out = []
    while exp.More():
        out.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return out


def _canon_dir(x, y, z):
    """Unit direction with a canonical SIGN (first non-zero component made
    positive). Face orientation flips across a boolean — a tool cylinder is
    FORWARD, the hole it leaves is REVERSED — and we must not care."""
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / n, y / n, z / n
    for c in (x, y, z):
        if abs(c) > 1e-9:
            if c < 0:
                x, y, z = -x, -y, -z
            break
    return (round(x, NV) + 0.0, round(y, NV) + 0.0, round(z, NV) + 0.0)


def _axis_foot(px, py, pz, dx, dy, dz):
    """The point where an infinite axis passes closest to the world origin —
    a canonical anchor, so *where along* the axis OCCT chose to park its
    reference location stops mattering."""
    n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    dx, dy, dz = dx / n, dy / n, dz / n
    t = px * dx + py * dy + pz * dz
    return (round(px - t * dx, ND) + 0.0, round(py - t * dy, ND) + 0.0,
            round(pz - t * dz, ND) + 0.0)


def surface_key(tface) -> tuple:
    """Identity of the INFINITE surface a face lies on: orientation-free and
    trim-free, so it survives every later boolean that only trims the face.

    NOT an identity for the face itself — a plate full of coplanar faces shares
    one key. It is the cheap filter; the bounding box and the containment test
    do the discriminating."""
    ad = BRepAdaptor_Surface(tface, True)
    t = ad.GetType()
    try:
        if t == ST.GeomAbs_Plane:
            pl = ad.Plane()
            ax = pl.Axis()
            d = ax.Direction()
            loc = ax.Location()
            nd = _canon_dir(d.X(), d.Y(), d.Z())
            # signed distance of the plane from the origin, in canonical dir
            off = nd[0] * loc.X() + nd[1] * loc.Y() + nd[2] * loc.Z()
            return ("PLANE", nd, round(off, ND) + 0.0)
        if t == ST.GeomAbs_Cylinder:
            cy = ad.Cylinder()
            ax = cy.Axis()
            d, loc = ax.Direction(), ax.Location()
            return ("CYL", _canon_dir(d.X(), d.Y(), d.Z()),
                    _axis_foot(loc.X(), loc.Y(), loc.Z(), d.X(), d.Y(), d.Z()),
                    round(cy.Radius(), ND) + 0.0)
        if t == ST.GeomAbs_Cone:
            co = ad.Cone()
            ax = co.Axis()
            d = ax.Direction()
            ap = co.Apex()
            # SemiAngle() is RADIANS here and can be negative — abs() it
            return ("CONE", _canon_dir(d.X(), d.Y(), d.Z()),
                    (round(ap.X(), ND) + 0.0, round(ap.Y(), ND) + 0.0,
                     round(ap.Z(), ND) + 0.0),
                    round(abs(co.SemiAngle()), NV) + 0.0)
        if t == ST.GeomAbs_Sphere:
            sp = ad.Sphere()
            c = sp.Location()
            # a sphere's axis is a construction artifact — key on centre+radius
            return ("SPHERE", (round(c.X(), ND) + 0.0, round(c.Y(), ND) + 0.0,
                               round(c.Z(), ND) + 0.0),
                    round(sp.Radius(), ND) + 0.0)
        if t == ST.GeomAbs_Torus:
            to = ad.Torus()
            ax = to.Axis()
            d, loc = ax.Direction(), ax.Location()
            return ("TORUS", _canon_dir(d.X(), d.Y(), d.Z()),
                    (round(loc.X(), ND) + 0.0, round(loc.Y(), ND) + 0.0,
                     round(loc.Z(), ND) + 0.0),
                    round(to.MajorRadius(), ND) + 0.0,
                    round(to.MinorRadius(), ND) + 0.0)
    except Exception:
        pass
    # BSPLINE / EXTRUSION / REVOLUTION / OFFSET: no analytic parameters to key
    # on. Fall back to the type alone and let bbox + containment decide.
    return (str(t).replace("GeomAbs_SurfaceType.GeomAbs_", ""),)


def _bbox(tface) -> tuple:
    """EXACT bounding box — never the triangulated one.

    BRepBndLib.Add_s(..., useTriangulation=True) silently switches to the
    face's cached triangulation once one exists. The viewport tessellates every
    body it draws, so in the real app the boxes changed the moment a design was
    rendered: the query face and its ancestor were then measured differently,
    rule 3's containment failed, and attribution slid down to a much later
    feature (on the impeller, 42 of 65 faces collapsed onto the final fuse).
    Unit tests never mesh, so they were all green while the app was wrong.
    Exact boxes cost more but do not depend on whether something drew the part.
    """
    box = Bnd_Box()
    BRepBndLib.Add_s(tface, box, False)
    if box.IsVoid():
        return None
    return box.Get()        # (xmin, ymin, zmin, xmax, ymax, zmax)


def _surface_type(tface) -> str:
    return str(BRepAdaptor_Surface(tface, True).GetType()) \
        .replace("GeomAbs_SurfaceType.GeomAbs_", "")


# ---------------------------------------------------------------------------
# A point that is really ON the face
#
# face.center() is a TRAP: for a planar face it is the centroid of mass, which
# for a ring or a face-with-a-hole falls INSIDE THE HOLE (probed: annulus and
# 40x40-plate-with-r19-hole both report not-on-face). So try it, then sample.
# position_at() takes NORMALISED u,v in 0..1 — raw UV bounds sample off-patch.
# ---------------------------------------------------------------------------

_UV = [(0.5, 0.5), (0.25, 0.25), (0.75, 0.75), (0.25, 0.75), (0.75, 0.25),
       (0.1, 0.5), (0.9, 0.5), (0.5, 0.1), (0.5, 0.9)]


def interior_point(face, extra=None):
    """A point guaranteed to lie inside the trimmed face (build123d Face).
    `extra` (e.g. the viewport's raycast hit) is tried first when given."""
    cands = []
    if extra is not None:
        cands.append(tuple(extra))
    try:
        c = face.center()
        cands.append((c.X, c.Y, c.Z))
    except Exception:
        pass
    for (u, v) in _UV:
        try:
            p = face.position_at(u, v)
            cands.append((p.X, p.Y, p.Z))
        except Exception:
            continue
    for p in cands:
        try:
            if face.is_inside(p, TOL):
                return p
        except Exception:
            continue
    try:                            # last resort: biggest triangle's centroid
        verts, tris = face.tessellate(0.05)
        best, bp = -1.0, None
        for (a, b, c) in tris:
            pa, pb, pc = verts[a], verts[b], verts[c]
            ar = ((pb - pa).cross(pc - pa)).length / 2
            if ar > best:
                best, bp = ar, (pa + pb + pc) * (1 / 3)
        if bp is not None:
            return (bp.X, bp.Y, bp.Z)
    except Exception:
        pass
    return None


def surface_gap(tface, x, y, z, tol: float = TOL) -> float:
    """How far a point lies from a face's underlying SURFACE, in mm — or `inf`
    when the kernel will not analyse the face, which refuses (a failed pick
    beats the wrong selection).

    A different question from OnFace's, and it ignores the trimming wires ON
    PURPOSE. build123d's `Face.center()` is the AREA CENTROID on a plane and
    the uv midpoint on a curved face, so a legitimate pick's centre can sit off
    the material — a washer's centroid is in its hole, a U-shaped face's is in
    the notch — but never off the surface (probes/face_of_revolve_probe.py §2,
    which measured 0.00000 for every face type). That makes this the test for
    "is the clicked point on THIS face's surface at all", which a bounding box
    cannot answer: a cylinder wall's box is the whole cube around the body."""
    try:
        sas = ShapeAnalysis_Surface(BRep_Tool.Surface_s(tface))
        sas.ValueOfUV(gp_Pnt(float(x), float(y), float(z)), max(tol, 1e-4))
        return float(sas.Gap())
    except Exception:
        return float("inf")


class OnFace:
    """Cached point-on-face test: 9 us per query after a ~150 us build, vs
    229 us for Face.is_inside every time. That 25x matters because a design
    full of coplanar faces (esp32-remote: 490 planes) puts HUNDREDS of
    candidates through this test on a single click.

    BOTH stages are mandatory. FClass2d alone classifies a (u,v) against the
    trimming wires, so any point that merely PROJECTS into the patch reports
    IN — probed: a point on r=9 tested IN on an r=10 cylinder. The Gap() check
    is what makes it a 3D test."""

    __slots__ = ("_sas", "_cls", "_dead")

    def __init__(self, tface):
        self._dead = False
        try:
            self._sas = ShapeAnalysis_Surface(BRep_Tool.Surface_s(tface))
            self._cls = BRepTopAdaptor_FClass2d(tface, 1e-7)
        except Exception:
            self._dead = True

    def __call__(self, x, y, z, tol=TOL) -> bool:
        if self._dead:
            return False
        try:
            uv = self._sas.ValueOfUV(gp_Pnt(x, y, z), tol)
            if self._sas.Gap() > max(tol, 1e-4):      # not ON the surface
                return False
            st = self._cls.Perform(uv)
            return st in (TopAbs_State.TopAbs_IN, TopAbs_State.TopAbs_ON)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Per-feature face index (cached on the Document, dropped when it goes stale)
# ---------------------------------------------------------------------------

def _index_of(part) -> list:
    """[[topods_face, surface_type, surface_key, bbox, OnFace|None]] for one
    solid. The tester is built lazily — only faces that survive the type, bbox
    and surface-key filters ever pay for one, and it is then reused by every
    later query on the same document."""
    rows = []
    for tf in topo_faces(part):
        bb = _bbox(tf)
        if bb is None:
            continue
        rows.append([tf, _surface_type(tf), surface_key(tf), bb, None])
    return rows


def _cache(doc) -> dict:
    """One face-index cache per Document, alive across queries.

    Freshness is per ENTRY, not per cache: every entry remembers the Part it
    was built from and is rebuilt when that object changes, which is exactly
    what a rebuild does (_mark_stale clears _parts and rebuild puts NEW Part
    objects in). So the dict never holds a stale index and never grows past one
    entry per feature. (An earlier version tokenised the whole cache on
    `id(doc._parts)` and compared it with `is` — two equal ints are not the
    same object, so the token never matched and the index was rebuilt on EVERY
    query: 22.8 ms per click instead of sub-millisecond.)"""
    cache = getattr(doc, "_prov_index", None)
    if cache is None:
        cache = {}
        doc._prov_index = cache
    return cache


def picked_faces(doc, fid, part):
    """The body's faces in `part.faces()` order — the SAME order _tagged_mesh
    used when it handed the viewport its face ids, so a picked index means the
    same face here. Cached: faces() is not memoised and costs ~100 us per face,
    which was the single biggest per-click cost before this."""
    cache = _cache(doc)
    ckey = ("__faces__", fid)
    hit = cache.get(ckey)
    if hit is not None and hit[0] is part:
        return hit[1]
    faces = part.faces()
    cache[ckey] = (part, faces)
    return faces


def feature_index(doc, fid):
    """Face index for one feature's cached solid, built once per rebuild."""
    part = doc._parts.get(fid)
    if part is None:
        return []
    cache = _cache(doc)
    hit = cache.get(fid)
    if hit is not None and hit[0] is part:
        return hit[1]
    rows = _index_of(part)
    cache[fid] = (part, rows)
    return rows


def _points(doc, fid):
    """One interior point per face of a feature's cached solid, in
    feature_index order — built once per rebuild, like the index (the host
    test needs one per face, and sampling a face is the costly part)."""
    part = doc._parts.get(fid)
    if part is None:
        return []
    cache = _cache(doc)
    ckey = ("__pts__", fid)
    hit = cache.get(ckey)
    if hit is not None and hit[0] is part:
        return hit[1]
    pts = [interior_point(Face(row[0])) for row in feature_index(doc, fid)]
    cache[ckey] = (part, pts)
    return pts


def edge_feature(doc, fid):
    """The feature a tree row names, for an edge tool — or the sentence."""
    f = next((x for x in doc.features if x.id == fid), None)
    if f is None:
        raise ValueError(f"no feature '{fid}' in this design — click a row of the tree")
    if f.op in sk.SKETCH_PRODUCERS:
        raise ValueError("a sketch has no edges — click the row of what it was extruded "
                         "into, a face, or an edge")
    return f


def feature_faces(doc, fid, body_id) -> set:
    """The forward direction of attribute_face, for one feature at once: the
    identities (blocks._shape_key) of the faces of body `body_id` that feature
    `fid` MADE. Fusion's Fillet takes a FEATURE as a selection, meaning the
    edges of the faces it created as they exist now — this is the faces half.

    A face of the body is the feature's when it is a trimmed survivor (this
    module's host test) of a face the feature's own output has and its input
    did not, AND no later body on this body's spine had lost it: a face the
    spine dropped and has again was remade, and belongs to whatever remade it
    (_later_spine); `document.delta_features` says what output and input mean (the
    tree's folding rule — a pulled tool with a folded cut is that cut's before
    and after; a creator or a placement is a whole body, so every face is its).
    Measured in probes/feature_edges_probe.py: a cut's row is its pocket's
    five faces, the base plate's row its six faces AS THEY ARE NOW (the top
    with the pocket's opening in it), a fillet's row its bands; ~40 ms on a
    pocketed box with the indexes and points cached per rebuild.

    Raises a sentence for a row that is not a feature of this body: a sketch,
    an unknown or struck-out row, one outside the body's history, an unbuilt one."""
    edge_feature(doc, fid)
    before_id, after_id = doc.delta_features(fid)
    if after_id != body_id and after_id not in doc.ancestors(body_id):
        raise ValueError(f"'{fid}' is not part of {body_id}'s history — click a feature of "
                         f"the body the edges are on")
    if doc._parts.get(after_id) is None or (before_id and doc._parts.get(before_id) is None):
        raise ValueError(f"'{fid}' is not built (failed upstream?) — fix it first")
    before_rows = feature_index(doc, before_id) if before_id else []
    new_rows = []
    for row, pt in zip(feature_index(doc, after_id), _points(doc, after_id)):
        if pt is None:
            continue
        if before_rows and _hosts(before_rows, row[1], row[2], row[3], pt, len(row[2]) > 1):
            continue                         # the input had it already: not this feature's
        new_rows.append(row)
    keys = set()
    later = _later_spine(doc, fid, body_id)          # the newest-wins evidence
    for row, pt in zip(feature_index(doc, body_id), _points(doc, body_id)):
        if pt is None:
            continue
        analytic = len(row[2]) > 1
        if not _hosts(new_rows, row[1], row[2], row[3], pt, analytic):
            continue
        # NEWEST WINS. A face that a LATER body on this spine did NOT have was
        # remade after `fid`, so it belongs to whatever remade it. A boss fused
        # flush into a pocket lies on the base plate's own plane and inside its
        # bbox, so the plate's row claimed the boss's rim too and a radius
        # rounded it: 7 faces / 20 edges instead of 6 / 16
        # (probes/feature_faces_newest_probe.py §1).
        if any(not _hosts(rows, row[1], row[2], row[3], pt, analytic)
               for rows in later):
            continue
        keys.add(hash(row[0]))
    return keys


# ---------------------------------------------------------------------------
# The tree walk
# ---------------------------------------------------------------------------

def _solid_features(doc, upto=None):
    """Feature ids in BUILD ORDER whose cached output is a solid. `upto` stops
    at (and includes) that feature — nothing built after the picked body can
    have created one of its faces."""
    out = []
    for f in doc.features:
        part = doc._parts.get(f.id)
        if part is not None and f.op not in sk.SKETCH_PRODUCERS \
                and not sk.is_sketch(part):
            out.append(f.id)
        if upto is not None and f.id == upto:
            break
    return out


def _ancestors(doc, fid):
    """fid plus every feature it transitively consumes (tools included)."""
    seen, stack = set(), [fid]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        try:
            stack.extend(doc.get(cur).inputs)
        except KeyError:
            continue
    return seen


def _spine(doc, fid):
    """The inputs[0] chain back from a feature — the bodies this one IS, as
    opposed to the tools it merely consumed. A face enters the final part on
    its spine; it originates anywhere in the ancestry."""
    out, cur = [], fid
    while cur:
        out.append(cur)
        try:
            f = doc.get(cur)
        except KeyError:
            break
        cur = f.inputs[0] if f.inputs else None
    return out


def _later_spine(doc, fid, body_id) -> list:
    """The face indexes of the bodies this body's SPINE passes through AFTER
    `fid`, in build order — the newest-wins tie-break's evidence.

    [] when `fid` is not on that spine: a TOOL body's row (a moved prism, a
    disc that got fused) answers for its own geometry and must not be
    out-voted by the boolean that consumed it. Restricting this to the spine
    is not optional — measured over the whole ancestry it wiped every tool
    row instead (probes/feature_faces_newest_probe.py: the pocketed box's
    `tm` went from 12 edges to none)."""
    spine, anc = set(_spine(doc, body_id)), _ancestors(doc, body_id)
    walk = [f for f in _solid_features(doc, upto=body_id)
            if f in spine and f in anc]
    if fid not in walk:
        return []
    return [feature_index(doc, later) for later in walk[walk.index(fid) + 1:]
            if doc._parts.get(later) is not None]


def _hosts(rows, stype, key, qbb, point, analytic: bool):
    """Does this feature's solid have a face that the queried face is a trimmed
    survivor of? (see the module docstring for why bbox containment is the
    discriminator)"""
    x, y, z = point
    for row in rows:
        if row[1] != stype:
            continue
        bb = row[3]
        # 3. the creator's face must still BOUND the survivor
        if not (bb[0] - PAD <= qbb[0] and bb[1] - PAD <= qbb[1]
                and bb[2] - PAD <= qbb[2] and bb[3] + PAD >= qbb[3]
                and bb[4] + PAD >= qbb[4] and bb[5] + PAD >= qbb[5]):
            continue
        # 2. same infinite surface (skipped for spline-ish faces with no key)
        if analytic and row[2] != key:
            continue
        # 4. and it really contains the point
        if row[4] is None:
            row[4] = OnFace(row[0])
        if row[4](x, y, z):
            return True
    return False


def _sketch_behind(doc, fid, depth=0):
    """The sketch a solid feature descends from (the profile the user drew)."""
    if depth > 8:
        return None
    try:
        f = doc.get(fid)
    except KeyError:
        return None
    if f.op in sk.SKETCH_PRODUCERS:
        return fid
    for dep in f.inputs:
        got = _sketch_behind(doc, dep, depth + 1)
        if got:
            return got
    return None


SKETCH_CONSUMERS = {"extrude", "revolve", "loft", "sweep", "extrude_face", "revolve_face"}


def _extrude_behind(doc, fid, depth=0):
    """The feature that turned a sketch into this solid."""
    if depth > 8:
        return None
    try:
        f = doc.get(fid)
    except KeyError:
        return None
    if f.op in SKETCH_CONSUMERS:
        return fid
    for dep in f.inputs:
        got = _extrude_behind(doc, dep, depth + 1)
        if got:
            return got
    return None


def _area_matches(face, area) -> bool:
    """Is this face still the size the pick recorded? True when the pick
    carried no size (nothing to check), or when the kernel will not measure the
    face — the size may only ever confirm an answer, never veto every one."""
    if area is None:
        return True
    try:
        a0 = float(area)
        return abs(face.area - a0) <= max(0.5, 0.01 * a0)
    except Exception:
        return True


def attribute_face(doc, body_id=None, face_index=None, point=None,
                   center=None, area=None) -> dict:
    """Which feature created the picked face?

    body_id/face_index come straight from the viewport pick (the tagged mesh
    ids). center+area, when given, verify that the index still points at the
    same face — the document may have been rebuilt since the mesh was sent.
    `point` is the raycast hit, used as the preferred interior sample.

    Never raises for geometry: an unattributable face returns
    {"feature": None, "reason": ...} so the UI can say so honestly.
    """
    if not doc.features:
        return {"feature": None, "reason": "the design is empty"}
    part = doc._parts.get(body_id) if body_id else None
    resolved_body = body_id if part is not None else None
    if part is None:
        part = doc.result()
        rf = doc._result_feature()
        resolved_body = rf.id if rf else None
    if part is None:
        return {"feature": None,
                "reason": "nothing is built — rebuild the design first"}

    # A NEGATIVE INDEX IS THE IMPORTED-MESH PSEUDO-FACE (studio.MESH_FACE_ID).
    # A body whose faces are all single triangles is drawn as ONE untagged
    # mesh, so every click on it arrives as face -1 with no centre — and the
    # "could not resolve" sentence below told the user to click again, for
    # ever. Say what is actually true, the way Measure was made to (3ce97a3).
    if face_index is not None and face_index < 0:
        return {"feature": None, "body": resolved_body,
                "reason": "this body is drawn as one mesh (an imported STL has "
                          "no named faces), so there is no face to trace — open "
                          "its row in the tree instead"}

    # -- resolve the picked face --------------------------------------------
    faces = picked_faces(doc, resolved_body, part)   # tagged-mesh order
    face = None
    if face_index is not None and face_index < len(faces):
        cand = faces[face_index]
        # the index may be stale after a rebuild; the area says so
        face = cand if _area_matches(cand, area) else None
    if face is None and center is not None:     # fall back to geometry
        cx, cy, cz = [float(v) for v in center]
        near = []
        for f in faces:
            try:
                c = f.center()
            except Exception:
                continue
            d = (c.X - cx) ** 2 + (c.Y - cy) ** 2 + (c.Z - cz) ** 2
            if d <= 1.0:
                near.append((d, f))
        # NEAREST IS NOT AN IDENTITY when two faces sit in the same place: a
        # round pocket with a flush pad in it has an outer top of 2343.36 mm2
        # and a pad top of 113.10 whose centroids are BOTH (0, 0, 10) — and a
        # centre arrives rounded to 2 decimals, so they tie exactly and the
        # kernel's own order decided. The pick already says which it was; the
        # area is the same fact blocks.resolve_face separates them by. It
        # narrows only when something matches, so a face the design has since
        # resized still gets the nearest-centre answer it got before.
        sized = [r for r in near if _area_matches(r[1], area)]
        near = sized or near
        if near:
            face = min(near, key=lambda r: r[0])[1]
    if face is None:
        return {"feature": None, "body": resolved_body,
                "reason": "could not resolve which face was picked "
                          "(the design changed — click it again)"}

    tf = face.wrapped
    stype = _surface_type(tf)
    key = surface_key(tf)
    analytic = len(key) > 1         # spline-ish faces have no analytic key
    qbb = _bbox(tf)
    pt = interior_point(face, extra=point)
    if pt is None or qbb is None:
        return {"feature": None, "body": resolved_body,
                "reason": "this face has no sampleable interior"}

    # -- walk the ancestry in build order ----------------------------------
    pool = [fid for fid in _solid_features(doc, upto=resolved_body)
            if fid in _ancestors(doc, resolved_body)] \
        if resolved_body else _solid_features(doc)
    # ONE pass finds both: the earliest ancestor that hosts the face (where the
    # geometry came from) and the earliest feature on this body's own spine
    # that hosts it (where it entered this body). Two passes doubled the cost
    # of every click for nothing.
    spine = set(_spine(doc, resolved_body)) if resolved_body else set()
    # WHERE THIS BODY LAST DID NOT HAVE THE FACE. Rule 3 (bbox containment) is
    # an "is a trimmed survivor of" test, and coplanar geometry can satisfy it
    # by accident: the top of a boss fused flush into a pocket lies on the base
    # plate's own plane and inside its bbox, so the earliest-ancestor walk
    # credited the PLATE with it — and said so with high confidence. A face the
    # spine once did not have was remade after that, so nothing built earlier
    # can be its origin (measured: origin b -> sm, applied_by b -> the fuse;
    # probes/feature_faces_newest_probe.py §2b).
    first = 0
    for i, fid in enumerate(pool):
        if fid in spine and not _hosts(feature_index(doc, fid), stype, key,
                                       qbb, pt, analytic):
            first = i + 1
    origin = applied_by = None
    for fid in pool[first:]:
        if not _hosts(feature_index(doc, fid), stype, key, qbb, pt, analytic):
            continue
        if origin is None:
            origin = fid
        if fid in spine:
            applied_by = fid
            break               # the spine hit is always at or after origin

    if origin is None:
        # every candidate rejected: report the body itself rather than nothing
        return {"feature": applied_by or resolved_body, "body": resolved_body,
                "face": {"type": stype, "area": round(face.area, 2)},
                "origin": None, "applied_by": applied_by,
                "confidence": "low",
                "reason": "no earlier feature bounds this face — it is new here"}

    sketch_id = _sketch_behind(doc, origin)
    extrude_id = _extrude_behind(doc, origin)
    reveal = applied_by or origin
    return {
        "feature": reveal,          # what the tree should reveal
        "op": doc.get(reveal).op,
        "origin": origin,           # where the geometry came from
        "origin_op": doc.get(origin).op,
        "applied_by": applied_by,   # the boolean that put it in this body
        "applied_op": doc.get(applied_by).op if applied_by else None,
        "sketch": sketch_id,
        "extrude": extrude_id,
        "body": resolved_body,
        "face": {"type": stype, "area": round(face.area, 2),
                 "index": face_index},
        "chain": _chain(doc, origin, applied_by, sketch_id, extrude_id),
        "confidence": "high" if analytic else "medium",
        "explanation": _explain(doc, reveal, origin, applied_by, sketch_id,
                                extrude_id, stype),
    }


def _chain(doc, origin, applied_by, sketch_id, extrude_id) -> list:
    """The lineage to show in the UI, sketch first (creation order)."""
    out, seen = [], set()
    for fid, role in ((sketch_id, "sketch"), (extrude_id, "extrude"),
                      (origin, "origin"), (applied_by, "applied")):
        if fid and fid not in seen:
            seen.add(fid)
            try:
                out.append({"id": fid, "op": doc.get(fid).op, "role": role})
            except KeyError:
                continue
    return out


def _explain(doc, reveal, origin, applied_by, sketch_id, extrude_id,
             stype) -> str:
    what = "flat face" if stype == "PLANE" else f"{stype.lower()} face"
    bits = [f"This {what} was created by '{origin}' ({doc.get(origin).op})"]
    if sketch_id and sketch_id != origin:
        bits.append(f"from sketch '{sketch_id}'")
    if extrude_id and extrude_id not in (origin, sketch_id):
        bits.append(f"extruded by '{extrude_id}'")
    if applied_by and applied_by != origin:
        bits.append(f"and applied to this body by '{applied_by}' "
                    f"({doc.get(applied_by).op})")
    return ", ".join(bits) + "."
