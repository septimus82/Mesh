from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from engine.content_audit import audit_world
from mesh_cli.content_integrity import run_content_audit

_WINDOWS_ABS_RE = re.compile(r"[A-Za-z]:[\\/]")
_UNIX_ABS_RE = re.compile(r"(^|[\\s\"'])/(home|users|tmp|var|etc)/", re.IGNORECASE)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_content_tree(root: Path) -> None:
    _write_json(
        root / "assets/data/events.json",
        {
            "events": [
                {"name": "ep.entered", "description": "entered", "payload": {}},
                {"name": "ep.done", "description": "done", "payload": {}},
            ]
        },
    )
    _write_json(
        root / "assets/data/quests.json",
        {
            "quests": [
                {
                    "id": "ep01",
                    "title": "Episode 01",
                    "description": "desc",
                    "stages": [{"id": "s0", "title": "S0", "text": "t", "complete_on": "ep.entered"}],
                }
            ]
        },
    )
    _write_json(
        root / "cutscenes.json",
        {
            "cutscenes": [
                {
                    "id": "ep01_intro",
                    "steps": [{"type": "emit_event", "event": "ep.entered"}],
                    "commands": [{"type": "emit_event", "event_type": "ep.entered"}, {"type": "stop"}],
                }
            ]
        },
    )
    _write_json(
        root / "assets/data/dialogues.json",
        {
            "dialogues": [
                {
                    "id": "ep01_dialogue",
                    "schema_version": 1,
                    "start_node": "start",
                    "script": {"start": {"speaker": "Mentor", "text": "hello", "choices": []}},
                }
            ]
        },
    )
    _write_json(
        root / "assets/prefabs.json",
        [
            {"id": "player", "entity": {"behaviours": [], "behaviour_config": {}}},
            {
                "id": "controller",
                "entity": {
                    "behaviours": ["ActionListRunner"],
                    "behaviour_config": {"ActionListRunner": {"listen_events": ["ep.entered"], "actions": []}},
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
                {"id": "controller", "prefab_id": "controller", "x": 0, "y": 0},
            ],
        },
    )


def _issue_triples_from_legacy(payload: dict) -> list[tuple[str, str, str]]:
    rows = payload.get("integrity_issues", [])
    filtered = [
        (
            str(item.get("file", "")),
            str(item.get("pointer", "")),
            str(item.get("code", "")),
        )
        for item in rows
        if isinstance(item, dict) and not str(item.get("code", "")).startswith("content.audit_legacy.")
    ]
    return sorted(filtered)


def _issue_triples_from_modern(payload: object) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for issue in tuple(getattr(payload, "errors", ())) + tuple(getattr(payload, "warnings", ())):
        rows.append((str(getattr(issue, "file", "")), str(getattr(issue, "pointer", "")), str(getattr(issue, "code", ""))))
    return sorted(rows)


def test_shim_matches_content_integrity_modulo_legacy_format(tmp_path: Path, monkeypatch) -> None:
    _build_content_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    modern = run_content_audit(tmp_path)
    legacy = audit_world("worlds/main_world.json")

    assert legacy["ok"] == modern.ok
    legacy_triples = _issue_triples_from_legacy(legacy)
    modern_triples = _issue_triples_from_modern(modern)
    assert len(legacy_triples) == len(modern_triples)
    assert legacy_triples == modern_triples

    legacy_text = "\n".join(f"{f}:{p}[{c}]" for f, p, c in legacy_triples)
    modern_text = "\n".join(f"{f}:{p}[{c}]" for f, p, c in modern_triples)
    assert legacy_text == modern_text


def test_shim_output_has_no_absolute_paths(tmp_path: Path, monkeypatch) -> None:
    _build_content_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    report = audit_world(str((tmp_path / "worlds/main_world.json").resolve()))
    payload_text = json.dumps(report, sort_keys=True)
    assert not _WINDOWS_ABS_RE.search(payload_text)
    assert not _UNIX_ABS_RE.search(payload_text)


def test_content_audit_module_is_shim_only_policy() -> None:
    path = Path("engine/content_audit.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    forbidden_modules = {"engine.migrations", "engine.paths"}
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
    assert not (forbidden_modules & imported_modules), (
        "content_audit shim must not reintroduce legacy scanner dependencies"
    )

    forbidden_tokens = ("get_content_index", "resolve_path", "migrate_payload")
    leaked = [token for token in forbidden_tokens if token in source]
    assert not leaked, f"content_audit shim must not contain legacy scanner logic tokens: {leaked}"

    assert "_run_content_integrity_audit(" in source, "content_audit shim must delegate to deterministic content_integrity"
