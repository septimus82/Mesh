from __future__ import annotations

from typing import TYPE_CHECKING

from engine.audio import AudioManager
from engine.runtime_settings import RuntimeSettings, ensure_runtime_settings
from engine.runtime_settings_storage import load_runtime_settings, resolve_runtime_settings_path

if TYPE_CHECKING:
    from engine.game import GameWindow


def init_audio_coordinator(
    window: "GameWindow",
    *,
    audio_manager_cls: type[AudioManager] = AudioManager,
) -> None:
    window.audio = audio_manager_cls()
    window.audio.set_master_volume(window.engine_config.master_volume)
    window.audio.set_sfx_volume(window.engine_config.sfx_volume)
    window.audio.set_music_volume(window.engine_config.music_volume)

    window.runtime_settings = ensure_runtime_settings(window)
    window.runtime_settings_path = resolve_runtime_settings_path()
    loaded_settings = load_runtime_settings(
        window.runtime_settings_path,
        base=window.runtime_settings,
    )
    if isinstance(loaded_settings, RuntimeSettings):
        window.runtime_settings = loaded_settings
    window.runtime_settings.apply(window)