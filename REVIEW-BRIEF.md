# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `bf5550b` — the FIX COMMIT of the P5b
> review (round two). Base `f6add94`. A P0-class finding was fixed, so the
> queue's rule applies: the fix pass's own new code gets read.
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

## The commit

Round one of the P5b review (`7a811b6..c11fd74`) found 9, fixed 9, 0 rejected,
12 new tests (fast tier 1657 -> 1668). TWO were in the PRODUCT, found by the
instrument P5b had just added; seven were the instrument lying about it.

- `document.py` — `strike` records the ids it actually suppressed
  (`_struck_by`, in memory, not in the file; `rename` rewrites it) and
  `unstrike` puts back exactly those plus the struck ancestors the restored
  set cannot build without, decided by `_passthrough` (the delete plan's own
  healing rule).
- `tests/journeys.py` — `unhandled()` asks builtins and OCP for the exception
  NAMES instead of guessing at suffixes; `Bug` carries a baseline document and
  the whole sequence to resend; `call` checks a dry run; `replay` re-asks the
  identity question, falls back to `after.tcad.json`, and still reads a
  pre-fix folder; `make_client` moves `MESH_PATH` off the repo root; a new
  `write_crash` keeps the child's stderr and refuses to file a folder when the
  MACHINE ran out of memory.
- `static/js/bugreport.js` — a successful GET no longer costs a ring slot
  (`worthKeeping`), ui v198.
- Tests: `tests/test_strike.py` (+4), `tests/test_journeys.py` (+7),
  `tests/e2e/test_bug_button.py` (+1). Every one proven RED in a worktree at
  `c11fd74` before the fix, except the two whose red proof is a missing
  function (`write_crash`) and the one that locks a case two mechanisms
  already cover (its docstring says so).

## Where the risk is

On this project a fix pass's OWN new guard has been wrong more often than not,
and this one changed a path every saved design walks.

1. **`unstrike`'s new rule.** `_passthrough(dep, still, by_id, kinds)` decides
   whether a struck ancestor hands its own input down. `still` is rebuilt as
   `back` grows — is it right for a chain of several struck nodes, for a
   `move` (whose `_kinds` entry follows its input), and for a struck node
   whose first input is itself struck and a SKETCH? The regression guard is
   `test_restoring_a_dependent_restores_its_struck_sketch_too`, which existed
   before; the new tests cover a cut chain and a fillet.
2. **`_struck_by` is state that outlives nothing.** Undo replaces the document
   object, so the record is gone and the restore falls back to the plan
   (§10 P2 row). `Document.rename` rewrites the record (found and fixed inside
   this pass, with the key case proven red). Is there another sequence where
   the record is present but STALE and the fallback would have been better —
   a `remove` of a recorded id, an `edit` that changes what the plan would be,
   `edit_many`, a version restore into the same tab?
3. **`unhandled()` now flags any `<ExceptionName>: ...` prefix.** The name set
   is builtins + `OCP.Standard` + `OCP.StdFail`. A product sentence that
   begins with one of those names and a colon would file a phantom finding —
   is there one? (`Error: none` is not in the set, and is tested.)
4. **`replay`'s identity re-ask.** `_IDENTITY_BUGS` is a hand-kept set of
   kinds; a new pair oracle added later and forgotten there replays as
   "passes now" again. And the comparison is `j.data() != base or
   j.volumes() != vols` — `volumes()` swallows a raising `.volume` as None.
5. **`worthKeeping`** drops every 200 GET, so `/api/model` and `/api/mesh.stl`
   are no longer in the report at all. Was one of them load-bearing for a
   repro (a mesh that never arrived)?
6. **`spawn` now captures stderr** (`subprocess.PIPE`, `text=True`). stdout is
   still live, so a child that fills the stderr pipe cannot deadlock — but is
   that true of a child that dies mid-write, and does the `[-8000:]` tail ever
   cut a `MemoryError` line out of reach of `machine_gave_up`, which would
   file the box's failure as the product's again?

## Ground rules for this review

Reproduce before reporting. Fix in the same chat, smallest fix, test proven
red first. Restart the user's server if `studio.py` changes (it did not this
time). Never `--fix`.

## Do not report (already decided or recorded)

- `_struck_by` not surviving a save or an undo — §10 P2 row, on purpose: the
  file format carries one boolean per feature and changing it touches every
  saved design.
- `/api/bug` reading the document without the kernel lock — §10 P3 row;
  measured to touch no OCCT at all.
- The journey runner's unchecked rename / suppress round-trips, and that it
  never plays `loft` or `sweep` — appended to the existing §10 P3 row.
- `check_bodies` re-asking the product's own `inspector.health` on the
  product's own leaf set: it is a cache-coherence check by design, not an
  independent witness.
- The values-at-random and viewport-only-screenshot rows (§10 P3).
