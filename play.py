"""
play.py — free exploration. Type a prompt, get a part in the OCP viewer.

No spec is used here, so the model builds purely from your words (Layer 1 still
guarantees valid geometry; Layer 2 shape-checking is off for free play).

Two ways to use it:
  1) Edit PROMPT below, then run:   python play.py
  2) Pass the prompt on the command line:
       python play.py "a washer 40mm outer, 20mm inner hole, 4mm thick"
"""

import sys
from generate import text_to_cad

# Change this line to whatever you want to build, then run `python play.py`
PROMPT = "a hexagonal plate 50mm across, 8mm thick, with a 15mm center hole"


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or PROMPT
    print(f"PROMPT: {prompt}\n")
    # no spec -> builds from your words only, then auto-shows in the OCP viewer
    text_to_cad(prompt)
