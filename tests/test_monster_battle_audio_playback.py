"""Battle audio playback: mapping, ordered cues, intro idempotency, and music restore."""

from __future__ import annotations

import types
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import engine.audio as audio_mod
from engine.audio import AudioManager, MusicPlaybackSnapshot
from engine.monster.battle_audio import (
    BATTLE_CUE_INTERVAL_S,
    BATTLE_MUSIC_PATH,
    DEFAULT_BATTLE_SOUND_MAP,
    BattleAudioPlayback,
    approved_battle_sound_map_keys,
    approved_battle_sound_map_matches_vocabulary,
)
from engine.monster.battle_mode import BattlePresentationStep, MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.battle_sound_cues import (
    APPROVED_BATTLE_SOUND_CUES,
    BATTLE_ACTION,
    BATTLE_FAINT,
    BATTLE_HIT,
    BATTLE_START,
    BATTLE_SUPER_EFFECTIVE,
    BATTLE_VICTORY,
)
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

REPO_ROOT = Path(__file__).resolve().parents[1]

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)

PLAYER = Species(
    id="player_mon",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=20),
    types=("normal",),
    learnset=("tackle", "ko"),
)
OPPONENT = Species(
    id="opponent_mon",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("normal",),
    learnset=("tackle",),
)


@dataclass
class _SoundCall:
    path: str
    volume: float


@dataclass
class _TransitionCall:
    path: str
    volume: float
    loop: bool
    fade_out_s: float
    fade_in_s: float


class RecordingAudio:
    def __init__(self, *, snapshot: MusicPlaybackSnapshot | None = None) -> None:
        self.snapshot_state = snapshot or MusicPlaybackSnapshot(
            path="assets/music/forest_theme.wav",
            volume=0.8,
            loop=True,
        )
        self.sound_calls: list[_SoundCall] = []
        self.transition_calls: list[_TransitionCall] = []
        self.restore_calls: list[tuple[MusicPlaybackSnapshot, float, float]] = []
        self.snapshot_calls = 0

    def play_sound(self, path: str, volume: float = 1.0) -> None:
        self.sound_calls.append(_SoundCall(path=path, volume=float(volume)))

    def snapshot_music(self) -> MusicPlaybackSnapshot:
        self.snapshot_calls += 1
        return self.snapshot_state

    def transition_music(
        self,
        path: str,
        *,
        fade_out_s: float = 0.25,
        fade_in_s: float = 0.25,
        volume: float = 1.0,
        loop: bool = True,
    ) -> None:
        self.transition_calls.append(
            _TransitionCall(
                path=str(path),
                volume=float(volume),
                loop=bool(loop),
                fade_out_s=float(fade_out_s),
                fade_in_s=float(fade_in_s),
            ),
        )

    def restore_music(
        self,
        snapshot: MusicPlaybackSnapshot,
        *,
        fade_out_s: float = 0.25,
        fade_in_s: float = 0.25,
    ) -> None:
        self.restore_calls.append((snapshot, fade_out_s, fade_in_s))


def _window(*, audio: Any | None = None) -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.audio = audio
    window.ui_controller = UIController(as_any(window))
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    from engine.game_state_controller import GameState

    state = GameState()
    window.game_state_controller = types.SimpleNamespace(state=state)

    sheet = MagicMock()
    sheet.frames = [MagicMock(width=32, height=32) for _ in range(4)]
    cache = MagicMock()
    cache.get_or_build.return_value = sheet
    window.battle_sprite_cache = cache
    return window


def _start_battle(window: types.SimpleNamespace) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=10, current_hp=30, known_moves=("tackle", "ko")),
        opponent_monster=MonsterInstance(OPPONENT, level=5, current_hp=30, known_moves=("tackle",)),
        moves={"tackle": TACKLE, "ko": KO},
    )
    return mode


def _drain_presentation(mode: MonsterBattleMode) -> None:
    overlay = mode.overlay
    assert overlay is not None
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()


