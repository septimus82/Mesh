"""
World Digest - Replay-grade determinism verification.

This module provides functions to compute stable cryptographic digests
of world state for verifying deterministic gameplay execution.

The digest is computed from:
- All entity positions and states
- All quest states
- Frame number / tick count

Design Principles:
1. Deterministic: Same world state = same digest, always
2. Stable: Output is independent of dict iteration order
3. Fast: Suitable for per-frame verification in debug mode
4. Minimal: Only includes gameplay-relevant state
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:  # pragma: no cover
    pass


def _sort_recursive(obj: Any) -> Any:
    """Recursively sort dict keys for deterministic JSON output.
    
    Args:
        obj: Any JSON-serializable value
        
    Returns:
        Same structure with all dicts having sorted keys
    """
    if isinstance(obj, dict):
        return {k: _sort_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_sort_recursive(item) for item in obj]
    return obj


def _stable_float(value: float, precision: int = 6) -> float:
    """Round float to fixed precision for deterministic comparison.
    
    Floating point arithmetic can produce slightly different results
    on different platforms. This rounds to a fixed precision.
    
    Args:
        value: Float value to normalize
        precision: Decimal places to keep (default: 6)
        
    Returns:
        Rounded float value
    """
    return round(value, precision)


def normalize_entity_state(entity: dict[str, Any]) -> dict[str, Any]:
    """Normalize entity state dict for deterministic hashing.
    
    Args:
        entity: Entity state dict from serialize_entity()
        
    Returns:
        Normalized dict with sorted keys and rounded floats
    """
    normalized: dict[str, Any] = {}
    
    # Required fields
    normalized["entity_id"] = str(entity.get("entity_id", ""))
    normalized["x"] = _stable_float(float(entity.get("x", 0.0)))
    normalized["y"] = _stable_float(float(entity.get("y", 0.0)))
    
    # Optional fields (only include if present)
    if "prefab_id" in entity and entity["prefab_id"]:
        normalized["prefab_id"] = str(entity["prefab_id"])
    
    if "tags" in entity and entity["tags"]:
        normalized["tags"] = sorted(str(t) for t in entity["tags"])
    
    if "animation_state" in entity and entity["animation_state"]:
        normalized["animation_state"] = str(entity["animation_state"])
    
    if "behaviour_state" in entity and entity["behaviour_state"]:
        # Deep sort behaviour state
        normalized["behaviour_state"] = _sort_recursive(entity["behaviour_state"])
    
    return normalized


def normalize_quest_state(quest: dict[str, Any]) -> dict[str, Any]:
    """Normalize quest state dict for deterministic hashing.
    
    Args:
        quest: Quest state dict from serialize_quest()
        
    Returns:
        Normalized dict with sorted keys
    """
    normalized: dict[str, Any] = {}
    
    # Required fields
    normalized["quest_id"] = str(quest.get("quest_id", ""))
    normalized["state"] = str(quest.get("state", "inactive"))
    normalized["current_step"] = int(quest.get("current_step", 0))
    
    # Optional fields
    if "counters" in quest and quest["counters"]:
        normalized["counters"] = {
            str(k): int(v) for k, v in sorted(quest["counters"].items())
        }
    
    # Timestamps excluded from digest (they're not deterministic)
    
    return normalized


def compute_entity_digest(entities: list[dict[str, Any]]) -> str:
    """Compute digest of entity states.
    
    Args:
        entities: List of entity state dicts
        
    Returns:
        SHA-256 hex digest of normalized entity state
    """
    if not entities:
        return hashlib.sha256(b"[]").hexdigest()
    
    # Normalize and sort by entity_id
    normalized = [normalize_entity_state(e) for e in entities]
    normalized.sort(key=lambda e: e.get("entity_id", ""))
    
    # JSON encode with sorted keys
    json_bytes = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


def compute_quest_digest(quests: list[dict[str, Any]]) -> str:
    """Compute digest of quest states.
    
    Args:
        quests: List of quest state dicts
        
    Returns:
        SHA-256 hex digest of normalized quest state
    """
    if not quests:
        return hashlib.sha256(b"[]").hexdigest()
    
    # Normalize and sort by quest_id
    normalized = [normalize_quest_state(q) for q in quests]
    normalized.sort(key=lambda q: q.get("quest_id", ""))
    
    json_bytes = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


def compute_world_digest(
    entities: list[dict[str, Any]] | None = None,
    quests: list[dict[str, Any]] | None = None,
    frame: int = 0,
    include_frame: bool = True,
) -> str:
    """Compute combined world state digest.
    
    This is the main entry point for determinism verification.
    Given the same inputs, this function will always produce
    the same output regardless of platform or Python version.
    
    Args:
        entities: List of entity state dicts (from serialize_entities)
        quests: List of quest state dicts (from serialize_quests)
        frame: Current frame/tick number
        include_frame: Whether to include frame in digest (default: True)
        
    Returns:
        SHA-256 hex digest of world state
        
    Example::
    
        entities = serialize_entities(scene_controller)
        quests = serialize_quests(quest_manager)
        digest = compute_world_digest(entities, quests, frame=100)
    """
    components: list[str] = []
    
    # Entity digest
    entity_digest = compute_entity_digest(entities or [])
    components.append(f"entities:{entity_digest}")
    
    # Quest digest
    quest_digest = compute_quest_digest(quests or [])
    components.append(f"quests:{quest_digest}")
    
    # Frame number (for sequence verification)
    if include_frame:
        components.append(f"frame:{frame}")
    
    # Combine components
    combined = "|".join(components)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def compute_world_digest_from_scene(
    scene_controller: Any,
    quest_manager: Any | None = None,
    frame: int = 0,
) -> str:
    """Convenience function to compute digest directly from scene objects.
    
    Args:
        scene_controller: SceneController with all_sprites
        quest_manager: Optional QuestManager with quests
        frame: Current frame number
        
    Returns:
        World state digest
    """
    # Import here to avoid circular imports
    from engine.save_runtime.entity_state import serialize_entities
    from engine.save_runtime.quest_state import serialize_quests
    
    entities = serialize_entities(scene_controller)
    
    # serialize_quests returns {"schema_version": ..., "quests": {...}}
    # Extract just the quest dicts as a list
    quests_data = serialize_quests(quest_manager) if quest_manager else {}
    quests_dict = quests_data.get("quests", {}) if isinstance(quests_data, dict) else {}
    quests_list = list(quests_dict.values()) if isinstance(quests_dict, dict) else []
    
    return compute_world_digest(entities, quests_list, frame)


class DigestTracker:
    """Track world digests across frames for determinism verification.
    
    Use this class to record digests during gameplay and compare
    against recorded sequences for replay verification.
    
    Example::
    
        tracker = DigestTracker(seed=12345)
        
        for frame in range(100):
            game.update(dt)
            digest = compute_world_digest_from_scene(scene_controller, frame=frame)
            tracker.record(frame, digest)
        
        # Later, verify replay produces same sequence
        replay_tracker = DigestTracker(seed=12345)
        for frame in range(100):
            replay.update(dt)
            digest = compute_world_digest_from_scene(scene_controller, frame=frame)
            replay_tracker.record(frame, digest)
        
        assert tracker.digests == replay_tracker.digests
    """

    def __init__(self, seed: int | None = None) -> None:
        """Initialize digest tracker.
        
        Args:
            seed: Optional RNG seed for identifying this run
        """
        self.seed = seed
        self.digests: dict[int, str] = {}

    def record(self, frame: int, digest: str) -> None:
        """Record digest for a frame.
        
        Args:
            frame: Frame number
            digest: World digest
        """
        self.digests[frame] = digest

    def get(self, frame: int) -> str | None:
        """Get recorded digest for frame.
        
        Args:
            frame: Frame number
            
        Returns:
            Digest string or None if not recorded
        """
        return self.digests.get(frame)

    def compare(self, other: "DigestTracker") -> list[tuple[int, str, str]]:
        """Compare this tracker against another.
        
        Args:
            other: DigestTracker to compare against
            
        Returns:
            List of (frame, this_digest, other_digest) for mismatches
        """
        mismatches: list[tuple[int, str, str]] = []
        all_frames = set(self.digests.keys()) | set(other.digests.keys())
        
        for frame in sorted(all_frames):
            this_digest = self.digests.get(frame, "<missing>")
            other_digest = other.digests.get(frame, "<missing>")
            if this_digest != other_digest:
                mismatches.append((frame, this_digest, other_digest))
        
        return mismatches

    def to_dict(self) -> dict[str, Any]:
        """Serialize tracker to dict.
        
        Returns:
            Dict with seed and digest sequence
        """
        return {
            "seed": self.seed,
            "digests": {str(k): v for k, v in sorted(self.digests.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DigestTracker":
        """Deserialize tracker from dict.
        
        Args:
            data: Dict from to_dict()
            
        Returns:
            DigestTracker instance
        """
        tracker = cls(seed=data.get("seed"))
        digests = data.get("digests", {})
        for frame_str, digest in digests.items():
            try:
                frame = int(frame_str)
                tracker.digests[frame] = str(digest)
            except (TypeError, ValueError):
                pass
        return tracker
