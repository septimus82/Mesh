from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SceneLoadInputs:
    scene_path: str
    current_scene_path: str | None
    preserved_camera_state: dict[str, float] | None
    clear_assets_on_next_load: bool
    has_assets: bool
    has_audio: bool
    camera_center: tuple[float, float] | None
    camera_zoom: float | None


@dataclass(frozen=True, slots=True)
class SceneLoadPlan:
    scene_path: str
    is_reload: bool
    should_clear_event_queue: bool
    should_clear_assets: bool
    saved_camera_pos: tuple[float, float] | None
    saved_zoom: float | None


@dataclass(frozen=True, slots=True)
class SceneLoadEffects:
    clear_assets: bool
    restore_camera: bool
    restore_zoom: bool


def build_scene_load_plan(inputs: SceneLoadInputs) -> SceneLoadPlan:
    scene_path = str(inputs.scene_path or "").strip()
    current = str(inputs.current_scene_path or "").strip()
    is_reload = bool(scene_path and current and scene_path == current)

    saved_camera_pos: tuple[float, float] | None = None
    saved_zoom: float | None = None

    if is_reload:
        if inputs.preserved_camera_state:
            saved_camera_pos = (
                float(inputs.preserved_camera_state.get("x", 0.0)),
                float(inputs.preserved_camera_state.get("y", 0.0)),
            )
            saved_zoom = float(inputs.preserved_camera_state.get("zoom", 1.0))
        elif inputs.camera_center is not None:
            saved_camera_pos = (float(inputs.camera_center[0]), float(inputs.camera_center[1]))
            if inputs.camera_zoom is not None:
                saved_zoom = float(inputs.camera_zoom)

    should_clear_assets = bool(inputs.clear_assets_on_next_load and inputs.has_assets)

    return SceneLoadPlan(
        scene_path=scene_path,
        is_reload=is_reload,
        should_clear_event_queue=True,
        should_clear_assets=should_clear_assets,
        saved_camera_pos=saved_camera_pos,
        saved_zoom=saved_zoom,
    )


def compute_state_resets(plan: SceneLoadPlan) -> SceneLoadEffects:
    return SceneLoadEffects(
        clear_assets=bool(plan.should_clear_assets),
        restore_camera=bool(plan.is_reload and plan.saved_camera_pos is not None),
        restore_zoom=bool(plan.is_reload and plan.saved_zoom is not None),
    )
