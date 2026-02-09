from __future__ import annotations

import json
from pathlib import Path

import mesh_cli


def test_cli_debug_diff_json_outputs_stable_payload(tmp_path, capsys) -> None:
    payload = {
        "world": {"current": "w1"},
        "lighting": {"plan_digest": "l1"},
        "render": {"plan_digest": "r1"},
        "quests": {"inspector_state": {}, "diagnostics": []},
        "cutscene": {"summary": {}},
        "events": {
            "event_type_filter": "",
            "entity_id_filter": "",
            "limit": 0,
            "total_events": 0,
            "filtered_count": 0,
        },
    }

    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    Path(path_a).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    Path(path_b).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert mesh_cli.main(["debug", "diff", "--a", str(path_a), "--b", str(path_b), "--json"]) == 0

    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["changed"] is False
    assert "digests" in data


def test_cli_debug_diff_exit_codes_default(tmp_path, capsys) -> None:
    base = {
        "world": {"current": "w1"},
        "lighting": {"plan_digest": "l1"},
        "render": {"plan_digest": "r1"},
        "quests": {"inspector_state": {}, "diagnostics": []},
        "cutscene": {"summary": {}},
        "events": {
            "event_type_filter": "",
            "entity_id_filter": "",
            "limit": 0,
            "total_events": 0,
            "filtered_count": 0,
        },
    }
    changed = dict(base)
    changed["world"] = {"current": "w2"}

    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_c = tmp_path / "c.json"
    path_a.write_text(json.dumps(base, indent=2, sort_keys=True), encoding="utf-8")
    path_b.write_text(json.dumps(base, indent=2, sort_keys=True), encoding="utf-8")
    path_c.write_text(json.dumps(changed, indent=2, sort_keys=True), encoding="utf-8")

    assert mesh_cli.main(["debug", "diff", "--a", str(path_a), "--b", str(path_b)]) == 0
    capsys.readouterr()
    assert mesh_cli.main(["debug", "diff", "--a", str(path_a), "--b", str(path_c)]) == 1


def test_cli_debug_diff_no_fail_forces_zero(tmp_path) -> None:
    base = {
        "world": {"current": "w1"},
        "lighting": {"plan_digest": "l1"},
        "render": {"plan_digest": "r1"},
        "quests": {"inspector_state": {}, "diagnostics": []},
        "cutscene": {"summary": {}},
        "events": {
            "event_type_filter": "",
            "entity_id_filter": "",
            "limit": 0,
            "total_events": 0,
            "filtered_count": 0,
        },
    }
    changed = dict(base)
    changed["world"] = {"current": "w2"}

    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(base, indent=2, sort_keys=True), encoding="utf-8")
    path_b.write_text(json.dumps(changed, indent=2, sort_keys=True), encoding="utf-8")

    assert mesh_cli.main(["debug", "diff", "--a", str(path_a), "--b", str(path_b), "--no-fail"]) == 0


def test_cli_debug_diff_quiet_suppresses_output(tmp_path, capsys) -> None:
    base = {
        "world": {"current": "w1"},
        "lighting": {"plan_digest": "l1"},
        "render": {"plan_digest": "r1"},
        "quests": {"inspector_state": {}, "diagnostics": []},
        "cutscene": {"summary": {}},
        "events": {
            "event_type_filter": "",
            "entity_id_filter": "",
            "limit": 0,
            "total_events": 0,
            "filtered_count": 0,
        },
    }
    changed = dict(base)
    changed["world"] = {"current": "w2"}

    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(base, indent=2, sort_keys=True), encoding="utf-8")
    path_b.write_text(json.dumps(changed, indent=2, sort_keys=True), encoding="utf-8")

    assert mesh_cli.main(["debug", "diff", "--a", str(path_a), "--b", str(path_b), "--quiet"]) == 1
    out = capsys.readouterr().out
    assert out == ""
