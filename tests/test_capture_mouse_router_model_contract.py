"""Contract tests for capture_mouse_router_model.

These tests lock:
- Route table determinism (building twice yields identical results)
- No conflicts in route table
- Alias handling (intentional aliases are permitted)
- Coverage floor (each high-impact scope has routes)
- Centralized validation via validate_route_table()
"""
from __future__ import annotations

import pytest

from engine.input_runtime.capture_mouse_router_model import (
    ALLOWED_ALIAS_PAIRS,
    MouseRouteAuditIssue,
    MouseRouteAuditReport,
    MouseRouteSpec,
    RouteTableValidationError,
    audit_mouse_routes,
    assert_no_conflicts_or_duplicates,
    build_mouse_routes,
    dedupe_mouse_routes,
    format_audit_issues,
    validate_route_table,
    _when_always,
    _when_debug,
)
from engine.input_runtime.capture_runtime_focus_model import (
    SCOPE_CAPTURE_MODE,
    SCOPE_CONFIRM_MODAL,
    SCOPE_CONTEXT_MENU,
    SCOPE_ENTITY_PAINT,
    SCOPE_ENTITY_SELECT,
    SCOPE_GLOBAL,
    SCOPE_PRIORITY,
    SCOPE_TILE_PAINT,
)
from tests._typing import as_any


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_build_mouse_routes_is_deterministic() -> None:
    """Building the route table twice yields identical results."""
    first = build_mouse_routes()
    second = build_mouse_routes()
    assert first == second, "Route table must be deterministic"


@pytest.mark.fast
def test_dedupe_preserves_order_when_no_duplicates() -> None:
    """Dedupe returns routes in deterministic order even without duplicates."""
    routes = build_mouse_routes()
    deduped = dedupe_mouse_routes(routes)
    assert routes == deduped, "Dedupe should preserve routes when no duplicates"


@pytest.mark.fast
def test_dedupe_removes_exact_duplicates() -> None:
    """Dedupe removes exact duplicate routes, keeping first occurrence."""
    route = MouseRouteSpec(
        scope=SCOPE_GLOBAL,
        kind="press",
        button=None,
        action_id="test.action",
        when=_when_always,
    )
    routes = [route, route, route]
    deduped = dedupe_mouse_routes(routes)
    assert len(deduped) == 1
    assert deduped[0] == route


