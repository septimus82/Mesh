from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = REPO_ROOT / "engine"

# Escape hatch for rare, explicitly-approved imports from engine.tooling.
# Keep this minimal.
ALLOWED_TOOLING_IMPORTS: set[str] = set()


@dataclass(frozen=True)
class _Violation:
    file: str
    line: int
    col: int
    module: str
    message: str


def _is_excluded_engine_file(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if "tooling" in parts:
        return True
    if "tooling_runtime" in parts:
        return True
    if "validators" in parts:
        return True
    return False


def _check_module_import(file_rel: str, line: int, col: int, module: str) -> _Violation | None:
    mod = str(module or "")

    if mod == "mesh_cli" or mod.startswith("mesh_cli."):
        return _Violation(
            file=file_rel,
            line=line,
            col=col,
            module=mod,
            message="Runtime code must not import CLI module mesh_cli.",
        )

    if mod == "engine.tooling" or mod.startswith("engine.tooling."):
        if mod in ALLOWED_TOOLING_IMPORTS:
            return None
        return _Violation(
            file=file_rel,
            line=line,
            col=col,
            module=mod,
            message="Runtime code must not import engine.tooling.* (use engine.tooling_runtime or a neutral module).",
        )

    return None


def _check_relative_from_import(file_rel: str, line: int, col: int, module: str, level: int) -> _Violation | None:
    if level <= 0:
        return None
    mod = str(module or "")

    if mod == "tooling" or mod.startswith("tooling."):
        full = f"engine.{mod}"
        if full in ALLOWED_TOOLING_IMPORTS:
            return None
        return _Violation(
            file=file_rel,
            line=line,
            col=col,
            module=f".{mod}",
            message="Runtime code must not import from engine.tooling via relative import (use engine.tooling_runtime).",
        )

    return None


def test_engine_runtime_import_boundaries() -> None:
    violations: list[_Violation] = []

    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        if _is_excluded_engine_file(path):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError as exc:  # pragma: no cover
            violations.append(
                _Violation(
                    file=rel,
                    line=int(getattr(exc, "lineno", 1) or 1),
                    col=int(getattr(exc, "offset", 0) or 0),
                    module="<syntax>",
                    message=f"SyntaxError parsing file for import boundary check: {exc}",
                )
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    v = _check_module_import(rel, node.lineno, node.col_offset, alias.name)
                    if v is not None:
                        violations.append(v)
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    v = _check_module_import(rel, node.lineno, node.col_offset, node.module)
                    if v is not None:
                        violations.append(v)
                    v = _check_relative_from_import(rel, node.lineno, node.col_offset, node.module, int(node.level or 0))
                    if v is not None:
                        violations.append(v)

    violations.sort(key=lambda v: (v.file, v.line, v.col, v.module))
    if violations:
        rendered = "\n".join(
            f"{v.file}:{v.line}:{v.col} {v.module} -> {v.message}" for v in violations
        )
        raise AssertionError(f"Import boundary violations detected:\n{rendered}")

