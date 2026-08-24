"""import_stl — external STL files become solid bodies in the feature tree.

Covers the block (read/repair/validate), the Document integration, the
/api/import-stl endpoint, and the mesh-mode fast path in studio's viewer
meshing. All STL fixtures are generated on the fly (binary via struct,
ascii by hand) — no binary files in the repo.
"""
import base64
import struct

import build123d as b3d
import pytest
from fastapi.testclient import TestClient

import blocks
import inspector
import studio
from document import Document


# ---------------------------------------------------------------------------
# STL fixtures
# ---------------------------------------------------------------------------

def write_binary_stl(path, tris):
    """tris: list of ((x,y,z),(x,y,z),(x,y,z)) triples."""
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", 0, 0, 0))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


TET = [((0, 0, 0), (0, 10, 0), (10, 0, 0)),
       ((0, 0, 0), (10, 0, 0), (0, 0, 10)),
       ((0, 0, 0), (0, 0, 10), (0, 10, 0)),
       ((10, 0, 0), (0, 10, 0), (0, 0, 10))]
TET_VOL = 1000.0 / 6.0

ASCII_TET = "solid tet\n" + "".join(
    "facet normal 0 0 0\n outer loop\n"
    + "".join(f"  vertex {v[0]} {v[1]} {v[2]}\n" for v in tri)
    + " endloop\nendfacet\n" for tri in TET) + "endsolid tet\n"


def box_tris(ox=0.0, s=5.0, oy=0.0, oz=0.0):
    """12 watertight triangles of an s-cube at offset (ox, oy, oz)."""
    P = [(ox, oy, oz), (ox + s, oy, oz), (ox + s, oy + s, oz),
         (ox, oy + s, oz), (ox, oy, oz + s), (ox + s, oy, oz + s),
         (ox + s, oy + s, oz + s), (ox, oy + s, oz + s)]
    F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [(P[a], P[b], P[c]) for a, b, c in F]


# ---------------------------------------------------------------------------
# The block
# ---------------------------------------------------------------------------

def test_binary_roundtrip_box(tmp_path):
    p = tmp_path / "box.stl"
    b3d.export_stl(b3d.Box(20, 10, 5), str(p))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert part.volume == pytest.approx(1000, rel=1e-6)


def test_ascii_stl(tmp_path):
    p = tmp_path / "tet_ascii.stl"
    p.write_text(ASCII_TET)
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert part.volume == pytest.approx(TET_VOL, rel=1e-6)


def test_inverted_winding_is_repaired(tmp_path):
    p = tmp_path / "tet_inv.stl"
    write_binary_stl(p, [(c, b, a) for a, b, c in TET])
    part = blocks.import_stl(str(p))
    assert part.volume == pytest.approx(TET_VOL, rel=1e-6)
    assert inspector.health(part) == []


def test_two_disjoint_bodies(tmp_path):
    p = tmp_path / "two.stl"
    write_binary_stl(p, box_tris(0) + box_tris(20))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert part.volume == pytest.approx(250, rel=1e-6)


def test_open_mesh_friendly_error(tmp_path):
    p = tmp_path / "open.stl"
    write_binary_stl(p, TET[:3])
    with pytest.raises(ValueError, match="watertight"):
        blocks.import_stl(str(p))


def test_garbage_file_friendly_error(tmp_path):
    p = tmp_path / "junk.stl"
    p.write_bytes(b"this is not an stl file, just junk bytes 12345")
    with pytest.raises(ValueError, match="not an STL"):
        blocks.import_stl(str(p))


def test_missing_file_friendly_error():
    with pytest.raises(ValueError, match="not found"):
        blocks.import_stl("does-not-exist-anywhere.stl")


def test_empty_ascii_friendly_error(tmp_path):
    p = tmp_path / "empty.stl"
    p.write_text("solid nothing\nendsolid nothing\n")
    with pytest.raises(ValueError, match="no triangles"):
        blocks.import_stl(str(p))


def test_input_triangle_cap(tmp_path):
    import meshrepair
    n = meshrepair.MAX_INPUT_TRIANGLES + 1
    p = tmp_path / "big.stl"
    with open(p, "wb") as f:          # valid size formula, degenerate content
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", n))
        f.write(b"\0" * (50 * n))
    with pytest.raises(ValueError, match="limit"):
        blocks.import_stl(str(p))


