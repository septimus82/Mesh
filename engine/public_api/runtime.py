from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def load_scene_payload(scene_path: str | Path) -> dict[str, Any]:
    """Load and return a resolved scene payload using the engine SceneLoader."""
    from engine.scene_loader import SceneLoader  # noqa: PLC0415

    loader = SceneLoader()
    return loader.load_scene(str(scene_path))


@contextmanager
def _temporary_repo_root_override(project_root: Path | None):
    """Internal helper to scope path resolution without process-wide cwd changes."""
    if project_root is None:
        yield
        return

    from engine.paths import reset_path_caches  # noqa: PLC0415

    key = "MESH_REPO_ROOT"
    previous = os.environ.get(key)
    had_key = key in os.environ

    os.environ[key] = str(project_root)
    reset_path_caches()
    try:
        yield
    finally:
        if had_key and previous is not None:
            os.environ[key] = previous
        else:
            os.environ.pop(key, None)
        reset_path_caches()


def run_game(
    main_scene_path: str | Path,
    *,
    project_root: Path | None = None,
) -> None:
    """Start the game window and load a specific initial scene.

    This is a thin public wrapper around the engine's canonical runtime entrypoint.
    """
    from engine.config import load_config  # noqa: PLC0415
    from engine.game import GameWindow  # noqa: PLC0415

    root = Path(project_root).resolve() if project_root is not None else None
    config_path = root / "config.json" if root is not None else Path("config.json")
    scene_path = Path(main_scene_path)
    scene_value = scene_path.as_posix() if not scene_path.is_absolute() else str(scene_path)

    with _temporary_repo_root_override(root):
        config = load_config(str(config_path))
        window = GameWindow(
            width=config.width,
            height=config.height,
            title=config.title,
            fullscreen=config.fullscreen,
            vsync=config.vsync,
            config=config,
            config_path=str(config_path),
        )
        window.load_scene(scene_value)
        window.run()


__all__ = ["load_scene_payload", "run_game"]
