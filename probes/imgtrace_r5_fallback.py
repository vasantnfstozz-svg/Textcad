"""REVIEW-QUEUE section 9 ROUND FIVE — the fit-height fallback's own choice.

When no tried height fits the box, `studio._trace_fit_height` picks the
height that needs the LEAST shrinking: it maximises `s = min(m_w/w, m_h/h)`.
The art the user ends up with is `w*s x h*s`, whose AREA is `w*h*s^2` — and
the biggest `s` is not the biggest area. This probe asks whether the rule
ever leaves a materially bigger piece of art on the table among the heights
it already measured.

It also re-counts round four's own "222 boxes come out smaller in area than
the one-shot rule" — and says, for each, WHY.

Run:  C:/Python314/python.exe probes/imgtrace_r5_fallback.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import studio                                               # noqa: E402
from imgtrace_fit_height_attack import ladder, old_rule     # noqa: E402

_CACHE: dict = {}
_REAL = imgtrace.artwork_aspect


def cached(data, height_mm=50.0):
    key = round(float(height_mm), 6)
    if key not in _CACHE:
        _CACHE[key] = _REAL(data, key)
    return _CACHE[key]


def tried_of(data, m_w, m_h):
    seen = []

    def spy(d, height_mm=50.0):
        a = cached(d, height_mm)
        seen.append((round(float(height_mm), 6), a))
        return a

    studio.imgtrace.artwork_aspect = spy
    try:
        h, rot = studio._trace_fit_height(data, m_w, m_h)
    finally:
        studio.imgtrace.artwork_aspect = _REAL
    return h, rot, seen


def final(h, aspect, rot, m_w, m_h):
    w, hh = (h, h * aspect) if rot else (h * aspect, h)
    s = min(1.0, m_w / w, m_h / hh)
    return w * s, hh * s


def main():
    data = ladder(radii=(30, 24, 20, 17, 14, 12, 10, 8, 7, 6), gap=130)
    n = fb = worse_than_old = 0
    worst = (1.0, None)
    wrong_reason: list = []
    for fw10 in range(120, 600, 4):
        for fh10 in range(100, 600, 4):
            fw, fh = fw10 / 10.0, fh10 / 10.0
            m_w, m_h = 0.9 * fw, 0.9 * fh
            n += 1
            h, rot, seen = tried_of(data, m_w, m_h)
            tol = 1.0 + 1e-9
            if any((x <= m_h * tol and x * a <= m_w * tol)
                   or (x <= m_w * tol and x * a <= m_h * tol)
                   for x, a in seen):
                continue                       # something fitted; not the
            fb += 1                            # fallback's decision
            gw, gh = final(h, cached(data, h), rot, m_w, m_h)
            got = gw * gh
            best, bpick = got, (h, rot)
            for x, a in seen:
                for r in (False, True):
                    aw, ah = final(x, a, r, m_w, m_h)
                    if aw * ah > best * (1 + 1e-9):
                        best, bpick = aw * ah, (x, r)
            if got < best * (1 - 1e-9):
                ratio = got / best
                if ratio < worst[0]:
                    worst = (ratio, (fw, fh, (h, rot), gw, gh, bpick, best))
            oh, orot = old_rule(data, m_w, m_h)
            ow, ohh = final(oh, cached(data, oh), orot, m_w, m_h)
            if got < ow * ohh * 0.999:
                worse_than_old += 1
                # the reason the rule gives for being smaller: it traced
                # CLOSER to the size the art ends up at
                a_new, a_old = cached(data, h), cached(data, oh)
                w_n, h_n = final(h, a_new, rot, 1e9, 1e9)
                s_new = min(m_w / w_n, m_h / h_n)
                w_o, h_o = final(oh, a_old, orot, 1e9, 1e9)
                s_old = min(m_w / w_o, m_h / h_o)
                if s_new < s_old * (1 - 1e-9):
                    wrong_reason.append((fw, fh, s_new, s_old))
    print(f"{n} boxes, {fb} fell back")
    print(f"  smaller in area than the one-shot rule: {worse_than_old}")
    print(f"  ...of those, ones that ALSO needed more shrinking than the "
          f"one-shot rule (i.e. smaller for no reason): {len(wrong_reason)}")
    for row in wrong_reason[:6]:
        print(f"      box {row[0]} x {row[1]}: shrink {row[2]:.4f} "
              f"vs one-shot {row[3]:.4f}")
    if worst[1]:
        fw, fh, pick, gw, gh, bpick, best = worst[1]
        print(f"  worst 'a tried height would have been bigger': "
              f"{100 * worst[0]:.1f}% of the best tried option")
        print(f"    box {fw} x {fh}: picked h={pick[0]:.3f} rot={pick[1]} "
              f"-> {gw:.2f} x {gh:.2f} = {gw * gh:.1f} mm2; "
              f"h={bpick[0]:.3f} rot={bpick[1]} would give {best:.1f} mm2")
    else:
        print("  the fallback's pick is the biggest-area tried option "
              "in every fallback box")


if __name__ == "__main__":
    main()
