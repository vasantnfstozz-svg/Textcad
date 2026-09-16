# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `cc78019..HEAD` - the fix pass for the review of
> `b17d626..cc78019`. One commit, and it puts SIXTY new lines of geometry into
> the pre-kernel shell guard.
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

## Why this is PENDING when no P0 was fixed

`REVIEW-QUEUE.md` step 8 says a second round happens only after a P0, and the
finding below is a P1. It is PENDING anyway, and the reason is this repo's own
record: of the shell guard's three reviews, **round two and round three were
both bugs inside the previous round's own new guard** (fb0b8c8 -> 667ccc0 ->
b99a24d -> b5c6e70), and section 7's round two was too. This fix adds a new
geometric search to that same guard, and while writing it one bug of exactly
that kind was already found and fixed in it (a failed measurement left `None`
where a float was compared). A reviewer who disagrees may close it in a line.

## The range

    cc78019..HEAD          (base cc78019, the "thin everywhere" shell guard)

One commit: the fix pass for the review of `b17d626..cc78019`. Two findings
fixed, none rejected, 4 new tests.

Touched: `sketch.py` (the only product file), `tests/test_shell_tool.py`,
four probes. No frontend, so ui stays v200.

## What it changes

**F1 (P1), `sketch._climb_to_the_deepest`, new, called from
`deepest_material` ONLY when the guard is about to refuse.**
`cc78019`'s stations lie on rays through face sample points, so they find the
deepest material only when symmetry puts it on one - a box, a plate, a
cylinder. On a plain draft wedge (2 mm at one end, 30 at the other, 40 deep)
the stations reached 10.62 mm where the real maximum is 12.42, so a CLOSED
shell at 11, 11.5 and 12 mm was refused BEFORE the kernel, in a sentence that
told the user "walls must be under 10.62 mm", while the kernel builds all
three sound (314, 127 and 27 mm3 of cavity). The best measured points are now
walked uphill - away from the face nearest them, which is the direction the
inscribed sphere grows - and only then may a refusal stand.

**F2 (P3), `deepest_material` returns None when NO face stays.** Six clicks on
a box opens all six faces; the distance to an empty compound is no answer, and
the sentence came out "no point of it is more than 0 mm from the faces that
stay ... so walls must be under 0 mm". The kernel's own refusal speaks again.

## Where the risk is

- **The climb is a local search on a field with several maxima.** It takes the
  three deepest measured points and climbs each; a body whose real maximum sits
  in a basin none of those three reaches still reads low. That is the same
  class of hole as the one it fixes, one level further in - the reviewer should
  look for it. The safety argument is that it can only ever RAISE the answer
  (a point is accepted only when the same exact `BRepExtrema` measures it
  deeper), so it can turn a refusal into a build and can never invent one.
- **It runs only on the refusal path**, so the cost is paid exactly where the
  answer was going to be a refusal. Measured on the 675-face autonomiq-panel
  body; the numbers are below.
- **`_DEPTH_CLIMB_STEPS = 40` and `_DEPTH_CLIMB_SEEDS = 3` are budget numbers**,
  not theorems. They were set so the wedge converges to 0.005 mm of an
  independent grid's answer; a body needing more steps reads low.

## Cleared by measurement, not by argument

- The committed corpus (`probes/shell_thin_wall_corpus.py`) returns the SAME
  verdict as it did for `cc78019`: 238 cases, 24 refusals the kernel would have
  crashed/stalled/refused on, **0 false refusals** - and every crash body still
  reads its documented depth (`finding_mypart` 0.65 closed / 1.3 open,
  `oneplus_case` 1.0 / 1.2, `impeller_cut` 3.5, box 15 / 25, cylinder 20 / 25,
  hex prism 12.5 / 25, l-bracket 10, plate with hole 5 / 10). The crash
  protection `cc78019` exists for is untouched.
- An independent oracle - a hierarchical grid over the whole interior,
  `probes/shell_depth_oracle_probe.py` - now agrees with the guard on every
  shape tried, where before it found the wedge 1.80 mm and an L-plate 4.75 mm
  short.
- **The user's designs, both ways** (`probes/shell_depth_library_probe.py`,
  the finished body of every design measured with the climb and without it):
  50 designs, 47 bodies, **36 body/mode combinations across 25 designs sat in a
  band `cc78019` refused wrongly** - widest `my-part-2` closed 38.62 -> 41.47
  (2.85 mm), then planetary-carrier 6.667 -> 9.092 open, thread-case
  17.13 -> 19, isogrid-panel 7.427 -> 9.198, pump-housing 7.333 -> 8.292. Half
  the library, so this was not a corner.

## Cleared for `b17d626..cc78019` - do not re-report

- **The cost of the pre-kernel guard on a 675-face body**, which `cc78019`'s
  own brief flagged as unmeasured: `probes/shell_depth_cost_probe.py` on the
  scaled autonomiq-panel body reads tessellate-every-face 0.96 s, the allow
  path 2.4 s and the whole refusal path 7.1 s, against a shell that takes
  692 s. It is not a problem.
- **`stays()` comparing openings by `IsSame`** where `assert_every_lump_open`
  uses a geometric `_shape_key`: measured sound for a NAME and for a PICK, and
  the three depths agree exactly (`probes/shell_depth_review_probe.py`).
- **Reversed faces on a mirrored body** (12 of my-part-5's 25): `normal_at`
  carries the orientation, so the inward ray really goes inward - zero faces
  wrong.
- **`face.is_inside(face.center())`** really is a face classifier in this
  build123d, not a solid one.
- **An OCCT exception escaping the guard**, which runs OUTSIDE kernelguard:
  `document.rebuild` catches it and `blocks.plain_cause` renders it as "the
  geometry kernel rejected the shape it would produce" - a sentence, not a
  traceback.
- **`275eeab`'s skin ceiling, which its own brief called "the one judgement
  call".** Measured over the user's library for the first time
  (`probes/shell_skin_library_probe.py`, 50 designs, the skin check patched off
  so a result it would refuse is still measured): of 37 results that pass every
  OTHER check, 35 read 0.4449-1.0377 and two read 2.0524 and 2.7189 - and both
  of those are genuinely WRONG bodies. On designs/cam-cover-lower at t = 1 the
  kernel removed 971.569 mm3 where the real cavity is 39,921.8 +/- 280.9 by
  Monte Carlo (`probes/shell_skin_camcover_probe.py`). The check earns its keep
  on the user's real parts. The caution runs the OTHER way and is now
  LAUNCH-PLAN section 10 (P2): 2.0524 clears the ceiling by 2.6 per cent.
- Everything `cc78019`'s own brief listed under "Do not re-report" still
  stands: the my-part 1.1 mm crash reaching the kernel, the my-part-9 stall,
  the lone-rib expectation moving one step earlier, the my-part-5 segfault,
  OUTSIDE shells not being judged, kernelguard's sleep-counting budget.
- The reviewer may of course say any of these calls was wrong.
