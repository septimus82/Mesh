from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import MonsterBattleMode, _battle_combatant_layout
from engine.monster.battle_model import BattleSprite, BattleSpriteClip, BattleStats, MonsterInstance, Move, Species
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
    clips={"idle": BattleSpriteClip(frames=(0, 1, 2, 3, 4, 5, 6), fps=6.0, loop=True)},
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
        clips={"idle": BattleSpriteClip(frames=(0, 1), fps=4.0, loop=True)},
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
    animator = BattleSpriteAnimator(
        textures=textures,
        clips={"idle": BattleSpriteClip(frames=(0, 1, 2), fps=10.0, loop=True)},
    )
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


def test_shelltide_battle_sprite_parses_from_catalog() -> None:
    catalog, result = load_monster_catalog()
    assert result.ok is True
    assert catalog is not None
    battle_sprite = catalog.species["shelltide"].battle_sprite
    assert battle_sprite is not None
    assert battle_sprite.sheet == "assets/sprites/shelltide.png"
    assert battle_sprite.columns == 7
    assert battle_sprite.frame_width == 128
    assert battle_sprite.frame_height == 128
    assert battle_sprite.clips["idle"].frames == (0, 1, 2, 3, 4, 5, 6)
    assert battle_sprite.clips["idle"].fps == 6.0
    assert battle_sprite.clips["idle"].loop is True


def test_overlay_resolves_shelltide_opponent_battle_sprite() -> None:
    catalog, result = load_monster_catalog()
    assert result.ok is True
    assert catalog is not None
    window = _window_with_assets(
        *(_texture(f"sprout_{index}") for index in range(7)),
        *(_texture(f"shell_{index}", width=128, height=128) for index in range(7)),
    )
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(
            catalog.species["sproutling"],
            level=8,
            known_moves=("tackle",),
        ),
        opponent_monster=MonsterInstance(
            catalog.species["shelltide"],
            level=6,
            known_moves=("tackle",),
        ),
        moves={"tackle": TACKLE},
        type_chart={},
    )
    overlay = mode.overlay
    assert overlay is not None
    assert overlay._player_sprite.has_sprite is True
    assert overlay._opponent_sprite.has_sprite is True
    assert overlay._opponent_sprite.species_id == "shelltide"


def test_opponent_shelltide_battle_sprite_draws_in_opponent_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.optional_arcade as optional_arcade
    from engine.animation import AnimationFactory
    from engine.assets import AssetManager

    catalog, result = load_monster_catalog()
    assert result.ok is True
    assert catalog is not None

    draws: list[tuple[float, float, float, float]] = []

    def record(cx: float, cy: float, w: float, h: float, tex: object, **kwargs: object) -> None:
        _ = kwargs
        _ = tex
        draws.append((float(cx), float(cy), float(w), float(h)))

    monkeypatch.setattr(optional_arcade, "draw_texture_rect_compat", record)

    assets = AssetManager()
    factory = AnimationFactory(assets)
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
    window.animation_factory = factory
    window.assets = assets

    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(
            catalog.species["sproutling"],
            level=8,
            known_moves=("tackle",),
        ),
        opponent_monster=MonsterInstance(
            catalog.species["shelltide"],
            level=6,
            known_moves=("tackle",),
        ),
        moves={"tackle": TACKLE},
        type_chart={},
    )
    overlay = mode.overlay
    assert overlay is not None
    layout = _battle_combatant_layout(1280.0 * 0.12, 1280.0 * 0.88, 720.0 * 0.86)
    overlay._opponent_sprite.draw(*layout["opponent_sprite"])

    layout = _battle_combatant_layout(1280.0 * 0.12, 1280.0 * 0.88, 720.0 * 0.86)
    opponent_x, opponent_y = layout["opponent_sprite"]
    opponent_draws = [
        entry
        for entry in draws
        if abs(entry[0] - opponent_x) < 1.0
        and abs(entry[1] - opponent_y) < 1.0
        and entry[2] == 128.0
        and entry[3] == 128.0
    ]
    assert opponent_draws, f"expected opponent-slot draw near {(opponent_x, opponent_y)}, got {draws}"


def test_clips_schema_shelltide_display_loads_real_sheet_frames() -> None:
    from engine.animation import AnimationFactory
    from engine.assets import AssetManager

    catalog, result = load_monster_catalog()
    assert result.ok is True
    assert catalog is not None

    assets = AssetManager()
    factory = AnimationFactory(assets)
    window = types.SimpleNamespace(
        width=1280,
        height=720,
        animation_factory=factory,
        assets=assets,
    )
    display = BattleSpriteDisplay(as_any(window))
    display.reload(catalog.species["shelltide"])
    assert display.has_sprite is True
    assert display._animator is not None
    assert len(display._animator.textures) == 7
    texture = display._animator.current_texture()
    assert texture is not None
    assert int(getattr(texture, "width", 0) or 0) == 128
    assert int(getattr(texture, "height", 0) or 0) == 128


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


def test_shelltide_opponent_battle_sprite_renders_visible_pixel() -> None:
    """Live probe: Shelltide draws a non-panel pixel in the opponent battle slot."""
    import engine.optional_arcade as optional_arcade
    from engine.config import EngineConfig
    from engine.game import GameWindow
    from engine.game_runtime import tick
    from engine.monster.battle_model import MonsterInstance
    from tests._game_window_live import dispose_game_window

    cfg = EngineConfig(
        width=1280,
        height=720,
        title="shelltide opponent render contract",
        fullscreen=False,
        vsync=False,
        start_scene="scenes/showcase_hub.json",
        main_menu_scene=None,
        world_file=None,
    )
    try:
        window = GameWindow(width=1280, height=720, title=cfg.title, vsync=False, config=cfg)
    except TypeError as exc:
        if "OpenGLArcadeContext" in str(exc):
            pytest.skip("OpenGL context unavailable in this test runner session")
        raise
    try:
        catalog, result = load_monster_catalog()
        assert result.ok is True
        assert catalog is not None
        window.start_monster_battle(
            player_monster=MonsterInstance(
                catalog.species["sproutling"],
                level=8,
                known_moves=("tackle",),
            ),
            opponent_monster=MonsterInstance(
                catalog.species["shelltide"],
                level=6,
                known_moves=("tackle",),
            ),
            moves={"tackle": TACKLE},
            type_chart=catalog.type_chart,
            return_context={"source": "render_contract"},
        )
        overlay = window.monster_battle_mode.overlay
        assert overlay is not None
        overlay.update(1.0 / 6.0)
        tick.on_draw(window)

        layout = _battle_combatant_layout(1280.0 * 0.12, 1280.0 * 0.88, 720.0 * 0.86)
        ox, oy = (int(layout["opponent_sprite"][0]), int(layout["opponent_sprite"][1]))
        panel_rgb = (16, 18, 28)
        hits = 0
        for dx in range(-48, 49, 4):
            for dy in range(-48, 49, 4):
                pixel = optional_arcade.arcade.get_pixel(ox + dx, oy + dy, components=4)
                if pixel[3] < 200:
                    continue
                if pixel[:3] == panel_rgb:
                    continue
                if sum(pixel[:3]) > 90:
                    hits += 1
        assert hits >= 8, f"expected visible Shelltide pixels near opponent slot ({ox}, {oy})"
    finally:
        dispose_game_window(window)

