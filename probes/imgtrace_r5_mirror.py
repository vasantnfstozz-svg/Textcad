"""REVIEW-QUEUE section 9 ROUND FIVE — the direction `_pull_apart` never asks.

`_pull_apart` walks the pairs (small, big) and calls
`_nearest_on_ring(small, big)`: how far is every VERTEX of the smaller loop
from the bigger loop's OUTLINE. The mirror question — how far is every vertex
of the BIGGER loop from the smaller loop's outline — is never asked, and the
minimum distance between two polylines is attained at a vertex of one OR of
the other. Round four measured that 49 of 50 residual pairs within 0.002 mm
are invisible to the guard's own test but found none that built an unhealthy
solid, and left the question open.

This probe hunts for the picture that closes it: it traces a corpus built to
put hole loops a hair apart, measures the TRUE pairwise minimum (both
directions), and builds the 2 mm extrusion of every trace whose true minimum
is under a micron — the distance at which the 0.001 mm coordinate grid can
put two loops on the same point exactly and pinch the face.

Run:  C:/Python314/python.exe probes/imgtrace_r5_mirror.py [n] [seed]
      --health   build every trace, not only the sub-micron ones
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
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402

TOUCH = 1e-6        # closer than this, the 0.001 grid can merge them
# the height sets mm/px and so where the 0.001 mm grid falls: an exact
# contact is a grid coincidence, so the sweep walks the heights too
HEIGHTS = (9.5, 12.0, 17.3, 25.0, 33.7, 40.0)


def png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def ring_with_spokes(rng):
    """round four's own pinch family: a ring cut by hairline spokes"""
    m = np.zeros((320, 420), np.uint8)
    cv2.circle(m, (210, 160), int(rng.integers(95, 145)), 1, 30)
    for _ in range(int(rng.integers(2, 6))):
        a = float(rng.random() * 6.283)
        cv2.line(m, (210, 160),
                 (int(210 + 300 * np.cos(a)), int(160 + 300 * np.sin(a))),
                 1, int(rng.integers(1, 3)))
    return m


def pierced_plate(rng):
    """a plate whose HOLES are separated by 1-4 px walls — the loops that
    pinch a face are hole loops, and this is how a picture makes pairs of
    them a hair apart"""
    m = np.zeros((300, 400), np.uint8)
    cv2.rectangle(m, (20, 20), (379, 279), 1, -1)
    n = int(rng.integers(3, 9))
    cy = int(rng.integers(90, 200))
    x = 40
    for _ in range(n):
        r = int(rng.integers(12, 40))
        kind = int(rng.integers(0, 3))
        dy = int(rng.integers(-12, 13))
        if kind == 0:
            cv2.circle(m, (x + r, cy + dy), r, 0, -1)
        elif kind == 1:
            cv2.rectangle(m, (x, cy + dy - r), (x + 2 * r, cy + dy + r), 0, -1)
        else:
            tri = np.array([[x, cy + dy + r], [x + 2 * r, cy + dy + r],
                            [x + r, cy + dy - r]], np.int32)
            cv2.fillPoly(m, [tri], 0)
        x += 2 * r + int(rng.integers(1, 5))         # a 1-4 px wall
        if x > 350:
            break
    return m


def comb_slots(rng):
    """long horizontal slots with needle-shaped holes aimed at them — the
    exact shape of the blind spot: a vertex of one loop on the MIDDLE of a
    long straight edge of another"""
    m = np.zeros((320, 420), np.uint8)
    cv2.rectangle(m, (10, 10), (409, 309), 1, -1)
    y = 40
    for _ in range(int(rng.integers(2, 5))):
        cv2.rectangle(m, (30, y), (380, y + int(rng.integers(8, 25))), 0, -1)
        top = y
        for k in range(int(rng.integers(2, 7))):
            x = int(rng.integers(50, 360))
            gap = int(rng.integers(1, 4))
            tip = top - gap
            tri = np.array([[x - int(rng.integers(3, 20)), tip - 40],
                            [x + int(rng.integers(3, 20)), tip - 40],
                            [x, tip]], np.int32)
            cv2.fillPoly(m, [tri], 0)
            _ = k
        y += int(rng.integers(55, 95))
        if y > 250:
            break
    return m


