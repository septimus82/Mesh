# Mesh CLI Commands

Reference documentation for all available CLI commands.

## `mesh add-puzzle`
Add a puzzle to a scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--scene-path` | `scene_path` | `str` | Yes | - | Scene path |
| `--prefix` | `prefix` | `str` | Yes | - | ID prefix |
| `--switch-x` | `switch_x` | `float` | Yes | - | Switch X |
| `--switch-y` | `switch_y` | `float` | Yes | - | Switch Y |
| `--door-x` | `door_x` | `float` | Yes | - | Door X |
| `--door-y` | `door_y` | `float` | Yes | - | Door Y |
| `--reward-x` | `reward_x` | `float` | Yes | - | Reward X |
| `--reward-y` | `reward_y` | `float` | Yes | - | Reward Y |
| `--item` | `item` | `str` | Yes | - | Reward item ID |
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

## `mesh artifacts-diff`
Compare two verify artifact bundles and summarise regressions

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--base` | `base` | `str` | Yes | - | Base (reference) artifacts directory |
| `--curr` | `curr` | `str` | Yes | - | Current artifacts directory to compare against base |
| `--format` | `format` | `str` | No | `text` | Output format (default: text) |
| `--out` | `out` | `str` | No | - | Optional output path to write formatted diff content |
| `--fail-on-regression` | `fail_on_regression` | `bool` | No | `False` | Exit 2 if any regression detected |
| `--update-baseline` | `update_baseline` | `bool` | No | `False` | Copy minimal baseline files from --curr into --base (overwrites) |

## `mesh artifacts-validate`
Validate verify-all artifact bundle index

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | `artifacts` | Artifact directory containing verify outputs (default: artifacts) |

## `mesh assets`
Asset utilities

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `assets_command` | `str` | No | - | Asset subcommand |

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

## `mesh baseline-update`
Refresh the committed CI baseline artifacts in one shot

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--baseline-dir` | `baseline_dir` | `str` | No | - | Target baseline directory (default: tooling/metrics/ci_baseline_artifacts) |
| `--artifacts` | `artifacts` | `str` | No | - | Use an existing artifacts dir instead of running verify-all |
| `--keep-temp` | `keep_temp` | `bool` | No | `False` | Keep the temp artifacts dir after update (for debugging) |
| `--no-verify-all` | `no_verify_all` | `bool` | No | `False` | Do not run verify-all; requires --artifacts |

## `mesh brush`
Brush discovery and validation

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `brush_command` | `str` | No | - | Brush subcommand |

## `mesh build-demo`
Build the demo content pack

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--diff-from` | `diff_from` | `str` | No | - | Path to old lockfile for changelog generation |
| `--strict-audit` | `strict_audit` | `bool` | No | `False` | Fail build if audit thresholds are exceeded |

## `mesh build-web`
Build web target via pygbag

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--entrypoint` | `entrypoint` | `str` | No | `web_main.py` | Web entry point script |
| `--out` | `out` | `str` | No | - | Optional output directory to copy web build artifacts into (e.g., artifacts/web_build) |
| `--extra-arg` | `extra_arg` | `str` | No | `[]` | Extra argument passed through to tooling.build_web (repeatable) |
| `--disable-sound-format-error, --no-disable-sound-format-error` | `disable_sound_format_error` | `str` | No | `True` | Pass pygbag --disable-sound-format-error (default: enabled) |

## `mesh bundle`
Verify or inspect release bundle ZIPs

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `bundle_command` | `str` | No | - | Bundle subcommand |

## `mesh campaign`
Campaign replay-check and determinism verification

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `campaign_command` | `str` | No | - | Campaign subcommand |

## `mesh capture`
Captured asset discovery and validation

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `capture_command` | `str` | No | - | Capture subcommand |

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

## `mesh content`
Create deterministic content scaffolds

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `content_command` | `str` | No | - | Content subcommand |

## `mesh content-contract`
Validate content contract for FX references

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--paths` | `paths` | `str` | No | - | File, directory, or glob to scan (repeatable). Defaults to packs/**/scenes, scenes, worlds. |
| `--repo-root` | `repo_root` | `str` | No | `.` | Repo root for resolving relative paths (default: cwd). |
| `--log` | `log` | `str` | No | - | Optional file path to write the contract output log. |
| `--with-prefabs` | `with_prefabs` | `bool` | No | `False` | Validate prefab references in entity data. |
| `--with-behaviours` | `with_behaviours` | `bool` | No | `False` | Validate behaviour names against the registry. |

