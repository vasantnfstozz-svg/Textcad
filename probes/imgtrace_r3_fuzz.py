"""REVIEW-QUEUE section 9 round THREE — an independent fuzz of the tracer.

Different generators and a different seed from round two's sweep, and it
measures the things round two's sweep did NOT:

  * pieces: the number of `add` entities against the number of connected
    pieces the traceable mask really has — a trace with MORE pieces than the
    picture has INVENTED material;
  * excess: traced area ABOVE the picture's ink, not only the shortfall
    (`_uncross` keeping a loop can only add);
  * overlap: two `add` entities from the SAME contour whose rasters
    intersect — the new geometry round two started emitting;
  * self-crossings and solid health, as before.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_fuzz.py [n_pictures]
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
from imgtrace_r3_uncross import overlaps                    # noqa: E402


def png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def crossings(pts):
    n = len(pts)
    a = np.asarray(pts, float)
    r = np.roll(a, -1, axis=0) - a
    hits = 0
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            den = r[i, 0] * r[j, 1] - r[i, 1] * r[j, 0]
            if abs(den) < 1e-15:
                continue
            d = a[j] - a[i]
            t = (d[0] * r[j, 1] - d[1] * r[j, 0]) / den
            u = (d[0] * r[i, 1] - d[1] * r[i, 0]) / den
            hits += 0 <= t <= 1 and 0 <= u <= 1
    return hits


def corpus(n):
    """pictures built to make the tracer touch itself: hairline joins,
    ribbons that fold back through themselves, combs, rings with spokes"""
    rng = np.random.default_rng(20260917)
    for k in range(n):
        h, w = 320, 420
        m = np.zeros((h, w), np.uint8)
        kind = k % 7
        if kind == 0:                                   # blobs + hairlines
            pts = rng.integers(50, 280, (int(rng.integers(2, 6)), 2))
            for p in pts:
                cv2.circle(m, (int(p[1]), int(p[0])),
                           int(rng.integers(20, 60)), 1, -1)
            for _ in range(int(rng.integers(1, 4))):
                a = pts[int(rng.integers(0, len(pts)))]
                b = rng.integers(50, 280, 2)
                cv2.line(m, (int(a[1]), int(a[0])), (int(b[1]), int(b[0])),
                         1, int(rng.integers(1, 3)))
        elif kind == 1:                                 # a ribbon folded back
            y = int(rng.integers(90, 160))
            cv2.rectangle(m, (30, y - 50), (390, y - 2), 1, -1)
            cv2.rectangle(m, (30, y + 2), (390, y + 50), 1, -1)
            for x in rng.integers(60, 360, int(rng.integers(1, 4))):
                m[y - 2:y + 3, int(x):int(x) + int(rng.integers(1, 3))] = 1
        elif kind == 2:                                 # comb of thin teeth
            cv2.rectangle(m, (40, 180), (380, 280), 1, -1)
            t = int(rng.integers(1, 4))
            for i in range(int(rng.integers(6, 20))):
                m[60:180, 50 + i * 16:50 + i * 16 + t] = 1
        elif kind == 3:                                 # ring with spokes
            cv2.circle(m, (210, 160), int(rng.integers(90, 140)), 1, 30)
            for ang in rng.uniform(0, 6.28, int(rng.integers(1, 5))):
                cv2.line(m, (210, 160),
                         (int(210 + 200 * np.cos(ang)),
                          int(160 + 200 * np.sin(ang))),
                         1, int(rng.integers(1, 4)))
        elif kind == 4:                                 # text-like bars
            for i in range(int(rng.integers(3, 9))):
                x = 30 + i * 45
                cv2.rectangle(m, (x, 90), (x + int(rng.integers(8, 34)), 230),
                              1, -1)
                if rng.random() < 0.5:
                    m[155:157, x:x + 60] = 1
        elif kind == 5:                                 # random polygons
            for _ in range(int(rng.integers(1, 4))):
                q = rng.integers(30, 300, (int(rng.integers(3, 9)), 2))
                cv2.fillPoly(m, [q[:, ::-1].astype(np.int32)], 1)
        else:                                           # speckle + blobs
            cv2.circle(m, (200, 160), int(rng.integers(60, 120)), 1, -1)
            ys = rng.integers(0, h, 40)
            xs = rng.integers(0, w, 40)
            for yy, xx in zip(ys, xs):
                m[int(yy):int(yy) + 2, int(xx):int(xx) + 2] = 1
        if int(m.sum()) >= 600:
            yield f"f{k}", m


def main():
    n_pics = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    tot = cross_tot = bad_tot = extra_pieces = over_pairs = 0
    worst_short = worst_excess = (0.0, "")
    refused = 0
    for name, m in corpus(n_pics):
        data = png(m)
        for h_mm in (12.0, 40.0, 90.0):
            try:
                ents, info = imgtrace.image_to_entities(data, height_mm=h_mm)
            except Exception:                               # noqa: BLE001
                refused += 1
                continue
            tot += 1
            cross_tot += sum(crossings(e["points"]) for e in ents)
            # the ink is measured on the mask the module ITSELF traces, at
            # the scale it itself uses - otherwise dropped speckles make the
            # two numbers answer different questions
            solid, _ma = imgtrace._traceable(
                imgtrace._mask_from_image(
                    cv2.imdecode(np.frombuffer(data, np.uint8),
                                 cv2.IMREAD_UNCHANGED)), h_mm)
            sy, _sx = np.where(solid)
            mm_px = h_mm / (int(sy.max()) - int(sy.min()) + 1)
            ink = float(solid.sum()) * mm_px * mm_px
            n_true = cv2.connectedComponents(solid, 8)[0] - 1
            n_add = sum(1 for e in ents if e["mode"] == "add")
            if n_add > n_true:
                extra_pieces += 1
                print(f"  MORE PIECES  {name} at {h_mm:g} mm: "
                      f"{n_add} add entities, picture has {n_true}")
            adds = [[(e["x"] + p[0], e["y"] + p[1]) for p in e["points"]]
                    for e in ents if e["mode"] == "add"]
            if 1 < len(adds) <= 12:
                ov = overlaps(adds)
                if ov:
                    over_pairs += len(ov)
                    biggest = max(ov, key=lambda t: t[2])
                    print(f"  OVERLAP      {name} at {h_mm:g} mm: "
                          f"{biggest[2]:.2f} mm2 between two add entities")
            try:
                s = sk.make_sketch("XY", 0, ents)
                area = s.area
                if inspector.health(sk.extrude_sketch(s, 2.0)):
                    bad_tot += 1
                    print(f"  UNHEALTHY    {name} at {h_mm:g} mm")
            except Exception as exc:                        # noqa: BLE001
                bad_tot += 1
                print(f"  SKETCH FAIL  {name} at {h_mm:g} mm: "
                      f"{type(exc).__name__}: {str(exc)[:60]}")
                continue
            short = (ink - area) / ink
            excess = (area - ink) / ink
            if short > worst_short[0]:
                worst_short = (short, f"{name} at {h_mm:g} mm")
            if excess > worst_excess[0]:
                worst_excess = (excess, f"{name} at {h_mm:g} mm")
    print(f"\n{tot} traces ({refused} refused with a sentence)")
    print(f"  self-crossing edges in the entities handed to sketch.py: "
          f"{cross_tot}")
    print(f"  invalid / unhealthy solids: {bad_tot}")
    print(f"  traces with MORE add pieces than the picture: {extra_pieces}")
    print(f"  overlapping pairs of add entities: {over_pairs}")
    print(f"  worst shortfall vs the ink: {100 * worst_short[0]:.2f}% "
          f"({worst_short[1]})")
    print(f"  worst EXCESS over the ink:  {100 * worst_excess[0]:.2f}% "
          f"({worst_excess[1]})")


if __name__ == "__main__":
    main()
