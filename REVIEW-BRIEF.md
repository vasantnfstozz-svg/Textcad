# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `53f5653..2231095` (two commits, `77bc7fa` and
> `2231095`) - the fix pass for the overnight run's eight findings, and for
> the review of `8f72d9e..53f5653`, which is now DONE (what it found is below).
> A P0-class finding was fixed, so the queue's step 8 asks for a second read of
> the FIX COMMIT, and this project's own history is the reason: a fix pass's
> own new guard has been wrong more often than not. `77bc7fa` puts a measured
> bound on the RESULT of every fillet and chamfer, and it runs on every rebuild
> of one.
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

## The range: `53f5653..2231095`

- `77bc7fa` - Fillet/Chamfer: `blocks._assert_is_a_blend` measures what the
  kernel returned; 9 new tests (fast tier 1701 -> 1710). Files: `blocks.py`
  (+45: `_BLEND_VOLUME_FACTOR`, `_BLEND_SHRINK_FACTOR`, `_bbox_retreat`,
  `_assert_is_a_blend`, and the tail of `_finish` re-shaped so the health
  refusal comes first and the measurement runs after it),
  `tests/test_fillet_tool.py` (+7 tests), `tests/test_fillet_gauntlet.py` (the
  bound asserted across the whole corpus),
  `tests/fixtures/sliver_intersect_plate.brep`, seven probes.
- `2231095` - the journey runner's oracles: the geometry is asked before the
  clock, and a child that answers nothing is killed; 3 new tests (1710 ->
  1713). Files: `tests/journeys.py` (+45: `STALL_KILL_S`, `steps_taken`,
  `wait_or_kill_a_stalled_child`, `spawn` draining stderr on a thread,
  `write_crash` gaining `stalled_s`, `--stall-secs`), `tests/test_journeys.py`
  (+3 tests), `LAUNCH-PLAN.md` (4 section-10 rows), two shell fixtures, two
  probes, and the eight bug folders the overnight run filed.

## What each fixes, in one paragraph

**The P0 (`77bc7fa`).** The overnight run - 512 journeys, 496 clean, 8
findings - filed `bugs/20260912-232440-my-part-8-s46791-crash/` as a segfault.
It is one, but underneath it was worse. On that design's `intersect` body
(181.499 mm3, valid by `BRepCheck_Analyzer`, unchanged by `.clean()`,
`inspector.health` empty, and carrying a ZERO-area cylindrical face with edges
0.00014 mm long) a radius-0.4 round on ONE picked edge came back 44.621 mm3.
Valid. Healthy. Green row. Saved. All eight of its flat rims did the same
(34-46 mm3 of 181.5; the 50.67 mm wide bounding box collapsing to 1.0 mm).
`_finish` called the kernel once and never asked what came back. It measures
now: over every fillet and chamfer in the library
(`probes/fillet_result_corpus.py`) an honest one moves 0.204 to 0.377 of
`value^2 x picked edge length` - the 90-degree ideals are `1 - pi/4` and 0.5 -
and retracts the bounding box by at most 0.155 x value. The bounds are 3x and
12x. BOTH run: the volume test alone misses the widest radius (3.8x, under the
bound) and the box test alone is loose on a sharp wedge. All 52 designs
rebuild with zero feature errors (`probes/library_blend_guard.py`).

**The runner (`2231095`).** Two defects in `53f5653`'s own new oracles. First,
the clock spoke over the geometry: a Bug ENDS the journey, and `HANG_MS` was
checked before "every green body on screen is sound", so autonomiq-panel's
1195 s shell was filed as a "hang" and nothing ever asked whether the body it
returned was sound. The document and geometry oracles run first now; the clock
and the memory reading are last. Second, `HANG_MS` is only read when a request
COMES BACK, so one that never does is invisible to it: journey 512
(planetary-ring s47276) sat in one `POST /api/edit` from 05:09:13 to 08:15:33
- three hours and six minutes - and what ended it came from outside the
runner, which filed "exit code 4294967295". The PARENT watches the child's
step log now (`_flush_log` writes it BEFORE each request, so the count rising
is progress and the last entry is the request the child is in): no new step
for `--stall-secs` (default 600) and the child is killed and filed as a `hang`
naming that request. Verified end to end on that very seed at
`--stall-secs 90`.

## Where the risk is

1. **The blend bound's two constants are the whole guard.** They come from 14
   fillet/chamfer features across 52 designs - a small corpus, and every one
   of them a round or bevel the user meant. A legitimate blend on a SHARP
   wedge moves more material and retracts the box further than a 90-degree one
   (the removed cross-section grows like `r^2 / sin(theta)`); the library has
   no such edge, so nothing measured that case. A false refusal would read
   "what it returned is not a blend of this body" over geometry that is fine.
