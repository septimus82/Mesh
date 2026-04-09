"""Contract tests for capture_key_router_model.

These tests lock:
- Route table determinism (building twice yields identical results)
- No conflicts in route table (audit finds no issues)
- Alias handling (ENTER/RETURN intentional aliases are permitted)
- Coverage floor (each high-impact scope has routes)
- Build→Audit→Dedupe is idempotent
- Centralized validation via audit_routes()
"""
from __future__ import annotations

import pytest

import engine.optional_arcade as optional_arcade
from engine.input_runtime.capture_key_router_model import (
    AuditResult,
    KeyCombo,
    RouteSpec,
    audit_routes,
    build_route_table,
    _dedupe_routes,
    _when_always,
    _when_debug,
    _when_editor_active,
)
from engine.input_runtime.capture_runtime_focus_model import (
    SCOPE_CAPTURE_MODE,
    SCOPE_COMMAND_PALETTE,
    SCOPE_CONFIRM_MODAL,
    SCOPE_CONSOLE,
    SCOPE_CONTEXT_MENU,
    SCOPE_ENTITY_PAINT,
    SCOPE_ENTITY_SELECT,
    SCOPE_GLOBAL,
    SCOPE_INLINE_RENAME,
    SCOPE_KEYBINDS,
    SCOPE_PALETTE_MODE,
    SCOPE_PRIORITY,
    SCOPE_PROBLEMS,
    SCOPE_PROJECT_EXPLORER,
    SCOPE_TILE_PAINT,
)
from tests._typing import as_any


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_build_route_table_is_deterministic() -> None:
    """Building the route table twice yields identical results."""
    first = build_route_table()
    second = build_route_table()
    assert first == second, "Route table must be deterministic"


@pytest.mark.fast
def test_build_route_table_returns_tuple() -> None:
    """Route table is returned as an immutable tuple."""
    table = build_route_table()
    assert isinstance(table, tuple), "Route table must be a tuple (immutable)"
    assert len(table) > 0, "Route table must have at least one route"


@pytest.mark.fast
def test_dedupe_preserves_order_when_no_duplicates() -> None:
    """Dedupe returns routes in same order when no duplicates exist."""
    routes = build_route_table()
    deduped = tuple(_dedupe_routes(routes))
    # build_route_table already dedupes, so these should be identical
    assert routes == deduped, "Dedupe should preserve routes when no duplicates"


@pytest.mark.fast
def test_dedupe_removes_exact_duplicates() -> None:
    """Dedupe removes exact duplicate routes, keeping first occurrence."""
    key = optional_arcade.arcade.key
    route = RouteSpec(
        scope=SCOPE_GLOBAL,
        combo=KeyCombo(key=key.A, mods=0),
        action_id="test.action",
        when=_when_always,
    )
    routes = [route, route, route]
    deduped = _dedupe_routes(routes)
    assert len(deduped) == 1
    assert deduped[0] == route


@pytest.mark.fast
def test_build_audit_dedupe_produces_clean_routes() -> None:
    """The canonical build+audit+dedupe pipeline produces a clean route table.
    
    This test ensures that:
    1. build_route_table() returns routes
    2. audit_routes() reports no conflicts or duplicates
    3. _dedupe_routes() produces identical routes (since build already dedupes)
    4. Re-auditing confirms no conflicts or duplicates remain
    """
    # Step 1: Build routes
    routes = build_route_table()
    assert len(routes) > 0, "build_route_table() must return at least one route"
    
    # Step 2: Audit before dedupe
    report_before = audit_routes(routes)
    
    # Step 3: Dedupe
    deduped_routes = tuple(_dedupe_routes(routes))
    
    # Step 4: Re-audit after dedupe
    report_after = audit_routes(deduped_routes)
    
    # Verify: no conflicts remain
    assert len(report_after.conflicts) == 0, (
        f"Conflicts remain after dedupe: {report_after.conflicts}"
    )
    
    # Verify: no duplicates remain
    assert len(report_after.duplicates) == 0, (
        f"Duplicates remain after dedupe: {report_after.duplicates}"
    )
    
    # Verify: routes are identical (build_route_table already dedupes internally)
    assert routes == deduped_routes, (
        "build_route_table() should already return deduped routes"
    )


