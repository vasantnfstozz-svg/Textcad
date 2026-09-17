"""REVIEW-QUEUE section 9, ROUND THREE — a THIRD independent corpus for the
foreground/background rule, plus a scorer that runs ALL THREE corpora.

Round one scored its own new rule on its own corpus (9/10 against 7). Round
two built a second corpus and found round one was a NET REGRESSION and had
re-opened the P0 it closed. A reviewer grading its own corpus is how this
went wrong twice, so this round builds a THIRD corpus — cases neither earlier
round used, clustered around round two's own 5%-of-the-picture threshold,
which is where its rule turns — and scores every rule on every corpus:

    old  = pre-4c9ea32  ("the artwork is the MINORITY of pixels")
    r1   = 4c9ea32      ("the ground is whichever side fills the 1 px border")
    r2   = 4b3af6a      ("... read past a THIN border shell")
    cand = the round-three candidate (see `cand_mask`)

Ground truth per picture is which SIDE of the Otsu split is the artwork.
Frames are drawn as EXACT bands (cv2.rectangle centres its stroke on the
line, so `thickness=12` is a six-pixel band inside a picture).

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_corpus.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                               # noqa: E402  the r2 rule
import _imgtrace_old as OLD                   # noqa: E402  verified == git
import _imgtrace_r1 as R1                     # noqa: E402  verified == git


def _otsu(img):
    gray = (cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
            if img.ndim == 3 else img)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return m


def side_of(img, mask):
    """'bright' if the rule kept the Otsu-bright pixels, else 'dark'"""
    m = _otsu(img)
    return "bright" if int((mask == m).sum()) == m.size else "dark"


# --------------------------------------------------------------------------
# the round-three candidate: the r2 rule with its two measured defects closed
#   1. only a DARK shell is read past.  A thin LIGHT shell is an ordinary
#      export margin, not an artefact, and stripping it turns art with any
#      enclosed light region (a ring, a plate with holes, the counter of an
#      O) into its own negative.
#   2. the "is there anything inside to read" floor is the module's own 64 px,
#      not 1% of the picture: a small logo inside a scan's platen edge is
#      under 1% and fell back on the contaminated ring.
# --------------------------------------------------------------------------
def cand_border_bright(m) -> float:
    valid = np.ones(m.shape, np.uint8)
    ring = imgtrace._ring_mean(m, valid)
    if ring > 0.4:                             # a light border is normal
        return ring
    shell = imgtrace._edge_shell(m, 0, valid)
    if shell is None:
        return ring
    if float(cv2.distanceTransform(shell, cv2.DIST_L2, 3).max()) > \
            0.05 * min(m.shape):
        return ring
    rest = (1 - shell).astype(np.uint8)
    inside = m[rest.astype(bool)]
    lit = int(inside.sum())
    if min(lit, int(inside.size) - lit) < 64:
        return ring
    return imgtrace._ring_mean(m, rest)


def cand_mask(img) -> np.ndarray:
    if img is None:
        raise ValueError("could not decode the image — is it a PNG/JPG?")
    if img.ndim == 3 and img.shape[2] == 4 and int(img[:, :, 3].min()) < 250:
        return (img[:, :, 3] > 128).astype(np.uint8)
    m = _otsu(img)
    bright_edge = cand_border_bright(m)
    if bright_edge > 0.6:
        m = 1 - m
    elif bright_edge >= 0.4:
        if int(m.sum()) > m.size // 2:
            m = 1 - m
    return m.astype(np.uint8)


RULES = [("old", OLD._mask_from_image),
         ("r1", R1._mask_from_image),
         ("r2", imgtrace._mask_from_image),
         ("cand", cand_mask)]


# --------------------------------------------------------------------------
# helpers - EXACT bands, so "12 px frame" means twelve rows
# --------------------------------------------------------------------------
W = 400


def _white(h=W, w=W):
    return np.full((h, w, 3), 255, np.uint8)


def _black(h=W, w=W):
    return np.zeros((h, w, 3), np.uint8)


def _band(im, t, colour=(0, 0, 0)):
    """paint an EXACT t-pixel band round the picture"""
    im[:t] = colour
    im[-t:] = colour
    im[:, :t] = colour
    im[:, -t:] = colour
    return im


def _letters(im, n=5, colour=(0, 0, 0), x0=60, step=60, w=35,
             y0=160, y1=240):
    for i in range(n):
        cv2.rectangle(im, (x0 + i * step, y0), (x0 + i * step + w, y1),
                      colour, -1)
    return im


# --------------------------------------------------------------------------
# the corpus - cases neither round one nor round two used
# --------------------------------------------------------------------------
def c_ring_thin_margin():
    """A rectangular RING (a washer, a gasket, the letter O) exported with an
    8 px pad.  The light margin is thin AND the ring has a light middle, so
    "a thin light margin has nothing to read inside" is false here."""
    im = _white()
    cv2.rectangle(im, (8, 8), (391, 391), (0, 0, 0), -1)
    cv2.rectangle(im, (120, 120), (279, 279), (255, 255, 255), -1)
    return im, "dark", "a rectangular ring with an 8 px light pad"


def c_plate_with_holes_thin_pad():
    """A traced part silhouette with bolt holes, trimmed to a 5 px pad —
    what designs/*.py do with img.crop(getbbox()) plus any padding."""
    im = _white()
    cv2.rectangle(im, (5, 5), (394, 394), (0, 0, 0), -1)
    for cx, cy in ((90, 90), (310, 90), (90, 310), (310, 310), (200, 200)):
        cv2.circle(im, (cx, cy), 40, (255, 255, 255), -1)
    return im, "dark", "a dark plate with light holes, 5 px light pad"


def c_scan_edge_small_logo():
    """A scan with the platen's 6 px dark edge and a SMALL logo on the
    paper — under 1% of the sheet."""
    im = _white()
    cv2.circle(im, (200, 200), 20, (0, 0, 0), -1)
    return _band(im, 6), "dark", "6 px scan edge, art under 1% of the sheet"


def c_scan_edge_13px():
    """the scan edge just UNDER round two's 5% threshold (14.1 px)"""
    return _band(_letters(_white()), 13), "dark", "13 px scan edge + letters"


def c_scan_edge_16px():
    """the same scan edge just OVER round two's threshold"""
    return _band(_letters(_white()), 16), "dark", "16 px scan edge + letters"


def c_dark_mount_board():
    """dark art photographed in a dark mount board"""
    return _band(_letters(_white()), 30), "dark", "30 px dark mount board"


def c_photo_frame_fat():
    """a print photographed in a fat black picture frame"""
    im = _white()
    cv2.circle(im, (200, 200), 90, (0, 0, 0), -1)
    return _band(im, 60), "dark", "60 px black picture frame"


def c_passepartout():
    """black frame, white mount, dark art: two shells"""
    im = _white()
    cv2.circle(im, (200, 200), 60, (0, 0, 0), -1)
    return _band(im, 10), "dark", "10 px black frame, white mount, dark art"


def c_inverse_video_white_edge():
    """inverse video with the 1 px bright border an exporter leaves"""
    im = _black()
    cv2.circle(im, (200, 200), 120, (255, 255, 255), -1)
    return _band(im, 1, (255, 255, 255)), "bright", \
        "white art on black, 1 px white export edge"


def c_inverse_video_dark_scan_edge():
    """inverse video art whose picture also has a 6 px darker edge"""
    im = _black()
    cv2.circle(im, (200, 200), 120, (255, 255, 255), -1)
    return _band(im, 6), "bright", "white art on black, 6 px darker edge"


def c_logo_on_dark_card():
    """white lettering on a dark card that fills the picture"""
    return _letters(_black(), colour=(255, 255, 255)), "bright", \
        "white lettering on a dark card, no margin"


def c_art_touches_three_edges():
    """a U-shape running off left, right and bottom"""
    im = _white()
    cv2.rectangle(im, (0, 100), (70, 399), (0, 0, 0), -1)
    cv2.rectangle(im, (329, 100), (399, 399), (0, 0, 0), -1)
    cv2.rectangle(im, (0, 330), (399, 399), (0, 0, 0), -1)
    return im, "dark", "a U touching left, right and bottom"


def c_black_background_render():
    """a render on a black ground with a soft falloff"""
    im = _black()
    cv2.circle(im, (200, 190), 130, (210, 210, 210), -1)
    cv2.circle(im, (170, 160), 60, (255, 255, 255), -1)
    return im, "bright", "a bright render on a black ground"


def c_noisy_paper_edge():
    """dark art on paper whose border carries scanner speckle"""
    rng = np.random.default_rng(7)
    im = _letters(_white())
    for y, x in rng.integers(0, W, size=(600, 2)):
        if y < 6 or y > W - 7 or x < 6 or x > W - 7:
            im[y, x] = 0
    return im, "dark", "dark art on paper, speckled picture edge"


def c_banner_wide():
    """a wide banner: min(shape) is the SHORT side, so 5% is 10 px"""
    im = np.full((200, 1200, 3), 255, np.uint8)
    for i in range(6):
        cv2.rectangle(im, (100 + i * 180, 60), (180 + i * 180, 140),
                      (0, 0, 0), -1)
    return _band(im, 6), "dark", "wide banner, 6 px dark edge (5% = 10 px)"


def c_tall_thin():
    """a tall narrow strip of art with a 4 px dark edge"""
    im = np.full((1200, 200, 3), 255, np.uint8)
    for i in range(6):
        cv2.rectangle(im, (60, 100 + i * 180), (140, 180 + i * 180),
                      (0, 0, 0), -1)
    return _band(im, 4), "dark", "tall strip, 4 px dark edge"


def c_grey_ground():
    """dark art on a MID-GREY card with a white margin round the card"""
    im = _white()
    cv2.rectangle(im, (40, 40), (359, 359), (150, 150, 150), -1)
    cv2.circle(im, (200, 200), 90, (0, 0, 0), -1)
    return im, "dark", "dark art on a grey card on white"


def c_hairline_frame_1px():
    """the one-pixel frame an exporter leaves round ordinary art"""
    im = _white()
    cv2.circle(im, (200, 200), 110, (0, 0, 0), -1)
    return _band(im, 1), "dark", "ordinary art, 1 px dark export frame"


def c_plain_art_margin():
    """the baseline every rule must keep: art with a generous margin"""
    im = _white()
    cv2.circle(im, (200, 200), 110, (0, 0, 0), -1)
    cv2.rectangle(im, (60, 60), (140, 140), (0, 0, 0), -1)
    return im, "dark", "ordinary dark art, generous margin"


def c_solid_disc_thin_margin():
    """a filled square with a thin pad: the shell is thin but the art really
    is solid, so "nothing to read inside" does apply here"""
    im = _white()
    cv2.rectangle(im, (6, 6), (393, 393), (0, 0, 0), -1)
    return im, "dark", "a filled square with a 6 px light pad"


def c_letter_o_thin_pad():
    """the single most ordinary padded-art case: one letter with a counter"""
    im = _white()
    cv2.circle(im, (200, 200), 192, (0, 0, 0), -1)
    cv2.circle(im, (200, 200), 120, (255, 255, 255), -1)
    return im, "dark", "an O with an 8 px pad and a light counter"


CASES = [c_ring_thin_margin, c_plate_with_holes_thin_pad,
         c_scan_edge_small_logo, c_scan_edge_13px, c_scan_edge_16px,
         c_dark_mount_board, c_photo_frame_fat, c_passepartout,
         c_inverse_video_white_edge, c_inverse_video_dark_scan_edge,
         c_logo_on_dark_card, c_art_touches_three_edges,
         c_black_background_render, c_noisy_paper_edge, c_banner_wide,
         c_tall_thin, c_grey_ground, c_hairline_frame_1px,
         c_plain_art_margin, c_solid_disc_thin_margin, c_letter_o_thin_pad]


def score(cases, title):
    """cases: iterable of (name, image, truth-side, description)"""
    got_all = {n: 0 for n, _ in RULES}
    judged = 0
    print(f"\n=== {title} ===")
    print(f"{'case':30s} {'truth':7s} "
          + " ".join(f"{n:7s}" for n, _ in RULES) + "  note")
    print("-" * 104)
    for name, im, truth, desc in cases:
        if truth is None:
            continue
        got = []
        for _n, rule in RULES:
            try:
                got.append(side_of(im, rule(im)))
            except Exception as exc:                        # noqa: BLE001
                got.append(f"ERR:{type(exc).__name__}"[:7])
        judged += 1
        for (n, _), g in zip(RULES, got):
            got_all[n] += g == truth
        flags = []
        if got[0] == truth and got[2] != truth:
            flags.append("r2<old")
        if got[1] == truth and got[2] != truth:
            flags.append("r2<r1")
        if got[3] != truth:
            flags.append("CAND WRONG")
        print(f"{name:30s} {truth:7s} "
              + " ".join(f"{g:7s}" for g in got)
              + f"  {';'.join(flags):16s} {desc}")
    print("-" * 104)
    print(f"judged {judged}:  "
          + ",  ".join(f"{n} {got_all[n]}" for n, _ in RULES))
    return judged, got_all


def r3_cases():
    for fn in CASES:
        im, truth, desc = fn()
        yield fn.__name__[2:], im, truth, desc


def r2_cases():
    import imgtrace_r2_polarity as P
    for fn in P.CASES:
        im, truth, desc = fn()
        yield fn.__name__[2:], im, truth, desc


def r1_cases():
    import imgtrace_polarity_probe as P
    for name, img, art_is in P.corpus():
        yield name, img, ("bright" if art_is == "light" else "dark"), ""


def main():
    total = {n: 0 for n, _ in RULES}
    grand = 0
    for cases, title in ((r1_cases(), "round ONE's own corpus"),
                         (r2_cases(), "round TWO's corpus"),
                         (r3_cases(), "round THREE's corpus (this one)")):
        j, s = score(cases, title)
        grand += j
        for n in total:
            total[n] += s[n]
    print("\n" + "=" * 104)
    print(f"ALL THREE CORPORA, {grand} judged pictures:  "
          + ",  ".join(f"{n} {total[n]}" for n, _ in RULES))


if __name__ == "__main__":
    main()
