from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from engine.input_runtime.capture_runtime_focus_model import (
    CaptureFocusSnapshot,
    SCOPE_AUTHORING_SELECTED,
    SCOPE_CAPTURE_MODE,
    SCOPE_COMMAND_PALETTE,
    SCOPE_CONFIRM_MODAL,
    SCOPE_CONTEXT_MENU,
    SCOPE_CONSOLE,
    SCOPE_ENTITY_PAINT,
    SCOPE_ENTITY_SELECT,
    SCOPE_GLOBAL,
    SCOPE_INLINE_RENAME,
    SCOPE_KEYBINDS,
    SCOPE_PALETTE_MODE,
    SCOPE_PROBLEMS,
    SCOPE_PROJECT_EXPLORER,
    SCOPE_TILE_PAINT,
    SCOPE_PRIORITY,
)


@dataclass(frozen=True, slots=True)
class MouseEvent:
    kind: str  # press|release|scroll
    button: int | None
    x: float
    y: float
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    modifiers: int = 0


@dataclass(frozen=True, slots=True)
class MouseRouteSpec:
    scope: str
    kind: str
    button: int | None
    action_id: str
    when: Callable[[CaptureFocusSnapshot], bool]


# ---------------------------------------------------------------------------
# Audit dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MouseRouteAuditIssue:
    """A single audit issue for a mouse route."""
    kind: str  # "conflict" | "duplicate" | "alias"
    scope: str
    combo: tuple[str, int | None]  # (event_kind, button)
    action_ids: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class MouseRouteAuditReport:
    """Full audit report for mouse routes."""
    conflicts: tuple[MouseRouteAuditIssue, ...]
    duplicates: tuple[MouseRouteAuditIssue, ...]
    aliases: tuple[MouseRouteAuditIssue, ...]


# ---------------------------------------------------------------------------
# Allowed alias pairs - intentional aliases that are permitted
# ---------------------------------------------------------------------------

# No known alias pairs for mouse routes currently; placeholder for future needs
# Format: frozenset of action_ids that can co-exist on the same (scope, combo)
ALLOWED_ALIAS_PAIRS: frozenset[frozenset[str]] = frozenset()


# ---------------------------------------------------------------------------
# When predicates
# ---------------------------------------------------------------------------

def _when_always(_snapshot: CaptureFocusSnapshot) -> bool:
    return True


def _when_debug(snapshot: CaptureFocusSnapshot) -> bool:
    return snapshot.show_debug


# ---------------------------------------------------------------------------
# Route identity and audit helpers
# ---------------------------------------------------------------------------

def _when_name(when: Callable[[CaptureFocusSnapshot], bool] | None) -> str:
    """Get the name of a when predicate function."""
    if when is None:
        return ""
    return when.__name__


def _mouse_route_identity(route: MouseRouteSpec) -> tuple[str, str, int | None, str, str]:
    """Get a unique identity tuple for a mouse route."""
    return (
        route.scope,
        route.kind,
        route.button,
        route.action_id,
        _when_name(route.when),
    )


def _mouse_route_sort_key(route: MouseRouteSpec) -> tuple[int, str, int, int | None, str]:
    """Get a deterministic sort key for a mouse route.
    
    Sort order: scope priority, kind, modifiers (none for now), button, action_id.
    """
    try:
        scope_priority = SCOPE_PRIORITY.index(route.scope)
    except ValueError:
        scope_priority = len(SCOPE_PRIORITY)  # unknown scopes go last
    
    kind_order = {"press": 0, "release": 1, "scroll": 2}.get(route.kind, 99)
    # button: None sorts before any button number
    button_key = route.button if route.button is not None else -1
    
    return (scope_priority, route.kind, kind_order, button_key, route.action_id)


def dedupe_mouse_routes(routes: Sequence[MouseRouteSpec]) -> tuple[MouseRouteSpec, ...]:
    """Deduplicate mouse routes, keeping first occurrence of exact duplicates.
    
    Routes are considered duplicates if (scope, kind, button, action_id, when_name) match.
    Returns routes in deterministic order: by scope priority, then kind, then button, then action_id.
    """
    seen: set[tuple[str, str, int | None, str, str]] = set()
    deduped: list[MouseRouteSpec] = []
    
    for route in routes:
        ident = _mouse_route_identity(route)
        if ident in seen:
            continue
        seen.add(ident)
        deduped.append(route)
    
    # Sort for deterministic ordering
    deduped.sort(key=_mouse_route_sort_key)
    
    return tuple(deduped)


