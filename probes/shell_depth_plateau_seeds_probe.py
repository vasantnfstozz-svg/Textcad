"""What actually gets a seed onto the TAPER when a PLATEAU outranks it?

LAUNCH-PLAN section 10: `_climb_to_the_deepest` climbs the three DEEPEST
sampled points, and a uniform region measures exactly what its chord allows,
so an 80 x 80 x 24 slab's mid-plane (12.0000 everywhere) outranks every station
on the 2-to-30 mm draft wedge fused into it, whose real maximum is 12.4300.
Already measured out as NOT the fix: 24 seeds (the slab holds dozens of points
at exactly 12.0, all more than 12 mm apart, so they take every seed) and 400
steps (a plateau has no gradient to climb).

This probe does not argue; it dumps what the sampler actually saw and then runs
the candidate seedings side by side on the SAME measured points, counting every
`BRepExtrema` call so the cost is a number too.

  A. today          the three deepest, spread by their own radius
  B. grid           one candidate per cell of a coarse spatial grid, scouted
                    with a few steps, then the best few climbed in full
                    (the candidate LAUNCH-PLAN records)
  C. slack          ranked by bound - depth: a station's chord already says how
                    much material COULD be there, and on a plateau the station
                    measures exactly that, so its slack is zero

    python probes/shell_depth_plateau_seeds_probe.py
    python probes/shell_depth_plateau_seeds_probe.py --body wedge_in_slab
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import build123d as b3d  # noqa: E402

import sketch as sk  # noqa: E402


def wedge_in_slab():
    """the LAUNCH-PLAN repro: ONE solid, 155,657.143 mm3"""
    w = b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-40, 0), (40, 0), (40, 30), (-40, 2), close=True)), 40)
    slab = b3d.Pos(0, -30.0, 12.0) * b3d.Box(80, 80, 24)
    return b3d.Part() + (w + slab)


def long_draft_prism():
    return b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-90, 0), (90, 0), (90, 34), (-90, 2), close=True)), 40)


def ramped_plate():
    return b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-60, 0), (60, 0), (60, 8), (10, 26), (-60, 8), close=True)), 50)


def plateau_pair():
    """a uniform 20 mm slab with a fat post on it: the slab's plateau is 10.0
    everywhere and the post's centre is deeper"""
    return b3d.Part() + (b3d.Pos(0, 0, 10) * b3d.Box(120, 80, 20)
                         + b3d.Pos(40, 0, 32) * b3d.Box(34, 34, 24))


BODIES = {"wedge_in_slab": wedge_in_slab, "long_draft_prism": long_draft_prism,
          "ramped_plate": ramped_plate, "plateau_pair": plateau_pair}


# ---------------------------------------------------------------------------
# the sampler, re-run here so every measured station can be kept
# ---------------------------------------------------------------------------

