"""
meshrepair.py — mesh sanitation for STL import: heal, split, remesh, decimate.

Real-world STLs (this module was built against an actual Fusion 360 assembly
export, "liquid piston 2 v1.stl", 88,990 triangles) are routinely broken in
ways the OCCT kernel cannot digest:

  * coincident interface walls where touching bodies were exported as one
    mesh (exact-duplicate triangles -> edges shared 4x),
  * pinched/self-touching surfaces (edges shared by >2 triangles even inside
    a single body),
  * far more triangles than a BREP kernel can carry interactively.

Feeding such a file straight to lib3mf/OCCT produced a 6-MINUTE read that
returned an EMPTY invalid solid. The honest fix is a mesh-level repair
pipeline (all numpy, all deterministic), with the inspector's health check
as the final arbiter downstream:

  parse -> weld -> drop duplicated walls -> split into connected components,
  then per component:
    clean + small enough      -> pass through
    clean + too dense         -> decimate (volume-guarded ladder)
    pinched (edges shared >2) -> parity voxel remesh -> marching cubes ->
                                 decimate (volume-guarded ladder)
  open (boundary edges)       -> refuse: a hole is not repairable honestly.

Every decimation step re-checks manifoldness (fast-simplification is not
topology-safe: it re-pinches meshes unpredictably — probed) and collapses
the handful of bad edges it creates. Every accepted result must keep its
signed volume within VOLUME_RTOL of the pre-decimation reference — probed:
decimating a thin-walled body too hard silently imploded 94% of its volume
while staying perfectly manifold.

Heavy dependencies (scipy, scikit-image, fast-simplification) are imported
lazily so plain clean imports never need them.
"""

from __future__ import annotations
import io
import struct

import numpy as np

# repair budget: how many triangles an imported file may hand to the BREP
# kernel. Probed costs per 1k triangles: lib3mf read ~0.8s (one-off, cached),
# viewer fast-path mesh ~0.2s/request, export_stl ~0.5s/rebuild.
DEFAULT_BUDGET = 18_000
MAX_INPUT_TRIANGLES = 500_000     # numpy parse/voxelize stays in seconds
MIN_COMPONENT_BUDGET = 1_500
LADDER = (1.0, 1.5, 2.0, 3.0)     # budget multipliers tried per component
VOLUME_RTOL = 0.15                # decimation may not eat >15% of a body
VOXEL_RES = 200                   # remesh grid cells along the longest axis


# ---------------------------------------------------------------------------
# Parse / serialize
# ---------------------------------------------------------------------------

