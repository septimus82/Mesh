"""Contract tests for components_model.py.

Tests cover:
- Transform always present
- Legacy flat x/y/rotation read correctly
- set_component_field writes into components dict and is immutable
- add_component/remove_component deterministic and preserves unrelated keys
"""

from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from engine.editor.components_model import (
    LIGHT_DEFAULTS,
    add_component,
    build_components,
    ensure_components_container,
    get_addable_components,
    get_component_dict,
    remove_component,
    set_component_field,
)

# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def minimal_entity() -> Dict[str, Any]:
    """Minimal entity with just transform fields (legacy flat format)."""
    return {
        "id": "test_entity",
        "name": "Test Entity",
        "x": 100.0,
        "y": 200.0,
        "rotation": 45.0,
    }


@pytest.fixture
def entity_with_components() -> Dict[str, Any]:
    """Entity with explicit components container."""
    return {
        "id": "full_entity",
        "name": "Full Entity",
        "components": {
            "transform": {"x": 50.0, "y": 60.0, "rot": 90.0},
            "sprite": {"asset": "player.png"},
            "light": {
                "radius_px": 200.0,
                "color_rgba": [255, 128, 0, 255],
                "flicker_enabled": True,
            },
        },
    }


@pytest.fixture
def entity_with_legacy_light() -> Dict[str, Any]:
    """Entity with light in legacy behaviour_config format."""
    return {
        "id": "light_entity",
        "x": 10.0,
        "y": 20.0,
        "behaviours": ["LightSource"],
        "behaviour_config": {
            "LightSource": {
                "radius": 256.0,
                "color": "#ff0000",
            }
        },
    }


# -----------------------------------------------------------------------------
# Test Transform Always Present
# -----------------------------------------------------------------------------

class TestTransformAlwaysPresent:
    """Test that Transform component is always included."""

    def test_minimal_entity_has_transform(self, minimal_entity: Dict[str, Any]):
        """Transform should be present even for minimal entity."""
        components = build_components(minimal_entity)
        assert len(components) >= 1
        assert components[0].kind == "transform"

    def test_empty_entity_has_transform(self):
        """Transform should be present even for empty entity."""
        entity = {"id": "empty"}
        components = build_components(entity)
        assert len(components) >= 1
        assert components[0].kind == "transform"
        # Should have default values
        assert components[0].fields[0].value == 0.0  # x
        assert components[0].fields[1].value == 0.0  # y
        assert components[0].fields[2].value == 0.0  # rot

    def test_transform_is_first(self, entity_with_components: Dict[str, Any]):
        """Transform should always be first component."""
        components = build_components(entity_with_components)
        assert components[0].kind == "transform"

    def test_transform_not_removable(self, minimal_entity: Dict[str, Any]):
        """Transform should not be removable."""
        components = build_components(minimal_entity)
        assert components[0].removable is False


# -----------------------------------------------------------------------------
# Test Legacy Flat Fields
# -----------------------------------------------------------------------------

class TestLegacyFlatFields:
    """Test reading legacy flat x/y/rotation fields."""

    def test_read_legacy_x_y(self, minimal_entity: Dict[str, Any]):
        """Should read x/y from top-level fields."""
        components = build_components(minimal_entity)
        transform = components[0]

        x_field = next(f for f in transform.fields if f.key == "x")
        y_field = next(f for f in transform.fields if f.key == "y")

        assert x_field.value == 100.0
        assert y_field.value == 200.0

    def test_read_legacy_rotation(self, minimal_entity: Dict[str, Any]):
        """Should read rotation from top-level field."""
        components = build_components(minimal_entity)
        transform = components[0]

        rot_field = next(f for f in transform.fields if f.key == "rot")
        assert rot_field.value == 45.0

    def test_get_component_dict_legacy_transform(self, minimal_entity: Dict[str, Any]):
        """get_component_dict should read legacy transform fields."""
        comp = get_component_dict(minimal_entity, "transform")
        assert comp is not None
        assert comp["x"] == 100.0
        assert comp["y"] == 200.0
        assert comp["rot"] == 45.0

    def test_read_legacy_sprite(self):
        """Should read sprite from top-level field."""
        entity = {"id": "e", "sprite": "path/to/sprite.png"}
        components = build_components(entity)

        sprite_comps = [c for c in components if c.kind == "sprite"]
        assert len(sprite_comps) == 1
        sprite = sprite_comps[0]

        asset_field = next(f for f in sprite.fields if f.key == "asset")
        assert asset_field.value == "path/to/sprite.png"

    def test_read_legacy_light(self, entity_with_legacy_light: Dict[str, Any]):
        """Should read light from behaviour_config.LightSource."""
        components = build_components(entity_with_legacy_light)

        light_comps = [c for c in components if c.kind == "light"]
        assert len(light_comps) == 1
        light = light_comps[0]

        radius_field = next(f for f in light.fields if f.key == "radius_px")
        assert radius_field.value == 256.0


