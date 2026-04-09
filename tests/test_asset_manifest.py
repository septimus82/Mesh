"""Tests for asset manifest generation and dependency auditing.

Tests cover:
- Manifest determinism (stable across runs)
- Missing dependency detection with blame chain
- Asset type classification
- Schema migration compatibility
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tooling.asset_manifest import (
    AssetReference,
    DependencyReport,
    ManifestEntry,
    MissingDependency,
    audit_dependencies,
    build_manifest,
    compute_sha256,
    extract_dependencies,
    get_asset_type,
    scan_asset_roots,
)
from tests._typing import as_any


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "asset_manifest"


@pytest.fixture
def fixture_repo() -> Path:
    """Return the path to the test fixtures repo root."""
    return FIXTURES_ROOT


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a minimal temporary repo structure."""
    # Create assets directory
    assets = tmp_path / "assets"
    sprites = assets / "sprites"
    sprites.mkdir(parents=True)

    # Create a test image
    test_png = sprites / "test.png"
    test_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # Create scenes directory
    scenes = tmp_path / "scenes"
    scenes.mkdir(parents=True)

    # Create a test scene
    scene_data = {
        "name": "test_scene",
        "schema_version": 1,
        "entities": [
            {"name": "player", "sprite": "assets/sprites/test.png", "x": 0, "y": 0}
        ],
    }
    (scenes / "test.json").write_text(json.dumps(scene_data), encoding="utf-8")

    return tmp_path


# --------------------------------------------------------------------------- #
# Asset Type Classification
# --------------------------------------------------------------------------- #


class TestAssetTypeClassification:
    """Tests for get_asset_type()."""

    def test_image_types(self) -> None:
        """Image file extensions are classified correctly."""
        assert get_asset_type(Path("test.png")) == "image"
        assert get_asset_type(Path("test.jpg")) == "image"
        assert get_asset_type(Path("test.jpeg")) == "image"
        assert get_asset_type(Path("test.bmp")) == "image"
        assert get_asset_type(Path("test.gif")) == "image"
        assert get_asset_type(Path("test.webp")) == "image"

    def test_audio_types(self) -> None:
        """Audio file extensions are classified correctly."""
        assert get_asset_type(Path("test.wav")) == "audio"
        assert get_asset_type(Path("test.ogg")) == "audio"
        assert get_asset_type(Path("test.mp3")) == "audio"
        assert get_asset_type(Path("test.flac")) == "audio"

    def test_font_types(self) -> None:
        """Font file extensions are classified correctly."""
        assert get_asset_type(Path("test.ttf")) == "font"
        assert get_asset_type(Path("test.otf")) == "font"

    def test_data_types(self) -> None:
        """Data file extensions are classified correctly."""
        assert get_asset_type(Path("test.json")) == "json"
        assert get_asset_type(Path("test.yaml")) == "yaml"
        assert get_asset_type(Path("test.yml")) == "yaml"

    def test_shader_types(self) -> None:
        """Shader file extensions are classified correctly."""
        assert get_asset_type(Path("test.glsl")) == "shader"
        assert get_asset_type(Path("test.vert")) == "shader"
        assert get_asset_type(Path("test.frag")) == "shader"

    def test_unknown_type(self) -> None:
        """Unknown extensions default to 'other'."""
        assert get_asset_type(Path("test.xyz")) == "other"
        assert get_asset_type(Path("test")) == "other"

    def test_case_insensitive(self) -> None:
        """Extension matching is case-insensitive."""
        assert get_asset_type(Path("test.PNG")) == "image"
        assert get_asset_type(Path("test.OGG")) == "audio"


# --------------------------------------------------------------------------- #
# Manifest Building
# --------------------------------------------------------------------------- #


class TestManifestBuilding:
    """Tests for build_manifest() and scan_asset_roots()."""

    def test_manifest_has_required_fields(self, temp_repo: Path) -> None:
        """Manifest contains all required top-level fields."""
        manifest = build_manifest(temp_repo)

        assert "version" in manifest
        assert "repo_root" in manifest
        assert "asset_count" in manifest
        assert "assets" in manifest
        assert manifest["version"] == 1

    def test_asset_entries_have_required_fields(self, temp_repo: Path) -> None:
        """Each asset entry has all required fields."""
        manifest = build_manifest(temp_repo)
        assert manifest["asset_count"] > 0

        for asset in manifest["assets"]:
            assert "id" in asset
            assert "type" in asset
            assert "sha256" in asset
            assert "size" in asset
            assert "mtime" in asset

    def test_manifest_determinism(self, temp_repo: Path) -> None:
        """Manifest is deterministic across multiple runs."""
        manifest1 = build_manifest(temp_repo)
        manifest2 = build_manifest(temp_repo)

        # Remove mtime for comparison (can change between runs)
        for m in [manifest1, manifest2]:
            for asset in m["assets"]:
                asset.pop("mtime", None)
            m.pop("repo_root", None)

        assert manifest1 == manifest2

    def test_manifest_sorted_by_asset_id(self, temp_repo: Path) -> None:
        """Assets are sorted alphabetically by ID."""
        manifest = build_manifest(temp_repo)
        asset_ids = [a["id"] for a in manifest["assets"]]
        assert asset_ids == sorted(asset_ids)

    def test_sha256_is_correct(self, temp_repo: Path) -> None:
        """SHA256 hashes are computed correctly."""
        # Create a known file
        test_file = temp_repo / "assets" / "test.txt"
        test_file.write_bytes(b"hello world")

        manifest = build_manifest(temp_repo)
        
        # Find the test.txt entry
        txt_asset = next((a for a in manifest["assets"] if a["id"].endswith("test.txt")), None)
        assert txt_asset is not None

        # Verify hash
        expected_hash = compute_sha256(test_file)
        assert txt_asset["sha256"] == expected_hash


