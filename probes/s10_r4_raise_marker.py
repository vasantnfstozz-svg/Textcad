"""Round FOUR, attack on round three's `blocks._python_raised_it`.

The marker says a ValueError is OURS when the innermost traceback frame lives
in this directory AND the instruction at its `tb_lasti` is `RAISE_VARARGS` or
`RERAISE`. Round three measured 24 of our own refusals: 24 correct, 0 misread.

The dangerous direction is a refusal OF OURS that the marker calls Python's,
because the user then loses a sentence they could have acted on. This probe
hunts one, over every shape a `raise` can take in Python 3.14 — a raise inside
a comprehension, a re-raise, one from a decorator, a context manager, a
generator, a property, a dataclass, a helper that builds the exception first,
one crossing the kernel-worker boundary, and one raised from exec'd code.

Run: C:\\Python314\\python.exe probes/s10_r4_raise_marker.py
"""
import contextlib
import dis
import functools
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blocks                                                      # noqa: E402

print("python", sys.version)
print("_OUR_DIR:", blocks._OUR_DIR)
print("_RAISE_OPS:", blocks._RAISE_OPS)
_REAL_DIR = blocks._OUR_DIR
print()

SENTENCE = "plate: width must be a number in mm (got None) — type just the number"


def marker(e):
    """(is_python_by_the_marker, innermost file, opname at tb_lasti)"""
    tb = e.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    op, fn = "?", "?"
    if tb is not None:
        code = tb.tb_frame.f_code
        fn = os.path.basename(code.co_filename)
        for ins in dis.get_instructions(code):
            if ins.offset == tb.tb_lasti:
                op = ins.opname
                break
    return blocks._python_raised_it(e), fn, op


def show(label, fn, expect_ours=True):
    try:
        fn()
    except ValueError as e:
        is_py, f, op = marker(e)
        out = blocks.plain_cause(e)
        swallowed = out == blocks.NOT_A_SENTENCE
        verdict = "OK " if swallowed != expect_ours else "*** MISREAD ***"
        print(f"{verdict} {label:<46} {f:<18}{op:<20}"
              f"{'python' if is_py else 'ours'}")
        if swallowed and expect_ours:
            print(f"        the sentence LOST: {e}")
        return
    print(f"     {label:<46} did not raise")


# --- the shapes a `raise` of ours can take ----------------------------------
# The synthetic battery below lives in probes/, one directory DOWN from the
# modules the marker trusts, so the FILE test alone would answer every row and
# measure nothing. Point the marker at this file's own directory: the only
# thing under test here is the BYTECODE half.
blocks._OUR_DIR = os.path.dirname(os.path.abspath(__file__))

print("EXPECT 'ours' (a refusal we wrote — must never be swallowed)")
print("-" * 100)


def plain():
    raise ValueError(SENTENCE)


def from_none():
    try:
        float("")
    except ValueError:
        raise ValueError(SENTENCE) from None


def from_e():
    try:
        float("")
    except ValueError as e:
        raise ValueError(SENTENCE) from e


def bare_reraise():
    try:
        raise ValueError(SENTENCE)
    except ValueError:
        raise


def built_then_raised():
    err = ValueError(SENTENCE)
    raise err


def through_finally():
    try:
        raise ValueError(SENTENCE)
    finally:
        pass


def through_with():
    with contextlib.suppress(TypeError):
        raise ValueError(SENTENCE)


def in_a_comprehension():
    def bad(x):
        raise ValueError(SENTENCE)
    return [bad(x) for x in (1,)]


def in_a_genexp():
    def bad(x):
        raise ValueError(SENTENCE)
    return list(bad(x) for x in (1,))


def in_a_generator():
    def gen():
        yield 1
        raise ValueError(SENTENCE)
    g = gen()
    next(g)
    next(g)


def thrown_into_a_generator():
    def gen():
        try:
            yield 1
        except ValueError:
            raise ValueError(SENTENCE) from None
    g = gen()
    next(g)
    g.throw(ValueError("x"))


def in_a_property():
    class C:
        @property
        def v(self):
            raise ValueError(SENTENCE)
    return C().v


def in_a_dataclass():
    @dataclass
    class C:
        x: int = 0

        def __post_init__(self):
            raise ValueError(SENTENCE)
    return C()


def deco(fn):
    @functools.wraps(fn)
    def inner(*a, **k):
        raise ValueError(SENTENCE)
    return inner


@deco
def decorated():
    pass


def in_a_context_manager_exit():
    class CM:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            raise ValueError(SENTENCE)
    with CM():
        pass


