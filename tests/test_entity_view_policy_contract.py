"""Policy tests for EntityView usage.

These tests enforce that canonical entity fields are accessed via EntityView
rather than direct dict access in production code.

Exempt modules:
- Serialization/migration (scene_loader.py, scene_serializer.py, migrations.py)
- Validators (need raw dict access for validation)
- Tooling (operates on raw JSON)
- Tests
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from engine.entity_view import (
    CANONICAL_ENTITY_FIELDS,
    ENTITY_VIEW_POLICY_EXEMPT_MODULES,
)


def _get_engine_root() -> Path:
    """Get the path to the engine directory."""
    return Path(__file__).parent.parent / "engine"


def _is_exempt(filepath: Path) -> bool:
    """Check if a file is exempt from the policy."""
    # Normalize path for comparison
    rel_path = filepath.as_posix()
    
    for exempt in ENTITY_VIEW_POLICY_EXEMPT_MODULES:
        if exempt.endswith("/"):
            # Directory exemption
            if exempt in rel_path or rel_path.startswith(exempt):
                return True
        else:
            # File exemption
            if rel_path.endswith(exempt):
                return True
    return False


def _find_direct_entity_access(content: str) -> list[tuple[int, str, str]]:
    """Find direct dict access patterns for canonical entity fields.
    
    Returns list of (line_number, pattern_found, field_name).
    """
    violations: list[tuple[int, str, str]] = []
    
    # Patterns that indicate direct dict access on entity-like variables
    # We look for: entity["field"] or entity.get("field") where field is canonical
    # and entity is a variable name that looks entity-related
    
    entity_var_patterns = (
        r'\bentity\b',
        r'\bent\b',
        r'\braw_entity\b',
        r'\bnew_entity\b',
        r'\bcopy_entity\b',
    )
    
    lines = content.split('\n')
    for line_num, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        
        for field in CANONICAL_ENTITY_FIELDS:
            # Pattern 1: entity["field"] (dict subscript)
            for var_pattern in entity_var_patterns:
                # Match entity["field"] or entity['field']
                pattern = rf'{var_pattern}\s*\[\s*["\']({re.escape(field)})["\']\s*\]'
                match = re.search(pattern, line)
                if match:
                    violations.append((line_num, match.group(0), field))
                    break
            
            # Pattern 2: entity.get("field") (dict get method)
            for var_pattern in entity_var_patterns:
                pattern = rf'{var_pattern}\.get\s*\(\s*["\']({re.escape(field)})["\']'
                match = re.search(pattern, line)
                if match:
                    violations.append((line_num, match.group(0), field))
                    break
    
    return violations


@pytest.mark.fast
def test_entity_view_exists() -> None:
    """EntityView module exists and exports required symbols."""
    from engine.entity_view import EntityView, CANONICAL_ENTITY_FIELDS
    
    assert EntityView is not None
    assert len(CANONICAL_ENTITY_FIELDS) > 0


@pytest.mark.fast
def test_entity_view_wraps_dict() -> None:
    """EntityView wraps a dict and provides typed access."""
    from engine.entity_view import EntityView
    
    data = {"x": 100.0, "y": 200.0, "name": "Test", "tags": ["enemy"]}
    view = EntityView(data)
    
    # Typed access
    assert view.x == 100.0
    assert view.y == 200.0
    assert view.name == "Test"
    assert view.tags == ["enemy"]
    
    # Setters update underlying dict
    view.x = 150.0
    assert data["x"] == 150.0
    
    view.tags = ["boss"]
    assert data["tags"] == ["boss"]


@pytest.mark.fast
def test_entity_view_is_dict_like() -> None:
    """EntityView implements MutableMapping protocol."""
    from engine.entity_view import EntityView
    
    data = {"x": 100.0, "custom_field": "value"}
    view = EntityView(data)
    
    # Dict-like access for non-canonical fields
    assert view["custom_field"] == "value"
    view["custom_field"] = "new_value"
    assert data["custom_field"] == "new_value"
    
    # Can iterate
    assert "x" in view
    assert len(view) == 2


@pytest.mark.fast
def test_entity_view_wrap_idempotent() -> None:
    """EntityView.wrap() is idempotent."""
    from engine.entity_view import EntityView
    
    data = {"x": 100.0}
    view1 = EntityView(data)
    view2 = EntityView.wrap(view1)
    
    assert view1 is view2


@pytest.mark.fast
def test_canonical_fields_comprehensive() -> None:
    """CANONICAL_ENTITY_FIELDS covers all expected fields."""
    expected = {
        # Position
        "x", "y",
        # Identity
        "id", "name", "prefab_id", "variant_id", "spawn_id",
        # Rendering
        "sprite", "sprite_sheet", "scale", "rotation", "layer", "alpha", "tint",
        # Collision
        "solid", "collision_poly", "occluder_poly",
        # Behaviours
        "behaviours", "behaviour_config",
        # Tags
        "tags",
        # Animation
        "animations", "animation_state", "animation_frame_rate",
        # Depth
        "depth_z", "render_layer",
        # Flags
        "require_flags", "forbid_flags",
    }
    
    assert CANONICAL_ENTITY_FIELDS == expected


@pytest.mark.fast
def test_exempt_modules_reasonable() -> None:
    """Exempt module list is reasonable and not empty."""
    assert len(ENTITY_VIEW_POLICY_EXEMPT_MODULES) > 0
    
    # Must include serialization
    assert "engine/scene_loader.py" in ENTITY_VIEW_POLICY_EXEMPT_MODULES
    assert "engine/scene_serializer.py" in ENTITY_VIEW_POLICY_EXEMPT_MODULES
    
    # Must include tests
    assert "tests/" in ENTITY_VIEW_POLICY_EXEMPT_MODULES


# NOTE: The policy test below is intentionally lenient at introduction.
# It documents the pattern but does not fail on existing code.
# Once codebase is migrated to EntityView, enable stricter checking.

@pytest.mark.fast
@pytest.mark.skip(reason="Policy test - enable after EntityView adoption")
def test_no_direct_entity_access_in_production() -> None:
    """Production code should use EntityView for canonical entity fields.
    
    This test scans non-exempt engine modules for direct dict access patterns
    like entity["x"] or entity.get("sprite") on canonical fields.
    
    DISABLED: This is a forward-looking policy test. Enable after the codebase
    has been migrated to use EntityView for canonical field access.
    """
    engine_root = _get_engine_root()
    violations: list[str] = []
    
    for py_file in engine_root.rglob("*.py"):
        if _is_exempt(py_file):
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        
        file_violations = _find_direct_entity_access(content)
        for line_num, pattern, field in file_violations:
            rel_path = py_file.relative_to(engine_root.parent)
            violations.append(
                f"  {rel_path}:{line_num}: direct access to '{field}' via {pattern}\n"
                f"    hint: Use EntityView.{field} instead"
            )
    
    if violations:
        pytest.fail(
            f"Found {len(violations)} direct entity dict access patterns:\n\n"
            + "\n".join(violations[:20])
            + ("\n  ... and more" if len(violations) > 20 else "")
            + "\n\nUse EntityView for typed access to canonical entity fields."
        )


@pytest.mark.fast
def test_entity_view_policy_test_exists() -> None:
    """Verify the policy test infrastructure exists.
    
    This test ensures the policy enforcement code is present and functional,
    even though the strict policy test is currently skipped.
    """
    # The detection function should work
    sample_code = '''
entity = {"x": 100}
value = entity["x"]
name = entity.get("name")
'''
    violations = _find_direct_entity_access(sample_code)
    
    # Should detect the violations
    assert len(violations) == 2
    fields = {v[2] for v in violations}
    assert "x" in fields
    assert "name" in fields