# -----------------------------------------------------------------------------
# Test set_component_field
# -----------------------------------------------------------------------------

class TestSetComponentField:
    """Test set_component_field behavior."""

    def test_immutability(self, minimal_entity: Dict[str, Any]):
        """set_component_field should not mutate input."""
        original = copy.deepcopy(minimal_entity)
        result = set_component_field(minimal_entity, "transform", "x", 999.0)

        # Original should be unchanged
        assert minimal_entity == original
        # Result should be different
        assert result != minimal_entity

    def test_writes_to_components_container(self, minimal_entity: Dict[str, Any]):
        """set_component_field should write into components dict."""
        result = set_component_field(minimal_entity, "transform", "x", 500.0)

        assert "components" in result
        assert "transform" in result["components"]
        assert result["components"]["transform"]["x"] == 500.0

    def test_preserves_unrelated_keys(self, minimal_entity: Dict[str, Any]):
        """set_component_field should preserve all unrelated keys."""
        result = set_component_field(minimal_entity, "transform", "x", 500.0)

        assert result["id"] == minimal_entity["id"]
        assert result["name"] == minimal_entity["name"]

    def test_migrates_legacy_to_components(self, minimal_entity: Dict[str, Any]):
        """When updating legacy entity, values should be in components container."""
        result = set_component_field(minimal_entity, "transform", "y", 300.0)

        # Should have y in components
        assert result["components"]["transform"]["y"] == 300.0
        # Should also have x (migrated from legacy)
        assert result["components"]["transform"]["x"] == 100.0

    def test_updates_existing_component(self, entity_with_components: Dict[str, Any]):
        """Should update existing component field."""
        result = set_component_field(entity_with_components, "transform", "x", 999.0)

        assert result["components"]["transform"]["x"] == 999.0
        # Other fields unchanged
        assert result["components"]["transform"]["y"] == 60.0

    def test_collider_kind_change_adds_defaults(self):
        """Changing collider kind should add shape-specific defaults."""
        entity = {"id": "e", "components": {"collider": {"kind": "none"}}}

        # Change to rect
        result = set_component_field(entity, "collider", "kind", "rect")
        assert result["components"]["collider"]["kind"] == "rect"
        assert "w" in result["components"]["collider"]
        assert "h" in result["components"]["collider"]

        # Change to circle
        result2 = set_component_field(result, "collider", "kind", "circle")
        assert result2["components"]["collider"]["kind"] == "circle"
        assert "r" in result2["components"]["collider"]
        # Rect fields removed
        assert "w" not in result2["components"]["collider"]


# -----------------------------------------------------------------------------
# Test add_component/remove_component
# -----------------------------------------------------------------------------

