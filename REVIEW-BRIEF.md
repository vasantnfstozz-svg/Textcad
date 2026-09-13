# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `53f5653..HEAD`. That is THREE code commits: the
> two the previous brief named and that have still not been reviewed
> (`77bc7fa`, `2231095`), plus `f7c1d1f` - a new top-level module that puts
> the three segfaulting ops in a child process. It is the largest structural
> change since the supervisor, it is on the path of EVERY fillet, chamfer and
> shell the user or the AI builds, and it moves geometry across a process
> boundary, which is a brand-new door for silent wrong geometry. Read it as if
> nothing about it had been checked.
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

## The range: `53f5653..HEAD`

- `77bc7fa` - Fillet/Chamfer: `blocks._assert_is_a_blend` measures what the
  kernel returned; 9 new tests. **Not yet reviewed.** The previous brief's note
  on it still stands and is repeated under "Where the risk is" below.
- `2231095` - the journey runner's oracles: the geometry is asked before the
  clock, and a child that answers nothing is killed; 3 new tests. **Not yet
  reviewed.**
- `f7c1d1f` - the kernel worker (2026-09-13): `kernelguard.py` (new, ~470
  lines) plus the seams: `blocks.py` (`_finish` split, the new
  `blend_after_guards`, `_BLEND_KERNEL`), `sketch.py` (`shell` split, the new
  `shell_after_guards`), `document.py` (a `transient` failure is not cached),
  `static/js/api.js` + `static/index.html` (the busy overlay speaks at 20 s and
  90 s, ui v199), `tests/journeys.py` (two new oracles), `tests/conftest.py`
  (the `in_process_kernel` fixture), `tests/test_kernel_guard.py` (new, 21
  tests), `tests/test_fillet_tool.py` + `tests/test_supervisor.py` (they ask
  for the in-process kernel by name now), five probes, `ARCHITECTURE.md`,
  `LAUNCH-PLAN.md` (5 rows rewritten, 1 added), `.gitignore`.

## What the kernel worker does, in one paragraph

OpenCASCADE segfaults on the user's own parts, in one click, and an access
violation is not an exception - no `except` in this process will ever see it.
The overnight run of 2026-09-13 filed four of them and the measurements that
followed said no geometric bound fences any: `fillet` on the eight flat rims of
a sliver body dies at every radius from 0.05 to 0.5 and refuses politely at
0.8, while ANY ONE of those rims alone never crashes and all 53 at once never
crash either; `shell` open-bottom 1.1 on the oneplus case dies while 0.2 builds
and 2.0 refuses (the window is not monotonic in thickness); a CLOSED `shell` of
1.9 on the pump impeller's three lumps dies at every thickness from 0.8 to 2.9,
and the SAME shell built at the previous `z` with every bounding box identical.
Shell's own review already spent three rounds on geometric guards and TWICE
ended up refusing correct geometry, so `LAUNCH-PLAN.md` section 10 had already
concluded the answer was structural. It is built: the half of each op that
touches the kernel (`blocks.blend_after_guards`, `sketch.shell_after_guards`)
runs in a WARM child process, its death becomes a plain refusal and a red row,
and a call that outruns `TEXTCAD_KERNEL_SECONDS` (900) is killed and says so.
Verified: all three committed crash bodies refuse in a process that lives, and
the planetary-ring `/api/edit` that ran **3 h 6 min** in the overnight run
answers in 169 s at a 120 s budget and 60 s at 30 s - the budget is the whole
of the difference, so the spin is inside a guarded call.

## Where the risk is

1. **A process boundary is a new door for silent wrong geometry, and that is
   worse than the crash it replaces.** Three checks stand in that door and all
   three are mine, none of them reviewed: the body's VOLUME is compared on both
   sides (`same_weight`, tolerance `1e-9` relative); each picked edge/face
   crosses as an INDEX plus a `[size, cx, cy, cz]` fingerprint that the worker
   re-measures (`take`, tolerance `1e-4`); and `indices()` finds those indices
   by `hash(shape.wrapped)` with an `==` confirm. **The sharpest question for
   the reviewer: is `hash(TopoDS_Shape)` stable across the two routes a pick
   arrives by?** `edges_for` can return an edge taken from `part.faces()[i].edges()`
   rather than from `part.edges()`, OCCT's hash folds in ORIENTATION while
   `IsSame` does not, and a lookup miss raises "a shape that was picked is not
   part of this body" on correct geometry. The fillet tests that pick through
   faces pass, so it holds in practice - it is not proven, and a linear-scan
   FALLBACK was added for exactly that doubt, which means the hash path could
   be silently wrong for every pick and every test would still be green.