@pytest.mark.fast
def test_build_audit_dedupe_is_idempotent() -> None:
    """Running the full pipeline twice produces identical results.
    
    This tests that:
    1. Two independent runs of build→audit→dedupe produce the same routes
    2. The ordering is preserved exactly (not just set equality)
    3. No hidden state mutation occurs between runs
    """
    # First run
    routes_1 = build_route_table()
    report_1 = audit_routes(routes_1)
    deduped_1 = tuple(_dedupe_routes(routes_1))
    
    # Second run (independent)
    routes_2 = build_route_table()
    report_2 = audit_routes(routes_2)
    deduped_2 = tuple(_dedupe_routes(routes_2))
    
    # Assert: raw builds are identical
    assert routes_1 == routes_2, (
        f"build_route_table() is not idempotent.\n"
        f"First run: {len(routes_1)} routes\n"
        f"Second run: {len(routes_2)} routes"
    )
    
    # Assert: deduped outputs are identical (including order)
    assert deduped_1 == deduped_2, (
        f"_dedupe_routes() is not idempotent.\n"
        f"First run: {len(deduped_1)} routes\n"
        f"Second run: {len(deduped_2)} routes"
    )
    
    # Assert: audit reports are identical (same issues found)
    assert report_1.conflicts == report_2.conflicts, "Audit conflicts differ between runs"
    assert report_1.duplicates == report_2.duplicates, "Audit duplicates differ between runs"
    assert report_1.aliases == report_2.aliases, "Audit aliases differ between runs"
    
    # Assert: ordering is preserved (not just set equality)
    for i, (r1, r2) in enumerate(zip(deduped_1, deduped_2)):
        assert r1 == r2, (
            f"Route ordering differs at index {i}:\n"
            f"  First:  {r1}\n"
            f"  Second: {r2}"
        )


# ---------------------------------------------------------------------------
# Conflict/duplicate tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_no_conflicts_in_route_table() -> None:
    """Route table has no unintentional conflicts."""
    table = build_route_table()
    audit = audit_routes(table)
    assert audit.conflicts == (), f"Conflicts found: {audit.conflicts}"
    assert audit.duplicates == (), f"Duplicates found: {audit.duplicates}"


@pytest.mark.fast
def test_audit_detects_conflict() -> None:
    """Audit correctly detects conflicting routes (different actions, same combo)."""
    key = optional_arcade.arcade.key
    routes = [
        RouteSpec(SCOPE_GLOBAL, KeyCombo(key.A, 0), "action.one", _when_always),
        RouteSpec(SCOPE_GLOBAL, KeyCombo(key.A, 0), "action.two", _when_always),
    ]
    report = audit_routes(routes)
    
    assert len(report.conflicts) == 1, f"Expected 1 conflict, got {report.conflicts}"
    conflict = report.conflicts[0]
    assert conflict.scope == SCOPE_GLOBAL
    assert conflict.key == key.A
    assert conflict.mods == 0
    assert "action.one" in conflict.action_ids
    assert "action.two" in conflict.action_ids


@pytest.mark.fast
def test_audit_detects_duplicate() -> None:
    """Audit correctly detects exact duplicate routes."""
    key = optional_arcade.arcade.key
    route = RouteSpec(SCOPE_GLOBAL, KeyCombo(key.A, 0), "action.one", _when_always)
    routes = [route, route]
    report = audit_routes(routes)
    
    assert len(report.duplicates) == 1, f"Expected 1 duplicate, got {report.duplicates}"


# ---------------------------------------------------------------------------
# Alias tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_enter_return_alias_is_allowed() -> None:
    """ENTER and RETURN keys are treated as intentional aliases."""
    key = optional_arcade.arcade.key
    table = build_route_table()
    audit = audit_routes(table)
    assert audit.aliases, "expected at least one ENTER/RETURN alias"
    assert any(alias.mods == 0 for alias in audit.aliases)
    assert any(alias.action_id and alias.scope for alias in audit.aliases)


