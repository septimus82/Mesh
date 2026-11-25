"""S1-0 part B section 2: which Studio-offered behaviours does any test drive through a REAL GameWindow?

Static and approximate (no engine import): a test file counts as "real runtime" when it constructs a GameWindow or
uses one of the repo's real-window entry points (tests/_game_window_live.py, tests/_b01_arena.py, launch_editor,
public_api run_game, the trace/perf/release-check commands). A behaviour counts as covered there when its registry
name appears in that file as a string or identifier. A file that mentions a behaviour is not proof that it drives it,
so a 0 is the useful signal: no real-window test even names the behaviour.

Prints one row per behaviour in engine/behaviour_guide.GUIDES (the picker's catalogue) plus the advanced ones Studio
or the shipped content reach. Always exits 0.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REAL = re.compile(r"GameWindow\(|_game_window_live|_b01_arena|launch_editor\(|run_game\(|perf_command|trace_command|"
                  r"release_check_pipeline|_run_owned_editor")


def catalogue() -> list[str]:
    tree = ast.parse((REPO / "engine" / "behaviour_guide.py").read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "GUIDES":
            names = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]  # type: ignore[union-attr]
    return names + ["ActionListRunner", "IncrementCounterOnEvent", "QuestProgressOnEvent", "QuestHook", "SceneExit",
                    "EmitEventOnEvent", "ListenForEvent", "MessageOnZoneEnter"]


def main() -> None:
    files = {p: p.read_text(encoding="utf-8", errors="replace") for p in (REPO / "tests").rglob("*.py")}
    real = {p for p, s in files.items() if REAL.search(s)}
    print(f"test files: {len(files)}; real-window test files: {len(real)}\n")
    print(f"{'behaviour':26} {'tests naming it':>15} {'real-window tests naming it':>28}")
    for name in catalogue():
        pat = re.compile(rf"\b{re.escape(name)}\b")
        hits = [p for p, s in files.items() if pat.search(s)]
        real_hits = [p for p in hits if p in real]
        example = real_hits[0].relative_to(REPO).as_posix() if real_hits else ""
        print(f"{name:26} {len(hits):>15} {len(real_hits):>28}  {example}")


if __name__ == "__main__":
    main()
