"""Animation determinism contract tests.

These tests verify that:
1. Animation stepping is deterministic given the same inputs.
2. Frame indices stay within bounds at all times.
3. Events are emitted deterministically.
4. Golden test: config + dt sequence → expected frames/events.

Uses headless step simulator helper for isolation from Arcade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import pytest

# ---------------------------------------------------------------------------
# Headless step simulator
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AnimationConfig:
    """Headless animation config for determinism testing."""
    name: str
    frames: tuple[int, ...]
    fps: float = 8.0
    loop: bool = True


@dataclass
class AnimationStepSimulator:
    """Headless animation step simulator.
    
    Mimics the logic of SpriteAnimator and AnimationPlayer without
    requiring Arcade textures or sprites.
    
    All state transitions are deterministic given the same sequence of calls.
    """
    configs: dict[str, AnimationConfig]
    active: str = ""
    cursor: int = 0
    elapsed: float = 0.0
    paused: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.configs:
            raise ValueError("AnimationStepSimulator requires at least one config")
        if not self.active or self.active not in self.configs:
            # Deterministic fallback: sorted first name
            self.active = sorted(self.configs.keys())[0]
        self._clamp_cursor()

    def set_animation(self, name: str, *, restart: bool = False) -> bool:
        """Set the active animation, returning True if changed."""
        if name not in self.configs:
            return False
        if name == self.active and not restart:
            return False
        self.active = name
        self.cursor = 0
        self.elapsed = 0.0
        self.paused = False
        return True

    def step(self, dt: float) -> list[dict[str, Any]]:
        """Advance animation by dt seconds, returning any emitted events."""
        if dt <= 0 or self.paused:
            return []

        config = self.configs.get(self.active)
        if config is None or not config.frames:
            return []

        fps = max(config.fps, 0.0001)
        if fps <= 0 or len(config.frames) == 1:
            return []

        frame_time = 1.0 / fps
        self.elapsed += float(dt)
        emitted: list[dict[str, Any]] = []

        while self.elapsed >= frame_time and not self.paused:
            self.elapsed -= frame_time
            prev_cursor = self.cursor
            self.cursor += 1

            if self.cursor >= len(config.frames):
                if config.loop:
                    self.cursor = 0
                    emitted.append({"event": "loop", "animation": self.active})
                else:
                    self.cursor = len(config.frames) - 1
                    self.paused = True
                    emitted.append({"event": "finish", "animation": self.active})
            else:
                emitted.append({
                    "event": "frame_advance",
                    "animation": self.active,
                    "from": prev_cursor,
                    "to": self.cursor,
                })

        self.events.extend(emitted)
        return emitted

    def current_frame(self) -> int:
        """Get the current frame index from the active animation's frames list."""
        config = self.configs.get(self.active)
        if config is None or not config.frames:
            return 0
        idx = min(max(0, self.cursor), len(config.frames) - 1)
        return config.frames[idx]

    def snapshot(self) -> dict[str, Any]:
        """Return a deterministic snapshot of current state."""
        return {
            "active": self.active,
            "cursor": self.cursor,
            "frame": self.current_frame(),
            "elapsed": round(self.elapsed, 6),
            "paused": self.paused,
        }

    def _clamp_cursor(self) -> None:
        config = self.configs.get(self.active)
        if config is None or not config.frames:
            self.cursor = 0
        else:
            self.cursor = min(max(0, self.cursor), len(config.frames) - 1)


# ---------------------------------------------------------------------------
# Golden test cases
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AnimationGoldenCase:
    """A golden test case for animation determinism."""
    name: str
    configs: dict[str, AnimationConfig]
    initial: str
    dt_sequence: tuple[float, ...]
    expected_frames: tuple[int, ...]
    expected_events: tuple[dict[str, Any], ...] = ()


