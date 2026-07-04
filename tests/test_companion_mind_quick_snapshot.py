from __future__ import annotations

from pathlib import Path

import pytest

from engine import savegame
from engine.monster.collection import (
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    add_caught_monster,
    load_companion_mind_for_instance,
    persist_companion_mind,
)
from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament, praise
from engine.monster.battle_model import MonsterInstance
from tests.test_monster_encounter_zone import SPROUT

pytestmark = pytest.mark.fast


class _StubSceneController:
    def __init__(self, scene_path: str) -> None:
        self.current_scene_path = scene_path


class _StubEngineConfig:
    def __init__(self, world_file: str | None) -> None:
        self.world_file = world_file


class _StubWindow:
    def __init__(self, *, world_file: str | None, scene_path: str) -> None:
        from engine.game_state_controller import GameStateController

        self.engine_config = _StubEngineConfig(world_file)
        self.scene_controller = _StubSceneController(scene_path)
        self.game_state_controller = GameStateController(self)
        self.requested_scene: str | None = None

    def request_scene_change(self, scene_path: str) -> None:
        self.requested_scene = scene_path


def test_quick_snapshot_roundtrip_preserves_companion_mind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "saves").mkdir(parents=True, exist_ok=True)

    window = _StubWindow(
        world_file="packs/core_regions/worlds/main.json",
        scene_path="packs/core_regions/scenes/start.json",
    )
    values = window.game_state_controller.state.values
    monster = MonsterInstance(SPROUT, level=8, current_hp=24, known_moves=("tackle",))
    caught = add_caught_monster(values, monster)
    instance_id = caught.instance_id
    mind = CompanionMind(
        temperament=Temperament(aggression=65.0, fear=12.0),
        learned=LearnedWeights(ATTACK=18.0, DEFEND=2.0, HESITATE=1.0),
        trust=70.0,
        bond=55.0,
    )
    mind = praise(mind)
    persist_companion_mind(values, instance_id, mind)

    assert savegame.save_quick_snapshot(window) is True
    save_path = tmp_path / "saves" / "quick.json"
    assert save_path.is_file()
    raw = save_path.read_text(encoding="utf-8")
    assert MONSTER_PARTY_KEY in raw
    assert MONSTER_INSTANCES_KEY in raw
    assert "companion_mind" in raw

    fresh = _StubWindow(
        world_file="packs/core_regions/worlds/main.json",
        scene_path="packs/core_regions/scenes/start.json",
    )
    assert MONSTER_PARTY_KEY not in fresh.game_state_controller.state.values
    assert savegame.load_quick_snapshot(fresh) is True

    restored = load_companion_mind_for_instance(fresh.game_state_controller.state.values, instance_id)
    assert restored is not None
    assert restored.bond == pytest.approx(mind.bond)
    assert restored.trust == pytest.approx(mind.trust)
    assert float(getattr(restored.learned, "ATTACK")) == pytest.approx(float(getattr(mind.learned, "ATTACK")))
