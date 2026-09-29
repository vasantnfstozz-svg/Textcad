"""Probe: OpenJev + Laya / Verdict (CPU) as TextCAD's judge — 2026-09-29.

Run with the OpenJev server up (see judge.py). Measures, through the REAL
client in judge.py: the wire format, latency for a checklist-sized call,
and whether the yes/no probabilities separate present from absent
elements in a tree summary of the exact shape author._tree_words writes.

    C:/Python314/python.exe probes/openjev_laya.py

RESULT (ThinkPad, Intel Iris Xe, no NVIDIA, 15.7 GB RAM; both backends on
the CPU) — NEITHER FREE MODEL PASSES on a realistic tree:

  Laya-1.0 (421M), 11-feature phone case, 8 yes/no questions, three
  phrasings ("contain", "built by a feature", true/false criteria):
    present min 0.27 / absent max 0.31  (gap -0.05), 22.5 s
    present min 0.16 / absent max 0.17  (gap -0.01), 39.2 s
    present min 0.46 / absent max 0.52  (gap -0.06), 28.0 s
  Laya, one pick-one question PER FEATURE (11 calls, 18.7 s): absent
    elements stay <= 0.10 but "camera opening" reads 0.17 and
    "charging-port opening" 0.09 — present ones score like absent ones.
  Laya, the 2-feature washer: present 0.53-0.63 / absent 0.15-0.18 — it
    separates only a tree this small (2.4 s for 4 questions).
  Verdict-1.4 (151M): everything 0.65-0.74 whichever tree or element
    (gap +0.02), 8.7 s for the case, 1.4 s for the washer. ~1 GB RAM.

  A wired-in Laya would refuse "done" for elements that ARE there (all
  eight read "missing" at 0.5), so neither local model is the default.

  The hosted Jev through OpenRouter (TEXTCAD_JUDGE_URL=https://openrouter.ai/api,
  the OPENROUTER_API_KEY TextCAD already holds), same file, same questions:
    case: present 0.94-0.99 / absent 0.03-0.20 (gap +0.74), 8 of 8 right,
          p50 291 ms, max 416 ms for 8 questions
    washer without bore: body 0.94, bore 0.15; with bore: 0.97 / 0.98
  That is the judge judge.py picks when the key exists (see WHICH JUDGE).
"""
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import judge  # noqa: E402

print("alive:", judge.alive(), "url:", judge.URL)

CASE = """REQUEST: design a OnePlus 7 Pro phone case with a very unique design
DESIGN, in build order:
- base_sketch: sketch — on XY — 1 rectangle
- back_shell: extrude — amount 10 — of base_sketch
- hollow: shell — thickness 1.2 — open_face top — of back_shell
- camera_sketch: sketch_on_face — on back — 1 rectangle — of hollow
- camera_cut: extrude — amount 3 — through True — of camera_sketch
- usb_sketch: sketch_on_face — on bottom — 1 rectangle — of camera_cut
- usb_cut: extrude — amount 3 — through True — of usb_sketch
- dimple_sketch: sketch_on_face — on back — 1 circle — of usb_cut
- dimple: extrude — amount 0.6 — of dimple_sketch
- dimples: rect_pattern — count_x 8 — count_y 14 — of dimple
- corner_round: fillet — radius 4 — of dimples"""

QS = {
    "shell": "Does the design contain this element: back shell?",
    "walls": "Does the design contain this element: thin side walls (hollowed)?",
    "camera": "Does the design contain this element: camera opening on the back?",
    "usb": "Does the design contain this element: charging-port opening?",
    "buttons": "Does the design contain this element: volume and power button openings?",
    "speaker": "Does the design contain this element: speaker slots?",
    "lip": "Does the design contain this element: a lip holding the phone?",
    "dimples": "Does the design contain this element: a grid of dimples on the back?",
}
EXPECT = {"shell": 1, "walls": 1, "camera": 1, "usb": 1, "buttons": 0,
          "speaker": 0, "lip": 0, "dimples": 1}

times = []
got = None
for _ in range(5):
    t0 = time.perf_counter()
    got = judge.yes_no(CASE, QS)
    times.append(time.perf_counter() - t0)
print(f"state {len(CASE)} chars, {len(QS)} questions: "
      f"p50 {statistics.median(times)*1000:.0f} ms, max {max(times)*1000:.0f} ms")
assert got, "no answer from the judge"
wrong = 0
for k, q in QS.items():
    p = got[k]
    verdict = "present" if p >= 0.5 else "MISSING"
    ok = (p >= 0.5) == bool(EXPECT[k])
    wrong += not ok
    print(f"  {k:8s} P(yes)={p:.3f}  -> {verdict:8s} {'ok' if ok else 'WRONG'}")
print(f"{wrong} of {len(QS)} judged against expectation")

# a small washer, exactly what the unit tests script
WASHER = ("REQUEST: a washer\nDESIGN, in build order:\n"
          "- body: disc — radius 20 — thickness 4")
w = judge.yes_no(WASHER, {"p0": "Does the design contain this element: a round body?",
                          "p1": "Does the design contain this element: a centre bore?"})
print("washer without bore:", {k: round(v, 3) for k, v in w.items()})
WASHER2 = WASHER + "\n- bore: with_center_hole — radius 10 — of body"
w2 = judge.yes_no(WASHER2, {"p0": "Does the design contain this element: a round body?",
                            "p1": "Does the design contain this element: a centre bore?"})
print("washer with bore:   ", {k: round(v, 3) for k, v in w2.items()})
