# TextCAD backlog — the single source of truth for problems & missing tools

How this file works:
- **One entry per problem.** Every bug, friction point, or missing tool gets a line
  here the moment it is noticed — especially during dogfooding sessions.
- Each entry: what's wrong → how to reproduce/see it → why it matters.
- Priorities: **P0** = silent wrong geometry or data loss (trust killers — fix first),
  **P1** = blocks basic manual design, **P2** = hurts daily use, **P3** = release/polish.
- We work top-down. A fix is only "done" after ship-check (tests + live smoke test),
  and the entry moves to the Done section with the commit hash.

Dogfooding round 1 (2026-07-28): 5 agents built flange / L-bracket / enclosure /
stepped shaft with keyway / gasket through the UI only. All 5 parts completed with
volumes matching hand calculations to <0.1% — the geometry pipeline is solid. The
UI around it produced 36 friction items, merged below. Screenshots in scratchpad
`dogfood/<part>/`.

## To triage (dump new problems here, sort later)

- (empty — add anything that annoys you, even small things)

## P0 — silent wrong geometry / false verification / data loss

- [ ] **Extrude `both` is silently always-on: string "false" is truthy.** Found
  independently by 4 of 5 agents. The dialog renders booleans as text pre-filled
  "false"; backend does `bool(both)` → every dialog-driven extrude goes BOTH ways,
  silently doubling thickness (3mm gasket → 6mm; 8mm pegs → 16mm; 40mm box → 80mm).
  Tree then SHOWS `both: false` while geometry contradicts it, and retyping "false"
  is a no-op — only typing 0 fixes it. Fix: checkboxes for booleans in dialog AND
  tree, backend rejects/properly-coerces string booleans, regression test. Audit ALL
  ops for other string-coerced params while in there.
- [ ] **Slot entity: canvas preview shows overall length, backend builds
  center-to-center.** Click 20mm slot → readout "L 20" → solid comes out 28mm
  (SlotCenterToCenter). Preview and geometry must agree (decide ONE convention,
  fix canvas + backend + AI author docs together). Repro: sketch slot L20 H8,
  extrude, measure top view.
- [ ] **Wrong upstream input silently switches the displayed part while badge says
  "verified".** Chaining a modifier to an early feature (e.g. bolt circle ← disc1
  instead of ← bore) makes prior features a dangling dead branch: bore + holes
  vanish from viewport/volume, every row stays green, badge stays ✓. Exported part
  would be wrong. Fix: default-check the current tip, warn on dangling leaf
  branches, and surface "N bodies not in result" in the spec box.
- [ ] **Sketch features falsely FAIL verification and flip the whole doc to "check
  failed".** A valid 2-circle sketch got status=failed ("non-positive volume (0) —
  empty solid") — the solid-verifier ran on a 2D profile despite rebuild being
  2D-aware; doc badge went permanently red even though the final solid was correct.
  Poisons the one signal users are told to trust. Verify root cause (regression?)
  and add a test: bare sketch → status ok.
