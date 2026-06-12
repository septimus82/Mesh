from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


_SELECTION_METHODS = (
    "debug_align_selection",
    "debug_distribute_selection",
    "debug_snap_to_grid",
    "debug_nudge_selection",
    "debug_rotate_selection",
    "debug_mirror_selection",
    "debug_group_selection",
    "debug_ungroup_selection",
    "debug_duplicate_to_grid",
    "debug_duplicate_along_path",
    "debug_scatter_selection",
)


def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    return object.__new__(SceneController)


def test_selection_proxy_methods_are_bound_from_selection_module() -> None:
    from engine.scene_controller import SceneController

    for name in _SELECTION_METHODS:
        method = getattr(SceneController, name, None)
        assert callable(method), f"SceneController.{name} missing or not callable"
        assert getattr(method, "__module__", None) == "engine.scene_controller_selection"


def test_debug_align_selection_preserves_argument_forwarding_and_return_shape() -> None:
    sc = _make_controller()
    sentinel = {"changed": 2, "skipped": 0}
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _call_authoring(fn_name: str, *args: Any, **kwargs: Any) -> Any:
        calls.append((fn_name, args, kwargs))
        return sentinel

    sc._call_authoring = _call_authoring

    result = sc.debug_align_selection(["a", "b"], "x", "left", reference="group", primary_id="a")

    assert result is sentinel
    assert calls == [
        (
            "debug_align_selection",
            (["a", "b"], "x", "left"),
            {"reference": "group", "primary_id": "a"},
        )
    ]


def test_debug_duplicate_along_path_preserves_keyword_forwarding_and_return_shape() -> None:
    sc = _make_controller()
    sentinel = {"created": ["dup-1"], "selected_ids": ["dup-1"], "warnings": []}
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _call_authoring(fn_name: str, *args: Any, **kwargs: Any) -> Any:
        calls.append((fn_name, args, kwargs))
        return sentinel

    sc._call_authoring = _call_authoring

    result = sc.debug_duplicate_along_path(
        ["hero"],
        from_x=1.0,
        from_y=2.0,
        to_x=3.0,
        to_y=4.0,
        count=5,
        include_original=False,
        origin="group",
        name_mode="suffix",
        orient=True,
    )

    assert result is sentinel
    assert calls == [
        (
            "debug_duplicate_along_path",
            (["hero"],),
            {
                "from_x": 1.0,
                "from_y": 2.0,
                "to_x": 3.0,
                "to_y": 4.0,
                "count": 5,
                "include_original": False,
                "origin": "group",
                "name_mode": "suffix",
                "orient": True,
            },
        )
    ]
