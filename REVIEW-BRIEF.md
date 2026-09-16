# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** The next `code review` goes to `REVIEW-QUEUE.md`
> and takes the first status-board row marked TODO - **section 9, Trace image**.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range named here; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes.

---

## What was just reviewed and fixed

    cc78019..3bbfcca   reviewed        (the shell depth guard's climb)
    b9a8f8f            the fix pass    1 of 1 findings fixed, 0 rejected, 2 tests

`3bbfcca`'s own brief asked the reviewer to hunt for one thing: the climb is a
local search, so a body whose real maximum sits in a basin none of its three
seeds reaches still reads low. It is there, it was reproduced, and **half of it
is fixed**.

**The finding (P2).** The guard still reads below the real deepest material, so
its refusal quotes a wall limit that is too low. Measured against an
independent grid over the whole interior, **18 of 58 library body/modes read
low**, my-part-3 by 1.5 mm (26.1037 against 27.6094).

**Fixed - COVERAGE.** A flat face tessellates into one to six triangles however
big it is, so one ray per centroid spent **33 of a 108-point sample budget** on
the review's wedge-in-a-slab and put no ray within 40 mm of the taper's thick
end. The climb is a LOCAL walk: what it needed was a seed nearby, not more
steps (400 steps move nothing). `sketch._barycentres` fills each picked
triangle to the budget, the centroid FIRST, so a body that already had enough
triangles is sampled exactly as before.

**Deferred - SEED RANKING** (LAUNCH-PLAN section 10, P2,
`probes/shell_depth_plateau_probe.py`). The climb seeds from the three DEEPEST
samples, and a uniform region measures exactly what its chord allows, so it
outranks every station on a taper whose real maximum is higher. On a 2-to-30 mm
draft wedge fused into an 80 x 80 x 24 slab the guard reads the slab's 12.0000
against a real 12.4300, and `shell` refuses 12.05 / 12.2 / 12.4 mm while the
kernel builds all three valid. **24 seeds do not fix it** (the slab holds dozens
of samples at exactly 12.0, all more than 12 mm apart) and neither does 400
steps: a plateau has no gradient to climb. The candidate is spatial seeding and
it wants its own cost measurement first.

## Where the risk is

- **The change can only RAISE a measured depth, and a raised depth turns a
  REFUSAL into an ALLOW.** That is the whole of the risk, and the corpus cannot
  see it - `shell_thin_wall_corpus.py` asks the kernel only where the guard
  REFUSES. The complement was measured instead: **every wall this change newly
  permits, put to the kernel one by one**
  (`probes/shell_depth_newly_allowed_probe.py`). Corpus bodies and crash
  bodies: every one refused in a sentence. The three live designs whose depth
  rose: **24 walls, all sound or refused in a sentence, 0 not.**
- **Said out loud: two walls now reach the kernel and SEGFAULT it.** my-part-3
  top open at 26.41 and 26.87 mm were refused before on a number that was
  wrong; the kernel worker catches both as a sentence with nothing changed,
  which is what it is for, and that band is the kernel's own pathology rather
  than this guard's question. A reviewer may say that trade was wrong.
- **The budget arithmetic is what keeps big bodies free.** `per_face` is
  `200_000 // faces**2`, so a body of 130+ faces already gets ONE sample and
  `_barycentres(1)` is the centroid and nothing else. That is measured, not
  argued: the 675-face panel's refusal path reads 7.2 s against 7.7 s before.
  A reviewer who doubts it should re-measure `probes/shell_depth_cost_probe.py`.

## Cleared by measurement - do not re-report

- **The crash protection `cc78019` exists for is untouched.** Every committed
  crash body reads exactly its documented depth (oneplus_case 1.0 closed /
  1.2 open, impeller_cut 3.5, mirror_shell 17.5, crash_fillet 24.3295), and the
  corpus returns the same verdict as before: **238 cases, 24 correct refusals,
  0 false refusals.**
- **The climb's containment gate, the ONE door to a false ALLOW.** `outside()`
  takes UNKNOWN and ON as inside, and an escaped point measures a real distance
  that RISES with every step outside the body - so one wrong classification
  would let the answer run away. `BRepClass3d_SolidClassifier` gave **zero
  UNKNOWN in 116,000 classifications** over 9 shapes including a Compound of two
  lumps, a mirrored body and 5 live designs, with on-face points reading
  ON / IN / OUT exactly as the step logic assumes
  (`probes/shell_depth_classifier_probe.py`).
- **The classifier works on a Compound**, which is what every build123d
  `Part.wrapped` is: IN/OUT correct across the gap between lumps, inside a
  through hole and inside a closed void.
- **`3bbfcca`'s F2 (every face opened) is sound and hands the kernel no crash.**
  With all 6 faces of a box, a 12.7 mm thin box and the 60-face oneplus_case
  crash body opened, `deepest_material` returns `None` and `shell` comes back
  with the kernel's own "nothing was hollowed" - in process, no worker needed.
- **How much the residual actually costs the user, measured rather than
  assumed:** on 6 of the 8 live bands put to the kernel it REFUSES TOO, so only
  the number in the sentence is wrong; on 2 it builds sound and the cavity is a
  sliver (fan-disk t = 2.55 removes 301.190 mm3 of 34,649; my-part-2 t = 41.8
  removes 6.014 of 1,297,968). That is why the residual is P2 and not P1.
- Everything `3bbfcca`'s own brief listed under "Cleared for `b17d626..cc78019`
  - do not re-report" still stands: the pre-kernel guard's cost on a 675-face
  body, `stays()` comparing openings by `IsSame`, reversed faces on a mirrored
  body, `face.is_inside(face.center())`, an OCCT exception escaping the guard,
  and `275eeab`'s skin ceiling (LAUNCH-PLAN section 10, P2).
- **Coverage of the review's own sweep, said out loud:** 11 bodies over 400
  faces were skipped (the grid oracle is too slow on them) and the library
  sweep was stopped on rocky-keychain's second mode, so **58 body/modes were
  measured, not the whole library**.
- The reviewer may of course say any of these calls was wrong.
