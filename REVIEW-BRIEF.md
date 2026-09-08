# REVIEW-BRIEF.md — what the next code review should look at

> **How this file works.** It is written fresh at the end of every work
> session, right after the code commit, and it is always about ONE review. It
> is not a log: the previous contents are REPLACED, so the file stays short
> and the review chat pays for one small read instead of re-deriving three
> commits of context. Ship-check step 6 refreshes it.
>
> **In the review chat, type exactly this and nothing else:**
>
> ```
> /code-review high — read REVIEW-BRIEF.md first: it names the commit range, the base, and what not to re-report
> ```
>
> That line never changes. Everything specific to today is below, which is
> why the line can stay the same forever.

---

## Review this

| | |
|---|---|
| **Range** | `bdd8ebf..HEAD` — ONE commit: the first lint pass over the whole project (Ruff for Python, ESLint for JavaScript). It found **no real bug**; it removed dead code and added the two linters plus an edit hook |
| **Already reviewed** | everything up to `bdd8ebf` (the review answer of 2026-09-07). **Do not re-review it** |
| **Effort** | low is enough — nothing in this commit is meant to change behaviour, so the whole review is one question |
| **Branch** | `master` (no pull request — do not try to comment on GitHub) |
| **Frontend** | `ui v170` (css unchanged at v39) |

The one question: **did any removed line actually do something?** Every
removal was reported by a linter as unused and then checked by hand, but the
checks were reading, not running, and the fast test tier does not execute
every browser path.

## What was removed, and where the risk is

### 1. `static/js/viewport.js` — the module-level `mesh` variable

Declared at the top, written in `disposeModel()` (`mesh = null`) and in the
body loader (`mesh = m` for the result body), **never read** — every reader in
the file uses `bodyObjs[i].mesh` or a local `const mesh`. Both writes and the
declaration are gone. ESLint's `no-undef` confirms no reader remains.

**Look at:** is there a reader OUTSIDE the file — a `__vp` debug hook, a test
that pokes `viewport.mesh`? I searched `static/js` and `tests/e2e`; nothing.

### 2. `static/js/tool.js` — the dead store in `applyOnce`

`doc = settled.doc; f = settled.f;` lost its first half: `doc` is a local of
`applyOnce` that nothing reads after the settle (`applyOp()` reads `S.doc`).
Also new: an `eslint-disable-next-line no-unmodified-loop-condition` on the
apply loop with the reason `hide() sets st = null during the await`
(`tool.js:303`). **Check that reason is true**, because if it is not, the loop
`while (applyPending && st)` has a condition that never changes.

### 3. Four unused imports and three unused results, JavaScript

`doctabs.js` (`S`), `fillet.js` and `pattern.js` (`say`), `tree.js`
(`openFeatDialog`); `sketch3d.js` dropped `const c =` before
`ctx.setOrbitUp(...)`, `sketcher.js` dropped `const cur = pathCursor()` in
`pathGhost` (`pathCursor` is pure — three lines, no side effect), `api.js`
wraps the `setTimeout` in a promise executor in braces so its id is not the
executor's return value (a lint rule, no behaviour change).

### 4. Python: 17 unused imports, 2 f-strings with no placeholders

Removed by `ruff --fix`, then read. `blocks.py` lost `Locations` from its
build123d import, `pattern.py` lost `math`, `author.py` lost `document`,
`backfill.py` lost `HistoryError`, `assembly.py` lost `build123d`; the rest are
in tests. `generate.py` (the old prototype) gained `if TYPE_CHECKING: import
check` so its `"check.Spec | None"` annotation names a real module.
`tests/e2e/test_sketch_scale.py` lost a walrus that assigned a name nothing
read.

### 5. New tooling — `ruff.toml`, `.claude/lint/`, `.claude/hooks/py_lint_check.py`

- `ruff.toml` selects `F, E7, E9, B, PLE` and ignores eight rules with a
  reason each. **`B023` is ignored** because all 32 hits were checked to be a
  lambda called inside the same loop iteration (the gauntlet tests'
  `assert_op(label, lambda: ...)`) or an IIFE that binds the variable
  (`pattern.py`'s `(lambda t: (lambda s: ...))(t)`). If you find one that is
  called AFTER its loop moves on, that is a real finding.
- `.claude/lint/` holds `package.json` + `eslint.config.mjs`; `npm install`
  there, then `npm run lint`. `node_modules` and the lockfile are ignored.
- The hook runs `ruff check --select E9,F63,F7,F82,PLE` on every edited `.py`
  and blocks with the output. **A hook must never break a tool call**: check
  it exits 0 on every path, including "ruff not installed" and "not a .py".

## Ground rules for this repo (they change what counts as a finding)

- **Never re-derive a backend fact in the frontend.** Axis, origin, frame, safe
  range, target body, edge groups: a field on a server response, never JS math.
- **A failed feature beats a corrupt body.** A kernel exception reaching the
  user and a "successful" invalid solid are both banned. OCP errors derive
  from `Exception`, not `RuntimeError`.
- **Geometry claims are measured, not reasoned about.** If you think a number
  is wrong, say what to measure. A finding that rests on reading the code
  alone, in a place where a probe exists, will be measured before it is fixed.
- Comments carry the user's own words and the date a bug was seen; they are
  the repo's memory, not clutter.

## Already known — do NOT re-report

- Everything in `16ade36..bdd8ebf`: those two reviews are closed (STEP export,
  fillet picking, edge-group chips, and the six fixes). In particular the
  pixel-space `ownFaceHit` proposal was measured and rejected.
- Style-class lint output that is deliberately ignored: `a = x; b = y` on one
  line (`E702`), single-letter geometry names (`E741`), lambda assignment,
  `raise` without `from`, `zip` without `strict`.
- ESLint's `no-use-before-define` is configured with `variables: false`: a
  module-level `let` declared lower in the file and used inside a function is
  legal and common here. Do not report those.
- Five tools hand-type "a value typed before the plan arrived waits for it"
  (LAUNCH-PLAN §10, P3).
- `test_revolve_tool.py::test_open_from_the_tree_row_and_drag_the_ring` is
  order-dependent (§10 P1): it passes in its own file, fails after its
  neighbours. Pre-existing.
- 5 pre-existing red browser tests in `tests/e2e/test_tree_delete.py` (§10 P1,
  someone else's work).
- Pattern's drag ghost (§10 P3, deferred by the user).
- `designs/esp32-remote` reports a spec mismatch (36 solids vs `n_solids: 1`);
  the spec is the user's to update, not the code's.

## After the review

Bring the findings back to the work chat. Each one gets reproduced by
measurement, then a test that is RED before the fix, then the fix — never a
fix applied straight from the review (`--fix` skips that discipline).
