# Scenes

Mesh scene schema lives at `docs/mesh_scene_spec.md`.

Engine version: 0.1.0

## scenes/door_field.json
[ok] Valid

- Entities: 11
- Layers: background, entities, foreground
- Tags: player, spawn_point

## scenes/door_interior.json
[ok] Valid

- Entities: 3
- Layers: background, entities, foreground
- Tags: player, spawn_point

## scenes/edited_scene.json
[ok] Valid

- Entities: 8
- Layers: background, entities, foreground
- Tags: hazard, npc, pickup, player

## scenes/main_menu.json
[ok] Valid

- Entities: 1
- Layers: ui
- Tags: -
- Warnings:
  - Entity[0] 'MainMenuController': unknown field 'visible' will be copied verbatim

## scenes/test_scene.json
[ok] Valid

- Entities: 7
- Layers: background, entities, foreground
- Tags: hazard, pickup, player, terrain
