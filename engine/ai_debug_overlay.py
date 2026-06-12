from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:
    from engine.game import GameWindow

class AIDebugOverlay:
    def __init__(self):
        pass

    def draw(self, window: "GameWindow") -> None:
        scene = getattr(window, "scene_controller", None)
        if not scene:
            return

        # 1. Collect Data
        npcs = []
        transitions = []

        # Iterate entities
        sprites = scene.layers.get("entities", [])
        for sprite in sprites:
            data = getattr(sprite, "mesh_entity_data", {})
            behaviours = getattr(sprite, "mesh_behaviours", [])

            if "SceneTransition" in behaviours:
                transitions.append(sprite)
            elif data.get("name") or data.get("dialogue") or data.get("tags") or data.get("tag"):
                # Assume it's an NPC/Interactive if it has name/dialogue/tags
                npcs.append(sprite)

        # 2. Setup Camera for HUD
        # We assume the game loop has already drawn the scene, so we are drawing on top.
        # We need to switch to a screen-space camera (GUI camera).
        camera_controller = getattr(window, "camera_controller", None)
        if camera_controller and hasattr(camera_controller, "gui_camera"):
            camera_controller.gui_camera.use()

        # 3. Draw HUD Panel
        scene_id = getattr(scene, "current_scene_path", "Unknown")
        lines = [
            "AI DEBUG OVERLAY (F7)",
            f"Scene: {scene_id}",
            f"NPCs: {len(npcs)}",
            f"Transitions: {len(transitions)}",
        ]

        start_y = window.height - 60
        for line in lines:
            optional_arcade.arcade.draw_text(line, 10, start_y, optional_arcade.arcade.color.NEON_GREEN, 12, bold=True)
            start_y -= 16

        # 4. Draw World Labels (Projected to Screen)
        # We need the world camera to project coordinates
        world_camera = None
        if camera_controller:
            world_camera = camera_controller.camera

        for npc in npcs:
            wx, wy = npc.center_x, npc.center_y
            sx, sy = self._world_to_screen(window, world_camera, wx, wy)

            if not (0 <= sx <= window.width and 0 <= sy <= window.height):
                continue # Off screen

            # Draw label above
            data = getattr(npc, "mesh_entity_data", {})
            name = data.get("name", "Unknown")
            tags = list(data.get("tags", []))
            tag = data.get("tag")
            if tag and tag not in tags:
                tags.append(tag)

            label = f"{name}"
            if tags:
                label += f" {tags}"

            dialogue = data.get("dialogue")
            if dialogue:
                d_id = dialogue.get("id", "???")
                label += f"\nDial: {d_id}"

            optional_arcade.arcade.draw_text(label, sx, sy + 40, optional_arcade.arcade.color.WHITE, 10, anchor_x="center", align="center")
            optional_arcade.arcade.draw_circle_outline(sx, sy, 5, optional_arcade.arcade.color.WHITE)

        for trans in transitions:
            wx, wy = trans.center_x, trans.center_y
            sx, sy = self._world_to_screen(window, world_camera, wx, wy)

            if not (0 <= sx <= window.width and 0 <= sy <= window.height):
                continue

            # Draw marker
            # sx, sy is center, so left=sx-15, bottom=sy-15
            optional_arcade.arcade.draw_lbwh_rectangle_outline(sx - 15, sy - 15, 30, 30, optional_arcade.arcade.color.YELLOW, 2)

            # Label
            configs = getattr(trans, "mesh_behaviour_configs", [])
            target = "?"
            for cfg in configs:
                if cfg.get("type") == "SceneTransition":
                    target = cfg.get("target_scene", "?")
                    break

            optional_arcade.arcade.draw_text(f"To: {target}", sx, sy - 30, optional_arcade.arcade.color.YELLOW, 10, anchor_x="center")

    def _world_to_screen(self, window: "GameWindow", camera: Any, wx: float, wy: float) -> tuple[float, float]:
        if camera and hasattr(camera, "project"):
            try:
                projected = camera.project((wx, wy))
                if (
                    isinstance(projected, tuple)
                    and len(projected) == 2
                    and all(isinstance(value, (int, float)) for value in projected)
                ):
                    return float(projected[0]), float(projected[1])
            except Exception as exc:  # noqa: BLE001  # REASON: camera projection fallbacks must not block overlay rendering
                if not getattr(self, "_mesh_project_error_logged", False):
                    print(f"[Mesh][AIDebug] ERROR projecting world coords: {exc}")
                    setattr(self, "_mesh_project_error_logged", True)

        # Fallback: Manual projection if project() fails or doesn't exist
        # This assumes simple 2D camera without rotation/complex matrix
        if camera:
            # Arcade 2.6 Camera
            # screen_x = (world_x - camera_x) * zoom + viewport_width / 2
            # But camera position is usually bottom-left or center depending on implementation.
            # In Mesh, CameraController seems to track center or bottom-left?
            # CameraController.get_camera_center() returns center.

            # Let's try to use window.camera_controller.screen_to_world inverse logic
            # But screen_to_world uses camera.screen_to_world.

            # If we can't project, we might be out of luck for accurate screen space.
            # But let's try a basic offset based on camera position.
            cx, cy = (0.0, 0.0)
            if hasattr(window, "camera_controller") and window.camera_controller:
                cx, cy = window.camera_controller.get_camera_center()

            zoom = 1.0
            if hasattr(window, "camera_controller") and window.camera_controller and hasattr(window.camera_controller, "zoom_state"):
                 zoom = window.camera_controller.zoom_state.current

            # (wx - cx) is distance from center in world units
            # * zoom converts to screen units
            # + window.width / 2 centers it on screen
            sx = (wx - cx) * zoom + window.width / 2
            sy = (wy - cy) * zoom + window.height / 2
            return (sx, sy)

        return (wx, wy)
