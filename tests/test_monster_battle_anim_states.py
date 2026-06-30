from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.monster.battle_controller import MonsterBattleController, MoveAction
from engine.monster.battle_mode import (
    BattlePresentationStep,
    MonsterBattleMode,
    _battle_combatant_layout,
)
from engine.monster.battle_model import BattleSprite, BattleSpriteClip, BattleStats, MonsterInstance, Move, Species
from engine.monster.battle_sprite_view import BattleSpriteAnimator, BattleSpriteDisplay
from engine.monster.data_load import parse_species
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

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


def _texture(name: str, *, width: int = 32, height: int = 32) -> MagicMock:
    texture = MagicMock(name=name)
    texture.width = width
    texture.height = height
    return texture


def _window_with_assets(*textures: MagicMock) -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.game_over = False
    window.show_debug = False
    window.monster_battle_mode_active = False
    window.ui_controller = UIController(as_any(window))
    window.emit_event = MagicMock()
    window.console_log = MagicMock()

    sheet = MagicMock()
    sheet.frames = list(textures)
    cache = MagicMock()
    cache.get_or_build.return_value = sheet
    factory = MagicMock()
    factory.sheets = cache
    window.animation_factory = factory
    return window


def test_parse_battle_sprite_clips_idle_and_optional(tmp_path: Path) -> None:
    payload = {
        "species": [
            {
                "id": "demo",
                "types": ["normal"],
                "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                "learnset": ["tackle"],
                "battle_sprite": {
                    "sheet": "assets/sprites/demo.png",
                    "columns": 4,
                    "rows": 2,
                    "frame_width": 32,
                    "frame_height": 32,
                    "clips": {
                        "idle": {"frames": [0, 1], "fps": 6, "loop": True},
                        "attack": {"frames": [2, 3], "fps": 8, "loop": False},
                        "hurt": {"frames": [4], "fps": 4, "loop": False},
                    },
                },
            }
        ]
    }
    (tmp_path / "monster_species.json").write_text(json.dumps(payload), encoding="utf-8")
    species, result = parse_species(payload)
    assert result.ok is True
    sprite = species["demo"].battle_sprite
    assert sprite is not None
    assert sprite.clips["idle"].frames == (0, 1)
    assert sprite.clips["attack"].loop is False
    assert sprite.clips["hurt"].frames == (4,)


def test_parse_battle_sprite_backward_compat_idle_frames_only(tmp_path: Path) -> None:
    payload = {
        "species": [
            {
                "id": "legacy",
                "types": ["grass"],
                "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                "learnset": ["tackle"],
                "battle_sprite": {
                    "sheet": "assets/sprites/legacy.png",
                    "columns": 3,
                    "rows": 1,
                    "frame_width": 16,
                    "frame_height": 16,
                    "idle_frames": [0, 1, 2],
                    "fps": 5,
                },
            }
        ]
    }
    species, result = parse_species(payload)
    assert result.ok is True
    sprite = species["legacy"].battle_sprite
    assert sprite is not None
    assert sprite.idle_frames == (0, 1, 2)
    assert sprite.fps == 5.0
    assert sprite.clips["idle"].loop is True


def test_play_clip_cycles_looping_clip() -> None:
    textures = tuple(_texture(f"f{index}") for index in range(4))
    animator = BattleSpriteAnimator(
        textures=textures,
        clips={"idle": BattleSpriteClip(frames=(0, 1), fps=10.0, loop=True)},
    )
    assert animator.play_clip("idle") == "idle"
    assert animator.frame_cursor == 0
    animator.update(0.11)
    assert animator.frame_cursor == 1
    animator.update(0.11)
    assert animator.frame_cursor == 0


def test_one_shot_clip_reverts_to_idle_on_completion() -> None:
    textures = tuple(_texture(f"f{index}") for index in range(4))
    animator = BattleSpriteAnimator(
        textures=textures,
        clips={
            "idle": BattleSpriteClip(frames=(0,), fps=10.0, loop=True),
            "attack": BattleSpriteClip(frames=(1, 2), fps=10.0, loop=False),
        },
    )
    animator.play_clip("attack")
    animator.update(0.11)
    assert animator.active_clip_name == "attack"
    assert animator.frame_cursor == 1
    animator.update(0.11)
    assert animator.active_clip_name == "idle"
    assert animator.frame_cursor == 0