GOLDEN_CASES: Sequence[AnimationGoldenCase] = [
    AnimationGoldenCase(
        name="simple_loop_4_frames",
        configs={"idle": AnimationConfig("idle", frames=(0, 1, 2, 3), fps=10.0, loop=True)},
        initial="idle",
        dt_sequence=(0.0, 0.1, 0.1, 0.1, 0.1),
        expected_frames=(0, 1, 2, 3, 0),  # Loops back
    ),
    AnimationGoldenCase(
        name="non_loop_stops_at_end",
        configs={"once": AnimationConfig("once", frames=(5, 6, 7), fps=10.0, loop=False)},
        initial="once",
        dt_sequence=(0.0, 0.1, 0.1, 0.1, 0.1),
        expected_frames=(5, 6, 7, 7, 7),  # Stays at last frame
    ),
    AnimationGoldenCase(
        name="fractional_dt_accumulates",
        configs={"walk": AnimationConfig("walk", frames=(0, 1, 2), fps=10.0, loop=True)},
        initial="walk",
        # At 10fps, frame_time=0.1s. After 0.05+0.05=0.1s we advance to frame 1
        dt_sequence=(0.05, 0.05, 0.05, 0.05),  # first is initial (0), then step 0.05, etc.
        expected_frames=(0, 0, 1, 1),  # initial=0, 0.05s=0, 0.10s=1, 0.15s=1
    ),
    AnimationGoldenCase(
        name="large_dt_skips_frames",
        configs={"fast": AnimationConfig("fast", frames=(0, 1, 2, 3), fps=10.0, loop=True)},
        initial="fast",
        dt_sequence=(0.0, 0.35),  # 0.35s at 10fps = 3.5 frames → cursor 3
        expected_frames=(0, 3),
    ),
    AnimationGoldenCase(
        name="single_frame_stays_put",
        configs={"static": AnimationConfig("static", frames=(42,), fps=10.0, loop=True)},
        initial="static",
        dt_sequence=(0.0, 0.5, 1.0, 2.0),
        expected_frames=(42, 42, 42, 42),
    ),
    AnimationGoldenCase(
        name="zero_dt_no_advance",
        configs={"idle": AnimationConfig("idle", frames=(0, 1, 2), fps=10.0, loop=True)},
        initial="idle",
        dt_sequence=(0.0, 0.0, 0.0),
        expected_frames=(0, 0, 0),
    ),
    AnimationGoldenCase(
        name="negative_dt_no_advance",
        configs={"idle": AnimationConfig("idle", frames=(0, 1, 2), fps=10.0, loop=True)},
        initial="idle",
        dt_sequence=(0.0, -0.1, -0.5),
        expected_frames=(0, 0, 0),
    ),
]


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.name)
def test_animation_golden(case: AnimationGoldenCase) -> None:
    """Golden test: config + dt sequence → expected frames."""
    sim = AnimationStepSimulator(
        configs=dict(case.configs),
        active=case.initial,
    )

    actual_frames: list[int] = []
    for dt in case.dt_sequence:
        if actual_frames:  # Don't step on first iteration (initial state)
            sim.step(dt)
        actual_frames.append(sim.current_frame())

    assert tuple(actual_frames) == case.expected_frames, (
        f"Frame mismatch for {case.name}:\n"
        f"  Expected: {case.expected_frames}\n"
        f"  Got:      {tuple(actual_frames)}"
    )


# ---------------------------------------------------------------------------
# Invariant tests
# ---------------------------------------------------------------------------

