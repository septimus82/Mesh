"""Tests for the campaign replay-check CLI command and tooling.

Covers:
- CLI smoke: command produces expected files with deterministic content
- Determinism: run twice yields identical digest traces
- Diff: intentionally perturb one input and ensure diff detects first divergence
- Artifact paths: outputs written to correct locations with stable names
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

CAMPAIGN_ID = "mini_campaign_01"
SCRIPT_PATH = Path("tests/fixtures/campaign_scripts/mini_campaign_01.json")


def _load_script() -> Dict[str, Any]:
    return json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Unit tests for the headless replay harness
# ---------------------------------------------------------------------------


class TestCampaignReplayHarness:
    """Tests for tooling.campaign_replay module."""

    @pytest.mark.fast
    def test_script_exists(self) -> None:
        """Campaign script fixture file exists and is valid JSON."""
        assert SCRIPT_PATH.exists(), f"Missing fixture: {SCRIPT_PATH}"
        script = _load_script()
        assert script["campaign_id"] == CAMPAIGN_ID
        assert len(script["scenes"]) == 3

    @pytest.mark.fast
    def test_single_run_produces_result(self) -> None:
        """A single replay run returns a CampaignReplayResult with data."""
        from tooling.campaign_replay import load_campaign_script, run_campaign_replay

        script = load_campaign_script(CAMPAIGN_ID)
        result = run_campaign_replay(script)

        # Must have digest entries
        assert len(result.tracker.digests) > 0
        # Must have checkpoints
        assert "after_town" in result.checkpoints
        assert "after_puzzle" in result.checkpoints
        assert "after_combat" in result.checkpoints
        # Must have milestone log
        assert len(result.milestone_log) > 0
        # Must have final flags
        assert len(result.final_flags) > 0

    @pytest.mark.fast
    def test_determinism_two_runs_identical(self) -> None:
        """Two runs with the same script produce identical digest traces."""
        from tooling.campaign_replay import (
            load_campaign_script,
            run_campaign_replay,
            diff_traces,
        )

        script = load_campaign_script(CAMPAIGN_ID)
        r1 = run_campaign_replay(script)
        r2 = run_campaign_replay(script)

        t1 = r1.to_trace_dict()
        t2 = r2.to_trace_dict()

        # Digest dicts must be identical
        assert t1["digests"] == t2["digests"], (
            f"Digest mismatch: run1 has {len(t1['digests'])} entries, "
            f"run2 has {len(t2['digests'])} entries"
        )

        # Diff must report identical
        diff = diff_traces(t1, t2)
        assert diff["identical"] is True
        assert diff["first_divergence_tick"] is None
        assert len(diff["mismatches"]) == 0

    @pytest.mark.fast
    def test_determinism_final_flags_match(self) -> None:
        """Two runs produce identical final flag snapshots."""
        from tooling.campaign_replay import load_campaign_script, run_campaign_replay

        script = load_campaign_script(CAMPAIGN_ID)
        r1 = run_campaign_replay(script)
        r2 = run_campaign_replay(script)

        assert r1.final_flags == r2.final_flags
        # Campaign flags should be set
        assert r1.final_flags.get("campaign.started") is True

    @pytest.mark.fast
    def test_determinism_milestones_match(self) -> None:
        """Milestone logs are identical across deterministic runs."""
        from tooling.campaign_replay import load_campaign_script, run_campaign_replay

        script = load_campaign_script(CAMPAIGN_ID)
        r1 = run_campaign_replay(script)
        r2 = run_campaign_replay(script)

        assert len(r1.milestone_log) == len(r2.milestone_log)
        for m1, m2 in zip(r1.milestone_log, r2.milestone_log):
            assert m1["tick"] == m2["tick"]
            assert m1["digest"] == m2["digest"]

    @pytest.mark.fast
    def test_checkpoints_contain_quest_state(self) -> None:
        """Checkpoint bundles include quest state."""
        from tooling.campaign_replay import load_campaign_script, run_campaign_replay

        script = load_campaign_script(CAMPAIGN_ID)
        result = run_campaign_replay(script)

        for label in ("after_town", "after_puzzle", "after_combat"):
            cp = result.checkpoints[label]
            assert "quest_state" in cp
            assert "flags" in cp
            assert "label" in cp
            assert cp["label"] == label

    @pytest.mark.fast
    def test_diff_detects_perturbation(self) -> None:
        """When one trace is perturbed, diff reports the first divergence."""
        from tooling.campaign_replay import diff_traces

        # Build two traces that are identical except at tick 3
        trace_a: Dict[str, Any] = {
            "digests": {"1": "aaa", "2": "bbb", "3": "ccc", "4": "ddd"},
        }
        trace_b: Dict[str, Any] = {
            "digests": {"1": "aaa", "2": "bbb", "3": "DIFFERENT", "4": "ddd"},
        }

        diff = diff_traces(trace_a, trace_b)
        assert diff["identical"] is False
        assert diff["first_divergence_tick"] == 3
        assert len(diff["mismatches"]) == 1
        assert diff["mismatches"][0]["tick"] == 3

    @pytest.mark.fast
    def test_diff_empty_traces_are_identical(self) -> None:
        """Two empty traces are identical."""
        from tooling.campaign_replay import diff_traces

        diff = diff_traces({"digests": {}}, {"digests": {}})
        assert diff["identical"] is True
        assert diff["first_divergence_tick"] is None

    @pytest.mark.fast
    def test_format_diff_text(self) -> None:
        """format_diff_text produces readable output."""
        from tooling.campaign_replay import format_diff_text

        diff_identical = {
            "identical": True,
            "first_divergence_tick": None,
            "mismatches": [],
            "total_ticks": 10,
            "summary": "Traces identical (10 ticks)",
        }
        text = format_diff_text(diff_identical)
        assert "IDENTICAL" in text
        assert "10" in text

        diff_divergent = {
            "identical": False,
            "first_divergence_tick": 3,
            "mismatches": [{"tick": 3, "digest_a": "aaa", "digest_b": "bbb"}],
            "total_ticks": 10,
            "summary": "DIVERGENCE at tick 3",
        }
        text = format_diff_text(diff_divergent)
        assert "DIVERGENT" in text
        assert "tick 3" in text

    @pytest.mark.fast
    def test_trace_dict_is_json_serializable(self) -> None:
        """CampaignReplayResult.to_trace_dict() is JSON-serializable."""
        from tooling.campaign_replay import load_campaign_script, run_campaign_replay

        script = load_campaign_script(CAMPAIGN_ID)
        result = run_campaign_replay(script)
        trace = result.to_trace_dict()

        # Must not raise
        text = json.dumps(trace, sort_keys=True, indent=2)
        parsed = json.loads(text)
        assert parsed["digests"] == trace["digests"]


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCampaignReplayCheckCLI:
    """Tests for the mesh_cli campaign replay-check command."""

    @pytest.mark.fast
    def test_cli_smoke_produces_expected_files(self, tmp_path: Path) -> None:
        """CLI command produces all expected output files."""
        from mesh_cli.campaign import _handle_replay_check
        import argparse

        args = argparse.Namespace(
            campaign=CAMPAIGN_ID,
            out_dir=str(tmp_path),
            json=False,
        )
        exit_code = _handle_replay_check(args)
        assert exit_code == 0, "replay-check should exit 0 for deterministic runs"

        expected_files = [
            "run_1_digest_trace.json",
            "run_2_digest_trace.json",
            "digest_diff.txt",
            "debug_bundle_checkpoint_after_town.json",
            "debug_bundle_checkpoint_after_puzzle.json",
            "debug_bundle_checkpoint_after_combat.json",
        ]
        for fname in expected_files:
            fpath = tmp_path / fname
            assert fpath.exists(), f"Missing expected output: {fname}"
            assert fpath.stat().st_size > 0, f"Output is empty: {fname}"

    @pytest.mark.fast
    def test_cli_json_mode(self, tmp_path: Path) -> None:
        """CLI --json flag produces digest_diff.json."""
        from mesh_cli.campaign import _handle_replay_check
        import argparse

        args = argparse.Namespace(
            campaign=CAMPAIGN_ID,
            out_dir=str(tmp_path),
            json=True,
        )
        exit_code = _handle_replay_check(args)
        assert exit_code == 0

        diff_json_path = tmp_path / "digest_diff.json"
        assert diff_json_path.exists()
        diff = json.loads(diff_json_path.read_text(encoding="utf-8"))
        assert diff["identical"] is True

    @pytest.mark.fast
    def test_cli_deterministic_traces(self, tmp_path: Path) -> None:
        """Both trace files have identical digests."""
        from mesh_cli.campaign import _handle_replay_check
        import argparse

        args = argparse.Namespace(
            campaign=CAMPAIGN_ID,
            out_dir=str(tmp_path),
            json=False,
        )
        _handle_replay_check(args)

        t1 = json.loads((tmp_path / "run_1_digest_trace.json").read_text(encoding="utf-8"))
        t2 = json.loads((tmp_path / "run_2_digest_trace.json").read_text(encoding="utf-8"))
        assert t1["digests"] == t2["digests"]

    @pytest.mark.fast
    def test_cli_artifact_paths_stable(self, tmp_path: Path) -> None:
        """Output artifact names are stable across multiple invocations."""
        from mesh_cli.campaign import _handle_replay_check
        import argparse

        args = argparse.Namespace(
            campaign=CAMPAIGN_ID,
            out_dir=str(tmp_path),
            json=False,
        )
        _handle_replay_check(args)
        files_run1 = sorted(f.name for f in tmp_path.iterdir() if f.is_file())

        # Run again — should produce same set of files
        _handle_replay_check(args)
        files_run2 = sorted(f.name for f in tmp_path.iterdir() if f.is_file())

        assert files_run1 == files_run2

    @pytest.mark.fast
    def test_cli_checkpoint_content_valid(self, tmp_path: Path) -> None:
        """Checkpoint debug bundles contain valid state snapshots."""
        from mesh_cli.campaign import _handle_replay_check
        import argparse

        args = argparse.Namespace(
            campaign=CAMPAIGN_ID,
            out_dir=str(tmp_path),
            json=False,
        )
        _handle_replay_check(args)

        for label in ("after_town", "after_puzzle", "after_combat"):
            cp_path = tmp_path / f"debug_bundle_checkpoint_{label}.json"
            cp = json.loads(cp_path.read_text(encoding="utf-8"))
            assert cp["label"] == label
            assert "flags" in cp
            assert "quest_state" in cp
            assert isinstance(cp["tick"], int)

    @pytest.mark.fast
    def test_cli_handles_unknown_campaign(self, tmp_path: Path) -> None:
        """CLI exits with code 2 for unknown campaign id."""
        from mesh_cli.campaign import _handle_replay_check
        import argparse

        args = argparse.Namespace(
            campaign="nonexistent_campaign",
            out_dir=str(tmp_path),
            json=False,
        )
        exit_code = _handle_replay_check(args)
        assert exit_code == 2

    @pytest.mark.fast
    def test_campaign_command_handle_dispatch(self) -> None:
        """campaign handle() returns 2 for missing subcommand."""
        from mesh_cli.campaign import handle
        import argparse

        args = argparse.Namespace(campaign_command=None)
        assert handle(args) == 2

    @pytest.mark.fast
    def test_diff_text_file_content(self, tmp_path: Path) -> None:
        """digest_diff.txt contains IDENTICAL for deterministic runs."""
        from mesh_cli.campaign import _handle_replay_check
        import argparse

        args = argparse.Namespace(
            campaign=CAMPAIGN_ID,
            out_dir=str(tmp_path),
            json=False,
        )
        _handle_replay_check(args)

        txt = (tmp_path / "digest_diff.txt").read_text(encoding="utf-8")
        assert "IDENTICAL" in txt
