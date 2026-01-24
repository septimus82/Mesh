import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from engine.config import EngineConfig, load_config
from engine.constants import EVENT_COLLECTED
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.inventory import get_or_create_inventory
from engine.tooling.event_trace import read_event_jsonl, write_event_jsonl


# Minimal headless game context for replay
class HeadlessGame:
    def __init__(self, config: EngineConfig):
        self.config = config
        self.event_bus = MeshEventBus()
        self.game_state_controller = GameStateController(self) # type: ignore
        # GameStateController has .quests, not .quest_manager
        self.quest_manager = self.game_state_controller.quests
        # We need to mimic GameWindow's event consumption for QuestManager
        self.event_bus.subscribe_all(self._on_event)
        self._event_queue: List[MeshEvent] = []

        # Mock SceneController for SaveManager compatibility
        self.scene_controller = MockSceneController()

        # In-memory save storage for headless replay
        self._saves: Dict[str, Any] = {}

        # Disable auto-completion in lightweight quest manager during replay
        # because it lacks full logic (stages) and might prematurely complete quests.
        self.game_state_controller.quests.update_quest_states = (  # type: ignore[method-assign,assignment]  # intentional headless monkeypatch
            lambda game_state: None
        )

        # Load quest definitions so we can track state
        self._load_quests()

    def _load_quests(self) -> None:
        """Load quest definitions from common locations."""
        paths = [
            Path("assets/data/quests.json"),
            Path("packs/core_regions/assets/data/quests.json"),
        ]
        for p in paths:
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                quests = data.get("quests", [])
                for q in quests:
                    if isinstance(q, dict):
                        self.quest_manager.register_quest(q)
            except Exception as e:
                print(f"[Headless] Failed to load quests from {p}: {e}")

    @property
    def game_state(self):
        return self.game_state_controller.state

    def _on_event(self, event: MeshEvent) -> None:
        self._event_queue.append(event)

        # Handle quest state updates based on events (since we don't run full quest logic)
        if event.type in ("quest_start", "QUEST_START"):
            q_id = event.payload.get("quest_id")
            if q_id:
                q = self.quest_manager._quests.get(q_id)
                if q:
                    q.state = "active"
        elif event.type in ("quest_completed", "QUEST_COMPLETED"):
            q_id = event.payload.get("quest_id")
            if q_id:
                q = self.quest_manager._quests.get(q_id)
                if q:
                    q.state = "completed"
        elif event.type == EVENT_COLLECTED:
            item_id = event.payload.get("item_id")
            amount = event.payload.get("amount", 1)
            if item_id:
                inv = get_or_create_inventory(self.game_state.values)
                inv.add_item(item_id, amount)

    def update(self):
        # Process events for GameStateController
        events = list(self._event_queue)
        self._event_queue.clear()

        for event in events:
            try:
                # Handle debug state updates for headless testing
                if event.type == "DEBUG_SET_FLAG":
                    flag = event.payload.get("flag")
                    value = event.payload.get("value", True)
                    if flag:
                        self.game_state_controller.state.flags[flag] = value
                elif event.type == "DEBUG_SET_COUNTER":
                    counter = event.payload.get("counter")
                    value = event.payload.get("value", 0)
                    if counter:
                        self.game_state_controller.state.counters[counter] = float(value)

                # Handle Save/Load events in headless mode
                elif event.type == "SAVE_GAME":
                    slot = event.payload.get("slot", "autosave")
                    state = self.game_state_controller.state.snapshot()
                    self._saves[slot] = state
                    print(f"[Headless] Saved game to slot '{slot}'")

                elif event.type == "LOAD_GAME":
                    slot = event.payload.get("slot", "autosave")
                    if slot in self._saves:
                        self.game_state_controller.state.restore(self._saves[slot])
                        print(f"[Headless] Loaded game from slot '{slot}'")
                    else:
                        print(f"[Headless] Failed to load game from slot '{slot}' (not found)")

                # Handle damage events (simulated)
                elif event.type == "damage_applied":
                    # In a real game, this would reduce HP.
                    # In headless replay, we might just log it or trigger death if fatal.
                    # For now, we assume the trace is authoritative about what happens.
                    pass

                self.game_state_controller.handle_event(event)

            except Exception as e:
                print(f"[Headless] Error processing event {event.type}: {e}")

