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
| **Range** | `bea3144..c2390ac` - TWO code commits, from two chats working the same checkout: `e2c93fe` (Extrude: a FACE sketch follows the drag - Join out / Cut in) and `c2390ac` (the fix pass for the six findings of the e5ffb8d review) |
| **Already reviewed** | everything up to `e5ffb8d` (Fillet faces + tree rows). Its six findings are FIXED in `c2390ac` - review the fixes, not the findings |
| **Effort** | high - `e2c93fe` changes what a drag DOES (which body a boss lands in) and how a session deletes, for every tool built on `tool.js`; `c2390ac` changes a provenance RULE, a pick guard and the per-body memo's lifetime, all on paths every face and edge click uses |
| **Branch** | `master` (no pull request - do not try to comment on GitHub) |
| **Frontend** | `ui v174`, `css v40` |

---

## Commit 1 - `e2c93fe`: a face sketch follows the drag

The user exported a design and the other program said "3 solid bodies" and
refused to edit it. The STEP was honest (753c24c exports every body): two
bosses had been drawn on pocket floors and pulled up with Extrude's Operation
box left at **New body** - `tool.js open()` set `'new'` for EVERY sketch
profile, a face sketch included. Fusion's default for a profile that lies on a
body: pulled away it JOINS, pushed in it CUTS; New body is for a free sketch.

- **`static/js/extrude.js beforeApply`** (l.188): when the profile is a face
  sketch (`plan.into_sign` is set), the session is not an edit, the user has
  not touched the Operation box (`st.opUser`), Through all is off and the
  direction is one-sided: the effective sign (`Math.sign(dist)` times Flip)
  equal to `into_sign` selects `cut`, otherwise `join`; `sync(st)` follows so
  the Through row appears. Runs on EVERY apply while untouched, so dragging
  through the face swaps Join and Cut (Fusion does the same) and a plan that
  lands after the first apply corrects the first choice.
- **`static/js/tool.js`**: `session()` gains `opUser`; the Operation box's
  `onchange` sets it. `applyOp` and `unbuild` remove the session's combiner
  (and, on Cancel, the feature) with **`mode: 'strict'`**. The default
  `auto` mode REPAIRS the tree: `Document._orphan_sweep` takes a cut's tool
  prism and that prism's SKETCH with it, so switching Cut to Join, or Cancel
  in a Cut session, deleted the user's sketch and the extrude. Pre-existing;
  found by the new journey's phase 3.
- Tests: `tests/e2e/test_extrude_face_sketch_joins.py` (boss joins, pocket
  cuts, hand-picked New body kept + sketch survives the switch; Cancel of a
  Cut session keeps the sketch). `test_user_workflow.py
  test_extrude_never_auto_selects_the_sketch` now expects the join (one body).

## Commit 2 - `c2390ac`: the e5ffb8d fix pass (six findings)

Each geometry fix was measured first and its probe is in the commit
(`probes/feature_faces_newest_probe.py`, `probes/face_of_revolve_probe.py`,
`probes/shape_cache_leak_probe.py`); every number below was printed by the
kernel, and each probe still runs against the shipped code.

- **A `provenance.feature_faces` NEWEST WINS** (was P0/P1). A face a later
  feature made, coplanar with and inside the bbox of an earlier feature's
  face, passed the host test for BOTH rows: a 6x6 boss fused flush into a
  pocket made the base plate's row light 20 edges instead of 16, and a radius
  rounded the boss's rim. New `_later_spine(doc, fid, body_id)`: a face that a
  later body on this body's SPINE did not have was remade after `fid`, so it
  belongs to whatever remade it. The spine scope is load-bearing - over the
  whole ancestry the same rule wiped every tool-body row to zero edges.
- **A2 `attribute_face`, same defect, which the review had cleared.** "Find in
  Timeline" on that boss's own top named the BASE PLATE with high confidence.
  Its walk now starts after the last spine body that did not host the face
  (measured: origin `b` -> `sm`, applied_by `b` -> the fuse). The "earliest"
  invariant in `tests/test_face_provenance.py` states the sharper rule now.
