# Mirror — tool spec (P4, LAUNCH-PLAN.md §8 step 1)

> **Status: DONE 2026-09-07 — tool 023ca5d, five review rounds (9644b6d,
> c4d5961, 85821be, 072aa95, 21429d8) + the deferred findings in the commit
> after the stamp, ui v164; user's checklist passed 2026-09-07.** Written
> 2026-09-06 with the kernel probe (`probes/mirror_probe.py`, §1–§10). The
> sixth tool on the framework
> (`tool.js`): one ribbon button, **Mirror** (Fusion's name), on the op that
> already exists — `mirror` — grown the way Pattern grew `polar_pattern`: it
> now mirrors a FEATURE (a hole, a boss, a fillet — its delta reflected across
> a plane and applied again) or a BODY (the body fused with its reflection),
> and the legacy call (`plane: "YZ"`, no seed — the reflected COPY alone) still
> builds every existing design. Mirror is a pattern with one copy and a
> reflection instead of a rotation, so it lives in `pattern.py` on the same
> delta machinery, the same seed resolver (`document.delta_features`) and the
> same seed reference rules (rename / delete / strike-out walk it).
>
> Decisions made here without the user (say so if any is wrong):
> 1. **A mirror of a body is Fusion's *Join*** — the body fused with its
>    reflection, one feature that eats its body (like a pattern). Fusion's
>    *New Body* is left out: in this tree a modifier consumes its input, so a
>    "new body" mirror would make the original disappear from view (that IS
>    what the legacy copy-only `mirror` does, and why the AI always fused it).
>    The copy-only behaviour stays for saved designs (`join` absent / false).
> 2. **Mirror planes are a flat face, one of the three origin planes, or the
>    body's own mid-plane across X / Y / Z.** TextCAD has no construction
>    planes yet, and a mid-plane is the mirror plane a machinist wants most
>    (Fusion makes you build a Midplane first). The origin planes appear as the
>    familiar glass quads (the sketch tool's) while the panel is open.
> 3. **No drag, no ghost.** Mirror has nothing to drag: the plane is chosen by
>    a click (or from the panel's list) and the real reflection appears after
>    ONE verified rebuild, like Pattern's copies. A gold translucent quad
>    marks the chosen plane.
> 4. Fusion's *Compute* option (Optimized / Identical / Adjust) is left out —
>    there is one way to compute here.
> 5. An image that lands ON the seed (the plane runs through it) or OFF the
>    body is refused with a sentence, never a silent no-op (probe §3, §4).
> 6. **A body face wins a click over an origin quad behind it** (P4 review,
>    closed by decision 2026-09-07). The quads are glass THROUGH the model and
>    sized past its silhouette; "nearest hit wins" once made faces unpickable
>    from whole view angles. Click a quad where it shows outside the part.

## What you click, what you see

Click a hole (its wall) or its row in the tree, press **Mirror**: the panel
opens — Seed **hole1 on box1**, Plane **— click a flat face or an origin plane
—** — and the three origin planes appear as glass quads around the part.
Nothing has been built. Click the red **YZ** quad: a gold quad marks the plane
and a second hole appears on the other side of it after one verified rebuild.
Click the green **XZ** quad instead: the image moves across that plane. Open
the Plane box and choose **the body's mid-plane across X**: the image follows.
OK: one `mirror1` row in the tree after the body, no cut chip. Click the box's
plain top face and press Mirror: the seed is the **body**; click the box's +x
face and the body doubles across that face into one solid. Double-click a
mirror row and the gold quad comes back on the stored plane.

## Inputs (rules 1, 2)

* **A feature, or a body — the seed.** Exactly Pattern's: the tree row
  selected when the tool is pressed (the `feature` kind), or the face picked
  in the viewport, whose maker the server looks up (provenance — a hole's
  wall is the hole, a boss's top is its extrude + folded fuse, the plate's own
  top is the body). With nothing picked the tool waits for a click or a tree
  row. A sketch is refused with a sentence.
* **What "the feature" means is the server's rule** — `document.delta_features`,
  the ONE resolver Pattern already uses. The delta (before − after = what the
  feature removed, after − before = what it added) is reflected across the
  plane and applied to the body's CURRENT state: the removed part is cut
  again, the added part fused again (probe §2, §5). A body seed is the body
  fused with its reflection (§6).
* **The mirror goes on the body's current state**: the feature's input is the
  seed body's tip, the row is appended there; `seed: "hole1"` is a param,
  `seed: null` is a body mirror. The op eats its body (no combiner row).
* **`seed` is a REFERENCE** (`document.REF_PARAMS`, shared with the patterns):
  rename walks it, delete and strike-out take the mirrors of a seed along.
* **`own_id`** on a replan (the feature this session built) — Pattern's rule,
  inherited. *Found writing this spec:* `own_id` was never in the server's
  request model, so over HTTP it was dropped and the fix of the Pattern review
  did not reach the browser; the model gains the field with this tool.

## The plane — ONE stored form each (the Hole review's lesson)

| Stored as | Meaning | Resolved |
|---|---|---|
| `"XY"` / `"XZ"` / `"YZ"` | an origin plane (the legacy form the AI writes) | through the origin |
| `{face_center, face_normal}` / `{face: "top"}` | a flat face's plane — through the centre of its OUTER wire (a hole cannot move it) | by geometry at every rebuild, on the body the op receives |
| `{mid: "X"}` (`"Y"`, `"Z"`) | the body's mid-plane across that world axis | the input body's bounding-box centre at every rebuild — it rides a resize |
| `{origin, normal}` | an explicit plane (the AI's, or a later construction plane) | as given |

A plane is an origin and a normal, nothing more: the same plane with the normal
flipped is the same mirror (probe §1). The picked face's plane is stored in the
face form (`pattern.stored_face`), read off the body the op will receive.

## The handles and the panel (rules 3, 4, 5)

* **The plane is picked**, not dragged. While the panel is open a click on a
  flat face of the body or on one of the three origin quads sets the plane
  (the framework's session pick, `repick`, with a new `planes` option that
  shows the quads; `onRepick` says the click means the PLANE). A curved face
  is refused in the hint (a sketch's plane-pick rule).
* **The gold quad**: a translucent square in the plan's `frame` (origin = the
  body's centre projected onto the plane, so it sits on the part; size
  `half` = ¾ of the body's largest extent), the same gold as the axis line.
  Nothing about where or which way is decided in the browser (R1).
* **Panel** `mrDialog`, ids `mr…`: Seed (locked, "hole1 on box1" / "the body
  box1") · Plane (a select of the plan's `alternatives`: the three origin
  planes, the body's three mid-planes, the picked face when one was clicked,
  "the stored plane" on edit if none matches — the current plane is ALWAYS one
  of them, Rectangular's rule) · Cancel / OK. **Honest zero:** the tool opens
  with no plane and builds nothing; the first plane (a click, or a choice in
  the box) builds the mirror; OK without a plane says so.
* **Body seed = Join.** The reflection is fused with the body; when they do
  not touch the framework's pieces warning fires with the remedy "the mirror
  image does not touch the body — pick a plane on the body (a face or its
  mid-plane) for one part". A body mirrored across its own symmetry plane is
  itself and is NOT refused (probe §7 — a saved design may never stop
  rebuilding; Pattern's lesson).
* **Edit**: tree ✎ or double-click reopens with the quad on the stored plane;
  Cancel restores verbatim — inherited. A LEGACY mirror (copy only) edited
  here keeps `join` as it was — the plan carries the stored `join`, but ONLY
  while the stored params and the plan agree about whether there is a seed.
  When they disagree the stored seed has stopped resolving to a feature (it
  names a whole body, or a PLACEMENT row that now folds to one) and its
  `join: false` no longer means "a copy", it means nothing: the plan comes back
  as a body **Join**. Carrying the stored value there replaced the body with a
  detached reflection, with no Join row to undo from — measured on both
  collapse paths (`probes/mirror_seed_collapse_probe.py`): of a 76460 mm³
  plate, 0 and 5940 mm³ still overlapped where the body had been.
* **Framework extensions this tool forces** (§8 step 5): a session pick may
  show the origin quads (`beginProfilePick(..., { planes: true })`, answered as
  `('plane', 'YZ')`), `armRepick` passes `spec.planePick`, and the feature
  tool's refusal sentences take the tool's verb (`spec.verb`: "repeats" for the
  patterns, "mirrors" here) instead of Pattern's hard-coded "repeats".

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | What is said |
|---|---|
| OK with no plane chosen | "Nothing mirrored — no plane was chosen. Open Mirror again and click a flat face or an origin plane before OK." |
| A plane in no known form | `mirror: plane must be "XY", "XZ" or "YZ", a face ({face_center, face_normal} or {face: "top"}), a mid-plane ({mid: "X"}) or {origin, normal} (got …)` |
| The plane's face is gone | `mirror: the plane face is gone — …; click a face for the plane` |
| A curved face as the plane | `mirror: the picked face is CYLINDER — a mirror plane is a flat face, an origin plane or the body's mid-plane` |
| A seed the tree no longer has, struck out, a sketch | `mirror: the seed 'hole1' is not in the tree — pick it again` · `… is struck out — restore it, or pick another feature` · `a sketch is not a feature to repeat (sketch patterns come with the sketch tools) — …` (delta_features' own sentences) |
| A seed not upstream of the body | `mirror: 'hole1' is not part of box1's history — mirror works on a feature of the body it is on` |
| A body named as `seed` | `mirror: 'box1' is a whole body, not a feature of one — leave 'seed' empty to mirror the body itself` |
| A seed whose delta is empty | `mirror: 'fillet1' neither removed nor added material — there is nothing to mirror` |
| The plane runs through the seed (probe §3: removes 0.0, image ∩ seed > 0) | `mirror: the mirror image of 'hole1' is the seed itself (it lands where the seed already is) — pick a plane beside the feature, through the body` |
| The image lands off the body (probe §4: removes 0.0, image ∩ seed = 0) | `mirror: the mirror image of 'hole1' lands off the body (nothing to cut there) — pick a plane beside the feature, through the body` |
| An added delta whose image lies inside the body | `mirror: the mirror image of 'boss1' adds nothing (it lies inside the body) — pick a plane beside the feature, through the body` |
| The image tangent to an edge (probe §8: an open shell is_valid calls fine) | `mirror: the mirror image leaves a broken solid (solid is not manifold/watertight …) — it runs exactly along an edge of the body; pick a plane beside the feature, through the body` |
| A body mirror whose image does not touch | allowed; the pieces warning with the remedy above |
| Kernel exception | `mirror: the kernel could not build the mirror image of 'hole1' — …` / `mirror: the kernel could not build the mirror image — pick another plane` (a body) |

The same measured step serves the patterns: a copy that lands ON its seed (a
hole on the pattern's axis) now says "copy 2 of 6 is the seed itself" instead
of blaming the body.
| A sketch row / pick as the seed (UI) | `Mirror mirrors a feature or a body — a sketch is not one (sketch mirrors come with the sketch tools). Click a hole, a boss, or a body.` |

The "exactly nothing" floor is Pattern's `1e-9` mm³: a through hole reflected
across the body's own Z mid-plane is its own image within 3 × 10⁻¹¹ of boolean
noise on two corpus bodies (probe §10) — by number, that is nothing.

## Acceptance (LAUNCH-PLAN P4)

* `static/js/mirror.js` in **≤ 90 lines, no geometry maths**: the quad's
  frame and size, the plane in stored form and the words for it, the seed's
  words and the alternatives all come from the plan.
* Backend: `pattern.mirror` and `pattern.plane_of` (the plane forms) beside
  the two pattern ops, on the shared `_seed` / `_repeat` / `stored_face`;
  `toolplan.plan_mirror` on a seed resolution factored OUT of `plan_pattern`
  (`_seed_plan` — one copy for three tools, R10); `document` wires the op by
  one tuple (`pattern.SEEDED_OPS`) for `_eval` and `REF_PARAMS`;
  `probes/mirror_probe.py` records the kernel facts (§1–§10); `author.py`'s
  catalogue teaches the AI `seed`, `join` and the plane forms; the legacy
  signature `mirror(part, plane="YZ")` still returns the copy.
* **Tests**: `tests/test_mirror_tool.py` (op: a hole's, a boss's and a
  fillet's delta reflected — volumes against formulas, positions against the
  centroids of the material that went away; a body join across its face = 2×,
  one solid; across its mid-plane = itself; every plane form; every sentence
  above; legacy copy unchanged; the document builds a mirror of a hole and it
  rides the seed; rename / delete walk the seed; plan tests: a row → no plane,
  the six alternatives, nothing built; a face pick → provenance; `plane_pick`
  face / world → stored form + frame; the select's name → its plane; edit
  reopens on the stored plane, a legacy plane keeps `join`, and a stored seed
  that has stopped resolving — a body name, or a placement row that now folds
  to one — comes back as a body Join on BOTH paths; `own_id`) and
  `tests/test_mirror_gauntlet.py` (every corpus body: a ⌀3 through hole on
  every flat face reflected across each of the body's three mid-planes and
  across the face's own plane, and the BODY across its largest face — a
  healthy solid or a sentence, never a raw kernel error; every mid-plane case
  of the plain box must build or be refused by number).
* **Browser journeys**: select the hole's row + Mirror + click the YZ quad +
  OK (two holes, one row, no combiner); a click on a face re-aims the plane
  mid-session and the image moves; the Plane box's mid-plane choice; a body
  seed doubled across its +x face; edit-and-cancel restores; OK with no plane
  adds no row and says so.

## The user's five-step checklist (R9)

1. Build a 60 × 40 × 12 box, put a ⌀6 through hole at (20, 10) on its top.
   Click the hole's wall, press **Mirror**: the three glass origin planes
   appear, the panel says Seed hole1, Plane "click a flat face or an origin
   plane", the box unchanged. Click the red **YZ** quad: a gold quad marks it
   and a second hole appears at (−20, 10). Click the green **XZ** quad: the
   image moves to (20, −10). OK: `mirror1` in the tree, no cut chip;
   double-click it and the gold quad is back on XZ.
2. Undo that (or delete the row). Click the box's plain top face, press
   Mirror: the panel says the seed is the body. Click the box's **+x** face:
   the body doubles to 120 mm across that face, one body. Click its **top**
   face: it doubles upward instead (24 mm thick). Cancel: the box is 60 × 40
   × 12 again.
3. Select the hole's row in the tree, press Mirror, open the **Plane** box and
   choose "the body's mid-plane across Y": the image at (20, −10). Choose
   "mid-plane across X": at (−20, 10). OK. Edit the box's width to 80 in the
   tree: the mirrored hole stays at (−20, 10) (the mid-plane is still x = 0).
4. Press Mirror with nothing selected: the hint asks for a feature or a body;
   click a sketch row and the chat says why not. Select the hole's row, press
   Mirror and press OK straight away: the chat says nothing was mirrored, no
   row is added. Press Mirror on the hole again and click the box's +x face:
   the chat says the image lands off the body and the box is unchanged; click
   the XZ quad: the image appears. Esc closes the panel and the image goes.
5. Put a second ⌀6 hole at (20, 0). Mirror it across the XZ quad: the chat
   says the plane runs through hole2 (its image is itself); choose the YZ
   plane in the box: the image appears at (−20, 0). OK. Rename hole2 to
   `pin` in the tree: the mirror row still builds. Strike out `pin`: the
   mirror is struck with it; restore it: both are back.
