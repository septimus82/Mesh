from __future__ import annotations

import json
from pathlib import Path

from engine.content_audit import ContentAuditor
from engine.content_packs import load_pack


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_minimal_content_tree(root: Path) -> None:
    _write_json(root / "assets/data/events.json", {"events": [{"name": "ep.entered", "description": "e", "payload": {}}]})
    _write_json(root / "assets/data/quests.json", {"quests": [{"id": "q1", "title": "q", "description": "d", "stages": []}]})
    _write_json(root / "cutscenes.json", {"cutscenes": [{"id": "c1", "steps": []}]})
    _write_json(
        root / "assets/data/dialogues.json",
        {
            "dialogues": [
                {
                    "id": "d1",
                    "schema_version": 1,
                    "start_node": "start",
                    "script": {"start": {"speaker": "n", "text": "t", "choices": []}},
                }
            ]
        },
    )
    _write_json(root / "assets/prefabs.json", [{"id": "player", "entity": {"behaviours": [], "behaviour_config": {}}}])
    _write_json(root / "scenes/s1.json", {"name": "s1", "entities": [{"id": "player", "prefab_id": "player", "x": 0, "y": 0}]})


def test_load_pack_exempt(tmp_path: Path) -> None:
    manifest = {
        "id": "test_pack",
        "audit_exempt": True,
        "wip": True,
        "audit_policy_override": {"max_unused_assets": 100},
    }
    pack_dir = tmp_path / "test_pack"
    pack_dir.mkdir()
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pack = load_pack(pack_dir)
    assert pack.audit_exempt is True
    assert pack.wip is True
    assert pack.audit_policy_override["max_unused_assets"] == 100


def test_legacy_allow_packs_is_explicitly_reported_as_adapter_warning(tmp_path: Path, monkeypatch) -> None:
    _build_minimal_content_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    report = ContentAuditor("worlds/main.json").audit(allow_packs=["pack1"], ignore_patterns=["assets/*"])
    issue_codes = [str(item.get("code", "")) for item in report["integrity_issues"] if isinstance(item, dict)]
    assert "content.audit_legacy.allow_packs_ignored" in issue_codes
    assert "content.audit_legacy.ignore_patterns_ignored" in issue_codes
