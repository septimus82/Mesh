from engine.ui import (
    maybe_enqueue_boss_spawn_toast,
    maybe_enqueue_miniboss_defeat_toast,
    maybe_enqueue_miniboss_spawn_toast,
)


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


def test_miniboss_spawn_toast_enqueued_once() -> None:
    window = StubWindow()
    payload = {"id": "mini_ogre", "name": "Mini Ogre", "tags": ["mini_boss"]}
    scene_id = "scenes/golden_slice.json"

    assert maybe_enqueue_miniboss_spawn_toast(window, payload, scene_id, seconds=1.0) is True
    assert window.player_hud.toasts == ["MINI-BOSS: Mini Ogre"]

    assert maybe_enqueue_miniboss_spawn_toast(window, payload, scene_id, seconds=1.0) is False
    assert window.player_hud.toasts == ["MINI-BOSS: Mini Ogre"]


def test_miniboss_defeat_toast_enqueued_once() -> None:
    window = StubWindow()
    actor = StubActor({"id": "mini_ogre", "name": "Mini Ogre", "is_mini_boss": True})
    scene_id = "scenes/golden_slice.json"

    assert maybe_enqueue_miniboss_defeat_toast(window, actor, scene_id, seconds=1.0) is True
    assert window.player_hud.toasts == ["Mini-boss defeated!"]

    assert maybe_enqueue_miniboss_defeat_toast(window, actor, scene_id, seconds=1.0) is False
    assert window.player_hud.toasts == ["Mini-boss defeated!"]


def test_miniboss_toasts_do_not_fire_for_bosses_and_do_not_collide_with_boss_keys() -> None:
    window = StubWindow()
    scene_id = "scenes/golden_slice.json"

    boss_payload = {"id": "slime_king", "name": "Slime King", "tags": ["boss"]}
    mini_payload = {"id": "slime_king", "name": "Slime King", "tags": ["mini_boss"]}

    assert maybe_enqueue_miniboss_spawn_toast(window, boss_payload, scene_id, seconds=1.0) is False

    assert maybe_enqueue_miniboss_spawn_toast(window, mini_payload, scene_id, seconds=1.0) is True
    assert maybe_enqueue_boss_spawn_toast(window, boss_payload, scene_id, seconds=1.0) is True

    assert window.player_hud.toasts == ["MINI-BOSS: Slime King", "BOSS: Slime King"]


def test_miniboss_toasts_are_per_scene_load() -> None:
    window = StubWindow()
    payload = {"id": "mini_ogre", "name": "Mini Ogre", "tags": ["mini_boss"]}

    assert maybe_enqueue_miniboss_spawn_toast(window, payload, "scene_a", seconds=1.0) is True
    assert maybe_enqueue_miniboss_spawn_toast(window, payload, "scene_a", seconds=1.0) is False

    assert maybe_enqueue_miniboss_spawn_toast(window, payload, "scene_b", seconds=1.0) is True


def test_miniboss_toasts_dedupe_is_per_entity_id_not_mesh_name() -> None:
    window = StubWindow()
    scene_id = "scenes/golden_slice.json"

    payload_a = {"id": "mini_a", "mesh_name": "ThemedEnemy", "name": "Mini A", "tags": ["mini_boss"]}
    payload_b = {"id": "mini_b", "mesh_name": "ThemedEnemy", "name": "Mini B", "tags": ["mini_boss"]}

    assert maybe_enqueue_miniboss_spawn_toast(window, payload_a, scene_id, seconds=1.0) is True
    assert maybe_enqueue_miniboss_spawn_toast(window, payload_b, scene_id, seconds=1.0) is True
    assert window.player_hud.toasts == ["MINI-BOSS: Mini A", "MINI-BOSS: Mini B"]

    actor_a = StubActor({"id": "mini_a", "mesh_name": "ThemedEnemy", "name": "Mini A", "is_mini_boss": True})
    actor_b = StubActor({"id": "mini_b", "mesh_name": "ThemedEnemy", "name": "Mini B", "is_mini_boss": True})

    assert maybe_enqueue_miniboss_defeat_toast(window, actor_a, scene_id, seconds=1.0) is True
    assert maybe_enqueue_miniboss_defeat_toast(window, actor_b, scene_id, seconds=1.0) is True
    assert window.player_hud.toasts[-2:] == ["Mini-boss defeated!", "Mini-boss defeated!"]
