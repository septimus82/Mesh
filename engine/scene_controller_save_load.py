"""Save/load orchestration delegation helpers for SceneController."""
from __future__ import annotations

from typing import Any, Callable, Dict, cast


def snapshot_player_state(
    controller: Any,
    *,
    snapshot_player_state_runtime: Callable[[Any], dict[str, Any] | None],
) -> dict[str, Any] | None:
    return snapshot_player_state_runtime(controller)


def restore_player_state(
    controller: Any,
    snapshot: dict[str, Any] | None,
    *,
    restore_player_state_runtime: Callable[[Any, dict[str, Any] | None], None],
) -> None:
    restore_player_state_runtime(controller, snapshot)


def snapshot_camera_state(
    controller: Any,
    *,
    snapshot_camera_state_runtime: Callable[[Any], dict[str, Any] | None],
) -> dict[str, Any] | None:
    return snapshot_camera_state_runtime(controller)


def restore_camera_state(
    controller: Any,
    snapshot: dict[str, Any] | None,
    *,
    restore_camera_state_runtime: Callable[[Any, dict[str, Any] | None], None],
) -> None:
    restore_camera_state_runtime(controller, snapshot)


def get_loaded_scene_payload(
    controller: Any,
    *,
    scene_load_apply_runtime: Any,
) -> Dict[str, Any]:
    return cast(Dict[str, Any], scene_load_apply_runtime.get_loaded_scene_payload(controller))


def get_authored_scene_payload(
    controller: Any,
    *,
    scene_load_apply_runtime: Any,
    authoring_runtime: Any,
) -> Dict[str, Any]:
    return cast(
        Dict[str, Any],
        scene_load_apply_runtime.get_authored_scene_payload(controller, authoring_runtime=authoring_runtime),
    )


def debug_apply_authored_scene_payload(
    controller: Any,
    authored_payload: Dict[str, Any],
    *,
    scene_load_apply_runtime: Any,
    authoring_runtime: Any,
) -> bool:
    return bool(
        scene_load_apply_runtime.debug_apply_authored_scene_payload(
            controller,
            authored_payload,
            authoring_runtime=authoring_runtime,
        )
    )


def apply_scene_settings(
    controller: Any,
    settings: Dict[str, Any],
    *,
    scene_load_apply_runtime: Any,
) -> None:
    scene_load_apply_runtime.apply_scene_settings(controller, settings)


def apply_scene_state(
    controller: Any,
    state_block: Any,
    *,
    scene_load_apply_runtime: Any,
    apply_scene_state_runtime: Callable[[Any, Any], None],
) -> None:
    scene_load_apply_runtime.apply_scene_state(controller, state_block, apply_scene_state_runtime=apply_scene_state_runtime)


def build_scene_snapshot(
    controller: Any,
    *,
    compact: bool = False,
    build_scene_snapshot_runtime: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    return build_scene_snapshot_runtime(controller, compact=compact)
