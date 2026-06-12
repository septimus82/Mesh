"""
Tests for RNG service determinism and isolation.

These tests verify that:
1. Same seed produces same sequence
2. Named streams are properly isolated
3. State save/restore works correctly
4. Service reset clears all state
"""
from __future__ import annotations

from engine.rng_service import RNGService, RNGStream, get_rng, rng_service

# ============================================================================
# RNGStream tests
# ============================================================================


class TestRNGStream:
    """Tests for individual RNG streams."""

    def test_seed_determinism(self) -> None:
        """Same seed produces same sequence."""
        stream1 = RNGStream(seed=12345)
        stream2 = RNGStream(seed=12345)

        for _ in range(100):
            assert stream1.random() == stream2.random()

    def test_different_seeds_different_sequence(self) -> None:
        """Different seeds produce different sequences."""
        stream1 = RNGStream(seed=12345)
        stream2 = RNGStream(seed=54321)

        # Very unlikely to match
        values1 = [stream1.random() for _ in range(10)]
        values2 = [stream2.random() for _ in range(10)]
        assert values1 != values2

    def test_reseed_resets_sequence(self) -> None:
        """Reseeding resets to same sequence."""
        stream = RNGStream(seed=12345)
        values1 = [stream.random() for _ in range(10)]

        stream.seed(12345)
        values2 = [stream.random() for _ in range(10)]

        assert values1 == values2

    def test_call_count(self) -> None:
        """Call count tracks RNG usage."""
        stream = RNGStream(seed=1)
        assert stream.call_count == 0

        stream.random()
        assert stream.call_count == 1

        stream.uniform(0, 1)
        stream.randint(0, 10)
        assert stream.call_count == 3

        stream.seed(1)
        assert stream.call_count == 0  # Reset on seed

    def test_state_save_restore(self) -> None:
        """State can be saved and restored."""
        stream = RNGStream(seed=12345)

        # Advance the stream
        for _ in range(50):
            stream.random()

        # Save state
        state = stream.get_state()

        # Get next values
        expected = [stream.random() for _ in range(10)]

        # Restore state
        stream.set_state(state)

        # Should get same values
        actual = [stream.random() for _ in range(10)]
        assert actual == expected

    def test_uniform(self) -> None:
        """Uniform distribution is in range."""
        stream = RNGStream(seed=1)
        for _ in range(100):
            value = stream.uniform(10.0, 20.0)
            assert 10.0 <= value <= 20.0

    def test_randint(self) -> None:
        """Randint is in range."""
        stream = RNGStream(seed=1)
        for _ in range(100):
            value = stream.randint(5, 10)
            assert 5 <= value <= 10

    def test_choice(self) -> None:
        """Choice returns element from sequence."""
        stream = RNGStream(seed=1)
        options = ["a", "b", "c", "d"]
        for _ in range(100):
            value = stream.choice(options)
            assert value in options

    def test_sample(self) -> None:
        """Sample returns unique elements."""
        stream = RNGStream(seed=1)
        population = list(range(100))
        sample = stream.sample(population, 10)
        assert len(sample) == 10
        assert len(set(sample)) == 10  # All unique

    def test_shuffle(self) -> None:
        """Shuffle randomizes list."""
        stream = RNGStream(seed=1)
        original = [1, 2, 3, 4, 5]
        shuffled = original.copy()
        stream.shuffle(shuffled)
        # Very unlikely to stay in order
        assert shuffled != original or len(original) <= 1


# ============================================================================
# RNGService tests
# ============================================================================