class MockSceneController:
    def __init__(self):
        self.current_scene_path = "headless/scene.json"

    def build_scene_snapshot(self, compact: bool = False) -> Dict[str, Any]:
        return {
            "path": self.current_scene_path,
            "entities": [],
            "layers": []
        }

    def request_scene_change(self, path: str) -> None:
        self.current_scene_path = path


def verify_assertions(game: HeadlessGame, assertions_path: str) -> bool:
    try:
        with open(assertions_path, "r") as f:
            assertions = json.load(f)
    except Exception as e:
        print(f"[Trace] Failed to load assertions: {e}")
        return False

    state = game.game_state_controller.state
    ok = True

    # Check flags
    for k, v in assertions.get("flags", {}).items():
        actual_flag = state.flags.get(k, False)
        if actual_flag != v:
            print(f"[FAIL] Flag '{k}': expected {v}, got {actual_flag}")
            ok = False

    # Check counters
    for k, v in assertions.get("global_counters", {}).items():
        actual_counter = state.counters.get(k, 0)
        if actual_counter != v:
            print(f"[FAIL] Counter '{k}': expected {v}, got {actual_counter}")
            ok = False

    # Check quest counters (flattened in state.counters)
    for q_id, counters in assertions.get("quest_counters", {}).items():
        for k, v in counters.items():
            full_key = f"quest:{q_id}:{k}"
            actual_quest_counter = state.counters.get(full_key, 0)
            if actual_quest_counter != v:
                print(f"[FAIL] Quest Counter '{full_key}': expected {v}, got {actual_quest_counter}")
                ok = False

    # Check quest states
    quests = game.game_state_controller.quests._quests
    for q_id, status in assertions.get("quests", {}).items():
        q = quests.get(q_id)
        actual_quest_status = q.state if q else "missing"
        if actual_quest_status != status:
            print(f"[FAIL] Quest '{q_id}': expected {status}, got {actual_quest_status}")
            ok = False

    # Check inventory
    inv = get_or_create_inventory(state.values)
    for item_id, count in assertions.get("inventory", {}).items():
        actual_inventory = inv.get_count(item_id)
        if actual_inventory != count:
            print(f"[FAIL] Inventory '{item_id}': expected {count}, got {actual_inventory}")
            ok = False

    return ok

def handle_trace(args: argparse.Namespace) -> int:
    if args.record:
        # Record mode: Launch actual game with recorder
        from engine.game import GameWindow

        config = load_config()
        if args.world:
            config.world_file = args.world
        if args.overlay:
            config.debug_mode = True

        window = GameWindow(
            width=config.width,
            height=config.height,
            title=config.title,
            fullscreen=config.fullscreen,
            vsync=config.vsync,
            config=config,
            config_path="config.json",
        )

        # Setup recorder
        metadata = {
            "world_file": args.world,
            "start_scene": config.start_scene,
        }

        def recorder(event_dict: Dict[str, Any]):
            write_event_jsonl(args.record, event_dict, metadata)

        window.event_bus.set_recorder(recorder)

        # Load start scene
        try:
            window.load_scene(config.start_scene)
        except Exception as e:
            print(f"[Trace] Failed to load scene: {e}")
            return 1

        window.run()
        return 0

    elif args.replay:
        # Replay mode: Headless replay
        print(f"[Trace] Replaying from {args.replay}...")
        config = load_config()
        game = HeadlessGame(config)

        count = 0
        for event_dict in read_event_jsonl(args.replay):
            # Reconstruct event
            event = MeshEvent(
                type=event_dict["name"],
                payload=event_dict.get("payload", {})
            )
            # Emit
            game.event_bus.emit_event(event)
            # Update systems
            game.update()
            count += 1

        print(f"[Trace] Replayed {count} events.")

        if args.assert_file:
            if verify_assertions(game, args.assert_file):
                print("[Trace] Assertions PASSED.")
                return 0
            else:
                print("[Trace] Assertions FAILED.")
                return 1

        # Dump final state for verification?
        print("Final Counters:", game.game_state_controller.state.counters)
        return 0

    else:
        print("Must specify --record or --replay")
        return 1