def test_mapping_keys_equal_fifteen_approved_semantic_cues() -> None:
    assert approved_battle_sound_map_matches_vocabulary()
    assert len(approved_battle_sound_map_keys()) == len(APPROVED_BATTLE_SOUND_CUES) == 15
    assert approved_battle_sound_map_keys() == frozenset(APPROVED_BATTLE_SOUND_CUES)


def test_every_mapped_path_exists_and_is_relative() -> None:
    for cue, spec in DEFAULT_BATTLE_SOUND_MAP.items():
        assert cue in APPROVED_BATTLE_SOUND_CUES
        assert spec.path
        assert not spec.path.startswith("/")
        assert "\\" not in spec.path
        assert (REPO_ROOT / spec.path).is_file(), f"missing asset for {cue}: {spec.path}"
        assert 0.0 <= spec.volume <= 1.0


def test_battle_sound_cues_module_has_no_asset_paths() -> None:
    source = (REPO_ROOT / "engine/monster/battle_sound_cues.py").read_text(encoding="utf-8")
    assert "assets/" not in source
    assert ".wav" not in source


def test_single_cue_plays_immediately_once() -> None:
    audio = RecordingAudio()
    playback = BattleAudioPlayback()
    playback.attach(audio)
    playback.dispatch_step_cues((BATTLE_ACTION,))
    assert len(audio.sound_calls) == 1
    assert audio.sound_calls[0].path == DEFAULT_BATTLE_SOUND_MAP[BATTLE_ACTION].path
    playback.update(1.0)
    assert len(audio.sound_calls) == 1


def test_ordered_cues_do_not_all_fire_on_first_frame() -> None:
    audio = RecordingAudio()
    playback = BattleAudioPlayback(cue_interval_s=0.1)
    playback.attach(audio)
    playback.dispatch_step_cues((BATTLE_ACTION, BATTLE_HIT, BATTLE_SUPER_EFFECTIVE))
    assert len(audio.sound_calls) == 1
    assert audio.sound_calls[0].path == DEFAULT_BATTLE_SOUND_MAP[BATTLE_ACTION].path
    playback.update(0.09)
    assert len(audio.sound_calls) == 1
    playback.update(0.02)
    assert len(audio.sound_calls) == 2
    assert audio.sound_calls[1].path == DEFAULT_BATTLE_SOUND_MAP[BATTLE_HIT].path
    playback.update(0.1)
    assert len(audio.sound_calls) == 3
    assert audio.sound_calls[2].path == DEFAULT_BATTLE_SOUND_MAP[BATTLE_SUPER_EFFECTIVE].path


def test_new_presentation_step_clears_stale_queued_cues() -> None:
    audio = RecordingAudio()
    playback = BattleAudioPlayback(cue_interval_s=0.1)
    playback.attach(audio)
    playback.dispatch_step_cues((BATTLE_ACTION, BATTLE_HIT, BATTLE_SUPER_EFFECTIVE))
    playback.dispatch_step_cues((BATTLE_FAINT,))
    assert len(audio.sound_calls) == 2
    assert audio.sound_calls[-1].path == DEFAULT_BATTLE_SOUND_MAP[BATTLE_FAINT].path
    playback.update(0.5)
    assert len(audio.sound_calls) == 2


def test_end_battle_clears_pending_cues() -> None:
    audio = RecordingAudio()
    playback = BattleAudioPlayback(cue_interval_s=0.1)
    playback.attach(audio)
    playback.begin_battle()
    playback.dispatch_step_cues((BATTLE_ACTION, BATTLE_HIT))
    playback.end_battle()
    playback.update(1.0)
    assert len(audio.sound_calls) == 1


