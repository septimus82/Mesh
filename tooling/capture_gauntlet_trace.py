import os

from engine.config import load_config
from engine.game import GameWindow
from engine.tooling import scaffold
from engine.tooling.event_trace import write_event_jsonl


def main():
    # 1. Generate Scene
    scene_path = "packs/dev_sandbox/scenes/gauntlet_test.json"
    if os.path.exists(scene_path):
        os.remove(scene_path)

    extra_args = {
        "encounter_layout": "gauntlet",
        "difficulty": "normal",
        "region_theme": "moss" # Ensure we have a theme for spawns
    }
    scaffold.create_scene(scene_path, template_name="dungeon", extra_args=extra_args)

    # 2. Capture Trace
    config = load_config()
    config.start_scene = scene_path

    window = GameWindow(
        width=800,
        height=600,
        title="Trace Capture",
        config=config
    )

    window.load_scene(config.start_scene)

    # Run a few frames
    for _ in range(10):
        window.on_update(1/60.0)

    # Inspect entities
    events = []
    scene_controller = window.scene_controller
    for layer_name, sprite_list in scene_controller.layers.items():
        for sprite in sprite_list:
            pid = getattr(sprite, "mesh_entity_data", {}).get("prefab_id")
            # Only care about enemies for this trace
            if pid and pid != "player":
                event = {
                    "type": "entity_snapshot",
                    "payload": {
                        "name": getattr(sprite, "mesh_name", "unknown"),
                        "prefab_id": pid,
                        "layer": layer_name
                    }
                }
                events.append(event)

    # Write trace
    metadata = {
        "world_file": None,
        "start_scene": config.start_scene,
    }

    out_path = "traces/golden/encounter_layout_gauntlet_flow.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        pass # Clear

    for event in events:
        write_event_jsonl(out_path, event, metadata)
    print(f"Captured {len(events)} events to {out_path}")

if __name__ == "__main__":
    main()