def parse_binary_stl(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Binary STL bytes -> (welded vertices float64 (v,3), faces int64 (f,3)).
    Welding is by exact float equality — STL exporters emit identical floats
    for shared vertices."""
    (n,) = struct.unpack_from("<I", data, 80)
    rec = np.frombuffer(data, dtype=np.uint8, count=50 * n, offset=84)
    tris = rec.reshape(n, 50)[:, 12:48].copy().view("<f4").reshape(n, 3, 3)
    flat = tris.reshape(-1, 3).astype(np.float64)
    verts, inv = np.unique(flat, axis=0, return_inverse=True)
    return verts, inv.reshape(n, 3).astype(np.int64)


def to_binary_stl(verts: np.ndarray, faces: np.ndarray) -> bytes:
    recs = np.zeros((len(faces), 50), dtype=np.uint8)
    recs[:, 12:48] = (verts[faces].astype("<f4")
                      .reshape(len(faces), 9).view(np.uint8))
    return b"\0" * 80 + struct.pack("<I", len(faces)) + recs.tobytes()


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------

def edge_counts(faces: np.ndarray) -> tuple[int, int]:
    """(boundary_edges, overshared_edges). A watertight manifold mesh has
    every edge shared by EXACTLY two triangles -> (0, 0)."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e.sort(axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return int((cnt == 1).sum()), int((cnt > 2).sum())


def duplicate_triangles(faces: np.ndarray) -> np.ndarray:
    """Mask of triangles whose vertex-set appears more than once (coincident
    interface walls between touching exported bodies)."""
    k = np.sort(faces, axis=1)
    _, kinv, kcnt = np.unique(k, axis=0, return_inverse=True,
                              return_counts=True)
    return kcnt[kinv] > 1


def signed_volume(verts: np.ndarray, faces: np.ndarray) -> float:
    """Sum of signed origin-tetrahedra: the enclosed volume of a closed,
    consistently outward-wound surface."""
    a, b, c = (verts[faces[:, i]] for i in range(3))
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def is_clean(faces: np.ndarray) -> bool:
    once, more = edge_counts(faces)
    return once == 0 and more == 0 and not duplicate_triangles(faces).any()


# ---------------------------------------------------------------------------
# Repair primitives (each probed against the liquid-piston file)
# ---------------------------------------------------------------------------

def drop_duplicate_walls(faces: np.ndarray) -> tuple[np.ndarray, int]:
    """Remove ALL copies of duplicated triangles. Two solids exported touching
    face-to-face each carry a copy of the interface wall; removing both merges
    the volumes through it (probed: healed 1 of the piston's 3 bodies
    completely)."""
    dup = duplicate_triangles(faces)
    return faces[~dup], int(dup.sum())


def split_components(faces: np.ndarray, n_verts: int) -> list[np.ndarray]:
    """Connected components over shared vertices, as face-index arrays."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    rows = np.repeat(np.arange(len(faces)), 3)
    m = coo_matrix((np.ones(len(rows), np.int8), (rows, faces.reshape(-1))),
                   shape=(len(faces), n_verts))
    ncomp, labels = connected_components(m @ m.T, directed=False)
    return [np.nonzero(labels == c)[0] for c in range(ncomp)]


def collapse_repair(verts: np.ndarray, faces: np.ndarray,
                    rounds: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """Heal the few non-manifold edges decimation creates by collapsing them
    (merge the edge's endpoints, drop degenerate + re-duplicated triangles).
    Probed: converges in 1 round on real damage (tens of bad edges)."""
    faces = faces.copy()
    for _ in range(rounds):
        e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]],
                            faces[:, [2, 0]]])
        e.sort(axis=1)
        ue, cnt = np.unique(e, axis=0, return_counts=True)
        bad = ue[cnt != 2]
        if len(bad) == 0:
            return verts, faces
        remap = np.arange(len(verts))
        for v0, v1 in bad:
            a, b = remap[v0], remap[v1]
            if a != b:
                remap[remap == b] = a
        faces = remap[faces]
        degen = ((faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2])
                 | (faces[:, 0] == faces[:, 2]))
        faces = faces[~degen]
        faces, _ = drop_duplicate_walls(faces)
    return verts, faces


def voxel_remesh(verts: np.ndarray, faces: np.ndarray,
                 res: int = VOXEL_RES) -> tuple[np.ndarray, np.ndarray]:
    """Parity-fill remesh: Z-crossings per XY column -> inside/outside grid ->
    marching cubes. Output is watertight-manifold by construction, whatever
    the input's sins (pinches, self-touches, inconsistent winding)."""
    from skimage.measure import marching_cubes
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    pitch = float((hi - lo).max()) / res
    # grid offset by irrational-ish fractions so rays dodge exact edge hits
    nx = int(np.ceil((hi[0] - lo[0]) / pitch)) + 3
    ny = int(np.ceil((hi[1] - lo[1]) / pitch)) + 3
    nz = int(np.ceil((hi[2] - lo[2]) / pitch)) + 3
    ox, oy, oz = (lo[0] - pitch * 1.0137, lo[1] - pitch * 1.0731,
                  lo[2] - pitch * 1.0421)
    crossings: list[list[float]] = [[] for _ in range(nx * ny)]
    for a, b, c in verts[faces]:
        xmin = int(np.floor((min(a[0], b[0], c[0]) - ox) / pitch))
        xmax = int(np.floor((max(a[0], b[0], c[0]) - ox) / pitch)) + 1
        ymin = int(np.floor((min(a[1], b[1], c[1]) - oy) / pitch))
        ymax = int(np.floor((max(a[1], b[1], c[1]) - oy) / pitch)) + 1
        d = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(d) < 1e-12:
            continue                     # vertical triangle: no Z crossing
        gx = ox + (np.arange(xmin, xmax) + 0.5) * pitch
        gy = oy + (np.arange(ymin, ymax) + 0.5) * pitch
        X, Y = np.meshgrid(gx, gy, indexing="ij")
        w1 = ((X - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (Y - a[1])) / d
        w2 = ((b[0] - a[0]) * (Y - a[1]) - (X - a[0]) * (b[1] - a[1])) / d
        w0 = 1.0 - w1 - w2
        insi = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not insi.any():
            continue
        Z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        ii, jj = np.nonzero(insi)
        for i, j, z in zip(ii + xmin, jj + ymin, Z[insi]):
            crossings[i * ny + j].append(float(z))
    grid = np.zeros((nx, ny, nz), dtype=np.float32)
    zc = oz + (np.arange(nz) + 0.5) * pitch
    for idx, cl in enumerate(crossings):
        if not cl:
            continue
        cl.sort()
        if len(cl) % 2:                  # defective column — skip it
            continue
        i, j = divmod(idx, ny)
        col = np.zeros(nz, dtype=bool)
        for k in range(0, len(cl), 2):
            col |= (zc > cl[k]) & (zc < cl[k + 1])
        grid[i, j] = col
    if grid.sum() == 0:
        raise ValueError("voxel remesh produced an empty volume")
    mv, mf, _, _ = marching_cubes(grid, level=0.5)
    mv = mv * pitch + np.array([ox + 0.5 * pitch, oy + 0.5 * pitch,
                                oz + 0.5 * pitch])
    # marching_cubes winding is inward for our grid convention — flip (probed:
    # OCCT accepts flipped output with positive volumes)
    return mv.astype(np.float64), np.ascontiguousarray(mf[:, ::-1]).astype(np.int64)


def decimate_guarded(verts: np.ndarray, faces: np.ndarray, budget: int,
                     ref_volume: float) -> tuple[np.ndarray, np.ndarray]:
    """Decimate to <= some rung of the budget ladder such that the result is
    (a) manifold after collapse_repair and (b) keeps its volume. Both guards
    are load-bearing: fast-simplification re-pinches meshes at unpredictable
    targets, and over-decimating a thin-walled body imploded 94% of its
    volume while staying perfectly manifold (both probed)."""
    import fast_simplification
    for mult in LADDER:
        target = int(budget * mult)
        if target >= len(faces):
            return verts, faces          # already under this rung
        dv, df = fast_simplification.simplify(
            verts.astype(np.float32), faces.astype(np.int32),
            target_count=target)
        dv, df = collapse_repair(dv.astype(np.float64), df.astype(np.int64))
        if not is_clean(df):
            continue
        if ref_volume > 0 and abs(abs(signed_volume(dv, df)) - ref_volume) \
                > VOLUME_RTOL * ref_volume:
            continue
        return dv, df
    raise ValueError(
        f"could not simplify a {len(faces):,}-triangle body below "
        f"{int(budget * LADDER[-1]):,} triangles without destroying it")


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

def repair_stl_mesh(data: bytes, budget: int = DEFAULT_BUDGET
                    ) -> tuple[list[bytes], dict]:
    """Full repair of one binary STL: returns (per-body binary STL bytes,
    report). Raises ValueError with a user-facing message when the mesh is
    beyond honest repair (holes, unsimplifiable)."""
    verts, faces = parse_binary_stl(data)
    n_in = len(faces)
    if n_in > MAX_INPUT_TRIANGLES:
        raise ValueError(
            f"mesh has {n_in:,} triangles — beyond the {MAX_INPUT_TRIANGLES:,} "
            "import limit even for auto-repair. Decimate it in a mesh tool "
            "(Blender/MeshLab) and re-export.")

    degen = ((faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2])
             | (faces[:, 0] == faces[:, 2]))
    faces = faces[~degen]
    if len(faces) == 0:
        raise ValueError("the mesh contains no usable (non-degenerate) "
                         "triangles")

    faces, healed = drop_duplicate_walls(faces)
    comps = split_components(faces, len(verts))

    # budget shares proportional to component size, floored
    sizes = np.array([len(c) for c in comps], dtype=np.float64)
    shares = np.maximum(sizes / sizes.sum() * budget,
                        MIN_COMPONENT_BUDGET).astype(int)

    pieces: list[bytes] = []
    remeshed = 0
    n_out = 0
    for ci, (fidx, share) in enumerate(zip(comps, shares)):
        f = faces[fidx]
        v_used, f_local = np.unique(f, return_inverse=True)
        cv = verts[v_used]
        cf = f_local.reshape(len(f), 3)
        boundary, overshared = edge_counts(cf)
        if boundary:
            raise ValueError(
                f"body {ci + 1} of the mesh is not watertight ({boundary} "
                "open edge(s)) — a solid needs a fully closed surface. "
                "Repair it in a mesh tool and re-export.")
        if overshared:
            cv, cf = voxel_remesh(cv, cf)
            remeshed += 1
        ref = abs(signed_volume(cv, cf))
        if len(cf) > share:
            cv, cf = decimate_guarded(cv, cf, share, ref)
        pieces.append(to_binary_stl(cv, cf))
        n_out += len(cf)

    return pieces, {"input_triangles": n_in, "output_triangles": n_out,
                    "bodies": len(comps), "healed_wall_triangles": healed,
                    "remeshed_bodies": remeshed}


if __name__ == "__main__":
    # self-test: synthetic broken meshes (no external files)
    def box_soup(ox=0.0, s=5.0, oz=0.0):
        P = [(ox, 0, oz), (ox + s, 0, oz), (ox + s, s, oz), (ox, s, oz),
             (ox, 0, oz + s), (ox + s, 0, oz + s), (ox + s, s, oz + s),
             (ox, s, oz + s)]
        F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
        return [(P[a], P[b], P[c]) for a, b, c in F]

    def soup_to_stl(tris):
        out = io.BytesIO()
        out.write(b"\0" * 80)
        out.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            out.write(struct.pack("<3f", 0, 0, 0))
            for v in (a, b, c):
                out.write(struct.pack("<3f", *v))
            out.write(struct.pack("<H", 0))
        return out.getvalue()

    ok = True
    # 1: clean disjoint boxes -> 2 bodies, untouched
    pieces, rep = repair_stl_mesh(soup_to_stl(box_soup(0) + box_soup(20)))
    print("disjoint boxes:", rep)
    ok &= rep["bodies"] == 2 and rep["output_triangles"] == 24

    # 2: two boxes stacked with a duplicated interface wall -> healed into
    # ONE body (the box_soup triangulation makes the shared face's triangles
    # exact duplicates)
    stacked = box_soup(0) + box_soup(0, oz=5.0)
    pieces, rep = repair_stl_mesh(soup_to_stl(stacked))
    print("stacked boxes:", rep)
    ok &= (rep["healed_wall_triangles"] == 4 and rep["bodies"] == 1
           and rep["output_triangles"] == 20)
    v, f = parse_binary_stl(pieces[0])
    ok &= abs(abs(signed_volume(v, f)) - 250.0) < 1e-6

    # 3: a box with a hole (2 missing triangles) -> honest refusal
    try:
        repair_stl_mesh(soup_to_stl(box_soup()[:-2]))
        print("open box: NOT refused (BAD)")
        ok = False
    except ValueError as e:
        print("open box refused:", str(e)[:60])

    v, f = parse_binary_stl(soup_to_stl(box_soup()))
    print("box volume:", signed_volume(v, f))
    ok &= abs(signed_volume(v, f) - 125.0) < 1e-9

    print("SELF-TEST", "OK" if ok else "FAILED")
