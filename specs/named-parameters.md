# Named parameters — spec (Tier 2, LAUNCH-PLAN.md §4 / §8 step 1)

> **Status: approved by default while the user was out (2026-09-17, the
> scheduled Tier 2 build, tool 5 of 5 — memory `tier2-build-plan`).** Written
> before the code; the user's first try is the approval gate. The plan calls
> this "the biggest usability win after the tree".

## What you click, what you see

Press **Parameters** in the Modify tab. A panel lists the design's named
values — name, formula, value, comment, and how many features use each — with
a row to add one: type `wall`, `3`, press Add. Now, in the feature tree, click
any dimension and type a formula instead of a number: `wall*2`. The row shows
`wall*2 = 6` and the part rebuilds. Change `wall` to 4 in the panel and every
feature that names it follows. Rename `wall` to `thickness` and every formula
is rewritten. Delete is refused while anything still uses it, naming the users.

## Rules

* **A parameter** is `name → {expr, comment}`. Names are identifiers (letters,
  digits, `_`, not starting with a digit), never a Python keyword, never a
  function name, never a feature's id (both directions: a feature cannot take
  a parameter's name either).
* **A formula** is text parsed with Python's `ast` and walked by hand —
  `paramexpr.py` — never `eval`: numbers, parameter names, `+ - * / **`,
  unary minus, brackets, and the functions `min max abs round sqrt floor ceil
  sin cos tan` (degrees). Anything else is refused naming the piece.
  `**` caps its exponent at 64; results must be finite and below 1e9.
  Measured against an injection corpus (`probes/paramexpr_probe.py`): 43
  strings from `__import__('os')` to `10**10**10` — every one a sentence,
  none ran.
* **Where a formula may stand:** any NUMERIC parameter of any op
  (`Document.numeric_params`, the annotation-driven whitelist). `_resolved(f)`
  turns formulas into numbers before an op runs, so no op ever sees a string;
  `_check_numeric_params` accepts a string iff it parses as a formula AND
  works out under the current parameters (`"wal*2"` is refused with the
  evaluator's sentence — the unknown name comes with a suggestion; `"8mm"`
  is no formula and keeps the sentence it always had).
* **The cache follows the values:** `_signature` is taken on the RESOLVED
  params, so changing `wall` rebuilds exactly the features that name it.
  Measured: a `wall*2` extrude went 1200 → 1600 mm³ on `wall` 3 → 4.
* **Order and loops:** parameters may name each other; they evaluate in
  dependency order; a loop is refused at the door (`set_parameter` puts
  everything back) and, in a loaded file, is a sentence naming the loop.
* **Rename** rewrites NAME tokens (`tokenize`), never text: `wall` inside
  `wall_2` is left alone. **Delete** is refused while a feature or another
  parameter names it, listing them.
* **Saving:** `parameters` is a top-level key of the design, ABSENT when
  empty — the 47 saved designs round-trip byte for byte (measured). A file
  whose parameter is gone or looped still OPENS: the parameter carries its
  problem, the features that name it go red with the sentence.
* **Undo / versions** carry parameters because both work on `to_data`.
* **The AI** may author `parameters` and formulas (prompt paragraph; the MCP
  `build_design` door sets them before the features).
* **Not in this version (§10):** formulas in the TOOL panels' boxes (Extrude's
  distance box stays numeric — type the formula in the tree afterwards), units
  on parameters, "make this measurement a parameter" (MEASURE-PLAN P4's ⛓
  button), a parameter's value driven BY a measurement.

## Failures speak

| Situation | What is said |
|---|---|
| `wal*2` | "'e' (extrude): amount = 'wal*2' — no parameter named 'wal' — did you mean 'wall'?" |
| `8mm` | the sentence that already stood: "'e' (extrude): amount must be a number (got '8mm') — type just the number, without units" (text that is no formula never enters the evaluator) |
| `__import__('os')` | "… '__import__('os')' is not allowed — the functions a formula may use are abs, ceil, …" |
| `1/0` | "'1/0' divides by zero" |
| a = b, b = a | "'a' is in a loop of parameters that need each other (a -> b -> a) — one of them must be a plain number" |
| delete a used parameter | "'wall' is used by feature 'e', parameter 'wall_2' — change those to a number or another parameter first" |
| a feature's name | "'e' is the name of a feature — a parameter and a feature cannot share a name" |

## Acceptance

`paramexpr.py`; `Document.parameters / set_parameter / rename_parameter /
remove_parameter / parameter_users / _resolved / parameters_json /
resolved_json`; `/api/parameters`, `/rename`, `/remove`; `_doc_json` carries
`parameters` and per-feature `resolved`; `static/js/params.js` panel; tree
rows show `formula = value` and accept formulas; the AI note; tests
(`tests/test_named_params.py`: the injection corpus, cycles, unknown names,
rename by token, delete refusal, cache invalidation by measured volume,
round trip absent-when-empty, a broken file opens red, the API) and 3 browser
journeys (`tests/e2e/test_named_params.py`).