## `mesh cutscene-simulate`
Run a deterministic cutscene simulation with a dt schedule

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--script` | `script` | `str` | Yes | - | Path to cutscene script JSON |
| `--dt` | `dt` | `str` | No | `0.0` | Comma-separated dt values (e.g., '0.0,0.5,0.5,1.0') or single value repeated |
| `--dt-repeat` | `dt_repeat` | `int` | No | `1` | Repeat single dt value this many times |
| `--flags` | `flags` | `str` | No | - | Initial flags as JSON object (e.g., '{"flag1": true}') |
| `--out` | `out` | `str` | No | - | Optional path to write result JSON |
| `--verbose` | `verbose` | `bool` | No | `False` | Print step-by-step output |

## `mesh cutscene-validate`
Validate cutscene script JSON file

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `path` | `str` | Yes | - | Path to cutscene script JSON |
| `--out` | `out` | `str` | No | - | Optional path to write validation result JSON |

## `mesh debug`
Debug bundle export and diagnostics

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `debug_command` | `str` | No | - | Debug subcommand |

## `mesh debug-report`
Print deterministic debug diagnostics from verify artifacts

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | `artifacts` | Artifact directory containing verify outputs (default: artifacts) |
| `--json-out` | `json_out` | `str` | No | - | Optional JSON output path |

## `mesh demo`
Demo helpers

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `demo_command` | `str` | No | - | Demo subcommand |
| `--scene` | `scene_override` | `str` | No | - | Override start scene path |

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
| `--out-dir` | `out_dir` | `str` | No | `docs` | Directory where markdown files should be written |
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
| `--json` | `json` | `bool` | No | `False` | Emit JSON payload |
| `--pack` | `pack` | `str` | No | - | Limit prefab checks to a pack id |

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

## `mesh edit`
Launch the in-game editor for a standalone project (skips project browser)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `project_path` | `str` | No | - | Project directory containing config.json (default: current directory) |
| `--scene` | `scene_path` | `str` | No | - | Optional scene path override |

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

## `mesh episode`
Deterministic episode replay checks

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `episode_command` | `str` | No | - | Episode subcommand |

## `mesh explain`
Explain doctor/validation failures

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World file to validate |
| `--last` | `last` | `bool` | No | `False` | Explain the most recent stored failure |
| `--json` | `json` | `bool` | No | `False` | Machine-readable output |

## `mesh export`
Build and manage shippable bundles

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `export_command` | `str` | No | - | Export subcommand |

## `mesh fx`
FX tooling

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `fx_command` | `str` | Yes | - | None |

## `mesh golden-slice`
Golden Slice tooling

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `golden_slice_command` | `str` | No | - | Golden Slice subcommands |

## `mesh health-report`
Aggregate deterministic repo health signals

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | `artifacts` | Artifact output directory (default: artifacts) |

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
List all scenes in the project

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

## `mesh macro`
Macro asset discovery and validation

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `macro_command` | `str` | No | - | Macro subcommand |

## `mesh mcp`
Configure an MCP client for this Mesh project

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `mcp_command` | `str` | No | - | MCP subcommand |

## `mesh migrate`
Migrate content to latest version

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `path` | `str` | Yes | - | Path to content |
| `--write` | `write` | `bool` | No | `False` | Write changes to file |

## `mesh new`
Create a playable Mesh project in a new folder.
Example: mesh new my_game

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Project name (also used as the folder name) |
| `--force` | `force` | `bool` | No | `False` | Overwrite the target directory if it already exists |
| `--dest` | `dest` | `str` | No | `.` | Parent directory to create the project in (default: current directory) |
| `--template` | `template` | `str` | No | `starter` | Template id from engine.project_templates (default: starter) |

## `mesh new-behaviour`
Create a new behaviour script

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Behaviour name |

## `mesh new-game`
Generates a fresh save file for a campaign start.  The output is deterministic: same arguments always produce byte-identical JSON.

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | Yes | - | Path to write the save JSON file. |
| `--campaign` | `campaign` | `str` | No | `mini_campaign_01` | Campaign identifier (default: mini_campaign_01). |
| `--scene` | `scene` | `str` | No | - | Override starting scene path. |
| `--seed` | `seed` | `int` | No | - | RNG seed (default: 42). |
| `--force` | `force` | `bool` | No | `False` | Allow overwriting an existing file. |
| `--json` | `print_json` | `bool` | No | `False` | Print the payload to stdout as well. |

## `mesh new-npc`
Create a new NPC

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `role` | `str` | Yes | - | NPC role/name |
| `--into` | `into` | `str` | Yes | - | Scene path |
| `--x` | `x` | `float` | No | `0.0` | X coordinate |
| `--y` | `y` | `float` | No | `0.0` | Y coordinate |

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
| `` | `name` | `str` | Yes | - | Quest name |
| `--target` | `target` | `str` | No | - | Target entity/location |

## `mesh new-scene`
Create a new scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Scene name |
| `--template` | `template` | `str` | No | `empty` | Scene template |
| `--encounter-layout` | `encounter_layout` | `str` | No | - | Encounter layout preset |

## `mesh new_project`
Scaffold a schema-valid blank project using engine.project_scaffold.
Example: python -m mesh_cli new_project my_game C:/Games

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Project name (also used as the window title) |
| `` | `dest` | `str` | No | `.` | Parent directory for the new project folder (default: current directory) |
| `--template` | `template` | `str` | No | `blank` | Template id from engine.project_templates (default: blank) |
| `--force` | `force` | `bool` | No | `False` | Remove an existing project directory before scaffolding |

## `mesh pack`
Pack manifest tooling

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `pack_command` | `str` | Yes | - | None |

## `mesh package-player`
Build a deterministic player-only runtime package (no editor modules)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--out` | `out` | `str` | Yes | - | Output package directory (e.g., artifacts/player_pkg) |
| `--smoke` | `smoke` | `bool` | No | `False` | Run runtime smoke against the packaged bundle |
| `--manifest` | `manifest` | `str` | No | - | Optional manifest path override (default: <out>/manifest.json) |
| `--diagnostics-artifact` | `diagnostics_artifact` | `str` | No | - | Optional diagnostics artifact path for packaged runtime smoke (requires --smoke) |