def test_play_clip_undefined_falls_back_to_idle_without_crash() -> None:
    textures = tuple(_texture("idle"))
    animator = BattleSpriteAnimator(
        textures=textures,
        clips={"idle": BattleSpriteClip(frames=(0,), fps=6.0, loop=True)},
    )
    effective = animator.play_clip("attack")
    assert effective == "idle"
    assert animator.last_requested_clip == "attack"
    assert animator.last_effective_clip == "idle"
    animator.update(1.0)


def test_presentation_requests_attack_hurt_and_faint_clips() -> None:
    window = _window_with_assets()
    mode = MonsterBattleMode(as_any(window))
    player = MonsterInstance(PLAYER, level=10, current_hp=30, known_moves=("ko",))
    opponent = MonsterInstance(OPPONENT, level=5, current_hp=5, known_moves=("tackle",))
    mode.controller = MonsterBattleController(
        player=player,
        opponent=opponent,
        moves={"tackle": TACKLE, "ko": KO},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    mode.active = True

    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)

    move_step = next(step for step in steps if "used ko" in step.line)
    assert move_step.player_clip == "attack"
    assert move_step.opponent_clip == "hurt"

    faint_step = next(step for step in steps if "fainted" in step.line.lower())
    assert faint_step.opponent_clip == "faint"


def test_overlay_applies_presentation_clip_requests() -> None:
    window = _window_with_assets(*(_texture(f"sprout_{index}") for index in range(2)))
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(
            Species(
                id="sproutling",
                base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
                types=("grass",),
                learnset=("tackle",),
                battle_sprite=BattleSprite(
                    sheet="assets/sprites/sproutling.png",
                    columns=2,
                    rows=1,
                    frame_width=32,
                    frame_height=32,
                    clips={"idle": BattleSpriteClip(frames=(0, 1), fps=6.0, loop=True)},
                ),
            ),
            level=8,
            known_moves=("tackle",),
        ),
        opponent_monster=MonsterInstance(OPPONENT, level=6, known_moves=("tackle",)),
        moves={"tackle": TACKLE},
        type_chart={},
    )
    overlay = mode.overlay
    assert overlay is not None
    overlay.begin_turn_presentation(
        [
            BattlePresentationStep(
                "Sproutling attacks!",
                30,
                20,
                player_clip="attack",
            ),
        ],
        result=None,
    )
    overlay._advance_presentation()
    assert overlay._player_sprite.last_requested_clip == "attack"
    assert overlay._player_sprite.last_effective_clip == "idle"


def test_sprite_positions_align_with_hp_panel_sides() -> None:
    left = 1280.0 * 0.12
    right = 1280.0 * 0.88
    top = 720.0 * 0.86
    layout = _battle_combatant_layout(left, right, top)
    center = (left + right) / 2.0

    assert layout["opponent_hp"][0] < center
    assert layout["player_hp"][0] > center
    assert layout["opponent_sprite"][0] < center
    assert layout["player_sprite"][0] > center

    opponent_hp_distance = abs(layout["opponent_sprite"][0] - layout["opponent_hp"][0])
    opponent_cross_distance = abs(layout["opponent_sprite"][0] - layout["player_hp"][0])
    player_hp_distance = abs(layout["player_sprite"][0] - layout["player_hp"][0])
    player_cross_distance = abs(layout["player_sprite"][0] - layout["opponent_hp"][0])

    assert opponent_hp_distance < opponent_cross_distance
    assert player_hp_distance < player_cross_distance


def test_display_play_clip_without_sprite_is_safe() -> None:
    window = _window_with_assets()
    display = BattleSpriteDisplay(as_any(window))
    assert display.play_clip("attack") is None
