# SceneIndex Contract

This document defines the *contract* for Mesh Engine's per-scene `SceneIndex`.

## Purpose

`SceneIndex` is a deterministic, defensive lookup structure built once per scene load.
It exists to avoid repeated linear scans over entities/sprites during gameplay and tooling.

## Indexed Keys

`SceneIndex` indexes the current scene's sprites/entities by:

- **`id`**: the entity ID (`mesh_entity_data["id"]`)
- **`zone_id`**: for TriggerZone entities (`mesh_entity_data["behaviour_config"]["TriggerZone"]["zone_id"]`)
- **`mesh_name`**: the sprite name (`sprite.mesh_name`)

## Normalization Rules

Lookups are **case-insensitive** and **whitespace-tolerant**.

- For all keys (`id`, `zone_id`, `mesh_name`):
  - leading/trailing whitespace is ignored
  - lookup is performed using a lowercased version of the key

There is **no slugification** or other transformation beyond trim + lowercase.

Rationale: legacy spawn resolution historically compared keys using `.strip().lower()`.

## Duplicate Policy

`SceneIndex` is defensive even if strict schema validation is enabled.

- **First wins**: if multiple sprites share the same normalized key, the *first* sprite encountered during index build is retained.
- **Duplicates are recorded**:
  - `duplicate_ids`: each duplicate occurrence beyond the first (normalized key)
  - `duplicate_zone_ids`: each duplicate occurrence beyond the first (normalized key)
  - `duplicate_mesh_names`: each duplicate occurrence beyond the first (normalized key)

No crash or exception occurs due to duplicates.

## Spawn Resolution Order

Spawn targeting in `SceneController._apply_pending_spawn_point` follows this order:

1. **Spawn marker**: sprites tagged `spawn_point` (via `spawn_id` or `mesh_name` marker ID)
2. **Entity id**: `SceneIndex.get_by_id(spawn_id)`
3. **Trigger zone id**: `SceneIndex.get_by_zone_id(spawn_id)`
4. **Mesh name**: `SceneIndex.get_first_by_mesh_name(spawn_id)`
5. **Scene spawns dictionary**: fallback to `scene["spawns"]` (non-sprite spawn definition)

If none match, the engine logs that the spawn point was not found.

## Determinism

- Index build order is deterministic and derived from the scene's loaded sprites.
- Duplicate resolution is deterministic because it always keeps the first occurrence.

