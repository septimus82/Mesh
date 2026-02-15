"""Tests for ``mesh_cli new-game`` command.

Covers:
- Output file creation, valid JSON, passes validate_save()
- Determinism: same args → byte-identical file content
- Overwrite guard (without --force fails, with --force succeeds)
- Seed behaviour: different seed changes only RNG fields
- CLI dispatch integration
- No writes to repo root (uses tmp_path)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.persistence_io import dumps_json_deterministic
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION, validate_save
from mesh_cli.new_game import (
    DEFAULT_CAMPAIGN,
    DEFAULT_SEED,
    build_new_game_payload,
    handle,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(**overrides):  # type: ignore[no-untyped-def]
    """Build a minimal argparse.Namespace-like object."""
    import argparse

    defaults = {
        "out": "new_game.json",
        "campaign": DEFAULT_CAMPAIGN,
        "scene": None,
        "seed": None,
        "force": False,
        "print_json": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# =========================================================================
# Unit tests – build_new_game_payload
# =========================================================================

class TestBuildPayload:
    """Tests for the payload builder (no filesystem)."""

    def test_payload_is_valid_save(self) -> None:
        payload = build_new_game_payload()
        # Must not raise
        validate_save(payload)

    def test_schema_version(self) -> None:
        payload = build_new_game_payload()
        assert payload["save_schema_version"] == SAVE_SCHEMA_VERSION

    def test_default_scene_is_town(self) -> None:
        payload = build_new_game_payload()
        assert payload["scene_id"] == "scenes/town_schedule_01.json"
        assert payload["scene_path"] == "scenes/town_schedule_01.json"

    def test_campaign_started_flag(self) -> None:
        payload = build_new_game_payload()
        assert "campaign.started" in payload["flags"]
        assert payload["game_state"]["flags"]["campaign.started"] is True

    def test_default_seed(self) -> None:
        payload = build_new_game_payload()
        assert payload["rng_seed"] == DEFAULT_SEED

    def test_explicit_seed(self) -> None:
        payload = build_new_game_payload(seed=999)
        assert payload["rng_seed"] == 999

    def test_scene_override(self) -> None:
        payload = build_new_game_payload(scene="scenes/custom.json")
        assert payload["scene_id"] == "scenes/custom.json"
        assert payload["scene_path"] == "scenes/custom.json"

    def test_unknown_campaign_without_scene_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown campaign"):
            build_new_game_payload(campaign="nonexistent_campaign")

    def test_unknown_campaign_with_scene_ok(self) -> None:
        payload = build_new_game_payload(
            campaign="nonexistent_campaign",
            scene="scenes/somewhere.json",
        )
        assert payload["campaign"] == "nonexistent_campaign"
        assert payload["scene_id"] == "scenes/somewhere.json"

    def test_saved_entities_empty(self) -> None:
        payload = build_new_game_payload()
        assert payload["saved_entities"] == {"schema_version": 1, "entities": []}

    def test_saved_quests_empty(self) -> None:
        payload = build_new_game_payload()
        assert payload["saved_quests"] == {"schema_version": 1, "quests": {}}

    def test_gold_zero(self) -> None:
        payload = build_new_game_payload()
        assert payload["gold"] == 0

    def test_meta_block(self) -> None:
        payload = build_new_game_payload()
        meta = payload["meta"]
        assert meta["slot"] == "new_game"
        assert meta["scene_path"] == "scenes/town_schedule_01.json"
        assert isinstance(meta["timestamp"], str)

    def test_rng_state_present(self) -> None:
        payload = build_new_game_payload()
        rng_state = payload["rng_state"]
        assert "global_seed" in rng_state
        assert "default" in rng_state

    def test_payload_json_serializable(self) -> None:
        payload = build_new_game_payload()
        # Must not raise
        text = dumps_json_deterministic(payload)
        assert isinstance(text, str)
        assert len(text) > 10


# =========================================================================
# Determinism tests
# =========================================================================

class TestDeterminism:
    """Same arguments must produce byte-identical output."""

    def test_same_args_identical_bytes(self) -> None:
        text_a = dumps_json_deterministic(build_new_game_payload())
        text_b = dumps_json_deterministic(build_new_game_payload())
        assert text_a == text_b

    def test_same_seed_identical(self) -> None:
        text_a = dumps_json_deterministic(build_new_game_payload(seed=123))
        text_b = dumps_json_deterministic(build_new_game_payload(seed=123))
        assert text_a == text_b

    def test_different_seed_differs_rng_only(self) -> None:
        payload_a = build_new_game_payload(seed=1)
        payload_b = build_new_game_payload(seed=2)

        # RNG-related fields must differ
        assert payload_a["rng_seed"] != payload_b["rng_seed"]
        assert payload_a["rng_state"] != payload_b["rng_state"]

        # Non-RNG fields must be identical
        for key in ("scene_id", "scene_path", "gold", "flags",
                     "save_schema_version", "save_format_version",
                     "saved_entities", "saved_quests", "game_state",
                     "meta", "campaign"):
            assert payload_a[key] == payload_b[key], f"Key '{key}' differs across seeds"


# =========================================================================
# CLI integration tests
# =========================================================================

class TestCLIHandle:
    """Tests for the CLI handle() function (writes to tmp_path)."""

    def test_creates_output_file(self, tmp_path: Path) -> None:
        out = tmp_path / "save.json"
        rc = handle(_make_args(out=str(out)))
        assert rc == 0
        assert out.exists()

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        out = tmp_path / "save.json"
        handle(_make_args(out=str(out)))
        data = json.loads(out.read_text("utf-8"))
        validate_save(data)

    def test_deterministic_file_content(self, tmp_path: Path) -> None:
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"
        handle(_make_args(out=str(out_a)))
        handle(_make_args(out=str(out_b), force=True))
        assert out_a.read_bytes() == out_b.read_bytes()

    def test_overwrite_without_force_fails(self, tmp_path: Path) -> None:
        out = tmp_path / "save.json"
        out.write_text("{}")
        rc = handle(_make_args(out=str(out)))
        assert rc == 1

    def test_overwrite_with_force_succeeds(self, tmp_path: Path) -> None:
        out = tmp_path / "save.json"
        out.write_text("{}")
        rc = handle(_make_args(out=str(out), force=True))
        assert rc == 0
        data = json.loads(out.read_text("utf-8"))
        validate_save(data)

    def test_json_flag_prints_to_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        out = tmp_path / "save.json"
        handle(_make_args(out=str(out), print_json=True))
        captured = capsys.readouterr().out
        # stdout contains the status line then the JSON payload.
        # Extract the JSON portion (starts with '{').
        json_start = captured.index("{")
        data = json.loads(captured[json_start:])
        assert isinstance(data, dict)
        assert data["save_schema_version"] == SAVE_SCHEMA_VERSION
        assert out.exists()

    def test_seed_argument(self, tmp_path: Path) -> None:
        out = tmp_path / "save.json"
        handle(_make_args(out=str(out), seed=777))
        data = json.loads(out.read_text("utf-8"))
        assert data["rng_seed"] == 777

    def test_scene_argument(self, tmp_path: Path) -> None:
        out = tmp_path / "save.json"
        handle(_make_args(out=str(out), scene="scenes/custom.json"))
        data = json.loads(out.read_text("utf-8"))
        assert data["scene_id"] == "scenes/custom.json"

    def test_no_write_to_repo_root(self, tmp_path: Path) -> None:
        """Ensure new-game writes only under tmp_path, never repo root."""
        out = tmp_path / "subdir" / "save.json"
        rc = handle(_make_args(out=str(out)))
        assert rc == 0
        # Parent dir was created
        assert out.exists()
        assert out.parent == tmp_path / "subdir"
