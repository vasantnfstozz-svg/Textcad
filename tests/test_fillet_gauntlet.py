"""Fillet / Chamfer × the gauntlet corpus (CLAUDE.md rule 4: an operation is the
feature TIMES the geometry).

Every edge of every nasty-but-legal body in tests/gauntlet.py — fused taper
seams, DPrism bosses, BSPLINE-typed flat walls, a hole's circles — picked ALONE
and rounded / bevelled by a small value. The contract is assert_op's: a healthy
solid or a friendly ValueError, never a kernel exception and never an invalid
"success". Plus the identity rules the tool leans on: every edge's stored form
resolves back to that very edge, and tangent chains are consistent.
"""
import pytest

import blocks
import toolplan
from tests.gauntlet import BODIES, assert_op

OPS = {"fillet": blocks.fillet_edges, "chamfer": blocks.chamfer_edges}


@pytest.mark.parametrize("name", sorted(BODIES))
@pytest.mark.parametrize("op", sorted(OPS))
def test_every_edge_picked_alone_builds_or_refuses_friendly(name, op):
    solid = BODIES[name]()
    by_edge = blocks._edge_faces(solid)
    built = refused = 0
    for e in solid.edges():
        ref = blocks.edge_ref(solid, e, by_edge)
        r = assert_op(f"{name} {op} edge@{ref['mid']}",
                      lambda: OPS[op](solid, 0.5, [ref]))
        if r is None:
            refused += 1
        else:
            built += 1
            # an absolute floor, not approx's relative one: a 0.5 round on the
            # 160-degree edge where the clipped ball's cap meets its sphere
            # removes 0.017 mm3 of a 68235 mm3 body — real work, under 1e-6 of it
            assert abs(r.volume - solid.volume) > 1e-6, f"{name}: {op} changed nothing"
            # ... and what it changed must be a BLEND of this body, not a new
            # shape: on the sliver plate of 2026-09-13 the kernel returned a
            # quarter of the part, valid and healthy (see test_fillet_tool)
            assert blocks._bbox_retreat(solid.bounding_box(), r.bounding_box())                 <= blocks._BLEND_SHRINK_FACTOR * 0.5, f"{name}: {op} moved the body's extremes"
    assert built > 0, f"{name}: no edge could be {op}ed"


@pytest.mark.parametrize("name", sorted(BODIES))
def test_every_edge_resolves_back_to_itself(name):
    solid = BODIES[name]()
    by_edge = blocks._edge_faces(solid)
    for e in solid.edges():
        ref = blocks.edge_ref(solid, e, by_edge)
        if len(ref["faces"]) == 1:              # the seam of a round face touches ONE face
            only = by_edge[blocks._shape_key(e)][0]
            assert blocks._gtype(only) != "PLANE", f"{name}: a flat face's edge with one face"
        else:
            assert len(ref["faces"]) == 2, f"{name}: an edge with {len(ref['faces'])} faces"
        got = blocks.resolve_edge(solid, ref)
        assert blocks._shape_key(got) == blocks._shape_key(e), f"{name}: {ref['mid']} resolved elsewhere"


@pytest.mark.parametrize("name", sorted(BODIES))
def test_tangent_chains_are_consistent(name):
    """membership is symmetric and every chain contains its seed — the walk
    never depends on which edge of a rim was clicked"""
    solid = BODIES[name]()
    edges = list(solid.edges())
    chains = {blocks._shape_key(e): {blocks._shape_key(c) for c in blocks.tangent_chain(solid, e)}
              for e in edges}
    for k, members in chains.items():
        assert k in members
        for m in members:
            assert chains[m] == members, f"{name}: chain differs by seed"


@pytest.mark.parametrize("name", sorted(BODIES))
def test_the_ball_points_into_the_material_on_every_edge(name):
    solid = BODIES[name]()
    by_edge = blocks._edge_faces(solid)
    for e in solid.edges():
        ball = toolplan._ball(solid, e, by_edge)
        d = ball["dir"]
        assert sum(c * c for c in d) == pytest.approx(1, abs=1e-3)
        # a step along the bisector from the edge lands INSIDE the solid
        probe = [o + 0.05 * c for o, c in zip(ball["origin"], d)]
        assert solid.is_inside(probe), f"{name}: ball at {ball['origin']} points out of the body"
