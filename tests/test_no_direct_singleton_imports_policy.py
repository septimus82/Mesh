from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROD_ROOTS = (ROOT / "engine", ROOT / "mesh_cli")
SINGLETON_IMPORT_ALLOWLIST = {
    "engine/singletons.py",
}
TRACKED_SINGLETON_ASSIGN_ALLOWLIST = {
    "engine/rng_service.py:rng_service",
    "engine/encounter_sets.py:_THEME_MANAGER",
    "engine/action_runtime/registry.py:_ACTIONS",
    "engine/action_runtime/registry.py:_REQUIRED",
    "engine/behaviours/__init__.py:_BUILTINS_LOADED",
    "engine/editor_runtime/input.py:_shortcut_conflicts_warned",
    "engine/singletons.py:_REGISTRY",
}
TRACKED_SINGLETON_NAMES = {
    "rng_service",
    "_THEME_MANAGER",
    "_ACTIONS",
    "_REQUIRED",
    "_BUILTINS_LOADED",
    "_shortcut_conflicts_warned",
    "_REGISTRY",
}


def _iter_production_files() -> list[Path]:
    files: list[Path] = []
    for base in PROD_ROOTS:
        files.extend(sorted(base.rglob("*.py")))
    return files


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _resolve_import_module(path: Path, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level <= 0:
        return module

    rel = path.relative_to(ROOT)
    parts = list(rel.with_suffix("").parts)
    if len(parts) < node.level:
        return module

    base = parts[: len(parts) - node.level]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _module_level_targets(node: ast.stmt) -> list[str]:
    targets: list[str] = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                targets.append(target.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        targets.append(node.target.id)
    return targets


def test_no_direct_rng_singleton_imports_outside_registry() -> None:
    violations: list[str] = []
    for path in _iter_production_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in SINGLETON_IMPORT_ALLOWLIST:
            continue
        tree = ast.parse(_read_source(path), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                resolved = _resolve_import_module(path, node)
                if resolved != "engine.rng_service":
                    continue
                for alias in node.names:
                    if alias.name in {"rng_service", "get_rng"}:
                        violations.append(f"{rel}:{node.lineno} imports {alias.name} from engine.rng_service")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "engine.rng_service":
                        violations.append(f"{rel}:{node.lineno} imports engine.rng_service directly")
    assert not violations, (
        "Use engine.singletons.get_registry() for singleton RNG access; direct imports are forbidden: "
        f"{violations}"
    )


def test_no_new_tracked_singleton_assignments_outside_allowlist() -> None:
    violations: list[str] = []
    for path in _iter_production_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        tree = ast.parse(_read_source(path), filename=rel)
        for node in tree.body:
            for target in _module_level_targets(node):
                if target not in TRACKED_SINGLETON_NAMES:
                    continue
                token = f"{rel}:{target}"
                if token not in TRACKED_SINGLETON_ASSIGN_ALLOWLIST:
                    violations.append(f"{token} (line {getattr(node, 'lineno', '?')})")
    assert not violations, (
        "Tracked singleton globals must be centralized or explicitly allowlisted. "
        f"Unexpected assignments: {violations}"
    )
