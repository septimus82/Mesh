import json
from pathlib import Path

from engine.game_state_controller import GameStateController
from engine.quests import QuestManager
from engine import savegame


class _StubSceneController:
    def __init__(self, scene_path: str) -> None:
        self.current_scene_path = scene_path


class _StubEngineConfig:
    def __init__(self, world_file: str | None) -> None:
        self.world_file = world_file


class _StubWindow:
    def __init__(self, *, world_file: str | None, scene_path: str) -> None:
        self.engine_config = _StubEngineConfig(world_file)
        self.scene_controller = _StubSceneController(scene_path)
        self._events: list[tuple[str, dict]] = []
        self.requested_scene: str | None = None

        self.game_state_controller = GameStateController(self)

    @property
    def game_state(self):
        return self.game_state_controller.state

    def emit_signal(self, event_type: str, **payload):
        self._events.append((event_type, dict(payload)))

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def request_scene_change(self, scene_path: str) -> None:
        self.requested_scene = scene_path


def test_snapshot_roundtrip_preserves_world_scene_gold_flags(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    window = _StubWindow(world_file="worlds/act1_prologue.json", scene_path="packs/core_regions/scenes/Act1_Prologue_Cabin.json")

    window.game_state_controller.state.counters["gold"] = 42
    window.game_state_controller.state.flags.update({"zzz": True, "aaa": True, "bbb": True})

    payload = savegame.dump_snapshot(window.game_state_controller)
    assert payload["version"] == savegame.SNAPSHOT_VERSION
    assert payload["world_file"] == "worlds/act1_prologue.json"
    assert payload["scene_id"] == "packs/core_regions/scenes/Act1_Prologue_Cabin.json"
    assert payload["gold"] == 42
    assert payload["flags"] == ["aaa", "bbb", "zzz"]

    # Apply to a fresh window and ensure state is restored.
    fresh = _StubWindow(world_file=None, scene_path="packs/core_regions/scenes/Act1_Prologue_Exterior.json")
    savegame.apply_snapshot_to_game_state(fresh.game_state_controller, payload)

    assert fresh.game_state_controller.state.counters["gold"] == 42
    assert sorted([k for k, v in fresh.game_state_controller.state.flags.items() if v]) == ["aaa", "bbb", "zzz"]


def test_snapshot_file_determinism(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    window = _StubWindow(world_file="worlds/act1_prologue.json", scene_path="packs/core_regions/scenes/Act1_Prologue_Cabin.json")
    window.game_state_controller.state.counters["gold"] = 7
    window.game_state_controller.state.flags.update({"b": True, "a": True})

    path = Path("saves/quick.json")
    assert savegame.save_quick_snapshot(window, path=path) is True
    before = path.read_bytes()

    assert savegame.save_quick_snapshot(window, path=path) is True
    after = path.read_bytes()

    assert before == after

    # Also sanity-check stable ordering in the JSON text.
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["flags"] == ["a", "b"]


def test_snapshot_integration_with_real_quest_reward(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # Use a real quest from assets/data/quests.json to mutate gold/flags.
    window = _StubWindow(world_file="worlds/act1_prologue.json", scene_path="packs/core_regions/scenes/Act1_Prologue_Cabin.json")
    repo_root = Path(__file__).resolve().parents[1]
    quests = QuestManager(window, data_path=str(repo_root / "assets/data/quests.json"))

    assert window.game_state_controller.get_counter("gold", 0) == 0
    assert window.game_state_controller.get_flag("prologue_note_found", False) is False

    # Completing the quest applies reward (gold + flag).
    assert quests.complete_quest("quest_prologue_optional_note") is True
    assert window.game_state_controller.get_counter("gold", 0) == 5
    assert window.game_state_controller.get_flag("prologue_note_found", False) is True

    path = Path("saves/quick.json")
    assert savegame.save_quick_snapshot(window, path=path) is True

    # Reset state + scene to prove load restores.
    window.game_state_controller.state.flags = {}
    window.game_state_controller.state.counters = {"gold": 0}
    window.scene_controller.current_scene_path = "packs/core_regions/scenes/Act1_Prologue_Exterior.json"

    assert savegame.load_quick_snapshot(window, path=path) is True

    assert window.game_state_controller.get_counter("gold", 0) == 5
    assert window.game_state_controller.get_flag("prologue_note_found", False) is True
    assert window.requested_scene == "packs/core_regions/scenes/Act1_Prologue_Cabin.json"

    # Idempotent: applying snapshot again is stable.
    assert savegame.load_quick_snapshot(window, path=path) is True
    assert window.game_state_controller.get_counter("gold", 0) == 5
    assert window.game_state_controller.get_flag("prologue_note_found", False) is True
