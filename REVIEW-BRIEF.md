# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **In a fresh chat on Opus (`/model claude-opus-5`), type exactly this:**
>
> ```
> /code-review high - read REVIEW-BRIEF.md first: it names the commit range, the base, and what not to re-report
> ```
>
> That line never changes. Everything specific to this review is below.

---

## Review this

| | |
|---|---|
| **Range** | `357c14e..e5ffb8d` - ONE code commit, `e5ffb8d` (Fillet / Chamfer: pick FACES and TREE ROWS). Commits above it on `master` are docs only (the review queue) and are not part of this review |
| **Already reviewed** | everything up to `bdd8ebf` (the STEP export, Fillet picking parts 1 and 2, the edge-group chips and their six review fixes) |
| **Effort** | high - a shipped tool change that touches the picker every tool goes through, plus a per-body memo that WAS a P0 for an hour during the work (a moved copy resolved faces by its parent's centres) |
| **Branch** | `master` (no pull request - do not try to comment on GitHub) |
| **Frontend** | `ui v171`, `css v40` |

## What the commit does

The user, testing the six edge-group chips (2026-09-08): "instead of dividing
all edges into vertical and horizontal and inside and outside, I can select a
body, like from the feature tree - if I am selecting an extrude and pressing
Fillet, those selected face or body edges should be selected ... another click
on the selected body should deselect." That is Fusion's Fillet (its filter
reads Edges / Faces / Features), so the chips are GONE and three selection
kinds remain:

- **an EDGE click** (unchanged, reviewed before);
- **a FACE click** (`face_toggle`): every edge two faces meet at on that
  face, as one set - missing ones come in, a fully picked set goes out.
  `toolplan._face_of` (l.659) resolves the face by nearest centre and REFUSES
  a centre outside the resolved face's bounding box, because the picker hands
  the tool clicks on its own PREVIEW body, whose new fillet band would
  otherwise name the wall beside it;
- **a TREE ROW** (`feature_toggle`): the edges of the faces that feature MADE,
  as they are now - `provenance.feature_faces` (l.369): a face of the body is
  the feature's when it is a trimmed survivor of a face the feature's output
  has and its input did not; `document.delta_features` says which features.
  A cut row = its 12 pocket edges; the base plate = its outer 12 plus the
  pocket's opening; a fillet row = its bands. Seams (one face) are never
  offered. A row picked BEFORE the tool also names the body.

Select-then-command for all three (`tool.js firstClick`); the tree stays a
selection surface all session (`waitForRow(onRow)`; the tree emits `null`
when the lit row is clicked again = the same row, toggled); the face under the
pointer glows while the picker is armed (`viewport.hoverFaceAt`); `speakClick`
says what every click did.

**The cost that was hiding.** The first row click on a 48-edge ring took 55 s:
`resolve_face` measured all 254 face centres for both faces of every edge, and
`tangent_chain` rebuilt its vertex table per edge. Now `blocks._face_rows`
(centre + normal per face) and `blocks._edge_topo` (edge/face adjacency + end
tangents) are enumerated once per built Part through `blocks._cached` (l.314):
a `WeakKeyDictionary` keyed on the Python shape object, every entry checked
against the TopoDS shape with `IsEqual`, so a copy, a re-used id and an
in-place move all miss. (Stored as attributes on the Part they rode along in
build123d's `__deepcopy__`, which is how a moved plate resolved a face by its
parent's centres. `test_a_moved_copy_does_not_inherit_its_parents_faces`
locks it in; `probes/shape_cache_probe.py` measured it.)

Files: `blocks.py` (+250/-), `toolplan.py` (129), `static/js/tool.js` (111),
`static/js/viewport.js` (44), `provenance.py` (+69), `static/js/fillet.js`
(chips removed), `static/index.html`, `static/css/studio.css`, `studio.py`
(3 lines). Tests: `tests/test_fillet_tool.py` (53, 8 new), browser
`tests/e2e/test_fillet_tool.py` (11, 2 rewritten). Probes:
`probes/feature_edges_probe.py` (sections 1-4, timings), `probes/shape_cache_probe.py`.