def audit_mouse_routes(routes: Sequence[MouseRouteSpec]) -> MouseRouteAuditReport:
    """Audit mouse routes for conflicts, duplicates, and aliases.
    
    Returns:
        MouseRouteAuditReport with:
        - conflicts: routes where (scope, kind, button) maps to different action_ids
                    and those action_ids are not in ALLOWED_ALIAS_PAIRS
        - duplicates: exact duplicate routes (same identity tuple)
        - aliases: allowed alias pairs that were detected
    """
    # Group routes by (scope, kind, button) combo
    by_combo: dict[tuple[str, str, int | None], list[MouseRouteSpec]] = {}
    for route in routes:
        combo_key = (route.scope, route.kind, route.button)
        by_combo.setdefault(combo_key, []).append(route)
    
    # Track exact duplicates by full identity
    identity_counts: dict[tuple[str, str, int | None, str, str], int] = {}
    for route in routes:
        ident = _mouse_route_identity(route)
        identity_counts[ident] = identity_counts.get(ident, 0) + 1
    
    conflicts: list[MouseRouteAuditIssue] = []
    duplicates: list[MouseRouteAuditIssue] = []
    aliases: list[MouseRouteAuditIssue] = []
    
    # Check for duplicates (same full identity appearing multiple times)
    seen_dup_idents: set[tuple[str, str, int | None, str, str]] = set()
    for route in routes:
        ident = _mouse_route_identity(route)
        if identity_counts[ident] > 1 and ident not in seen_dup_idents:
            seen_dup_idents.add(ident)
            duplicates.append(MouseRouteAuditIssue(
                kind="duplicate",
                scope=route.scope,
                combo=(route.kind, route.button),
                action_ids=(route.action_id,),
                note=f"Exact duplicate route (count={identity_counts[ident]})",
            ))
    
    # Check for conflicts/aliases (same combo, different action_ids)
    for combo_key, group in by_combo.items():
        action_ids = frozenset(r.action_id for r in group)
        if len(action_ids) <= 1:
            continue  # No conflict: single action_id
        
        scope, kind, button = combo_key
        action_id_tuple = tuple(sorted(action_ids))
        
        # Check if this is an allowed alias pair
        is_alias = action_ids in ALLOWED_ALIAS_PAIRS
        
        if is_alias:
            aliases.append(MouseRouteAuditIssue(
                kind="alias",
                scope=scope,
                combo=(kind, button),
                action_ids=action_id_tuple,
                note="Allowed alias pair",
            ))
        else:
            when_names = sorted(set(_when_name(r.when) for r in group))
            conflicts.append(MouseRouteAuditIssue(
                kind="conflict",
                scope=scope,
                combo=(kind, button),
                action_ids=action_id_tuple,
                note=f"Different action_ids with when={when_names}",
            ))
    
    # Sort for deterministic output
    def issue_sort_key(issue: MouseRouteAuditIssue) -> tuple:
        try:
            scope_idx = SCOPE_PRIORITY.index(issue.scope)
        except ValueError:
            scope_idx = len(SCOPE_PRIORITY)
        return (scope_idx, issue.combo, issue.action_ids)
    
    conflicts.sort(key=issue_sort_key)
    duplicates.sort(key=issue_sort_key)
    aliases.sort(key=issue_sort_key)
    
    return MouseRouteAuditReport(
        conflicts=tuple(conflicts),
        duplicates=tuple(duplicates),
        aliases=tuple(aliases),
    )


