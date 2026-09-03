"""Extrude + taper run over the whole gauntlet corpus.

The bug that motivated this file: extruding a picked face with a TINY taper
(0.3 deg = 0.2mm over 38mm) failed with a raw Standard_NoSuchObject on a
pentagon face of a fused body, while the SAME face tapered the other way
worked. It passed every box-shaped test we had.
"""
import math

import pytest


def test_tilted_face_taper_heals_intermittent_invalids():
    """User repro 2026-08-05: narrowing taper on a face extruded from the
    tilted wall of a tapered body failed at 10 and 31 deg but built at
    5/20/40 — OCCT intermittently flags the loft result invalid. ShapeFix
    heals it (probed: identical volume); the whole sweep must now be ok."""
    from document import Document
    for taper in (-5.0, -10.0, -20.0, -31.0, -40.0):     # Fusion sign: negative narrows
        doc = Document(name="repro")
        doc.add("sk", "sketch", {"plane": "XY", "offset": 0, "entities": [
            {"kind": "rectangle", "mode": "add", "x": 16.25, "y": 46.25,
             "w": 37.5, "h": 32.5, "rotation": 0}]})
        doc.add("e1", "extrude", {"amount": 94.12, "taper": -31.3}, ["sk"])
        doc.add("e2", "extrude_face",
                {"face_center": [16.25, 36.05, 9.96],
                 "face_normal": [0, -0.854, 0.52], "amount": 71.78}, ["e1"])
        doc.add("j1", "fuse", {}, ["e1", "e2"])
        doc.add("e3", "extrude_face",
                {"face_center": [16.25, 56.45, 9.96],
                 "face_normal": [0, 0.854, 0.52], "amount": 97.32,
                 "taper": taper}, ["j1"])
        doc.add("j2", "fuse", {}, ["j1", "e3"])
        doc.rebuild()
        f = doc.get("e3")
        assert f.status == "ok", (taper, f.problems)
from build123d import Edge, Kind, Line, Spline, Wire

import sketch as sk
from gauntlet import BODIES, assert_op, face_edge_kinds, planar_faces

TAPERS = (-2.0, -0.3, 0.0, 0.3, 2.0)
FLIPS = (False, True)


@pytest.mark.parametrize("body_name", sorted(BODIES))
def test_extrude_face_taper_gauntlet(body_name):
    """Every planar face of every corpus body, tapered both ways, must either
    build a healthy solid or refuse with a friendly message — never a kernel
    exception, never a crash."""
    solid = BODIES[body_name]()
    faces = planar_faces(solid)
    assert faces, f"{body_name}: no planar faces to test"
    for idx, _face, center, normal in faces:
        for taper in TAPERS:
            for flip in FLIPS:
                assert_op(
                    f"{body_name}.face{idx} taper={taper} flip={flip}",
                    lambda t=taper, f=flip, c=center, n=normal: sk.extrude_face(
                        solid, c, n, amount=25, taper=t, flip=f))


def test_seam_face_tapers_both_ways():
    """THE regression: a face carrying a straight BSPLINE seam edge (left by
    fusing a tapered body) used to work for one taper sign and raise a raw
    kernel error for the other. Both directions must now build."""
    solid = BODIES["fused_taper_seam"]()
    seam = [(i, f, c, n) for i, f, c, n in planar_faces(solid)
            if any(k != "LINE" for k in face_edge_kinds(f))]
    assert seam, "corpus body no longer produces a BSPLINE seam face"

    idx, _f, center, normal = seam[0]
    vols = {}
    for taper in (-2.0, -0.3, 0.3, 2.0):
        solid_out = assert_op(
            f"seam face{idx} taper={taper}",
            lambda t=taper: sk.extrude_face(solid, center, normal,
                                            amount=38.44, taper=t),
            allow_failure=False)          # these MUST succeed, not just refuse
        vols[taper] = solid_out.volume

    # narrowing (NEGATIVE, Fusion sign) removes material, flaring adds it —
    # monotonic in the taper
    assert vols[-2.0] < vols[-0.3] < vols[0.3] < vols[2.0], vols