- [ ] **Sketch-on-face offered on CYLINDER faces → 3 failed features + a FALSE
  success message in chat.** Pick panel labels the face CYLINDER yet still offers
  "✎ Sketch on this face"; editor opens, user draws everything, Create commits
  sketch_on_face+extrude+cut which all fail ("Planes can only be created from planar
  faces") while chat announces "Pocket cut into the face". Cleanup = 3 hover-hidden
  deletes in reverse dependency order. Fix: hide/disable the button on non-planar
  faces with a hint; never emit success chat when features failed; add
  "delete feature + dependents" action.
- [ ] **Esc while drawing destroys the entire sketch.** The hint bar SAYS "Esc
  cancel (tool)", but canvas clicks focus <body>, the dialog's key handler never
  fires, and the browser's default closes the modal — all entities lost. Cost one
  agent two full redraws. Fix: keydown listener at document level while dialog open;
  Esc = cancel tool only; closing the dialog with entities present asks to confirm.

## P1 — blocks basic manual design

- [ ] **Viewport renders only the LAST feature's body — positioning is blind.**
  Worst single workflow problem, hit by 3 agents. Add a second body and the first
  vanishes (status volume too); rotating/moving a part into place happens with the
  reference body invisible; a cutter can't be judged against the part it will cut.
  Fix: render ALL leaf bodies (tip solid opaque, other leaves ghosted/translucent),
  and make result() vs displayed-set explicit in the status bar.
- [ ] **Committed sketches cannot be edited — any mistake = delete features and
  redraw from scratch.** No "edit sketch" action reopens the 2D editor; the tree
  shows entities as read-only JSON. For a sketch-centric CAD tool this is the
  biggest workflow gap. Fix: ✎ edit action on sketch rows → reopen #sketchDialog
  loaded with entities → save rewrites params → rebuild.
- [ ] **Fillet cannot target vertical edges — canonical "round the box corners"
  is unreachable** (was already listed; dogfooding upgraded it to blocker with
  evidence). edges accepts only all/top/bottom; "all" at r5 fails on 3mm shelled
  walls. Agent had to redraw the footprint as rounded sketch by hand (2 rects + 4
  circles — no rounded-rectangle entity, no sketch-corner-fillet either). Fix path:
  picked-edge → fillet (needs stable edge refs) OR at least a "vertical" rule +
  sketch corner-fillet tool + rounded-rect entity.
- [ ] **Add-Feature dialogs are bare snake_case + free text: no units, no enums, no
  conventions, radius/diameter chaos.** Hit by 4 agents. `bolt_radius` (radius) sits
  next to `pitch_circle_dia` (diameter); enum params (fillet.edges, shell.open_face)
  are text fields with placeholder "number" — valid values discoverable only by
  failing; nothing states primitives are origin-CENTERED, move is a RELATIVE offset,
  or which way plane offset / extrude go. Fix: per-op param metadata (label, unit,
  enum choices → dropdowns, bool → checkbox, help line with anchoring convention),
  consumed by dialog + tree + AI author docs.
- [ ] **Fresh/empty server state: /api/doc 500s (KeyError: None), UI boots
  half-dead, Add-feature silently no-ops.** All 5 agents hit it (they launch
  uvicorn directly, so no __main__ seed doc exists — but any empty state must
  behave). No welcome message, watcher spams 500s every 3s, clicking Add feature
  does nothing with no error. Fix: /api/doc returns a clean empty response (or
  auto-creates "untitled"), UI shows an onboarding empty state.
- [ ] **Sketch dialog footer (Create button!) pushed off-screen once entities grow.**
  At 1600×900 with 7 entities the Create/Cancel buttons sit below the viewport with
  no visible scrollbar — the flow's primary action is invisible. Fix: dialog
  max-height with internal scroll for the entity list + sticky footer.
- [ ] **Sketch trim tool missing** (pre-existing). Needs curve-curve intersection;
  add/cut composition covers some cases but real 2D drafting needs trim.

## P2 — hurts daily use

- [ ] **Stale/blank viewport around rebuilds.** Busy overlay clears when the POST
  returns, but the old mesh (even of deleted features) keeps rendering for seconds
  while /api/model tessellates — screen contradicts tree; on first load it's blank
  WHITE with no spinner; loadMesh() swallows fetch errors so a failed fetch leaves
  stale geometry forever. Fix: "updating model…" indicator tied to the /api/model
  fetch, dark canvas from boot, surface fetch errors.
- [ ] **Feature failures are near-silent and speak developer.** No toast/chat on a
  failed rebuild — just a small red dot; errors are raw Python reprs; one message
  suggests `max_fillet()`, an API a mouse user can't call. Fix: failure toast +
  human message templates per error class.
- [ ] **Boolean/cut dialogs don't express operand roles.** cut = "first minus rest"
  by TREE order of checked boxes, not click order — nothing says which body is kept.
  Fix: explicit "Keep / Remove" pickers (radio + checkboxes).
- [ ] **No positioned-hole feature.** "Hole" = center-only with_center_hole (no XY),
  so two bolt holes cost sketch + extrude + cut (3 features + throwaway body).
  Add hole(x, y, radius[, depth]) op; rename ribbon label to "Center hole" meanwhile.
- [ ] **No cylinder primitive by name; radius-only entry.** A shaft is Create > "Disc"
  with a 60mm "thickness" — first-timers scan for "Cylinder" and find nothing. Alias
  the label, and consider diameter entry (ties into dialog-metadata item above).
- [ ] **Feature ids must be invented by hand every time.** Auto-suggest disc1/hole2
  style defaults, editable. Quick win.
- [ ] **Viewport camera quirks.** Fit resets to iso instead of zoom-to-fit preserving
  orientation; post-rebuild auto-fit overrides a view button clicked during load.
- [ ] **No orientation cues in viewport.** No axes triad or labeled grid — after a
  rotate you cannot tell upright from flat. Add a corner triad.
- [ ] **Sketcher precision gaps.** Hard 1mm snap (can't click-place r2.5), no typed
  dimension during placement (Fusion-style), and the hint says "grid 10mm" while
  snap is actually 1mm. Card-editing afterwards works but is per-entity busywork.
- [ ] **No sketch constraints/solver** (pre-existing, long-term; explicit dimensions
  only — revisit after the P0/P1 list is burned down).
- [ ] **Compressor sample rebuild is slow (~1–2 min)** (pre-existing). Profile;
  cache unchanged sub-parts or parallelize blade builds.
- [ ] **Frontend automated test coverage is minimal.** E2E suite exists as a skill
  plan (tests/e2e/) — every P0/P1 fix above must land with an E2E regression test.
- [ ] **No measure tools in viewport** (pre-existing): distance between two picks,
  whole-part bounding box readout.

## P3 — release preparation / later

- [ ] **Vendor three.js locally** (unpkg CDN today — app breaks offline).
- [ ] **No LICENSE file / third-party notices.** Decide license; NOTICE for
  build123d/OCCT/three.js.
- [ ] **No git remote (backup!).** `winget install GitHub.cli` + `gh auth login`
  (user), then private repo + push + CI running pytest.
- [ ] **Assemblies/joints in Studio** (assembly.py exists; UI is single-part).
- [ ] **Units/grid settings** — everything is implicitly mm; at least label it.
- [ ] **AI-flow polish** (chat edits during rollback etc.) — parked until manual
  design is robust.

## Done

- (fixes move here with commit hash + date)
