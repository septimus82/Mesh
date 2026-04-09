"""Tests for engine.provenance module."""
from __future__ import annotations

import platform as _platform
import sys

import pytest

from engine.provenance import (
    Provenance,
    format_provenance_text,
    get_provenance,
    provenance_to_dict,
)
from tests._typing import as_any


class TestProvenanceDataclass:
    """Provenance is frozen and has sane defaults."""

    def test_frozen(self) -> None:
        prov = Provenance()
        with pytest.raises(AttributeError):
            as_any(prov).tool_name = "X"

    def test_defaults(self) -> None:
        prov = Provenance()
        assert prov.tool_name == "Mesh Engine"
        assert prov.tool_version == ""
        assert prov.build_timestamp_utc is None
        assert prov.git_commit is None
        assert prov.git_dirty is None
        assert prov.git_describe is None


class TestGetProvenance:
    """get_provenance returns a populated snapshot."""

    def test_has_tool_version(self) -> None:
        prov = get_provenance()
        assert prov.tool_version != ""
        assert prov.tool_version != "unknown"

    def test_has_python_version(self) -> None:
        prov = get_provenance()
        assert prov.python_version == _platform.python_version()

    def test_has_platform(self) -> None:
        prov = get_provenance()
        assert prov.platform == sys.platform

    def test_deterministic_omits_timestamp(self) -> None:
        prov = get_provenance(deterministic=True)
        assert prov.build_timestamp_utc is None

    def test_non_deterministic_has_timestamp(self) -> None:
        prov = get_provenance(deterministic=False)
        assert prov.build_timestamp_utc is not None
        assert "T" in prov.build_timestamp_utc


class TestProvenanceToDict:
    """provenance_to_dict produces a stable dict."""

    def test_required_keys(self) -> None:
        prov = get_provenance()
        d = provenance_to_dict(prov)
        assert "tool_name" in d
        assert "tool_version" in d
        assert "python_version" in d
        assert "platform" in d

    def test_omits_none_fields(self) -> None:
        prov = Provenance()
        d = provenance_to_dict(prov)
        assert "build_timestamp_utc" not in d
        assert "git_commit" not in d

    def test_includes_non_none_fields(self) -> None:
        prov = Provenance(git_commit="abc123", git_dirty=False)
        d = provenance_to_dict(prov)
        assert d["git_commit"] == "abc123"
        assert d["git_dirty"] is False

    def test_deterministic_no_timestamp(self) -> None:
        prov = get_provenance(deterministic=True)
        d = provenance_to_dict(prov)
        assert "build_timestamp_utc" not in d

    def test_roundtrip_to_provenance(self) -> None:
        """Dict can reconstruct a Provenance via **kwargs."""
        prov = get_provenance(deterministic=True)
        d = provenance_to_dict(prov)
        rebuilt = Provenance(**d)
        assert rebuilt.tool_name == prov.tool_name
        assert rebuilt.tool_version == prov.tool_version


class TestFormatProvenanceText:
    """format_provenance_text produces human-readable output."""

    def test_contains_tool_line(self) -> None:
        prov = get_provenance()
        text = format_provenance_text(prov)
        assert "Mesh Engine" in text

    def test_contains_python(self) -> None:
        prov = get_provenance()
        text = format_provenance_text(prov)
        assert "Python:" in text

    def test_contains_platform(self) -> None:
        prov = get_provenance()
        text = format_provenance_text(prov)
        assert "Platform:" in text

    def test_dirty_shown(self) -> None:
        prov = Provenance(git_commit="abc", git_dirty=True)
        text = format_provenance_text(prov)
        assert "(dirty)" in text

    def test_no_dirty_for_clean(self) -> None:
        prov = Provenance(git_commit="abc", git_dirty=False)
        text = format_provenance_text(prov)
        assert "(dirty)" not in text
        assert "abc" in text
