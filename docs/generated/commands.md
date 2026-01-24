# Mesh CLI Commands

Reference documentation for all available CLI commands.

## `mesh add-puzzle`
Add a switch/door puzzle to a scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_path` | `str` | Yes | - | Path to scene file |
| `--prefix` | `prefix` | `str` | No | - | ID prefix for puzzle entities |
| `--switch-x` | `switch_x` | `int` | No | `0` | Switch X coordinate |
| `--switch-y` | `switch_y` | `int` | No | `0` | Switch Y coordinate |
| `--door-x` | `door_x` | `int` | No | `0` | Door X coordinate |
| `--door-y` | `door_y` | `int` | No | `0` | Door Y coordinate |
| `--reward-x` | `reward_x` | `int` | No | `0` | Reward X coordinate |
| `--reward-y` | `reward_y` | `int` | No | `0` | Reward Y coordinate |
| `--item` | `item` | `str` | No | - | Reward item ID |
| `--gold` | `gold` | `int` | No | `0` | Reward gold amount |

## `mesh ai-audit`
Audit scenes and quests for AI completeness

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--json` | `json` | `bool` | No | `False` | Output as JSON |

## `mesh ai-bundle`
Create AI bundle

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--scenes` | `scenes` | `str` | Yes | - | Scene paths |
| `--goal` | `goal` | `str` | Yes | - | Goal description |
| `--out` | `out` | `str` | Yes | - | Output file |

## `mesh ai-export-context`
Export scene context for AI

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_paths` | `str` | Yes | - | Paths to scene files |
| `--out` | `out` | `str` | No | - | Output JSON file path |

## `mesh ai-generate-plan`
Generate plan from prompt

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `prompt` | `str` | Yes | - | Prompt text |
| `--out` | `out` | `str` | Yes | - | Output file |
| `--allow-todos` | `allow_todos` | `bool` | No | `False` | Allow placeholder TODO/TBD tokens in the generated plan (default: strict). |

## `mesh ai-history`
Show AI plan history

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--scene` | `scene` | `str` | No | - | Filter by scene ID |
| `--plan` | `plan` | `str` | No | - | Filter by plan path |
| `--limit` | `limit` | `int` | No | `20` | Limit number of entries |
| `--json` | `json` | `bool` | No | `False` | Output as JSON |

## `mesh apply-plan`
Apply a content plan

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `plan_path` | `str` | No | - | Path to plan file |
| `--from-triage` | `from_triage` | `bool` | No | `False` | Use last triage plan |
| `--no-lint` | `no_lint` | `bool` | No | `False` | Skip linting |
| `--dry-run` | `dry_run` | `bool` | No | `False` | Dry run |
| `--run-tests` | `run_tests` | `bool` | No | `False` | Run tests after apply |
| `--ai-safe` | `ai_safe` | `bool` | No | `False` | Run AI safety checks (lint-ai + test-ai) before applying |

## `mesh assist`
Triage, apply, and test fixes

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | Yes | - | World to check |
| `--dry-run` | `dry_run` | `bool` | No | `False` | Dry run (triage only) |
| `--diff` | `diff` | `bool` | No | `False` | Show diff (requires --dry-run) |
| `--summary-json` | `summary_json` | `bool` | No | `False` | Output JSON summary (requires --dry-run) |
| `--also-text` | `also_text` | `bool` | No | `False` | Output text summary before JSON (requires --summary-json) |
| `--max-diff-lines` | `max_diff_lines` | `int` | No | `200` | Max lines to show per file diff (default: 200) |

## `mesh audit-content`
Audit content for unused assets

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_path` | `str` | Yes | - | Path to world file |
| `--json` | `json` | `bool` | No | `False` | Output JSON report |
| `--output` | `output` | `str` | No | - | Output file for JSON report |
| `--ignore` | `ignore` | `str` | No | - | Comma-separated list of glob patterns to ignore |
| `--allow-packs` | `allow_packs` | `str` | No | - | Comma-separated list of pack IDs to allow unused assets from |
| `--fail-on-unused` | `fail_on_unused` | `bool` | No | `False` | Fail if any unused content is found |
| `--max-unused-assets` | `max_unused_assets` | `int` | No | - | Max allowed unused assets |
| `--max-unused-prefabs` | `max_unused_prefabs` | `int` | No | - | Max allowed unused prefabs |
| `--max-unused-items` | `max_unused_items` | `int` | No | - | Max allowed unused items |
| `--max-unused-quests` | `max_unused_quests` | `int` | No | - | Max allowed unused quests |
| `--max-unused-textures` | `max_unused_textures` | `int` | No | - | Max allowed unused textures |
| `--max-unused-audio` | `max_unused_audio` | `int` | No | - | Max allowed unused audio files |
| `--max-unused-data` | `max_unused_data` | `int` | No | - | Max allowed unused data files |
| `--baseline` | `baseline` | `str` | No | - | Path to baseline lockfile for delta comparison |
| `--max-unused-delta` | `max_unused_delta` | `int` | No | - | Max allowed increase in unused assets vs baseline |