def test_unknown_cue_does_not_crash() -> None:
    audio = RecordingAudio()
    playback = BattleAudioPlayback()
    playback.attach(audio)
    playback.dispatch_step_cues(("battle.unknown", BATTLE_HIT))
    assert len(audio.sound_calls) == 0
    playback.update(BATTLE_CUE_INTERVAL_S)
    assert len(audio.sound_calls) == 1
    assert audio.sound_calls[0].path == DEFAULT_BATTLE_SOUND_MAP[BATTLE_HIT].path


def test_intro_plays_once_and_repeated_set_intro_log_is_idempotent() -> None:
    audio = RecordingAudio()
    window = _window(audio=audio)
    mode = _start_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    start_path = DEFAULT_BATTLE_SOUND_MAP[BATTLE_START].path
    assert len([call for call in audio.sound_calls if call.path == start_path]) == 1
    playback = mode._battle_audio
    assert playback is not None
    overlay.set_intro_log()
    playback.consume_intro(overlay.intro_audio_cue)
    assert len([call for call in audio.sound_calls if call.path == start_path]) == 1
    overlay.update(0.5)
    overlay.snapshot()
    assert len([call for call in audio.sound_calls if call.path == start_path]) == 1


def test_advance_presentation_dispatches_step_cues_once() -> None:
    audio = RecordingAudio()
    window = _window(audio=audio)
    mode = _start_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    audio.sound_calls.clear()
    overlay.begin_turn_presentation(
        [
            BattlePresentationStep(
                "Hit!",
                30,
                20,
                audio_cues=(BATTLE_ACTION, BATTLE_HIT),
            ),
        ],
        result=None,
    )
    overlay._advance_presentation()
    assert len(audio.sound_calls) == 1
    overlay.update(BATTLE_CUE_INTERVAL_S)
    assert len(audio.sound_calls) == 2
    overlay.update(0.5)
    overlay.snapshot()
    assert len(audio.sound_calls) == 2


def test_manual_advance_to_next_step_plays_only_new_cues() -> None:
    audio = RecordingAudio()
    window = _window(audio=audio)
    mode = _start_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    playback = mode._battle_audio
    assert playback is not None
    playback._cue_interval_s = 0.1
    audio.sound_calls.clear()
    overlay.begin_turn_presentation(
        [
            BattlePresentationStep("One", 30, 30, audio_cues=(BATTLE_ACTION, BATTLE_HIT)),
            BattlePresentationStep("Two", 30, 30, audio_cues=(BATTLE_VICTORY,)),
        ],
        result=None,
    )
    overlay._advance_presentation()
    overlay._advance_presentation()
    paths = [call.path for call in audio.sound_calls]
    assert paths.count(DEFAULT_BATTLE_SOUND_MAP[BATTLE_ACTION].path) == 1
    assert paths.count(DEFAULT_BATTLE_SOUND_MAP[BATTLE_VICTORY].path) == 1


def test_audio_manager_snapshot_and_restore_path_volume_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AudioManager()
    monkeypatch.setattr(manager, "get_sound", lambda _path: object())
    monkeypatch.setattr(
        audio_mod.optional_arcade.arcade,
        "Sound",
        lambda *_args, **_kwargs: MagicMock(play=lambda **_kw: MagicMock()),
    )
    manager.play_music("assets/music/forest_theme.wav", volume=0.75, loop=False)
    snapshot = manager.snapshot_music()
    assert snapshot.path == "assets/music/forest_theme.wav"
    assert snapshot.volume == pytest.approx(0.75)
    assert snapshot.loop is False
    manager.play_music("assets/music/dungeon_theme.wav", volume=0.5, loop=True)
    manager.restore_music(snapshot, fade_out_s=0.0, fade_in_s=0.0)
    manager.update(1.0)
    restored = manager.snapshot_music()
    assert restored.path == "assets/music/forest_theme.wav"
    assert restored.volume == pytest.approx(0.75)
    assert restored.loop is False


def test_begin_battle_snapshots_scene_music_before_transition() -> None:
    audio = RecordingAudio()
    playback = BattleAudioPlayback()
    playback.attach(audio)
    playback.begin_battle()
    assert audio.snapshot_calls == 1
    assert audio.transition_calls
    assert audio.transition_calls[0].path == BATTLE_MUSIC_PATH


