# Section view — spec (Tier 2, LAUNCH-PLAN.md §4 / §8 step 1)

> **Status: approved by default while the user was out (2026-09-17, the
> scheduled Tier 2 build, tool 4 of 5 — memory `tier2-build-plan`).** Written
> before the code; the user's first try is the approval gate.

## What you click, what you see

Press **Section** in the Inspect tab. A gold, translucent plane appears
through the middle of the model and everything on one side of it is cut away
on screen, so you look into the part — pockets, walls, bores — the way
Fusion's Section Analysis does. An arrow on the plane drags it along its axis;
the panel has **Axis** (X / Y / Z, default Z), **Offset** (mm, starts at the
model's centre), **Flip** (which side is hidden) and **Close**. Press Section
again, Close, or Esc with no tool open, and the model is whole again.

Nothing about the design changes: a section view is a way of LOOKING. It is
not saved, it does not survive a reload, no tree row is made, no request goes
to the server (R1 has nothing to hand over: the plane is three numbers the
user chose).

## Rules

* **A mode is never a separate screen (parity rule 10):** the section is the
  normal 3D view with a clipping plane on the bodies. Orbit, pan and zoom as
  ever; sketches, ghosts and the tool handles are NOT clipped — only bodies
  and their edges.
* **Direct manipulation first (rule 3):** the arrow on the plane is the
  primary control; the Offset box is the exact-figure second option, in the
  display unit like every length box.
* **It is a view state, not a command:** opening a tool (Extrude, Fillet…)
  leaves the section on. Esc cancels an open TOOL first (tool.js's Escape
  runs while its panel holds the modal lock, and the section's Escape stands
  down whenever `S.modalTool` is set); with nothing open, Esc closes the
  section. Bodies loaded while the section is on get the plane too (every
  body material is made in one place, `viewport.addBodies`).
* **The cut face is honest, not pretty:** the body is rendered two-sided while
  sectioned so the inside shows as the body's own colour; a capped, filled cut
  face (a stencil trick) is a §10 loose end.
* **Shared handles:** the arrow and the gold quad are the same gizmos Extrude
  and Mirror use. A tool that opens while the section is on takes them for its
  session and they go with it when the tool closes; the section itself stays
  (the clipping is on the materials) and the panel's Offset box still moves
  it; touching Axis / Flip / Offset brings the handles back. A §10 loose end.

## Failures speak

There is nothing the kernel can refuse here. The one sentence: the chat says
once, on opening, what the plane is and how to put the model back.

## Acceptance

* `static/js/section.js` (80–150 lines) + `viewport.beginSection /
  setSectionOffset / endSection / sectionInfo`; the Inspect tab's **Section**
  button; the `sectionDialog` panel; ui v bump.
* `tests/e2e/test_section_view.py`: toggle on → every body and edge material
  carries the plane, the quad and the arrow are present, the plane's constant
  is the model's centre; a typed offset moves the plane; the arrow drag moves
  the Offset box; Flip reverses the normal; Close clears every material and
  the quad; a body added while sectioned is clipped; Esc with a tool panel open
  cancels the tool and leaves the section; a screenshot LOOKED at.