2. **`_assert_is_a_blend` runs on every rebuild of a fillet or chamfer.** It
   costs one `volume` and two `bounding_box()` calls on the input and on the
   result. Not measured against the cached-rebuild path, which skips the build
   and the health check together.
3. **The bound cannot fence the segfault it was found beside.** Filleting
   several edges of that same body at once still dies (section 10 row); the
   guard is post-kernel by construction, and nothing it does helps there.
4. **The stall watchdog polls a JSON file every 2 s and kills on no change.**
   `steps_taken` returns -1 for a half-written file and the loop reads that as
   no news, so a child writing its log slowly could in principle be killed
   while alive; 600 s against a file written before every request makes that
   unlikely but it is not proven. `proc.kill()` on a process inside a Job
   object, and the stderr reader thread's 30 s join, are unmeasured against a
   child that ignores the kill.
5. **`spawn` no longer calls `communicate()` on the main thread.** stderr is
   drained on a daemon thread; if that thread has not finished when
   `reader.join(30)` returns, `full_err` is None and the "did the machine give
   up" verdict is read from an empty string - which would file a MEMORY death
   of the box as a product finding, the exact confusion `machine_gave_up`
   exists to prevent.

## The review of `8f72d9e..53f5653` - DONE, and what it found

ONE finding, fixed in `2231095`: the oracle ordering (defect 1 above). The
rest of that range was read and is sound. Cleared by measurement or by reading
the library, so none of it needs re-deriving:

- `bounding_box()` in build123d defaults to `optimal=True`
  (`topology/shape_core.py:1142`), so the brief's own risk 1 - a loose box
  failing a symmetric part - does not arise.
- `Shape.distance_to` takes `Shape | VectorLike` (`shape_core.py:1255`), so
  the vertex gate's point argument is supported and is not being swallowed by
  the outer `except Exception: return False`.
- `SkipClean` has exactly ONE user in the product (`inspector.py:187`), so its
  `__exit__` restoring `clean = True` unconditionally cannot un-nest an outer
  block. Two requests at once there is the known FastAPI-threadpool P2.
- `assert_wall_fits_every_lump`'s bound is a true necessary condition: a
  lump's inradius is at most half its smallest bounding-box extent, so
  `2t >= dmin` does imply an empty inward offset. It refuses nothing correct.
  It also does not reach the open-face or multi-lump crashes below - measured,
  not assumed.
- The `--library` line in a crash folder's repro is right in all eight folders
  the overnight run filed: the live designs get it, the `pump-impeller`
  fixture does not.

## Do not re-report

- **The four LAUNCH-PLAN section-10 rows this chat added**: the multi-edge
  fillet segfault on the sliver body; `shell` segfaulting on two more real
  bodies (oneplus_7_pro_case at 0.5-1.5 mm through an open face; the
  pump-impeller 3-lump CLOSED shell at every thickness from 0.8 to 2.9, where
  the same shell built at the previous `z` and no bounding box changed); the
  three-hour planetary-ring edit; and fillet/chamfer of ALL the edges of a
  traced keychain outline taking 156 to 630 s. All measured, all with a
  committed fixture or a seed.
- **A pre-kernel guard on sliver geometry was measured and REJECTED**:
  `probes/sliver_body_corpus.py` shows real bodies carry faces of 0.00028 mm2
  and edges of 0.000035 mm (my-part-9, planetary-assembly, planetary-ring,
  autonomiq-sat-panel) and fillet correctly, so refusing them blocks real work.
- Whether autonomiq-panel's 1195 s shell returns a SOUND body is still
  unmeasured: it needs 20+ minutes under `probes/memcap.py --timeout 1800`,
  and `sketch.shell` already measures its own result four ways. The next
  overnight run answers it by itself now that the geometry oracle runs first.
- `bugs/journeys-stdout.log` is tracked and grows every night; it is left
  uncommitted on purpose.
- The pre-existing red browser tests (section 10) are untouched; there is no
  frontend change and no `ui v` bump in either commit.

## Ground rules

Ruff zero; fast tier `1713 passed` at `2231095`. Probe first; anything that
can eat memory runs under `probes/memcap.py --gb 6` - note its `--timeout`
defaults to 600 s, which is not enough for a shell on a 3000-face body. Fix in
the same chat, then this file -> `Status: NOTHING PENDING` (next review takes
REVIEW-QUEUE section 9, Trace image).