def test_end_battle_restores_scene_music_once() -> None:
    audio = RecordingAudio()
    playback = BattleAudioPlayback()
    playback.attach(audio)
    playback.begin_battle()
    playback.end_battle()
    playback.end_battle()
    assert len(audio.restore_calls) == 1
    snapshot, _, _ = audio.restore_calls[0]
    assert snapshot.path == "assets/music/forest_theme.wav"


def test_no_prior_music_restores_to_silence() -> None:
    audio = RecordingAudio(snapshot=MusicPlaybackSnapshot(path=None, volume=1.0, loop=True))
    playback = BattleAudioPlayback()
    playback.attach(audio)
    playback.begin_battle()
    playback.end_battle()
    assert len(audio.restore_calls) == 1
    snapshot, _, _ = audio.restore_calls[0]
    assert snapshot.path is None


def test_victory_battle_restores_scene_music_after_presentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = RecordingAudio()
    window = _window(audio=audio)
    mode = _start_battle(window)
    controller = mode.controller
    assert controller is not None
    audio.restore_calls.clear()
    mode.submit_player_move("ko")
    _drain_presentation(mode)
    assert len(audio.restore_calls) == 1


def test_run_from_battle_restores_scene_music() -> None:
    audio = RecordingAudio()
    window = _window(audio=audio)
    mode = _start_battle(window)
    audio.restore_calls.clear()
    mode.run_from_battle()
    assert len(audio.restore_calls) == 1


def test_battle_music_failure_does_not_prevent_battle_entry() -> None:
    class BrokenAudio:
        def snapshot_music(self) -> MusicPlaybackSnapshot:
            raise RuntimeError("snapshot failed")

        def transition_music(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("transition failed")

        def play_sound(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("sound failed")

        def restore_music(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("restore failed")

    window = _window(audio=BrokenAudio())
    mode = _start_battle(window)
    assert mode.active is True
    mode.run_from_battle()
    assert mode.active is False


def test_defeat_battle_restores_scene_music() -> None:
    from typing import cast

    from engine.monster.battle_controller import BattleResult

    audio = RecordingAudio()
    window = _window(audio=audio)
    mode = _start_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    audio.restore_calls.clear()
    result = BattleResult(
        cast(Any, "lost"),
        winning_side="opponent",
        losing_side="player",
        turns=1,
    )
    overlay.begin_turn_presentation(
        [BattlePresentationStep(mode.terms.defeat_no_fighters, 0, 30, audio_cues=(BATTLE_VICTORY,))],
        result=result,
    )
    _drain_presentation(mode)
    assert len(audio.restore_calls) == 1


def test_capture_success_restores_scene_music(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.monster.capture import CaptureResult

    audio = RecordingAudio()
    window = _window(audio=audio)
    mode = _start_battle(window)
    controller = mode.controller
    assert controller is not None
    controller.opponent = replace(controller.opponent, current_hp=1)
    monkeypatch.setattr(
        "engine.monster.battle_mode.resolve_capture",
        lambda *_args, **_kwargs: CaptureResult(
            caught=True,
            roll=0.0,
            chance=1.0,
            capture_rate=255,
            hp_fraction=0.1,
            ball_bonus=1.0,
        ),
    )
    audio.restore_calls.clear()
    mode.attempt_capture(item_id="pocket_ball")
    _drain_presentation(mode)
    assert len(audio.restore_calls) == 1


def test_missing_window_audio_allows_battle_flow() -> None:
    window = _window(audio=None)
    mode = _start_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    overlay.begin_turn_presentation(
        [BattlePresentationStep("Line", 30, 30, audio_cues=(BATTLE_ACTION, BATTLE_HIT))],
        result=None,
    )
    overlay._advance_presentation()
    overlay.update(0.2)
    mode.run_from_battle()
    assert mode.active is False