def nested_rings(rng):
    """concentric rings with 1-3 px walls"""
    m = np.zeros((340, 340), np.uint8)
    r = int(rng.integers(150, 165))
    while r > 12:
        t = int(rng.integers(4, 14))
        cv2.circle(m, (170, 170), r, 1, t)
        r -= t + int(rng.integers(1, 4))
    return m


GENS = [("ring", ring_with_spokes), ("plate", pierced_plate),
        ("comb", comb_slots), ("rings", nested_rings)]


def rings_of(ents):
    return [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                     float) for e in ents]


def gaps(ents):
    """-> (true_min, one_way_min_the_guard_sees, i, j)"""
    rs = rings_of(ents)
    size = [abs(imgtrace._area2(r)) for r in rs]
    true_best, one_best = (float("inf"), -1, -1), float("inf")
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            d1, _f = imgtrace._nearest_on_ring(rs[i], rs[j])
            d2, _f = imgtrace._nearest_on_ring(rs[j], rs[i])
            g = min(float(d1.min()), float(d2.min()))
            if g < true_best[0]:
                true_best = (g, i, j)
            small, big = (i, j) if size[i] <= size[j] else (j, i)
            d, _f = imgtrace._nearest_on_ring(rs[small], rs[big])
            one_best = min(one_best, float(d.min()))
    return true_best[0], one_best, true_best[1], true_best[2]


def contact_kind(ents, i, j):
    """"cross" when the two loops genuinely overlap (harmless — a cut cuts
    the union), "tangent" when they only meet, which is the pinch."""
    ri, rj = rings_of(ents)[i], rings_of(ents)[j]
    a = np.asarray(ri, np.float32)
    ins = [cv2.pointPolygonTest(a, (float(p[0]), float(p[1])), False)
           for p in rj]
    n_in = sum(1 for v in ins if v > 0)
    n_out = sum(1 for v in ins if v < 0)
    return "cross" if n_in and n_out else "tangent"


def build(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:60]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 200
    seed = int(args[1]) if len(args) > 1 else 5_2026
    always = "--health" in sys.argv
    rng = np.random.default_rng(seed)
    traces = touches = blind = unhealthy = 0
    worst = []
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
                if len(ents) < 2:
                    continue
                g, one, i, j = gaps(ents)
                worst.append(g)
                if g >= TOUCH and not always:
                    continue
                if g < TOUCH:
                    touches += 1
                    if one >= TOUCH:
                        blind += 1
                bad, vol = build(ents)
                if g < TOUCH:
                    with open(os.path.join(HERE,
                                           f"_r5_touch_{gname}{k}.png"),
                              "wb") as fh:
                        fh.write(data)
                    print(f"  TOUCH {gname}{k} h={h_mm:g}: {len(ents)} loops, "
                          f"gap {g:.9f} loops {i},{j} "
                          f"({ents[i]['mode']}/{ents[j]['mode']}, "
                          f"{contact_kind(ents, i, j)}), guard's "
                          f"one-way {one:.9f} -> {bad or 'healthy'} "
                          f"vol {vol}")
                if bad:
                    unhealthy += 1
                    print(f"  UNHEALTHY {gname}{k} h={h_mm:g}: {len(ents)} "
                          f"loops, true gap {g:.9f} (loops {i},{j}), guard's "
                          f"one-way {one:.9f} -> {bad} vol {vol}")
    worst.sort()
    print(f"\n{traces} traces")
    print(f"  pairs at a true gap under {TOUCH:g} mm : {touches}")
    print(f"  ...of which the guard's own test calls clear: {blind}")
    print(f"  unhealthy solids                          : {unhealthy}")
    if worst:
        print(f"  closest true gaps: "
              f"{', '.join(f'{g:.9f}' for g in worst[:6])}")


if __name__ == "__main__":
    main()
