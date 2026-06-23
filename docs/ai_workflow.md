# Mesh AI Workflow

- **What `ai_ops` does:** exposes small, stable operations (create scenes, add/modify entities, behaviours, dialogue, quests, paint tiles, run validation) so AIs don't edit raw Python/JSON directly.
- **Job JSON shape:** top-level object with `operations: []`. Each entry has a `type` plus the fields it needs (e.g., `scene_path`, `prefab_name`, `entity_id`, `behaviour_name`, `params`, `ops` for tiles).
- **Operation types:**
  - `create_scene` - create a new scene from a named template.
  - `add_entity_from_prefab` - place a prefab instance in a scene at `x`, `y`.
  - `delete_entity` - remove an entity from a scene by `entity_id`.
  - `set_behaviour_params` - patch `behaviour_config` for one behaviour on an entity.
  - `edit_dialogue` - patch an entity dialogue payload.
  - `edit_quest` - patch a quest reference on a scene/entity.
  - `add_quest_definition` - add or replace a quest definition in a quests file.
  - `update_quest_definition` - update a quest definition in a quests file.
  - `delete_quest_definition` - remove a quest definition by `quest_id`.
  - `paint_tiles` - apply tile edits from `{layer, col, row, gid}` operations.
  - `add_light` - append a light entry to a scene.
  - `update_light` - patch a light entry by index.
  - `delete_light` - delete a light entry by index.
  - `run_validation` - validate a scene and return errors/warnings.
  - `add_world_scene` - add a scene entry to a world graph.
  - `link_world_scenes` - link two world scenes, optionally bidirectional.
  - `set_world_start` - set the world start scene and optional spawn.
  - `add_cutscene` - add or replace a cutscene definition.
  - `update_cutscene` - update a cutscene definition.
  - `delete_cutscene` - remove a cutscene definition by id.
  - `insert_cutscene_step` - insert a step into a cutscene.
  - `update_cutscene_step` - patch a cutscene step by index.
  - `delete_cutscene_step` - delete a cutscene step by index.

## Run from CLI (Plan workflow)

1) Generate a plan:

```bash
python -m mesh_cli ai-generate-plan "Add a crate room to scenes/cellar.json" --out plans/latest.plan.json
```

2) Lint the plan:

```bash
python -m mesh_cli plan lint-ai plans/latest.plan.json
```

3) (Optional) test the plan in a sandbox:

```bash
python -m mesh_cli plan test-ai plans/latest.plan.json
```

4) Apply the plan:

```bash
python -m mesh_cli apply-plan plans/latest.plan.json
python -m mesh_cli apply-plan plans/latest.plan.json --ai-safe
```

## Run in-game (console-only)

- Press `F1` to open the dev console.
- Type `ai_job jobs/add_crate_room.json`.
- Scene reloads automatically; open Editor Mode (`F4`) to tweak with inspector/panels and save with `F6`.

- **Job/Plan storage:** put AI-authored plans in `plans/` or jobs in `jobs/` for easy reuse.