@pytest.mark.fast
def test_build_audit_dedupe_produces_clean_routes() -> None:
    """The canonical build+audit+dedupe pipeline produces a clean route table.
    
    This test ensures that:
    1. build_mouse_routes() returns routes
    2. audit_mouse_routes() reports no issues (or only allowed aliases)
    3. dedupe_mouse_routes() produces identical routes (since build already dedupes)
    4. Re-auditing confirms no conflicts or duplicates remain
    """
    # Step 1: Build routes
    routes = build_mouse_routes()
    assert len(routes) > 0, "build_mouse_routes() must return at least one route"
    
    # Step 2: Audit before dedupe
    report_before = audit_mouse_routes(routes)
    
    # Step 3: Dedupe
    deduped_routes = dedupe_mouse_routes(routes)
    
    # Step 4: Re-audit after dedupe  
    report_after = audit_mouse_routes(deduped_routes)
    
    # Verify: no conflicts remain (aliases are OK)
    assert len(report_after.conflicts) == 0, (
        f"Conflicts remain after dedupe:\n{format_audit_issues(report_after)}"
    )
    
    # Verify: no duplicates remain
    assert len(report_after.duplicates) == 0, (
        f"Duplicates remain after dedupe:\n{format_audit_issues(report_after)}"
    )
    
    # Verify: routes are identical (build_mouse_routes already dedupes)
    assert routes == deduped_routes, (
        "build_mouse_routes() should already return deduped routes"
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
    routes_1 = build_mouse_routes()
    report_1 = audit_mouse_routes(routes_1)
    deduped_1 = dedupe_mouse_routes(routes_1)
    
    # Second run (independent)
    routes_2 = build_mouse_routes()
    report_2 = audit_mouse_routes(routes_2)
    deduped_2 = dedupe_mouse_routes(routes_2)
    
    # Assert: raw builds are identical
    assert routes_1 == routes_2, (
        f"build_mouse_routes() is not idempotent.\n"
        f"First run: {len(routes_1)} routes\n"
        f"Second run: {len(routes_2)} routes"
    )
    
    # Assert: deduped outputs are identical (including order)
    assert deduped_1 == deduped_2, (
        f"dedupe_mouse_routes() is not idempotent.\n"
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
    routes = build_mouse_routes()
    report = audit_mouse_routes(routes)
    # Use the canonical helper for clear failure messages
    assert_no_conflicts_or_duplicates(report)


@pytest.mark.fast
def test_no_duplicates_in_route_table() -> None:
    """Route table has no exact duplicates (same identity tuple)."""
    routes = build_mouse_routes()
    report = audit_mouse_routes(routes)
    # Use the canonical helper for clear failure messages
    assert_no_conflicts_or_duplicates(report)


@pytest.mark.fast
def test_audit_detects_conflict() -> None:
    """Audit correctly detects conflicting routes."""
    routes = [
        MouseRouteSpec(SCOPE_GLOBAL, "press", None, "action.one", _when_always),
        MouseRouteSpec(SCOPE_GLOBAL, "press", None, "action.two", _when_always),
    ]
    report = audit_mouse_routes(routes)
    
    assert len(report.conflicts) == 1
    conflict = report.conflicts[0]
    assert conflict.kind == "conflict"
    assert conflict.scope == SCOPE_GLOBAL
    assert conflict.combo == ("press", None)
    assert "action.one" in conflict.action_ids
    assert "action.two" in conflict.action_ids


@pytest.mark.fast
def test_audit_detects_duplicate() -> None:
    """Audit correctly detects exact duplicate routes."""
    route = MouseRouteSpec(SCOPE_GLOBAL, "press", None, "test.action", _when_always)
    routes = [route, route]
    report = audit_mouse_routes(routes)
    
    assert len(report.duplicates) == 1
    dup = report.duplicates[0]
    assert dup.kind == "duplicate"
    assert "count=2" in dup.note


# ---------------------------------------------------------------------------
# Alias handling tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_allowed_alias_pairs_is_frozenset() -> None:
    """ALLOWED_ALIAS_PAIRS is a frozenset for immutability."""
    assert isinstance(ALLOWED_ALIAS_PAIRS, frozenset)


@pytest.mark.fast
def test_audit_categorizes_allowed_aliases() -> None:
    """Audit categorizes intentional aliases as aliases, not conflicts."""
    # If we have allowed alias pairs, test them
    if not ALLOWED_ALIAS_PAIRS:
        pytest.skip("No allowed alias pairs defined")
    
    # Pick first allowed pair and create routes
    pair = next(iter(ALLOWED_ALIAS_PAIRS))
    action_ids = list(pair)
    routes = [
        MouseRouteSpec(SCOPE_GLOBAL, "press", None, action_ids[0], _when_always),
        MouseRouteSpec(SCOPE_GLOBAL, "press", None, action_ids[1], _when_always),
    ]
    report = audit_mouse_routes(routes)
    
    assert len(report.aliases) == 1
    assert len(report.conflicts) == 0


# ---------------------------------------------------------------------------
# Coverage floor tests
# ---------------------------------------------------------------------------

# Minimum routes per high-impact scope (tiny guard, not overfitting)
SCOPE_MIN_ROUTES: dict[str, int] = {
    SCOPE_CONFIRM_MODAL: 2,
    SCOPE_CONTEXT_MENU: 2,
    SCOPE_CAPTURE_MODE: 2,
    SCOPE_TILE_PAINT: 2,
    SCOPE_ENTITY_PAINT: 1,
    SCOPE_ENTITY_SELECT: 1,
    SCOPE_GLOBAL: 2,
}


@pytest.mark.fast
def test_coverage_floor_per_scope() -> None:
    """Each high-impact scope has minimum number of routes."""
    routes = build_mouse_routes()
    
    scope_counts: dict[str, int] = {}
    for route in routes:
        scope_counts[route.scope] = scope_counts.get(route.scope, 0) + 1
    
    missing: list[str] = []
    for scope, min_count in SCOPE_MIN_ROUTES.items():
        actual = scope_counts.get(scope, 0)
        if actual < min_count:
            missing.append(f"{scope}: expected >= {min_count}, got {actual}")
    
    if missing:
        pytest.fail(f"Coverage floor violations:\n" + "\n".join(missing))


@pytest.mark.fast
def test_all_scopes_in_priority() -> None:
    """All scopes used in routes are defined in SCOPE_PRIORITY."""
    routes = build_mouse_routes()
    scopes_used = {route.scope for route in routes}
    scopes_defined = set(SCOPE_PRIORITY)
    
    unknown = scopes_used - scopes_defined
    if unknown:
        pytest.fail(f"Routes use scopes not in SCOPE_PRIORITY: {unknown}")


# ---------------------------------------------------------------------------
# Format/utility tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_format_audit_issues_empty_report() -> None:
    """format_audit_issues handles empty report."""
    report = MouseRouteAuditReport(conflicts=(), duplicates=(), aliases=())
    output = format_audit_issues(report)
    assert output == "No audit issues found."


@pytest.mark.fast
def test_format_audit_issues_truncation() -> None:
    """format_audit_issues respects max_issues limit."""
    conflicts = tuple(
        MouseRouteAuditIssue(
            kind="conflict",
            scope=SCOPE_GLOBAL,
            combo=("press", i),
            action_ids=(f"action.{i}",),
            note=f"Test conflict {i}",
        )
        for i in range(15)
    )
    report = MouseRouteAuditReport(conflicts=conflicts, duplicates=(), aliases=())
    
    output = format_audit_issues(report, max_issues=5)
    assert "... and 10 more" in output


# ---------------------------------------------------------------------------
# Route table structure tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_route_table_is_tuple() -> None:
    """Route table is a tuple for immutability."""
    routes = build_mouse_routes()
    assert isinstance(routes, tuple)


@pytest.mark.fast
def test_all_routes_have_required_fields() -> None:
    """All routes have valid scope, kind, action_id, and when."""
    routes = build_mouse_routes()
    
    for route in routes:
        assert route.scope, f"Route missing scope: {route}"
        assert route.kind in ("press", "release", "scroll"), f"Invalid kind: {route.kind}"
        assert route.action_id, f"Route missing action_id: {route}"
        assert callable(route.when), f"Route when is not callable: {route}"


@pytest.mark.fast
def test_route_table_sorted_by_scope_priority() -> None:
    """Routes are sorted by scope priority order."""
    routes = build_mouse_routes()
    
    # Extract scope indices in order they appear
    scope_indices: list[int] = []
    for route in routes:
        try:
            idx = SCOPE_PRIORITY.index(route.scope)
        except ValueError:
            idx = len(SCOPE_PRIORITY)
        scope_indices.append(idx)
    
    # Check indices are non-decreasing (sorted)
    for i in range(1, len(scope_indices)):
        if scope_indices[i] < scope_indices[i - 1]:
            pytest.fail(
                f"Route table not sorted by scope priority at index {i}: "
                f"{routes[i - 1].scope} -> {routes[i].scope}"
            )


# ---------------------------------------------------------------------------
# Centralized validation tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_validate_route_table_passes_for_valid_routes() -> None:
    """validate_route_table() passes for the production route table."""
    routes = build_mouse_routes()
    # Should not raise
    validate_route_table(routes)


@pytest.mark.fast
def test_validate_route_table_rejects_non_tuple() -> None:
    """validate_route_table() rejects non-tuple input."""
    routes = list(build_mouse_routes())  # Convert to list
    with pytest.raises(RouteTableValidationError, match="must be tuple"):
        validate_route_table(as_any(routes))


@pytest.mark.fast
def test_validate_route_table_rejects_empty() -> None:
    """validate_route_table() rejects empty route table."""
    with pytest.raises(RouteTableValidationError, match="must not be empty"):
        validate_route_table(())


@pytest.mark.fast
def test_validate_route_table_rejects_invalid_entry_type() -> None:
    """validate_route_table() rejects routes that aren't MouseRouteSpec."""
    with pytest.raises(RouteTableValidationError, match="expected MouseRouteSpec"):
        validate_route_table(as_any(("not a route",)))


@pytest.mark.fast
def test_validate_route_table_rejects_invalid_kind() -> None:
    """validate_route_table() rejects routes with invalid kind."""
    bad_route = MouseRouteSpec(
        scope=SCOPE_GLOBAL,
        kind="invalid_kind",  # Not press/release/scroll
        button=None,
        action_id="test.action",
        when=_when_always,
    )
    with pytest.raises(RouteTableValidationError, match="invalid kind"):
        validate_route_table((bad_route,))


@pytest.mark.fast
def test_validate_route_table_rejects_missing_action_id() -> None:
    """validate_route_table() rejects routes with empty action_id."""
    bad_route = MouseRouteSpec(
        scope=SCOPE_GLOBAL,
        kind="press",
        button=None,
        action_id="",  # Empty
        when=_when_always,
    )
    with pytest.raises(RouteTableValidationError, match="missing action_id"):
        validate_route_table((bad_route,))


@pytest.mark.fast
def test_validate_route_table_rejects_conflicts() -> None:
    """validate_route_table() rejects route tables with conflicts."""
    # Two routes with same (scope, kind, button) but different action_ids
    route1 = MouseRouteSpec(SCOPE_GLOBAL, "press", None, "action.one", _when_always)
    route2 = MouseRouteSpec(SCOPE_GLOBAL, "press", None, "action.two", _when_always)
    with pytest.raises(RouteTableValidationError, match="integrity violation"):
        validate_route_table((route1, route2))
