from __future__ import annotations


def _update_animation_stage(self, delta_time: float) -> None:
    import engine.scene_controller_core as scene_controller_module

    for sprite in self._iter_layered_sprites():
        if getattr(sprite, "frozen", False):
            continue
        scene_controller_module.tick_animation_state(sprite, delta_time)
        animator = getattr(sprite, "mesh_animator", None)
        if animator is None:
            continue
        try:
            entity_data = getattr(sprite, "mesh_entity_data", None)
            desired_state = None
            if isinstance(entity_data, dict):
                raw_state = entity_data.get("animation_state")
                if isinstance(raw_state, str):
                    desired_state = raw_state
            if desired_state:
                animator.set_state(desired_state)
            animator.update(delta_time)
        except Exception as exc:
            if getattr(self.window, "strict_mode", False):
                raise
            if "animator_update" not in scene_controller_module._LOG_ONCE:
                scene_controller_module.logger.error("Animator update failed: %s", exc, exc_info=True)
                scene_controller_module._LOG_ONCE.add("animator_update")


def bind_animation_runtime_methods(cls) -> None:
    cls._update_animation_stage = _update_animation_stage