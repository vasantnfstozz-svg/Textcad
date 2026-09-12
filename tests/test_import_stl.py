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


# ---------------------------------------------------------------------------
# Section 8 review (2026-09-12). Every case below was measured on the code as
# it stood — probes/s8_*.py — before the fix that makes it pass.
# ---------------------------------------------------------------------------

def flipped(tris):
    """The same triangles wound the other way: an INWARD surface, which is
    exactly what a sealed void inside a solid looks like in an STL."""
    return [(a, c, b) for a, b, c in tris]


def brick(x0, y0, z0, x1, y1, z1):
    """12 watertight triangles of an arbitrary box (box_tris does cubes)."""
    P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [(P[a], P[b], P[c]) for a, b, c in F]


def test_hollow_stl_keeps_its_cavity(tmp_path):
    """A 10 mm cube holding a sealed 4 mm void is ONE body of 936 mm3.

    Measured 2026-09-12: it imported as TWO bodies totalling 1064 mm3 — the
    cavity FILLED (1000) plus a phantom 64 mm3 block sitting inside it, all
    green. lib3mf had already read the file correctly as one Solid of 936;
    the guard meant to take that as-is called `shp.is_valid()`, which is a
    PROPERTY, so it raised TypeError into a bare `except` and the shape was
    exploded shell by shell instead."""
    p = tmp_path / "hollow.stl"
    write_binary_stl(p, box_tris(s=10)
                     + flipped(box_tris(ox=3, oy=3, oz=3, s=4)))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert len(part.solids()) == 1
    assert part.volume == pytest.approx(936, rel=1e-6)
    assert blocks.import_stl_report(str(p))["bodies"] == 1


def test_hollow_body_beside_a_second_body(tmp_path):
    """The assembly case: a hollow body AND a plain one in one file. The void
    belongs to the body that contains it; the other body stays its own."""
    p = tmp_path / "hollow_pair.stl"
    write_binary_stl(p, box_tris(s=10)
                     + flipped(box_tris(ox=3, oy=3, oz=3, s=4))
                     + box_tris(ox=30, s=10))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert len(part.solids()) == 2
    assert part.volume == pytest.approx(1936, rel=1e-6)


def test_hollow_stl_through_the_repair_path(tmp_path):
    """The same part reached through the OTHER door: a duplicated wall makes
    the file dirty, so it goes through heal/split/decimate, which splits by
    connected component — and a void is always its own component."""
    p = tmp_path / "hollow_dirty.stl"
    dup_wall = box_tris(ox=30, s=10) + box_tris(ox=30, oz=10, s=10)
    write_binary_stl(p, box_tris(s=10)
                     + flipped(box_tris(ox=3, oy=3, oz=3, s=4)) + dup_wall)
    part = blocks.import_stl(str(p))
    rep = blocks.import_stl_report(str(p))
    assert rep["repaired"]
    assert inspector.health(part) == []
    assert len(part.solids()) == 2                  # the hollow one + the stack
    assert part.volume == pytest.approx(936 + 2000, rel=1e-6)


def test_duplicate_body_is_not_deleted(tmp_path):
    """An assembly that exports one component TWICE at the same place must
    not lose it.

    Measured 2026-09-12: `drop_duplicate_walls` removes ALL copies of a
    duplicated triangle — right for the interface wall between two touching
    bodies, fatal when the duplicate IS the whole body. 2000 mm3 of part came
    in as 1000 mm3 in one body, announced as "merged 24 coincident wall
    triangles". A file holding nothing but the doubled body was refused with
    "no solid found in the mesh"."""
    p = tmp_path / "dup.stl"
    write_binary_stl(p, box_tris(s=10) + box_tris(s=10) + box_tris(ox=30, s=10))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert len(part.solids()) == 2
    assert part.volume == pytest.approx(2000, rel=1e-6)

    q = tmp_path / "dup_only.stl"
    write_binary_stl(q, box_tris(s=10) + box_tris(s=10))
    only = blocks.import_stl(str(q))
    assert only.volume == pytest.approx(1000, rel=1e-6)


def test_welded_overlapping_bodies_keep_their_material(tmp_path):
    """Two bodies that INTERPENETRATE and are welded along a shared edge —
    the Fusion assembly export this pipeline exists for. The pinch sends the
    component through the voxel remesh.

    Measured 2026-09-12: the parity fill paired the crossings as (enter A,
    enter B), (exit A, exit B), so the solid overlap between the two bodies
    was filled with NOTHING: 12 000 mm3 came back as 7 998.4, a void punched
    straight through, health [] and status ok."""
    p = tmp_path / "overlap.stl"
    write_binary_stl(p, brick(0, 0, 0, 20, 20, 20) + brick(0, 0, 0, 10, 20, 40))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert blocks.import_stl_report(str(p))["remeshed_bodies"] == 1
    assert part.volume == pytest.approx(12000, rel=0.02)


