"""Tests for export bundle builder.

Tests cover:
- Export plan computation
- Unused asset exclusion
- Missing dependency detection
- Bundle building
- Bundle diffing
- Determinism (two exports produce identical results)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tooling.export_bundle import (
    BundleDiff,
    BundleManifest,
    ExportFile,
    ExportPlan,
    build_bundle,
    compute_export_plan,
    diff_bundles,
    load_bundle_manifest,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

FIXTURES_GOOD = Path(__file__).parent / "fixtures" / "export_bundle"
FIXTURES_BAD = Path(__file__).parent / "fixtures" / "export_bundle_bad"


@pytest.fixture
def good_repo() -> Path:
    """Return the path to the good test fixture (valid project)."""
    return FIXTURES_GOOD


@pytest.fixture
def bad_repo() -> Path:
    """Return the path to the bad test fixture (has missing deps)."""
    return FIXTURES_BAD


@pytest.fixture
def temp_bundle_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for bundle output."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    return bundle_dir


# --------------------------------------------------------------------------- #
# Export Plan Tests
# --------------------------------------------------------------------------- #


class TestExportPlan:
    """Tests for compute_export_plan()."""

    def test_plan_includes_required_assets(self, good_repo: Path) -> None:
        """Required assets are included in the plan."""
        plan = compute_export_plan(good_repo)

        included_paths = {f.rel_path for f in plan.files}

        # These sprites are referenced in scenes
        assert "assets/sprites/hero.png" in included_paths
        assert "assets/sprites/item.png" in included_paths
        assert "assets/sprites/npc.png" in included_paths

    def test_plan_excludes_unused_assets(self, good_repo: Path) -> None:
        """Unused assets are excluded from the plan."""
        plan = compute_export_plan(good_repo)

        included_paths = {f.rel_path for f in plan.files}

        # This sprite is not referenced anywhere
        assert "assets/sprites/unused_decor.png" not in included_paths
        assert "assets/sprites/unused_decor.png" in plan.excluded_assets

    def test_plan_includes_content_files(self, good_repo: Path) -> None:
        """Scene files are included."""
        plan = compute_export_plan(good_repo)

        included_paths = {f.rel_path for f in plan.files}

        assert "scenes/scene_a.json" in included_paths
        assert "scenes/scene_b.json" in included_paths

    def test_plan_includes_prefabs(self, good_repo: Path) -> None:
        """Prefabs.json is always included."""
        plan = compute_export_plan(good_repo)

        included_paths = {f.rel_path for f in plan.files}
        assert "assets/prefabs.json" in included_paths

    def test_plan_ok_with_valid_project(self, good_repo: Path) -> None:
        """Plan.ok is True for a valid project."""
        plan = compute_export_plan(good_repo)
        assert plan.ok
        assert len(plan.missing_deps) == 0

    def test_plan_fails_with_missing_deps(self, bad_repo: Path) -> None:
        """Plan.ok is False when there are missing dependencies."""
        plan = compute_export_plan(bad_repo)

        assert not plan.ok
        assert len(plan.missing_deps) > 0
        assert "assets/sprites/missing_asset.png" in plan.missing_deps

    def test_plan_include_unused_option(self, good_repo: Path) -> None:
        """include_unused=True includes all assets."""
        plan_normal = compute_export_plan(good_repo, include_unused=False)
        plan_all = compute_export_plan(good_repo, include_unused=True)

        # Should have more files with include_unused
        assert len(plan_all.files) > len(plan_normal.files)
        # Should have no excluded assets
        assert len(plan_all.excluded_assets) == 0

    def test_plan_is_deterministic(self, good_repo: Path) -> None:
        """Plan produces identical results across runs."""
        plan1 = compute_export_plan(good_repo)
        plan2 = compute_export_plan(good_repo)

        paths1 = [f.rel_path for f in plan1.files]
        paths2 = [f.rel_path for f in plan2.files]

        assert paths1 == paths2

        hashes1 = [f.sha256 for f in plan1.files]
        hashes2 = [f.sha256 for f in plan2.files]

        assert hashes1 == hashes2

    def test_plan_files_sorted(self, good_repo: Path) -> None:
        """Plan files are sorted by path."""
        plan = compute_export_plan(good_repo)

        paths = [f.rel_path for f in plan.files]
        assert paths == sorted(paths)


# --------------------------------------------------------------------------- #
# Bundle Building Tests
# --------------------------------------------------------------------------- #


class TestBundleBuilding:
    """Tests for build_bundle()."""

    def test_build_creates_bundle_directory(self, good_repo: Path, tmp_path: Path) -> None:
        """Build creates the output directory."""
        output_dir = tmp_path / "test_bundle"

        exit_code, manifest = build_bundle(good_repo, output_dir)

        assert exit_code == 0
        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_build_creates_manifest(self, good_repo: Path, tmp_path: Path) -> None:
        """Build creates bundle_manifest.json."""
        output_dir = tmp_path / "test_bundle"

        exit_code, manifest = build_bundle(good_repo, output_dir)

        assert exit_code == 0
        manifest_path = output_dir / "bundle_manifest.json"
        assert manifest_path.exists()

    def test_build_manifest_has_required_fields(self, good_repo: Path, tmp_path: Path) -> None:
        """Bundle manifest contains all required fields."""
        output_dir = tmp_path / "test_bundle"

        exit_code, manifest = build_bundle(good_repo, output_dir)

        assert exit_code == 0
        assert manifest is not None
        assert manifest.version == 1
        assert manifest.created_at != ""
        assert manifest.file_count > 0
        assert manifest.total_size > 0
        assert len(manifest.files) > 0

    def test_build_copies_required_files(self, good_repo: Path, tmp_path: Path) -> None:
        """Build copies required asset files."""
        output_dir = tmp_path / "test_bundle"

        exit_code, _ = build_bundle(good_repo, output_dir)

        assert exit_code == 0
        assert (output_dir / "assets" / "sprites" / "hero.png").exists()
        assert (output_dir / "assets" / "sprites" / "item.png").exists()
        assert (output_dir / "assets" / "sprites" / "npc.png").exists()

    def test_build_excludes_unused_files(self, good_repo: Path, tmp_path: Path) -> None:
        """Build does not copy unused assets."""
        output_dir = tmp_path / "test_bundle"

        exit_code, _ = build_bundle(good_repo, output_dir)

        assert exit_code == 0
        assert not (output_dir / "assets" / "sprites" / "unused_decor.png").exists()

    def test_build_fails_on_missing_deps_by_default(self, bad_repo: Path, tmp_path: Path) -> None:
        """Build fails when there are missing dependencies."""
        output_dir = tmp_path / "test_bundle"

        exit_code, manifest = build_bundle(bad_repo, output_dir)

        assert exit_code == 1
        assert manifest is None

    def test_build_allow_missing_option(self, bad_repo: Path, tmp_path: Path) -> None:
        """Build succeeds with allow_missing=True."""
        output_dir = tmp_path / "test_bundle"

        exit_code, manifest = build_bundle(bad_repo, output_dir, fail_on_missing=False)

        assert exit_code == 0
        assert manifest is not None


# --------------------------------------------------------------------------- #
# Bundle Determinism Tests
# --------------------------------------------------------------------------- #


class TestBundleDeterminism:
    """Tests for export determinism."""

    def test_two_builds_produce_identical_file_lists(self, good_repo: Path, tmp_path: Path) -> None:
        """Two consecutive builds produce identical file lists."""
        output_dir1 = tmp_path / "bundle1"
        output_dir2 = tmp_path / "bundle2"

        exit_code1, manifest1 = build_bundle(good_repo, output_dir1)
        exit_code2, manifest2 = build_bundle(good_repo, output_dir2)

        assert exit_code1 == 0
        assert exit_code2 == 0
        assert manifest1 is not None
        assert manifest2 is not None

        # File lists should be identical
        paths1 = [f["path"] for f in manifest1.files]
        paths2 = [f["path"] for f in manifest2.files]
        assert paths1 == paths2

    def test_two_builds_produce_identical_hashes(self, good_repo: Path, tmp_path: Path) -> None:
        """Two consecutive builds produce identical file hashes."""
        output_dir1 = tmp_path / "bundle1"
        output_dir2 = tmp_path / "bundle2"

        exit_code1, manifest1 = build_bundle(good_repo, output_dir1)
        exit_code2, manifest2 = build_bundle(good_repo, output_dir2)

        assert exit_code1 == 0
        assert exit_code2 == 0

        # Hashes should be identical
        hashes1 = {f["path"]: f["sha256"] for f in manifest1.files}
        hashes2 = {f["path"]: f["sha256"] for f in manifest2.files}
        assert hashes1 == hashes2

    def test_bundle_diff_identical(self, good_repo: Path, tmp_path: Path) -> None:
        """Diff of two identical builds shows no changes."""
        output_dir1 = tmp_path / "bundle1"
        output_dir2 = tmp_path / "bundle2"

        build_bundle(good_repo, output_dir1)
        build_bundle(good_repo, output_dir2)

        diff = diff_bundles(output_dir1, output_dir2)

        assert not diff.has_changes
        assert len(diff.added) == 0
        assert len(diff.removed) == 0
        assert len(diff.changed) == 0


# --------------------------------------------------------------------------- #
# Bundle Diffing Tests
# --------------------------------------------------------------------------- #


class TestBundleDiffing:
    """Tests for diff_bundles().
    
    Note: diff_bundles compares manifests by default. To detect post-build
    file changes, we delete the manifests to trigger filesystem scanning.
    """

    def test_diff_detects_added_files(self, good_repo: Path, tmp_path: Path) -> None:
        """Diff detects files added in the second bundle."""
        output_dir1 = tmp_path / "bundle1"
        output_dir2 = tmp_path / "bundle2"

        build_bundle(good_repo, output_dir1)
        build_bundle(good_repo, output_dir2)

        # Add a file to bundle2
        new_file = output_dir2 / "extra.txt"
        new_file.write_text("extra content")

        # Remove manifests to trigger file scanning comparison
        (output_dir1 / "bundle_manifest.json").unlink()
        (output_dir2 / "bundle_manifest.json").unlink()

        diff = diff_bundles(output_dir1, output_dir2)

        assert diff.has_changes
        assert "extra.txt" in diff.added

    def test_diff_detects_removed_files(self, good_repo: Path, tmp_path: Path) -> None:
        """Diff detects files removed from the second bundle."""
        output_dir1 = tmp_path / "bundle1"
        output_dir2 = tmp_path / "bundle2"

        build_bundle(good_repo, output_dir1)
        build_bundle(good_repo, output_dir2)

        # Remove a file from bundle2
        (output_dir2 / "scenes" / "scene_a.json").unlink()

        # Remove manifests to trigger file scanning comparison
        (output_dir1 / "bundle_manifest.json").unlink()
        (output_dir2 / "bundle_manifest.json").unlink()

        diff = diff_bundles(output_dir1, output_dir2)

        assert diff.has_changes
        assert "scenes/scene_a.json" in diff.removed

    def test_diff_detects_changed_files(self, good_repo: Path, tmp_path: Path) -> None:
        """Diff detects files with different content."""
        output_dir1 = tmp_path / "bundle1"
        output_dir2 = tmp_path / "bundle2"

        build_bundle(good_repo, output_dir1)
        build_bundle(good_repo, output_dir2)

        # Modify a file in bundle2
        scene_file = output_dir2 / "scenes" / "scene_a.json"
        scene_file.write_text('{"modified": true}')

        # Remove manifests to trigger file scanning comparison
        (output_dir1 / "bundle_manifest.json").unlink()
        (output_dir2 / "bundle_manifest.json").unlink()

        diff = diff_bundles(output_dir1, output_dir2)

        assert diff.has_changes
        assert "scenes/scene_a.json" in diff.changed

    def test_diff_uses_manifest_when_available(self, good_repo: Path, tmp_path: Path) -> None:
        """Diff uses manifests when both bundles have them."""
        output_dir1 = tmp_path / "bundle1"
        output_dir2 = tmp_path / "bundle2"

        build_bundle(good_repo, output_dir1)
        build_bundle(good_repo, output_dir2)

        # Keep manifests - diff should use them
        diff = diff_bundles(output_dir1, output_dir2)

        # Same build = no changes
        assert not diff.has_changes
        assert len(diff.unchanged) > 0


# --------------------------------------------------------------------------- #
# Data Class Tests
# --------------------------------------------------------------------------- #


class TestExportFile:
    """Tests for ExportFile dataclass."""

    def test_to_dict(self) -> None:
        """ExportFile.to_dict() produces expected structure."""
        f = ExportFile(
            rel_path="assets/test.png",
            src_path="/path/to/test.png",
            sha256="abc123",
            size=1024,
            category="asset",
        )
        d = f.to_dict()

        assert d["path"] == "assets/test.png"
        assert d["sha256"] == "abc123"
        assert d["size"] == 1024
        assert d["category"] == "asset"


class TestExportPlanClass:
    """Tests for ExportPlan dataclass."""

    def test_ok_when_no_issues(self) -> None:
        """Plan.ok is True when no missing deps or errors."""
        plan = ExportPlan()
        assert plan.ok

    def test_not_ok_with_missing_deps(self) -> None:
        """Plan.ok is False when there are missing deps."""
        plan = ExportPlan(missing_deps=["missing.png"])
        assert not plan.ok

    def test_not_ok_with_errors(self) -> None:
        """Plan.ok is False when there are errors."""
        plan = ExportPlan(errors=["Some error"])
        assert not plan.ok

    def test_to_dict(self) -> None:
        """Plan.to_dict() produces expected structure."""
        plan = ExportPlan(
            files=[ExportFile("a", "b", "c", 100, "asset")],
            excluded_assets=["unused.png"],
        )
        d = plan.to_dict()

        assert d["ok"] is True
        assert d["file_count"] == 1
        assert d["excluded_asset_count"] == 1


class TestBundleManifest:
    """Tests for BundleManifest dataclass."""

    def test_to_dict(self) -> None:
        """Manifest.to_dict() produces expected structure."""
        manifest = BundleManifest(
            version=1,
            created_at="2026-02-06T00:00:00Z",
            repo_root="/repo",
            file_count=10,
            total_size=1000,
            files=[{"path": "test.png", "sha256": "abc"}],
        )
        d = manifest.to_dict()

        assert d["version"] == 1
        assert d["file_count"] == 10
        assert len(d["files"]) == 1

    def test_from_dict(self) -> None:
        """Manifest.from_dict() parses correctly."""
        data = {
            "version": 1,
            "created_at": "2026-02-06T00:00:00Z",
            "repo_root": "/repo",
            "file_count": 5,
            "total_size": 500,
            "files": [],
        }
        manifest = BundleManifest.from_dict(data)

        assert manifest.version == 1
        assert manifest.file_count == 5


class TestBundleDiff:
    """Tests for BundleDiff dataclass."""

    def test_has_changes_false_when_empty(self) -> None:
        """has_changes is False when no differences."""
        diff = BundleDiff()
        assert not diff.has_changes

    def test_has_changes_true_with_added(self) -> None:
        """has_changes is True when files added."""
        diff = BundleDiff(added=["new.txt"])
        assert diff.has_changes

    def test_has_changes_true_with_removed(self) -> None:
        """has_changes is True when files removed."""
        diff = BundleDiff(removed=["old.txt"])
        assert diff.has_changes

    def test_has_changes_true_with_changed(self) -> None:
        """has_changes is True when files changed."""
        diff = BundleDiff(changed=["modified.txt"])
        assert diff.has_changes


# --------------------------------------------------------------------------- #
# Integration Tests
# --------------------------------------------------------------------------- #


class TestEndToEndWorkflow:
    """Integration tests for the full export workflow."""

    def test_full_export_workflow(self, good_repo: Path, tmp_path: Path) -> None:
        """Full workflow: plan -> build -> diff."""
        # 1. Compute plan
        plan = compute_export_plan(good_repo)
        assert plan.ok

        # 2. Build bundle
        output_dir = tmp_path / "bundle"
        exit_code, manifest = build_bundle(good_repo, output_dir)
        assert exit_code == 0

        # 3. Verify manifest matches plan
        assert manifest is not None
        assert manifest.file_count == len(plan.files)

        # 4. Build again and diff
        output_dir2 = tmp_path / "bundle2"
        build_bundle(good_repo, output_dir2)

        diff = diff_bundles(output_dir, output_dir2)
        assert not diff.has_changes

    def test_manifest_can_be_loaded(self, good_repo: Path, tmp_path: Path) -> None:
        """Bundle manifest can be loaded after build."""
        output_dir = tmp_path / "bundle"
        build_bundle(good_repo, output_dir)

        loaded = load_bundle_manifest(output_dir)
        assert loaded is not None
        assert loaded.version == 1
        assert loaded.file_count > 0
