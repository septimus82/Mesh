"""S1-0 part C section 3: does mypy-island fail closed when mypy can't run? (#633 fixed ruff-gate and mypy-gate only)

    py -3.13 docs/s1/evidence/probe_gate_fail_open.py      (PYTHONPATH = the repository root)

``tooling.mypy_island.main`` runs with its subprocess replaced by what a Python without mypy prints
(``No module named mypy``, exit 1). The real gate code runs. Exit 1 when the gate passes although it checked nothing.
The other gate findings in the report are from code reading (line numbers given there).
"""

from __future__ import annotations

import subprocess

import engine
from tooling import mypy_island

print(f"engine from {engine.__file__}")

real_run = subprocess.run


def no_mypy(cmd, *args, **kwargs):  # what `python -m mypy` gives on an interpreter without mypy
    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="/usr/bin/python: No module named mypy\n")


mypy_island.subprocess.run = no_mypy
try:
    code = mypy_island.main([])
finally:
    mypy_island.subprocess.run = real_run
print(f"A) mypy-island with mypy missing: exit {code}")

bad = code == 0
if bad:
    print("DEFECT REPRODUCED: mypy-island reports ok when mypy could not run (its return code is never read)")
raise SystemExit(1 if bad else 0)
