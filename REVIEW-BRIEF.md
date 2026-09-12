# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** Section 8 (Import STL and STEP) is CLOSED
> after four rounds (`94eb47e`, `d94518c`, `8fdfa5b`, `8241115`; 13 findings,
> all fixed, 20 new tests, fast tier 1623 -> 1643). Round four's one finding
> was a P1 cost cliff, not a P0, so the queue's step 8 does not force a fifth
> read. The next `code review` goes to `REVIEW-QUEUE.md` and takes the first
> TODO row of the status board — **section 9, Trace image**. (The user may
> instead name `d94518c..8241115` — the nesting rule in `blocks.py`,
> `_solids_from_shells` and its helpers, ~150 lines — for a fifth read; each
> of rounds two to four found a hole in the round before it.)
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

## What the last review closed (section 8 — Import STL and STEP)

Never reviewed before this. Four rounds, 13 findings, all fixed, 0 rejected;
20 new tests; every finding reproduced by measurement first
(`probes/s8_*.py`, `s8r2_*`, `s8r3_*`, `s8r4_*`) and every fix locked by a
test proven RED on the commit it fixes. Rounds two to four ran on Fable 5.1
at the user's call.

The shape of it: round one found two P0s (a hollow STL imported with its
cavity FILLED plus a phantom body inside it — `is_valid` is a property, the
guard called it — and the parity voxel fill XORing overlapping material
away). Rounds two, three and four each found a hole in the round before it,
all in the ONE rule "which shell is a cavity of which body": by the SIGN of
each shell's volume (wrong for an inside-out file) → by nesting depth from
ONE vertex (turned an overlapping bracket into a void) → by a 400 + 400 point
survey (right, at ~140 s against a 32k-face housing) → by one confirming
point, trusting an inward-wound shell, with a survey sized to the container
only for an outward-wound one.

What the module now promises, each with a test: a hollow part is ONE body
with its cavity (wound either way, alone or beside other bodies, clean or
through the repair path, thin walls down to 0.005 mm); a body sealed inside
a cavity is a body; two bodies that overlap are two bodies (bracket in a
notch, pin through two walls); a body exported twice is not deleted; a
pinched cavity remeshes; a pinched mesh with flipped faces keeps its volume;
overlapping welded bodies keep their material; a remesh reports how much the
grid could not hold and refuses over 15%; 40 parts in a housing import in
~1 s; a not-a-STEP file and a truncated or BOM'd STL are named as such.

Not changed, measured on every commit: `imports/liquid-piston-2-v1.stl`
(88,990 triangles) imports to 339,926.9 mm3, 3 bodies, 21,552 triangles,
health clean, 25 s. No saved design uses `import_stl` or `import_step`.

Residuals, documented in the code, none silent: a body embedded in another
by all but less than one sampled point in `_nest_cap` reads as a void and
`MakeSolid.Add` then builds an INVALID solid (red row); an inside-out body
that also overlaps another is trusted as a cavity (two exporter bugs at
once; invalid, red); a mesh whose winding is inconsistent AND overlaps itself
takes the parity fill and loses the overlap (as before any of this).

## Where the next review goes

`REVIEW-QUEUE.md` section 9, Trace image — `imgtrace.py` and the trace
functions of `static/js/sketcher.js`, with `/api/trace-png`. The section's
paste line, finding classes and known items are in the queue.
