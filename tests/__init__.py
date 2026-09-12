# Makes tests/ a package so a fast-tier file and a tests/e2e/ file may share a
# basename (pytest 9 prepend mode refuses duplicate rootless module names,
# which is what kept `pytest -m library` from collecting - LAUNCH-PLAN P5b).
