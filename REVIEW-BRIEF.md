# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
> **A rewrite must carry over every PENDING range it did not review** - this
> brief exists because one did not.
>
> **Status: NOTHING PENDING** - the five Tier 2 tools built on 2026-09-17
> (never reviewed until today, restored to this brief at `9e51bd8`) were all
> reviewed and fixed on 2026-09-23 in ONE Opus 5.5 chat, the user asleep, on
> their instruction to "review, fix, re-run, fix, until no bugs are found".
> Every P0 fix got its own re-read in the same chat, and a last re-read of
> the whole fix range found one more gap (fixed, `eddd909`) and then none.
> The next `code review` has nothing queued here; `REVIEW-QUEUE.md` is empty
> too (all 13 sections closed 2026-09-17).

## What was reviewed and fixed (base `48f6920`)

| Tool | Findings | Commits |
|---|---|---|
| Named parameters | 11 (3 P0) | `cc0ff03`, round two `767f95b` |
| Sweep | 5 (2 P0-class folds) | `c908da5`, round two `d52d495`, final `eddd909` |
| Loft | 2 (P1, P3) | `c7b09cd` |
| Text entity | 4 (P2, P2, P3, P3) + a cache | `547b75c`, `38c329d` |
| Section view | 1 (P3) | `f7cca4d` |

The P0s, for whoever touches these tools next:

- **Named parameters.** A parameter that drives a `move` slid the body and
  left its face picks behind (14010.62 -> 18000.0 mm3, all green).
  `floor(1e400)` wrote a parameter the file could not reopen with. Every
  tool's edit panel turned a formula into 0, and OK wrote it back. **The
  rule:** a numeric param is read through `Document.values()` /
  `_resolved`, never `float(params[k])`.
- **Sweep.** The kernel turns the profile about the path's START, not the
  profile's centre (every earlier probe used straight paths).
  - An off-centre start hid a fold from the guards.
  - A slanted profile folds at `a - b(m.N)/(t.N) >= R`, not `a >= R`.
  - OCCT calls both of those valid, at the exact Pappus volume.
  - Only `sketch.sweep_geometry` can see them.

## Do not re-report

- Everything listed as known in LAUNCH-PLAN section 10's Tier 2 "loose ends"
  rows (Sweep, Loft, Text, Section view, Named parameters).
- A legacy 3D `path_points` sweep (not planar) keeps the full-reach bend rule
  and is volume-checked only when it starts at the centroid - deliberate;
  its spline bends have no bend guard (pre-existing, AI-authored trees only).
- A loft through a U-turn is refused, by design: the kernel's loft through
  one intersects itself (`probes/loft_review_probe.py`).

**How the review starts.** The user opens a fresh chat on Opus
(`/model claude-opus-5-5[1m]`) and types only `code review`. CLAUDE.md's
section "The review chat" tells that chat to read this status line: PENDING
means review the range named here; NOTHING PENDING means go to the queue.
