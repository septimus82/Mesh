from __future__ import annotations

import json
from pathlib import Path

import mesh_cli
from mesh_cli.content_integrity import content_audit_report_to_json, run_content_audit


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_minimums() -> dict[str, int]:
    return {
        "events": 1,
        "quests": 1,
        "cutscenes": 1,
        "dialogues": 1,
        "prefabs": 1,
        "scenes": 1,
    }


def _build_valid_content_fixture(root: Path) -> None:
    _write_json(
        root / "assets/data/events.json",
        {
            "events": [
                {"name": "episode_entered", "description": "enter", "payload": {}},
                {"name": "episode_done", "description": "done", "payload": {}},
                {"name": "quest_complete", "description": "quest", "payload": {}},
            ]
        },
    )
    _write_json(
        root / "assets/data/quests.json",
        {
            "quests": [
                {
                    "id": "episode_01",
                    "title": "Episode 01",
                    "description": "desc",
                    "stages": [
                        {"id": "stage0", "title": "Start", "text": "start", "complete_on": "episode_entered"},
                        {
                            "id": "stage1",
                            "title": "Finish",
                            "text": "finish",
                            "complete_on": "episode_done",
                            "emit_events_on_complete": ["quest_complete"],
                        },
                    ],
                }
            ]
        },
    )
    _write_json(
        root / "cutscenes.json",
        {
            "cutscenes": [
                {
                    "id": "episode_intro",
                    "steps": [{"type": "emit_event", "event": "episode_entered"}],
                    "commands": [
                        {"type": "emit_event", "event_type": "episode_entered"},
                        {"type": "start_dialogue", "dialogue_id": "episode_dialogue_intro"},
                        {"type": "stop"},
                    ],
                }
            ]
        },
    )
    _write_json(
        root / "assets/data/dialogues.json",
        {
            "dialogues": [
                {
                    "id": "episode_dialogue_intro",
                    "schema_version": 1,
                    "start_node": "start",
                    "script": {
                        "start": {
                            "speaker": "Mentor",
                            "text": "Ready?",
                            "choices": [{"text": "Yes", "next": "end"}],
                        },
                        "end": {"speaker": "Mentor", "text": "Go.", "next": None},
                    },
                }
            ]
        },
    )
    _write_json(
        root / "assets/prefabs.json",
        [
            {
                "id": "player",
                "entity": {"behaviours": [], "behaviour_config": {}},
            },
            {
                "id": "episode_controller",
                "entity": {
                    "behaviours": ["ActionListRunner"],
                    "behaviour_config": {
                        "ActionListRunner": {
                            "listen_events": ["episode_entered"],
                            "actions": [{"type": "emit_event", "event_type": "episode_done"}],
                        }
                    },
                },
            },
        ],
    )
    _write_json(
        root / "scenes/episode_01.json",
        {
            "name": "Episode 01",
            "entities": [
                {"id": "player", "prefab_id": "player", "x": 0, "y": 0},
                {"id": "controller", "prefab_id": "episode_controller", "x": 0, "y": 0},
            ],
        },
    )


def test_content_audit_happy_path_real_repo_is_clean() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report = run_content_audit(repo_root)
    assert report.ok is True
    assert report.errors == ()
    assert report.stats["events"] >= 100
    assert report.stats["scenes"] >= 10


def test_content_audit_deterministic_on_same_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    first = run_content_audit(repo_root)
    second = run_content_audit(repo_root)
    assert first.to_dict() == second.to_dict()
    assert content_audit_report_to_json(first) == content_audit_report_to_json(second)


def test_content_audit_missing_prefab_error_includes_file_and_pointer(tmp_path: Path) -> None:
    _build_valid_content_fixture(tmp_path)
    scene_path = tmp_path / "scenes/episode_01.json"
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    scene["entities"][1]["prefab_id"] = "missing_prefab"
    _write_json(scene_path, scene)

    report = run_content_audit(tmp_path, minimum_counts=_make_minimums())
    assert report.ok is False
    issue = next(err for err in report.errors if err.code == "content.scenes.missing_prefab")
    assert issue.file == "scenes/episode_01.json"
    assert issue.pointer.endswith("/prefab_id")


def test_content_audit_missing_event_error_includes_file_and_pointer(tmp_path: Path) -> None:
    _build_valid_content_fixture(tmp_path)
    scene_path = tmp_path / "scenes/episode_01.json"
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    scene["entities"].append(
        {
            "id": "extra_ctrl",
            "prefab_id": "episode_controller",
            "x": 0,
            "y": 0,
            "behaviour_config": {
                "ActionListRunner": {
                    "listen_events": ["event_not_cataloged"],
                    "actions": [],
                }
            },
        }
    )
    _write_json(scene_path, scene)

    report = run_content_audit(tmp_path, minimum_counts=_make_minimums())
    assert report.ok is False
    issue = next(err for err in report.errors if err.code == "content.events.missing_reference")
    assert issue.file == "scenes/episode_01.json"
    assert issue.pointer.endswith("/listen_events/0")


def test_content_audit_invalid_dialogue_choice_next_reports_pointer(tmp_path: Path) -> None:
    _build_valid_content_fixture(tmp_path)
    dialogue_path = tmp_path / "assets/data/dialogues.json"
    dialogues = json.loads(dialogue_path.read_text(encoding="utf-8"))
    dialogues["dialogues"][0]["script"]["start"]["choices"][0]["next"] = "missing_node"
    _write_json(dialogue_path, dialogues)

    report = run_content_audit(tmp_path, minimum_counts=_make_minimums())
    assert report.ok is False
    issue = next(err for err in report.errors if err.code == "content.dialogues.invalid_choice_next")
    assert issue.file == "assets/data/dialogues.json"
    assert issue.pointer.endswith("/choices/0/next")


def test_cli_content_audit_writes_reports(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    out_dir = tmp_path / "audit_artifacts"
    rc = mesh_cli.main(["content", "audit", "--out-dir", str(out_dir), "--quiet"])
    assert rc == 0
    json_report = out_dir / "content_audit_report.json"
    txt_report = out_dir / "content_audit_report.txt"
    assert json_report.exists()
    assert txt_report.exists()
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["schema_version"] == 1