def test_remesh_says_how_far_it_moved(tmp_path):
    """The remesh replaces a whole body with a voxel approximation at
    pitch = longest bbox axis / 200, and NOTHING used to measure or report
    that — only decimation had a volume guard, and its reference was taken
    AFTER the remesh. Measured 2026-09-12: a 0.6 mm plate 100 mm across came
    back 8.7% light, green, with no number anywhere."""
    p = tmp_path / "thin_pinch.stl"
    write_binary_stl(p, brick(0, 0, 0, 100, 100, 0.6)
                     + brick(100, 100, 0, 110, 110, 0.6))
    blocks.import_stl(str(p))
    rep = blocks.import_stl_report(str(p))
    assert rep["remeshed_bodies"] == 1
    assert rep["remesh_drift_pct"] >= 1.0


def test_gross_remesh_drift_is_refused(tmp_path):
    """A body whose features are far below the voxel pitch cannot be honestly
    remeshed: say so instead of importing a different part."""
    import meshrepair
    p = tmp_path / "hopeless.stl"
    write_binary_stl(p, brick(0, 0, 0, 200, 200, 0.12)
                     + brick(200, 200, 0, 210, 210, 0.12))
    with pytest.raises(ValueError, match="repair|remesh|thin"):
        blocks.import_stl(str(p))
    assert meshrepair.REMESH_VOLUME_RTOL == 0.15


def test_many_bodies_stay_within_the_triangle_budget():
    """MIN_COMPONENT_BUDGET is a floor per BODY, and nothing capped the sum:
    40 bodies of 5 000 triangles each got 1 500 apiece = 60 000 triangles out
    of an 18 000 budget (measured 2026-09-12), 3.3x what the kernel and the
    viewer were budgeted for."""
    import meshrepair
    shares = meshrepair.component_shares([5000] * 40, meshrepair.DEFAULT_BUDGET)
    assert sum(shares) <= meshrepair.DEFAULT_BUDGET * meshrepair.MAX_OUTPUT_MULT
    # a handful of bodies still gets the full floor
    few = meshrepair.component_shares([5000] * 3, meshrepair.DEFAULT_BUDGET)
    assert min(few) >= meshrepair.MIN_COMPONENT_BUDGET


def test_truncated_binary_stl_is_named_as_cut_short(tmp_path):
    """A part-downloaded STL used to read "not an STL file (neither binary nor
    ascii STL)" — a diagnosis the file does not deserve."""
    p = tmp_path / "cut.stl"
    full = tmp_path / "full.stl"
    write_binary_stl(full, box_tris(s=10))
    p.write_bytes(full.read_bytes()[:200])
    with pytest.raises(ValueError, match="cut short"):
        blocks.import_stl(str(p))


# ---------------------------------------------------------------------------
# Section 8 ROUND TWO (2026-09-12): the fix commit 94eb47e re-read. Every case
# measured on 94eb47e first (probes/s8r2_*.py).
# ---------------------------------------------------------------------------

def test_inverted_hollow_stl_keeps_its_cavity(tmp_path):
    """The P0 through the INVERSION door. A hollow part whose whole file is
    wound inside-out (a known exporter bug; the plain case has its own test)
    still imported as 1064 mm3 in TWO bodies on 94eb47e: the sign rule read
    the outer shell as a 'void' and the cavity as a 'body'. What a shell IS
    is decided by nesting depth now, and its winding is FORCED to match."""
    p = tmp_path / "hollow_inv.stl"
    write_binary_stl(p, flipped(box_tris(s=10)) + box_tris(ox=3, oy=3, oz=3, s=4))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert len(part.solids()) == 1
    assert part.volume == pytest.approx(936, rel=1e-6)

    q = tmp_path / "hollow_inv_pair.stl"
    write_binary_stl(q, flipped(box_tris(s=10)) + box_tris(ox=3, oy=3, oz=3, s=4)
                     + box_tris(ox=30, s=10))
    pair = blocks.import_stl(str(q))
    assert len(pair.solids()) == 2
    assert pair.volume == pytest.approx(1936, rel=1e-6)


def test_a_body_inside_a_cavity_is_its_own_body(tmp_path):
    """Nesting depth 2: a loose part sealed inside a cavity is a BODY again,
    not a void of the void. 20-cube, cavity 4..16, island 8..12."""
    p = tmp_path / "island.stl"
    write_binary_stl(p, box_tris(s=20) + flipped(box_tris(ox=4, oy=4, oz=4, s=12))
                     + box_tris(ox=8, oy=8, oz=8, s=4))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert len(part.solids()) == 2
    assert part.volume == pytest.approx(8000 - 1728 + 64, rel=1e-6)


