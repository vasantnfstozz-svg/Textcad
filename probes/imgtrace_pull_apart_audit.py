"""Audit of `_pull_apart`: does it really leave NO two loops of one sketch
touching, and does it leave every loop SIMPLE?

Two things the shipped guard does not measure:

  * it walks the pairs (small, big) only — `_nearest_on_ring(arr[i], arr[j])`
    asks "how far is every VERTEX of the small loop from the big loop's
    outline". The mirror question — how far is every vertex of the BIG loop
    from the SMALL loop's outline — is never asked, and the minimum distance
    between two polylines is attained at a vertex of one OR of the other;
  * `_uncross` runs BEFORE the push, so a polygon that comes out of the push
    crossing itself is handed to sketch.py unchecked.

This probe measures the true pairwise minimum (both directions) and
re-checks every emitted polygon for self-crossings, over the pinch family
and over the round-four fuzz corpus.

Run:  C:/Python314/python.exe probes/imgtrace_pull_apart_audit.py [n]
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402


def _png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def ring_with_spokes(radius, angles, thickness=1):
    m = np.zeros((320, 420), np.uint8)
    cv2.circle(m, (210, 160), radius, 1, 30)
    for a in angles:
        cv2.line(m, (210, 160),
                 (int(210 + 300 * np.cos(a)), int(160 + 300 * np.sin(a))),
                 1, thickness)
    return m


def true_gap(ents):
    """the honest minimum distance between any two DIFFERENT entities:
    vertices of A to the outline of B **and** vertices of B to the outline
    of A. -> (gap_mm, i, j)"""
    rings = [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                      float) for e in ents]
    best = (float("inf"), -1, -1)
    for i in range(len(rings)):
        for j in range(i + 1, len(rings)):
            d1, _f = imgtrace._nearest_on_ring(rings[i], rings[j])
            d2, _f = imgtrace._nearest_on_ring(rings[j], rings[i])
            g = min(float(d1.min()), float(d2.min()))
            if g < best[0]:
                best = (g, i, j)
    return best


def one_way_gap(ents):
    """what `_pull_apart` itself looks at: small-loop vertices only."""
    rings = [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                      float) for e in ents]
    size = [abs(imgtrace._area2(r)) for r in rings]
    best = float("inf")
    for i in range(len(rings)):
        for j in range(len(rings)):
            if i == j or size[j] < size[i]:
                continue
            d, _f = imgtrace._nearest_on_ring(rings[i], rings[j])
            best = min(best, float(d.min()))
    return best


def self_crossings(ents):
    return sum(1 for e in ents
               if imgtrace._first_crossing(
                   [(e["x"] + x, e["y"] + y) for x, y in e["points"]])
               is not None)


def audit(name, data, height_mm):
    try:
        ents, _info = imgtrace.image_to_entities(data, height_mm=height_mm)
    except ValueError:
        return None
    except Exception as exc:                                # noqa: BLE001
        print(f"  TRACEBACK {name}: {type(exc).__name__}: {str(exc)[:70]}")
        return None
    if len(ents) < 2:
        return ("ok", 0, float("inf"), float("inf"))
    g, i, j = true_gap(ents)
    one = one_way_gap(ents)
    sc = self_crossings(ents)
    if g < 0.002 or sc:
        note = ""
        if HEALTH:
            import inspector
            import sketch as sk
            try:
                solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
                bad = inspector.health(solid)
                note = (f" -> UNHEALTHY {bad}" if bad else
                        f" -> healthy, {solid.volume:.2f} mm3")
            except Exception as exc:                        # noqa: BLE001
                note = f" -> SKETCH FAIL {type(exc).__name__}: {str(exc)[:50]}"
        print(f"  {name} h={height_mm:g}: {len(ents)} loops, "
              f"true gap {g:.6f} mm (loops {i},{j}), one-way gap "
              f"{one:.6f} mm, {sc} self-crossing polygons{note}")
    return ("ok", sc, g, one)


HEALTH = "--health" in sys.argv


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 120
    seed = int(args[1]) if len(args) > 1 else 917_2026
    rng = np.random.default_rng(seed)
    rows = []
    print("--- pinch family: rings cut by hairline spokes ---")
    for k in range(n):
        radius = int(rng.integers(95, 145))
        n_sp = int(rng.integers(2, 6))
        angles = tuple(float(a) for a in rng.random(n_sp) * 6.283)
        data = _png(ring_with_spokes(radius, angles))
        for h_mm in (12.0, 40.0):
            r = audit(f"ring{k}(r={radius},{n_sp})", data, h_mm)
            if r:
                rows.append(r)
    if "--rings-only" not in sys.argv:
        print("--- round-four fuzz corpus ---")
        from imgtrace_r4_fuzz import corpus
        for pname, img, _art, _cls, _drew in corpus(n):
            ok, buf = cv2.imencode(".png", img)
            assert ok
            for h_mm in (15.0, 45.0):
                r = audit(pname, buf.tobytes(), h_mm)
                if r:
                    rows.append(r)
    sc = sum(r[1] for r in rows)
    touch = [r for r in rows if r[2] < 0.002]
    blind = [r for r in rows if r[2] < 0.002 <= r[3]]
    print(f"\n{len(rows)} traces measured")
    print(f"  self-crossing polygons emitted : {sc}")
    print(f"  pairs closer than 0.002 mm     : {len(touch)}")
    print(f"  ...of which `_pull_apart`'s own one-way test calls CLEAR: "
          f"{len(blind)}")
    if touch:
        print(f"  worst true gap {min(r[2] for r in touch):.6f} mm")


if __name__ == "__main__":
    main()
