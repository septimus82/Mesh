import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.content_lock import build_lock, write_lock, read_lock, compute_content_fingerprint
from engine.content_packs import Pack

@pytest.fixture
def mock_index():
    with patch("engine.content_lock.get_content_index") as mock:
        index = MagicMock()
        mock.return_value = index
        
        # Setup some dummy packs
        p1 = Pack(id="core", root=Path("/core"), version="1.0.0", type="core")
        p2 = Pack(id="mod_a", root=Path("/mod_a"), version="0.1.0", type="mod")
        index.packs = [p1, p2]
        index.entries = {}
        
        yield index

def test_build_lock(mock_index):
    # Mock _hash_file to return dummy hashes
    with patch("engine.content_lock._hash_file") as mock_hash:
        mock_hash.return_value = "dummy_hash"
        
        lock = build_lock()
        assert lock["version"] == 1
        assert len(lock["packs"]) == 2
        assert lock["packs"][0]["id"] == "core"
        assert lock["packs"][1]["id"] == "mod_a"
        assert lock["overrides"] == {}
        assert "content_files" in lock

def test_read_write_lock(tmp_path):
    lock_data = {"version": 1, "packs": [], "overrides": {}, "content_files": {}}
    p = tmp_path / "lock.json"
    write_lock(p, lock_data)
    
    loaded = read_lock(p)
    assert loaded == lock_data

def test_fingerprint_determinism():
    lock_data = {"version": 1, "packs": [], "overrides": {}, "content_files": {"a": "b"}}
    fp1 = compute_content_fingerprint(lock_data)
    fp2 = compute_content_fingerprint(lock_data)
    assert fp1 == fp2
    assert len(fp1) == 64 # SHA-256 hex digest length