class TestManifestDeterminismWithFixtures:
    """Tests for manifest determinism using real fixtures."""

    def test_fixture_manifest_stable(self, fixture_repo: Path) -> None:
        """Manifest from fixtures is stable across runs."""
        manifest1 = build_manifest(fixture_repo)
        manifest2 = build_manifest(fixture_repo)

        # Asset IDs should be identical
        ids1 = [a["id"] for a in manifest1["assets"]]
        ids2 = [a["id"] for a in manifest2["assets"]]
        assert ids1 == ids2

        # Hashes should be identical
        hashes1 = [a["sha256"] for a in manifest1["assets"]]
        hashes2 = [a["sha256"] for a in manifest2["assets"]]
        assert hashes1 == hashes2


# --------------------------------------------------------------------------- #
# Dependency Extraction
# --------------------------------------------------------------------------- #


class TestDependencyExtraction:
    """Tests for extract_dependencies()."""

    def test_extracts_scene_sprite_refs(self, fixture_repo: Path) -> None:
        """Scene sprite references are extracted."""
        report = extract_dependencies(fixture_repo)

        sprite_refs = [r for r in report.references if "sprite" in r.field_path.lower()]
        assert len(sprite_refs) > 0

    def test_extracts_music_refs(self, fixture_repo: Path) -> None:
        """Scene music references are extracted."""
        report = extract_dependencies(fixture_repo)

        music_refs = [r for r in report.references if "music" in r.field_path.lower()]
        assert len(music_refs) > 0

    def test_extracts_prefab_refs(self, fixture_repo: Path) -> None:
        """Prefab sprite references are extracted."""
        report = extract_dependencies(fixture_repo)

        prefab_refs = [r for r in report.references if r.source_type == "prefab"]
        assert len(prefab_refs) > 0

    def test_references_sorted_deterministically(self, fixture_repo: Path) -> None:
        """References are sorted for determinism."""
        report1 = extract_dependencies(fixture_repo)
        report2 = extract_dependencies(fixture_repo)

        refs1 = [(r.source_file, r.field_path, r.asset_id) for r in report1.references]
        refs2 = [(r.source_file, r.field_path, r.asset_id) for r in report2.references]

        assert refs1 == refs2


# --------------------------------------------------------------------------- #
# Dependency Auditing
# --------------------------------------------------------------------------- #


class TestDependencyAuditing:
    """Tests for audit_dependencies()."""

    def test_detects_missing_dependencies(self, fixture_repo: Path) -> None:
        """Missing asset references are detected."""
        report = audit_dependencies(fixture_repo)

        # Our fixtures have intentional missing references
        assert len(report.missing) > 0

    def test_missing_deps_have_blame_chain(self, fixture_repo: Path) -> None:
        """Missing dependencies include blame chain (reference info)."""
        report = audit_dependencies(fixture_repo)

        for dep in report.missing:
            assert len(dep.references) > 0
            for ref in dep.references:
                assert ref.source_file != ""
                assert ref.field_path != ""

    def test_missing_deps_have_hints(self, fixture_repo: Path) -> None:
        """Missing dependencies include actionable hints."""
        report = audit_dependencies(fixture_repo)

        for dep in report.missing:
            assert dep.hint != ""
            # Hints should be actionable
            assert "create" in dep.hint.lower() or "use" in dep.hint.lower() or "update" in dep.hint.lower()

    def test_known_missing_assets_detected(self, fixture_repo: Path) -> None:
        """Specific missing assets from fixtures are detected."""
        report = audit_dependencies(fixture_repo)

        missing_ids = {d.asset_id for d in report.missing}

        # These are intentionally missing in our fixtures
        assert "assets/sprites/missing_ghost.png" in missing_ids
        assert "assets/sprites/nonexistent_sprite.png" in missing_ids

    def test_report_ok_false_when_missing(self, fixture_repo: Path) -> None:
        """Report.ok is False when there are missing dependencies."""
        report = audit_dependencies(fixture_repo)
        assert not report.ok

    def test_report_serializable(self, fixture_repo: Path) -> None:
        """Report can be serialized to JSON."""
        report = audit_dependencies(fixture_repo)
        report_dict = report.to_dict()

        # Should not raise
        json_str = json.dumps(report_dict, indent=2, sort_keys=True)
        assert len(json_str) > 0

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "ok" in parsed
        assert "missing" in parsed
        assert "references" in parsed


