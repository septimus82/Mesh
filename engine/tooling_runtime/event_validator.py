from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


class EventValidatorCore:
    def __init__(self, workspace_root: Path):
        self.root = workspace_root
        self.events_path = self.root / "assets/data/events.json"
        self.quests_path = self.root / "assets/data/quests.json"
        self.scenes_dir = self.root / "scenes"

        self.defined_events: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def load_definitions(self):
        if not self.events_path.exists():
            self.errors.append(f"Events catalog not found at {self.events_path}")
            return

        try:
            with open(self.events_path, "r") as f:
                data = json.load(f)
                events_list = data.get("events", [])
                self.defined_events = {e["name"]: e for e in events_list}
        except Exception as e:
            self.errors.append(f"Failed to load events catalog: {e}")

    def validate_event_ref(self, event_name: str, context: str):
        if not event_name:
            return  # Empty event name might be valid in some contexts (optional) or handled elsewhere

        if event_name not in self.defined_events:
            self.errors.append(f"[{context}] Undefined event '{event_name}'")
            return

    def validate_quests(self):
        if not self.quests_path.exists():
            return

        try:
            with open(self.quests_path, "r") as f:
                data = json.load(f)

            quests = data.get("quests", [])
            if isinstance(quests, dict):
                quests = quests.values()

            for quest in quests:
                qid = quest.get("id", "unknown")

                # Check quest triggers
                for trigger in ["start_on_event", "complete_on_event", "fail_on_event"]:
                    evt = quest.get(trigger)
                    if evt:
                        self.validate_event_ref(evt.get("type"), f"Quest {qid} {trigger}")

                # Check stages
                stages = quest.get("stages", [])
                for stage in stages:
                    sid = stage.get("id", "unknown")

                    # Stage completion
                    complete_on = stage.get("complete_on")
                    if complete_on:
                        # It can be a list or single object
                        if isinstance(complete_on, dict):
                            self.validate_event_ref(complete_on.get("type"), f"Quest {qid} Stage {sid} complete_on")
                        elif isinstance(complete_on, list):
                            for item in complete_on:
                                self.validate_event_ref(item.get("type"), f"Quest {qid} Stage {sid} complete_on")

        except Exception as e:
            self.errors.append(f"Failed to validate quests: {e}")

    def validate_scenes(self):
        if not self.scenes_dir.exists():
            return

        for scene_file in sorted(self.scenes_dir.glob("*.json"), key=lambda p: p.name):
            try:
                with open(scene_file, "r") as f:
                    scene = json.load(f)

                scene_name = scene_file.name
                entities = scene.get("entities", [])

                for entity in entities:
                    eid = entity.get("id", "unknown")
                    behaviours = entity.get("behaviours", [])
                    behaviour_config = entity.get("behaviour_config", {})

                    # Check SetGameStateOnEvent
                    if "SetGameStateOnEvent" in behaviours:
                        cfg = behaviour_config.get("SetGameStateOnEvent", {})
                        self.validate_event_ref(
                            cfg.get("event_type"),
                            f"Scene {scene_name} Entity {eid} SetGameStateOnEvent",
                        )

                    # Check EmitEventOnEvent
                    if "EmitEventOnEvent" in behaviours:
                        cfg = behaviour_config.get("EmitEventOnEvent", {})
                        self.validate_event_ref(
                            cfg.get("listen_event"),
                            f"Scene {scene_name} Entity {eid} EmitEventOnEvent listen",
                        )
                        self.validate_event_ref(
                            cfg.get("emit_event"),
                            f"Scene {scene_name} Entity {eid} EmitEventOnEvent emit",
                        )

            except Exception as e:
                self.errors.append(f"Failed to validate scene {scene_file}: {e}")

    def run(self) -> int:
        self.load_definitions()
        if self.errors:  # Stop if catalog load failed
            self.print_report()
            return 1

        self.validate_quests()
        self.validate_scenes()

        self.print_report()
        return 1 if self.errors else 0

    def print_report(self):
        if not self.errors and not self.warnings:
            print("Events validation passed.")
        else:
            for err in self.errors:
                print(f"ERROR: {err}")
            for warn in self.warnings:
                print(f"WARN: {warn}")


def main(argv: List[str] | None = None) -> int:
    validator = EventValidatorCore(Path("."))
    return validator.run()


if __name__ == "__main__":
    sys.exit(main())