class TestAddRemoveComponent:
    """Test add_component and remove_component."""

    def test_add_component_creates_with_defaults(self, minimal_entity: Dict[str, Any]):
        """add_component should add component with defaults."""
        result = add_component(minimal_entity, "light")

        assert "components" in result
        assert "light" in result["components"]
        light = result["components"]["light"]
        assert light["radius_px"] == LIGHT_DEFAULTS["radius_px"]

    def test_add_component_is_noop_if_present(self, entity_with_components: Dict[str, Any]):
        """add_component should be no-op if already present."""
        original_light = entity_with_components["components"]["light"].copy()
        result = add_component(entity_with_components, "light")

        # Light should be unchanged
        assert result["components"]["light"]["radius_px"] == original_light["radius_px"]

    def test_add_transform_is_noop(self, minimal_entity: Dict[str, Any]):
        """add_component for transform should be no-op."""
        result = add_component(minimal_entity, "transform")
        # Should not have explicit transform component added
        # (transform is implicit)
        assert result.get("components", {}).get("transform") is None or \
               "components" not in result or "transform" not in result.get("components", {})

    def test_add_component_preserves_keys(self, minimal_entity: Dict[str, Any]):
        """add_component should preserve all existing keys."""
        result = add_component(minimal_entity, "sprite")

        assert result["id"] == minimal_entity["id"]
        assert result["x"] == minimal_entity["x"]

    def test_remove_component(self, entity_with_components: Dict[str, Any]):
        """remove_component should remove the component."""
        result = remove_component(entity_with_components, "light")

        assert "light" not in result["components"]

    def test_remove_transform_is_noop(self, entity_with_components: Dict[str, Any]):
        """remove_component for transform should be no-op."""
        result = remove_component(entity_with_components, "transform")

        # Transform should still be readable
        components = build_components(result)
        assert components[0].kind == "transform"

    def test_remove_preserves_keys(self, entity_with_components: Dict[str, Any]):
        """remove_component should preserve unrelated keys."""
        result = remove_component(entity_with_components, "light")

        assert result["id"] == entity_with_components["id"]
        assert result["components"]["sprite"] == entity_with_components["components"]["sprite"]

    def test_remove_legacy_light(self, entity_with_legacy_light: Dict[str, Any]):
        """remove_component should clean up legacy light data."""
        result = remove_component(entity_with_legacy_light, "light")

        # Should remove from behaviours
        assert "LightSource" not in result.get("behaviours", [])
        # Should clean behaviour_config
        assert "LightSource" not in result.get("behaviour_config", {})


# -----------------------------------------------------------------------------
# Test Component Order
# -----------------------------------------------------------------------------

class TestComponentOrder:
    """Test that components are in stable order."""

    def test_order_is_transform_sprite_light_collider(self, entity_with_components: Dict[str, Any]):
        """Components should be in order: Transform, Sprite, Light, Collider."""
        # Add collider
        entity = copy.deepcopy(entity_with_components)
        entity["components"]["collider"] = {"kind": "rect", "w": 16, "h": 16}

        components = build_components(entity)
        kinds = [c.kind for c in components]

        assert kinds == ["transform", "sprite", "light", "collider"]

    def test_order_stable_with_missing_components(self):
        """Order should be stable even with missing components."""
        entity = {
            "id": "e",
            "components": {
                "collider": {"kind": "circle", "r": 8},
                "transform": {"x": 0, "y": 0, "rot": 0},
            }
        }

        components = build_components(entity)
        kinds = [c.kind for c in components]

        # Transform then collider, no sprite or light
        assert kinds == ["transform", "collider"]


# -----------------------------------------------------------------------------
# Test get_addable_components
# -----------------------------------------------------------------------------

class TestGetAddableComponents:
    """Test get_addable_components function."""

    def test_minimal_entity_can_add_all(self, minimal_entity: Dict[str, Any]):
        """Minimal entity can add sprite, light, collider."""
        addable = get_addable_components(minimal_entity)

        assert "sprite" in addable
        assert "light" in addable
        assert "collider" in addable
        # Transform never addable
        assert "transform" not in addable

    def test_entity_with_sprite_cannot_add_sprite(self):
        """Entity with sprite cannot add sprite."""
        entity = {"id": "e", "sprite": "test.png"}
        addable = get_addable_components(entity)

        assert "sprite" not in addable

    def test_full_entity_has_none_addable(self, entity_with_components: Dict[str, Any]):
        """Entity with all components has limited addable options."""
        # Add collider too
        entity = copy.deepcopy(entity_with_components)
        entity["components"]["collider"] = {"kind": "none"}

        addable = get_addable_components(entity)

        assert len(addable) == 0


# -----------------------------------------------------------------------------
# Test ensure_components_container
# -----------------------------------------------------------------------------

class TestEnsureComponentsContainer:
    """Test ensure_components_container function."""

    def test_adds_components_key(self, minimal_entity: Dict[str, Any]):
        """Should add components key if missing."""
        result = ensure_components_container(minimal_entity)

        assert "components" in result
        assert isinstance(result["components"], dict)

    def test_preserves_existing_components(self, entity_with_components: Dict[str, Any]):
        """Should preserve existing components."""
        result = ensure_components_container(entity_with_components)

        assert result["components"]["transform"] == entity_with_components["components"]["transform"]

    def test_does_not_mutate_input(self, minimal_entity: Dict[str, Any]):
        """Should not mutate input."""
        original = copy.deepcopy(minimal_entity)
        ensure_components_container(minimal_entity)

        assert minimal_entity == original
