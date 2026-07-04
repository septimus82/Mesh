"""Physical/special move category split: data, damage routing, and special clip."""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from engine.monster.battle_controller import MonsterBattleController, MoveAction
from engine.monster.battle_mode import MonsterBattleMode, _attack_clip_for_move
from engine.monster.battle_model import (
    BattleStats,
    MonsterInstance,
    Move,
    Species,
    compute_damage,
    derive_stats,
    resolve_move,
)
from engine.monster.battle_sprite_view import BattleSpriteAnimator, BattleSpriteClip
from engine.monster.data_load import KNOWN_MOVE_CATEGORIES, parse_moves, parse_species
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
WATER_PULSE = Move(id="water_pulse", type="water", power=60, accuracy=100, pp=20, category="special")

MIXED_ATTACKER = Species(
    id="mixed",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8, sp_attack=30, sp_defense=10),
    types=("water",),
    learnset=("tackle", "water_pulse"),
)
MIXED_DEFENDER = Species(
    id="mixed_def",
    base_stats=BattleStats(hp=30, atk=20, defense=20, spd=8, sp_attack=10, sp_defense=25),
    types=("water",),
    learnset=("tackle",),
)


def test_move_category_defaults_to_physical() -> None:
    moves, result = parse_moves(
        {"moves": [{"id": "tackle", "type": "normal", "power": 40, "accuracy": 100, "pp": 35}]},
    )
    assert result.ok is True
    assert moves["tackle"].category == "physical"


def test_move_category_accepts_special() -> None:
    moves, result = parse_moves(
        {
            "moves": [
                {
                    "id": "water_pulse",
                    "type": "water",
                    "power": 60,
                    "accuracy": 100,
                    "pp": 20,
                    "category": "special",
                }
            ]
        },
    )
    assert result.ok is True
    assert moves["water_pulse"].category == "special"


def test_move_category_rejects_unknown_with_allowed_list() -> None:
    _, result = parse_moves(
        {
            "moves": [
                {
                    "id": "bad",
                    "type": "normal",
                    "power": 40,
                    "accuracy": 100,
                    "pp": 35,
                    "category": "status",
                }
            ]
        },
    )
    assert result.ok is False
    message = " ".join(result.errors)
    for name in sorted(KNOWN_MOVE_CATEGORIES):
        assert name in message


def test_base_stats_sp_fields_default_to_physical_values() -> None:
    species, result = parse_species(
        {
            "species": [
                {
                    "id": "plain",
                    "types": ["normal"],
                    "base_stats": {"hp": 30, "atk": 11, "defense": 12, "spd": 8},
                    "learnset": ["tackle"],
                }
            ]
        },
    )
    assert result.ok is True
    stats = species["plain"].base_stats
    assert stats.sp_attack == 11
    assert stats.sp_defense == 12


def test_derive_stats_sp_fallback_matches_physical_when_unspecified() -> None:
    base = BattleStats(hp=30, atk=10, defense=10, spd=8)
    derived = derive_stats(base, 10)
    assert derived.atk == derived.sp_attack
    assert derived.defense == derived.sp_defense


def test_compute_damage_uses_different_stat_pairs_by_category() -> None:
    attacker = MonsterInstance(MIXED_ATTACKER, level=10)
    defender = MonsterInstance(MIXED_DEFENDER, level=10)

    physical = resolve_move(attacker, defender, TACKLE, rng=None)
    special = resolve_move(attacker, defender, WATER_PULSE, rng=None)

    assert physical.damage != special.damage
    assert special.damage > physical.damage

    expected_physical = compute_damage(
        level=10,
        attacker_atk=attacker.stats.atk,
        defender_def=defender.stats.defense,
        move_power=40,
        type_mult=1.0,
        rng=None,
    )
    expected_special = compute_damage(
        level=10,
        attacker_atk=attacker.stats.sp_attack,
        defender_def=defender.stats.sp_defense,
        move_power=60,
        type_mult=1.0,
        rng=None,
    )
    assert physical.damage == expected_physical
    assert special.damage == expected_special


def test_existing_physical_moves_damage_unchanged_when_sp_defaults() -> None:
    plain = Species(
        id="plain",
        base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
        types=("grass",),
        learnset=("tackle",),
    )
    turtle = Species(
        id="turtle",
        base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
        types=("water",),
        learnset=("tackle",),
    )
    attacker = MonsterInstance(plain, level=10)
    defender = MonsterInstance(turtle, level=10, current_hp=42)
    result = resolve_move(attacker, defender, TACKLE, rng=None)
    assert result.damage == 6


def test_play_clip_special_falls_back_attack_then_idle() -> None:
    textures = tuple(MagicMock(width=32, height=32) for _ in range(3))
    idle_only = BattleSpriteAnimator(
        textures=textures,
        clips={"idle": BattleSpriteClip(frames=(0,), fps=6.0, loop=True)},
    )
    assert idle_only.play_clip("special") == "idle"

    attack_only = BattleSpriteAnimator(
        textures=textures,
        clips={
            "idle": BattleSpriteClip(frames=(0,), fps=6.0, loop=True),
            "attack": BattleSpriteClip(frames=(1,), fps=8.0, loop=False),
        },
    )
    assert attack_only.play_clip("special") == "attack"

    both = BattleSpriteAnimator(
        textures=textures,
        clips={
            "idle": BattleSpriteClip(frames=(0,), fps=6.0, loop=True),
            "attack": BattleSpriteClip(frames=(1,), fps=8.0, loop=False),
            "special": BattleSpriteClip(frames=(2,), fps=8.0, loop=False),
        },
    )
    assert both.play_clip("special") == "special"


def test_presentation_requests_special_clip_for_special_move() -> None:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.ui_controller = UIController(as_any(window))
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    window.game_state_controller = types.SimpleNamespace(state=types.SimpleNamespace(values={}))

    mode = MonsterBattleMode(as_any(window))
    opponent = MonsterInstance(MIXED_DEFENDER, level=10, current_hp=30, known_moves=("tackle",))
    mode.controller = MonsterBattleController(
        player=MonsterInstance(MIXED_ATTACKER, level=10, current_hp=30, known_moves=("water_pulse",)),
        opponent=opponent,
        moves={"water_pulse": WATER_PULSE, "tackle": TACKLE},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    mode.active = True

    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "water_pulse")
    steps = mode._build_presentation_steps(before_len, 30, 30)
    move_step = next(step for step in steps if "water_pulse" in step.line)
    assert move_step.player_clip == "special"
    assert _attack_clip_for_move(mode.controller.moves, "tackle") == "attack"


def test_legacy_five_clip_species_still_loads() -> None:
    species, result = parse_species(
        {
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
                        "clips": {
                            "idle": {"frames": [0], "fps": 6, "loop": True},
                            "attack": {"frames": [1], "fps": 8, "loop": False},
                            "defend": {"frames": [1], "fps": 8, "loop": False},
                            "hurt": {"frames": [1], "fps": 4, "loop": False},
                            "faint": {"frames": [1], "fps": 6, "loop": False},
                        },
                    },
                }
            ]
        },
    )
    assert result.ok is True
    assert set(species["legacy"].battle_sprite.clips) == {"idle", "attack", "defend", "hurt", "faint"}  # type: ignore[union-attr]