## `mesh audit-trend`
Analyze audit trends across lockfiles

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `locks` | `str` | Yes | - | Comma-separated list of lockfiles or patterns |
| `--json` | `json` | `bool` | No | `False` | Output JSON |

## `mesh auto-wire-transitions`
Auto-wire scene transitions

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_path` | `str` | Yes | - | World file |
| `--apply` | `apply` | `bool` | No | `False` | Apply changes |

## `mesh build-demo`
Build the demo content pack

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--diff-from` | `diff_from` | `str` | No | - | Path to old lockfile for changelog generation |
| `--strict-audit` | `strict_audit` | `bool` | No | `False` | Fail build if audit thresholds are exceeded |

## `mesh changelog`
Generate content changelog

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--from` | `old_lock` | `str` | Yes | - | Path to old lockfile |
| `--to` | `new_lock` | `str` | Yes | - | Path to new lockfile |
| `--out` | `out` | `str` | Yes | - | Output markdown file |

## `mesh check`
Run quality checks

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | `worlds/main_world.json` | World file to validate |
| `--full` | `full` | `bool` | No | `False` | Run full test suite |
| `--replay-trace` | `replay_trace` | `str` | No | - | Optional trace file to replay |
| `--frozen` | `frozen` | `bool` | No | `False` | Fail if content packs do not match content.lock.json |

## `mesh cli-smoke`
Run CLI smoke tests

## `mesh cli-snapshot`
Generate CLI structure snapshot

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Output JSON file path |
| `--verify` | `verify` | `bool` | No | `False` | Verify against existing snapshot |

## `mesh demo`
Demo helpers

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `demo_command` | `str` | No | - | Demo subcommand |

## `mesh diff-content`
Compare content locks

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--from` | `old_lock` | `str` | Yes | - | Path to old lockfile |
| `--to` | `new_lock` | `str` | No | - | Path to new lockfile (default: current state) |
| `--json` | `json` | `bool` | No | `False` | Output JSON |

## `mesh dist`
Build a distribution release

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--profile` | `profile` | `str` | Yes | - | Release profile |
| `--world` | `world` | `str` | Yes | - | World file to build |
| `--out` | `out` | `str` | No | - | Output directory |

## `mesh docs`
Generate documentation

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--verify` | `verify` | `bool` | No | `False` | Verify docs are up to date |

## `mesh doctor`
Diagnose project health

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World file to validate |
| `--quiet` | `quiet` | `bool` | No | `False` | Only summary + suggested commands |
| `--explain` | `explain` | `bool` | No | `False` | Output explain format (same as mesh explain) |
| `--json` | `json` | `bool` | No | `False` | Machine-readable output |

## `mesh doctor-assets`
Inventory content/assets deterministically and optionally apply safe fixes (no engine load)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Optional path to write JSON output |
| `--fix` | `fix` | `bool` | No | `False` | Apply safe auto-fixes in-place |
| `--strict` | `strict` | `bool` | No | `False` | Treat warnings as errors where applicable |

