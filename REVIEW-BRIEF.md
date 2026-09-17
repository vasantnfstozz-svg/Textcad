# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING — and for the first time, the queue is empty too.**
> On the night of 2026-09-16/17 the last five sections of `REVIEW-QUEUE.md`
> were reviewed and closed: **section 9 (four rounds), 10 (two), 11 (three),
> 12 (seven), 13 (three)**. Every status-board row now reads CLOSED. 57
> findings fixed, 12 of them P0, about 155 new tests, fast tier 1824 → 1992.
>
> **So the next `code review` has no queued work to pick up.** What it should
> do instead, in order of what would pay most:
>
> 1. **The two P1s in LAUNCH-PLAN section 10 that this pass could not reach**,
>    both in the trace pipeline and both deferred only because another
>    reviewer held the file at the time: the fit path measures its aspect at
>    the default 50 mm and then traces at the fitted height (`studio.py`, a
>    three-line fix), and art traced on a DOWN-facing face reads mirrored
>    (`sketch.py` — this one is a product decision as much as a patch, because
>    flipping `_face_frame` would mirror every existing face sketch in the
>    library, so put it to the user before touching it).
> 2. **A re-read of the highest-churn code**, if the user wants one: `studio.py`
>    took seven rounds and now carries a per-request tab mechanism (a context
>    var armed by a middleware) plus a page-wide `fetch` wrapper in
>    `static/js/api.js`. Round seven found nothing across 140 endpoint asks and
>    26 URL shapes, so this is optional, not owed.
> 3. Otherwise the remaining section-10 rows, ranked: the shell/fillet stalls
>    (a 15-minute Shell on a pocketed hexagon is the one the user actually
>    feels), then the guards that sit close to the line.
>
> **What must NOT be re-reported** — measured and settled during this pass:
> - Two browser windows now hold INDEPENDENT tabs. Deliberate, and the direct
>   consequence of addressing a request to a tab.
> - `doc = e["doc"]` can still go stale if `/api/open` reloads that same tab
>   mid-request. Carried on purpose (a lost update between the user's own two
>   actions, no cross-design loss); it needs a per-tab lock.
> - The trace ground rule's 5% threshold and its light-shell half. Both are
>   knife edges, both were measured across four independent corpora (74
>   pictures) and a 458-picture generator. **Do not "simplify" either without
>   re-scoring every rule on every corpus** — `probes/imgtrace_r4_corpus.py`
>   runs all four. Three separate rounds got this wrong by grading their own
>   corpus.
> - Every other row already carried in LAUNCH-PLAN section 10.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range named here; NOTHING PENDING means go to the queue. With the
> queue now empty, this file's numbered list above is the work.