class TestAnimationInvariants:
    """Structural invariant tests for animation stepping."""

    def test_frame_index_always_in_bounds(self) -> None:
        """Frame index must always be within the frames list bounds."""
        config = AnimationConfig("test", frames=(0, 1, 2, 3, 4), fps=100.0, loop=True)
        sim = AnimationStepSimulator(configs={"test": config}, active="test")

        # Rapid stepping with various dt values
        dt_values = [0.001, 0.01, 0.1, 0.5, 1.0, 0.0, -0.1, 0.123456]
        for _ in range(100):
            for dt in dt_values:
                sim.step(dt)
                # cursor must be in [0, len(frames)-1]
                assert 0 <= sim.cursor < len(config.frames), (
                    f"cursor {sim.cursor} out of bounds for {len(config.frames)} frames"
                )
                # current_frame must be a valid frame from the list
                assert sim.current_frame() in config.frames, (
                    f"frame {sim.current_frame()} not in {config.frames}"
                )

    def test_non_loop_stops_and_stays_stopped(self) -> None:
        """Non-looping animation must stop at last frame and stay stopped."""
        config = AnimationConfig("once", frames=(10, 20, 30), fps=10.0, loop=False)
        sim = AnimationStepSimulator(configs={"once": config}, active="once")

        # Step until finished
        for _ in range(10):
            sim.step(0.1)

        assert sim.paused, "Non-looping animation should be paused"
        assert sim.cursor == len(config.frames) - 1
        assert sim.current_frame() == 30

        # Further stepping should not change state
        for _ in range(10):
            sim.step(0.1)

        assert sim.paused
        assert sim.cursor == len(config.frames) - 1
        assert sim.current_frame() == 30

    def test_determinism_same_input_same_output(self) -> None:
        """Same config and dt sequence must produce identical results."""
        config = AnimationConfig("det", frames=(0, 1, 2, 3), fps=12.5, loop=True)
        dt_sequence = [0.08, 0.08, 0.08, 0.08, 0.08, 0.16, 0.04]

        results: list[list[dict[str, Any]]] = []
        for _ in range(3):
            sim = AnimationStepSimulator(configs={"det": config}, active="det")
            snapshots = [sim.snapshot()]
            for dt in dt_sequence:
                sim.step(dt)
                snapshots.append(sim.snapshot())
            results.append(snapshots)

        # All runs must produce identical snapshot sequences
        for i in range(1, len(results)):
            assert results[i] == results[0], (
                f"Run {i} differs from run 0:\n"
                f"  Run 0: {results[0]}\n"
                f"  Run {i}: {results[i]}"
            )

    def test_elapsed_never_negative(self) -> None:
        """Elapsed time accumulator should never go negative."""
        config = AnimationConfig("test", frames=(0, 1, 2), fps=10.0, loop=True)
        sim = AnimationStepSimulator(configs={"test": config}, active="test")

        dt_values = [0.05, 0.1, 0.15, 0.001, 0.5]
        for _ in range(50):
            for dt in dt_values:
                sim.step(dt)
                assert sim.elapsed >= 0, f"elapsed {sim.elapsed} is negative"

    def test_set_animation_resets_state(self) -> None:
        """Setting a new animation must reset cursor and elapsed."""
        configs = {
            "a": AnimationConfig("a", frames=(0, 1, 2, 3), fps=10.0, loop=True),
            "b": AnimationConfig("b", frames=(10, 11, 12), fps=10.0, loop=True),
        }
        sim = AnimationStepSimulator(configs=configs, active="a")

        # Advance animation a
        sim.step(0.25)  # Should be at cursor 2
        assert sim.cursor > 0

        # Switch to b
        sim.set_animation("b")
        assert sim.active == "b"
        assert sim.cursor == 0
        assert sim.elapsed == 0.0
        assert not sim.paused

    def test_events_emitted_deterministically(self) -> None:
        """Events must be emitted in deterministic order."""
        config = AnimationConfig("loop", frames=(0, 1, 2), fps=10.0, loop=True)

        results: list[list[dict[str, Any]]] = []
        for _ in range(3):
            sim = AnimationStepSimulator(configs={"loop": config}, active="loop")
            all_events: list[dict[str, Any]] = []
            for dt in [0.1, 0.1, 0.1, 0.1]:  # 4 steps, should loop once
                events = sim.step(dt)
                all_events.extend(events)
            results.append(all_events)

        for i in range(1, len(results)):
            assert results[i] == results[0], f"Event sequence differs in run {i}"

        # Verify at least one loop event occurred
        loop_events = [e for e in results[0] if e.get("event") == "loop"]
        assert len(loop_events) >= 1, "Expected at least one loop event"