## `mesh drift-check`
Run encounter drift check with presets

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `preset` | `str` | Yes | - | Preset name (strict, standard, lenient) |
| `` | `old_path` | `str` | Yes | - | Baseline report or file |
| `` | `new_path` | `str` | Yes | - | New report or file |
| `--json` | `json` | `bool` | No | `False` | Output JSON |
| `--out` | `out` | `str` | No | - | Output file path |

## `mesh dump-state`
Print a deterministic debug state snapshot

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Optional path to write JSON instead of stdout |

## `mesh edit-scene`
Edit scene properties

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `path` | `str` | Yes | - | Path to scene file |
| `--budget` | `budget` | `float` | No | - | Set encounter budget |
| `--elite-cap` | `elite_cap` | `int` | No | - | Set elite cap |
| `--allow-elites` | `allow_elites` | `str` | No | - | Set allow elites |
| `--boss-reserve` | `boss_reserve` | `float` | No | - | Set boss budget reserve |
| `--add-transition` | `add_transition` | `str` | No | - | Target scene for new transition |
| `--at` | `at` | `str` | No | - | Coordinates x,y |
| `--spawn-id` | `spawn_id` | `str` | No | - | Spawn ID in target scene |

## `mesh encounter-report`
Generate encounter balance report

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `path` | `str` | Yes | - | World file, scene file, directory, or 'diff <old> <new>' |
| `--json` | `json` | `bool` | No | `False` | Output JSON to stdout |
| `--out` | `out` | `str` | No | - | Output file path |
| `--themes` | `themes` | `str` | No | - | Comma-separated list of themes to filter |
| `--difficulty` | `difficulty` | `str` | No | - | Comma-separated list of difficulties (default: easy,normal,hard) |
| `--only-dungeons` | `only_dungeons` | `bool` | No | `False` | Only process dungeon scenes |
| `--max-elite-delta` | `max_elite_delta` | `int` | No | - | Fail if elite count delta exceeds this |
| `--max-spawn-delta` | `max_spawn_delta` | `int` | No | - | Fail if spawn count delta exceeds this |
| `--max-cost-overrun` | `max_cost_overrun` | `float` | No | - | Fail if cost overrun exceeds this |
| `--fail-on-overrun` | `fail_on_overrun` | `bool` | No | `False` | Fail if any cost overrun increases |

## `mesh explain`
Explain doctor/validation failures

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World file to validate |
| `--last` | `last` | `bool` | No | `False` | Explain the most recent stored failure |
| `--json` | `json` | `bool` | No | `False` | Machine-readable output |

## `mesh golden-slice`
Golden Slice tooling

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `golden_slice_command` | `str` | No | - | Golden Slice subcommands |

## `mesh index`
Rebuild project index

## `mesh index-content`
Build and summarize content index

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--refresh` | `refresh` | `bool` | No | `False` | Force refresh |

## `mesh init-content-pack`
Initialize a new content pack

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `pack_id` | `str` | Yes | - | ID of the new pack |
| `--type` | `type` | `str` | No | `mod` | Pack type |
| `--wip` | `wip` | `bool` | No | `False` | Mark pack as Work In Progress |

## `mesh lint-presets`
Check that all scene encounter_preset_id values exist (no engine load)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Optional path to write JSON output |

## `mesh list-encounter-presets`
List available encounter preset ids (no engine load)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Optional path to write JSON output |

## `mesh list-overrides`
List overridden assets

## `mesh list-scenes`
List and analyze scene JSON files (no engine load)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Optional path to write JSON output |

## `mesh list-worlds`
List and analyze world JSON files (no engine load)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Optional path to write JSON output |

## `mesh lock-packs`
Generate content lockfile

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | No | - | Output path (default: content.lock.json) |
| `--update-audit-snapshot` | `update_audit_snapshot` | `bool` | No | `False` | Only update the audit snapshot in existing lockfile |

## `mesh migrate`
Migrate content to latest version

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `path` | `str` | Yes | - | Path to content |
| `--write` | `write` | `bool` | No | `False` | Write changes to file |

## `mesh new-behaviour`
Create a new behaviour script

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Behaviour name |

## `mesh new-npc`
Create a new NPC

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--role` | `role` | `str` | Yes | - | NPC role |
| `--into` | `into` | `str` | Yes | - | Target scene |
| `--x` | `x` | `int` | No | `0` | X coordinate |
| `--y` | `y` | `int` | No | `0` | Y coordinate |