2. **The `.brep` round trip is trusted for ORDER.** `take` re-measures each
   picked shape, so a reordering is caught - but only for the shapes that were
   picked. Nothing checks that the body's OTHER faces and edges kept their
   order, and `assert_every_lump_hollowed` (which runs in the worker) compares
   result lumps to INPUT lumps, both post-round-trip. A compound flattened in
   transit would be caught by `same_weight`; a compound REORDERED would not.
3. **The 900 s budget refuses correct work.** It is above every correct blend
   the overnight run measured (630 s, 156 s) and below the 3 h spin, but the
   run's slowest correct call was a 1195 s shell on autonomiq-panel, which is
   now STOPPED at 15 minutes instead of answering at 20 (section 10 row, P3,
   and the previous brief's "still unmeasured" note about that body's soundness
   will now never be answered by the app). Whether 900 is the right number is a
   judgement, not a measurement.
4. **The failure is deliberately NOT cached** (`document.py`, `transient`). A
   crash refusal therefore costs a full re-evaluation on every rebuild while it
   is on screen, where every other failure is cached. On a design whose fillet
   crashes, every rebuild now pays the crash AND a 10-30 s worker restart.
5. **One lock, held across the child.** `kernelguard._LOCK` is held for the
   whole call including the budget wait, INSIDE `studio._KERNEL_LOCK`. Two locks
   in a fixed order is not a deadlock, but nothing proves the order is fixed -
   `_warm_up_soon` takes `_LOCK` on a daemon thread, and `shutdown()` takes it
   from wherever it is called.
6. **The worker restart path is the least exercised code here.** `_fresh_worker`
   raising `KernelGone`, a worker that dies during its own startup import, a
   `_warm_up_soon` thread that fails silently and leaves `_WORKER` None for
   ever, `READY_SECONDS` (180) on a loaded box - none of those is a test.
7. **`_cap_memory` is untested and silent.** It assigns the worker to a Windows
   Job object AFTER `Popen` (no `CREATE_SUSPENDED`, unlike `tests/journeys.py`'s
   `JobCap`), swallows every exception, leaks the job handle on purpose, and
   reaches into `proc._handle`. If it silently does nothing, the 6 GB ceiling
   the user's laptop crash bought is not there.
8. **The blend bound's two constants (`77bc7fa`, still unreviewed).** They come
   from 14 fillet/chamfer features across 52 designs, and a legitimate blend on
   a SHARP wedge moves more material than a 90-degree one (`r^2 / sin(theta)`);
   the library has no such edge, so nothing measured that case.
9. **The runner's stall watchdog (`2231095`, still unreviewed).** It polls a
   JSON file every 2 s and kills on no change; `steps_taken` returns -1 for a
   half-written file and the loop reads that as no news.

## Do not re-report

- **That the guard is not universal.** Booleans, 2D offsets (`sketch.py:1259`,
  `1355`, `1505` - a degenerate offset wire access-violated the server once
  before) and tessellation still run in the server, and `supervise.py` is what
  covers those. Deliberate: the guard costs a `.brep` round trip per call, and
  putting every op through it would put that on every feature of every rebuild.
- **That `tests/test_supervisor.py` now starts one server with
  `TEXTCAD_KERNEL_GUARD=0`.** The test is about the supervisor, whose crash
  still has to work for the doors above; the guard would have removed its crash.
- **That four tests in `tests/test_fillet_tool.py` ask for `in_process_kernel`.**
  They spy on `blocks._b3d_fillet` or make it throw, which a process boundary
  puts out of reach; they are tests of the in-process guard chain.
- **The cost.** Measured, not guessed: a cold worker is 10-30 s (once), a warm
  call adds about 40 ms on a small body and about 0.9 s on the 968-face traced
  keychain (`probes/sidecar_cost.py`, `probes/sidecar_roundtrip.py`); the fillet
  + shell gauntlets go from 23.4 s to 41.3 s, most of that the single cold start.
- **That OCCT progress callbacks were considered and are not available.**
  `Message_ProgressRange` exists and `Build()` takes one, but OCP will not let
  Python subclass `Message_ProgressIndicator` ("No constructor defined") - so a
  no-progress stall detector is impossible and the budget has to be a clock
  (`probes/occt_progress_probe.py`).
- **That filleting the picked edges ONE AT A TIME was rejected**: it changes the
  geometry at shared vertices.
- `bugs/journeys-stdout.log` is tracked and grows every night; it is left
  uncommitted on purpose. `bugs/kernel-crashes.log` is now ignored.

## Ground rules

Ruff zero; ESLint zero; fast tier `1734 passed` and `-m library` `101 passed` at `f7c1d1f`.
Probe first; anything that can eat memory runs under `probes/memcap.py --gb 6`.
Never two OCCT workloads at once. Fix in the same chat, then this file ->
`Status: NOTHING PENDING` (next review takes REVIEW-QUEUE section 9, Trace
image).
