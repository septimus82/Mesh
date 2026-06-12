import os
import tempfile
import unittest

from engine.config import EngineConfig
from engine.events import MeshEvent, MeshEventBus
from engine.tooling.event_trace import read_event_jsonl, write_event_jsonl
from engine.tooling.trace_command import HeadlessGame


class TestEventTrace(unittest.TestCase):
    def test_structured_history(self):
        bus = MeshEventBus()
        bus.emit(MeshEvent("test_event", {"foo": "bar"}))

        history = bus.get_recent_events(1)
        self.assertEqual(len(history), 1)
        event_dict = history[0]
        self.assertEqual(event_dict["name"], "test_event")
        self.assertEqual(event_dict["payload"], {"foo": "bar"})
        self.assertIn("timestamp", event_dict)

    def test_schema_version(self):
        # Verify schema version is injected
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as tmp:
            tmp_path = tmp.name

        try:
            write_event_jsonl(tmp_path, {"name": "test", "payload": {}})
            events = list(read_event_jsonl(tmp_path))
            self.assertEqual(len(events), 1)
            self.assertIn("schema_version", events[0])
            self.assertEqual(events[0]["schema_version"], 1)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_recorder_hook(self):
        bus = MeshEventBus()
        recorded = []

        def recorder(e):
            recorded.append(e)

        bus.set_recorder(recorder)
        bus.emit(MeshEvent("e1", {}))
        bus.emit(MeshEvent("e2", {}))

        self.assertEqual(len(recorded), 2)
        self.assertEqual(recorded[0]["name"], "e1")
        self.assertEqual(recorded[1]["name"], "e2")

    def test_trace_cycle(self):
        # 1. Record events to a temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as tmp:
            tmp_path = tmp.name

        try:
            # Write events
            events_to_write = [
                {"name": "quest_start", "payload": {"quest_id": "test_quest"}},
                {"name": "died", "payload": {"name": "rat", "mesh_tag": "enemy"}},
                {"name": "died", "payload": {"name": "rat", "mesh_tag": "enemy"}},
            ]

            for e in events_to_write:
                write_event_jsonl(tmp_path, e)

            # 2. Replay into HeadlessGame
            config = EngineConfig() # Defaults
            game = HeadlessGame(config)

            received_events = []
            game.event_bus.subscribe_all(lambda e: received_events.append(e))

            # Verify logic can be driven by replay
            counters = {"kills": 0}
            def on_died(e):
                counters["kills"] += 1
            game.event_bus.subscribe("died", on_died)

            for event_dict in read_event_jsonl(tmp_path):
                event = MeshEvent(
                    type=event_dict["name"],
                    payload=event_dict.get("payload", {})
                )
                game.event_bus.emit_event(event)
                game.update()

            self.assertEqual(len(received_events), 3)
            self.assertEqual(received_events[0].type, "quest_start")
            self.assertEqual(received_events[1].type, "died")
            self.assertEqual(counters["kills"], 2)

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