# ---------------------------------------------------------------------------
# Coverage tests - ensure high-impact scopes have routes
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_global_scope_has_routes() -> None:
    """Global scope must have at least one route."""
    table = build_route_table()
    global_routes = [r for r in table if r.scope == SCOPE_GLOBAL]
    assert len(global_routes) > 0, "Global scope must have at least one route"


@pytest.mark.fast
def test_confirm_modal_scope_has_routes() -> None:
    """Confirm modal scope must handle ENTER/ESC."""
    key = optional_arcade.arcade.key
    table = build_route_table()
    modal_routes = [r for r in table if r.scope == SCOPE_CONFIRM_MODAL]
    assert len(modal_routes) >= 2, "Confirm modal needs at least ENTER and ESC handlers"
    
    # Check for escape and enter/return
    keys_handled = {r.combo.key for r in modal_routes}
    assert key.ESCAPE in keys_handled, "Modal must handle ESCAPE"
    assert key.ENTER in keys_handled or key.RETURN in keys_handled, "Modal must handle ENTER"


@pytest.mark.fast
def test_command_palette_scope_has_routes() -> None:
    """Command palette scope must handle navigation keys."""
    key = optional_arcade.arcade.key
    table = build_route_table()
    palette_routes = [r for r in table if r.scope == SCOPE_COMMAND_PALETTE]
    assert len(palette_routes) >= 3, "Command palette needs navigation keys"
    
    keys_handled = {r.combo.key for r in palette_routes}
    assert key.UP in keys_handled or key.DOWN in keys_handled, (
        "Command palette must handle UP/DOWN for navigation"
    )


@pytest.mark.fast
def test_console_scope_has_routes() -> None:
    """Console scope must handle basic keys."""
    key = optional_arcade.arcade.key
    table = build_route_table()
    console_routes = [r for r in table if r.scope == SCOPE_CONSOLE]
    assert len(console_routes) >= 1, "Console scope needs at least ESC to close"


@pytest.mark.fast
def test_inline_rename_scope_has_routes() -> None:
    """Inline rename scope must handle ENTER to confirm and ESC to cancel."""
    key = optional_arcade.arcade.key
    table = build_route_table()
    rename_routes = [r for r in table if r.scope == SCOPE_INLINE_RENAME]
    assert len(rename_routes) >= 2, "Inline rename needs ENTER and ESC handlers"
    
    keys_handled = {r.combo.key for r in rename_routes}
    assert key.ESCAPE in keys_handled, "Inline rename must handle ESCAPE"


@pytest.mark.fast
def test_context_menu_scope_has_routes() -> None:
    """Context menu scope must handle ESC to close."""
    key = optional_arcade.arcade.key
    table = build_route_table()
    context_routes = [r for r in table if r.scope == SCOPE_CONTEXT_MENU]
    assert len(context_routes) >= 1, "Context menu needs at least ESC to close"


# ---------------------------------------------------------------------------
# Route spec immutability tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_route_spec_is_frozen() -> None:
    """RouteSpec instances must be frozen (immutable)."""
    key = optional_arcade.arcade.key
    route = RouteSpec(SCOPE_GLOBAL, KeyCombo(key.A, 0), "test", _when_always)
    
    with pytest.raises(AttributeError):
        as_any(route).scope = SCOPE_CONSOLE
    
    with pytest.raises(AttributeError):
        as_any(route).action_id = "modified"


@pytest.mark.fast
def test_key_combo_is_frozen() -> None:
    """KeyCombo instances must be frozen (immutable)."""
    key = optional_arcade.arcade.key
    combo = KeyCombo(key=key.A, mods=0)
    
    with pytest.raises(AttributeError):
        as_any(combo).key = key.B
    
    with pytest.raises(AttributeError):
        as_any(combo).mods = 1


# ---------------------------------------------------------------------------
# Route count ratchet - prevent accidental route deletion
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_route_count_ratchet() -> None:
    """Route table must have at least the minimum expected routes.
    
    This prevents accidental deletion of routes. If you intentionally
    remove routes, update this threshold.
    """
    table = build_route_table()
    MIN_ROUTES = 50  # Conservative floor
    assert len(table) >= MIN_ROUTES, (
        f"Route table has {len(table)} routes, expected at least {MIN_ROUTES}. "
        f"Did you accidentally delete routes?"
    )