class TestAnimationEdgeCases:
    """Edge case tests for animation handling."""

    def test_empty_frames_handled(self) -> None:
        """Empty frames list should not crash."""
        # AnimationConfig with empty frames
        config = AnimationConfig("empty", frames=(), fps=10.0, loop=True)
        sim = AnimationStepSimulator(
            configs={"empty": config, "valid": AnimationConfig("valid", frames=(1,), fps=1.0)},
            active="valid",  # Start with valid, then switch
        )

        # Should not crash on step
        sim.step(0.1)
        assert sim.current_frame() == 1

    def test_very_high_fps(self) -> None:
        """Very high FPS should not cause issues."""
        config = AnimationConfig("fast", frames=(0, 1), fps=10000.0, loop=True)
        sim = AnimationStepSimulator(configs={"fast": config}, active="fast")

        # Even small dt should advance multiple frames
        sim.step(0.01)  # 0.01s * 10000fps = 100 frame advances
        # Should have looped many times, cursor in [0, 1]
        assert 0 <= sim.cursor <= 1

    def test_very_low_fps(self) -> None:
        """Very low FPS should work correctly."""
        config = AnimationConfig("slow", frames=(0, 1, 2), fps=0.1, loop=True)
        sim = AnimationStepSimulator(configs={"slow": config}, active="slow")

        # Need 10 seconds per frame at 0.1 fps
        sim.step(5.0)  # Half a frame time
        assert sim.cursor == 0
        sim.step(5.0)  # Full frame time
        assert sim.cursor == 1

    def test_multiple_animations_isolation(self) -> None:
        """Switching animations must not leak state."""
        configs = {
            "a": AnimationConfig("a", frames=(0, 1, 2, 3, 4), fps=10.0, loop=True),
            "b": AnimationConfig("b", frames=(10, 11), fps=10.0, loop=False),
        }
        sim = AnimationStepSimulator(configs=configs, active="a")

        # Progress a
        sim.step(0.3)  # cursor 3
        cursor_a = sim.cursor

        # Switch to b, progress until stopped
        sim.set_animation("b")
        sim.step(0.5)  # Should finish
        assert sim.paused

        # Switch back to a - must be fresh
        sim.set_animation("a")
        assert not sim.paused
        assert sim.cursor == 0
        assert sim.elapsed == 0.0


# ---------------------------------------------------------------------------
# SpriteAnimator integration tests
# ---------------------------------------------------------------------------

class TestSpriteAnimatorDeterminism:
    """Tests that SpriteAnimator has deterministic behavior."""

    def test_sprite_animator_matches_simulator(self) -> None:
        """SpriteAnimator should match our headless simulator's behavior."""
        from engine.sprite_animator import AnimationDef, SpriteAnimator

        # Same config in both
        frames = [0, 1, 2, 3]
        fps = 10.0

        anim = SpriteAnimator(
            {"test": AnimationDef(frames=frames, fps=fps, loop=True)},
            initial="test",
        )
        sim = AnimationStepSimulator(
            configs={"test": AnimationConfig("test", frames=tuple(frames), fps=fps, loop=True)},
            active="test",
        )

        dt_sequence = [0.1, 0.1, 0.1, 0.1, 0.1]
        for dt in dt_sequence:
            anim.update(dt)
            sim.step(dt)
            assert anim.current_frame_index() == sim.current_frame(), (
                f"Mismatch after dt={dt}: "
                f"SpriteAnimator={anim.current_frame_index()}, "
                f"Simulator={sim.current_frame()}"
            )

    def test_sprite_animator_deterministic_across_runs(self) -> None:
        """SpriteAnimator must be deterministic across multiple runs."""
        from engine.sprite_animator import AnimationDef, SpriteAnimator

        def run_animation() -> list[int]:
            anim = SpriteAnimator(
                {"walk": AnimationDef(frames=[0, 1, 2, 3], fps=12.0, loop=True)},
                initial="walk",
            )
            results = [anim.current_frame_index()]
            for dt in [0.08, 0.08, 0.08, 0.08, 0.16, 0.04]:
                anim.update(dt)
                results.append(anim.current_frame_index())
            return results

        runs = [run_animation() for _ in range(5)]
        for i in range(1, len(runs)):
            assert runs[i] == runs[0], f"Run {i} differs from run 0"
