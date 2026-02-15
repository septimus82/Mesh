from __future__ import annotations

import json
from pathlib import Path

from engine.content_audit import ContentAuditor, audit_world, run_content_audit


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_minimal_content_tree(root: Path) -> None:
    _write_json(
        root / "assets/data/events.json",
        {"events": [{"name": "ep.entered", "description": "entered", "payload": {}}]},
    )
    _write_json(
        root / "assets/data/quests.json",
        {"quests": [{"id": "ep01", "title": "EP01", "description": "d", "stages": []}]},
    )
    _write_json(
        root / "cutscenes.json",
        {"cutscenes": [{"id": "ep01_intro", "steps": []}]},
    )
    _write_json(
        root / "assets/data/dialogues.json",
        {
            "dialogues": [
                {
                    "id": "ep01_dialogue",
                    "schema_version": 1,
                    "start_node": "start",
                    "script": {
                        "start": {"speaker": "Mentor", "text": "hello", "choices": []},
                    },
                }
            ]
        },
    )
    _write_json(
        root / "assets/prefabs.json",
        [{"id": "player", "entity": {"behaviours": [], "behaviour_config": {}}}],
    )
    _write_json(
        root / "scenes/episode_01.json",
        {"name": "EP01", "entities": [{"id": "player", "prefab_id": "player", "x": 0, "y": 0}]},
    )


def test_audit_world_returns_legacy_shape(tmp_path: Path, monkeypatch) -> None:
    _build_minimal_content_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    report = audit_world("worlds/main_world.json")
    assert isinstance(report, dict)
    assert isinstance(report["ok"], bool)
    assert isinstance(report["unused_assets"], list)
    assert isinstance(report["unused_prefabs"], list)
    assert isinstance(report["unused_items"], list)
    assert isinstance(report["unused_quests"], list)
    assert isinstance(report["stats"], dict)
    assert isinstance(report["integrity_issues"], list)
    assert "integrity" in report
    assert "report" in report["integrity"]


def test_content_auditor_and_run_content_audit_delegate_consistently(tmp_path: Path, monkeypatch) -> None:
    _build_minimal_content_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    via_function = audit_world("worlds/main_world.json")
    via_entrypoint = run_content_audit("worlds/main_world.json")
    via_class = ContentAuditor("worlds/main_world.json").audit()

    assert via_function["ok"] == via_entrypoint["ok"] == via_class["ok"]
    assert via_function["stats"] == via_entrypoint["stats"] == via_class["stats"]
    assert via_function["integrity_issues"] == via_entrypoint["integrity_issues"] == via_class["integrity_issues"]
