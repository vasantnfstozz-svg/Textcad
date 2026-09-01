# Version tree — development sheet

> **Status: P0–P5 shipped 2026-08-26 — the feature is complete**, except
> per-version thumbnails, deferred with a reason (see P5). Design agreed with
> the user 2026-08-26.
>
> **P6 revision, 2026-09-01 — explicit push.** The user tightened decision 1:
> *"whatever i am adding its going as new version, it should not be like
> that ... if i want then i can push those model with my changes into new
> version."* Tool commits, imports, strikes and AI edits **no longer mint
> versions on their own** — they mark the tab **dirty** (hash of `to_data()`
> vs the current version, cached per tab, recomputed only after a mutation)
> and accumulate as `pending` notes. Only an explicit **Save** mints (plus the
> open/reload baseline), with a label composed from the notes ("hole added; AI
> set bore.radius = 9; 2 tweaks") and the author attributed to the AI only if
> every pending change was the AI's. The UI: a ● on the doc tab and in the
> version panel summary, a "save as version" button in the panel, and closing
> a dirty tab asks **Save & close / Discard & close / Cancel** (in-app dialog,
> `askThree`). Discard = close without saving; the file and tree are untouched.
> Undo back to the version reads clean again — the prompt never cries wolf.
> A restored session compares against the history's current version, so dirty
> survives restarts. Tests: test_version_api.py (48), 2 new e2e.
>
> **P6 follow-ups (same day):** per-row ✎ rename + ✕ delete buttons
> (`History.delete` re-points children at the parent; refuses current/starred
> naming the way out; `id_floor` keeps single-delete ids monotonic). Then the
> finish-a-round choice: the dirty row offers **update vN** (`History.amend`
> — rewrite the current version in place, leaf-only so child diffs never
> lie) and **push vN+1** (`/api/save`, label from the next_id the listing now
> carries). The CURRENT row's ✕ is the **trim** gesture — `delete_after`
> removes every descendant in one confirmed click and RESETS `id_floor`, so
> trimming v16..v45 makes the next push v16, not v46 (the user's literal
> ask). A single delete still raises the floor; only the explicit
> tail-rewind rewinds the numbering.

## The problem, in the user's words

> "if i am creating a design using ai, its v1 … after that i might have tried
> different changes, continuously goes to v10 … every time when we are working
> in the changes, there is always a new tab will pop out with new modified
> design, after some time there will be many tabs, we do not know which is my
> intended design."

Two separate faults, often mistaken for one:

1. **Tab explosion.** [studio.py:1268](studio.py) `/api/open/{file}` is
   documented "Open from the library — in a NEW tab" and calls `_new_tab()`
   unconditionally, with **no check for a tab already holding that design**.
   `/api/sample/{name}` (:1281) and AI `create` (:1332) do the same. The design
   loop is: regenerate → `POST /api/open/<name>` → review in 3D. Ten
   iterations, ten identically-named tabs.
2. **No history.** `/api/save` overwrites `designs/<slug>.tcad.json`. v9 ceases
   to exist the moment v10 saves. The only history is `_snapshot()`'s undo
   stack — **in memory, per tab, capped at 25, destroyed on restart**.

Evidence the user already needs this and is hand-rolling it:
`autonomiq-sat-panel-v1.tcad.json`, `esp32-remote-live-t2.tcad.json`,
`esp32-remote-live-t3.tcad.json`.

## Decisions (locked 2026-08-26)

| # | Decision | Chosen |
|---|---|---|
| 1 | Version granularity | **Meaningful moments**, not every nudge. AI edit done / Save / tool committed / design opened. Bursts coalesce. Undo stays fine-grained. |
| 2 | Restore behaviour | **v3 becomes the live design** in the same tab, immediately editable. Editing it **branches**. `.tcad.json` is NOT overwritten until an explicit Save. |
| 3 | Backfill scope | **rocky-keychain → today, all designs** with git history. |

**The core invariant, from decision 2:** restoring v3 and editing creates a
version whose `parent` is v3. v4–v10 remain reachable. History is a *tree*,
never a list that truncates. Without this, going back to an old version
silently destroys the newer ones — the original complaint, re-created.

## Storage

A sidecar **directory** per design, not one big file. Appending a version must
not rewrite the whole history, and one corrupt snapshot must not destroy the
rest.

```
designs/
  esp32-remote.tcad.json         # CURRENT design — unchanged, as today
  esp32-remote.history/
    index.json                   # the tree: nodes, parents, labels, stars
    v1.json.gz                   # Document.to_data() snapshot
    v2.json.gz
    v1.png                       # optional thumbnail (P5)
```

`Document.to_data()` is already the right snapshot unit: `{name, spec,
features[]}` — complete design intent, pure JSON, no build state.

**Sizes measured, not guessed** (and the first estimate was too pessimistic):
`cam-cover-plaque` 198 KB → **10.4 KB gzipped (19.1×)**, `autonomiq-sat-panel`
196 → 11.6 KB (16.9×), `esp32-remote` 104 → 6.8 KB (15.3×), `rocky-balboa`
167 → 13.8 KB (12.2×); 15.6× across the set. So 25 versions of the biggest
design cost ~260 KB, not the ~5 MB first assumed — **a design's whole history
is cheaper than one raw copy of it.** Small designs compress poorly in ratio
terms (`flange-100` only 2.7×) but they are under 1 KB anyway.

### `index.json`

```json
{
  "schema": 1,
  "design_id": "d_8f3ac91e",
  "name": "esp32-remote",
  "current": "v10",
  "starred": "v9",
  "versions": [
    {"id": "v1", "parent": null, "created": "2026-08-25T09:12:04Z",
     "label": "first build", "source": "backfill:git", "commit": "8d6fb92",
     "features": 61, "hash": "sha1:…",
     "spec": {"volume": 128695.0, "size": [200, 90, 12]},
     "rebuildable": true, "thumb": "v1.png"}
  ]
}
```

- `parent` — the whole tree structure. `null` = root.
- `current` — where the design tab is sitting.
- `starred` — **one pinned "this is the one I want" per design.** This is what
  actually answers *"we do not know which is my intended design"*; recency
  alone never does.
- `hash` — content hash of the snapshot. **A version is minted only when the
  hash changes**, so no-op edits and repeated opens can never pad the tree.
- `spec` — stored so two versions can be compared without rebuilding either.

### Identity

Renaming a design must not fork its history, so `design_id` is generated once
and stored in **both** `index.json` and the `.tcad.json`. `to_data()` gains the
field; `from_data()` must treat it as optional — **every existing design file
lacks it** and must keep loading unchanged.

## Phases

Each phase is independently shippable and independently tested.

### P0 — tab reuse — **DONE**

`_new_tab(doc, source=...)` now records where a design came from
(`file:<slug>` / `sample:<name>`) and `_find_tab(source)` looks it up, keyed on
**origin rather than `doc.name`** — two designs can share a name, and renaming
must not orphan a tab. `/api/save` binds its tab to the file it just wrote, so
saving then re-opening lands back in the same tab.

Two behaviours that were NOT obvious up front and are worth keeping in mind for
P2:

- **Reuse must not mean stale.** The design loop exists to show a file that has
  *changed*, so `/api/open` reloads a tab whose design has moved on, pushing
  what the tab held onto its undo stack first — a refresh can never silently
  discard unsaved work. If the file matches what the tab already shows it only
  switches: `autonomiq-sat-panel` costs ~45 s to rebuild and re-opening an
  identical file must not pay that for nothing.
- **Samples have no file that can move on**, so an already-open sample is
  switched to as the user left it, edits included. File > New gets a clean one.

The response carries `tab_reused` / `reloaded`, and the chat message says which
actually happened — three "Opened flange-100" lines above a single flange-100
tab was the very confusion this set out to end.

Tests: `tests/test_tab_reuse.py` (11), plus `test_api.py`'s old
"opens in new tabs" test rewritten to the new intent. Verified live in the
browser: three gallery opens of one design → one tab; a different design still
gets its own.

### P1 — `history.py`, the storage core — **DONE**

Pure Python, no HTTP and no `Document` import. `History(path)` /
`History.for_design(dir, slug)` with: `init`, `append`, `versions`, `get`,
`snapshot`, `current`/`set_current`, `star`/`starred`, `relabel`, `rename`,
`repair`, `problems`, and tree walking — `children`, `roots`, `leaves`,
`ancestors`, `branch_points`, `tree_lines`.

Four invariants, each stated in the module docstring and each **verified by
mutation testing** (break it in the source, confirm the suite goes red):

| Invariant | Broken deliberately → |
|---|---|
| A version is recorded only when the content hash changes | 3 tests fail |
| Editing from an old version BRANCHES, never truncates | 3 tests fail |
| The snapshot is written before the index | 1 test fails |
| A broken index is never overwritten | 3 tests fail |

Details worth remembering:

- **Dedupe is against the PARENT only**, not the whole tree. A→B→A is real
  history — the design genuinely changed twice — so it records, while
  re-opening the same design ten times records nothing.
- **`parent` defaults to `current()`.** That single line is what makes
  restore-then-edit branch instead of truncate; there is no separate "branch"
  operation to forget to call.
- **`_save()` persists, then adopts.** Every writer builds a new index dict and
  hands it over; `self._data` only advances once the bytes are down, so a
  failed write cannot leave a live `History` disagreeing with its own disk.
- **Order matters for crash safety.** Snapshot first: a crash then leaves an
  orphaned `.json.gz` (harmless garbage) instead of an index entry promising a
  payload that never landed. The id of a never-indexed version is deliberately
  reused — ids are monotonic over real versions, not over failed attempts.
- **`repair()` is opt-in, never a silent fallback.** It rebuilds an index from
  the snapshots on disk, and says in its return value that it made the chain
  linear because the real parent links died with the index. Guessing is fine
  when asked for and unacceptable by default.
- **`rename()` moves the directory** and keeps `design_id`, so a renamed design
  does not fork its history. Renaming onto an existing history is refused
  rather than merged.

Tests: `tests/test_history.py`, **39**.

Still owed by P2, deliberately not done here: `design_id` is currently only in
`index.json`. The plan has it in the `.tcad.json` too, which means touching
`Document.to_data()`/`from_data()` — that changes every saved design file, so
it belongs with the server wiring, not with a storage layer that must not know
what a Document is. `rename()` covers the rename case until then.

### P2 — server wiring — **DONE**

`GET /api/versions`, `POST /api/versions/restore`, `POST /api/versions/star`,
`POST /api/versions/label`. Versions live under `_history_root()` — `designs/`
in production, overridable by `TEXTCAD_HISTORY_ROOT`.

**Where a version IS minted** (9 hook sites): design opened, design reloaded
because its file changed, save, `feature/add` (a tool commit), `feature/remove`,
`trace-png`, `import-stl`, an AI edit, an AI delete.

**Where it deliberately is NOT:** `/api/edit`, `/api/feature/params`,
`/api/spec`, `/api/feature/suppress`, `/api/feature/rename`, `/api/rollback`,
`/api/undo`. Those stay undo's business and then ride into the next recorded
version together — a save after five tweaks records ONE version holding all
five, which is the coalescing the user asked for. An AI edit *is* recorded even
though a hand-dragged slider is not: the user asked for it in words, so it is a
moment. That asymmetry is the decision, not an oversight.

Restore: loads the snapshot into the SAME tab, pushes the outgoing state onto
the undo stack (so restoring is undoable), sets `current` so the next edit
branches — and does **not** write `.tcad.json`. A version this build cannot
open (an op renamed since) fails with a real explanation and stays in the tree;
it is never dropped and never a 500.

`_record_version()` never raises into an endpoint. A design edit that succeeded
must not look like it failed because a sidecar file is unwritable, so the fault
comes back as `history_error` alongside the normal result.

**Test-pollution seam, worth knowing about:** `/api/open` now creates
`<slug>.history/` as a side effect, so without a guard any test that opened
`flange-100` would leave a directory inside tracked user work.
`tests/conftest.py` has an **autouse** fixture pointing `TEXTCAD_HISTORY_ROOT`
at a throwaway path for every test, and `test_version_api.py` ends with a guard
on the guard.

Tests: `tests/test_version_api.py`, **28**. Verified live end to end as well:
open → v1; a bare edit records nothing; save → v2; restore v1 puts the old
geometry back; edit+save from there → v3 with **parent v1**, v2 untouched;
star v2. Final tree from the live server:

```
   v1  opened flange-100
 ★   v2  saved
*    v3  saved
```

Still not done, and no longer needed the way the plan assumed: `design_id` is
in `index.json` only. There is **no design-rename endpoint in the app at all**
(`/api/feature/rename` renames a feature, not the design), so a design's slug
cannot currently change and the fork-on-rename problem has no way to occur.
`History.rename()` is built and unit-tested, ready for the day rename lands.

### P3 — UI — **DONE**

`static/js/versions.js` + a `#verPane` section at the BOTTOM of the left pane,
under the feature tree.

**Collapsed to one line by default**, and that line is the point: `v3 of 5 ★ v2`
answers "which version am I on" without opening anything, which is the literal
complaint. Expanded it takes at most 55% of the pane and scrolls itself, so the
feature tree keeps its space. A **Versions** button in Inspect → History opens
it, for discoverability.

Each row: star toggle, id, label, feature count. Current row is outlined and
underlined; the starred row shows a filled ★ (exactly one can). Children are
indented under their parent, so a branch is visible as two siblings at the same
depth. A version recorded as not verifying is struck through. Click a row to
restore; double-click its label to rename.

Restore has **no confirmation dialog, on purpose**: it does not overwrite
`.tcad.json`, the outgoing state goes on the undo stack, and the versions you
came from stay in the tree — nothing about it is destructive, so a prompt every
time would just be in the way. The chat reply says how to get back instead.

Refresh policy: on `doc-updated` only when the panel is open, or when the
server's reply carried `version` / `history_error` / `restored`. Otherwise the
collapsed summary would go stale while the panel stayed silent — and
`/api/versions` is kept off `/api/doc` precisely so it is not on the hot path.

**A P1 fix this phase forced:** `problems()` used to DECOMPRESS every snapshot
to prove it readable. The panel calls it on every document change, so that was
O(whole history) on a hot path — megabytes of gzip for a 100-version design.
It is now shallow by default (a `stat` catches a missing snapshot; a corrupt
one is caught the moment it is opened, where `snapshot()` already names it) with
`deep=True` kept for the tests that assert corruption is detected.

Tests: `tests/e2e/test_version_panel.py`, **7**. One of them started out
**vacuous** and was caught: it asserted feature names via `.prow .pname`, which
are PARAMETER rows (`radius`, `thickness`) — so it passed no matter what
restore did. It now reads `.node[data-fid]`, and asserts the "tiny" hole is
present BEFORE the click so the check after it cannot pass by finding nothing.

### P4 — git backfill, rocky → today — **DONE**

`backfill.py`, kept separate from `history.py` (which must not know what git
is) and from `studio.py` (which must not shell out). CLI:
`python backfill.py [--dry-run] [--only SLUG …] [--reset]`.

**Result of the real run: 108 versions across 41 designs, 794 KB** — including
rocky-keychain **24**, esp32-remote **15**, pump-housing **8**, sat-side-panel
**5**, autonomiq-panel **5**, pump-cover **5**, pump-impeller **4**. Commit
subjects became the labels, so the trees arrived readable rather than as
`v1..v24`; each version keeps its commit sha and the commit's own timestamp.

**Two git traps, both hit for real and both now regression-tested:**

1. `--reverse --follow` together return **ONE** commit for esp32-remote where
   `--follow` alone returns 16 — `--follow` is a hack in the revision walker
   and does not compose with `--reverse`. The first version of this module used
   both and would have silently imported 1 of 15. Ordering is done in Python.
2. `--follow` is not used **at all**, which is the worse of the two. For
   `autonomiq-sat-panel.tcad.json` git's rename heuristic walks back into
   `sat-side-panel.tcad.json` (5 commits) and on into `isogrid-panel.tcad.json`
   — *different designs*, each with their own file, history and tree. Following
   imported another design's commits under this one's name, and `git show
   <sha>:<path>` then failed because those commits do not contain the path.
   Plain path history gives 3 / 15 / 24 for sat-panel / esp32 / rocky, and
   those are the right answers. Cost: a genuinely renamed design loses its
   earlier life — an acceptable trade while the app has no rename.

Safety: **non-destructive by default.** A history holding versions recorded
from live editing is skipped with a reason, because git commits are *older* and
appending them would build a chain that lies about the order; `--reset` exists
for when git should be the only source. Idempotent on commit sha, so re-running
adds only new commits. Designs with no git history are reported, naming the
real limit (`designs/*.tcad.json` was only tracked from 2026-08-05).

Tests: `tests/test_backfill.py`, **21**, run against this repo's real history —
a mock would not have caught either trap. Both traps are mutation-verified.

**A UI bug the backfill exposed.** `tree_lines()` and the panel indented per
LINK, so rocky-keychain's linear chain of 24 became 24 nested levels — 253 px
of margin, labels off the edge of a 320 px pane. Both now indent by
`History.depths()`: a version's first child continues the trunk at the same
level and only a second child steps right. A straight line of edits is not 24
levels of anything. Max indent for rocky-keychain is now 0.

The pollution guard in `test_version_api.py` also had to be narrowed: it
asserted *no* `.history` existed under `designs/`, which was right for test
isolation and wrong the moment real histories legitimately lived there. It now
checks only for its own test slugs.

### P5 — diff and prune — **DONE** (thumbnails deferred)

**Diff between versions.** `diff_snapshots(base, target)` in `history.py`,
`GET /api/versions/diff?target=v5[&base=v3]` (base defaults to the parent), and
a `⇄` button per row in the panel that expands an inline explanation.

The whole difficulty is summarising rather than dumping: a sketch's `entities`
is a 1476-character list of points, so "from … to …" would bury the one number
that actually moved. Scalars print exactly (`block.thickness: 16 → 18`);
anything larger is described by shape. The first cut said
`10 items -> 10 items` — a number that had not moved while the content had — so
equal-length lists now report `10 items, 4 differ`, and that is pinned by a
regression test.

Rewiring is spelled out rather than flagged. Inserting features mid-chain
silently re-points whatever consumed the old node, and on the real esp32-remote
v14→v15 that is the interesting part:

```
+6 features, 3 changed          vs v14
+ logo_0_sketch  sketch … + logo_1  cut
tail_fold_scoop  inputs  tail_trench, … → logo_1, …
isl1_sketch.entities     10 items, 4 differ
```

Diffs are fetched **on demand**, never precomputed for the list: answering one
decompresses two snapshots, and the panel repaints whenever the document
changes — the same reason `problems()` is shallow. The `⇄` button stops
propagation so asking "what changed?" never restores the version, which has its
own E2E test.

**Prune.** `History.prune(keep=20, dry_run=True)` — **dry run by default**,
because it is the one operation here that destroys user work. Never removable,
whatever the limit says: the **starred** version (it is the user's answer to
"which is my intended design"), the **current** one, every **branch point**
(dropping one orphans a line of work) and every **leaf** (the tip of a line of
work is the work). Removing a node re-points its children at its parent, the
way dropping a commit from a chain does, so the tree stays connected. The
protection is mutation-verified. Not wired to the UI or run anywhere: at 794 KB
for 108 versions there is nothing to reclaim yet, and a one-click history
delete is a liability, not a feature.

**Thumbnails: DEFERRED, and the reason is not effort.** There is no server-side
renderer — the preview PNGs in `designs/` are drawn by each design's own `.py`
with PIL, not from geometry — so a thumbnail could only be captured from the
browser canvas at the moment a version is minted. That means **none of the 108
backfilled versions could ever have one**, and a gallery where 108 tiles are
blank and a handful are not reads as broken rather than as partial. Worth doing
only alongside a way to render an arbitrary snapshot headlessly; the labels
carry the recognition load well in the meantime.

Tests: 7 diff cases in `test_history.py`, 7 prune cases there, 5 diff-API cases
in `test_version_api.py`, 2 panel cases in `test_version_panel.py`.

## Test matrix

Written from the user's instruction: *"we always have different user case, at
those time we will get new issues or bugs, so try those test case."*

### Core invariants (P1)
| Case | Expected |
|---|---|
| Restore v3, edit, save | New version, `parent == v3`; **v4–v10 still reachable** |
| Branch twice from the same parent | Two children, both intact |
| Version ids across branches | Monotonic, never reused |
| Identical snapshot appended twice | Deduped by hash — no second version |
| Server restart | Full history intact (today's undo stack is not) |
| Crash mid-write | `index.json` never half-written (atomic rename) |
| Corrupt/truncated `v7.json.gz` | v7 marked unreadable; **v1–v6, v8+ still work**; message names the real fault |
| Missing `index.json`, snapshots present | Degrade honestly, offer rebuild-index; never crash |

> The corrupt-file case is not hypothetical. On 2026-08-26 the Examples dialog
> reported "No examples catalogued yet (designs/examples.json)" when the real
> fault was a dead server — it blamed a file that was fine. Every failure path
> here must name the actual fault.

### Behaviour (P2/P3)
| Case | Expected |
|---|---|
| Rename a design | History follows; does not fork (that's what `design_id` is for) |
| Same design open in two tabs | Defined winner on save; no silent clobber |
| Restore an old version | `.tcad.json` untouched until explicit Save |
| Version that no longer rebuilds (op renamed since v2) | "Recorded but can't rebuild" — record kept, never a crash |
| Rapid parameter drags | Coalesce to one version, not forty |
| Undo vs version-jump | Two mechanisms, must not corrupt each other |
| 100+ versions | UI stays usable (paging) |
| Design never saved | No history dir until first version |

### Backfill (P4)
| Case | Expected |
|---|---|
| Run twice | Idempotent — no duplicates |
| Design with 1 commit | Single v1, no error |
| Design with no git history | Skipped cleanly |
| Blob unparseable at some old commit | That commit skipped, rest still imported |
| Backfill onto a design that already has live versions | Merges without renumbering existing ids |

## Open, decide before P3

- ~~Where the tree lives.~~ **Decided: bottom of the left pane**, collapsed to
  one line. A dialog was rejected — "which version am I on" has to be visible
  without opening anything.
- Prune policy — none, or keep-last-N-per-branch with starred always kept.
- ~~Should `.history/` be git-tracked?~~ **Decided 2026-08-26: yes, track
  everything.** Same reasoning as the design library — losing v1..v9 to an
  untracked directory would defeat the point. `.gitignore` carries an explicit
  `!designs/*.history/**` so a future broader ignore cannot silently drop them.
