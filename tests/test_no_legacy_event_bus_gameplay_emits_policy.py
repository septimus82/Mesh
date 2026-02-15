from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CATALOG_PATH = ROOT / "assets" / "data" / "events.json"
KNOWN_EVENT_CONSTANT_MODULES = {"engine.combat_constants", "engine.constants"}

# Legacy emit sites intentionally tolerated for compatibility-only paths.
LEGACY_EVENT_BUS_EMIT_ALLOWLIST: dict[str, str] = {
    "engine/behaviours/pickup_collectible.py:108": "legacy collectible bridge",
    "engine/tooling/replay_goldens_command.py:51": "legacy tooling replay bridge",
    "tooling/campaign_replay.py:231": "legacy SceneExit bridge in campaign tooling",
    "tooling/campaign_replay.py:233": "legacy SceneExit bridge in campaign tooling",
}

# Existing MeshEventBus imports tolerated only in legacy gameplay/bridge modules.
MESH_EVENT_BUS_IMPORT_ALLOWLIST: dict[str, str] = {
    "engine/behaviours/cutscene_trigger.py:7": "legacy trigger wiring",
    "engine/behaviours/grant_experience.py:7": "legacy experience wiring",
    "engine/behaviours/quest_giver.py:5": "legacy quest giver integration",
    "engine/behaviours/scene_exit.py:5": "legacy scene exit integration",
    "engine/behaviours/time_of_day_gate.py:5": "legacy day/night integration",
    "engine/behaviours/toggle_scene_lights.py:7": "legacy lighting integration",
    "engine/behaviours/vendor.py:6": "legacy vendor integration",
    "engine/game.py:101": "core engine legacy bus owner",
    "engine/tooling/trace_command.py:8": "legacy tracing harness",
    "tooling/campaign_replay.py:17": "legacy replay harness bridge",
}


def _iter_scoped_files() -> list[Path]:
    files: set[Path] = set()
    files.update((ROOT / "engine").rglob("*.py"))
    files.add(ROOT / "mesh_cli" / "episode.py")
    files.add(ROOT / "tooling" / "campaign_replay.py")
    return sorted(path for path in files if path.exists())


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _resolve_import_module(path: Path, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level <= 0:
        return module

    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if len(parts) < node.level:
        return module
    base = parts[: len(parts) - node.level]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _load_cataloged_event_types() -> set[str]:
    payload = json.loads(EVENTS_CATALOG_PATH.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    result: set[str] = set()
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                name = event.get("name")
                if isinstance(name, str) and name.strip():
                    result.add(name.strip())
    return result


def _imported_constant_map(path: Path, tree: ast.AST) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str):
                        constants[target.id] = node.value.value
        if not isinstance(node, ast.ImportFrom):
            continue
        module_name = _resolve_import_module(path, node)
        if module_name not in KNOWN_EVENT_CONSTANT_MODULES:
            continue
        module = importlib.import_module(module_name)
        for alias in node.names:
            name = alias.name
            as_name = alias.asname or name
            value = getattr(module, name, None)
            if isinstance(value, str):
                constants[as_name] = value
    return constants


def _is_legacy_event_bus_target(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id in {"event_bus", "_event_bus", "MeshEventBus"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"event_bus", "_event_bus"}
    return False


def _expr_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_expr_name(node.value)}.{node.attr}"
    return type(node).__name__


def _resolve_event_type_expr(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "MeshEvent" and node.args:
            return _resolve_event_type_expr(node.args[0], constants)
        if isinstance(func, ast.Attribute) and func.attr == "MeshEvent" and node.args:
            return _resolve_event_type_expr(node.args[0], constants)
    return None


def _find_legacy_emit_tokens(path: Path, tree: ast.AST) -> list[tuple[str, str | None, str]]:
    rel_path = _rel(path)
    constants = _imported_constant_map(path, tree)
    tokens: list[tuple[str, str | None, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in {"emit", "publish"}:
            continue
        if not _is_legacy_event_bus_target(func.value):
            continue
        event_type: str | None = None
        if node.args:
            event_type = _resolve_event_type_expr(node.args[0], constants)
        call_form = f"{_expr_name(func.value)}.{func.attr}"
        tokens.append((f"{rel_path}:{node.lineno}", event_type, call_form))
    return tokens


def _find_mesh_event_bus_import_tokens(path: Path, tree: ast.AST) -> list[str]:
    rel_path = _rel(path)
    tokens: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        resolved = _resolve_import_module(path, node)
        if resolved != "engine.events":
            continue
        for alias in node.names:
            if alias.name == "MeshEventBus":
                tokens.append(f"{rel_path}:{node.lineno}")
    return tokens


def test_no_new_legacy_event_bus_emits_in_gameplay_scopes() -> None:
    catalog = _load_cataloged_event_types()
    violations: list[str] = []
    for path in _iter_scoped_files():
        tree = ast.parse(_read_source(path), filename=_rel(path))
        for token, event_type, call_form in _find_legacy_emit_tokens(path, tree):
            if event_type is not None and event_type in catalog:
                violations.append(
                    f"{token} [{call_form}] event_type={event_type} (cataloged gameplay event)"
                )
                continue
            if token not in LEGACY_EVENT_BUS_EMIT_ALLOWLIST:
                violations.append(
                    f"{token} [{call_form}] event_type={event_type or '<dynamic>'}"
                )
    assert not sorted(violations), (
        "Gameplay emit policy violation. Cataloged gameplay events must be emitted via "
        "engine.event_emit.emit_gameplay_event(...). For legacy non-catalog emits, add an explicit "
        f"allowlist rationale if unavoidable. Unexpected legacy emit sites: {sorted(violations)}"
    )


def test_no_new_mesh_event_bus_imports_in_gameplay_scopes() -> None:
    violations: list[str] = []
    for path in _iter_scoped_files():
        tree = ast.parse(_read_source(path), filename=_rel(path))
        for token in _find_mesh_event_bus_import_tokens(path, tree):
            if token not in MESH_EVENT_BUS_IMPORT_ALLOWLIST:
                violations.append(token)
    assert not sorted(violations), (
        "Gameplay import policy violation. New gameplay modules must route via GameplayEventBus/"
        "engine.event_emit instead of importing MeshEventBus directly. "
        f"Unexpected imports: {sorted(violations)}"
    )


def test_policy_detector_catches_synthetic_legacy_emit_violation() -> None:
    source = (
        "from engine.combat_constants import EVENT_COMBAT_ATTACK\n"
        "class Demo:\n"
        "    def run(self):\n"
        "        self.window.event_bus.emit(EVENT_COMBAT_ATTACK, value=1)\n"
    )
    path = ROOT / "synthetic_policy_sample.py"
    tree = ast.parse(source, filename="synthetic_policy_sample.py")
    tokens = _find_legacy_emit_tokens(path, tree)
    assert tokens == [
        ("synthetic_policy_sample.py:4", "combat_attack", "self.window.event_bus.emit")
    ], "Synthetic legacy emit violation was not detected; policy scanner is broken."
