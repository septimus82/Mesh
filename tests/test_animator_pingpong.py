from engine.behaviours.animator import SpriteAnimatorBehaviour


class DummyTexture:
    def __init__(self, name: str) -> None:
        self.name = name


class DummyAssets:
    def __init__(self) -> None:
        self.loaded = {}

    def get_texture(self, path: str):
        texture = DummyTexture(path)
        self.loaded[path] = texture
        return texture

    def load_sprite_sheet(self, *args, **kwargs):
        return []


class DummyWindow:
    def __init__(self) -> None:
        self.assets = DummyAssets()


class DummyEntity:
    def __init__(self) -> None:
        self.mesh_entity_data = {}
        self.texture = None


def _make_animator(states, initial_state="ping"):
    window = DummyWindow()
    entity = DummyEntity()
    animations = {}
    for state_name, definition in states.items():
        frame_count = definition.get("frames")
        fps = definition.get("fps", 10.0)
        mode = definition.get("mode", "ping-pong")
        animations[state_name] = {
            "frames": [f"{state_name}_{i}" for i in range(frame_count)],
            "fps": fps,
            "mode": mode,
        }
    behaviour = SpriteAnimatorBehaviour(
        entity,
        window,
        animations=animations,
        animation_state=initial_state,
    )
    return behaviour, entity


def _step(behaviour: SpriteAnimatorBehaviour, dt: float = 0.1) -> None:
    behaviour.pre_update(dt)
    behaviour.update(dt)
    behaviour.late_update(dt)


def test_pingpong_sequence_three_frames():
    behaviour, _ = _make_animator({"ping": {"frames": 3}})
    indices = [behaviour.frame_index]
    for _ in range(7):
        _step(behaviour)
        indices.append(behaviour.frame_index)
    assert indices == [0, 1, 2, 1, 0, 1, 2, 1]


def test_pingpong_single_frame_stays_zero():
    behaviour, _ = _make_animator({"ping": {"frames": 1}})
    for _ in range(5):
        _step(behaviour)
        assert behaviour.frame_index == 0


def test_pingpong_two_frame_bounce():
    behaviour, _ = _make_animator({"ping": {"frames": 2}})
    indices = [behaviour.frame_index]
    for _ in range(5):
        _step(behaviour)
        indices.append(behaviour.frame_index)
    assert indices == [0, 1, 0, 1, 0, 1]


def test_play_resets_pingpong_direction():
    behaviour, _ = _make_animator({
        "ping": {"frames": 3},
        "other": {"frames": 2},
    })

    for _ in range(3):
        _step(behaviour)
    assert behaviour.frame_index == 1  # descending phase

    behaviour.play("other")
    assert behaviour.frame_index == 0

    _step(behaviour)
    assert behaviour.frame_index == 1
    _step(behaviour)
    assert behaviour.frame_index == 0
