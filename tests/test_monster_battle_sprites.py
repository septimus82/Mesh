from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import BattleSprite, BattleStats, MonsterInstance, Move, Species
from engine.monster.battle_sprite_view import BattleSpriteAnimator, BattleSpriteDisplay
from engine.monster.data_load import load_monster_catalog, parse_species
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)

SPROUTLING_BATTLE_SPRITE = BattleSprite(
    sheet="assets/sprites/sproutling.png",
    columns=7,
    rows=1,
    frame_width=107,
    frame_height=109,
    idle_frames=(0, 1, 2, 3, 4, 5, 6),
    fps=6.0,
)
SPROUTLING = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
    types=("grass",),
    learnset=("tackle",),
    battle_sprite=SPROUTLING_BATTLE_SPRITE,
)
SHELLTIDE = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
)
BENCH = Species(
    id="benchling",
    base_stats=BattleStats(hp=28, atk=8, defense=10, spd=10),
    types=("normal",),
    learnset=("tackle",),
    battle_sprite=BattleSprite(
        sheet="assets/sprites/bench.png",
        columns=2,
        rows=1,
        frame_width=32,
        frame_height=32,
        idle_frames=(0, 1),
        fps=4.0,
    ),
)


def _texture(name: str, *, width: int = 107, height: int = 109) -> MagicMock:
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


def test_battle_sprite_animator_advances_idle_frame_over_dt() -> None:
    textures = tuple(_texture(f"frame_{index}") for index in range(3))
    animator = BattleSpriteAnimator(textures=textures, idle_frames=(0, 1, 2), fps=10.0)
    assert animator.frame_cursor == 0
    animator.update(0.05)
    assert animator.frame_cursor == 0
    animator.update(0.06)
    assert animator.frame_cursor == 1
    animator.update(0.2)
    assert animator.frame_cursor == 0


def test_overlay_resolves_player_and_opponent_battle_sprites_from_species() -> None:
    window = _window_with_assets(*(_texture(f"sprout_{index}") for index in range(7)))
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(SPROUTLING, level=8, known_moves=("tackle",)),
        opponent_monster=MonsterInstance(SHELLTIDE, level=6, known_moves=("tackle",)),
        moves={"tackle": TACKLE},
        type_chart={},
    )
    overlay = mode.overlay
    assert overlay is not None
    assert overlay._player_sprite.has_sprite is True
    assert overlay._opponent_sprite.has_sprite is False
    assert overlay._player_sprite.species_id == "sproutling"
    assert overlay._opponent_sprite.species_id == "shelltide"


def test_species_without_battle_sprite_falls_back_without_crashing() -> None:
    window = _window_with_assets()
    display = BattleSpriteDisplay(as_any(window))
    display.reload(SHELLTIDE)
    assert display.has_sprite is False
    display.update(1.0 / 30.0)
    display.draw(400.0, 300.0)


def test_switch_updates_displayed_battle_sprite() -> None:
    window = _window_with_assets(
        *(_texture(f"sprout_{index}") for index in range(7)),
        _texture("bench_a", width=32, height=32),
        _texture("bench_b", width=32, height=32),
    )
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(SPROUTLING, level=8, known_moves=("tackle",)),
        opponent_monster=MonsterInstance(SHELLTIDE, level=6, known_moves=("tackle",)),
        player_party=[
            MonsterInstance(SPROUTLING, level=8, known_moves=("tackle",)),
            MonsterInstance(BENCH, level=5, known_moves=("tackle",)),
        ],
        moves={"tackle": TACKLE},
        type_chart={},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    overlay = mode.overlay
    assert overlay is not None
    assert overlay._player_sprite.species_id == "sproutling"

    mode.submit_player_switch(1)

    overlay._sync_battle_sprites_if_needed()
    assert overlay._player_sprite.species_id == "benchling"
    assert overlay._player_sprite.has_sprite is True


def test_parse_species_reads_optional_battle_sprite(tmp_path: Path) -> None:
    payload = {
        "species": [
            {
                "id": "sproutling",
                "types": ["grass"],
                "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                "learnset": ["tackle"],
                "battle_sprite": {
                    "sheet": "assets/sprites/sproutling.png",
                    "columns": 7,
                    "rows": 1,
                    "frame_width": 107,
                    "frame_height": 109,
                    "idle_frames": [0, 1, 2, 3, 4, 5, 6],
                    "fps": 6,
                },
            }
        ]
    }
    (tmp_path / "monster_species.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "monster_moves.json").write_text(
        json.dumps({"moves": [{"id": "tackle", "type": "normal", "power": 40, "accuracy": 100, "pp": 35}]}),
        encoding="utf-8",
    )
    (tmp_path / "monster_type_chart.json").write_text(
        json.dumps({"types": ["normal", "grass"], "chart": {}}),
        encoding="utf-8",
    )
    species, result = parse_species(payload)
    assert result.ok is True
    battle_sprite = species["sproutling"].battle_sprite
    assert battle_sprite is not None
    assert battle_sprite.sheet == "assets/sprites/sproutling.png"
    assert battle_sprite.idle_frames == (0, 1, 2, 3, 4, 5, 6)

    catalog, catalog_result = load_monster_catalog(tmp_path)
    assert catalog_result.ok is True
    assert catalog is not None
    assert catalog.species["sproutling"].battle_sprite is not None