## `mesh new-prefab`
Extract prefab from scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--prefab-id` | `prefab_id` | `str` | Yes | - | ID for new prefab |
| `--from-scene` | `from_scene` | `str` | Yes | - | Source scene |
| `--entity-name` | `entity_name` | `str` | Yes | - | Entity to extract |
| `--remove-source` | `remove_source` | `bool` | No | `False` | Remove original entity |

## `mesh new-quest`
Create a new quest

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Quest ID |
| `--target` | `target` | `str` | No | - | Target entity/item |

## `mesh new-scene`
Create a new scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Scene name |
| `--template` | `template` | `str` | No | `empty` | Scene template |
| `--encounter-layout` | `encounter_layout` | `str` | No | - | Encounter layout preset |

## `mesh packs`
List loaded packs

## `mesh pipeline`
Apply plan, validate, and optionally run demo/preset

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `plan_path` | `str` | No | - | Path to plan file |
| `` | `path` | `str` | No | - | Path to world or scene file to validate |
| `--plan` | `plan_path_opt` | `str` | No | - | Path to plan file |
| `--world` | `path_opt` | `str` | No | - | World/scene path to validate |
| `--ai-safe` | `ai_safe` | `bool` | No | `False` | Use AI-safe apply-plan path |
| `--dry-run` | `dry_run` | `bool` | No | `False` | Dry run apply-plan (no writes) |
| `--strict` | `strict` | `bool` | No | `False` | Pass --strict to validate-all |
| `--strict-compact` | `strict_compact` | `bool` | No | `False` | Pass --strict-compact to validate-all |
| `--check-reachability` | `check_reachability` | `bool` | No | `False` | Pass --check-reachability to validate-all |
| `--check-orphans` | `check_orphans` | `bool` | No | `False` | Pass --check-orphans to validate-all |
| `--check-refs` | `check_refs` | `bool` | No | `False` | Pass --check-refs to validate-all |
| `--demo` | `demo` | `bool` | No | `False` | Run demo after validation |
| `--preset` | `preset` | `str` | No | - | Run a preset after validation |

## `mesh place-npc`
Place an NPC in a scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--role` | `role` | `str` | Yes | - | NPC role |
| `--into` | `into` | `str` | Yes | - | Target scene |
| `--x` | `x` | `int` | No | `0` | X coordinate |
| `--y` | `y` | `int` | No | `0` | Y coordinate |

## `mesh place-prefab`
Place prefab in scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--prefab-id` | `prefab_id` | `str` | No | - | Prefab ID |
| `--into` | `into` | `str` | Yes | - | Target scene |
| `--x` | `x` | `int` | No | `0` | X coordinate |
| `--y` | `y` | `int` | No | `0` | Y coordinate |
| `--from-encounter-set` | `from_encounter_set` | `str` | No | - | Pick random prefab from encounter set |
| `--as-placeholder` | `as_placeholder` | `bool` | No | `False` | Use placeholder sprite |

## `mesh plan`
Manage content plans

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `plan_command` | `str` | Yes | - | None |

## `mesh play`
Launch the game

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--scene-path` | `scene_path` | `str` | No | - | Override start scene |

## `mesh polish`
Polish content

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `path` | `str` | Yes | - | Path to content |
| `--compact-scenes` | `compact_scenes` | `bool` | No | `False` | Compact scene files |
| `--export-graph` | `export_graph` | `bool` | No | `False` | Export world graph |
| `--update-lock-audit` | `update_lock_audit` | `bool` | No | `False` | Update lock audit |

## `mesh prefab`
Manage prefabs

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `prefab_args` | `str` | No | - | Arguments for prefab tool |

## `mesh preset`
Preset management

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `preset_command` | `str` | No | - | Preset commands |

## `mesh recipes`
Show workflow recipes

