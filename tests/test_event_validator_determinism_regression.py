from __future__ import annotations

import json
from pathlib import Path

from engine.tooling_runtime.event_validator import EventValidatorCore


def test_event_validator_scene_iteration_is_sorted_by_name(tmp_path) -> None:
    root = Path(tmp_path)
    (root / "assets" / "data").mkdir(parents=True, exist_ok=True)
    (root / "scenes").mkdir(parents=True, exist_ok=True)

    (root / "assets" / "data" / "events.json").write_text(
        json.dumps({"events": [{"name": "known"}]}, indent=2),
        encoding="utf-8",
    )

    # Two scenes that reference different unknown events; ordering must follow filename sort.
    (root / "scenes" / "b.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "id": "E",
                        "behaviours": ["EmitEventOnEvent"],
                        "behaviour_config": {"EmitEventOnEvent": {"listen_event": "missing_b"}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "scenes" / "a.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "id": "E",
                        "behaviours": ["EmitEventOnEvent"],
                        "behaviour_config": {"EmitEventOnEvent": {"listen_event": "missing_a"}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    v = EventValidatorCore(root)
    v.load_definitions()
    assert not v.errors
    v.validate_scenes()

    assert v.errors == [
        "[Scene a.json Entity E EmitEventOnEvent listen] Undefined event 'missing_a'",
        "[Scene b.json Entity E EmitEventOnEvent listen] Undefined event 'missing_b'",
    ]

