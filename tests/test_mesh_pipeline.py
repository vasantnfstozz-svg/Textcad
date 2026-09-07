"""The viewport mesh: one shared triangulation, and it must be RIGHT.

User report (2026-08-25): switching tabs left the previous design on screen for
"at least one minute". Profiling the tab switch found the cause was not the
switch at all: `_tagged_mesh` meshed all 254 faces of esp32-remote one at a
time (8.8 s) and then sampled all 609 edges off their curves (2.5 s).

Meshing the solid ONCE and reading each face's slice is ~20x faster and better
geometry (independently meshed faces do not share nodes along their common
edges, so the shell has hairline cracks). The risk is winding: a REVERSED face's
triangles wind the other way, and getting that wrong turns the part inside out
under backface culling — invisible to any test that only counts triangles.

So these tests check the mesh as GEOMETRY: enclosed volume via the divergence
theorem (signed, so inside-out fails), surface area, bounding box, and that
every face keeps a pickable id.
"""
import pytest

import studio
from document import Document


def mesh_volume(m):
    """Signed volume of a closed triangle mesh (divergence theorem).

    Positive means the triangles wind outward — which is what the renderer
    needs. An inside-out mesh gives exactly the negative of the right answer,
    so this single number catches the bug that a triangle count never would."""
    pos, idx = m["positions"], m["indices"]
    total = 0.0
    for t in range(0, len(idx), 3):
        a, b, c = idx[t] * 3, idx[t + 1] * 3, idx[t + 2] * 3
        ax, ay, az = pos[a], pos[a + 1], pos[a + 2]
        bx, by, bz = pos[b], pos[b + 1], pos[b + 2]
        cx, cy, cz = pos[c], pos[c + 1], pos[c + 2]
        total += (ax * (by * cz - bz * cy)
                  - ay * (bx * cz - bz * cx)
                  + az * (bx * cy - by * cx)) / 6.0
    return total


def mesh_area(m):
    pos, idx = m["positions"], m["indices"]
    total = 0.0
    for t in range(0, len(idx), 3):
        a, b, c = idx[t] * 3, idx[t + 1] * 3, idx[t + 2] * 3
        ux, uy, uz = pos[b] - pos[a], pos[b + 1] - pos[a + 1], pos[b + 2] - pos[a + 2]
        vx, vy, vz = pos[c] - pos[a], pos[c + 1] - pos[a + 1], pos[c + 2] - pos[a + 2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        total += 0.5 * (nx * nx + ny * ny + nz * nz) ** 0.5
    return total


def block_doc():
    doc = Document(name="t-mesh")
    doc.add("sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30},
        {"kind": "circle", "r": 6, "x": 10, "y": 0, "mode": "subtract"}]})
    doc.add("body", "extrude", {"amount": 12}, inputs=["sk"])
    doc.add("cyl", "tube", {"outer_radius": 9, "inner_radius": 4,
                            "height": 20})
    doc.add("cyl_at", "move", {"x": -60, "y": 0, "z": 0}, inputs=["cyl"])
    assert doc.rebuild(), doc.tree()
    return doc


PARTS = ("body", "cyl_at")


@pytest.mark.parametrize("fid", PARTS)
def test_the_mesh_encloses_the_real_volume_and_faces_outward(fid):
    doc = block_doc()
    part = doc._parts[fid]
    m = studio._tagged_mesh(part, body_id=fid)
    v = mesh_volume(m)
    assert v > 0, "the mesh is inside out — every triangle winds the wrong way"
    assert v == pytest.approx(part.volume, rel=0.02), \
        f"mesh encloses {v:.1f} mm3, the solid is {part.volume:.1f} mm3"


@pytest.mark.parametrize("fid", PARTS)
def test_the_mesh_covers_the_real_surface(fid):
    doc = block_doc()
    part = doc._parts[fid]
    m = studio._tagged_mesh(part, body_id=fid)
    assert mesh_area(m) == pytest.approx(part.area, rel=0.03)


