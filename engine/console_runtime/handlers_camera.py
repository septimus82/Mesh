"""Camera console command handler."""

from __future__ import annotations

from typing import Any

from engine.console_runtime.utils import parse_float


def handle_camera(controller: Any, args: list[str]) -> bool:
    """``camera`` command with zoom/shake/stopshake/areas sub-commands."""
    if not args:
        center_x, center_y = controller.window.get_camera_center()
        zoom_state = controller.window.camera_controller.zoom_state
        area = controller.window.camera_controller.active_area
        shake = controller.window.camera_controller.shake_state
        controller.log(
            f"Camera center=({center_x:.1f}, {center_y:.1f}) zoom={zoom_state.current:.2f}->{zoom_state.target:.2f}"
        )
        if area:
            controller.log(
                f"  area: {area.name} ({area.x},{area.y},{area.width}x{area.height}) priority={area.priority}"
            )
        else:
            controller.log("  area: <default>")
        if shake.duration > 0:
            remaining = max(0.0, shake.duration - shake.timer)
            controller.log(
                f"  shake: amp={shake.amplitude:.2f} freq={shake.frequency:.1f} remaining={remaining:.2f}s"
            )
        else:
            controller.log("  shake: <inactive>")
        return True

    sub = args[0].lower()
    if sub == "zoom":
        if len(args) < 2:
            controller.log("Usage: camera zoom <value>")
            return True
        zoom_value = parse_float(controller, args[1], "zoom")
        if zoom_value is None:
            return True
        controller.window.set_camera_zoom_target(zoom_value)
        controller.log(f"Camera zoom target set to {controller.window.camera_controller.zoom_state.target:.2f}")
        return True

    if sub == "shake":
        if len(args) < 3:
            controller.log("Usage: camera shake <duration> <amplitude> [frequency] [falloff]")
            return True
        duration = parse_float(controller, args[1], "duration")
        amplitude = parse_float(controller, args[2], "amplitude")
        frequency = parse_float(controller, args[3], "frequency") if len(args) >= 4 else 18.0
        falloff = parse_float(controller, args[4], "falloff") if len(args) >= 5 else 1.0
        if (
            duration is None
            or amplitude is None
            or frequency is None
            or falloff is None
        ):
            return True
        controller.window.start_camera_shake(
            duration=float(duration),
            amplitude=float(amplitude),
            frequency=float(frequency),
            falloff=float(falloff),
        )
        controller.log("Camera shake started")
        return True

    if sub == "stopshake":
        controller.window.stop_camera_shake()
        controller.log("Camera shake cleared")
        return True

    if sub == "areas":
        if not controller.window.camera_controller.areas:
            controller.log("No camera areas configured")
            return True
        controller.log("Camera areas:")
        for area in controller.window.camera_controller.areas:
            indicator = "*" if area is controller.window.camera_controller.active_area else "-"
            controller.log(
                f"  {indicator} {area.name} [{area.x},{area.y},{area.width}x{area.height}] "
                f"priority={area.priority} zoom={area.zoom or '<inherit>'}"
            )
        return True

    controller.log("Unknown camera command. Usage: camera [zoom|shake|stopshake|areas]")
    return True