def format_audit_issues(report: MouseRouteAuditReport, max_issues: int = 10) -> str:
    """Format audit issues for CI-friendly output.
    
    Args:
        report: The audit report to format.
        max_issues: Maximum number of issues to show per category.
    
    Returns:
        A compact printable summary of audit issues.
    """
    lines: list[str] = []
    
    if report.conflicts:
        lines.append(f"CONFLICTS ({len(report.conflicts)}):")
        for issue in report.conflicts[:max_issues]:
            lines.append(f"  [{issue.scope}] {issue.combo} -> {issue.action_ids}")
            lines.append(f"    {issue.note}")
        if len(report.conflicts) > max_issues:
            lines.append(f"  ... and {len(report.conflicts) - max_issues} more")
    
    if report.duplicates:
        lines.append(f"DUPLICATES ({len(report.duplicates)}):")
        for issue in report.duplicates[:max_issues]:
            lines.append(f"  [{issue.scope}] {issue.combo} -> {issue.action_ids}")
            lines.append(f"    {issue.note}")
        if len(report.duplicates) > max_issues:
            lines.append(f"  ... and {len(report.duplicates) - max_issues} more")
    
    if report.aliases:
        lines.append(f"ALLOWED ALIASES ({len(report.aliases)}):")
        for issue in report.aliases[:max_issues]:
            lines.append(f"  [{issue.scope}] {issue.combo} -> {issue.action_ids}")
        if len(report.aliases) > max_issues:
            lines.append(f"  ... and {len(report.aliases) - max_issues} more")
    
    if not lines:
        return "No audit issues found."
    
    return "\n".join(lines)


def assert_no_conflicts_or_duplicates(report: MouseRouteAuditReport) -> None:
    """Assert that an audit report has no conflicts or duplicates.
    
    Raises AssertionError with a formatted message if issues are found.
    This is the canonical helper for tests to enforce route table integrity.
    """
    issues: list[str] = []
    
    if report.conflicts:
        issues.append(f"Found {len(report.conflicts)} conflict(s)")
    if report.duplicates:
        issues.append(f"Found {len(report.duplicates)} duplicate(s)")
    
    if issues:
        summary = format_audit_issues(report)
        raise AssertionError(f"Route table integrity violation: {', '.join(issues)}\n{summary}")


# ---------------------------------------------------------------------------
# Centralized route table validation
# ---------------------------------------------------------------------------

class RouteTableValidationError(Exception):
    """Raised when route table validation fails."""
    pass


def validate_route_table(routes: tuple[MouseRouteSpec, ...]) -> None:
    """Validate a route table for schema correctness and integrity.
    
    This is the single source of truth for route table validation.
    It checks:
    1. Type: must be a tuple (immutable)
    2. Non-empty: must contain at least one route
    3. Entry types: all entries must be MouseRouteSpec
    4. Field validity: each route has valid scope, kind, action_id, when
    5. Integrity: no conflicts or duplicates (via audit)
    
    Raises:
        RouteTableValidationError: If any validation check fails.
    """
    # 1. Must be a tuple
    if not isinstance(routes, tuple):
        raise RouteTableValidationError(
            f"Route table must be tuple, got {type(routes).__name__}"
        )
    
    # 2. Must be non-empty
    if len(routes) == 0:
        raise RouteTableValidationError("Route table must not be empty")
    
    # 3. All entries must be MouseRouteSpec
    for i, route in enumerate(routes):
        if not isinstance(route, MouseRouteSpec):
            raise RouteTableValidationError(
                f"Route at index {i} is {type(route).__name__}, expected MouseRouteSpec; "
                f"value={route!r}"
            )
    
    # 4. Field validity checks
    valid_kinds = ("press", "release", "scroll")
    for i, route in enumerate(routes):
        if not route.scope:
            raise RouteTableValidationError(
                f"Route {i} missing scope: action_id={route.action_id!r}, kind={route.kind!r}"
            )
        if route.kind not in valid_kinds:
            raise RouteTableValidationError(
                f"Route {i} has invalid kind={route.kind!r}, expected one of {valid_kinds}; "
                f"scope={route.scope!r}, action_id={route.action_id!r}"
            )
        if not route.action_id:
            raise RouteTableValidationError(
                f"Route {i} missing action_id: scope={route.scope!r}, kind={route.kind!r}"
            )
        if not callable(route.when):
            raise RouteTableValidationError(
                f"Route {i}.when is not callable: scope={route.scope!r}, "
                f"action_id={route.action_id!r}, kind={route.kind!r}"
            )
    
    # 5. Integrity: no conflicts or duplicates
    report = audit_mouse_routes(routes)
    if report.conflicts or report.duplicates:
        summary = format_audit_issues(report)
        raise RouteTableValidationError(
            f"Route table integrity violation:\n{summary}"
        )


# ---------------------------------------------------------------------------
# Route table builder
# ---------------------------------------------------------------------------