def test_straight_bspline_edge_is_straightened():
    """_straighten_face rebuilds straight-but-BSPLINE edges as LINEs. Without
    it, OCCT's offset silently returns a DEGENERATE wire (measured: a 4-edge
    rectangle came back as 1 edge of length 50.4 instead of 161.6)."""
    edges = [Line((0, 0), (50, 0)).edge(), Line((50, 0), (50, 30)).edge(),
             Spline([(50, 30), (25, 30), (0, 30)]).edge(),
             Line((0, 30), (0, 0)).edge()]
    wire = Wire(edges)
    assert [e.geom_type.name for e in wire.edges()].count("BSPLINE") == 1

    # the raw kernel really does produce garbage in ONE direction
    bad = wire.offset_2d(0.2, kind=Kind.INTERSECTION)
    assert len(bad.edges()) < 4, "kernel behaviour changed — revisit the fix"

    import build123d as b3d
    fixed = sk._straighten_face(b3d.Face(wire))
    assert all(e.geom_type.name == "LINE" for e in fixed.outer_wire().edges())
    assert math.isclose(fixed.area, 1500.0, rel_tol=1e-6)
    for d in (-3.0, -0.2, 0.2, 3.0):       # now every direction offsets right
        assert len(fixed.outer_wire().offset_2d(
            d, kind=Kind.INTERSECTION).edges()) == 4


def test_straighten_keeps_real_curves():
    """a genuinely curved edge must NOT be flattened into a line"""
    import build123d as b3d
    edges = [Line((0, 0), (50, 0)).edge(), Line((50, 0), (50, 30)).edge(),
             Spline([(50, 30), (25, 45), (0, 30)]).edge(),   # a real arch
             Line((0, 30), (0, 0)).edge()]
    face = b3d.Face(Wire(edges))
    kept = sk._straighten_face(face)
    assert any(e.geom_type.name != "LINE" for e in kept.outer_wire().edges())
    assert math.isclose(kept.area, face.area, rel_tol=1e-9)


def test_taper_failure_message_is_honest():
    """A failure must say what to change — and must not blame a 'too steep'
    taper for a 0.2mm offset, which was the old (wrong) explanation."""
    solid = BODIES["plate_with_hole"]()
    idx, _f, center, normal = max(planar_faces(solid),
                                  key=lambda t: t[1].area)
    try:
        sk.extrude_face(solid, center, normal, amount=25, taper=-80)    # steep NARROWING
    except ValueError as e:
        msg = str(e)
        assert "taper" in msg.lower()
        assert any(w in msg.lower() for w in ("smaller", "shorter", "other way"))
    # (building successfully is also acceptable — the contract is "not a crash")


def test_kernel_errors_never_reach_the_caller():
    """OCP exceptions derive from Exception, NOT RuntimeError — an
    `except RuntimeError` barrier silently let Standard_NoSuchObject through
    to the feature tree. Any taper failure must be a ValueError."""
    from OCP.Standard import Standard_NoSuchObject, Standard_Failure
    assert not issubclass(Standard_NoSuchObject, RuntimeError)
    assert not issubclass(Standard_Failure, RuntimeError)

    solid = BODIES["fused_taper_seam"]()
    for idx, _f, center, normal in planar_faces(solid):
        for taper in (-45.0, 45.0):        # extreme: many of these must refuse
            try:
                sk.extrude_face(solid, center, normal, amount=60, taper=taper)
            except ValueError:
                pass                        # the only allowed failure type
            except Exception as e:          # noqa: BLE001
                pytest.fail(f"face{idx} taper={taper}: raw "
                            f"{type(e).__name__} escaped: {str(e)[:100]}")