def test_pinched_cavity_is_remeshed_not_refused(tmp_path):
    """REGRESSION caught in round two: a hollow part whose CAVITY surface is
    pinched sent an inward-wound component through the winding fill, which
    never sees wind > 0 on an inward surface -> 'voxel remesh produced an
    empty volume'. The parity fill before it did not care. 40-cube with a
    cavity of two 8-cubes touching along an edge: 64000 - 1024."""
    p = tmp_path / "pinched_void.stl"
    write_binary_stl(p, box_tris(s=40)
                     + flipped(box_tris(ox=10, oy=10, oz=10, s=8))
                     + flipped(box_tris(ox=18, oy=18, oz=10, s=8)))
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert len(part.solids()) == 1
    assert part.volume == pytest.approx(64000 - 1024, rel=0.01)


def test_pinched_mesh_with_flipped_triangles_keeps_its_volume(tmp_path):
    """REGRESSION caught in round two: the parity fill did not care which way
    a triangle faced — the docstring promises 'inconsistent winding' is
    handled — and the winding fill does. Two pinched 20-cubes with cube A's
    top face flipped came back 7,998.8 of 16,000 on 94eb47e, drift 0.0, all
    green. A component whose winding is inconsistent falls back to parity."""
    tris = box_tris(s=20) + box_tris(ox=20, oy=20, s=20)
    tris[2], tris[3] = ((tris[2][0], tris[2][2], tris[2][1]),
                        (tris[3][0], tris[3][2], tris[3][1]))
    p = tmp_path / "pinched_mixed.stl"
    write_binary_stl(p, tris)
    part = blocks.import_stl(str(p))
    assert inspector.health(part) == []
    assert part.volume == pytest.approx(16000, rel=0.02)


def test_ascii_stl_with_a_byte_order_mark(tmp_path):
    """A Windows text editor's UTF-8 BOM in front of 'solid' made 94eb47e read
    the text as a binary header and say 'cut short — its header says
    824,211,557 triangles'."""
    p = tmp_path / "bom.stl"
    p.write_bytes(b"\xef\xbb\xbf" + ASCII_TET.encode())
    part = blocks.import_stl(str(p))
    assert part.volume == pytest.approx(TET_VOL, rel=1e-6)


# ---------------------------------------------------------------------------
# Section 8 ROUND THREE (2026-09-12): the round-two commit d94518c re-read.
# ---------------------------------------------------------------------------

def _stl_of(shape, path):
    """build123d shape -> (verts, faces) via export_stl."""
    import meshrepair
    b3d.export_stl(shape, str(path))
    return meshrepair.parse_binary_stl(path.read_bytes())


def _write_merged(path, parts):
    import numpy as np
    import meshrepair
    vs, fs, off = [], [], 0
    for v, f in parts:
        vs.append(v)
        fs.append(f + off)
        off += len(v)
    path.write_bytes(meshrepair.to_binary_stl(np.concatenate(vs), np.concatenate(fs)))


def test_a_body_overlapping_a_notch_is_not_a_void(tmp_path):
    """REGRESSION caught in round three. Round two decided 'shell B is inside
    shell A' from ONE vertex of B. A bracket sitting in the notch of a
    C-shaped frame, overlapping the frame's wall by 2 mm, has its box inside
    the frame's box and one corner inside the frame's material — and on
    d94518c it came in as ONE body of 20,360 mm3: the 640 mm3 bracket had
    been made a VOID of the 21,000 mm3 frame, valid and green. Two bodies
    that overlap are two bodies (the documented decision: never fuse)."""
    frame = (b3d.Box(30, 30, 30, align=b3d.Align.MIN)
             - b3d.Pos(10, 0, 10) * b3d.Box(10, 30, 20, align=b3d.Align.MIN))
    bracket = b3d.Pos(8, 11, 12) * b3d.Box(10, 8, 8, align=b3d.Align.MIN)
    p = tmp_path / "notch.stl"
    _write_merged(p, [_stl_of(frame, tmp_path / "a.stl"),
                      _stl_of(bracket, tmp_path / "b.stl")])
    part = blocks.import_stl(str(p))
    assert len(part.solids()) == 2
    assert part.volume == pytest.approx(21000 + 640, rel=1e-6)


def test_a_pin_through_two_walls_is_not_a_void(tmp_path):
    """The nastier cousin: a pin whose two ENDS are embedded in the two walls
    of a housing and whose middle spans the gap between them. Every vertex of
    the pin is inside wall material; only its faces cross the gap."""
    housing = (b3d.Box(40, 20, 20, align=b3d.Align.MIN)          # a U: two walls
               - b3d.Pos(10, 0, 0) * b3d.Box(20, 20, 15, align=b3d.Align.MIN))  # + a floor
    pin = b3d.Pos(5, 8, 8) * b3d.Box(30, 4, 4, align=b3d.Align.MIN)    # x 5..35
    p = tmp_path / "pin.stl"
    _write_merged(p, [_stl_of(housing, tmp_path / "h.stl"),
                      _stl_of(pin, tmp_path / "p.stl")])
    part = blocks.import_stl(str(p))
    assert len(part.solids()) == 2
    assert part.volume == pytest.approx(housing.volume + pin.volume, rel=1e-6)
