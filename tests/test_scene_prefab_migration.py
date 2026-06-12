"""Tests for scene and prefab migration system."""
from __future__ import annotations

import pytest

from engine.migrations import (
    PREFAB_SCHEMA_VERSION,
    SCENE_SCHEMA_VERSION,
    get_current_schema_version,
    migrate_prefab,
    migrate_scene,
)


@pytest.mark.fast
def test_scene_schema_version_defined() -> None:
    """Scene schema version is defined and positive."""
    assert SCENE_SCHEMA_VERSION >= 1


@pytest.mark.fast
def test_prefab_schema_version_defined() -> None:
    """Prefab schema version is defined and positive."""
    assert PREFAB_SCHEMA_VERSION >= 1


@pytest.mark.fast
def test_get_current_schema_version_scene() -> None:
    """get_current_schema_version returns correct version for scenes."""
    assert get_current_schema_version("scene") == SCENE_SCHEMA_VERSION


@pytest.mark.fast
def test_get_current_schema_version_prefab() -> None:
    """get_current_schema_version returns correct version for prefabs."""
    assert get_current_schema_version("prefab") == PREFAB_SCHEMA_VERSION


@pytest.mark.fast
def test_get_current_schema_version_unknown() -> None:
    """get_current_schema_version returns 1 for unknown types."""
    assert get_current_schema_version("unknown_type") == 1


@pytest.mark.fast
def test_migrate_scene_noop_current_version() -> None:
    """migrate_scene is a no-op for current schema version."""
    scene = {
        "name": "Test Scene",
        "schema_version": SCENE_SCHEMA_VERSION,
        "entities": [],
    }

    result = migrate_scene(scene)

    # Should return the same data (no migration needed)
    assert result["name"] == "Test Scene"
    assert result["schema_version"] == SCENE_SCHEMA_VERSION


@pytest.mark.fast
def test_migrate_scene_preserves_data() -> None:
    """migrate_scene preserves all scene data."""
    scene = {
        "name": "Test Scene",
        "schema_version": SCENE_SCHEMA_VERSION,
        "settings": {"background_color": "black"},
        "entities": [{"x": 100, "y": 200}],
        "tilemap": {"width": 10, "height": 10},
    }

    result = migrate_scene(scene)

    assert result["name"] == "Test Scene"
    assert result["settings"]["background_color"] == "black"
    assert result["entities"][0]["x"] == 100
    assert result["tilemap"]["width"] == 10


@pytest.mark.fast
def test_migrate_prefab_noop_current_version() -> None:
    """migrate_prefab is a no-op for current schema version."""
    prefab = {
        "id": "test_prefab",
        "schema_version": PREFAB_SCHEMA_VERSION,
        "entity": {"sprite": "test.png"},
    }

    result = migrate_prefab(prefab)

    assert result["id"] == "test_prefab"
    assert result["schema_version"] == PREFAB_SCHEMA_VERSION


@pytest.mark.fast
def test_migrate_prefab_preserves_data() -> None:
    """migrate_prefab preserves all prefab data."""
    prefab = {
        "id": "test_prefab",
        "schema_version": PREFAB_SCHEMA_VERSION,
        "base": "base_prefab",
        "display_name": "Test",
        "tags": ["enemy"],
        "entity": {
            "sprite": "test.png",
            "behaviours": ["AI"],
        },
    }

    result = migrate_prefab(prefab)

    assert result["id"] == "test_prefab"
    assert result["base"] == "base_prefab"
    assert result["display_name"] == "Test"
    assert result["tags"] == ["enemy"]
    assert result["entity"]["sprite"] == "test.png"


@pytest.mark.fast
def test_migrate_scene_adds_version_if_missing() -> None:
    """migrate_scene handles scenes without schema_version."""
    scene = {
        "name": "Old Scene",
        "entities": [],
    }

    # Should not raise, should treat as v1
    result = migrate_scene(scene)
    assert result["name"] == "Old Scene"


@pytest.mark.fast
def test_migrate_prefab_adds_version_if_missing() -> None:
    """migrate_prefab handles prefabs without schema_version."""
    prefab = {
        "id": "old_prefab",
        "entity": {},
    }

    # Should not raise, should treat as v1
    result = migrate_prefab(prefab)
    assert result["id"] == "old_prefab"
