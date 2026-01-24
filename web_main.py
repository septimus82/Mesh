"""Web entry point for Mesh Engine (Pygbag/WebAssembly)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Protocol, cast

from engine.config import EngineConfig


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def configure_web_runtime() -> None:
    """Apply lightweight path fixes for web builds."""
    if not _is_web_runtime():
        return
    if not os.environ.get("MESH_REPO_ROOT"):
        os.environ["MESH_REPO_ROOT"] = "."
    try:
        from engine import paths

        paths.reset_path_caches()
        paths.set_content_roots([Path(".")])
    except Exception:  # noqa: BLE001
        return


def _load_game_window():
    from engine.game import GameWindow  # noqa: PLC0415

    return GameWindow


class _WindowProto(Protocol):
    world_controller: Any | None
    game_state_controller: Any

    def set_next_spawn_point(self, spawn_id: str | None) -> None: ...
    def load_scene(self, scene_path: str) -> Dict[str, Any]: ...
    def run(self) -> None: ...


def create_window(*, config: EngineConfig, config_path: str) -> _WindowProto:
    GameWindow = _load_game_window()
    return cast(
        _WindowProto,
        GameWindow(
            width=config.width,
            height=config.height,
            title=config.title,
            fullscreen=config.fullscreen,
            vsync=config.vsync,
            config=config,
            config_path=config_path,
        ),
    )


def _resolve_initial_scene(window: _WindowProto, config: EngineConfig) -> tuple[str, str | None]:
    initial_scene = config.main_menu_scene if config.main_menu_scene else config.start_scene
    spawn_id = None
    wc = getattr(window, "world_controller", None)
    if wc is not None:
        start_key = wc.get_start_scene_key()
        path = wc.get_scene_path(start_key) if start_key else None
        if path:
            initial_scene = path
            spawn_id = wc.get_start_spawn()
            window.game_state_controller.set_var("world_id", wc.id)
            window.game_state_controller.set_var("world_scene_key", start_key)
            if spawn_id:
                window.set_next_spawn_point(spawn_id)
    return initial_scene, spawn_id


def main() -> None:
    configure_web_runtime()
    from engine.config import load_config  # noqa: PLC0415

    config = load_config()
    window = create_window(config=config, config_path="config.json")

    initial_scene, _ = _resolve_initial_scene(window, config)
    scene_data: Dict[str, Any] = window.load_scene(initial_scene)
    _ = scene_data
    window.run()


if __name__ == "__main__":
    main()
