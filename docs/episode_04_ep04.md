# Episode 04: Sentry at the Causeway

Episode 04 is a combat-focused vertical slice built on existing systems only:
- `CutsceneRunner`
- `DialogueRunner`
- `ActionListRunner` (flag/event gating)
- `Interactable`
- `TriggerVolume`
- Combat behaviours on sentries: `Health`, `Shooter`, `RangedEnemyAI`, `PatrolPath`

## Entity Table

| Entity ID | Prefab | Purpose |
|---|---|---|
| `episode_04_ep04_player` | `player` | Player start |
| `episode_04_ep04_entry_trigger` | `ep04_trigger` | Emits `ep04_entered` |
| `episode_04_ep04_mentor` | `ep04_mentor` | Intro dialogue actor |
| `episode_04_ep04_sentry_easy` | `ep04_sentry` | Safe-route single sentry |
| `episode_04_ep04_sentry_hard_a` | `ep04_sentry_hard` | Hard-route sentry A |
| `episode_04_ep04_sentry_hard_b` | `ep04_sentry_hard` | Hard-route sentry B |
| `episode_04_ep04_reward_cache` | `ep04_reward` | Reward chest (gated by `ep04.exit_unlocked`) |
| `episode_04_ep04_exit_door` | `ep04_door` | Exit door (also gated) |
| `episode_04_ep04_*_ctrl` | `ep04_controller` | Event/flag orchestration |

## Event Flow

1. Entry trigger emits `ep04_entered`.
2. Intro controller sets `ep04.entered` and emits `ep04_intro_start`.
3. Intro cutscene emits `ep04_intro_done`, then starts `ep04_dialogue_intro`.
4. Dialogue branch sets either:
   - `ep04.easy_mode` via “Take the safe route.”
   - `ep04.hard_mode` via “Challenge yourself.”
5. Choice controllers emit `ep04_choice_made`; combat start controllers emit `ep04_combat_started`.
6. Sentry deaths (from `died` events) set per-route flags.
7. Route completion emits `ep04_all_enemies_dead`, sets `ep04.exit_unlocked`, and emits `ep04_exit_unlocked`.
8. Reward chest interaction emits `ep04_reward_collected`, which emits `ep04_outro_start`.
9. Outro cutscene emits `ep04_complete`.
10. Quest stage 3 emits `quest_ep04_complete`.

## Flags

- Branch and combat:
  - `ep04.easy_mode`
  - `ep04.hard_mode`
  - `ep04.combat_started`
- Enemy completion:
  - `ep04.easy_sentry_dead`
  - `ep04.hard_sentry_a_dead`
  - `ep04.hard_sentry_b_dead`
  - `ep04.all_enemies_dead`
- Progression:
  - `ep04.exit_unlocked`
  - `ep04.reward_collected`
  - `ep04.complete`

## Quest Stages

Quest ID: `episode_04_ep04`

1. `step0`: complete on `ep04_intro_done`
2. `step1`: complete on `ep04_all_enemies_dead`
3. `step2`: complete on `ep04_complete` and emit `quest_ep04_complete`

## Test Scenarios

`tests/test_episode_04_ep04_integration.py` covers:
- Safe route happy path (1 sentry)
- Hard route happy path (2 sentries)
- Save/restore mid-cutscene
- Save/restore mid-dialogue and mid-combat with exact HP restoration
- Save/restore after kills before reward collection
- Determinism (event sequence + digest sequence)
