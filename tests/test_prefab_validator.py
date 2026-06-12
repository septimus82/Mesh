import pytest

from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours

def test_prefab_owned_sprite_override_is_error() -> None:
    loader = SceneLoader()
    report = loader.validate_entity(
        {
            "mesh_name": "Boss",
            "x": 0,
            "y": 0,
            "prefab_id": "slime_blob",
            "variant_id": "boss",
            "sprite": "assets/placeholder.png",
        },
        index=0,
        strict=True,
    )

    assert report.errors
    assert "must not set 'sprite'" in "\n".join(report.errors)


def test_prefab_entity_must_not_set_name() -> None:
    loader = SceneLoader()
    report = loader.validate_entity(
        {
            "name": "BadOverride",
            "mesh_name": "Boss1",
            "x": 0,
            "y": 0,
            "prefab_id": "slime_blob",
        },
        index=0,
        strict=True,
    )

    assert report.errors
    text = "\n".join(report.errors)
    assert "must not set 'name'" in text
    assert "Use mesh_name" in text


def test_prefab_entity_allows_mesh_name() -> None:
    loader = SceneLoader()
    report = loader.validate_entity(
        {
            "mesh_name": "EliteSlime01",
            "x": 0,
            "y": 0,
            "prefab_id": "slime_blob",
        },
        index=0,
        strict=True,
    )
    assert report.ok


def test_scene_entity_without_prefab_can_set_name() -> None:
    loader = SceneLoader()
    report = loader.validate_entity(
        {
            "name": "JustAProp",
            "x": 0,
            "y": 0,
            "sprite": "assets/placeholder.png",
        },
        index=0,
        strict=True,
    )
    assert report.ok
