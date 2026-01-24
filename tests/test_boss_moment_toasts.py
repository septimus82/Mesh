from engine.ui import maybe_enqueue_boss_defeat_toast, maybe_enqueue_boss_spawn_toast


class StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
        self.toasts.append(str(message))


class StubWindow:
    def __init__(self) -> None:
        self.player_hud = StubHUD()


class StubActor:
    def __init__(self, payload: dict) -> None:
        self.mesh_entity_data = dict(payload)
        self.mesh_name = payload.get("mesh_name") or payload.get("id") or payload.get("name") or "<unnamed>"


def test_boss_spawn_toast_enqueued_once() -> None:
    window = StubWindow()
    boss_payload = {"id": "slime_king", "name": "Slime King", "tags": ["boss"]}
    scene_id = "scenes/golden_slice.json"

    assert maybe_enqueue_boss_spawn_toast(window, boss_payload, scene_id, seconds=1.0) is True
    assert window.player_hud.toasts == ["BOSS: Slime King"]

    # does not repeat in the same scene load
    assert maybe_enqueue_boss_spawn_toast(window, boss_payload, scene_id, seconds=1.0) is False
    assert window.player_hud.toasts == ["BOSS: Slime King"]

    # non-boss does nothing
    assert maybe_enqueue_boss_spawn_toast(window, {"name": "Not Boss"}, scene_id, seconds=1.0) is False

def test_boss_defeat_toast_enqueued_once() -> None:
    window = StubWindow()
    actor = StubActor({"id": "slime_king", "name": "Slime King", "is_boss": True})
    scene_id = "scenes/golden_slice.json"

    assert maybe_enqueue_boss_defeat_toast(window, actor, scene_id, seconds=1.0) is True
    assert window.player_hud.toasts == ["Boss defeated!"]

    # does not repeat in the same scene load
    assert maybe_enqueue_boss_defeat_toast(window, actor, scene_id, seconds=1.0) is False
    assert window.player_hud.toasts == ["Boss defeated!"]

    non_boss = StubActor({"id": "slime", "name": "Slime", "tags": []})
    assert maybe_enqueue_boss_defeat_toast(window, non_boss, scene_id, seconds=1.0) is False


def test_boss_toasts_are_per_scene_load() -> None:
    window = StubWindow()
    boss_payload = {"id": "slime_king", "name": "Slime King", "tags": ["boss"]}

    assert maybe_enqueue_boss_spawn_toast(window, boss_payload, "scene_a", seconds=1.0) is True
    assert maybe_enqueue_boss_spawn_toast(window, boss_payload, "scene_a", seconds=1.0) is False

    # New scene_id should reset the per-scene-load store
    assert maybe_enqueue_boss_spawn_toast(window, boss_payload, "scene_b", seconds=1.0) is True

