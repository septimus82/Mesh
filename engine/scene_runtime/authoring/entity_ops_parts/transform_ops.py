# ruff: noqa
# mypy: ignore-errors
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import entity_ops_align as _align_helpers
from .. import entity_ops_transform as _transform_helpers
from ._shared import _anchor_value, _build_entity_index, _entity_bounds, _snap_value, _sorted_dedup_ids, debug_apply_authored_scene_payload, get_authored_scene_payload

if TYPE_CHECKING:
    from ....scene_controller import SceneController
def debug_align_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    mode: str,
    reference: str = "primary",
    primary_id: str = "",
) -> dict[str, Any]:
    return _align_helpers.debug_align_selection(
        controller,
        entity_ids,
        axis,
        mode,
        reference=reference,
        primary_id=primary_id,
        sorted_dedup_ids=_sorted_dedup_ids,
        get_authored_scene_payload=get_authored_scene_payload,
        debug_apply_authored_scene_payload=debug_apply_authored_scene_payload,
        build_entity_index=_build_entity_index,
        entity_bounds=_entity_bounds,
        anchor_value=_anchor_value,
    )


def debug_distribute_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    mode: str = "gap",
    reference: str = "group",
    primary_id: str = "",
) -> dict[str, Any]:
    return _align_helpers.debug_distribute_selection(
        controller,
        entity_ids,
        axis,
        mode=mode,
        reference=reference,
        primary_id=primary_id,
        sorted_dedup_ids=_sorted_dedup_ids,
        get_authored_scene_payload=get_authored_scene_payload,
        debug_apply_authored_scene_payload=debug_apply_authored_scene_payload,
        build_entity_index=_build_entity_index,
        entity_bounds=_entity_bounds,
    )


def debug_snap_to_grid(
    controller: "SceneController",
    entity_ids: list[str],
    step: int,
    axes: str = "xy",
    mode: str = "nearest",
) -> dict:
    return _transform_helpers.debug_snap_to_grid(
        controller,
        entity_ids,
        step,
        axes=axes,
        mode=mode,
        sorted_dedup_ids=_sorted_dedup_ids,
        get_authored_scene_payload=get_authored_scene_payload,
        debug_apply_authored_scene_payload=debug_apply_authored_scene_payload,
        build_entity_index=_build_entity_index,
        snap_value=_snap_value,
    )


def debug_nudge_selection(
    controller: "SceneController",
    entity_ids: list[str],
    dx: float,
    dy: float,
    count: int = 1,
    step: float | None = None,
) -> dict:
    return _transform_helpers.debug_nudge_selection(
        controller,
        entity_ids,
        dx,
        dy,
        count=count,
        step=step,
        sorted_dedup_ids=_sorted_dedup_ids,
        get_authored_scene_payload=get_authored_scene_payload,
        debug_apply_authored_scene_payload=debug_apply_authored_scene_payload,
        build_entity_index=_build_entity_index,
    )


def debug_rotate_selection(
    controller: "SceneController",
    entity_ids: list[str],
    deg: float,
    about: str = "self",
    primary_id: str = "",
) -> dict:
    return _transform_helpers.debug_rotate_selection(
        controller,
        entity_ids,
        deg,
        about=about,
        primary_id=primary_id,
        sorted_dedup_ids=_sorted_dedup_ids,
        get_authored_scene_payload=get_authored_scene_payload,
        debug_apply_authored_scene_payload=debug_apply_authored_scene_payload,
        build_entity_index=_build_entity_index,
    )


def debug_mirror_selection(
    controller: "SceneController",
    entity_ids: list[str],
    axis: str,
    about: str = "group",
    primary_id: str = "",
    include_rotation: bool = True,
) -> dict:
    return _transform_helpers.debug_mirror_selection(
        controller,
        entity_ids,
        axis,
        about=about,
        primary_id=primary_id,
        include_rotation=include_rotation,
        sorted_dedup_ids=_sorted_dedup_ids,
        get_authored_scene_payload=get_authored_scene_payload,
        debug_apply_authored_scene_payload=debug_apply_authored_scene_payload,
        build_entity_index=_build_entity_index,
    )
