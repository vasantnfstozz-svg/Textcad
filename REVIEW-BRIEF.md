# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** The P5b review is closed after two rounds. The
> next `code review` opens `REVIEW-QUEUE.md` and takes the first status-board
> row marked TODO — **section 9, Trace image**.
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

## What the P5b review did (for the record; nothing here needs re-reading)

**Round one — `bf5550b`, paperwork `8e32e69`.** 9 findings, all 9 fixed, 0
rejected, 12 new tests. TWO were in the PRODUCT, found by running the
instrument P5b had just added (44 journeys, ~2,700 requests); seven were the
instrument lying about the product. The P0: `unstrike` walked upstream and
un-struck every struck ancestor, so on designs/esp32-remote — where the user
has the logo OFF — striking and restoring any feature below it brought the
logo back and milled 227.86 mm3 away (107,484.782 -> 107,256.922), announced
only as a list of ids in a chat line. A strike now RECORDS what it suppressed
and a restore puts back exactly that plus only the ancestors the set cannot
build without.

**Round two — this commit.** The queue's rule sent it at the fix commit's own
new code, and it found ONE thing, in the half of the fix that was NOT
measured in round one:

- **`/api/feature/suppress` sets the flag behind `strike`'s back.** No UI
  button does, but the AI, the MCP and the journey runner's `move_misc` do.
  Strike A (which sweeps B up), suppress and re-suppress B by hand, then ↩ on
  A: B came back although the last hand on B struck it deliberately.
  `Document.set_suppressed` now prunes that row out of every ✕'s record.
  **The first attempt at this fix was backwards** — it dropped the record
  KEYED on the row too, which falls back to the recomputed plan, which is
  round one's exact bug; there is a test for that overreach as well as for the
  finding.

The other five risks round one named are CLEARED by measurement, not argument:

1. **The new `unstrike` rule is never worse than the old one.** Both restore
   sets computed for every feature of every design that carries struck rows
   (esp32-remote 81, my-part-8 27, my-part-5 24, pump-impeller 10), then every
   feature where they DIFFER rebuilt and checked: they differ on 5, 2, 2 and 0
   features, the difference is always that the new rule KEEPS the user's
   struck row, nothing is red after any restore, no volume moves, and on a
   design with nothing struck the new rule is a provable no-op.
   `probes/p5b_r2_unstrike_sweep.py`. Also measured: a struck `move` chain
   upstream (whose `_kinds` follows its input) stays struck with no red, and a
   struck sketch behind a struck extrude still comes back with its tool.
2. **The widened exception classifier reads no product sentence as a leak.**
   Every string literal in every `.py` (ast walk) tested against the 90-name
   set: all 29 matches are docstrings or test literals that genuinely ARE
   exception text.
3. **`_IDENTITY_BUGS` is complete today** — every `Bug` raised with a
   multi-step `replay` is in it, and `tab-leak` is correctly in
   `_REPLAY_BLIND`. Not a finding, so not touched.
4. **`spawn`'s stderr capture cannot deadlock** (one pipe, read to EOF by
   `communicate`). Hardened anyway: the machine-gave-up verdict now reads the
   WHOLE stderr and only the tail is kept for the folder, so truncating the
   display cannot turn the box's failure back into the product's.
5. **`worthKeeping` dropping successful reads** loses nothing a repro needs,
   but the report's heading claimed "every request this tab made" — it says
   what it actually keeps now, so a later reader cannot conclude the tab never
   loaded a mesh.

Proof: fast tier and library tier green, run one at a time (two heavy OCCT
runs at once put the box out of memory and crashed both — see the §10 rows).

## Still open, recorded not fixed

`LAUNCH-PLAN.md` §10 carries them: the `shell`-on-a-scaled-body SEGFAULT with
its repro in `bugs/` (P1), `_struck_by` not surviving a save or an undo (P2),
a sixth pre-existing red browser test (P2), and `/api/bug` reading the
document without the kernel lock (P3).