@pytest.mark.parametrize("fid", PARTS)
def test_the_mesh_fills_the_same_bounding_box(fid):
    doc = block_doc()
    part = doc._parts[fid]
    m = studio._tagged_mesh(part, body_id=fid)
    bb = part.bounding_box()
    xs, ys, zs = m["positions"][0::3], m["positions"][1::3], m["positions"][2::3]
    for lo, hi, got_lo, got_hi in ((bb.min.X, bb.max.X, min(xs), max(xs)),
                                   (bb.min.Y, bb.max.Y, min(ys), max(ys)),
                                   (bb.min.Z, bb.max.Z, min(zs), max(zs))):
        assert got_lo == pytest.approx(lo, abs=0.5)
        assert got_hi == pytest.approx(hi, abs=0.5)


def test_every_face_is_tagged_and_pickable():
    """Face ids drive picking AND face->feature attribution; a face with no
    triangles is a face the user cannot click."""
    doc = block_doc()
    part = doc._parts["body"]
    m = studio._tagged_mesh(part, body_id="body")
    tagged = set(m["faceId"])
    assert tagged == set(range(len(part.faces()))), \
        f"faces without triangles: {set(range(len(part.faces()))) - tagged}"
    assert {f["id"] for f in m["faces"]} == tagged
    for f in m["faces"]:
        assert f["body"] == "body" and f["area"] > 0
        assert "planar" in f


def test_indices_stay_inside_the_vertex_array():
    doc = block_doc()
    m = studio._tagged_mesh(doc._parts["body"], body_id="body")
    n = len(m["positions"]) // 3
    assert n == len(m["faceId"])
    assert m["indices"] and max(m["indices"]) < n and min(m["indices"]) >= 0


def test_edges_follow_the_mesh_and_stay_on_the_part():
    doc = block_doc()
    part = doc._parts["body"]
    m = studio._tagged_mesh(part, body_id="body")
    assert len(m["edges"]) == len(part.edges())
    bb = part.bounding_box()
    for e in m["edges"]:
        assert len(e["points"]) >= 2
        assert e["length"] > 0 and e["body"] == "body"
        for x, y, z in e["points"]:          # no stray points off the solid
            assert bb.min.X - 0.5 <= x <= bb.max.X + 0.5
            assert bb.min.Y - 0.5 <= y <= bb.max.Y + 0.5
            assert bb.min.Z - 0.5 <= z <= bb.max.Z + 0.5


def test_every_edge_names_the_faces_it_bounds():
    """The picker's occlusion rule (viewport.edgeHitAt): a face cannot hide its
    own boundary, so an inside corner's line — a hair behind the two walls that
    meet there from every angle — picks like an outside edge. Each edge carries
    the ids of its faces: one incidence per (face, edge) pair of the solid,
    every id a real face of the payload."""
    doc = block_doc()
    part = doc._parts["body"]
    m = studio._tagged_mesh(part, body_id="body")
    ids = {f["id"] for f in m["faces"]}
    assert all(1 <= len(e["faces"]) <= 2 and set(e["faces"]) <= ids for e in m["edges"])
    assert sum(len(e["faces"]) for e in m["edges"]) == sum(len(f.edges()) for f in part.faces())


def test_a_curved_face_is_not_a_coarse_polygon():
    """A small bore must still read as round: the angular tolerance is what
    keeps 4 mm holes from turning into hexagons."""
    doc = block_doc()
    part = doc._parts["cyl_at"]
    m = studio._tagged_mesh(part, body_id="cyl_at")
    cyls = [f for f in m["faces"] if f["type"] == "CYLINDER"]
    assert cyls, "no cylindrical face in a tube?"
    inner = min(cyls, key=lambda f: f.get("radius") or 1e9)
    verts = sum(1 for fid in m["faceId"] if fid == inner["id"])
    assert verts >= 24, f"the r={inner.get('radius')} bore has only {verts} " \
                        f"vertices — it will look faceted"


def test_meshing_twice_gives_the_same_mesh():
    doc = block_doc()
    part = doc._parts["body"]
    a = studio._tagged_mesh(part, body_id="body")
    b = studio._tagged_mesh(part, body_id="body")
    assert a["positions"] == b["positions"] and a["indices"] == b["indices"]