- **B `toolplan._face_of` on a body of REVOLUTION** (was P1). A cylinder
  wall's bounding box is the whole cube around the body, so a torus band's
  centre was "inside" it, `resolve_face` named the wall, and the plan silently
  added the disc's other rim 20 mm away. The guard is the two questions a bbox
  cannot answer: the centre lies ON the resolved face's surface (new
  `provenance.surface_gap`, gap <= 0.02 mm) and the face points the same way
  there (align >= 0.99). Both halves are needed: distance alone is 0.01 mm at
  r=0.05 while the normal reads 0.707 at every radius. 0 wrong verdicts over
  20 cases, and one `bounding_box()` call gone that cost 91 ms on a torus.
- **C `blocks._SHAPE_CACHES` never released anything** (was P2). The memo
  holds each body's own Faces and Edges and every one points back at the body
  (`Face.topo_parent`), so the WeakKeyDictionary's value kept its own key
  alive: 12 throwaway bodies, 12 live entries, 1.3 MB of python wrappers each
  at 200 faces. Now a bounded id-keyed `OrderedDict`, oldest out, 8 bodies,
  the shape held strongly (which is what makes `id()` safe). Freshness takes
  TWO tests: an in-place `part.move()` mutates the same TopoDS shape, so
  `IsEqual` compares it with itself and says True - the stored `hash(wrapped)`
  is what notices. Warm hits got faster (`id()` 0.25 us vs `hash()` 5.73 us).
- **D `toolplan._toggle_set`'s added count** (was P3). It was the set's own
  missing edges, so a wall click on a rounded box said "added 4 edges - that
  face's edges - 18 picked now". It is the edges that JOIN, chains included.
- **E `viewport.js` hover** (was P3, twice). `unhoverFace` leaked one
  `MeshBasicMaterial` per hovered face; and the patch was keyed on body/face
  id alone, so a radius drag - same ids, new triangles - hit the early return
  and the glow overhung into the new round. The key carries the mesh `data`
  now, and `disposeModel` drops the hover with the mesh it was built from.
- Proof: 12 new fast tests (10 in `test_fillet_tool.py`, 2 in
  `test_face_provenance.py`); fast tier 1188 passed; the 11 Fillet browser
  journeys pass; Ruff and ESLint at zero.

## Where the risk is (the authors' own lists - check them, do not trust them)

### In `e2c93fe`

1. **`mode: 'strict'` refuses when anything depends on the node.** In a fresh
   session the combiner is the tail, so nothing does - but is there ANY path
   where `applyOp` or `unbuild` runs with a feature downstream of the
   session's own combiner or feature (a plan landing late, a document change
   from the chat while the panel is open, a Pattern/Mirror session whose
   `featureId` is not the tail)? A refusal there returns HTTP 400 with
   `error`; `post()` does not throw on it, so the removal would silently not
   happen and the session state (`st.opId = null`) would lie.
2. **`into_sign` and Flip.** `intoSign` is the plan's; the box value runs
   along the arrow, which `setAxis` turns around when Flip is ticked. The
   OLDER cut-flip block right below (l.207) ignores Flip. Are the two
   consistent for a face sketch on a BOTTOM face (`into_sign = +1`) with Flip
   ticked - does the auto rule pick Cut for a distance that really goes in?
3. **The `opUser` reset.** Set once per session; `changeProfile()` (another
   profile chosen in the panel) keeps it. Should a new profile re-arm the
   default? `unlock()` does not clear it either (it runs before `session()`
   is created, so a new session starts false - confirm).
4. **Revolve, Loft, Sweep on `tool.js`.** They inherit the `strict` removal;
   Revolve's face sketch path has no such default rule (out of scope), but
   does any of them create its combiner NOT at the tail?
5. **`sync(st)` inside `beforeApply`.** extrude.js's `sync` clears
   `st.cutFlipped` when leaving Cut and unticks Through when not Cut; called
   mid-apply, before `params(st)` is read. Any order dependency with the
   cut-flip block that follows?
6. **A join that fails.** A boss pulled off a face whose profile touches the
   face boundary makes a fuse the kernel may refuse (zero-thickness wall).
   The extrude then builds and the FUSE row is red; `settle()` only looks at
   the extrude's health. What does the user see, and does OK say "created"?

### In `c2390ac`