## `mesh packs`
List loaded packs

## `mesh perf-compare`
Compare deterministic perf scene-counter run against baseline JSON

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--run` | `run` | `str` | Yes | - | Perf run JSON from perf-run --scenes |
| `--baseline` | `baseline` | `str` | Yes | - | Perf baseline JSON |
| `--out` | `out` | `str` | Yes | - | Path to write compare JSON |

## `mesh perf-run`
Run a replay script and measure performance

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--replay` | `replay` | `str` | No | - | Path to replay JSON script |
| `--scenes` | `scenes` | `str` | No | - | Path to deterministic perf scene set JSON (scene-counter mode) |
| `--ticks` | `ticks` | `int` | No | `120` | Tick multiplier for deterministic scene-counter metrics (default: 120) |
| `--frames` | `frames` | `int` | No | `300` | Number of frames to measure |
| `--warmup` | `warmup` | `int` | No | `60` | Number of warmup frames to ignore |
| `--out` | `out` | `str` | No | - | Path to write JSON performance report |
| `--headless` | `headless` | `bool` | No | `False` | Run in headless mode (if supported) |
| `--perf-baseline` | `perf_baseline` | `str` | No | - | Optional baseline JSON for deterministic scene-counter comparison |
| `--compare-out` | `compare_out` | `str` | No | - | Optional path to write deterministic perf compare JSON report |
| `--fail-p95-frame-ms` | `fail_p95_frame_ms` | `float` | No | - | Fail if p95 frame time exceeds threshold (ms) |
| `--fail-p95-update-ms` | `fail_p95_update_ms` | `float` | No | - | Fail if p95 update time exceeds threshold (ms) |
| `--fail-p95-draw-ms` | `fail_p95_draw_ms` | `float` | No | - | Fail if p95 draw time exceeds threshold (ms) |
| `--fail-max-frame-ms` | `fail_max_frame_ms` | `float` | No | - | Fail if max frame time exceeds threshold (ms) |

