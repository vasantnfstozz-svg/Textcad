"""REVIEW-QUEUE section 9 ROUND SIX — an INDEPENDENT ground truth for
"no two polygons of one sketch may meet", and the question rounds one to five
never asked at all: does a loop meet ITSELF after the push?

Rounds one..five all measured contact with `_nearest_on_ring`, i.e. VERTEX to
polyline. That misses two things by construction:

  * two edges that CROSS (the minimum is attained in the middle of both, and
    no vertex is near anything);
  * a loop against ITSELF. `_uncross` proves each loop simple BEFORE
    `_pull_apart` moves points and before the final `_round_pts` puts them
    back on the 0.001 mm grid. Nothing re-asks afterwards.

So this probe measures segment-to-segment, exactly, on the entities as
`sketch.py` receives them (absolute mm, `e["x"] + p`), for

  * every pair of DIFFERENT loops           -> `pair_min`
  * every pair of NON-ADJACENT edges of ONE loop -> `self_min`

and reports, per trace, the true minima, what the guard's own one-way test
read, and (for anything at contact) what the kernel says about the solid.

Run:  C:/Python314/python.exe probes/imgtrace_r6_truth.py [n] [seed]
      --health  build every trace, not only the touching ones
      --self    only the self-contact sweep (no kernel builds)
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402

TOUCH = 1e-6        # closer than this, the 0.001 mm grid can merge them


def _pt_seg(p, a, b):
    """distance from points `p` to segments a->b, broadcast over the leading
    axes — p (n,1,2) against a,b (1,m,2) gives (n,m)"""
    ab = b - a
    den = (ab * ab).sum(axis=-1)
    t = np.where(den > 1e-30,
                 ((p - a) * ab).sum(axis=-1) / np.where(den > 1e-30, den, 1.0),
                 0.0)
    t = np.clip(t, 0.0, 1.0)
    q = a + t[..., None] * ab
    return np.hypot(q[..., 0] - p[..., 0], q[..., 1] - p[..., 1])


def _block(a1, a2, b1, b2):
    A1, A2 = a1[:, None, :], a2[:, None, :]
    B1, B2 = b1[None, :, :], b2[None, :, :]
    r, s = A2 - A1, B2 - B1
    den = r[..., 0] * s[..., 1] - r[..., 1] * s[..., 0]
    d = B1 - A1
    safe = np.where(np.abs(den) > 1e-18, den, 1.0)
    t = (d[..., 0] * s[..., 1] - d[..., 1] * s[..., 0]) / safe
    u = (d[..., 0] * r[..., 1] - d[..., 1] * r[..., 0]) / safe
    crosses = ((np.abs(den) > 1e-18) & (t >= 0.0) & (t <= 1.0)
               & (u >= 0.0) & (u <= 1.0))
    best = np.minimum(
        np.minimum(_pt_seg(A1, B1, B2), _pt_seg(A2, B1, B2)),
        np.minimum(_pt_seg(B1, A1, A2), _pt_seg(B2, A1, A2)))
    return np.where(crosses, 0.0, best)


def seg_seg(a1, a2, b1, b2, chunk=256):
    """EXACT segment-to-segment distance for every pair (i, j): 0 when they
    cross, otherwise the smallest of the four point-to-segment distances.
    a* are (n, 2), b* are (m, 2); returns (n, m). Chunked on the first axis
    so a few thousand edges cannot build an n x m x 2 array."""
    out = np.empty((len(a1), len(b1)))
    for s0 in range(0, len(a1), chunk):
        out[s0:s0 + chunk] = _block(a1[s0:s0 + chunk], a2[s0:s0 + chunk],
                                    b1, b2)
    return out


def rings_of(ents):
    return [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                     float) for e in ents]


def pair_min(ri, rj):
    a1, a2 = ri, np.roll(ri, -1, axis=0)
    b1, b2 = rj, np.roll(rj, -1, axis=0)
    return float(seg_seg(a1, a2, b1, b2).min())


def self_min(r):
    """the closest two NON-ADJACENT edges of one loop come — 0 means the
    polygon crosses or touches itself, which `_uncross` is there to forbid"""
    n = len(r)
    if n < 4:
        return float("inf")
    a1, a2 = r, np.roll(r, -1, axis=0)
    d = seg_seg(a1, a2, a1, a2)
    i = np.arange(n)
    adj = (np.abs(i[:, None] - i[None, :]) <= 1) | \
          (np.abs(i[:, None] - i[None, :]) >= n - 1)
    d = np.where(adj, np.inf, d)
    return float(d.min())


def guard_one_way(rs, i, j):
    size = [abs(imgtrace._area2(r)) for r in rs]
    small, big = (i, j) if size[i] <= size[j] else (j, i)
    d, _f = imgtrace._nearest_on_ring(rs[small], rs[big])
    return float(d.min())


def build(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:60]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 60
    seed = int(args[1]) if len(args) > 1 else 6_2026
    always = "--health" in sys.argv
    only_self = "--self" in sys.argv
    rng = np.random.default_rng(seed)
    traces = pair_touch = self_touch = blind = unhealthy = 0
    worst_pair, worst_self = [], []
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data, height_mm=h_mm)
                except ValueError:
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: "
                          f"{type(exc).__name__}: {str(exc)[:60]}")
                    continue
                traces += 1
                rs = rings_of(ents)
                sm = min([self_min(r) for r in rs] or [float("inf")])
                worst_self.append(sm)
                if sm < TOUCH:
                    self_touch += 1
                    who = min(range(len(rs)), key=lambda q: self_min(rs[q]))
                    print(f"  SELF {gname}{k} h={h_mm:g}: loop {who} "
                          f"({ents[who]['mode']}, {len(rs[who])} pts) meets "
                          f"itself at {sm:.9f} mm")
                    with open(os.path.join(HERE, f"_r6_self_{gname}{k}.png"),
                              "wb") as fh:
                        fh.write(data)
                pm, pi, pj = float("inf"), -1, -1
                for i in range(len(rs)):
                    for j in range(i + 1, len(rs)):
                        g = pair_min(rs[i], rs[j])
                        if g < pm:
                            pm, pi, pj = g, i, j
                if len(rs) > 1:
                    worst_pair.append(pm)
                if only_self:
                    continue
                hit = (pm < TOUCH) or (sm < TOUCH)
                if not hit and not always:
                    continue
                if pm < TOUCH:
                    pair_touch += 1
                    one = guard_one_way(rs, pi, pj)
                    if one >= TOUCH:
                        blind += 1
                    print(f"  PAIR {gname}{k} h={h_mm:g}: loops {pi},{pj} at "
                          f"{pm:.9f} mm, guard one-way {one:.9f}")
                bad, vol = build(ents)
                if bad:
                    unhealthy += 1
                    print(f"  UNHEALTHY {gname}{k} h={h_mm:g}: pair "
                          f"{pm:.9f} self {sm:.9f} -> {bad} vol {vol}")
    worst_pair.sort()
    worst_self.sort()
    print(f"\n{traces} traces")
    print(f"  loops meeting a DIFFERENT loop under {TOUCH:g} mm : {pair_touch}"
          f"  (guard's one-way blind on {blind})")
    print(f"  loops meeting THEMSELVES under {TOUCH:g} mm       : {self_touch}")
    print(f"  unhealthy solids                                 : {unhealthy}")
    if worst_pair:
        print("  closest pair gaps: "
              + ", ".join(f"{g:.9f}" for g in worst_pair[:6]))
    if worst_self:
        print("  closest self gaps: "
              + ", ".join(f"{g:.9f}" for g in worst_self[:6]))


if __name__ == "__main__":
    main()
