from __future__ import annotations

from engine.editor_runtime import editor_input_router_model as model


def test_route_table_deterministic_and_unique() -> None:
    routes1 = model.build_route_table()
    routes2 = model.build_route_table()
    assert isinstance(routes1, tuple)
    assert routes1 == routes2
    seen = {(r.scope, r.combo.key, r.combo.mods) for r in routes1}
    assert len(seen) == len(routes1)


def test_resolve_route_scope_priority() -> None:
    combo = model.KeyCombo(1, 0)
    routes = (
        model.RouteSpec("scope_b", combo, "b", "always"),
        model.RouteSpec("scope_a", combo, "a", "always"),
    )
    action = model.resolve_route(["scope_a", "scope_b"], combo, routes, {"always": True})
    assert action == "a"