## `mesh perf-stage-bench`
Run a headless synthetic frame-stage benchmark

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--sprites` | `sprites` | `int` | No | `500` | Synthetic sprite count |
| `--behaviours` | `behaviours` | `int` | No | `2` | Behaviours per sprite |
| `--events` | `events` | `int` | No | `3` | Synthetic event count |

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
Place an NPC into a scene

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `role` | `str` | Yes | - | NPC role/name |
| `--into` | `into` | `str` | Yes | - | Scene path |
| `--x` | `x` | `float` | No | `0.0` | X coordinate |
| `--y` | `y` | `float` | No | `0.0` | Y coordinate |

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
| `` | `scene_path` | `str` | No | - | Optional start scene |

## `mesh play-runtime`
Launch runtime-only scene bootstrap (no editor wiring)

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_path` | `str` | No | - | Optional start scene |
| `--headless-smoke` | `headless_smoke` | `bool` | No | `False` | Run deterministic runtime smoke mode and exit |
| `--smoke-scene` | `smoke_scene` | `str` | No | - | Optional scene path override for --headless-smoke |
| `--smoke-ticks` | `smoke_ticks` | `int` | No | `3` | Tick count for smoke mode |
| `--smoke-artifact` | `smoke_artifact` | `str` | No | - | Optional JSON artifact path for smoke mode |
| `--diagnostics-artifact` | `diagnostics_artifact` | `str` | No | - | Optional JSON artifact path for deterministic diagnostics snapshot on exit |
| `--print-diagnostics-on-exit` | `print_diagnostics_on_exit` | `bool` | No | `False` | Print a deterministic diagnostics summary at shutdown |

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

## `mesh release`
Deterministic release checks and artifacts

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `release_command` | `str` | No | - | Release subcommand |

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

## `mesh release-contract`
Run deterministic release contract checks

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | - | Optional artifacts directory for logs/outputs |
| `--repo-root` | `repo_root` | `str` | No | - | Repo root for pack/content discovery (default: cwd) |
| `--report` | `report` | `str` | No | - | Optional JSON report path |
| `--with-asset-audit` | `with_asset_audit` | `_parse_bool` | No | `True` | Enable asset audit step |
| `--asset-audit-orphans` | `asset_audit_orphans` | `bool` | No | `False` | Enable orphan detection |
| `--asset-audit-duplicates` | `asset_audit_duplicates` | `_parse_bool` | No | `True` | Enable duplicate detection |
| `--asset-audit-warn-duplicates` | `asset_audit_warn_duplicates` | `_parse_bool` | No | `True` | Treat duplicates as warnings |
| `--asset-audit-strict` | `asset_audit_strict` | `bool` | No | `False` | Treat asset audit warnings as errors |
| `--strict` | `strict` | `bool` | No | `False` | Enable strict release gates |

## `mesh release-notes`
Generate deterministic release notes from verify artifacts

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | `artifacts` | Artifact directory containing verify outputs (default: artifacts) |
| `--out` | `out` | `str` | No | - | Optional markdown output path |
| `--title` | `title` | `str` | No | - | Optional title override |
| `--max-sites` | `max_sites` | `int` | No | `5` | Maximum swallowed exception sites to show |
| `--max-steps` | `max_steps` | `int` | No | `5` | Maximum slow steps to show |

