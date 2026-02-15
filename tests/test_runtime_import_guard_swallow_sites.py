from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_FILES_TO_CHECK = (
    Path("engine/swallowed_exceptions.py"),
    Path("engine/game_runtime/tick.py"),
    Path("engine/scene_controller.py"),
    Path("engine/lighting/shadows.py"),
)

_FORBIDDEN_EXACT = {"arcade"}
_FORBIDDEN_PREFIXES = (
    "engine.editor.editor_",
    "engine.ui_overlays",
    "editor.editor_",
    "ui_overlays",
)
_ALLOWED_EXACT = {
    # Used for editor ghosting visual polish path; keep explicit.
    "engine.editor.editor_sprite_ghosting",
}


def _collect_import_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def test_swallow_site_modules_do_not_import_arcade_or_editor_ui_modules() -> None:
    violations: list[str] = []
    for rel_path in _FILES_TO_CHECK:
        modules = sorted(_collect_import_modules(rel_path))
        for module in modules:
            if module in _ALLOWED_EXACT:
                continue
            if module in _FORBIDDEN_EXACT or any(module.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
                violations.append(f"{rel_path.as_posix()}: {module}")
    unique_violations = sorted(set(violations))
    assert not unique_violations, "Forbidden imports detected:\n" + "\n".join(unique_violations)
