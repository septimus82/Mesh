"""
RNG Service - Centralized random number generation for deterministic replay.

This module provides a seedable, centralized RNG service that behaviours
and game systems should use instead of the global random module.

Design Goals:
1. Determinism: Same seed = same sequence, always
2. Isolation: Multiple named streams for different subsystems
3. Replay: RNG state can be saved/restored for replay verification
4. Minimal surface: Simple API that's easy to adopt

Usage Pattern:
    # In game initialization
    from engine.rng_service import rng_service
    rng_service.seed(12345)
    
    # In behaviours/systems
    from engine.rng_service import rng_service
    value = rng_service.uniform(0.0, 1.0)
    choice = rng_service.choice(["a", "b", "c"])
    
    # For isolated streams (e.g., particle systems)
    particles_rng = rng_service.get_stream("particles")
    particles_rng.uniform(-1.0, 1.0)
"""
from __future__ import annotations

import random
from typing import Any, Sequence, TypeVar


T = TypeVar("T")


class RNGStream:
    """A single random number stream with its own state.
    
    Wraps random.Random to provide a consistent interface.
    """

    def __init__(self, seed: int | None = None, name: str = "default") -> None:
        """Initialize RNG stream.
        
        Args:
            seed: Initial seed value (None for system entropy)
            name: Stream name for identification
        """
        self.name = name
        self._seed = seed
        self._rng = random.Random(seed)
        self._call_count = 0

    def seed(self, value: int | None = None) -> None:
        """Re-seed this stream.
        
        Args:
            value: New seed value
        """
        self._seed = value
        self._rng.seed(value)
        self._call_count = 0

    def get_state(self) -> tuple[Any, ...]:
        """Get current RNG state for save/restore.
        
        Returns:
            Tuple containing RNG state
        """
        return self._rng.getstate()

    def set_state(self, state: tuple[Any, ...]) -> None:
        """Restore RNG state.
        
        Args:
            state: State tuple from get_state()
        """
        self._rng.setstate(state)

    @property
    def call_count(self) -> int:
        """Number of RNG calls made since last seed."""
        return self._call_count

    # -------------------------------------------------------------------------
    # Standard random methods
    # -------------------------------------------------------------------------

    def random(self) -> float:
        """Return random float in [0.0, 1.0)."""
        self._call_count += 1
        return self._rng.random()

    def uniform(self, a: float, b: float) -> float:
        """Return random float N such that a <= N <= b."""
        self._call_count += 1
        return self._rng.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        """Return random int N such that a <= N <= b."""
        self._call_count += 1
        return self._rng.randint(a, b)

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        """Return random int from range(start, stop, step)."""
        self._call_count += 1
        if stop is None:
            return self._rng.randrange(start)
        return self._rng.randrange(start, stop, step)

    def choice(self, seq: Sequence[T]) -> T:
        """Return random element from non-empty sequence."""
        self._call_count += 1
        return self._rng.choice(seq)

    def choices(
        self,
        population: Sequence[T],
        weights: Sequence[float] | None = None,
        k: int = 1,
    ) -> list[T]:
        """Return k random elements with optional weights."""
        self._call_count += 1
        return self._rng.choices(population, weights=weights, k=k)

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        """Return k unique random elements from population."""
        self._call_count += 1
        return self._rng.sample(population, k)

    def shuffle(self, seq: list[T]) -> None:
        """Shuffle list in place."""
        self._call_count += 1
        self._rng.shuffle(seq)

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Return Gaussian distribution with mean mu and std sigma."""
        self._call_count += 1
        return self._rng.gauss(mu, sigma)

    def triangular(
        self,
        low: float = 0.0,
        high: float = 1.0,
        mode: float | None = None,
    ) -> float:
        """Return triangular distribution value."""
        self._call_count += 1
        return self._rng.triangular(low, high, mode)


class RNGService:
    """Central RNG service managing multiple named streams.
    
    This is the main entry point for deterministic random number generation.
    Use the global instance `rng_service` in your code.
    
    Features:
    - Single global seed affects all streams
    - Named streams for isolation (particles, AI, etc.)
    - State save/restore for replay
    - Call counting for debugging
    
    Example::
    
        from engine.rng_service import rng_service
        
        # Initialize with seed
        rng_service.seed(12345)
        
        # Use default stream
        value = rng_service.uniform(0, 100)
        
        # Use named stream
        ai_rng = rng_service.get_stream("ai")
        decision = ai_rng.choice(["attack", "defend", "flee"])
    """

    def __init__(self) -> None:
        """Initialize RNG service."""
        self._global_seed: int | None = None
        self._streams: dict[str, RNGStream] = {}
        self._default = RNGStream(name="default")

    def seed(self, value: int | None = None) -> None:
        """Set global seed for all streams.
        
        This resets all existing streams to a deterministic state
        derived from the global seed.
        
        Args:
            value: Seed value (None for system entropy)
        """
        self._global_seed = value
        self._default.seed(value)
        
        # Reset all named streams with derived seeds
        for name, stream in self._streams.items():
            # Derive stream seed from global seed + stream name
            if value is not None:
                stream_seed = hash((value, name)) & 0xFFFFFFFF
            else:
                stream_seed = None
            stream.seed(stream_seed)

    def get_stream(self, name: str) -> RNGStream:
        """Get or create a named RNG stream.
        
        Named streams allow isolation between subsystems.
        For example, particle effects won't affect AI decisions.
        
        Args:
            name: Stream name (e.g., "particles", "ai", "loot")
            
        Returns:
            RNGStream for the given name
        """
        if name not in self._streams:
            # Create new stream with derived seed
            if self._global_seed is not None:
                stream_seed = hash((self._global_seed, name)) & 0xFFFFFFFF
            else:
                stream_seed = None
            self._streams[name] = RNGStream(seed=stream_seed, name=name)
        return self._streams[name]

    def get_state(self) -> dict[str, Any]:
        """Get complete RNG state for save/restore.
        
        Returns:
            Dict containing all stream states
        """
        return {
            "global_seed": self._global_seed,
            "default": self._default.get_state(),
            "streams": {
                name: stream.get_state()
                for name, stream in self._streams.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore complete RNG state.
        
        Args:
            state: State dict from get_state()
        """
        self._global_seed = state.get("global_seed")
        
        default_state = state.get("default")
        if default_state:
            self._default.set_state(default_state)
        
        streams_state = state.get("streams", {})
        for name, stream_state in streams_state.items():
            stream = self.get_stream(name)
            stream.set_state(stream_state)

    def reset(self) -> None:
        """Reset service to initial state.
        
        Clears all streams and resets to unseeded state.
        """
        self._global_seed = None
        self._streams.clear()
        self._default = RNGStream(name="default")

    # -------------------------------------------------------------------------
    # Convenience methods (delegate to default stream)
    # -------------------------------------------------------------------------

    def random(self) -> float:
        """Return random float in [0.0, 1.0)."""
        return self._default.random()

    def uniform(self, a: float, b: float) -> float:
        """Return random float N such that a <= N <= b."""
        return self._default.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        """Return random int N such that a <= N <= b."""
        return self._default.randint(a, b)

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        """Return random int from range(start, stop, step)."""
        return self._default.randrange(start, stop, step)

    def choice(self, seq: Sequence[T]) -> T:
        """Return random element from non-empty sequence."""
        return self._default.choice(seq)

    def choices(
        self,
        population: Sequence[T],
        weights: Sequence[float] | None = None,
        k: int = 1,
    ) -> list[T]:
        """Return k random elements with optional weights."""
        return self._default.choices(population, weights, k)

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        """Return k unique random elements from population."""
        return self._default.sample(population, k)

    def shuffle(self, seq: list[T]) -> None:
        """Shuffle list in place."""
        self._default.shuffle(seq)

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Return Gaussian distribution value."""
        return self._default.gauss(mu, sigma)


# Global singleton instance
rng_service = RNGService()


def get_rng(name: str | None = None) -> RNGStream:
    """Get an RNG stream.
    
    Convenience function for getting RNG streams.
    
    Args:
        name: Stream name, or None for default stream
        
    Returns:
        RNGStream instance
    """
    if name is None:
        return rng_service._default
    return rng_service.get_stream(name)