## `mesh release-preflight`
Run local release-critical preflight checks

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--tag` | `tag` | `str` | No | - | Optional release tag candidate (example: v0.4.1) |
| `--keep-temp` | `keep_temp` | `bool` | No | `False` | Keep auto-created artifacts directory |
| `--artifacts` | `artifacts` | `str` | No | - | Optional artifacts directory override |
| `--no-verify-all` | `no_verify_all` | `bool` | No | `False` | Skip verify-all/artifacts-validate subprocess checks |

## `mesh replay-goldens`
Replay golden traces

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World file to use for fingerprint check |
| `--strict` | `strict` | `bool` | No | `False` | Check content fingerprint |

## `mesh replay-hash`
Run a deterministic replay script and write a hash report

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--replay` | `replay` | `str` | Yes | - | Path to replay script JSON |
| `--frames` | `frames` | `int` | No | `300` | Frame count metadata for the report |
| `--warmup` | `warmup` | `int` | No | `0` | Warmup frame metadata for the report |
| `--float-round` | `float_round` | `int` | No | `6` | Round floats to N decimals |
| `--out` | `out` | `str` | Yes | - | Path to write hash JSON |
| `--expect` | `expect` | `str` | No | - | Expected hash JSON or text file |

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

## `mesh replays`
Run deterministic replay suite with golden ratchet

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `replays_command` | `str` | No | - | Replays subcommand |

## `mesh room`
Room scaffolding utilities

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `room_command` | `str` | No | - | Room subcommand |

## `mesh run-preset`
Run a command preset

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `name` | `str` | Yes | - | Preset name |

## `mesh scene`
Scene authoring commands

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_command` | `str` | Yes | - | None |

## `mesh schema-fix-ids`
Deterministically add missing entity ids (and TriggerZone.zone_id) to scene JSON

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--dry-run` | `dry_run` | `bool` | No | `False` | Print what would change but do not write files |
| `--paths` | `paths` | `str` | No | - | Glob(s) or file path(s) to scenes. Default targets shipped scenes. |

## `mesh selftest`
Run engine self-tests

## `mesh ship-check`
Run shipping readiness checks and print a deterministic artifact summary

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | `artifacts` | Artifacts directory used by verify/package/web gates (default: artifacts) |
| `--skip-package` | `skip_package` | `bool` | No | `False` | Skip package-player --smoke step |
| `--skip-web` | `skip_web` | `bool` | No | `False` | Skip web-smoke step and web artifact requirement |
| `--skip-perf` | `skip_perf` | `bool` | No | `False` | Skip perf artifact requirement checks |
| `--skip-verify` | `skip_verify` | `bool` | No | `False` | Skip verify-all --ci-bundle step |
| `--continue-on-web-fail` | `continue_on_web_fail` | `bool` | No | `False` | Continue to summary even when web-smoke fails (still exits non-zero) |
| `--quiet` | `quiet` | `bool` | No | `False` | Print only the final summary block |

## `mesh sprite`
Sprite authoring utilities

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `sprite_command` | `str` | No | - | Sprite subcommand |

## `mesh stamp`
Stamp discovery and validation

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `stamp_command` | `str` | No | - | Stamp subcommand |

## `mesh tidy-scene`
Format and compact scene file

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `scene_path` | `str` | Yes | - | Path to scene file |

## `mesh tilemap`
Tilemap utilities

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `tilemap_command` | `str` | No | - | Tilemap subcommand |

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

