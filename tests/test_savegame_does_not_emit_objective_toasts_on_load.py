from __future__ import annotations


def test_savegame_apply_does_not_emit_demo_complete_endcap_or_toasts() -> None:
    from engine.savegame import SaveGameV1, apply_savegame_to_window

    class _HUD:
        def __init__(self) -> None:
            self.toasts: list[str] = []

        def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
            self.toasts.append(str(message))

    class _Overlay:
        def __init__(self) -> None:
            self.shown = 0

        def show(self, *, seconds: float = 0.0) -> None:  # noqa: ARG002
            self.shown += 1

    class _State:
        flags: dict[str, bool] = {}

    class _GS:
        state = _State()

    class _Window:
        game_state_controller = _GS()
        player_hud = _HUD()
        demo_complete_overlay = _Overlay()

        def request_scene_change(self, _scene_path: str) -> None:
            return

    window = _Window()
    save = SaveGameV1(
        scene_path="scenes/door_field.json",
        player_x=0.0,
        player_y=0.0,
        flags={"demo.objective_started": True, "demo.reached_cellar": True},
    )

    apply_savegame_to_window(window, save)
    assert window.player_hud.toasts == []
    assert window.demo_complete_overlay.shown == 0