7. **The dip test is not the literal rule it replaces.** "Introduced at L"
   is `_hosts(after_L)` and not `_hosts(before_L)` with `delta_features`;
   `_later_spine` instead walks the spine and asks only whether each later
   body HOSTS the face, on the argument that a spine body's `before` is
   always the previous spine element or None. That was verified by reading
   `document.delta_features` and measured equal on 11 documents covering
   plate, move, cut, fuse, fillet and folded pulled tools - but NOT on a
   spine containing `polar_pattern`, `linear_pattern`, mirror-with-seed,
   `shell`, `hole`, `revolve_face`, `loft` or `sweep`. Is there an op whose
   `delta_features` returns a `before` that is not the previous spine body?
   That is where the two forms would diverge.
8. **A row can now answer with ZERO faces** where it answered before, which
   toolplan turns into "'X' has no edges left on Y". Nothing in the repro or
   in esp32-remote does (every count there is unchanged), but a design where a
   later spine feature remakes ALL of an earlier row's faces would. Is that
   reachable, and is the sentence still true when it happens?
9. **`attribute_face`'s `first` scan costs one `_hosts` per spine body on
   every click** and runs before the walk that already re-tests them. Warm
   cost on esp32-remote's worst row was +47 ms inside a 1612 ms plan, but that
   was measured on `feature_faces`, not on the click path through
   `/api/face-feature`. Is there a body where the scan is the cost centre?
10. **The `_face_of` guard when the payload has NO normal.** Then only the
    gap test runs, and that is the half with a small-radius floor. `studio.py`
    assigns a face row's `center` before its `normal` inside one `try`, so a
    face whose `normal_at` raised has one and not the other. Reachable?
11. **`_face_of` refuses on a kernel exception** (`surface_gap` returns
    `inf`). Safe direction, but it is a behaviour change for degenerate
    imported faces - a mesh-import body's face that OCCT will not analyse can
    no longer be picked by its face at all. Is the sentence right for that?
12. **The memo's bound is 8 bodies, held STRONGLY.** One plan touches one
    shape, so a request never evicts its own body - but a session alternating
    between more than 8 bodies (several tabs, or a face-sketch chain that
    makes a design multi-body) pays a cold rebuild each time, 5.8 s on
    esp32-remote. And `_touch`/`popitem` are read-modify-write on a module
    global: FastAPI serves sync endpoints from a threadpool, so two requests
    can be inside `_cached` at once. The `KeyError` guards cover the eviction
    race; is there a worse interleaving (two threads building the same slot,
    one overwriting a fresher value)?
13. **The hover key now compares `entry.data` by identity.** Does any path
    replace a body's `data` object without a new mesh (so the patch is rebuilt
    for nothing), or mutate it in place (so a stale patch survives)?

## Ground rules

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. Python DID change
  in `c2390ac`: `C:\Python314\python.exe -m pytest tests/test_fillet_tool.py
  tests/test_face_provenance.py -q` is the fast proof (82 tests), and
  `tests/test_delete_repair.py` documents the sweep semantics `strict` avoids.
- **A finding is a concrete input on which the code does the wrong thing**,
  with the exact click or data that triggers it. Order: P0 wrong geometry or
  data loss, P1 blocks the action, P2 daily annoyance, P3 polish.
- **The frontend must not re-derive backend facts** (rule R1): `into_sign`
  and `target_body` come from the plan, never from JS.
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

- **`blocks.resolve_face` picks by nearest centre, so two coplanar faces that
  SHARE a centre resolve to the wrong twin.** A boss centred on the face it
  stands on (symmetric parts - most of this repo's designs) makes a row click
  die with "the picked edge at (-20, 0, 10) is no longer on the body", and
  rows whose face sets are correct fail the same way. Measured in
  `probes/feature_faces_newest_probe.py` SS1b/c, deliberately NOT fixed in
  `c2390ac` (different root cause, needs its own probe). Queued, P1.
- **Pattern's `_axis_face` guards with the bounding box that B replaced** and
  cites `_face_of` as its precedent, so an axis click on a cylindrical or
  conical result body has the same hole; Mirror's `_plane_face` is in the same
  family (it tests the PLANE, which is the stronger form). Queued.
- Face MODE (a picked face, `extrude_face`) still opens on Join regardless of
  direction (`tool.js open()`, l.341); pulling a face inward with Join is a
  no-op fuse. Known, not this commit's.
- Edit mode never rewires a combiner ("changing the operation of an existing
  extrude comes later"). Known.
- `feature_faces` answers nothing for a row whose whole body was MOVED after
  it (plate -> pocket -> move: only the move's row answers). Pre-existing,
  untouched by A.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