# ---------------------------------------------------------------------------
# Auto-repair of broken real-world meshes (the "liquid piston" class:
# Fusion assembly exports with coincident walls and pinched edges)
# ---------------------------------------------------------------------------

def test_repair_duplicated_interface_walls(tmp_path):
    """Two boxes stacked with a duplicated interface wall (box_tris makes the
    shared face's triangles exact duplicates) heal into ONE body."""
    p = tmp_path / "stacked.stl"
    write_binary_stl(p, box_tris() + box_tris(oz=5.0))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert part.volume == pytest.approx(250, rel=1e-6)
    rep = blocks.import_stl_report(str(p))
    assert rep["repaired"] and rep["healed_wall_triangles"] == 4
    assert rep["bodies"] == 1


def test_repair_pinched_mesh_via_remesh(tmp_path):
    """Two boxes touching along one vertical edge (edge shared by 4 triangles
    = non-manifold pinch) get voxel-remeshed into a healthy solid with the
    right volume."""
    p = tmp_path / "pinched.stl"
    write_binary_stl(p, box_tris() + box_tris(ox=5.0, oy=5.0))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert part.volume == pytest.approx(250, rel=0.05)   # voxel-res tolerance
    rep = blocks.import_stl_report(str(p))
    assert rep["repaired"] and rep["remeshed_bodies"] >= 1


def test_scale_param(tmp_path):
    p = tmp_path / "tet_scale.stl"
    write_binary_stl(p, TET)
    part = blocks.import_stl(str(p), scale=2.0)
    assert part.volume == pytest.approx(TET_VOL * 8, rel=1e-6)
    with pytest.raises(ValueError, match="scale"):
        blocks.import_stl(str(p), scale=0)
    with pytest.raises(ValueError, match="scale"):
        blocks.import_stl(str(p), scale=-1)


def test_relative_name_resolves_to_imports_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(blocks, "IMPORTS_DIR", tmp_path)
    write_binary_stl(tmp_path / "rel.stl", TET)
    part = blocks.import_stl("rel.stl")
    assert part.volume == pytest.approx(TET_VOL, rel=1e-6)


# ---------------------------------------------------------------------------
# In a Document tree
# ---------------------------------------------------------------------------

def test_in_document_tree(tmp_path):
    p = tmp_path / "doc_tet.stl"
    write_binary_stl(p, TET)
    doc = Document("with-import")
    doc.add("mesh", "import_stl", {"file": str(p), "scale": 1.0}, [])
    doc.add("post", "disc", {"radius": 2, "thickness": 30}, [])
    doc.add("cut", "cut", {}, ["mesh", "post"])
    assert doc.rebuild()
    assert doc.get("mesh").status == "ok"
    assert doc.get("cut").volume < TET_VOL

    # intent JSON round-trip keeps the file param and rebuilds
    doc2 = Document.from_data(doc.to_data())
    assert doc2.rebuild()
    assert doc2.get("mesh").params["file"] == str(p)


# ---------------------------------------------------------------------------
# Studio: /api/import-stl + mesh-mode viewer meshing
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(blocks, "IMPORTS_DIR", tmp_path / "imports")
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(Document("imports-test"))
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def _b64(tris) -> str:
    import io
    buf = io.BytesIO()
    buf.write(b"\0" * 80)
    buf.write(struct.pack("<I", len(tris)))
    for a, b, c in tris:
        buf.write(struct.pack("<3f", 0, 0, 0))
        for v in (a, b, c):
            buf.write(struct.pack("<3f", *v))
        buf.write(struct.pack("<H", 0))
    return base64.b64encode(buf.getvalue()).decode()


