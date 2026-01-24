# Mesh AI Workflow

- **What `ai_ops` does:** exposes small, stable operations (create scenes, add/modify entities, behaviours, dialogue, quests, paint tiles, run validation) so AIs don't edit raw Python/JSON directly.
- **Job JSON shape:** top-level object with `operations: []`. Each entry has a `type` plus the fields it needs (e.g., `scene_path`, `prefab_name`, `entity_id`, `behaviour_name`, `params`, `ops` for tiles).
- **Common operation types:**
  - `add_entity_from_prefab` - place a prefab at `x`,`y`.
  - `set_behaviour_params` - patch `behaviour_config` for an entity.
  - `edit_dialogue` - set `behaviour_config.Dialogue.dialogue`.
  - `paint_tiles` - list of `{layer, col, row, gid}`.
  - `run_validation` - validate a scene.

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
