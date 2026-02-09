"""Contract tests for BOM-safe JSON loading.

Ensures that:
- JSON with a leading UTF-8 BOM parses correctly.
- JSON without BOM still parses identically.
- A deterministic log warning is emitted when a BOM is stripped.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from engine.json_io import read_json, loads_safe, _strip_bom


# ---------------------------------------------------------------------------
# _strip_bom unit tests
# ---------------------------------------------------------------------------

class TestStripBom:
    def test_strips_leading_bom(self) -> None:
        assert _strip_bom("\ufeff{}", source="test") == "{}"

    def test_no_bom_unchanged(self) -> None:
        assert _strip_bom("{}", source="test") == "{}"

    def test_empty_string_unchanged(self) -> None:
        assert _strip_bom("", source="test") == ""

    def test_bom_only(self) -> None:
        assert _strip_bom("\ufeff", source="test") == ""

    def test_warning_emitted_on_bom(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="engine.json_io"):
            _strip_bom("\ufeff{}", source="my_file.json")
        assert "Stripped UTF-8 BOM from JSON source: my_file.json" in caplog.text

    def test_no_warning_without_bom(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="engine.json_io"):
            _strip_bom("{}", source="my_file.json")
        assert "BOM" not in caplog.text


# ---------------------------------------------------------------------------
# loads_safe
# ---------------------------------------------------------------------------

class TestLoadsSafe:
    def test_parses_bom_prefixed_json(self) -> None:
        result = loads_safe('\ufeff{"key": 1}')
        assert result == {"key": 1}

    def test_parses_normal_json(self) -> None:
        result = loads_safe('{"key": 2}')
        assert result == {"key": 2}

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            loads_safe("{bad")

    def test_bom_json_array(self) -> None:
        result = loads_safe("\ufeff[1, 2, 3]")
        assert result == [1, 2, 3]


# ---------------------------------------------------------------------------
# read_json (file-based)
# ---------------------------------------------------------------------------

class TestReadJson:
    def test_reads_bom_file(self, tmp_path: Path) -> None:
        f = tmp_path / "bom.json"
        f.write_bytes(b"\xef\xbb\xbf" + b'{"ok": true}')
        assert read_json(f) == {"ok": True}

    def test_reads_normal_file(self, tmp_path: Path) -> None:
        f = tmp_path / "normal.json"
        f.write_text('{"ok": true}', encoding="utf-8")
        assert read_json(f) == {"ok": True}

    def test_bom_file_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        f = tmp_path / "warn.json"
        f.write_bytes(b"\xef\xbb\xbf" + b'{"a": 1}')
        with caplog.at_level(logging.WARNING, logger="engine.json_io"):
            read_json(f)
        assert "Stripped UTF-8 BOM" in caplog.text
        assert "warn.json" in caplog.text

    def test_non_bom_file_no_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        f = tmp_path / "clean.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="engine.json_io"):
            read_json(f)
        assert "BOM" not in caplog.text
