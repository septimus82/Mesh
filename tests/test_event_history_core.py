import unittest

from engine.events import MeshEvent, MeshEventBus


class TestEventHistoryCore(unittest.TestCase):
    def test_history_buffer(self):
        bus = MeshEventBus()

        # Emit some events
        for i in range(60):
            bus.emit(MeshEvent(f"event_{i}", {}))

        # Check history limit (default 50)
        history = bus.get_recent_events(100)
        self.assertEqual(len(history), 50)
        self.assertEqual(history[0]["name"], "event_10")
        self.assertEqual(history[-1]["name"], "event_59")

    def test_get_recent(self):
        bus = MeshEventBus()
        bus.emit(MeshEvent("e1", {}))
        bus.emit(MeshEvent("e2", {}))
        bus.emit(MeshEvent("e3", {}))

        recent = bus.get_recent_events(2)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["name"], "e2")
        self.assertEqual(recent[1]["name"], "e3")

if __name__ == "__main__":
    unittest.main()
