"""S1 1.2 (D4): F3's state-changing debug keys need a developer launch, through the real keys of a real (hidden) window.

#662 kept F3's ``show_debug`` tools out of a game launch, but F3 also turned on ``engine_config.debug_mode``, and that
alone unlocked the F12/F7/F8 debug battles, F10 breeding and the F9 batching toggle. An export's config.json can set
``debug_mode`` too. Owner decision D4: players keep read-only diagnostics (the F3 HUD, the perf, encounter and scene
inspector overlays); debug battles, breeding shortcuts, warps and other state-changing debug actions need a developer
launch (``mesh play``, ``mesh edit``, MESH_LEGACY_EDITOR=1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.monster.egg_lifecycle import MONSTER_EGGS_KEY
from tests.test_dev_tools_gate_real_window import _launch
from tests.test_legacy_editor_gate_real_window import _close
from tests.test_monster_egg_lifecycle import _seed_two_party_monsters

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

DEBUG_KEYS = ["F12", "F7", "F8", "F10", "F9"]  # debug battle, trainer battle, companion battle, breed, batching
BINDINGS = {"toggle_dev_browser": ["B"], "toggle_variant_picker": ["V"]}
DEV_LAUNCHES = pytest.mark.parametrize("mode,env", [("play", False), ("editor", False), (None, True)],
                                       ids=["mesh play", "mesh edit", "MESH_LEGACY_EDITOR=1"])


def _press(window: Any, symbol: int, mods: int = 0) -> None:
    window.dispatch_event("on_key_press", symbol, mods)
    window.on_update(1 / 60)  # (input-binding actions such as B and V fire on the frame the key is down)
    window.dispatch_event("on_key_release", symbol, mods)
    window.on_update(1 / 60)


def _game(window: Any) -> dict[str, Any]:
    """Everything a debug key could change: the saved game state, a battle, the pause, the render batching."""
    return {
        "values": json.dumps(window.game_state_controller.state.values, sort_keys=True, default=str),
        "battle": bool(window.monster_battle_mode.active),
        "paused": bool(window.paused),
        "batching": (window.render_batching_enabled, window.render_culling_enabled, window.tilemap_batching_enabled),
    }


def _seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str | None, *, env: bool = False,
            **config: Any) -> Any:
    # (B and V are bound as in a new project's config.json: the engine's own defaults leave them unbound)
    window = _launch(tmp_path, monkeypatch, mode, env=env, input_bindings=BINDINGS, **config)
    _seed_two_party_monsters(window.game_state_controller.state.values)  # (F10 breeds the first two)
    window.on_update(1 / 60)  # (the first frame sets the time of day in the game state)
    return window


# --------------------------------------------------------------------- a game launch: read-only only

@pytest.mark.parametrize("how", ["F3", "config.json debug_mode"])
@pytest.mark.parametrize("name", DEBUG_KEYS)
def test_debug_keys_change_nothing_in_a_game_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    how: str, name: str) -> None:
    key = optional_arcade.arcade.key
    window = _seeded(tmp_path, monkeypatch, None, debug_mode=(how != "F3"))
    try:
        if how == "F3":
            _press(window, key.F3)
        assert window.engine_config.debug_mode is True  # (the read-only debug HUD is on)
        assert window.show_debug is False
        before = _game(window)
        _press(window, getattr(key, name))
        assert _game(window) == before
        assert window.game_state_controller.state.values.get(MONSTER_EGGS_KEY, []) == []
    finally:
        _close(window)


def test_players_keep_the_read_only_overlays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """F3's HUD and the perf (P), encounter (F2) and scene inspector (F10) overlays still toggle in a game launch;
    with the HUD on, F10 opens the inspector as it does without it, instead of breeding."""
    key = optional_arcade.arcade.key
    window = _seeded(tmp_path, monkeypatch, None)
    try:
        _press(window, key.F3)
        assert window.engine_config.debug_mode is True
        for symbol, overlay in ((key.P, window.perf_overlay), (key.F2, window.encounter_debug_overlay),
                                (key.F10, window.scene_inspector_overlay)):
            _press(window, symbol)
            assert overlay.visible is True
            _press(window, symbol)
            assert overlay.visible is False
        _press(window, key.F3)
        assert window.engine_config.debug_mode is False
    finally:
        _close(window)


def test_the_scene_browser_and_variant_picker_never_open_in_a_game_launch(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B (scene/world browser) and V (variant picker) warp the player to any room or world."""
    key = optional_arcade.arcade.key
    window = _seeded(tmp_path, monkeypatch, None)
    try:
        for symbol in (key.B, key.V):
            _press(window, symbol)
        assert window.dev_browser_overlay.visible is False
        assert window.variant_picker_overlay.visible is False
    finally:
        _close(window)


def test_any_route_to_a_debug_battle_or_breeding_is_refused_in_a_game_launch(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate is in the debug actions themselves, so a route other than F3's keys (the key router's
    ``capture.debug.monster_battle.start`` handler, a future one) gets nothing either."""
    window = _seeded(tmp_path, monkeypatch, None, debug_mode=True)
    try:
        before = _game(window)
        assert window.start_debug_monster_battle() is None
        assert window.start_debug_trainer_monster_battle() is None
        assert window.start_debug_companion_monster_battle() is None
        assert window.debug_breed_first_party_pair() is False
        assert _game(window) == before
    finally:
        _close(window)


# --------------------------------------------------------------------- dev launches keep them (positive control)

@DEV_LAUNCHES
@pytest.mark.parametrize("name", DEBUG_KEYS)
def test_dev_launches_keep_the_debug_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          mode: str | None, env: bool, name: str) -> None:
    key = optional_arcade.arcade.key
    window = _seeded(tmp_path, monkeypatch, mode, env=env)
    try:
        _press(window, key.F3)
        assert window.engine_config.debug_mode is True and window.show_debug is True
        before = _game(window)
        _press(window, getattr(key, name))
        after = _game(window)
        if name == "F10":
            assert len(window.game_state_controller.state.values[MONSTER_EGGS_KEY]) == 1
        elif name == "F9":
            assert after["batching"] == tuple(not v for v in before["batching"])
        else:
            assert after["battle"] is True and before["battle"] is False
    finally:
        _close(window)


@DEV_LAUNCHES
def test_dev_launches_keep_the_scene_browser_and_variant_picker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                mode: str | None, env: bool) -> None:
    key = optional_arcade.arcade.key
    window = _seeded(tmp_path, monkeypatch, mode, env=env)
    try:
        _press(window, key.B)
        assert window.dev_browser_overlay.visible is True
        _press(window, key.B)  # (closes it)
        assert window.dev_browser_overlay.visible is False
        _press(window, key.V)
        assert window.variant_picker_overlay.visible is True
    finally:
        _close(window)
