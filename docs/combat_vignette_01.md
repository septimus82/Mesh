# Combat Vignette 01

A vertical slice that stress-tests ranged combat, HealthBehaviour save/restore,
reward collection, and quest progression — all driven by content wiring.

## Entities

| Entity | Prefab | Behaviours | Purpose |
|--------|--------|------------|---------|
| Player | `player` | Health(20 HP) | Player avatar |
| ArenaEntryTrigger | `cv_entry_trigger` | TriggerVolume | Emits `cv_entered` on player enter |
| SentryArcher | `sentry_archer` | Health(10 HP), RangedEnemyAI, Shooter, PatrolPath | Ranged enemy |
| RewardChest | `chest_reward_cv` | Interactable | Gated by `cv.reward_unlocked` |
| CombatVignetteInit | `cv_controller` | ActionListRunner | Room init logic |
| CombatVignetteOnEnemyDead | `cv_controller` | ActionListRunner | Death → reward unlock |
| CombatVignetteOnReward | `cv_controller` | ActionListRunner | Reward → completion |

## Event Flow

| Trigger | Event | Effect |
|---------|-------|--------|
| Player enters arena | `cv_entered` | Sets `cv.started`, emits `cv_combat_started` |
| Enemy health ≤ 0 | `cv_enemy_dead` | Sets `cv.enemy_dead`, `cv.reward_unlocked`, emits `cv_reward_unlocked` |
| Chest interaction | `reward_collected` | Sets `cv.completed`, emits `cv_complete` |

## Flags

| Flag | Meaning |
|------|---------|
| `cv.started` | Arena entered, combat begun |
| `cv.enemy_dead` | Sentry archer destroyed |
| `cv.reward_unlocked` | Reward chest interactable |
| `cv.completed` | Vignette finished |

## ActionListRunner Controllers

| Controller | Listens | Actions |
|------------|---------|---------|
| `cv_init` | `cv_entered` | `set_flag cv.started`, `emit_event cv_combat_started` |
| `cv_on_enemy_dead` | `cv_enemy_dead` | `set_flag cv.enemy_dead`, `set_flag cv.reward_unlocked`, `emit_event cv_reward_unlocked` |
| `cv_on_reward` | `reward_collected` | `set_flag cv.completed`, `emit_event cv_complete` |

## Sentry Archer Configuration

| Component | Config |
|-----------|--------|
| Health | `max_hp: 10` |
| RangedEnemyAI | `detect_radius: 300, attack_radius: 250, flee_radius: 80, speed: 80` |
| Shooter | `projectile_speed: 250, damage: 2, cooldown: 2s, range: 350` |
| PatrolPath | Two waypoints, pingpong mode, speed 50 |

## Quest

Quest `combat_vignette_01` has three stages:

| Stage | Complete On | Emits |
|-------|-------------|-------|
| `step0` | `cv_entered` | — |
| `step1` | `cv_enemy_dead` | — |
| `step2` | `reward_collected` | `quest_combat_vignette_complete` |

## Save / Restore

All components support save/restore:
- **HealthBehaviour** → `{hp, max_hp, invulnerable, dead}`
- **GameState flags** → all `cv.*` flags
- **GameplayEventBus** → pending events
- **ActionListRunner** → per-controller state

Mid-combat saves preserve enemy HP exactly.
Post-kill saves preserve chest unlock state for collection after restore.
