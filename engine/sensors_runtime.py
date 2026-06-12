"""
Runtime state management for sensors.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from .physics_model import Aabb
from .sensors_model import SensorDef, SensorEvent, diff_overlaps, parse_sensors
from .spatial_hash_model import SpatialHashConfig, SpatialHashIndex, build_spatial_hash, query_aabb


def _sensor_aabb(sensor: SensorDef) -> Aabb:
    return sensor.aabb

class SensorRuntime:
    def __init__(self, *, cell_size_px: int = 128):
        self.last_overlaps_by_entity: Dict[str, Tuple[str, ...]] = {}
        # Cache parsed sensors by object ID of the payload to avoid re-parsing every frame if payload passed
        self._sensor_cache: Dict[int, Tuple[SensorDef, ...]] = {}
        self._sensor_hash_cache: Dict[int, SpatialHashIndex] = {}
        self._hash_cfg = SpatialHashConfig(cell_size_px=int(cell_size_px))
        self.perf_enabled: bool = False
        self.candidate_count: int = 0
        self.exact_checks_count: int = 0

    def get_sensors(self, scene_payload: dict[str, Any]) -> Tuple[SensorDef, ...]:
        """Get or parse sensors from the payload."""
        pid = id(scene_payload)
        if pid in self._sensor_cache:
            return self._sensor_cache[pid]

        sensors = parse_sensors(scene_payload)
        self._sensor_cache[pid] = sensors
        return sensors

    def _get_sensor_index(self, scene_payload: dict[str, Any], sensors: Tuple[SensorDef, ...]) -> SpatialHashIndex:
        pid = id(scene_payload)
        cached = self._sensor_hash_cache.get(pid)
        if cached is not None and cached.item_count == len(sensors):
            return cached
        index = build_spatial_hash(sensors, _sensor_aabb, self._hash_cfg)
        self._sensor_hash_cache[pid] = index
        return index

    def enable_perf_counters(self, enabled: bool = True) -> None:
        self.perf_enabled = bool(enabled)
        self.candidate_count = 0
        self.exact_checks_count = 0

    def update_entity_sensors(
        self,
        scene_payload: dict[str, Any],
        entity_id: str,
        entity_aabb: Aabb
    ) -> Tuple[SensorEvent, ...]:
        """
        Update sensor state for an entity and return events.
        """
        sensors = self.get_sensors(scene_payload)
        if not sensors:
            return ()

        index = self._get_sensor_index(scene_payload, sensors)
        candidate_ids = query_aabb(index, entity_aabb)
        if self.perf_enabled:
            self.candidate_count += len(candidate_ids)

        hits: list[str] = []
        for idx in candidate_ids:
            if idx < 0 or idx >= len(sensors):
                continue
            sensor = sensors[idx]
            if not sensor.enabled:
                continue
            if self.perf_enabled:
                self.exact_checks_count += 1
            if sensor.aabb.intersection(entity_aabb):
                hits.append(sensor.id)
        current_overlaps = tuple(hits)
        prev_overlaps = self.last_overlaps_by_entity.get(entity_id, ())

        # Optimization: if equal, no diff needed
        if current_overlaps == prev_overlaps:
            return ()

        events = diff_overlaps(entity_id, prev_overlaps, current_overlaps)
        self.last_overlaps_by_entity[entity_id] = current_overlaps

        return events

    def reset(self):
        """Clear all state."""
        self.last_overlaps_by_entity.clear()
        self._sensor_cache.clear()
        self._sensor_hash_cache.clear()
        self.candidate_count = 0
        self.exact_checks_count = 0
