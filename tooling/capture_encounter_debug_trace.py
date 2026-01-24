import os

from engine.config import load_config
from engine.game import GameWindow
from engine.tooling.event_trace import write_event_jsonl


def main():
    config = load_config()
    config.profile = "dev"
    config.start_scene = "scenes/main_menu.json" # Any scene works

    window = GameWindow(
        width=800,
        height=600,
        title="Trace Capture",
        config=config
    )

    # Mock console log to capture output
    logs = []
    original_log = window.console_controller.log
    def mock_log(msg):
        logs.append(msg)
        original_log(msg)
    window.console_controller.log = mock_log

    # Execute command
    window.console_controller.execute_command("encounter show")

    # Verify output
    found_header = any("--- Encounter ---" in str(msg) for msg in logs)

    events = [
        {
            "type": "debug_command_result",
            "payload": {
                "command": "encounter show",
                "success": found_header,
                "logs_count": len(logs)
            }
        }
    ]

    trace_path = "traces/golden/encounter_show_debug_flow.jsonl"
    if os.path.exists(trace_path):
        os.remove(trace_path)

    for event in events:
        write_event_jsonl(trace_path, event)
    print(f"Generated {trace_path}")

if __name__ == "__main__":
    main()
