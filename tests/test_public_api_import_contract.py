from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE_MAIN = _REPO_ROOT / "examples" / "template_game" / "main.py"
_BASELINE = _REPO_ROOT / "tests" / "baselines" / "public_api_exports.txt"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                modules.append(node.module)
    return modules


def _is_stdlib_module(module_name: str) -> bool:
    root = module_name.split(".", 1)[0]
    stdlib_names = getattr(sys, "stdlib_module_names", set())
    return root in stdlib_names or root in {"__future__"}


def _public_export_lines() -> list[str]:
    runtime = importlib.import_module("engine.public_api.runtime")
    assets = importlib.import_module("engine.public_api.assets")
    types_mod = importlib.import_module("engine.public_api.types")
    version_mod = importlib.import_module("engine.public_api.version")
    root = importlib.import_module("engine.public_api")

    lines: list[str] = []
    for module_name, module_obj in (
        ("runtime", runtime),
        ("assets", assets),
        ("types", types_mod),
        ("version", version_mod),
        ("__init__", root),
    ):
        exports = getattr(module_obj, "__all__", [])
        for name in sorted(str(item) for item in exports):
            lines.append(f"{module_name}:{name}")
    return lines


def test_template_game_imports_only_public_api_and_stdlib() -> None:
    modules = _imported_modules(_TEMPLATE_MAIN)
    for module_name in modules:
        if module_name.startswith("engine.public_api"):
            continue
        assert _is_stdlib_module(module_name), f"unexpected import in template_game: {module_name}"


def test_public_api_runtime_and_assets_do_not_import_editor_modules() -> None:
    for rel_path in ("engine/public_api/runtime.py", "engine/public_api/assets.py"):
        modules = _imported_modules(_REPO_ROOT / rel_path)
        for module_name in modules:
            assert not module_name.startswith("engine.editor"), f"{rel_path} imports editor module: {module_name}"
            assert not module_name.startswith("engine.editor_"), f"{rel_path} imports editor module: {module_name}"


def test_public_api_export_set_matches_baseline() -> None:
    expected = [line.strip() for line in _BASELINE.read_text(encoding="utf-8").splitlines() if line.strip()]
    actual = _public_export_lines()
    assert actual == expected
