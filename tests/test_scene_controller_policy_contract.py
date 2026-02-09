from __future__ import annotations

import ast
from pathlib import Path

MAX_SCENE_CONTROLLER_LINES = 2419
MAX_METHOD_LINES = {
    "load_scene": 20,
    "reload_scene": 20,
    "request_scene_change": 30,
    "queue_scene_change": 30,
    "update": 40,
    "get_nav_grid": 12,
}


def _get_scene_controller_class(source: str) -> ast.ClassDef:
    mod = ast.parse(source)
    for node in mod.body:
        if isinstance(node, ast.ClassDef) and node.name == "SceneController":
            return node
    raise AssertionError("SceneController class not found")


def test_scene_controller_line_count_ratcheted() -> None:
    path = Path("engine/scene_controller.py")
    source = path.read_text(encoding="utf-8")
    line_count = len(source.splitlines())
    assert line_count <= MAX_SCENE_CONTROLLER_LINES, (
        f"scene_controller.py grew: {line_count} lines (max {MAX_SCENE_CONTROLLER_LINES})"
    )


def test_scene_controller_lifecycle_methods_not_megafunctions() -> None:
    path = Path("engine/scene_controller.py")
    source = path.read_text(encoding="utf-8")
    cls = _get_scene_controller_class(source)
    for fn in cls.body:
        if isinstance(fn, ast.FunctionDef) and fn.name in MAX_METHOD_LINES:
            start = fn.lineno
            end = fn.end_lineno or fn.lineno
            line_count = end - start + 1
            limit = MAX_METHOD_LINES[fn.name]
            assert (
                line_count <= limit
            ), f"{fn.name} too large: {line_count} lines (max {limit})"


def test_scene_controller_nav_helpers_not_reintroduced() -> None:
    path = Path("engine/scene_controller.py")
    source = path.read_text(encoding="utf-8")
    assert "NavGridCache" not in source
    assert "build_nav_grid_from_tilemap_instance" not in source


def test_scene_controller_update_is_delegated() -> None:
    path = Path("engine/scene_controller.py")
    source = path.read_text(encoding="utf-8")
    assert "handle_pending_scene" not in source


def test_scene_controller_entity_store_delegation_present() -> None:
    path = Path("engine/scene_controller.py")
    source = path.read_text(encoding="utf-8")
    assert "SceneEntityStoreController" in source
    # Check that scene_controller doesn't have its own _pending_ops attribute
    # but can call apply_pending_ops on the entities store
    assert "self._pending_ops" not in source
