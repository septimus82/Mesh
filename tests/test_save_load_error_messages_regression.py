from __future__ import annotations

import json
from pathlib import Path

from engine.persistence_io import SAVE_FORMAT_VERSION
from engine.save_runtime import io as save_io


def test_snapshot_future_version_error_is_single_line(tmp_path) -> None:
    path = tmp_path / "quick.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "save_format_version": SAVE_FORMAT_VERSION + 1,
                "version": 1,
                "world_file": "worlds/act1_prologue.json",
                "world_id": "act1_prologue",
                "scene_id": "packs/core_regions/scenes/Act1_Prologue_Cabin.json",
                "gold": 1,
                "flags": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    ok, payload_or_error = save_io.load_snapshot_payload(path)
    assert ok is False
    msg = str(payload_or_error)
    assert msg.startswith("[Mesh][Snapshot] ERROR: Unsupported save_format_version")
    assert "\n" not in msg


def test_snapshot_invalid_json_returns_deterministic_error_prefix(tmp_path) -> None:
    path = tmp_path / "quick.json"
    path.write_text("{", encoding="utf-8")
    ok, payload_or_error = save_io.load_snapshot_payload(path)
    assert ok is False
    msg = str(payload_or_error)
    assert msg.startswith("[Mesh][Snapshot] ERROR:")
    assert "\n" not in msg


def test_slot_missing_file_message_is_deterministic(tmp_path) -> None:
    missing = tmp_path / "missing.json"
    ok, payload_or_error = save_io.load_slot_payload(missing)
    assert ok is False
    assert str(payload_or_error) == f"[Mesh][Save] Save file '{missing}' not found"

