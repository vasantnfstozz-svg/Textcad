"""Safe arithmetic for NAMED PARAMETERS (Tier 2, specs/named-parameters.md).

`wall = 3` once, and a feature's `amount: "wall*2"` follows. An expression is
Python-looking text, but it is never handed to Python: it is parsed with `ast`
in 'eval' mode and walked by hand, and only these pieces are allowed —

    numbers            3   2.5   1e3
    parameter names    wall   base_thickness
    + - * / **         with unary minus and parentheses
    functions          min max abs round sqrt floor ceil  sin cos tan (DEGREES)

Everything else — attribute access, subscripts, calls to anything but the
list above, strings, comparisons, lambdas, names Python treats as keywords —
is refused with a sentence that names the offending piece. Results must be
finite and no larger than a dimension could ever be (`MAX_VALUE`); `**` caps
its exponent so `10**10**10` never runs. Renaming a parameter rewrites the
NAME tokens of every expression, never the text, so `wall` inside `wall_2`
is left alone.

Measured (probes/paramexpr_probe.py) against the injection corpus in
tests/test_named_params.py: every string in it is a sentence, none runs.
"""
from __future__ import annotations

import ast
import io
import keyword
import math
import re
import tokenize

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_VALUE = 1e9            # mm, degrees or a count — nothing in a design is bigger
MAX_EXPONENT = 64          # `**` past this is not a dimension either
MAX_LENGTH = 200           # characters; longer is not a formula anyone typed

FUNCS = {
    "min": min, "max": max, "abs": abs, "round": round,
    "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
}
_OPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**"}


def name_problem(name) -> str | None:
    """Why `name` cannot be a parameter's name, or None when it can."""
    if not isinstance(name, str) or not name.strip():
        return "a parameter needs a name"
    if not NAME_RE.match(name):
        return (f"'{name}' is not a usable name — letters, digits and '_', not starting "
                f"with a digit, no spaces")
    if keyword.iskeyword(name) or name in FUNCS or name in ("True", "False", "None"):
        return f"'{name}' is a reserved word — pick another name"
    return None


def _piece(expr: str, node: ast.AST) -> str:
    seg = ast.get_source_segment(expr, node)
    return repr(seg) if seg is not None else type(node).__name__


def parse(expr) -> ast.Expression:
    """The expression as a tree, or a sentence naming what is not allowed."""
    if not isinstance(expr, str):
        raise ValueError(f"an expression is text such as 'wall*2', got {expr!r}")
    text = expr.strip()
    if not text:
        raise ValueError("the expression is empty — type a number or a formula such as wall*2")
    if len(text) > MAX_LENGTH:
        raise ValueError(f"the expression is {len(text)} characters long — a formula is "
                         f"short; split it into parameters")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"'{text}' is not a formula — check the brackets and operators "
                         f"(Python says: {e.msg})") from None
    called: set = set()                # the Name nodes that are an allowed call's function
    for node in ast.walk(tree):        # breadth-first: a Call is seen before its func Name
        if isinstance(node, (ast.Expression, ast.Load)):
            continue
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError(f"{_piece(text, node)} is not a number — a formula holds "
                                 f"numbers and parameter names only")
            continue
        if isinstance(node, ast.Name):
            if node in called:
                continue
            if node.id in FUNCS:
                raise ValueError(f"'{node.id}' is a function — call it: {node.id}(...)")
            continue
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            continue
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            continue
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Name) and node.func.id in FUNCS
                    and not node.keywords):
                called.add(node.func)
                continue
            raise ValueError(f"{_piece(text, node)} is not allowed — the functions a formula "
                             f"may use are {', '.join(sorted(FUNCS))}")
        if isinstance(node, tuple(_OPS)) or isinstance(node, (ast.USub, ast.UAdd)):
            continue                                  # the operators the BinOp/UnaryOp checks allowed
        if isinstance(node, (ast.operator, ast.unaryop)):
            raise ValueError(f"the operator in {_piece(text, tree.body)} is not allowed — "
                             f"a formula uses + - * / ** and brackets")
        raise ValueError(f"{_piece(text, node)} is not a number or a parameter — a formula "
                         f"holds numbers, parameter names, + - * / ** and "
                         f"{', '.join(sorted(FUNCS))}")
    return tree