def sample(solid, openings=()):
    """`deepest_material`'s stations and the depth of each, with the station's
    own upper BOUND kept alongside — a copy of the real loop, stopped nowhere,
    so the probe sees what the guard saw plus what it never kept."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.TopoDS import TopoDS_Compound
    from build123d import Vector
    faces = solid.faces()
    n = len(faces)
    tol = max(1e-3, 1e-4 * float(solid.bounding_box().diagonal))
    per_face = max(1, min(sk._DEPTH_RAYS_PER_FACE, sk._DEPTH_RAY_BUDGET // (n * n)))

    def stays(f):
        return not any(f.IsSame(o.wrapped) for o in openings)

    staying = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(staying)
    for f in faces:
        if stays(f.wrapped):
            builder.Add(staying, f.wrapped)
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(solid.wrapped, 1e-6)

    def samples(face):
        verts, tris = face.tessellate(tol)
        m = len(tris)
        picks = list(range(m)) if m <= per_face else [(k * m) // per_face
                                                      for k in range(per_face)]
        pts = []
        for k in picks:
            a, b, c = (verts[i] for i in tris[k])
            for wa, wb, wc in sk._barycentres(max(1, per_face // max(1, len(picks)))):
                pts.append(a * wa + b * wb + c * wc)
        centre = face.center()
        if face.is_inside(centre):
            pts.append(centre)
        return pts

    stations = []
    for face in faces:
        if not stays(face.wrapped):
            for q in samples(face):
                stations.append((float("inf"), q))
            continue
        for p in samples(face):
            nrm = face.normal_at(p)
            inter.Perform(gp_Lin(gp_Pnt(*(p - nrm * (2 * tol))), gp_Dir(*(-nrm))), 0.0, 1e9)
            if not inter.IsDone() or inter.NbPnt() == 0:
                continue
            hit = min(range(1, inter.NbPnt() + 1), key=inter.WParameter)
            chord = inter.WParameter(hit) + 2 * tol
            far_stays = stays(inter.Face(hit))
            for f in sk._DEPTH_STATIONS + (() if far_stays else sk._DEPTH_STATIONS_TO_OPENING):
                bound = min(f, 1 - f) * chord if far_stays else f * chord
                stations.append((bound, p - nrm * (f * chord)))
    stations.sort(key=lambda st: -st[0])

    ext = BRepExtrema_DistShapeShape()
    ext.LoadS1(staying)
    calls = [0]

    def measure(q):
        calls[0] += 1
        ext.LoadS2(BRepBuilderAPI_MakeVertex(gp_Pnt(q.X, q.Y, q.Z)).Vertex())
        ext.Perform()
        if not ext.IsDone() or ext.NbSolution() < 1:
            return None, None
        near = ext.PointOnShape1(1)
        return float(ext.Value()), Vector(near.X(), near.Y(), near.Z())

    # the guard's own stopping rule, with t = infinity (the refusing case)
    best = (0.0, stations[0][1])
    seen = []
    for bound, q in stations:
        if bound <= best[0]:
            break
        d, _near = measure(q)
        if d is None:
            continue
        seen.append((d, q, bound))
        if d > best[0]:
            best = (d, q)
    return solid, measure, calls, seen, best, tol


# ---------------------------------------------------------------------------
# the climb, with the seeding swapped out
# ---------------------------------------------------------------------------

def climb(solid, measure, seeds, best, tol, steps):
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(solid.wrapped)

    def outside(q):
        cls.Perform(gp_Pnt(q.X, q.Y, q.Z), 1e-7)
        return cls.State() == TopAbs_State.TopAbs_OUT

    out = []
    for d0, q0 in seeds:
        q, d = q0, d0
        step, near = max(d0, tol), None
        for _ in range(steps):
            if near is None:
                got = measure(q)
                if got[0] is None:
                    break
                d, near = got
            away = q - near
            reach = away.length
            if reach <= 1e-9:
                break
            cand = q + away * (step / reach)
            got = (None, None) if outside(cand) else measure(cand)
            if got[0] is not None and got[0] > d:
                q, d, near = cand, got[0], got[1]
            else:
                step *= 0.5
                if step <= tol * 0.25:
                    break
        out.append((d, q))
        if d > best[0]:
            best = (d, q)
    return best, out


def seeds_today(seen, best, tol, k):
    picked, taken = [], []
    for d0, q0, _b in sorted(seen, key=lambda r: -r[0]):
        if len(picked) >= k:
            break
        if all((q0 - p).length > max(d0, tol) for p in taken):
            picked.append((d0, q0))
            taken.append(q0)
    return picked or [best]


def seeds_grid(solid, seen, cells):
    """the deepest measured point of each cell of a coarse spatial grid"""
    bb = solid.bounding_box()
    lo = (bb.min.X, bb.min.Y, bb.min.Z)
    span = (max(bb.size.X, 1e-9), max(bb.size.Y, 1e-9), max(bb.size.Z, 1e-9))
    pick = {}
    for d0, q0, _b in seen:
        key = tuple(min(cells - 1, int((c - lo[i]) / span[i] * cells))
                    for i, c in enumerate((q0.X, q0.Y, q0.Z)))
        if key not in pick or d0 > pick[key][0]:
            pick[key] = (d0, q0)
    return sorted(pick.values(), key=lambda r: -r[0])


def seeds_slack(seen, k):
    """ranked by how much MORE material the station's own chord allows"""
    scored = [(b - d0, d0, q0) for d0, q0, b in seen if b != float("inf")]
    return [(d0, q0) for _s, d0, q0 in sorted(scored, key=lambda r: -r[0])[:k]]


def spread(ranked, tol, k):
    """take `k` of an already-ranked list, each further than its own radius from
    the ones taken — the rule the shipped code uses to keep three seeds off one
    ray"""
    picked, taken = [], []
    for score, d0, q0 in ranked:
        if len(picked) >= k:
            break
        if all((q0 - p).length > max(d0, tol) for p in taken):
            picked.append((d0, q0))
            taken.append(q0)
    return picked


def seeds_room(seen, tol, k):
    """ranked by bound / depth: how much room the station's own chord says there
    could be, against what it actually measured.

    A PLATEAU measures exactly what its chord allows, so its ratio is 1.0 — the
    lowest any station can score — while a station beside a taper scores high
    because its ray passed through material its own point is nowhere near."""
    ranked = sorted(((b / max(d0, 1e-9), d0, q0) for d0, q0, b in seen
                     if b != float("inf")), key=lambda r: -r[0])
    return spread(ranked, tol, k)


def seeds_depth(seen, tol, k):
    return spread(sorted(((d0, d0, q0) for d0, q0, _b in seen), key=lambda r: -r[0]),
                  tol, k)


def seeds_room_deep(seen, tol, k, best):
    """bound / depth, but only among stations already half as deep as the best —
    a plateau's neighbour on a THICKER region is deep AND has room"""
    ranked = sorted(((b / max(d0, 1e-9), d0, q0) for d0, q0, b in seen
                     if b != float("inf") and d0 >= 0.5 * best),
                    key=lambda r: -r[0])
    return spread(ranked, tol, k)