class TestRNGService:
    """Tests for central RNG service."""

    def test_global_seed_determinism(self) -> None:
        """Global seed makes all streams deterministic."""
        service1 = RNGService()
        service2 = RNGService()

        service1.seed(12345)
        service2.seed(12345)

        for _ in range(100):
            assert service1.random() == service2.random()

    def test_named_streams_isolation(self) -> None:
        """Named streams are isolated from each other."""
        service = RNGService()
        service.seed(12345)

        stream_a = service.get_stream("a")
        stream_b = service.get_stream("b")

        # Streams should have different sequences
        values_a = [stream_a.random() for _ in range(10)]
        values_b = [stream_b.random() for _ in range(10)]
        assert values_a != values_b

    def test_named_streams_deterministic(self) -> None:
        """Same seed produces same named stream sequences."""
        service1 = RNGService()
        service2 = RNGService()

        service1.seed(99999)
        service2.seed(99999)

        stream1 = service1.get_stream("particles")
        stream2 = service2.get_stream("particles")

        for _ in range(50):
            assert stream1.random() == stream2.random()

    def test_stream_caching(self) -> None:
        """Getting same stream name returns same instance."""
        service = RNGService()
        stream1 = service.get_stream("test")
        stream2 = service.get_stream("test")
        assert stream1 is stream2

    def test_service_state_save_restore(self) -> None:
        """Service state can be saved and restored."""
        service = RNGService()
        service.seed(12345)

        # Use streams
        service.random()
        service.random()
        stream_a = service.get_stream("a")
        stream_a.random()

        # Save state
        state = service.get_state()

        # Get expected values
        expected_default = service.random()
        expected_a = stream_a.random()

        # Restore state
        service.set_state(state)

        # Should get same values
        assert service.random() == expected_default
        assert service.get_stream("a").random() == expected_a

    def test_service_reset(self) -> None:
        """Reset clears all state."""
        service = RNGService()
        service.seed(12345)
        service.get_stream("test")
        service.random()

        service.reset()

        assert service._global_seed is None
        assert len(service._streams) == 0

    def test_delegate_methods(self) -> None:
        """Service delegates to default stream."""
        service = RNGService()
        service.seed(12345)

        # All these should work
        service.random()
        service.uniform(0, 1)
        service.randint(0, 10)
        service.choice([1, 2, 3])
        service.choices([1, 2, 3], k=2)
        service.sample([1, 2, 3, 4, 5], 2)
        lst = [1, 2, 3]
        service.shuffle(lst)
        service.gauss(0, 1)


# ============================================================================
# Global service tests
# ============================================================================


class TestGlobalService:
    """Tests for the global rng_service singleton."""

    def test_global_service_exists(self) -> None:
        """Global service is available."""
        assert rng_service is not None

    def test_get_rng_default(self) -> None:
        """get_rng() returns default stream."""
        stream = get_rng()
        assert stream is rng_service._default

    def test_get_rng_named(self) -> None:
        """get_rng(name) returns named stream."""
        stream = get_rng("my_stream")
        assert stream is rng_service.get_stream("my_stream")


# ============================================================================
# Determinism integration tests
# ============================================================================


class TestDeterminismIntegration:
    """Integration tests for deterministic gameplay simulation."""

    def test_parallel_runs_identical(self) -> None:
        """Two runs with same seed produce identical results."""

        def simulate_game(seed: int) -> list[tuple[float, float, str]]:
            """Simulate a simple game run."""
            service = RNGService()
            service.seed(seed)

            ai_rng = service.get_stream("ai")
            loot_rng = service.get_stream("loot")

            results: list[tuple[float, float, str]] = []

            for _ in range(50):
                # Simulate game tick
                move = (service.uniform(-1, 1), service.uniform(-1, 1))
                ai_choice = ai_rng.choice(["attack", "defend", "move"])
                loot_rng.random()  # Simulate loot roll

                results.append((move[0], move[1], ai_choice))

            return results

        run1 = simulate_game(seed=42)
        run2 = simulate_game(seed=42)

        assert run1 == run2

    def test_stream_isolation_no_interference(self) -> None:
        """Using one stream doesn't affect another."""
        service = RNGService()
        service.seed(12345)

        ai_stream = service.get_stream("ai")
        particle_stream = service.get_stream("particles")

        # Get AI values
        ai_values_1 = [ai_stream.random() for _ in range(10)]

        # Reset
        service.seed(12345)
        ai_stream = service.get_stream("ai")
        particle_stream = service.get_stream("particles")

        # Use particle stream heavily
        for _ in range(1000):
            particle_stream.random()

        # AI values should be unchanged
        ai_values_2 = [ai_stream.random() for _ in range(10)]

        assert ai_values_1 == ai_values_2

    def test_save_restore_mid_game(self) -> None:
        """Save/restore works mid-game."""
        service = RNGService()
        service.seed(12345)

        # Play some ticks
        for _ in range(100):
            service.random()
            service.get_stream("ai").random()

        # Save
        saved_state = service.get_state()

        # Play more ticks and record
        expected = [service.random() for _ in range(10)]

        # Restore
        service.set_state(saved_state)

        # Should get same sequence
        actual = [service.random() for _ in range(10)]
        assert actual == expected
