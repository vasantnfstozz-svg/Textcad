# Version tree — development sheet

> **Status: PLANNED, nothing built yet.** Design agreed with the user
> 2026-08-26. Phases P0–P5 below; each ships and is tested on its own.

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

**Sizes measured, not guessed:** the largest design is `cam-cover-plaque` at
202 KB, `autonomiq-sat-panel` 201 KB, `esp32-remote` 107 KB. 25 raw snapshots
of the biggest ≈ 5 MB. Feature-tree JSON gzips roughly 10×, so **gzip from day
one**, giving ~500 KB per design's full history.

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

### P0 — tab reuse (quick win, ~20 lines)

`/api/open/{file}` switches to the existing tab if that design is already open
instead of cloning it; same for `/api/sample`. Fixes most of the day-to-day
pain on its own, and needs none of the version machinery.

### P1 — `history.py`, the storage core — **NO UI**

Pure Python: `init`, `append`, `list`, `get`, `restore_data`, `star`,
`set_current`, plus tree walking (children, ancestors, branch points). Atomic
writes (temp + rename) so a crash mid-write cannot corrupt `index.json`.

**This phase is where robustness is won or lost.** Everything later is
plumbing. It gets over-tested before any UI exists.

### P2 — server wiring

Auto-version policy at the agreed moments; `GET /api/versions`,
`POST /api/versions/{id}/restore`, `POST /api/versions/{id}/star`,
`POST /api/versions/label`. Restore loads into the active tab and sets
`current`; it does **not** write `.tcad.json`.

### P3 — UI

Version tree panel: parent/child indentation, current and starred markers,
click to restore, inline rename. E2E coverage.

### P4 — git backfill, rocky → today

`git log --reverse -- designs/<slug>.tcad.json`, one version per commit,
`git show <sha>:<path>` for each blob, identical blobs deduped, commit subject
becomes the label, `source: "backfill:git"`, `commit: <sha>`. Linear parent
chain. **Idempotent** — re-running skips shas already recorded. Dry-run first.

**Material available** (measured): rocky-keychain **24** commits,
esp32-remote **15**, pump-housing **8**, autonomiq-panel **5**,
autonomiq-sat-panel **3**, cam-cover-upper **2**, wing-rib **1**; 77 design
commits since rocky overall. The commit subjects are descriptive
("esp32-remote v9: fix two machinability defects…") so they make genuinely
good version labels.

**Limit:** `designs/*.tcad.json` was only un-ignored on 2026-08-05, so nothing
older has blob history. rocky (2026-08-18) is safely inside that window.

### P5 — polish

Structural diff between versions ("v9→v10: +6 features (logo)",
"`keypad_recess.depth` 2.0→3.0"), per-version thumbnails reusing the existing
preview pipeline, prune policy.

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

- Where the tree lives: right-hand panel beside the feature tree, or its own
  dialog. (Feature tree already owns that space.)
- Prune policy — none, or keep-last-N-per-branch with starred always kept.
- Should `.history/` be git-tracked? It is user work, which argues yes; it also
  grows with every edit, which argues for gzip + prune first.
