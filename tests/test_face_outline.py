"""Selected-surface reference in the sketch editor: project a picked face's
boundary into its plane's local 2D coords (2026-07-28 feature request)."""
import pytest

import build123d as b3d
import sketch as sk


def _plate_with_hole():
    return b3d.Box(80, 60, 10) - b3d.Cylinder(8, 12)


def test_face_outline_projects_outer_and_hole():
    part = _plate_with_hole()
    top_z = max(f.center().Z for f in part.faces()
                if f.geom_type == b3d.GeomType.PLANE)
    out = sk.face_outline_2d(part, [0, 0, top_z], [0, 0, 1])
    assert out["planar"] is True
    # world frame ships with the outline (for ghost previews)
    f = out["frame"]
    assert set(f) == {"origin", "x_dir", "y_dir", "z_dir"}
    assert f["origin"][2] == pytest.approx(top_z, abs=1e-3)
    assert abs(f["z_dir"][2]) == pytest.approx(1, abs=1e-6)   # normal is ±Z
    xs = [p[0] for p in out["outer"]]
    ys = [p[1] for p in out["outer"]]
    # 80x60 plate top -> local coords span +-40 x +-30
    assert max(xs) == pytest.approx(40, abs=0.5)
    assert min(xs) == pytest.approx(-40, abs=0.5)
    assert max(ys) == pytest.approx(30, abs=0.5)
    assert len(out["holes"]) == 1                 # the Ø16 bore
    hx = [p[0] for p in out["holes"][0]]
    assert (max(hx) - min(hx)) == pytest.approx(16, abs=0.5)


def test_face_outline_curved_face_reports_non_planar():
    cyl = b3d.Cylinder(10, 30)
    side = next(f for f in cyl.faces() if f.geom_type == b3d.GeomType.CYLINDER)
    c = side.center()
    out = sk.face_outline_2d(cyl, [c.X, c.Y, c.Z], None)
    assert out["planar"] is False
    assert out["outer"] == []


def test_resolve_face_is_geometric_and_survives_change():
    """The picked top face is still found after the plate gets thicker."""
    thin = b3d.Box(40, 40, 10)
    top = sk.resolve_face(thin, [0, 0, 5], [0, 0, 1])
    assert top.center().Z == pytest.approx(5)
    thick = b3d.Box(40, 40, 30)
    top2 = sk.resolve_face(thick, [0, 0, 5], [0, 0, 1])   # stored pick at z=5
    assert top2.center().Z == pytest.approx(15)           # snaps to the moved top


def test_face_outline_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    import studio
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    client = TestClient(studio.app)
    client.post("/api/new", json={"name": "faceref"})
    client.post("/api/feature/add", json={
        "id": "plate", "op": "plate",
        "params": {"width": 80, "depth": 60, "thickness": 10}, "inputs": []})
    r = client.post("/api/face-outline",
                    json={"face_center": [0, 0, 5], "face_normal": [0, 0, 1]})
    assert r.status_code == 200
    body = r.json()
    assert body["planar"] is True and len(body["outer"]) >= 4


def test_face_outline_endpoint_no_solid():
    from fastapi.testclient import TestClient
    import studio
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    client = TestClient(studio.app)
    r = client.post("/api/face-outline",
                    json={"face_center": [0, 0, 0]})
    assert r.status_code == 200
    assert r.json()["planar"] is False           # empty doc -> no solid, no crash


# ---------------------------------------------------------------------------
# Named-face sketches must be re-openable for editing (user report 2026-08-31:
# "even after selecting them, I can't edit those sketches"). Every AI-authored
# design names its faces (face="top", the offset method) instead of storing a
# face_center — and /api/face-outline rejected those with a 422 before the
# request was even read, so the tree's edit action silently did nothing.
# ---------------------------------------------------------------------------

def test_face_outline_named_face():
    part = _plate_with_hole()                      # 80x60x10 -> top at z=5
    out = sk.face_outline_2d(part, face="top")
    assert out["planar"] is True
    assert out["frame"]["origin"][2] == pytest.approx(5, abs=1e-3)
    assert len(out["holes"]) == 1                  # same projection as a pick


def test_face_outline_named_face_offset_matches_sketch_plane():
    """The frame with an offset must land EXACTLY where sketch_on_face puts
    the sketch (pl.offset), so the editor grid sits on the real plane."""
    part = _plate_with_hole()
    out = sk.face_outline_2d(part, face="top", offset=-4.2)   # logo depth
    assert out["planar"] is True
    assert out["frame"]["origin"][2] == pytest.approx(5 - 4.2, abs=1e-3)
    bot = sk.face_outline_2d(part, face="bottom", offset=3.0)  # cavity floor
    # bottom face canonicalises to the XY frame (z_dir +Z): +3 goes UP,
    # into the material — the same arithmetic sketch_on_face applies
    assert bot["frame"]["origin"][2] == pytest.approx(-5 + 3.0, abs=1e-3)


def test_face_outline_needs_face_or_center():
    part = _plate_with_hole()
    with pytest.raises(ValueError, match="face_center"):
        sk.face_outline_2d(part)


def test_face_outline_endpoint_named_face_no_center():
    """THE regression: a named-face request without face_center must be a
    normal 200, not a 422 validation error."""
    from fastapi.testclient import TestClient
    import studio
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    client = TestClient(studio.app)
    client.post("/api/new", json={"name": "namedface"})
    client.post("/api/feature/add", json={
        "id": "plate", "op": "plate",
        "params": {"width": 80, "depth": 60, "thickness": 10}, "inputs": []})
    r = client.post("/api/face-outline", json={"face": "top", "offset": -2.0})
    assert r.status_code == 200
    body = r.json()
    assert body["planar"] is True
    assert body["frame"]["origin"][2] == pytest.approx(5 - 2.0, abs=1e-3)
    # neither face nor center -> a spoken error, still not a 422
    r2 = client.post("/api/face-outline", json={})
    assert r2.status_code == 200
    assert "face" in (r2.json().get("error") or "")
