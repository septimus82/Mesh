"""Selection-operation proxy helpers for SceneController.

This module keeps selection-authoring forwarding logic isolated so
SceneController can remain an orchestration surface.
"""
from __future__ import annotations

from typing import Any


def debug_align_selection(
    controller: Any,
    entity_ids: list[str],
    axis: str,
    mode: str,
    reference: str = "primary",
    primary_id: str = "",
) -> Any:
    return controller._call_authoring(
        "debug_align_selection",
        entity_ids,
        axis,
        mode,
        reference=reference,
        primary_id=primary_id,
    )


def debug_distribute_selection(
    controller: Any,
    entity_ids: list[str],
    axis: str,
    mode: str = "gap",
    reference: str = "group",
    primary_id: str = "",
) -> Any:
    return controller._call_authoring(
        "debug_distribute_selection",
        entity_ids,
        axis,
        mode,
        reference=reference,
        primary_id=primary_id,
    )


def debug_snap_to_grid(
    controller: Any,
    entity_ids: list[str],
    step: int,
    axes: str = "xy",
    mode: str = "nearest",
) -> Any:
    return controller._call_authoring(
        "debug_snap_to_grid",
        entity_ids,
        step,
        axes=axes,
        mode=mode,
    )


def debug_nudge_selection(
    controller: Any,
    entity_ids: list[str],
    dx: float,
    dy: float,
    count: int = 1,
    step: float | None = None,
) -> Any:
    return controller._call_authoring(
        "debug_nudge_selection",
        entity_ids,
        dx,
        dy,
        count=count,
        step=step,
    )


def debug_rotate_selection(
    controller: Any,
    entity_ids: list[str],
    deg: float,
    about: str = "self",
    primary_id: str = "",
) -> Any:
    return controller._call_authoring(
        "debug_rotate_selection",
        entity_ids,
        deg,
        about=about,
        primary_id=primary_id,
    )


def debug_mirror_selection(
    controller: Any,
    entity_ids: list[str],
    axis: str,
    about: str = "group",
    primary_id: str = "",
    include_rotation: bool = True,
) -> Any:
    return controller._call_authoring(
        "debug_mirror_selection",
        entity_ids,
        axis,
        about=about,
        primary_id=primary_id,
        include_rotation=include_rotation,
    )


def debug_group_selection(
    controller: Any,
    entity_ids: list[str],
    name_base: str = "Group",
    about: str = "group",
    primary_id: str = "",
) -> Any:
    return controller._call_authoring(
        "debug_group_selection",
        entity_ids,
        name_base=name_base,
        about=about,
        primary_id=primary_id,
    )


def debug_ungroup_selection(
    controller: Any,
    entity_ids: list[str],
    mode: str = "auto",
) -> Any:
    return controller._call_authoring("debug_ungroup_selection", entity_ids, mode=mode)


def debug_duplicate_to_grid(
    controller: Any,
    entity_ids: list[str],
    rows: int = 1,
    cols: int = 1,
    dx: float = 0.0,
    dy: float = 0.0,
    origin: str = "selection",
    include_original: bool = True,
    name_mode: str = "none",
) -> Any:
    return controller._call_authoring(
        "debug_duplicate_to_grid",
        entity_ids,
        rows=rows,
        cols=cols,
        dx=dx,
        dy=dy,
        origin=origin,
        include_original=include_original,
        name_mode=name_mode,
    )


def debug_duplicate_along_path(
    controller: Any,
    entity_ids: list[str],
    from_x: float = 0.0,
    from_y: float = 0.0,
    to_x: float = 0.0,
    to_y: float = 0.0,
    count: int = 2,
    include_original: bool = True,
    origin: str = "selection",
    name_mode: str = "none",
    orient: bool = False,
) -> Any:
    return controller._call_authoring(
        "debug_duplicate_along_path",
        entity_ids,
        from_x=from_x,
        from_y=from_y,
        to_x=to_x,
        to_y=to_y,
        count=count,
        include_original=include_original,
        origin=origin,
        name_mode=name_mode,
        orient=orient,
    )


def debug_scatter_selection(
    controller: Any,
    entity_ids: list[str],
    n: int = 1,
    shape: str = "circle",
    radius: float = 64.0,
    width: float = 128.0,
    height: float = 128.0,
    center: str = "group",
    seed: int = 0,
    jitter_rot_deg: float = 0.0,
    snap_step: int | None = None,
    include_original: bool = True,
    name_mode: str = "none",
) -> Any:
    return controller._call_authoring(
        "debug_scatter_selection",
        entity_ids,
        n=n,
        shape=shape,
        radius=radius,
        width=width,
        height=height,
        center=center,
        seed=seed,
        jitter_rot_deg=jitter_rot_deg,
        snap_step=snap_step,
        include_original=include_original,
        name_mode=name_mode,
    )


def bind_selection_methods(cls) -> None:
    cls.debug_align_selection = debug_align_selection
    cls.debug_distribute_selection = debug_distribute_selection
    cls.debug_snap_to_grid = debug_snap_to_grid
    cls.debug_nudge_selection = debug_nudge_selection
    cls.debug_rotate_selection = debug_rotate_selection
    cls.debug_mirror_selection = debug_mirror_selection
    cls.debug_group_selection = debug_group_selection
    cls.debug_ungroup_selection = debug_ungroup_selection
    cls.debug_duplicate_to_grid = debug_duplicate_to_grid
    cls.debug_duplicate_along_path = debug_duplicate_along_path
    cls.debug_scatter_selection = debug_scatter_selection

