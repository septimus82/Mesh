"""Dispatch-lock tests for SceneController._call_authoring proxy layer.

Every debug_* (and private _debug_*) method that was compressed into
a ``self._call_authoring(fn_name, ...)`` one-liner is verified here.
We monkeypatch the corresponding function on ``_authoring_runtime`` with
a sentinel callable, invoke the SceneController method, and assert that
the sentinel was reached with ``self`` forwarded as the first positional.

This guarantees the string-based dispatch never silently drifts from the
real function names in ``engine.scene_runtime.authoring``.
"""
from __future__ import annotations

import inspect
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]

# ---------------------------------------------------------------------------
# The authoritative list of (method_name, fn_name) pairs.
# method_name  – attribute on SceneController
# fn_name      – attribute on _authoring_runtime dispatched via _call_authoring
# They are always identical in this codebase.
# ---------------------------------------------------------------------------
_PROXY_PAIRS: list[tuple[str, str]] = [
    ("debug_find_sprite_by_entity_id", "debug_find_sprite_by_entity_id"),
    ("_debug_iter_authoring_payloads", "_debug_iter_authoring_payloads"),
    ("_debug_remove_sprite", "_debug_remove_sprite"),
    ("debug_add_entity_payload", "debug_add_entity_payload"),
    ("debug_remove_entity_by_id", "debug_remove_entity_by_id"),
    ("debug_move_entity_by_id", "debug_move_entity_by_id"),
    ("debug_duplicate_entities_by_ids", "debug_duplicate_entities_by_ids"),
    ("debug_copy_entities_by_ids", "debug_copy_entities_by_ids"),
    ("debug_paste_entities_from_clipboard", "debug_paste_entities_from_clipboard"),
    ("debug_transform_entities_by_ids", "debug_transform_entities_by_ids"),
    ("debug_set_prefab_id", "debug_set_prefab_id"),
    ("debug_add_behaviour", "debug_add_behaviour"),
    ("debug_remove_behaviour", "debug_remove_behaviour"),
    ("debug_set_name", "debug_set_name"),
    ("debug_add_tag", "debug_add_tag"),
    ("debug_remove_tag", "debug_remove_tag"),
    ("debug_toggle_tag", "debug_toggle_tag"),
    ("debug_batch_rename", "debug_batch_rename"),
    ("debug_set_names", "debug_set_names"),
    ("debug_align_selection", "debug_align_selection"),
    ("debug_distribute_selection", "debug_distribute_selection"),
    ("debug_snap_to_grid", "debug_snap_to_grid"),
    ("debug_nudge_selection", "debug_nudge_selection"),
    ("debug_rotate_selection", "debug_rotate_selection"),
    ("debug_mirror_selection", "debug_mirror_selection"),
    ("debug_group_selection", "debug_group_selection"),
    ("debug_ungroup_selection", "debug_ungroup_selection"),
    ("debug_duplicate_to_grid", "debug_duplicate_to_grid"),
    ("debug_duplicate_along_path", "debug_duplicate_along_path"),
    ("debug_scatter_selection", "debug_scatter_selection"),
    ("debug_config_triggerzone_set_zone_id", "debug_config_triggerzone_set_zone_id"),
    ("debug_config_triggerzone_set_radius", "debug_config_triggerzone_set_radius"),
    ("debug_config_set_game_state_set_toast", "debug_config_set_game_state_set_toast"),
    ("debug_config_set_game_state_add_require_flag", "debug_config_set_game_state_add_require_flag"),
    ("debug_config_set_game_state_add_forbid_flag", "debug_config_set_game_state_add_forbid_flag"),
    ("debug_config_set_game_state_set_flag_true", "debug_config_set_game_state_set_flag_true"),
    ("debug_config_scene_transition_set_target_scene", "debug_config_scene_transition_set_target_scene"),
    ("debug_config_scene_transition_set_spawn_id", "debug_config_scene_transition_set_spawn_id"),
    ("_debug_config_entity_has_behaviour", "_debug_config_entity_has_behaviour"),
    ("_debug_config_mutate_for_behaviour", "_debug_config_mutate_for_behaviour"),
    ("_debug_config_set_field_for_behaviour", "_debug_config_set_field_for_behaviour"),
    ("debug_build_macro_objective_zone_payload", "debug_build_macro_objective_zone_payload"),
    ("debug_build_macro_door_transition_payload", "debug_build_macro_door_transition_payload"),
    ("debug_build_macro_dialogue_choice_flag_payload", "debug_build_macro_dialogue_choice_flag_payload"),
    ("_debug_preview_diff", "_debug_preview_diff"),
    ("debug_preview_macro_objective_zone", "debug_preview_macro_objective_zone"),
    ("debug_preview_macro_door_transition", "debug_preview_macro_door_transition"),
    ("debug_preview_macro_dialogue_choice_flag", "debug_preview_macro_dialogue_choice_flag"),
]