def test_api_import_stl(client):
    d = client.post("/api/import-stl", json={
        "stl_base64": "data:model/stl;base64," + _b64(TET),
        "feature_id": "my-mesh"}).json()
    assert "error" not in d or not d["error"]
    assert d["ok"]
    info = d["import_info"]
    assert info["feature_id"] == "my-mesh"
    assert info["triangles"] == 4
    assert info["size_mm"] == [10, 10, 10]
    assert info["volume_mm3"] == pytest.approx(TET_VOL, abs=0.1)
    assert (blocks.IMPORTS_DIR / info["file"]).exists()
    feat = next(f for f in d["features"] if f["id"] == "my-mesh")
    assert feat["op"] == "import_stl" and feat["status"] == "ok"

    # same name, different bytes -> a NEW file, not an overwrite
    d2 = client.post("/api/import-stl", json={
        "stl_base64": _b64(box_tris()), "feature_id": "my-mesh"}).json()
    assert d2["ok"]
    assert d2["import_info"]["file"] != info["file"]
    assert d2["import_info"]["feature_id"] == "my-mesh-2"


def test_api_import_bad_file_leaves_tree_untouched(client):
    before = client.get("/api/doc").json()["features"]
    d = client.post("/api/import-stl", json={
        "stl_base64": base64.b64encode(b"junk junk junk").decode()}).json()
    assert d["error"]
    assert [f["id"] for f in d["features"]] == [f["id"] for f in before]
    assert not any(blocks.IMPORTS_DIR.glob("*")) \
        or not (blocks.IMPORTS_DIR / "imported-stl.stl").exists()


def test_api_import_open_mesh_friendly(client):
    d = client.post("/api/import-stl", json={
        "stl_base64": _b64(TET[:3])}).json()
    assert "watertight" in d["error"]


def test_mesh_mode_tagged_mesh(tmp_path, monkeypatch):
    """Imported triangle bodies collapse into ONE pickable MESH face and skip
    per-triangle edges; plain BREP bodies keep the classic full tagging."""
    p = tmp_path / "tm.stl"
    write_binary_stl(p, box_tris())
    part = blocks.import_stl(str(p))

    monkeypatch.setattr(studio, "MESH_MODE_FACES", 4)   # box import = 12 faces
    m = studio._tagged_mesh(part, body_id="mesh")
    assert len(m["faces"]) == 1
    mf = m["faces"][0]
    assert mf["id"] == studio.MESH_FACE_ID
    assert mf["type"] == "MESH" and mf["planar"] is False
    assert mf["triangles"] == 12
    assert len(m["indices"]) == 12 * 3
    assert set(m["faceId"]) == {studio.MESH_FACE_ID}
    assert m["edges"] == []

    # winding: the emitted soup must enclose POSITIVE volume (every triangle
    # wound outward). The raw vertex-walk order shipped 296/1258 triangles
    # inverted on a real sphere — backface-culled holes in the viewport.
    pos, idx = m["positions"], m["indices"]
    signed6 = 0.0
    for t in range(0, len(idx), 3):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (
            pos[3 * idx[t + k]:3 * idx[t + k] + 3] for k in range(3))
        signed6 += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx)
                    + az * (bx * cy - by * cx))
    assert signed6 / 6.0 == pytest.approx(125, rel=1e-6)   # the 5mm cube

    # classic path unchanged for a real BREP body of the same size
    monkeypatch.setattr(studio, "MESH_MODE_FACES", 400)
    box = b3d.Box(5, 5, 5)
    m2 = studio._tagged_mesh(box, body_id="box")
    assert len(m2["faces"]) == 6 and len(m2["edges"]) == 12


def test_mesh_mode_winding_on_sphere(tmp_path, monkeypatch):
    """The geometry that actually shipped the winding bug: a tessellated
    sphere, where the raw vertex-walk order is inverted on ~1/4 of the
    triangles. The soup's signed volume must match the solid's volume."""
    p = tmp_path / "wind_sphere.stl"
    b3d.export_stl(b3d.Sphere(10), str(p), tolerance=0.2, angular_tolerance=0.6)
    part = blocks.import_stl(str(p))

    monkeypatch.setattr(studio, "MESH_MODE_FACES", 4)
    m = studio._tagged_mesh(part, body_id="s")
    assert m["faces"][0]["type"] == "MESH"
    pos, idx = m["positions"], m["indices"]
    signed6 = 0.0
    for t in range(0, len(idx), 3):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (
            pos[3 * idx[t + k]:3 * idx[t + k] + 3] for k in range(3))
        signed6 += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx)
                    + az * (bx * cy - by * cx))
    assert signed6 / 6.0 == pytest.approx(part.volume, rel=1e-4)
