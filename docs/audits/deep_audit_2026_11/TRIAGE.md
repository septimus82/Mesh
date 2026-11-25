# Deep audit triage (2026-11-25)

This covers an external auditor's review of `redesign/visual-editor` at `1b85698f`. The auditor claimed 13 reproduced critical gameplay and editor defects. **The report and scripts were not available**, so this is an independent hunt over the owner's named risk areas, not a one-to-one mapping of the 13 claims.

Verified at `a4465258`. Since `1b85698f`, the only `engine/` change is the FloorRoute extraction (`engine/hd2d/route.py`), which was reviewed as behaviour-identical. All other changes were in mesh_net, tooling, tests and docs.

Each script in `repro/` exits 1 and prints the defect at `a4465258`. Run it with `PYTHONPATH=<checkout> py -3.13 repro/<script>.py`. Scripts work in fresh temp projects and delete them.

## Confirmed (reproduced by the verifier and the coordinator)

| Issue | Finding | Reachability | Impact | Sev | Repro |
|---|---|---|---|---|---|
| #618 | Legacy rename/move uses `os.replace` onto an existing file | Legacy editor only (#347) | Irreversible file loss, references repointed | P2 by reach; treat as P1 | `repro_legacy_rename_overwrite.py` |
| #619 | Shop charges gold and stock when `add_item` fails | Shop panel → Vendor; shipped scenes; Studio | Gold lost, no item | P1 | `repro_shop_charges_without_item.py` |
| #620 | "Only once" / "Choice once" dialogue reward repeats after re-entry or load | Studio-authored dialogue | Double reward | P1 | `repro_dialogue_once_reward_repeats.py` |
| #621 | One event completes two consecutive same-trigger quest stages | Live QuestManager | Stage skipped, early reward | P1 | `repro_quest_one_event_two_stages.py` |
| #622 | ActionListRunner never gets events; cutscene `find_sprite` missing; `.behaviours` vs `mesh_behaviours_runtime` | 11 repo scenes; CutsceneTrigger; Studio | Actions inert; cutscene step crashes the frame | P1 | `repro_dead_actions_cutscenes.py` |
| #623 | Saves follow the current folder, not the project | Legacy project switch; `run_game(project_root=)`. Studio not affected | Cross-project slot overwrite | P2 | `repro_saves_follow_cwd.py` |
| #624 | Ruff gate passes with ruff missing; mypy baseline guard a no-op in CI; baselines can grow unchecked | Local verify-all, CI ratchets | Gates pass without checking | P1 (safeguard) | `python -m tooling.ruff_gate` in a venv without ruff exits 0 |

## Read only, not yet reproduced
- **MCP cutscene ops (P1 candidate).** `ai_ops.add_or_update_cutscene` writes unvalidated steps. The game loads `cutscenes.json` with a strict schema and catches only FileNotFoundError (`game.py:592-595`), so the project may fail to start.
- **Quest `emit_events_on_complete`.** Used 16 times in shipped `quests.json`, but ignored by the live QuestManager. `reward.gold` and `reward.xp` are dropped by `normalize_reward`. Silent no-op (P2).
- **Spurious warnings on load.** Every slot load warns "quest manager cannot register" for each quest; state restores correctly (P2).
- **Duplicate toast.** Quickload with no save shows two toasts (P2).

## Checked, nothing found
- **SaveManager:** sanitised slot names; pre-v3 slots get a verified `.v2.bak` before overwrite; newer-version saves refused; atomic writes. Party, box, monsters, eggs, inventory and quest stage state round-trip.
- **Exported games:** per-player settings, with an unreadable file set aside.
- **Studio:** new-room and map files are publish-only-if-absent; saves stay inside the ownership lock; room keys are slugged.
- **Imports:** slugged names, existing files never replaced.
- **MCP direct writes:** ownership-gated.
- **Export (F4):** token-proven deletes (spot-read only).
- **`project_save` (F3):** recovers from errors it sees. By its own documentation it is not crash or power-loss safe (no fsync, files replaced one at a time).

## Test doubles vs the real runtime (missing contracts)
- **ActionListRunner events:** `on_event` / `subscribed_event_types` missing (#622).
- **Cutscene lookup:** `SceneController.find_sprite` is faked in `test_cutscene.py:35` (#622).
- **Behaviour list:** `entity.behaviours` is set by hand in tests; real sprites use `mesh_behaviours_runtime` (#622).
- **Quest manager:** `game_state_controller.quests` is the lightweight `engine.quest_manager.QuestManager` in 34 test files. The game uses `engine.quests.QuestManager` (`game.py:533`).
- **GameWindow attributes** (read, not run): the real GameWindow never sets these.
  - `gameplay_event_bus`, `quest_runner`, `cutscene_runner`, `digest_tracker`
  - `player`
  - `editor` and `editor_mode_controller` (the real attribute is `editor_controller`)
- **Any-attribute doubles:** 98 `MagicMock()` windows and 188 `SimpleNamespace` windows. `engine/self_test.py` `_DummyWindow` returns None for any attribute.

## CI lanes and safeguards
- **Fan-in:** correct (skipped, cancelled or missing jobs fail).
- **Coverage gaps:**
  - No minimum selected-test count on the default lanes.
  - Full GL, slow and e2e tests run post-merge only (Extended).
  - The MCP-present test always skips in CI.
  - pyright is configured but never run.
- **Steps that pass when their input is missing:** perf baselines, smoke scene, golden replays (release-check), mypy island modules.

## Not checked
- No real GameWindow, Studio or exported-game run. Findings were driven through real classes and real delivery/tick functions.
- Whether Studio routes MCP cutscene ops another way.
- Monster box capacity and release edge cases.
- Duplicate hotkey bindings across the two input systems.
- The original 13 claims one-to-one.
