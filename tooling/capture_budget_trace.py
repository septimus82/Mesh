from engine.config import load_config
from engine.game import GameWindow
from engine.tooling.event_trace import write_event_jsonl


def main():
    config = load_config()
    config.start_scene = "packs/dev_sandbox/scenes/budget_test.json"

    window = GameWindow(
        width=800,
        height=600,
        title="Trace Capture",
        config=config
    )

    # Load scene
    window.load_scene(config.start_scene)

    # Run a few frames
    for _ in range(10):
        window.on_update(1/60)

    # Inspect entities
    events = []
    scene_controller = window.scene_controller
    for layer_name, sprite_list in scene_controller.layers.items():
        for sprite in sprite_list:
            # Check for variant info
            variant_id = getattr(sprite, "mesh_entity_data", {}).get("variant_id")
            tags = getattr(sprite, "mesh_entity_data", {}).get("tags", [])
            hp = getattr(sprite, "mesh_entity_data", {}).get("max_health")
            pid = getattr(sprite, "mesh_entity_data", {}).get("prefab_id")

            event = {
                "type": "entity_snapshot",
                "payload": {
                    "name": getattr(sprite, "mesh_name", "unknown"),
                    "prefab_id": pid,
                    "variant_id": variant_id,
                    "tags": list(tags),
                    "max_health": hp,
                    "layer": layer_name
                }
            }
            events.append(event)

    # Write trace
    metadata = {
        "world_file": None,
        "start_scene": config.start_scene,
    }

    out_path = "traces/golden/encounter_budget_moss_flow.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        pass # Clear

    for event in events:
        write_event_jsonl(out_path, event, metadata)

    print(f"Captured {len(events)} events to {out_path}")

if __name__ == "__main__":
    main()