## Where the risk is (the author's own list - check it, do not trust it)

1. **`provenance.feature_faces` when the feature's output is an ANCESTOR of
   the body.** The interior-point test decides whether a face coplanar with,
   and inside the bounding box of, an older feature's face still belongs to
   that feature - the case is a boss filling a pocket down to its floor. Wrong
   attribution = a row click lights the wrong edges = the wrong edges get
   filleted (P0 class).
2. **`toolplan._face_of`'s 0.05 mm bbox tolerance on CURVED faces.** A full
   cylinder's centroid is on its axis, a band's centroid is on its surface;
   both lie inside the bounding box, so the guard that keeps a preview band
   from naming the wall beside it may not fire on a curved face.
3. **`blocks._cached`.** Anything passed to `resolve_face`, `tangent_chain` or
   `_edge_faces` that is not a build123d shape (all callers found pass a
   `Part` or `Solid`); a shape that cannot be a weak key recomputes every call
   (cost only). Does the `IsEqual` check really cover a `moved()` copy AND an
   in-place move on the same Python object?
4. **`tangent_chain(part, edge)` with an edge that is not from `part`** now
   returns a chain of one (it used to find by position); its only caller is
   `toolplan._expand` with the part's own edges - confirm.
5. **`tool.js onRow`** for the tool's own preview row (a sentence, no request)
   and for a sketch row (the server's sentence). `waitForRow` is the ONE slot
   Pattern also uses: what happens to a Pattern session when a row is clicked
   while Fillet's wait is armed, or the reverse?
6. **The toggle semantics.** A face whose edge set is PARTLY picked toggles the
   rest IN; a fully picked set goes OUT. Is the stored set always equal to the
   gold edges shown, after a face click, a row click and an edge click on the
   same body in any order? A stored set that diverges from the display is a
   finding; the semantics themselves are the spec (`specs/fillet-chamfer.md`).
7. **`hoverFaceAt` / `unhoverFace`.** The glow left on after Cancel, Esc, a
   tool switch or a rebuild; the glow material disposed per hover.

## Ground rules

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. You may run
  `C:\Python314\python.exe -m pytest tests/test_fillet_tool.py -q`.
- **A finding is a concrete input on which the code does the wrong thing**,
  with the exact click or data that triggers it. Order: P0 wrong geometry or
  data loss, P1 blocks the action, P2 daily annoyance, P3 polish.
- **The frontend must not re-derive backend facts** (rule R1): which edges a
  face or a feature owns comes from the plan, never from JS.
- **Two banned failures:** a kernel exception reaching the user (OCP errors
  derive from `Exception`), and a "successful" invalid solid.
- **Comments naming a date record a past bug**; do not report them as noise.
- **No fixes, no style remarks**; both linters run at zero.

## Output format

```
### F1 - P<0-3> - <one line>
- File: <path>:<line>
- Trigger: <the exact click or input>
- Expected / Actual: <one line each>
- Confidence: high | medium | low - <why>
- Evidence: <1-3 quoted lines>
```
then `### Checked and found OK` (up to 8) and `### Could not judge without
running the app` (up to 5). At most 15 findings; say so if fewer than 5 are
high or medium confidence.

## Already known - do NOT report

- A tree row click starts the tree's own STL highlight, and a face click
  landing during it runs its plan concurrently on the same kernel - lost once
  in four journey runs. Known, LAUNCH-PLAN section 10 P2 (the threadpool).
- Rule R10 (delete more than you add) was not met by this commit: the chips'
  154 lines left, the memo and the hover face came in. Recorded in the plan.
- The six review findings of the chips (`bdd8ebf`) concerned code that is now
  deleted (`edge_side`, `edge_groups`, `_group_words`); do not look for them.
- The sketcher's parked items (the `enterMode` race, the 25-degree face snap,
  the `loadMesh` calls) and the pre-existing red browser tests
  (`tests/e2e/test_tree_delete.py`, five).
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