class TestDependencyAuditingCleanRepo:
    """Tests for audit_dependencies() with a clean repo (no missing deps)."""

    def test_clean_repo_has_no_missing(self, temp_repo: Path) -> None:
        """A clean repo with all assets present has no missing deps."""
        report = audit_dependencies(temp_repo)

        # temp_repo fixture has all required assets
        assert len(report.missing) == 0
        assert report.ok


# --------------------------------------------------------------------------- #
# Data Classes
# --------------------------------------------------------------------------- #


class TestManifestEntry:
    """Tests for ManifestEntry dataclass."""

    def test_to_dict(self) -> None:
        """ManifestEntry.to_dict() produces expected structure."""
        entry = ManifestEntry(
            asset_id="assets/test.png",
            asset_type="image",
            sha256="abc123",
            size=1024,
            mtime=1234567890.0,
        )
        d = entry.to_dict()

        assert d["id"] == "assets/test.png"
        assert d["type"] == "image"
        assert d["sha256"] == "abc123"
        assert d["size"] == 1024
        assert d["mtime"] == 1234567890.0

    def test_immutable(self) -> None:
        """ManifestEntry is immutable (frozen)."""
        entry = ManifestEntry(
            asset_id="test",
            asset_type="image",
            sha256="abc",
            size=0,
            mtime=0.0,
        )
        with pytest.raises(AttributeError):
            as_any(entry).asset_id = "changed"


class TestAssetReference:
    """Tests for AssetReference dataclass."""

    def test_to_dict(self) -> None:
        """AssetReference.to_dict() produces expected structure."""
        ref = AssetReference(
            asset_id="assets/test.png",
            source_file="scenes/test.json",
            source_type="scene",
            entity_name="player",
            field_path="entities[0].sprite",
        )
        d = ref.to_dict()

        assert d["asset_id"] == "assets/test.png"
        assert d["source_file"] == "scenes/test.json"
        assert d["source_type"] == "scene"
        assert d["entity_name"] == "player"
        assert d["field_path"] == "entities[0].sprite"


class TestMissingDependency:
    """Tests for MissingDependency dataclass."""

    def test_to_dict(self) -> None:
        """MissingDependency.to_dict() produces expected structure."""
        ref = AssetReference(
            asset_id="missing.png",
            source_file="scene.json",
            source_type="scene",
            entity_name="entity",
            field_path="sprite",
        )
        dep = MissingDependency(
            asset_id="missing.png",
            references=[ref],
            hint="Create the file",
        )
        d = dep.to_dict()

        assert d["asset_id"] == "missing.png"
        assert len(d["references"]) == 1
        assert d["hint"] == "Create the file"


class TestDependencyReport:
    """Tests for DependencyReport dataclass."""

    def test_ok_when_empty(self) -> None:
        """Report.ok is True when no missing deps or errors."""
        report = DependencyReport()
        assert report.ok

    def test_not_ok_with_missing(self) -> None:
        """Report.ok is False when there are missing deps."""
        ref = AssetReference("a", "b", "c", "d", "e")
        dep = MissingDependency("missing", [ref], "hint")
        report = DependencyReport(missing=[dep])
        assert not report.ok

    def test_not_ok_with_errors(self) -> None:
        """Report.ok is False when there are errors."""
        report = DependencyReport(errors=["Some error"])
        assert not report.ok


# --------------------------------------------------------------------------- #
# Integration Tests
# --------------------------------------------------------------------------- #


class TestEndToEndWorkflow:
    """Integration tests for the full manifest + audit workflow."""

    def test_build_then_audit(self, fixture_repo: Path) -> None:
        """Build manifest then audit deps uses same asset set."""
        manifest = build_manifest(fixture_repo)
        report = audit_dependencies(fixture_repo, manifest=manifest)

        # All detected missing deps should NOT be in the manifest
        manifest_ids = {a["id"] for a in manifest["assets"]}
        for dep in report.missing:
            assert dep.asset_id not in manifest_ids

    def test_output_files_are_valid_json(self, temp_repo: Path) -> None:
        """Output manifest and report are valid JSON."""
        manifest = build_manifest(temp_repo)
        report = audit_dependencies(temp_repo, manifest=manifest)

        # Serialize and parse back
        manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
        report_json = json.dumps(report.to_dict(), indent=2, sort_keys=True)

        # Should not raise
        json.loads(manifest_json)
        json.loads(report_json)