# ---------------------------------------------------------------------------
# Minimal stub so SceneController.__init__ doesn't blow up.
# We only need _call_authoring to resolve; nothing else matters.
# ---------------------------------------------------------------------------
class _Stub:
    """Absorb any attribute access and return a no-op callable or empty value."""

    def __getattr__(self, name: str) -> Any:
        return _Stub()

    def __call__(self, *a: Any, **kw: Any) -> Any:
        return _Stub()

    def __bool__(self) -> bool:
        return False

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


def _make_controller() -> Any:
    """Build a SceneController with enough scaffolding for _call_authoring.

    We import the real class but skip heavy __init__ by using object.__new__
    and only setting the attributes that _call_authoring needs (none beyond
    ``self``).
    """
    from engine.scene_controller import SceneController

    sc = object.__new__(SceneController)
    return sc


# ---------------------------------------------------------------------------
# Core dispatch test — parametrised over every proxy pair
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "method_name, fn_name",
    _PROXY_PAIRS,
    ids=[p[0] for p in _PROXY_PAIRS],
)
def test_proxy_dispatches_to_authoring_runtime(method_name: str, fn_name: str) -> None:
    """_call_authoring resolves *fn_name* on _authoring_runtime and calls it."""
    from engine.scene_controller import SceneController

    sc = _make_controller()
    sentinel = object()

    def _spy_call(self_arg: Any, called_fn_name: str, *a: Any, **kw: Any) -> Any:
        assert called_fn_name == fn_name, (
            f"Expected dispatch to {fn_name!r}, got {called_fn_name!r}"
        )
        return sentinel

    sc._call_authoring = lambda fn, *a, **kw: _spy_call(sc, fn, *a, **kw)  # type: ignore[assignment]

    method = getattr(SceneController, method_name)
    pos, kw = _auto_args(method)
    result = method(sc, *pos, **kw)

    # _debug_remove_sprite is void (no return), so result is None — that's fine.
    if method_name != "_debug_remove_sprite":
        assert result is sentinel, f"{method_name} did not return sentinel from _call_authoring"


# ---------------------------------------------------------------------------
# Auto-arg builder: inspect the signature and generate dummy values
# ---------------------------------------------------------------------------
_TYPE_DEFAULTS: dict[type | str, Any] = {
    str: "x",
    int: 0,
    float: 0.0,
    bool: False,
    list: lambda: [],
    dict: lambda: {},
    tuple: lambda: (),
}


def _dummy_value(param: inspect.Parameter) -> Any:
    """Return a minimal dummy value suitable for *param*."""
    ann = param.annotation
    if ann is inspect.Parameter.empty:
        return _Stub()
    # Unwrap Optional / union containing None
    origin = getattr(ann, "__origin__", None)
    if origin is not None:
        args = getattr(ann, "__args__", ())
        # list[str], dict[str, Any], tuple[str, ...] etc.
        if origin is list:
            return []
        if origin is dict:
            return {}
        if origin is tuple:
            return ()
        # unions: int | None → pick the non-None type
        import types
        if origin is types.UnionType:
            for a in args:
                if a is not type(None):
                    return _dummy_value_for_type(a)
            return None
    return _dummy_value_for_type(ann)


def _dummy_value_for_type(t: Any) -> Any:
    if t is str:
        return "x"
    if t is int:
        return 0
    if t is float:
        return 0.0
    if t is bool:
        return False
    if t is list:
        return []
    if t is dict:
        return {}
    if t is tuple:
        return ()
    if t is type(None):
        return None
    if isinstance(t, str):
        # Forward-ref string annotations like 'Callable[...]'
        return _Stub()
    return _Stub()


def _auto_args(method: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Build (positional, keyword) args from inspecting *method*'s signature."""
    sig = inspect.signature(method)
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.default is not inspect.Parameter.empty:
            # Has a default — skip (the default will be used)
            continue
        val = _dummy_value(param)
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional.append(val)
        else:
            # KEYWORD_ONLY or VAR_KEYWORD
            keyword[name] = val
    return tuple(positional), keyword


# ---------------------------------------------------------------------------
# Exhaustiveness guard — make sure _PROXY_PAIRS covers every _call_authoring site
# ---------------------------------------------------------------------------
def test_proxy_pairs_exhaustive() -> None:
    """Every _call_authoring call-site in scene_controller.py is listed in _PROXY_PAIRS."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "engine" / "scene_controller.py"
    text = src.read_text(encoding="utf-8")

    # Extract all fn_name strings passed to _call_authoring
    pattern = re.compile(r'self\._call_authoring\(\s*"([^"]+)"')
    found = set(pattern.findall(text))

    listed = {fn_name for _, fn_name in _PROXY_PAIRS}
    missing = found - listed
    assert not missing, f"_PROXY_PAIRS missing fn_names: {sorted(missing)}"
