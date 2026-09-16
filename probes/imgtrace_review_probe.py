"""probes/imgtrace_review_probe.py - REVIEW-QUEUE section 9 (Trace image).

Measures, never infers:
  1. input limits: a 16-bit PNG, a tiny height on detailed art, alpha-only,
     a flat-white JPG - each must give a SENTENCE, not a library traceback.
  2. entity quality: self-intersection, duplicate points, <3 points,
     sub-0.1mm edges in what image_to_entities hands sketch.py.
  3. orientation: is traced art ever MIRRORED (plane sketch / face sketch)?
  4. holes: nested contours deeper than two.

Run:  C:\\Python314\\python.exe probes/imgtrace_review_probe.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import imgtrace  # noqa: E402


def png(c):
    ok, b = cv2.imencode(".png", c)
    assert ok
    return b.tobytes()


def show(name, fn):
    try:
        r = fn()
        print(f"[{name}] OK -> {r[1] if isinstance(r, tuple) else r}")
        return r
    except Exception as e:
        print(f"[{name}] {type(e).__name__}: {str(e)[:300]}")
        return None


def seg_hit(a, b, c, d):
    """proper crossing of ab and cd (shared endpoints do not count)"""
    def o(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 1e-12) - (v < -1e-12)
    o1, o2, o3, o4 = o(a, b, c), o(a, b, d), o(c, d, a), o(c, d, b)
    return o1 != o2 and o3 != o4 and o1 and o2 and o3 and o4


def audit(ents, label):
    bad = []
    for k, e in enumerate(ents):
        p = [(x, y) for x, y in e["points"]]
        n = len(p)
        if n < 3:
            bad.append(f"ent{k}: {n} points")
            continue
        dup = sum(1 for i in range(n) if p[i] == p[(i + 1) % n])
        if dup:
            bad.append(f"ent{k}: {dup} duplicate consecutive points")
        # non-consecutive coincident points (a pinch)
        if len(set(p)) != n:
            bad.append(f"ent{k}: {n - len(set(p))} repeated (non-adjacent) points")
        mn = min(np.hypot(p[(i + 1) % n][0] - p[i][0],
                          p[(i + 1) % n][1] - p[i][1]) for i in range(n))
        if mn < 0.1:
            bad.append(f"ent{k}: shortest edge {mn:.4f}mm (< 0.1mm grid)")
        hits = 0
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                if seg_hit(p[i], p[(i + 1) % n], p[j], p[(j + 1) % n]):
                    hits += 1
        if hits:
            bad.append(f"ent{k}: {hits} SELF-INTERSECTIONS")
    print(f"  {label}: {len(ents)} entities, "
          + ("; ".join(bad) if bad else "clean"))
    return bad


def part1_limits():
    print("=== 1. input limits ===")
    i16 = np.full((300, 300, 3), 65535, np.uint16)
    cv2.rectangle(i16, (100, 50), (200, 250), (0, 0, 0), -1)
    show("16-bit PNG, opaque, dark art",
         lambda: imgtrace.image_to_entities(png(i16), height_mm=40))
    show("16-bit PNG aspect", lambda: imgtrace.artwork_aspect(png(i16)))

    i16a = np.zeros((300, 300, 4), np.uint16)
    cv2.circle(i16a, (150, 150), 100, (0, 0, 0, 65535), -1)
    show("16-bit RGBA",
         lambda: imgtrace.image_to_entities(png(i16a), height_mm=40))

    big = np.zeros((2000, 2000, 4), np.uint8)
    for i in range(10):
        cv2.rectangle(big, (100 + i * 180, 100), (100 + i * 180 + 60, 1900),
                      (0, 0, 0, 255), -1)
    for h in (50.0, 5.0, 2.0, 1.0):
        show(f"thin strokes, height_mm={h}",
             lambda h=h: imgtrace.image_to_entities(png(big), height_mm=h))

    tr = np.zeros((200, 200, 4), np.uint8)
    show("fully transparent",
         lambda: imgtrace.image_to_entities(png(tr), height_mm=20))
    show("fully transparent aspect", lambda: imgtrace.artwork_aspect(png(tr)))

    white = np.full((200, 200, 3), 255, np.uint8)
    ok, b = cv2.imencode(".jpg", white)
    show("flat white JPG",
         lambda: imgtrace.image_to_entities(b.tobytes(), height_mm=20))

    g = np.full((200, 200), 255, np.uint8)
    cv2.circle(g, (100, 100), 50, 0, -1)
    show("grayscale 1-channel",
         lambda: imgtrace.image_to_entities(png(g), height_mm=20))

    show("garbage bytes",
         lambda: imgtrace.image_to_entities(b"not an image", height_mm=20))
    show("garbage bytes aspect", lambda: imgtrace.artwork_aspect(b"nope"))


def part2_entities():
    print("=== 2. entity quality ===")
    # a) donut
    d = np.zeros((400, 400, 4), np.uint8)
    cv2.circle(d, (200, 200), 150, (10, 10, 10, 255), -1)
    cv2.circle(d, (200, 200), 60, (0, 0, 0, 0), -1)
    ents, info = imgtrace.image_to_entities(png(d), height_mm=50)
    audit(ents, f"donut {info}")

    # b) a pinched hourglass - DP is most likely to cross itself at a neck
    hg = np.zeros((600, 600, 4), np.uint8)
    pts = np.array([[100, 50], [500, 50], [310, 295], [500, 550],
                    [100, 550], [290, 305]], np.int32)
    cv2.fillPoly(hg, [pts], (0, 0, 0, 255))
    ents, info = imgtrace.image_to_entities(png(hg), height_mm=30)
    audit(ents, f"pinched neck {info}")

    # c) high-res art traced small: the smoothing floor in mm
    comb = np.zeros((2000, 1200, 4), np.uint8)
    cv2.rectangle(comb, (100, 100), (1100, 800), (0, 0, 0, 255), -1)
    for i in range(12):
        x0 = 120 + i * 80
        cv2.rectangle(comb, (x0, 800), (x0 + 30, 1800), (0, 0, 0, 255), -1)
    ents, info = imgtrace.image_to_entities(png(comb), height_mm=20)
    audit(ents, f"comb @20mm {info}")
    ents, info = imgtrace.image_to_entities(png(comb), height_mm=200)
    audit(ents, f"comb @200mm {info}")

    # d) a star with a long thin spike: DP at eps=3px
    star = np.zeros((800, 800, 4), np.uint8)
    sp = []
    for i in range(10):
        r = 350 if i % 2 == 0 else 60
        a = i * np.pi / 5
        sp.append([400 + r * np.cos(a), 400 + r * np.sin(a)])
    cv2.fillPoly(star, [np.array(sp, np.int32)], (0, 0, 0, 255))
    ents, info = imgtrace.image_to_entities(png(star), height_mm=8)
    audit(ents, f"star @8mm {info}")


def part3_nesting():
    print("=== 3. nested contours (holes in holes) ===")
    n = np.zeros((900, 900, 4), np.uint8)
    cv2.circle(n, (450, 450), 400, (0, 0, 0, 255), -1)      # outer  add
    cv2.circle(n, (450, 450), 300, (0, 0, 0, 0), -1)        # hole   subtract
    cv2.circle(n, (450, 450), 200, (0, 0, 0, 255), -1)      # island add
    cv2.circle(n, (450, 450), 100, (0, 0, 0, 0), -1)        # hole   subtract
    ents, info = imgtrace.image_to_entities(png(n), height_mm=60)
    print("  modes in order:", [e["mode"] for e in ents], info)
    import sketch as sk
    face = sk.make_sketch("XY", 0, ents)
    want = np.pi * (30 ** 2 - 22.5 ** 2 + 15 ** 2 - 7.5 ** 2)
    print(f"  built area {face.area:.1f} mm2, want ~{want:.1f} "
          f"({100 * face.area / want:.1f}%)")


def part4_orientation():
    print("=== 4. orientation / mirror ===")
    # an F: chiral. In IMAGE space the long stem is on the LEFT and the
    # arms point RIGHT; the top arm is longer than the middle one.
    f = np.zeros((400, 300, 4), np.uint8)
    cv2.rectangle(f, (60, 40), (110, 360), (0, 0, 0, 255), -1)   # stem
    cv2.rectangle(f, (60, 40), (250, 90), (0, 0, 0, 255), -1)    # top arm
    cv2.rectangle(f, (60, 170), (200, 220), (0, 0, 0, 255), -1)  # mid arm
    ents, info = imgtrace.image_to_entities(png(f), height_mm=40)
    p = ents[0]["points"]
    xs = [q[0] for q in p]
    ys = [q[1] for q in p]
    # top arm = the biggest y band; how far right does it reach there?
    top = max(q[0] for q in p if q[1] > max(ys) - 6)
    bot = max(q[0] for q in p if q[1] < min(ys) + 6)
    print(f"  traced F: x {min(xs):.1f}..{max(xs):.1f}, y {min(ys):.1f}..{max(ys):.1f}")
    print(f"  reach right at TOP {top:.1f} vs at BOTTOM {bot:.1f} "
          f"(top must be the longer arm -> {'UPRIGHT' if top > bot else 'FLIPPED'})")
    print(f"  stem at x={min(xs):.1f} (left) -> "
          f"{'NOT mirrored' if abs(min(xs)) > abs(max(xs)) else 'MIRRORED?'}")

    # the face frame for an UP-facing and a DOWN-facing face
    import build123d as b3d
    import sketch as sk
    box = b3d.Box(40, 20, 10)
    for nz in (1, -1):
        fc = sk.pick_face(box, [0, 0, 5 * nz], [0, 0, nz])
        pl = sk.face_sketch_plane(fc)
        print(f"  face normal z={nz:+d} -> sketch frame "
              f"x={tuple(round(v, 3) for v in pl.x_dir)} "
              f"z={tuple(round(v, 3) for v in pl.z_dir)} "
              f"origin={tuple(round(v, 3) for v in pl.origin)}")


def part5_polarity_and_size():
    print("=== 5. polarity and size ===")
    # artwork that covers MORE than half the canvas: the polarity rule
    # ("the art is the minority") inverts it and traces the BACKGROUND
    for frac, label in ((0.30, "art 30% of canvas"), (0.60, "art 60%"),
                        (0.80, "art 80%")):
        s = 400
        side = int(round(s * frac ** 0.5))
        img = np.full((s, s, 3), 255, np.uint8)
        off = (s - side) // 2
        cv2.rectangle(img, (off, off), (off + side, off + side), (0, 0, 0), -1)
        cv2.circle(img, (s // 2, s // 2), side // 6, (255, 255, 255), -1)
        try:
            ents, info = imgtrace.image_to_entities(png(img), height_mm=40)
            print(f"  {label}: {info}  first mode {ents[0]['mode']}")
        except Exception as e:                    # noqa: BLE001
            print(f"  {label}: {type(e).__name__}: {e}")

    # the decisive one: a tightly CROPPED logo (the user's own generator
    # scripts crop to the ink bbox) - ink is then the MAJORITY
    import sketch as sk
    for r, lab in ((120, "disc, loose crop (28% ink)"),
                   (199, "disc, tight crop (78% ink)")):
        s = 400
        img = np.full((s, s, 3), 255, np.uint8)
        cv2.circle(img, (s // 2, s // 2), r, (0, 0, 0), -1)
        ink = float((img[:, :, 0] < 128).mean())
        ents, info = imgtrace.image_to_entities(png(img), height_mm=40)
        face = sk.make_sketch("XY", 0, ents)
        print(f"  {lab}: ink={ink:.0%}  traced area {face.area:.1f} mm2 "
              f"(a 40mm disc is {np.pi * 400:.1f}, its negative "
              f"{40 * 40 - np.pi * 400:.1f})  {info}")

    import time
    for n in (2000, 4000):
        img = np.zeros((n, n, 4), np.uint8)
        cv2.circle(img, (n // 2, n // 2), n // 3, (0, 0, 0, 255), -1)
        for k in range(40):
            cv2.circle(img, (n // 2 + int(n / 3.5 * np.cos(k)),
                             n // 2 + int(n / 3.5 * np.sin(k))),
                       n // 40, (0, 0, 0, 0), -1)
        data = png(img)
        t = time.time()
        _, info = imgtrace.image_to_entities(data, height_mm=60)
        print(f"  {n}x{n} image: {time.time() - t:.2f}s  {info}")


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    if part in ("all", "5"):
        part5_polarity_and_size()
    if part in ("all", "1"):
        part1_limits()
    if part in ("all", "2"):
        part2_entities()
    if part in ("all", "3"):
        part3_nesting()
    if part in ("all", "4"):
        part4_orientation()
