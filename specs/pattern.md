# Pattern — tool spec (P4, LAUNCH-PLAN.md §8 step 1)

> **Status: spec 2026-09-06, being built.** The fifth tool on the framework
> (`tool.js`): two ribbon buttons, **Circular Pattern** and **Rectangular
> Pattern** (Fusion's names), one declaring function (as Fillet / Chamfer),
> two ops that already exist and stay backward-compatible — `polar_pattern`
> and `linear_pattern` — grown so a pattern repeats a FEATURE, not only a
> body. First tool whose input is a FEATURE (a tree row), so the framework
> grows a fourth selection kind; first tool whose op needs more than its one
> input part (the seed's before / after bodies come from the document).
>
> Decisions made here without the user (say so if any is wrong): the count
> is typed, not dragged (Fusion has a quantity handle — §10); Circular opens
> at count 1 and Rectangular at count 2 / distance 0, so nothing is built
> until the user acts (rule 4); Rectangular's distance is **Spacing** by
> default (the pitch a machinist knows; Fusion's box offers Extent too);
> Fusion's *Symmetric* distribution and the *Suppress* checkboxes are left
> out (§10); a copy that misses the body is refused with a sentence rather
> than silently skipped. Autodesk's Pattern reference (Object type · Objects ·
> Axis / Axes · Distribution: Extent / Spacing · Quantity · Distance · Angular
> distribution: Full / Angle) is the vocabulary.

## What you click, what you see

Click a hole (its wall) or its row in the tree, press **Circular Pattern**: a
gold ring lies on the face around the face's centre, through the hole; the
Count box reads **1**, Angle reads 360 (Full) — nothing has been built. Type
6: six holes on the bolt circle after one verified rebuild. Drag the ring to
180 and the six spread over a half turn. Click a bore's cylindrical face and
the ring re-centres on THAT axis. OK: one `polar_pattern1` row in the tree
after the body. **Rectangular Pattern** on the same hole: an arrow from the
hole along the face's x and a second along its y, Count 2 / Distance 0 — drag
the first arrow to 20 and a second hole appears 20 mm along; type Count 4 for
a row of four; drag the second arrow and the row becomes a grid. Double-click
a pattern row and the ring / arrows come back at the stored values.

## Inputs (rules 1, 2)

* **A feature, or a body — the seed.** Select-then-command: the tree row
  selected when the tool is pressed (a non-sketch row is a new selection kind,
  `feature`), or the face picked in the viewport, whose maker the server looks
  up (provenance — the hole's wall belongs to `hole1`, a boss's top to its
  `extrude1` + folded `fuse1`, the plate's own top to `plate1`). With nothing
  picked the tool waits for a click or a tree row (command-then-select). A
  sketch is refused with a sentence.
* **What "the feature" means is the server's rule** (`document.delta_parts`,
  ONE resolver for the op and the plan): a modifier of a body (`hole`,
  `fillet`, `chamfer`, `extrude_face`…) is its own before / after; a pulled
  tool (`extrude`, `revolve`, `loft`, `sweep`) with a folded 2-input boolean is
  that BOOLEAN's before / after (the tree's own folding rule); a bare boolean
  is before = its first input, after = itself; anything else (a creator, a
  standalone solid, a fuse of separate bodies) is a **body seed** — the whole
  body is repeated, Fusion's Bodies type and the legacy behaviour.
* **The delta, not the op** (probe §1–§4): what the seed REMOVED (before −
  after) is cut again at every copy, what it ADDED (after − before) is fused
  again. A hole, a pocket, a boss, a fillet all pattern the same way; the op
  never needs to know how the seed was made.
* **The pattern goes on the body's CURRENT state**: the feature's input is the
  seed body's latest solid descendant (the tip), the pattern row is appended
  there; `seed: "hole1"` is a param, `seed: null` is a body pattern. The op
  eats its body (a modifier in, a modifier out — no combiner row).
* **`seed` is a REFERENCE, the tree's only one that is not an input**
  (`document.REF_PARAMS`). Rename walks it, so renaming a seed renames it
  inside every pattern of it; delete walks it, so deleting (or striking) a seed
  takes the patterns of it along — rewiring one to the seed's upstream body
  would silently make it repeat a DIFFERENT feature.
* **The tool's own feature, mid-session** (`own_id` on the plan request): once
  a NEW session has built its pattern, replanning is about THAT feature —
  otherwise the walk to the tip lands on the pattern's own output and the next
  plan aims the axis at the already-patterned solid. `feature_id` stays the
  edit-session key; `own_id` is ignored while the feature is still in flight.
* **Stored forms are ONE each** (the Hole review's lesson): the circular
  `axis` is `null` (legacy: world Z through the origin), a world name `"+Z"`
  (through the origin — the AI's vocabulary), a face pick / name (`{face_center,
  face_normal}` or `{face: "top"}` — a flat face gives its normal through its
  OUTER wire's centre (probe §5), a cylindrical face its own axis (§6)), or an
  explicit `{origin, dir}` (a body seed from the tree, no face to hang it on).
  The rectangular `direction` / `direction2` are world unit vectors (a
  direction rides a translated face untouched; only a rotated one would move
  it) — `null` keeps the legacy `dx, dy, dz` step. EDITING such a legacy
  feature reads that step as a direction AND a distance (`pattern.legacy_step`,
  in the plan's `params`), so the panel opens on what the pattern actually does
  instead of re-aiming it to world X with the first distance typed.

## The handles and the panel (rules 3, 4, 5)

* **Circular — the ring**: the same ring Revolve drags, in the plane through
  the seed's centre perpendicular to the axis, radius = the seed's distance
  from the axis; it drags the total **Angle** (360 = Full: copies every
  360/count; less: copies from 0 to the angle inclusive, Fusion's Angle type).
  A gold axis line shows the axis (Revolve's). The Count is typed. Panel
  `cpDialog`, ids `cp…`: Seed (locked, "hole1 on box1") · Axis (what the plan
  chose, as words: "normal of the top face through its centre" / "axis of the
  ⌀20 bore") · Count (**1**) · Angle (360) · Cancel / OK.
* **Circular — re-aim by clicking**: while the panel is open a click on a
  cylindrical face of the body puts the axis on that cylinder's axis, a click
  on a flat face on its normal through its centre (the framework's `repick`
  with a tool hook: the click means the AXIS, not the input).
* **Rectangular — two arrows** from the seed's centre along the plan's
  direction 1 (the seed face's x) and direction 2 (its y), the same arrow
  Extrude drags: each drags its Distance; the second, dragged from 0, also
  sets Count 2 to 2 (Fusion activates Direction 2 when it gets a distance).
  Negative values are allowed (the other way along the axis). Panel
  `rpDialog`, ids `rp…`: Seed (locked) · Along: the face's x / y (swaps the
  two directions — from the plan's `alternatives`, never JS geometry) ·
  Distance type: Spacing / Extent · Count 1 (**2**) · Distance 1 (**0**) ·
  Count 2 (1) · Distance 2 (0) · Cancel / OK.
* **No ghost**: the copies are real (one verified rebuild on release / after a
  typed pause); a pattern is drawn only by the kernel.
* **Edit**: tree ✎ or double-click reopens with the handles at the stored
  values; Cancel restores verbatim — inherited.
* **Framework extensions this tool forces** (§8 step 5): the `feature`
  selection kind (a non-sketch tree row; the plan request carries
  `feature_id`), `onRepick(st, data)` (a tool decides what a session click
  means; Hole keeps the default — move the input), and the plan may name the
  body the feature is applied to (`input`) when it is not the picked one.

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | What is said |
|---|---|
| Count 1 (circular) on OK, or no rectangular direction with BOTH a count above 1 and a distance (Direction 2 alone IS a pattern) | "Nothing patterned — the count was 1. Open Circular Pattern again and type how many copies before OK." / "Nothing patterned — no direction had both a count above 1 and a distance. Open Rectangular Pattern again, then drag an arrow or type a distance before OK." |
| Count < 1, not a whole number, angle outside 0 < a ≤ 360 | `polar_pattern: count must be a whole number ≥ 1 (got 0)` · `polar_pattern: the angle must be between 0 and 360 (got 400) — 360 is a full circle` |
| A seed the tree no longer has, or one struck out | `polar_pattern: the seed 'hole1' is not in the tree — pick the feature to repeat again` |
| A seed that is not upstream of the body | `polar_pattern: 'hole1' is not part of box1's history — a pattern repeats a feature of the body it is on` |
| A seed whose delta is empty (a feature that changed nothing) | `polar_pattern: 'fillet1' neither removed nor added material — there is nothing to repeat` |
| A copy that lands off the body (probe §7: removes exactly 0.0) | `polar_pattern: copy 3 of 6 lands off the body (nothing to cut there) — a smaller count, another axis, or move the seed` |
| A copy whose cut leaves an open shell (probe §7: tangent to an edge) | `polar_pattern: copy 2 of 4 leaves a broken solid (an open shell) — it runs exactly along an edge; change the count or the angle` (the framework puts back the last value that built) |
| A legacy body pattern with no step at all (`count`, no `dx / dy / dz`) | `linear_pattern: the step is 0, so all 4 copies land on the seed — give dx, dy or dz (or a direction and a distance)`. A body pattern whose copies land back ON a symmetric body is NOT refused: it built before the op grew a seed, and a saved design may never stop rebuilding. |
| A body pattern whose copies are separate pieces (probe §8: healthy) | allowed — the framework's pieces warning with the remedy "separate copies are what a body pattern makes; pattern a feature of the body instead if you wanted one part" |
| An axis / direction that cannot be resolved (the face is gone) | `polar_pattern: the axis face is gone — the face it was taken from no longer exists; click a face for the axis` |
| A sketch row or a sketch pick as the seed | `Circular Pattern repeats a feature or a body — a sketch is not one (sketch patterns come with the sketch tools). Click a hole, a boss, or a body.` |
| Kernel exception | `polar_pattern: the kernel could not build copy 4 of 6 — change the count, the angle or the axis` (the kernel's class name stays out of the sentence) |

## Acceptance (LAUNCH-PLAN P4)

* `static/js/pattern.js` in **100–160 lines, no geometry maths**: the ring's
  frame, radius and centre, the axis line, the arrows' origin and directions,
  the seed's description and the alternatives all come from the plan.
* Backend: `pattern.py` (the two ops, the delta pattern, `axis_of`,
  `direction_of`, the per-copy measurement), `document.delta_parts` (the one
  seed resolver) and the rebuild handing the seed's parts to the op,
  `toolplan.plan_pattern`. `probes/pattern_probe.py` records the kernel facts
  (§1–§11 in its docstring). `author.py`'s catalogue teaches the AI the new
  params; the two legacy signatures still build every existing design
  (`tests/fixtures` designs with `polar_pattern` / `linear_pattern`).
* **Tests**: `tests/test_pattern_tool.py` (op guards and every sentence above;
  volumes against formulas for a hole, a boss and a fillet seed, circular and
  rectangular, Full and Angle, Spacing and Extent, two directions; the legacy
  body pattern unchanged; the seed resolver on a hole, a folded pocket, a
  boss, a body; riding an upstream change; plan tests: seed → ring frame /
  radius / axis words / directions / alternatives, edit reopens on stored
  values, a cylinder click re-aims) and `tests/test_pattern_gauntlet.py`
  (every corpus body, a through hole on every flat face, 3 and 5 copies
  circular about the face centre, 3 copies linear along u — a healthy solid or
  a sentence, never a raw kernel error; every face of the box must build).
* **Browser journeys**: click the hole's wall + Circular + type 6 + OK; drag
  the ring to 180; Rectangular: drag arrow 1, type Count 4, drag arrow 2;
  edit-and-cancel restores; a click on a bore re-aims the ring. Plus the three
  the P4 code review earned: Circular → Esc → Rectangular → a row click opens
  RECTANGULAR; a curved pick beats a tree row left selected; Direction 2 alone
  builds.

## The user's five-step checklist (R9)

1. Build a 60 × 40 × 12 box, put a ⌀6 through hole at (20, 0) on its top.
   Click the hole's wall, press **Circular Pattern**: a gold ring on the top
   face around the face's centre passing through the hole, an axis line
   through the centre, Count 1, Angle 360, the box unchanged. Type 6: six
   holes on the bolt circle. Type 4: four. Drag the ring to about 180: the
   four spread over a half turn, the box says so. OK: `polar_pattern1` in the
   tree, no cut chip; double-click it and the ring is back at 180.
2. Undo that (or delete the row). Add a second box 30 × 30 × 12 beside the
   first with a Ø10 bore through it, then a ⌀4 hole on the first box. Press
   Circular Pattern on the ⌀4 hole, click the bore's cylindrical wall: the
   ring re-centres on the bore's axis. Cancel: the hole is alone again.
3. Click the ⌀6 hole again, press **Rectangular Pattern**: two arrows from the
   hole along the face's x and y, Count 2 / Distance 0, nothing built. Drag the
   x arrow to about 15: a second hole 15 mm along. Type Count 4: a row of
   four. Drag the y arrow to 12: the row becomes a 4 × 2 grid. Switch Distance
   type to Extent: the four fit inside 45 mm. OK.
4. Press Circular Pattern with nothing selected: the hint asks for a feature
   or a body; click a sketch row and the chat says why not; click the box's
   plain top face: the seed is the BODY (the panel says so), type 3: three
   boxes around the face's centre, and the chat says they are separate
   copies. Cancel.
5. Open `polar_pattern1` and type Count 40: the chat says a copy lands off the
   body (or leaves a broken solid) and the body keeps the count that built.
   Type Angle 400: the chat says the angle must be between 0 and 360. Esc
   closes the panel — once.
