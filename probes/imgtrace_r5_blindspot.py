"""REVIEW-QUEUE section 9 ROUND FIVE — the picture built FOR the blind spot.

`_pull_apart` pushes the smaller loop's VERTICES off the bigger loop's
outline. The mirror — the bigger loop's vertex sitting on the middle of a
long edge of the smaller loop — is never measured, so a picture that makes
that shape walks straight through the guard.

The shape: a long horizontal SLOT (a hole with two long straight edges) with
a needle-shaped hole aimed at it a few pixels above. Douglas-Peucker moves
the needle's tip by up to `eps` pixels; the 0.001 mm grid then rounds it onto
the slot's edge exactly. The slot's own vertices are half its length away
from the needle, so the guard reads metres of clearance.

Scanned deterministically over the wall thickness, the needle's width and the
trace height — height matters because it sets mm/px and so where the 0.001 mm
grid falls.

Run:  C:/Python314/python.exe probes/imgtrace_r5_blindspot.py [--full]
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

TOUCH = 1e-6


def png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def slot_and_needle(wall, half, tipx, slot_h=26, tilt=0):
    """a plate with a long horizontal slot and a needle hole above it"""
    m = np.zeros((300, 420), np.uint8)
    cv2.rectangle(m, (10, 10), (409, 289), 1, -1)
    top = 170
    cv2.rectangle(m, (40, top), (379, top + slot_h), 0, -1)
    tip = top - wall
    cv2.fillPoly(m, [np.array([[tipx - half, tip - 70 - tilt],
                               [tipx + half, tip - 70 + tilt],
                               [tipx, tip]], np.int32)], 0)
    return m


def rings_of(ents):
    return [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                     float) for e in ents]


def gaps(ents):
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
            a, b = (i, j) if size[i] <= size[j] else (j, i)
            d, _f = imgtrace._nearest_on_ring(rs[a], rs[b])
            one_best = min(one_best, float(d.min()))
    return true_best[0], one_best, true_best[1], true_best[2]


def main():
    full = "--full" in sys.argv
    walls = range(1, 5)
    halves = (4, 7, 11, 16, 24)
    tips = (120, 165, 207, 251, 300)
    heights = [round(8.0 + 0.25 * k, 2) for k in range(0, 129)]
    n = touches = blind = unhealthy = 0
    seen = []
    for wall in walls:
        for half in halves:
            for tipx in tips:
                data = png(slot_and_needle(wall, half, tipx))
                for h_mm in heights:
                    try:
                        ents, _i = imgtrace.image_to_entities(data,
                                                              height_mm=h_mm)
                    except ValueError:
                        continue
                    n += 1
                    if len(ents) < 2:
                        continue
                    g, one, i, j = gaps(ents)
                    if g >= TOUCH:
                        continue
                    touches += 1
                    if one >= TOUCH:
                        blind += 1
                    try:
                        solid = sk.extrude_sketch(
                            sk.make_sketch("XY", 0, ents), 2.0)
                        bad = inspector.health(solid)
                        note = (bad[0] if bad else
                                f"healthy {solid.volume:.3f} mm3")
                    except Exception as exc:                # noqa: BLE001
                        note = f"SKETCH FAIL {type(exc).__name__}"
                    if "healthy" not in note:
                        unhealthy += 1
                    seen.append((wall, half, tipx, h_mm, g, one, note))
                    print(f"  wall={wall} half={half} tip={tipx} "
                          f"h={h_mm:g}: {len(ents)} loops, gap {g:.9f} "
                          f"(loops {i},{j} {ents[i]['mode']}/"
                          f"{ents[j]['mode']}), guard one-way {one:.6f} "
                          f"-> {note}")
                    if not full and unhealthy:
                        break
                if not full and unhealthy:
                    break
            if not full and unhealthy:
                break
        if not full and unhealthy:
            break
    print(f"\n{n} traces, {touches} exact touches, {blind} of them invisible "
          f"to the guard, {unhealthy} UNHEALTHY solids")


if __name__ == "__main__":
    main()