## `mesh release-check`
Run full release validation

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_path` | `str` | Yes | - | Path to world file |
| `--profile` | `profile` | `str` | No | - | Validation profile (sets default thresholds) |
| `--max-unused-assets` | `max_unused_assets` | `int` | No | - | Max allowed unused assets (default: 0) |
| `--max-unused-prefabs` | `max_unused_prefabs` | `int` | No | - | Max allowed unused prefabs (default: 0) |
| `--max-unused-items` | `max_unused_items` | `int` | No | - | Max allowed unused items (default: 0) |
| `--max-unused-quests` | `max_unused_quests` | `int` | No | - | Max allowed unused quests (default: 0) |
| `--ignore` | `ignore` | `str` | No | - | Comma-separated list of glob patterns to ignore in audit |
| `--allow-packs` | `allow_packs` | `str` | No | - | Comma-separated list of pack IDs to allow unused assets from |
| `--baseline` | `baseline` | `str` | No | - | Path to baseline lockfile for delta comparison |
| `--max-unused-delta` | `max_unused_delta` | `int` | No | - | Max allowed increase in unused assets vs baseline |
| `--diff-from` | `diff_from` | `str` | No | - | Path to old lockfile for changelog generation |
| `--emit-changelog` | `emit_changelog` | `str` | No | - | Path to write changelog markdown |
| `--require-golden_replays` | `require_golden_replays` | `bool` | No | `False` | Require golden traces to pass |

## `mesh replay-goldens`
Replay golden traces

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World file to use for fingerprint check |
| `--strict` | `strict` | `bool` | No | `False` | Check content fingerprint |

## `mesh replay-script`
Run a deterministic replay script

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `path` | `str` | Yes | - | Path to replay script JSON |
| `--out` | `out` | `str` | No | - | Optional path to write final state JSON |

## `mesh replay-suite`
Run all deterministic replay scripts in a folder and print a summary

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `folder` | `str` | Yes | - | Folder containing replay script JSON files |
| `--out` | `out` | `str` | No | - | Optional path to write summary JSON |

## `mesh run-preset`
Run a command preset

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Preset name |

## `mesh scene`
Scene utilities

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_command` | `str` | No | - | Scene subcommand |

## `mesh schema-fix-ids`
Deterministically add missing entity ids (and TriggerZone.zone_id) to scene JSON

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--dry-run` | `dry_run` | `bool` | No | `False` | Print what would change but do not write files |
| `--paths` | `paths` | `str` | No | - | Glob(s) or file path(s) to scenes. Default targets shipped scenes. |

## `mesh selftest`
Run engine self-tests

## `mesh tidy-scene`
Format and compact scene file

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_path` | `str` | Yes | - | Path to scene file |

## `mesh trace`
Record or replay traces

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--record` | `record` | `str` | No | - | Record to file |
| `--replay` | `replay` | `str` | No | - | Replay from file |
| `--world` | `world` | `str` | No | - | World file |
| `--overlay` | `overlay` | `bool` | No | `False` | Show overlay |
| `--assert-file` | `assert_file` | `str` | No | - | Assertions file |

## `mesh triage`
Run doctor, explain, and generate fix plan

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World to check |
| `--out` | `out` | `str` | Yes | - | Output plan path |
| `--write-artifacts` | `write_artifacts` | `bool` | No | `False` | Write doctor and explain artifacts to disk |

## `mesh undo-last-plan`
Undo last applied plan

## `mesh validate`
Validate a scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_path` | `str` | Yes | - | Path to scene file |

## `mesh validate-all`
Run all validators

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--path` | `path` | `str` | No | `.` | Root path |
| `--strict` | `strict` | `bool` | No | `False` | Enforce strict validation (no unknown fields) |
| `--schema-strict` | `schema_strict` | `bool` | No | `False` | Enforce strict schema rules |
| `--strict-compact` | `strict_compact` | `bool` | No | `False` | Enforce compact format |
| `--check-reachability` | `check_reachability` | `bool` | No | `False` | Check scene reachability |
| `--check-orphans` | `check_orphans` | `bool` | No | `False` | Check for orphan files |
| `--check-refs` | `check_refs` | `bool` | No | `False` | Check for missing asset references |

## `mesh validate-events`
Validate event definitions

## `mesh validate-packs`
Validate content packs

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--strict-overrides` | `strict_overrides` | `bool` | No | `False` | Fail on undeclared overrides |

