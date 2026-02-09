from engine.scene_navigation_model import NavInputs, build_nav_cache_plan, resolve_portals, stable_neighbor_order


def test_nav_cache_plan_deterministic() -> None:
    inputs = NavInputs(scene_path="scenes/a.json", revision=3)
    plan1 = build_nav_cache_plan(inputs)
    plan2 = build_nav_cache_plan(inputs)
    assert plan1 == plan2
    assert plan1.scene_path == "scenes/a.json"
    assert plan1.revision == 3


def test_portal_resolution_sorted() -> None:
    payload = {
        "portals": [
            {"from": "b", "to": "a", "via": "west"},
            {"from": "a", "to": "b", "via": "east"},
            {"from": "a", "to": "a", "via": ""},
        ]
    }
    links = resolve_portals(payload)
    assert [link.source for link in links] == ["a", "a", "b"]
    assert [link.target for link in links] == ["a", "b", "a"]


def test_neighbor_order_default_stable() -> None:
    assert stable_neighbor_order() == ((0, -1), (1, 0), (0, 1), (-1, 0))