def build_mouse_routes() -> tuple[MouseRouteSpec, ...]:
    """Build the canonical mouse route table.
    
    Routes are added per-scope, then deduped and validated before returning.
    validate_route_table() is called automatically - if it fails, fix the
    route definitions here, not the validator.
    
    To add a new scope's routes, add them in a block like the existing ones,
    then register a dispatch prefix in capture_mouse_router.MOUSE_PREFIX_DISPATCH.
    """
    routes: list[MouseRouteSpec] = []

    # Modal scopes
    for kind in ("press", "release", "scroll"):
        routes.append(MouseRouteSpec(SCOPE_CONFIRM_MODAL, kind, None, "mouse.confirm_modal", _when_always))
        routes.append(MouseRouteSpec(SCOPE_CONTEXT_MENU, kind, None, "mouse.context_menu", _when_always))
        routes.append(MouseRouteSpec(SCOPE_KEYBINDS, kind, None, "mouse.keybinds", _when_always))
        routes.append(MouseRouteSpec(SCOPE_INLINE_RENAME, kind, None, "mouse.inline_rename", _when_always))
        routes.append(MouseRouteSpec(SCOPE_COMMAND_PALETTE, kind, None, "mouse.command_palette", _when_always))
        routes.append(MouseRouteSpec(SCOPE_CONSOLE, kind, None, "mouse.console", _when_always))
        routes.append(MouseRouteSpec(SCOPE_PROJECT_EXPLORER, kind, None, "mouse.project_explorer", _when_always))
        routes.append(MouseRouteSpec(SCOPE_PROBLEMS, kind, None, "mouse.problems", _when_always))

    # Authoring modes (debug)
    routes.append(MouseRouteSpec(SCOPE_CAPTURE_MODE, "press", None, "mouse.capture_mode.press", _when_debug))
    routes.append(MouseRouteSpec(SCOPE_CAPTURE_MODE, "release", None, "mouse.capture_mode.release", _when_debug))
    routes.append(MouseRouteSpec(SCOPE_CAPTURE_MODE, "scroll", None, "mouse.capture_mode.scroll", _when_debug))

    routes.append(MouseRouteSpec(SCOPE_TILE_PAINT, "press", None, "mouse.tile_paint.press", _when_debug))
    routes.append(MouseRouteSpec(SCOPE_TILE_PAINT, "release", None, "mouse.tile_paint.release", _when_debug))
    routes.append(MouseRouteSpec(SCOPE_TILE_PAINT, "scroll", None, "mouse.tile_paint.scroll", _when_debug))

    routes.append(MouseRouteSpec(SCOPE_ENTITY_PAINT, "press", None, "mouse.entity_paint.press", _when_debug))
    routes.append(MouseRouteSpec(SCOPE_ENTITY_PAINT, "scroll", None, "mouse.entity_paint.scroll", _when_debug))

    routes.append(MouseRouteSpec(SCOPE_ENTITY_SELECT, "press", None, "mouse.entity_select.press", _when_debug))
    routes.append(MouseRouteSpec(SCOPE_ENTITY_SELECT, "release", None, "mouse.entity_select.release", _when_debug))

    routes.append(MouseRouteSpec(SCOPE_AUTHORING_SELECTED, "press", None, "mouse.authoring_selected.press", _when_debug))
    routes.append(MouseRouteSpec(SCOPE_AUTHORING_SELECTED, "release", None, "mouse.authoring_selected.release", _when_debug))

    # Global/editor
    for kind in ("press", "release", "scroll"):
        routes.append(MouseRouteSpec(SCOPE_GLOBAL, kind, None, "mouse.global", _when_always))

    # Dedupe and validate before returning
    result = dedupe_mouse_routes(routes)
    validate_route_table(result)
    return result


def resolve_mouse_route(
    active_scopes: list[str],
    event: MouseEvent,
    routes: tuple[MouseRouteSpec, ...],
    snapshot: CaptureFocusSnapshot,
) -> str | None:
    for scope in active_scopes:
        for route in routes:
            if route.scope != scope:
                continue
            if route.kind != event.kind:
                continue
            if route.button is not None and event.button is not None and int(route.button) != int(event.button):
                continue
            if route.when(snapshot):
                return route.action_id
    return None
