"""The safe evaluator against an injection corpus: every line must be a
SENTENCE (ValueError), never run, never a Python traceback."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paramexpr as px  # noqa: E402

V = {"wall": 3.0, "base": 12.0}
GOOD = ["3", "2.5", "wall", "wall*2", "(wall+1)/2", "-wall", "base - wall*2", "2**3",
        "min(wall, base)", "max(1, wall) + abs(-2)", "round(wall/2)", "sqrt(16)",
        "sin(30)*2", "cos(60)", "floor(2.7) + ceil(2.1)", "1e3", "wall ** 2"]
BAD = ["__import__('os').system('dir')", "().__class__", "wall.__class__", "open('x')",
       "lambda: 1", "[1,2][0]", "{'a': 1}", "'abc'", "f'{wall}'", "wall if 1 else 2",
       "1 < 2", "1 and 2", "not 1", "10**10**10", "1e400", "1/0", "wall/0", "wal*2",
       "print(1)", "eval('1')", "exec('x=1')", "import os", "x = 1", "wall; 1", "1,2",
       "True", "None", "sqrt", "sqrt(-1)", "min()", "round(1, 2, 3)", "2 // 3", "7 % 2",
       "~1", "1 @ 2", "wall(2)", "a" * 300, "", "   ", "(-8) ** 0.5", "9e300 * 9e300",
       "2 ** 65", "1e12"]
for e in GOOD:
    print(f"OK   {e:28s} = {px.evaluate(e, V):g}")
bad_ran = 0
for e in BAD:
    try:
        v = px.evaluate(e, V)
        print(f"RAN  {e:28s} = {v!r}   <-- MUST NOT HAPPEN")
        bad_ran += 1
    except ValueError as err:
        print(f"REF  {e[:28]:28s} -> {str(err)[:90]}")
    except Exception as err:                       # noqa: BLE001
        print(f"LEAK {e[:28]:28s} -> {type(err).__name__}: {str(err)[:70]}   <-- NOT A SENTENCE")
        bad_ran += 1
print("bad that ran or leaked:", bad_ran)
print("names_in:", px.names_in("wall*2 + max(base, wall_2)"))
print("rename:", px.rename_in("wall*2 + wall_2 - (wall)", "wall", "thickness"))
print("is_expression:", [px.is_expression(x) for x in ("wall*2", "all", "top", "8mm", 3, "3")])
