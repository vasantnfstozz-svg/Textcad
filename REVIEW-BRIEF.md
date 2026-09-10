# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING** — `b8a956f` re-read section 6's fix pass and
> found two findings, both P3 and neither live for the user, so there is no
> third round to run. The next `code review` goes to the queue and takes
> section 7, Extrude as a whole module.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range below; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes. Everything specific to this review is below.

---

## Just done: section 6's FIX PASS, re-reviewed (b8a956f)

`3ce97a3` closed a P0-class finding — over 400 faces the mesh switched to a
cheaper path that had its OWN edge numbering, so on 12 of the 50 saved
designs every edge click measured a different edge, and one could open an
edit box driving a hole the user never clicked — so the house rule sent a
second chat over the fix commit. It found **two findings, both fixed**, 2 new
tests, fast tier 1389 green.

Both were in the fix pass's own new code, which is where the queue said the
risk would be, and **neither was live for the user**:

- **P3: the extents fallback could never run.** `_measure_one`'s world-bbox
  fallback shared one `try` with the in-frame projection it is a fallback
  for, so an exception in the projection abandoned both and the row vanished
  instead of degrading. No real face reaches it; it took a patched
  `face_plane` to force. It has its own `try` now.
- **P3: a reverted edit still handed back `picks`.** Those ids describe the
  post-write body, and `_revert_last()` then restores the previous one — a
  ⌀8 bore whose ⌀38 edit was reverted came back as `picks.a` id 6, which in
  the restored body is a 6.28 mm² face. `measure.js` ignores `picks` unless
  the edit verified, so nothing misbehaved; it was one guard away. `picks`
  is only sent when the edit stands.

**The risk the brief named first was cleared by measurement, not by reading:**
322 driven edits through `/api/measure/set` across 9 saved designs — 92
diameters, 58 moves, and 172 deliberately destructive ones (tripling each
bore, then shrinking it to a sliver) — each checked against an independent
oracle written inline (axis collinearity for bores, plane offsets along the
normal for moves). **Zero false passes, zero false fails.** Also cleared:
`_shape_key` does not collide across located copies (70 identical boxes, 840
distinct keys); the mesh fix loses no outlines (identical distinct edge sets
on esp32-remote, isogrid-panel and planetary-assembly); the mixed-body cost
is +7% on a path already dominated by the mesh; dead-flat BSPLINE walls take
the new extents path correctly; an edge pick drives end to end; and face
order is deterministic across identical rebuilds.

Section 6 is closed. See `REVIEW-QUEUE.md`'s done log for the detail.