@contextlib.contextmanager
def cm():
    yield


def in_a_contextlib_cm():
    with cm():
        raise ValueError(SENTENCE)


def in_a_lambda_default():
    f = (lambda: (_ for _ in ()).throw(ValueError(SENTENCE)))
    return f()


def in_an_except_star():
    try:
        raise ExceptionGroup("g", [TypeError("t")])
    except* TypeError:
        raise ValueError(SENTENCE) from None


def in_a_match():
    v = 3
    match v:
        case 3:
            raise ValueError(SENTENCE)


for label, fn in [
    ("a plain raise", plain),
    ("raise ... from None", from_none),
    ("raise ... from e", from_e),
    ("a bare re-raise", bare_reraise),
    ("the exception built first, then raised", built_then_raised),
    ("a raise through a finally", through_finally),
    ("a raise inside a with", through_with),
    ("a helper called from a list comprehension", in_a_comprehension),
    ("a helper called from a generator expression", in_a_genexp),
    ("a raise inside a generator", in_a_generator),
    ("a raise from generator.throw()", thrown_into_a_generator),
    ("a raise inside a property", in_a_property),
    ("a raise inside __post_init__", in_a_dataclass),
    ("a raise inside a decorator's wrapper", decorated),
    ("a raise inside a context manager's __exit__", in_a_context_manager_exit),
    ("a raise inside a @contextmanager body", in_a_contextlib_cm),
    ("a genexp .throw() inside a lambda", in_a_lambda_default),
    ("a raise inside except*", in_an_except_star),
    ("a raise inside match/case", in_a_match),
]:
    show(label, fn, expect_ours=True)

# --- our real refusals, from the real modules --------------------------------
print()
print("the real refusals, called for real")
print("-" * 100)
blocks._OUR_DIR = _REAL_DIR                       # the real modules again
import document                                                    # noqa: E402
import paramexpr                                                   # noqa: E402
import pattern                                                     # noqa: E402
import sketch as sk                                                # noqa: E402

REAL = [
    ("blocks._positive", lambda: blocks._positive("plate", width=None)),
    ("blocks._numbers", lambda: blocks._numbers("scale", "times", factor=None)),
    ("blocks._pick_point", lambda: blocks._pick_point("abc", "face_center")),
    ("blocks.rotate axis", lambda: blocks.rotate(None, axis=[1])),
    ("blocks.revolve_profile", lambda: blocks.revolve_profile("abc")),
    ("blocks.curved_blade", lambda: blocks.curved_blade(None, 2, 3, 4, 5, 6)),
    ("document._params_dict", lambda: document._params_dict("plate", [1], "a")),
    ("document._check_numeric_params",
     lambda: document._check_numeric_params("extrude", {"amount": None}, "a")),
    ("document.add unknown op", lambda: document.Document(name="n").add("a", "nope")),
    ("paramexpr.evaluate", lambda: paramexpr.evaluate("1/0", {})),
    ("pattern.polar_angles", lambda: pattern.polar_pattern(None, 0)),
    ("sketch.compose", lambda: sk.compose([{"kind": "nope"}])),
]
for label, fn in REAL:
    show(label, fn, expect_ours=True)

# --- the other direction: PYTHON's own, from inside our own lines ------------
print()
blocks._OUR_DIR = os.path.dirname(os.path.abspath(__file__))   # this file again
print("EXPECT 'python' (a Python fact — must be replaced)")
print("-" * 100)


def our_float():
    return float("")


def our_unpack():
    a, b, c = [1, 2]
    return a, b, c


def our_list_remove():
    [1].remove(2)


def our_int():
    return int("x")


for label, fn in [("float('') in our line", our_float),
                  ("unpacking a pair into three", our_unpack),
                  ("list.remove of what is not there", our_list_remove),
                  ("int('x')", our_int)]:
    show(label, fn, expect_ours=False)

# --- exec'd code: co_filename '<string>' resolves against the CWD -----------
print()
print("exec'd code, whose co_filename is '<string>'")
print("-" * 100)
print("cwd == our dir:", os.path.abspath(os.getcwd()) == blocks._OUR_DIR)
ns: dict = {}
exec(compile("def boom():\n    raise ValueError('a sentence from exec')\n",
             "<string>", "exec"), ns)
show("a raise in exec'd code", ns["boom"], expect_ours=True)
ns2: dict = {}
exec(compile("def boom2():\n    return float('')\n", "<string>", "exec"), ns2)
show("float('') in exec'd code", ns2["boom2"], expect_ours=False)
