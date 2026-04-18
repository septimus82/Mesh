import pytest
from unittest.mock import MagicMock, patch
from engine.config import EngineConfig
from engine.content_lock import compute_strict_fingerprint
from engine.tooling.replay_goldens_command import handle_replay_goldens
from argparse import Namespace
from pathlib import Path

def test_strict_fingerprint_determinism():
    # Test that strict fingerprint only cares about content_files
    lock1 = {
        "content_files": {"a": "hash1"},
        "audit_snapshot": {"unused": 100}
    }
    lock2 = {
        "content_files": {"a": "hash1"},
        "audit_snapshot": {"unused": 0}
    }
    assert compute_strict_fingerprint(lock1) == compute_strict_fingerprint(lock2)
    
    lock3 = {
        "content_files": {"a": "hash2"},
        "audit_snapshot": {"unused": 100}
    }
    assert compute_strict_fingerprint(lock1) != compute_strict_fingerprint(lock3)

@patch("engine.tooling.replay_goldens_command.build_lock")
@patch("engine.tooling.replay_goldens_command.compute_strict_fingerprint")
@patch("engine.tooling.replay_goldens_command.load_config")
@patch("pathlib.Path.exists")
@patch("pathlib.Path.glob")
@patch("engine.tooling.trace_command.read_event_jsonl")
@patch("engine.tooling.trace_command.HeadlessGame")
@patch("engine.tooling.trace_command.verify_assertions")
def test_strict_golden_failure(mock_verify, mock_game, mock_read_events, mock_glob, mock_exists, mock_load_config, mock_compute_fp, mock_build_lock):
    # Setup mocks
    mock_exists.return_value = True
    mock_path = MagicMock()
    mock_path.name = "trace1.jsonl"
    mock_path.with_suffix.return_value = mock_path # simplify
    mock_glob.return_value = [mock_path]
    mock_read_events.return_value = []
    mock_verify.return_value = True
    mock_load_config.return_value = EngineConfig()
    
    # Mock meta file read
    mock_path.read_text.return_value = '{"content_fingerprint": "expected_hash"}'
    
    # Mock fingerprint mismatch
    mock_compute_fp.return_value = "actual_hash"
    
    args = Namespace(strict=True, world="worlds/main_world.json")
    
    # Should fail
    assert handle_replay_goldens(args) == 1

@patch("engine.tooling.replay_goldens_command.build_lock")
@patch("engine.tooling.replay_goldens_command.compute_strict_fingerprint")
@patch("engine.tooling.replay_goldens_command.load_config")
@patch("pathlib.Path.exists")
@patch("pathlib.Path.glob")
@patch("engine.tooling.trace_command.read_event_jsonl")
@patch("engine.tooling.trace_command.HeadlessGame")
@patch("engine.tooling.trace_command.verify_assertions")
def test_strict_golden_success(mock_verify, mock_game, mock_read_events, mock_glob, mock_exists, mock_load_config, mock_compute_fp, mock_build_lock):
    # Setup mocks
    mock_exists.return_value = True
    mock_path = MagicMock()
    mock_path.name = "trace1.jsonl"
    mock_path.with_suffix.return_value = mock_path # simplify
    mock_glob.return_value = [mock_path]
    mock_read_events.return_value = []
    mock_verify.return_value = True
    mock_load_config.return_value = EngineConfig()
    
    # Mock meta file read
    mock_path.read_text.return_value = '{"content_fingerprint": "expected_hash"}'
    
    # Mock fingerprint match
    mock_compute_fp.return_value = "expected_hash"
    
    args = Namespace(strict=True, world="worlds/main_world.json")
    
    # Should pass
    assert handle_replay_goldens(args) == 0