## `mesh validate-refs`
Validate asset references

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_path` | `str` | Yes | - | Path to world file |
| `--strict-overrides` | `strict_overrides` | `bool` | No | `False` | Treat overrides as errors |

## `mesh validate-world`
Validate world structure

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_path` | `str` | Yes | - | Path to world file |
| `--no-events` | `no_events` | `bool` | No | `False` | Skip event validation |

## `mesh verify-all`
Run core verification gates in order and print a deterministic JSON summary

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out-dir` | `out_dir` | `str` | No | - | Optional directory to write scene/world indices |
| `--artifacts` | `artifacts` | `str` | No | - | Optional directory to write CI-friendly JSON artifacts |
| `--no-index` | `no_index` | `bool` | No | `False` | Disable writing indices even if --out-dir is provided |
| `` | `pytest_args` | `str` | No | - | Optional pytest args after `--` for verify-demo only (selection-changing args are blocked) |

## `mesh verify-demo`
Run curated demo verification tests

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `pytest_args` | `str` | No | - | Optional pytest args after `--` (selection-changing args are blocked) |

## `mesh verify-replays`
Run the deterministic replay suite and fail if any script fails

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--folder` | `folder` | `str` | No | - | Folder containing replay scripts (defaults to repo-root replays/) |
| `--out` | `out` | `str` | No | - | Optional path to write summary JSON |

## `mesh verify-strict`
Run validate-all in strict mode and fail on any errors

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World file to validate |

## `mesh where`
Locate an asset

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `asset_key` | `str` | Yes | - | Relative path to asset |

## `mesh wizard`
Interactive content wizard

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `subcommand` | `str` | Yes | - | Wizard command to run |
| `--name-prefix` | `name_prefix` | `str` | No | - | Prefix for generated IDs |
| `--name` | `name` | `str` | No | - | Name for the new content |
| `--perks` | `perks` | `str` | No | - | List of perk IDs to include (comma separated) |
| `--apply` | `apply` | `bool` | No | `False` | (Deprecated) Alias for --run pipeline |
| `--scene` | `scene` | `str` | No | - | Scene template or path |
| `--pack` | `pack` | `str` | No | - | Content pack ID |
| `--plan` | `plan` | `str` | No | - | Output plan path |
| `--dry-run` | `dry_run` | `bool` | No | `False` | Print plan without executing |
| `--into-world` | `into_world` | `str` | No | - | World file to wire into |
| `--world` | `world` | `str` | No | - | World file to validate/run pipeline against |
| `--link-from` | `link_from` | `str` | No | - | Scene ID to link from |
| `--profile` | `profile` | `str` | No | `safe` | Execution profile |
| `--npc-role` | `npc_role` | `str` | No | - | Role for new NPC |
| `--quest-type` | `quest_type` | `str` | No | - | Type of quest |
| `--vars` | `vars` | `str` | No | - | Variables for macro |
| `--run` | `run` | `str` | No | - | Run the pipeline (or a macro when used with 'macro') |
| `--list` | `list` | `bool` | No | `False` | List macros |
| `--with-boss` | `with_boss` | `bool` | No | `False` | Include boss |
| `--with-puzzle` | `with_puzzle` | `bool` | No | `False` | Include puzzle |
| `--template` | `template` | `str` | No | - | Region template (hub-interior-dungeon, ruins, deep-dungeon) |
| `--theme` | `theme` | `str` | No | - | Region theme ID |
| `--encounter-set` | `encounter_set` | `str` | No | - | Encounter Set ID |
| `--preset` | `preset` | `str` | No | - | Wizard preset ID |
| `--difficulty` | `difficulty` | `str` | No | `normal` | Encounter difficulty |

## `mesh world-graph`
Export world graph

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_path` | `str` | Yes | - | World file |
| `` | `output` | `str` | Yes | - | Output DOT file |
