from __future__ import annotations

import json

import pytest


pytestmark = [pytest.mark.fast]


def test_cli_parser_registers_package_player_subcommand() -> None:
    from mesh_cli.main import create_parser

    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    choices = set(subparsers_action.choices.keys())
    assert "package-player" in choices


def test_player_package_manifest_schema_and_sorting_contract() -> None:
    from engine.runtime_only import FORBIDDEN_EDITOR_PREFIXES
    from mesh_cli.player_package import build_manifest_payload

    payload = build_manifest_payload(
        package_root="artifacts/player_pkg",
        included_files=["mesh_cli/main.py", "engine/runtime_only/entry.py", "config.json"],
        excluded_prefixes=list(reversed(FORBIDDEN_EDITOR_PREFIXES)),
        content_roots_included=["scenes"],
        total_bytes=1234,
        forbidden_hits=[],
    )

    assert set(payload.keys()) == {
        "schema_version",
        "created_by",
        "package_root",
        "included_files",
        "excluded_prefixes",
        "runtime_entry",
        "content_roots_included",
        "checks",
    }
    assert payload["schema_version"] == 1
    assert payload["created_by"] == "mesh_cli package-player"
    assert payload["package_root"] == "artifacts/player_pkg"
    assert payload["included_files"] == sorted(payload["included_files"])
    assert payload["excluded_prefixes"] == sorted(payload["excluded_prefixes"])
    for prefix in FORBIDDEN_EDITOR_PREFIXES:
        assert prefix in payload["excluded_prefixes"]

    checks = payload["checks"]
    assert isinstance(checks, dict)
    assert set(checks.keys()) == {"file_count", "total_bytes", "forbidden_hits"}
    assert checks["file_count"] == 3
    assert checks["total_bytes"] == 1234
    assert checks["forbidden_hits"] == []


def test_player_package_manifest_deterministic_json_ordering_contract() -> None:
    from engine.persistence_io import dumps_json_deterministic
    from mesh_cli.player_package import build_manifest_payload

    payload = build_manifest_payload(
        package_root="artifacts/player_pkg",
        included_files=["b.py", "a.py"],
        excluded_prefixes=["engine.editor", "engine.ui_overlays"],
        content_roots_included=["scenes"],
        total_bytes=2,
        forbidden_hits=[],
    )

    rendered = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
    assert rendered == dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
    roundtrip = json.loads(rendered)
    assert roundtrip == payload
    top_level_lines = [line for line in rendered.splitlines() if line.startswith('  "')]
    top_level_keys = [line.split('"')[1] for line in top_level_lines[:8]]
    assert top_level_keys == sorted(top_level_keys)
