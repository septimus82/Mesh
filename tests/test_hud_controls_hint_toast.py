from engine.ui import maybe_enqueue_controls_hint_toast


class StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
        self.toasts.append(message)


class StubWindow:
    def __init__(self, *, start_scene: str) -> None:
        self._flags: dict[str, bool] = {}
        self.engine_config = type("Cfg", (), {"start_scene": start_scene})()
        self.player_hud = StubHUD()

    def get_flag(self, name: str, default: bool = False) -> bool:
        return bool(self._flags.get(name, default))

    def set_flag(self, name: str, value: bool = True) -> None:
        self._flags[str(name)] = bool(value)


def test_controls_hint_enqueued_once_on_hub_entry() -> None:
    hub = "packs/core_regions/scenes/Ridge Outpost_hub.json"
    window = StubWindow(start_scene=hub)

    first = maybe_enqueue_controls_hint_toast(window, scene_id=hub, seconds=4.0)
    assert first is True
    assert window.get_flag("hint_shown_controls") is True
    assert window.player_hud.toasts == [
        "Q: Quest Log  Tab: Inventory  I: Inspector  C: Character  F2: Editor  H: Help",
    ]

    second = maybe_enqueue_controls_hint_toast(window, scene_id=hub, seconds=4.0)
    assert second is False
    assert window.player_hud.toasts == [
        "Q: Quest Log  Tab: Inventory  I: Inspector  C: Character  F2: Editor  H: Help",
    ]


def test_controls_hint_not_enqueued_outside_hub() -> None:
    hub = "packs/core_regions/scenes/Ridge Outpost_hub.json"
    window = StubWindow(start_scene=hub)

    did = maybe_enqueue_controls_hint_toast(window, scene_id="packs/core_regions/scenes/Ridge Outpost_dungeon.json")
    assert did is False
    assert window.get_flag("hint_shown_controls") is False
    assert window.player_hud.toasts == []

