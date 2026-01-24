from __future__ import annotations

from types import SimpleNamespace

from engine.behaviours.light_source import LightSource


class _StubLight:
    def __init__(self, radius: float, color: tuple[int, int, int, int]) -> None:
        self.radius = float(radius)
        self.color = color


class _StubLighting:
    def __init__(self) -> None:
        self.last_handle = None

    def register_dynamic_light(self, *, owner, radius, color=None, color_rgba=None, **kwargs):  # noqa: ANN001
        _ = (owner, color, kwargs)
        base = color_rgba if isinstance(color_rgba, (tuple, list)) else (255, 255, 255, 255)
        if isinstance(base, (tuple, list)):
            base = tuple(int(round(v)) for v in base[:4]) + (255,) * max(0, 4 - len(base))
        light = _StubLight(radius, base)  # type: ignore[arg-type]
        handle = SimpleNamespace(light=light, base_radius=float(radius), base_color=base)
        self.last_handle = handle
        return handle


def _build_light(seed: int) -> LightSource:
    entity = SimpleNamespace(center_x=0.0, center_y=0.0)
    lighting = _StubLighting()
    window = SimpleNamespace(lighting=lighting)
    source = LightSource(
        entity,
        window,  # type: ignore[arg-type]
        radius=80.0,
        color_rgba=(120, 160, 200, 255),
        flicker_enabled=True,
        flicker_seed=seed,
        flicker_speed=1.0,
        flicker_amount=0.5,
        flicker_radius_px=None,
        flicker_intensity=0.4,
    )
    source._uses_manager_flicker = False
    return source


def _sample_sequence(source: LightSource, steps: int = 12, dt: float = 1.0 / 60.0) -> list[tuple[float, tuple[int, int, int, int]]]:
    seq: list[tuple[float, tuple[int, int, int, int]]] = []
    for _ in range(steps):
        source.update(dt)
        handle = source._light_handle
        light = handle.light if handle is not None else None
        if light is None:
            seq.append((0.0, (0, 0, 0, 0)))
            continue
        seq.append((float(light.radius), tuple(light.color)))
    return seq


def test_seeded_legacy_flicker_is_deterministic() -> None:
    first = _build_light(123)
    second = _build_light(123)

    seq_a = _sample_sequence(first)
    seq_b = _sample_sequence(second)

    assert seq_a == seq_b


def test_different_seeds_produce_different_sequences() -> None:
    first = _build_light(123)
    second = _build_light(124)

    seq_a = _sample_sequence(first)
    seq_b = _sample_sequence(second)

    assert any(a != b for a, b in zip(seq_a, seq_b))


def test_seed_change_resets_deterministic_stream() -> None:
    source = _build_light(123)
    _sample_sequence(source, steps=5)
    source.config["flicker_seed"] = 999
    source.flicker_seed = 999  # type: ignore[attr-defined]

    seq_after = _sample_sequence(source, steps=6)

    fresh = _build_light(999)
    seq_fresh = _sample_sequence(fresh, steps=6)

    assert seq_after == seq_fresh
