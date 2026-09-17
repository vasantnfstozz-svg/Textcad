"""REVIEW-QUEUE section 9 ROUND FOUR — the closing fuzz, and the one the
earlier rounds did NOT run.

Round two's 426-trace sweep and round three's 450-trace fuzz both feed the
tracer PNGs with an ALPHA channel, and `_mask_from_image` short-circuits on
alpha: `if img.shape[2] == 4 and alpha.min() < 250: return alpha > 128`. So
900 fuzz traces never once exercised the polarity rule the three rounds spent
all their argument on. This fuzz draws OPAQUE pictures, remembers which side
it drew the art on, and reports polarity accuracy per picture CLASS as well
as the usual health numbers.

Per trace it measures:
  * whether the module picked the side the picture was drawn with;
  * self-crossing edges in the entities handed to sketch.py;
  * solid health of the 2 mm extrusion;
  * traced area against the TRUE ink (not against the module's own mask, so
    a polarity miss shows up as a number, not only as a flag);
  * add entities against the true piece count;
  * refusals (a sentence is a pass, a traceback is not).

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_fuzz.py [n_pictures]
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402
from imgtrace_r3_fuzz import crossings                      # noqa: E402

CLASSES = ["roomy", "tight_crop", "dark_band", "light_pad", "hairline",
           "band_and_pad", "speckled_edge"]


def _shapes(art, rng, h, w, fill="roomy"):
    """draw 1-5 pieces into `art` (1 = artwork).

    `fill` is the dimension a fair test of these rules needs: "roomy" art is
    the MINORITY of the picture, which the pre-4c9ea32 rule is right about by
    construction, and "full" art is the majority, which is the case that rule
    was replaced for. Half the corpus is each."""
    n = int(rng.integers(1, 6))
    m0, m1 = int(0.12 * h), int(0.12 * w)
    for _ in range(n):
        kind = int(rng.integers(0, 4))
        cy = int(rng.integers(m0, h - m0))
        cx = int(rng.integers(m1, w - m1))
        if fill == "full":
            r = int(rng.integers(min(h, w) // 4, min(h, w) // 2))
        else:
            r = int(rng.integers(min(h, w) // 14, min(h, w) // 4))
        if kind == 0:
            cv2.circle(art, (cx, cy), r, 1, -1)
        elif kind == 1:
            cv2.rectangle(art, (cx - r, cy - r // 2), (cx + r, cy + r // 2),
                          1, -1)
        elif kind == 2:                                     # a ring
            cv2.circle(art, (cx, cy), r, 1, -1)
            cv2.circle(art, (cx, cy), max(2, r // 2), 0, -1)
        else:                                               # a rough polygon
            k = int(rng.integers(3, 8))
            a0 = rng.random() * 6.283
            pts = np.array([[cx + r * np.cos(a0 + 6.283 * i / k),
                             cy + r * np.sin(a0 + 6.283 * i / k)]
                            for i in range(k)], np.int32)
            cv2.fillPoly(art, [pts], 1)
    return art


def corpus(n):
    """(name, picture, true-art-mask, class) — a DIFFERENT seed, different
    generators and OPAQUE pictures, so the polarity rule actually runs"""
    rng = np.random.default_rng(4_2026_0917)
    for k in range(n):
        h = int(rng.integers(300, 700))
        w = int(rng.integers(300, 700))
        fill = "full" if (k // 2) % 2 else "roomy"
        art = _shapes(np.zeros((h, w), np.uint8), rng, h, w, fill)
        if int(art.sum()) < 900:
            continue
        cls = CLASSES[k % len(CLASSES)]
        light_art = bool(k % 2)                       # inverse video every 2nd
        if cls == "tight_crop":
            ys, xs = np.where(art)
            art = art[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            h, w = art.shape
        ground = np.zeros_like(art)                   # 1 where the GROUND is
        ground[art == 0] = 1
        t = int(rng.integers(2, 15))
        if cls == "dark_band":
            band = np.zeros_like(art)
            band[:t] = band[-t:] = 1
            band[:, :t] = band[:, -t:] = 1
            art = art.copy()
            if light_art:                             # a DARK band on a dark
                art[band == 1] = 0                    # ground: part of it
            else:
                art[band == 1] = 1                    # a dark band IS ink
        elif cls == "light_pad":
            pad = np.zeros_like(art)
            pad[:t] = pad[-t:] = 1
            pad[:, :t] = pad[:, -t:] = 1
            art = art.copy()
            art[pad == 1] = 1 if light_art else 0
        elif cls == "hairline":
            art = art.copy()
            art[0] = art[-1] = art[:, 0] = art[:, -1] = 0 if light_art else 1
        elif cls == "band_and_pad":
            art = art.copy()
            art[:t + 6] = art[-t - 6:] = 0 if light_art else 1
            art[:, :t + 6] = art[:, -t - 6:] = 0 if light_art else 1
            art[:6] = art[-6:] = art[:, :6] = art[:, -6:] = (
                1 if light_art else 0)
        elif cls == "speckled_edge":
            art = art.copy()
            ys = rng.integers(0, h, 60)
            xs = rng.integers(0, w, 60)
            for yy, xx in zip(ys, xs):
                if min(int(yy), int(xx), h - int(yy), w - int(xx)) < 12:
                    art[int(yy):int(yy) + 3, int(xx):int(xx) + 3] = (
                        0 if light_art else 1)
        if int(art.sum()) < 900 or int((art == 0).sum()) < 900:
            continue
        img = np.full((h, w, 3), 255 if not light_art else 0, np.uint8)
        img[art == 1] = 0 if not light_art else 255
        yield (f"p{k}", img, art.astype(np.uint8), cls,
               ("light" if light_art else "dark") + "/" + fill)


def main():
    n_pics = int(sys.argv[1]) if len(sys.argv) > 1 else 160
    tot = refused = raised = cross_tot = bad = flipped = extra = 0
    by_cls = defaultdict(lambda: [0, 0])
    worst_short = worst_excess = (0.0, "")
    for name, img, art, cls, drew in corpus(n_pics):
        ok, buf = cv2.imencode(".png", img)
        assert ok
        data = buf.tobytes()
        for h_mm in (15.0, 45.0):
            try:
                ents, _info = imgtrace.image_to_entities(data, height_mm=h_mm)
            except ValueError:
                refused += 1
                continue
            except Exception as exc:                        # noqa: BLE001
                raised += 1
                print(f"  TRACEBACK    {name} {cls}/{drew} at {h_mm:g}: "
                      f"{type(exc).__name__}: {str(exc)[:70]}")
                continue
            tot += 1
            got = imgtrace._mask_from_image(
                cv2.imdecode(np.frombuffer(data, np.uint8),
                             cv2.IMREAD_UNCHANGED))
            same = int((got == art).sum()) / art.size
            by_cls[(cls, drew)][1] += 1
            if same > 0.98:
                by_cls[(cls, drew)][0] += 1
            else:
                flipped += 1
            cross_tot += sum(crossings(e["points"]) for e in ents)
            try:
                s = sk.make_sketch("XY", 0, ents)
                area = s.area
                if inspector.health(sk.extrude_sketch(s, 2.0)):
                    bad += 1
                    print(f"  UNHEALTHY    {name} {cls}/{drew} at {h_mm:g}")
            except Exception as exc:                        # noqa: BLE001
                bad += 1
                print(f"  SKETCH FAIL  {name} {cls}/{drew} at {h_mm:g}: "
                      f"{type(exc).__name__}: {str(exc)[:60]}")
                continue
            if same <= 0.98:
                continue                     # area is meaningless if flipped
            # the ink is measured on the mask the module ITSELF traces, at
            # the scale it itself uses: a speckle it drops shrinks its own
            # artwork bbox, so the true-art bbox would put the two numbers
            # on different scales and read 300% "excess" where nothing was
            # invented (measured 2026-09-17, round four's first pass)
            solid, _ma = imgtrace._traceable(got, h_mm)
            ys, _xs = np.where(solid)
            mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
            ink = float(solid.sum()) * mm_px * mm_px
            n_true = cv2.connectedComponents(solid, 8)[0] - 1
            n_add = sum(1 for e in ents if e["mode"] == "add")
            if n_add > n_true:
                extra += 1
            short, excess = (ink - area) / ink, (area - ink) / ink
            if short > worst_short[0]:
                worst_short = (short, f"{name} {cls}/{drew} at {h_mm:g}")
            if excess > worst_excess[0]:
                worst_excess = (excess, f"{name} {cls}/{drew} at {h_mm:g}")
    print(f"\n{tot} traces  ({refused} refused with a sentence, "
          f"{raised} raised something else)")
    print(f"  self-crossing edges handed to sketch.py: {cross_tot}")
    print(f"  invalid / unhealthy solids:              {bad}")
    print(f"  traces whose POLARITY was flipped:       {flipped}")
    print(f"  traces with MORE add pieces than drawn:  {extra}")
    print(f"  worst shortfall vs the true ink: {100 * worst_short[0]:.2f}% "
          f"({worst_short[1]})")
    print(f"  worst EXCESS over the true ink:  {100 * worst_excess[0]:.2f}% "
          f"({worst_excess[1]})")
    print("\n  polarity by picture class (right / traces):")
    for key in sorted(by_cls):
        good, n = by_cls[key]
        print(f"    {key[0]:14s} art drawn {key[1]:6s}: {good:3d} / {n:3d}"
              + ("   <-- MISSES" if good < n else ""))


if __name__ == "__main__":
    main()
