# Loft — tool spec (Tier 2, LAUNCH-PLAN.md §4 / §8 step 1)

> **Status: approved by default while the user was out (2026-09-17, the
> scheduled Tier 2 build, tool 2 of 5 — memory `tier2-build-plan`).** Written
> before the code, as §8 asks; the user's first try is the approval gate.

## What you click, what you see

Draw two or more closed profiles on different planes (a circle on the top of a
block and a square on an offset plane above it, say). Select the first and
press **Loft**: its outline lights up as a white ring, the panel lists it as
the first profile and asks for a second. Click another sketch in the viewport,
its row in the tree, or pick it from the **Add** list: the ghost skins the two
outlines and, after one verified rebuild, the real blended solid replaces it.
Keep adding profiles; tick **Ruled** for straight walls between them; choose
New body / Join / Cut; press **OK**. A ✕ beside a profile takes it out again.

## Inputs (parity rules 1, 2)

* **Two or more sketch profiles**, each a SINGLE closed shape (the
  multi-profile refusal of REVIEW-QUEUE section 7 stands). The first comes
  from the selection when Loft is pressed (tree row, viewport pick, or the
  row's `⏢` button); the rest are added while the panel is open — this is the
  framework's first MULTI-INPUT tool (`tool.js`: `spec.inputs(st)` names the
  feature's input list; a profile tool with `onRepick` takes further sketch
  picks while open). A second click on a listed profile removes it.
* **`loft` stays a COMBINER**: the feature's inputs ARE the sections, in
  order, so the tree, the delete plan and every saved design are unchanged.
  Its one parameter is `ruled` (bool) — the first parameter a combiner has
  (`document.op_params` names it).
* **Order.** Measured (`probes/loft_api_probe.py`): sections picked OUT OF
  ORDER along the axis (z 0, 20, 10) loft into a self-intersecting solid at
  1.98 × the honest volume that the kernel calls VALID. So the sections must
  step one way along the loft's axis (the mean of their normals): the op
  REFUSES any other order with a sentence that names the right one; the tool
  puts picks into that order itself and says so once (`plan.reordered`).
* Not in this version: a flat FACE of a body as a section (Fusion allows it),
  guide rails, the tangent/direction conditions at the ends.

## The panel and the ghost (rules 3, 4, 5, 7)

* **Panel** `loftDialog`, ids `lf…`: Profile (section 1) · the list of
  profiles in loft order, each with ✕ · a hint line · **Add** (the plan's
  `candidates`: unconsumed single-profile sketches not yet listed) · **Ruled**
  · Operation (New body / Join / Cut) · Combine with (the plan's default: the
  body the first profile lives on) · Cancel / OK.
* **Ghost**: one 64-point outline ring per section (the plan's `sections[].ring`,
  world points, R1) skinned between neighbours (`viewport.beginLoftGhost`);
  one ring alone is the "pick a second" hint. Hidden once the real solid is
  on screen. No drag handle: Fusion's Loft has none.
* **Honest zero**: with one profile nothing is built; OK with one profile says
  so. The first verified build happens the moment a second profile is in.
* **Edit**: tree ✎ or double-click reopens the panel on the feature's inputs
  (locked — the framework never rewires a combiner mid-edit) with Ruled
  editable; Cancel restores it.

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | Measured | What is said |
|---|---|---|
| One profile on OK | — | "Nothing lofted — a loft needs at least two profiles. Open Loft on one sketch, then click a second one before OK." |
| A section holds 0 or 2+ closed shapes | (section 7 F1: two 2-circle sketches → one snaking 1570.8 mm3 solid) | "loft blends ONE closed profile per sketch, and 'b' holds 2 — draw each profile in its own sketch" |
| Two sections on one plane | volume 0.0, health "empty solid" | "loft produced no solid — 'a' and 'b' are on the same plane; a loft needs them on DIFFERENT planes" |
| Sections out of order along the loft | z 0, 20, 10: 1614 mm3 against 817 honest, `is_valid` True, health [] | "loft: the profiles do not run one way along the loft — a, b, c would fold the solid back through itself (the kernel builds that and calls it sound). Loft them in the order they lie: a, c, b" (the tool reorders and says so instead) |
| Profiles facing opposite ways with no common direction | — | "loft: the profiles face opposite ways with no common direction — turn one of the sketch planes" |
| The same sketch twice | StdFail_NotDone | the document's "loft needs 2 DIFFERENT profiles" |
| A body among the sections | SEGFAULT (section 4 F4) | the document's kind gate, before the kernel |
| Kernel refuses / broken result | — | "loft could not blend these profiles — …" / "loft: the blended solid came back broken (…)"; never raw OCP text, never a zero-volume success |

Three sections smooth is 0.75 of the ruled volume on r5-r2-r5 (a spline
bulging inward) — a real shape, not a defect; not guarded, said in the AI
note. A twisted pair of rectangles (45°) is 0.90 of a straight prism — also
real.

## Acceptance

* `static/js/loft.js` in 100–200 lines; `tool.js` gains `spec.inputs` and
  profile-kind repicks, nothing else.
* `sk.loft_geometry` is the ONE verdict for the op and the planner; every
  sentence above is a red test.
* `toolplan.plan_loft`: one profile opens (ring only), two build; the order
  is the plan's; candidates listed; edit mode reads the inputs.
* Tests: `tests/test_loft_tool.py` (op guards, volumes exact against the
  cylinder / frustum, the order rule, `ruled` through the document, plan) and
  3 browser journeys in `tests/e2e/test_loft_tool.py` (open from the row and
  add via the tree, Add list + Ruled + OK + edit-and-cancel, the reorder
  note).