def seeds_reach(seen, tol, k):
    """bound^2 / depth: how far the station's chord reaches, weighted by how far
    short of it the station measured. One number instead of two rankings."""
    ranked = sorted(((b * b / max(d0, 1e-9), d0, q0) for d0, q0, b in seen
                     if b != float("inf")), key=lambda r: -r[0])
    return spread(ranked, tol, k)


def main() -> int:
    from shell_depth_oracle_probe import oracle_depth
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", default=None)
    ap.add_argument("--cells", type=int, default=3)
    ap.add_argument("--scout", type=int, default=6)
    args = ap.parse_args()
    names = [args.body] if args.body else list(BODIES)
    for name in names:
        solid = BODIES[name]()
        print(f"\n=== {name}: {len(solid.faces())} faces, {len(solid.solids())} lump(s), "
              f"{solid.volume:,.3f} mm3", flush=True)
        truth, at = oracle_depth(solid, coarse=20, refine=4)
        print(f"    oracle deepest = {truth:.4f} at "
              f"({at[0]:.2f}, {at[1]:.2f}, {at[2]:.2f})", flush=True)
        solid, measure, calls, seen, best, tol = sample(solid)
        print(f"    {len(seen)} stations measured, best sample {best[0]:.4f}, "
              f"{calls[0]} distance calls", flush=True)
        levels = {}
        for d0, _q, _b in seen:
            levels[round(d0, 6)] = levels.get(round(d0, 6), 0) + 1
        top = sorted(levels.items(), key=lambda r: -r[0])[:6]
        print(f"    deepest sample levels (depth x count): "
              + ", ".join(f"{d:.4f}x{c}" for d, c in top), flush=True)

        plans = [
            ("A today ", seeds_today(seen, best, tol, sk._DEPTH_CLIMB_SEEDS), 40, ""),
            ("B grid  ", seeds_grid(solid, seen, args.cells), args.scout, "scout"),
            ("C slack ", seeds_slack(seen, sk._DEPTH_CLIMB_SEEDS), 40, ""),
            ("D all   ", [(d, q) for d, q, _b in seen], 40, "ceiling"),
            ("E 3+1   ", seeds_depth(seen, tol, 3) + seeds_room(seen, tol, 1), 40, ""),
            ("E 3+3   ", seeds_depth(seen, tol, 3) + seeds_room(seen, tol, 3), 40, ""),
            ("F 3+3+3 ", seeds_depth(seen, tol, 3) + seeds_room(seen, tol, 3)
             + seeds_room_deep(seen, tol, 3, best[0]), 40, ""),
            ("G reach3", seeds_depth(seen, tol, 3) + seeds_reach(seen, tol, 3), 40, ""),
            ("G reach6", seeds_depth(seen, tol, 3) + seeds_reach(seen, tol, 6), 40, ""),
        ]
        for label, picked, steps, mode in plans:
            before = calls[0]
            got, each = climb(solid, measure, picked, best, tol, steps)
            note = ""
            if mode == "scout":
                order = sorted(range(len(each)), key=lambda i: -each[i][0])
                full = [(each[i][0], each[i][1]) for i in order[:sk._DEPTH_CLIMB_SEEDS]]
                got, _ = climb(solid, measure, full, got, tol, 40)
                note = f" ({len(picked)} cells scouted, {args.scout} steps each)"
            if mode == "ceiling":
                win = max(range(len(each)), key=lambda i: each[i][0])
                d0, q0, b0 = seen[win]
                ranks = {
                    "depth": sorted(range(len(seen)), key=lambda i: -seen[i][0]),
                    "bound": sorted(range(len(seen)), key=lambda i: -seen[i][2]),
                    "slack": sorted(range(len(seen)), key=lambda i: -(seen[i][2] - seen[i][0])),
                    "bound/depth": sorted(range(len(seen)),
                                          key=lambda i: -(seen[i][2] / max(seen[i][0], 1e-9))),
                }
                where = ", ".join(f"{k} #{v.index(win) + 1}" for k, v in ranks.items())
                note = (f"\n              the winner: depth {d0:.4f}, bound {b0:.4f}, at "
                        f"({q0.X:.2f}, {q0.Y:.2f}, {q0.Z:.2f}); rank by {where} "
                        f"of {len(seen)}")
                # how many seeds each ranking needs before it takes the winner
                for k, v in ranks.items():
                    top = v[:8]
                    got8, _ = climb(solid, measure, [(seen[i][0], seen[i][1]) for i in top],
                                    (0.0, q0), tol, 40)
                    note += f"\n              top-8 by {k:12s} -> {got8[0]:9.4f}"
            spent = calls[0] - before
            gap = truth - got[0]
            print(f"    {label} -> {got[0]:9.4f}  gap {gap:+8.4f}  "
                  f"{spent:5d} distance calls{note}"
                  + ("   <<< FINDS IT" if gap <= max(0.05, 0.01 * truth) else ""),
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