def names_in(expr) -> list[str]:
    """The parameter names an expression refers to, in order of first use."""
    out: list[str] = []
    for node in ast.walk(parse(expr)):
        if isinstance(node, ast.Name) and node.id not in FUNCS and node.id not in out:
            out.append(node.id)                 # (a parameter is never named like a function)
    return out


def _suggest(name: str, known) -> str:
    close = [k for k in known if k.lower() == name.lower()
             or (len(k) > 2 and (k in name or name in k))]
    return f" — did you mean '{close[0]}'?" if close else ""


def evaluate(expr, values: dict) -> float:
    """The value of an expression given the parameters' values. Every failure
    is a sentence: an unknown name (with a suggestion), division by zero, a
    result too large or not finite."""
    if isinstance(expr, bool):
        raise ValueError(f"{expr!r} is not a number")
    if isinstance(expr, (int, float)):
        return float(expr)
    tree = parse(expr)
    text = expr.strip()

    def walk(node):
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ValueError(f"no parameter named '{node.id}'"
                                 + _suggest(node.id, values))
            return float(values[node.id])
        if isinstance(node, ast.UnaryOp):
            v = walk(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            a, b = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                if b == 0:
                    raise ValueError(f"'{text}' divides by zero")
                return a / b
            if abs(b) > MAX_EXPONENT:
                raise ValueError(f"'{text}' raises to the power {b:g} — no dimension needs "
                                 f"an exponent past {MAX_EXPONENT}")
            try:
                r = a ** b
            except (OverflowError, ZeroDivisionError) as e:
                raise ValueError(f"'{text}' cannot be worked out ({e})") from None
            if isinstance(r, complex):
                raise ValueError(f"'{text}' has no real value (a negative number to a "
                                 f"fractional power)")
            return r
        if isinstance(node, ast.Call):
            args = [walk(a) for a in node.args]
            # every value here is a float, and Python's round() takes its
            # digits as an INT only: `round(x, 2)` read "'float' object cannot
            # be interpreted as an integer" (review, 2026-09-23)
            if node.func.id == "round" and len(args) == 2:
                if not args[1].is_integer():
                    raise ValueError(f"'{text}': round() takes a whole number of digits "
                                     f"(got {args[1]:g})")
                args[1] = int(args[1])
            try:
                return float(FUNCS[node.func.id](*args))
            # OverflowError is not a ValueError: floor/ceil/round of an
            # infinite value (`floor(1e400)`) raised it straight through, and
            # set_parameter had already written the formula, so the design
            # stopped opening (review, 2026-09-23)
            except (ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
                raise ValueError(f"'{text}': {node.func.id}({', '.join(f'{a:g}' for a in args)})"
                                 f" cannot be worked out ({e})") from None
        raise ValueError(f"'{text}' holds a piece a formula cannot ({type(node).__name__})")

    r = walk(tree.body)
    if r != r or r in (float("inf"), float("-inf")):
        raise ValueError(f"'{text}' has no finite value")
    if abs(r) > MAX_VALUE:
        raise ValueError(f"'{text}' comes to {r:.3g} — too large to be a dimension")
    return float(r)


def is_expression(v) -> bool:
    """A feature parameter holding a FORMULA rather than a number: text that
    parses. ("all", "top" and other words stay what they are — a bare name is
    a formula only if it is a parameter, which `evaluate` decides.)"""
    if not isinstance(v, str) or isinstance(v, bool):
        return False
    try:
        parse(v)
        return True
    except ValueError:
        return False


def rename_in(expr: str, old: str, new: str) -> str:
    """`old` -> `new` wherever it is a whole NAME token of the expression —
    the text and its spacing are otherwise untouched, and `wall` inside
    `wall_2` is not a match."""
    if not isinstance(expr, str) or "\n" in expr or "\r" in expr:
        return expr                    # a formula is one line (parse() refuses the rest)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(expr).readline))
    except (tokenize.TokenError, SyntaxError):
        return expr
    # splice by COLUMN, from the end, so earlier columns stay valid; only the
    # NAME tokens on the one line matter (INDENT / NEWLINE / ENDMARKER are
    # bookkeeping tokens with their own rows and are not touched)
    hits = [(t.start[1], t.end[1]) for t in toks
            if t.type == tokenize.NAME and t.string == old and t.start[0] == 1]
    out = expr
    for c0, c1 in reversed(hits):
        out = out[:c0] + new + out[c1:]
    return out
