from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROD_ROOTS = (ROOT / "engine", ROOT / "mesh_cli", ROOT / "tooling")

GETLOGGER_ALLOWLIST = {
    "engine/behaviour_event_router.py",
    "engine/camera_controller.py",
    "engine/content_audit.py",
    "engine/editor/editor_align_controller.py",
    "engine/editor/editor_command_dispatch_controller.py",
    "engine/editor/editor_dock_controller.py",
    "engine/editor/editor_entity_panels_controller.py",
    "engine/editor/editor_hierarchy_controller.py",
    "engine/input_controller.py",
    "engine/json_io.py",
    "engine/log_utils.py",
    "engine/logging_tools.py",
    "engine/palette_mode.py",
    "engine/prefabs.py",
    "engine/lighting/shadows.py",
    "engine/scene_controller.py",
    "engine/scene_runtime/transitions.py",
    "engine/scene_runtime/persistence.py",
    "engine/tooling_runtime/doctor_assets_registry.py",
    "engine/ui.py",
    "engine/ui_overlays/common.py",
    "engine/ui_overlays/menus.py",
    "engine/workspace_settings.py",
    "tooling/web_preview.py",
}

WARNED_ONCE_ALLOWLIST = {
    "engine/content_audit.py:_MESH_AUDIT_LOGGED_ONCE",
    "engine/content_lock.py:_MESH_LOCK_LOGGED_ONCE",
}


def _iter_prod_files() -> list[Path]:
    out: list[Path] = []
    for base in PROD_ROOTS:
        out.extend(sorted(base.rglob("*.py")))
    return out


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_no_new_bare_logging_getlogger_outside_allowlist() -> None:
    violations: list[str] = []
    for path in _iter_prod_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        tree = ast.parse(_read_source(path), filename=rel)

        logging_aliases = {"logging"}
        direct_getlogger_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "logging":
                        logging_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module == "logging":
                for alias in node.names:
                    if alias.name == "getLogger":
                        direct_getlogger_aliases.add(alias.asname or alias.name)

        uses_bare_getlogger = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in direct_getlogger_aliases:
                uses_bare_getlogger = True
                break
            if (
                isinstance(fn, ast.Attribute)
                and fn.attr == "getLogger"
                and isinstance(fn.value, ast.Name)
                and fn.value.id in logging_aliases
            ):
                uses_bare_getlogger = True
                break
        if uses_bare_getlogger and rel not in GETLOGGER_ALLOWLIST:
            violations.append(rel)

    assert not violations, (
        "Use engine.log_utils.get_logger() (or logging_tools.get_logger()) instead of bare logging.getLogger(). "
        f"New offenders: {violations}"
    )


def test_no_new_module_level_warned_once_sets() -> None:
    violations: list[str] = []
    for path in _iter_prod_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        tree = ast.parse(_read_source(path), filename=rel)
        for node in tree.body:
            targets: list[str] = []
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        targets.append(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets.append(node.target.id)
            for name in targets:
                lowered = name.lower()
                if "warned_once" in lowered or "logged_once" in lowered:
                    token = f"{rel}:{name}"
                    if token not in WARNED_ONCE_ALLOWLIST:
                        violations.append(token)
    assert not violations, (
        "Use engine.log_utils.log_once() instead of new module-level *_warned_once/*_logged_once sets. "
        f"Offenders: {violations}"
    )

