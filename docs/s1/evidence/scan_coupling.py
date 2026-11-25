"""S1-0 part B section 4: module size, import fan-in / fan-out, and change coupling (static; one process, git only).

* size: lines per module under engine/, mesh_net/, mesh_cli/;
* fan-out: distinct first-party modules a module imports (module level and inside functions);
  fan-in: distinct first-party modules that import it;
* change coupling: over the last N commits (default 300) of the current branch, how often two production files
  change in the same commit (merge commits skipped; commits touching more than 40 production files skipped as
  sweeping refactors). Reported: the top file pairs, and the files that co-change with the most distinct partners.

Usage: py -3.13 docs/s1/evidence/scan_coupling.py [N]. Always exits 0.
"""

from __future__ import annotations

import ast
import itertools
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOTS = ("engine", "mesh_net", "mesh_cli")


def modules() -> dict[str, Path]:
    out = {}
    for root in ROOTS:
        for p in (REPO / root).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(REPO).with_suffix("")
            name = ".".join(rel.parts[:-1] if rel.name == "__init__" else rel.parts)
            out[name] = p
    return out


def imports(mods: dict[str, Path]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for name, path in mods.items():
        pkg = name if path.name == "__init__.py" else name.rpartition(".")[0]
        deps: set[str] = set()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = pkg.split(".")
                    parts = parts[: len(parts) - (node.level - 1)]
                    base = ".".join(parts + ([base] if base else []))
                targets = [base] + [f"{base}.{a.name}" for a in node.names]
            for t in targets:
                while t and t not in mods:
                    t = t.rpartition(".")[0]
                if t and t != name:
                    deps.add(t)
        graph[name] = deps
    return graph


def co_change(n: int) -> tuple[Counter, dict[str, set[str]], Counter]:
    log = subprocess.run(["git", "-C", str(REPO), "log", f"-{n}", "--no-merges", "--format=@@%h", "--name-only"],
                         capture_output=True, text=True, check=True).stdout
    pairs: Counter = Counter()
    partners: dict[str, set[str]] = defaultdict(set)
    touches: Counter = Counter()
    for chunk in log.split("@@")[1:]:
        files = sorted({f for f in chunk.splitlines()[1:] if f.endswith(".py") and f.split("/")[0] in ROOTS})
        if not files or len(files) > 40:
            continue
        touches.update(files)
        for a, b in itertools.combinations(files, 2):
            pairs[(a, b)] += 1
            partners[a].add(b)
            partners[b].add(a)
    return pairs, partners, touches


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    mods = modules()
    graph = imports(mods)
    fan_in: Counter = Counter()
    for deps in graph.values():
        fan_in.update(deps)
    sizes = {m: sum(1 for _ in p.open(encoding="utf-8-sig", errors="replace")) for m, p in mods.items()}
    print(f"{len(mods)} production modules, {sum(sizes.values())} lines\n")
    print("largest modules (lines, fan-in, fan-out):")
    for m, lines in sorted(sizes.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {lines:6}  in={fan_in[m]:4}  out={len(graph.get(m, ())):3}  {m}")
    print("\nhighest fan-in (imported by most modules):")
    for m, c in fan_in.most_common(15):
        print(f"  in={c:4}  out={len(graph.get(m, ())):3}  lines={sizes.get(m, 0):6}  {m}")
    print("\nhighest fan-out:")
    for m in sorted(graph, key=lambda k: -len(graph[k]))[:12]:
        print(f"  out={len(graph[m]):3}  in={fan_in[m]:4}  lines={sizes[m]:6}  {m}")
    pairs, partners, touches = co_change(n)
    print(f"\nchange coupling over the last {n} non-merge commits:")
    print("most-changed production files:")
    for f, c in touches.most_common(15):
        print(f"  {c:3} commits  {len(partners[f]):4} distinct co-changed files  {f}")
    print("most frequent co-changing pairs (both files in the same commit):")
    for (a, b), c in pairs.most_common(20):
        print(f"  {c:3}  {a}  +  {b}")


if __name__ == "__main__":
    main()
