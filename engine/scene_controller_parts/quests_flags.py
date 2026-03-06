# mypy: ignore-errors
from __future__ import annotations


def debug_config_set_game_state_set_toast(
    self,
    selected_ids: list[str],
    *,
    toast: str,
    toast_seconds: float | None,
) -> tuple[int, int, int]:
    """
    Debug-only: set toast (+ optional toast_seconds) for selected entities with SetGameStateOnEvent.

    - If toast_seconds is None: keep existing toast_seconds if present, else use 3.0.
    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return self._call_authoring(
        "debug_config_set_game_state_set_toast",
        selected_ids,
        toast=toast,
        toast_seconds=toast_seconds,
    )


def debug_config_set_game_state_add_require_flag(self, selected_ids: list[str], flag: str) -> tuple[int, int, int]:
    """
    Debug-only: append a require_flags entry for SetGameStateOnEvent, idempotently.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return self._call_authoring("debug_config_set_game_state_add_require_flag", selected_ids, flag)


def debug_config_set_game_state_add_forbid_flag(self, selected_ids: list[str], flag: str) -> tuple[int, int, int]:
    """
    Debug-only: append a forbid_flags entry for SetGameStateOnEvent, idempotently.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return self._call_authoring("debug_config_set_game_state_add_forbid_flag", selected_ids, flag)


def debug_config_set_game_state_set_flag_true(self, selected_ids: list[str], flag_key: str) -> tuple[int, int, int]:
    """
    Debug-only: set set_flags[flag_key] = True for SetGameStateOnEvent, without removing other keys.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return self._call_authoring("debug_config_set_game_state_set_flag_true", selected_ids, flag_key)


def debug_config_scene_transition_set_target_scene(self, selected_ids: list[str], target_scene: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.SceneTransition.target_scene for selected entities that have SceneTransition.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return self._call_authoring("debug_config_scene_transition_set_target_scene", selected_ids, target_scene)


def debug_config_scene_transition_set_spawn_id(self, selected_ids: list[str], spawn_id: str) -> tuple[int, int, int]:
    """
    Debug-only: set behaviour_config.SceneTransition.spawn_id (and spawn_point alias) for selected entities.

    Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
    """
    return self._call_authoring("debug_config_scene_transition_set_spawn_id", selected_ids, spawn_id)

def bind_quests_flags_methods(cls) -> None:
    cls.debug_config_set_game_state_set_toast = debug_config_set_game_state_set_toast
    cls.debug_config_set_game_state_add_require_flag = debug_config_set_game_state_add_require_flag
    cls.debug_config_set_game_state_add_forbid_flag = debug_config_set_game_state_add_forbid_flag
    cls.debug_config_set_game_state_set_flag_true = debug_config_set_game_state_set_flag_true
    cls.debug_config_scene_transition_set_target_scene = debug_config_scene_transition_set_target_scene
    cls.debug_config_scene_transition_set_spawn_id = debug_config_scene_transition_set_spawn_id
