"""Animation panel helpers for the editor."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from arcade import Sprite


def entity_has_animator(sprite: Optional["Sprite"]) -> bool:
    """Check if an entity has the Animator behaviour."""
    if sprite is None:
        return False
    behaviours = getattr(sprite, "mesh_behaviours", []) or []
    return "Animator" in behaviours


def get_animator_config(
    scene_controller: Any,
    sprite: Optional["Sprite"],
) -> Dict[str, Any]:
    """Get a deep copy of the animator config for an entity."""
    if sprite is None:
        return {}
    entity_data = scene_controller._ensure_entity_data_dict(sprite)
    config_root = scene_controller._ensure_behaviour_config_root(entity_data)
    animator_cfg = config_root.get("Animator", {})
    return copy.deepcopy(animator_cfg if isinstance(animator_cfg, dict) else {})


def get_animation_names(animator_cfg: Dict[str, Any]) -> List[str]:
    """Get sorted list of animation names from config."""
    animations = animator_cfg.get("animations", {}) if isinstance(animator_cfg, dict) else {}
    if isinstance(animations, dict):
        return sorted(animations.keys())
    return []


def apply_animator_runtime(
    sprite: "Sprite",
    animator_cfg: Dict[str, Any],
    animation_names: List[str],
    selected_index: int,
) -> None:
    """Apply animator config to runtime behaviours and optionally preview selected state."""
    behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
    for beh in behaviours:
        if getattr(beh, "mesh_behaviour_type", None) == "Animator":
            animations = animator_cfg.get("animations", {})
            if isinstance(animations, dict):
                for name, definition in animations.items():
                    if isinstance(definition, dict):
                        beh.animation_configs[name] = {
                            "fps": float(definition.get("fps", beh.animation_configs.get(name, {}).get("fps", 8.0))),
                            "mode": definition.get("mode", beh.animation_configs.get(name, {}).get("mode", "loop")),
                            "next": definition.get("next"),
                        }
            # Optionally preview selected state
            if animation_names:
                state = animation_names[selected_index]
                play = getattr(beh, "play", None)
                if callable(play):
                    play(state, force=True)
            break


def next_animation_field(current: str) -> str:
    """Get the next animation field in cycle order."""
    fields = ["mode", "fps", "frames"]
    if current not in fields:
        return fields[0]
    idx = (fields.index(current) + 1) % len(fields)
    return fields[idx]


def prev_animation_field(current: str) -> str:
    """Get the previous animation field in cycle order."""
    fields = ["mode", "fps", "frames"]
    if current not in fields:
        return fields[-1]
    idx = (fields.index(current) - 1) % len(fields)
    return fields[idx]


def cycle_animation_mode(current: str, forward: bool) -> str:
    """Cycle through animation modes."""
    modes = ["loop", "once", "ping-pong"]
    if current not in modes:
        current = "loop"
    idx = modes.index(current)
    idx = (idx + (1 if forward else -1)) % len(modes)
    return modes[idx]