## `mesh trends-report`
Render weekly trends latest/delta panel

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--trend-file` | `trend_file` | `str` | No | `tooling/metrics/weekly_trends.json` | Trend input file (default: tooling/metrics/weekly_trends.json) |
| `--last` | `last` | `int` | No | `8` | History length for the table |
| `--out` | `out` | `str` | No | - | Optional output file path |
| `--format` | `format` | `str` | No | `markdown` | None |

## `mesh trends-update`
Append weekly health trend metrics from artifacts

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | Yes | - | Artifacts directory |
| `--trend-file` | `trend_file` | `str` | No | `tooling/metrics/weekly_trends.json` | Trend output file (default: tooling/metrics/weekly_trends.json) |

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
| `--report` | `report` | `bool` | No | `False` | Print a human-friendly diagnostics report after the JSON summary |
| `--report-json` | `report_json` | `bool` | No | `False` | Print a machine-readable JSON diagnostics report after the JSON summary |
| `--report-json-artifact` | `report_json_artifact` | `bool` | No | `False` | Write a verify_report.json artifact to the artifacts directory |
| `--artifact-index` | `artifact_index` | `bool` | No | `False` | Write an index.json artifact manifest to the artifacts directory |
| `--ci-bundle` | `ci_bundle` | `bool` | No | `False` | Convenience flag: implies --report-json-artifact and --artifact-index |
| `--release-notes-artifact` | `release_notes_artifact` | `bool` | No | `False` | Write release_notes.json and release_notes.md to the artifacts directory |
| `--skip-web-smoke` | `skip_web_smoke` | `bool` | No | `False` | Skip the web build + web smoke shipping gate |
| `` | `pytest_args` | `str` | No | - | Optional pytest args after `--` for verify-demo only (selection-changing args are blocked) |

## `mesh verify-demo`
Run curated demo verification tests

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | - | Optional artifact directory for verify-demo scratch and failure diagnostics |
| `--ci-bundle` | `ci_bundle` | `bool` | No | `False` | Compatibility flag accepted for verify-all parity; verify-demo ignores it |
| `` | `pytest_args` | `str` | No | - | Optional pytest args after `--` (selection-changing args are blocked) |

## `mesh verify-local`
Run a fast local verification subset with deterministic JSON output

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | - | Optional directory to write local verify artifacts |

## `mesh verify-replays`
Run the deterministic replay suite and fail if any script fails

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--folder` | `folder` | `str` | No | - | Folder containing replay scripts (defaults to repo-root replays/) |
| `--out` | `out` | `str` | No | - | Optional path to write summary JSON |

## `mesh verify-report`
Print a concise diagnostics report from verify artifacts

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--artifacts` | `artifacts` | `str` | No | `artifacts` | Artifact directory containing verify outputs (default: artifacts) |

## `mesh verify-strict`
Run validate-all in strict mode and fail on any errors

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--world` | `world` | `str` | No | - | World file to validate |

## `mesh version`
Print Mesh Engine version, Python, platform, and git info

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--json` | `version_json` | `bool` | No | `False` | Output provenance as JSON |
| `` | `version_command` | `str` | No | - | Version subcommand |

## `mesh version-bump`
Bump package/public API versions with guardrails

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--to` | `to` | `str` | Yes | - | Target package version (X.Y.Z) |
| `--public-api` | `public_api` | `str` | No | - | Optional PUBLIC_API_SEMVER target (X.Y.Z) |
| `--dry-run` | `dry_run` | `bool` | No | `False` | Show unified diffs without writing files |

## `mesh web-smoke`
Validate built web output structure and emit deterministic smoke artifact

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `--build-dir` | `build_dir` | `str` | No | - | Optional web build directory override (defaults to pygbag.toml output or build/web) |
| `--artifact` | `artifact` | `str` | No | - | Optional JSON artifact path (e.g., artifacts/web_smoke.json) |

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

## `mesh world`
World authoring utilities

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_command` | `str` | No | - | World subcommand |

## `mesh world-graph`
Export world graph

### Arguments
| Flag | Name | Type | Required | Default | Help |
|---|---|---|---|---|---|
| `` | `world_path` | `str` | Yes | - | World file |
| `` | `output` | `str` | Yes | - | Output DOT file |
