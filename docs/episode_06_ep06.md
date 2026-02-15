# Episode 06: Conduit of Ash

Episode 06 is a hybrid combat + puzzle slice built with existing systems only:
- `CutsceneRunner`
- `DialogueRunner`
- `ActionListRunner`
- `TriggerVolume`
- `Interactable`
- `Health` + `Shooter` + `RangedEnemyAI` + `PatrolPath`

## Branches

- Fight path:
  - Dialogue choice: `"Fight through."`
  - Defeat `Episode06FightSentry`
  - Solve rune order (`Rune A` -> `Rune B`)
  - Standard reward: `ep06_reward_collected`

- Puzzle path:
  - Dialogue choice: `"Solve first."`
  - Defeat `Episode06PuzzleSentry`
  - Solve rune order (`Rune A` -> `Rune B`)
  - Bonus reward: `ep06_reward_bonus_collected`

Both routes require combat clear + puzzle solved before extraction unlocks.

## Entity Table

- `episode_06_ep06_player`: player start.
- `episode_06_ep06_entry_trigger` (`ep06_trigger`): emits `ep06_entered`.
- `episode_06_ep06_mentor` (`ep06_mentor`): intro dialogue actor.
- `episode_06_ep06_fight_sentry` (`ep06_fight_sentry`): fight-path combat target.
- `episode_06_ep06_puzzle_sentry` (`ep06_puzzle_sentry`): puzzle-path combat target.
- `episode_06_ep06_rune_a` / `episode_06_ep06_rune_b`: ordered puzzle interaction.
- `episode_06_ep06_reward_cache` / `episode_06_ep06_reward_bonus_cache`: route-gated rewards.
- `episode_06_ep06_exit_door`: final extraction door.
- `episode_06_ep06_*_ctrl`: event and flag orchestration.

## Event Flow

1. Entry trigger emits `ep06_entered`.
2. Intro controller sets `ep06.entered` and emits `ep06_intro_start`.
3. Intro cutscene emits `ep06_intro_done` and starts `ep06_dialogue_intro`.
4. Dialogue branch sets `ep06.fight_path` or `ep06.puzzle_path`, emits `ep06_choice_made` and `ep06_combat_started`.
5. Route sentry death emits `ep06_combat_cleared` and sets `ep06.combat_cleared`.
6. Rune sequence:
   - `Rune A` sets `ep06.seq1`
   - `Rune B` with `ep06.seq1` emits `ep06_puzzle_solved`
   - Wrong-order `Rune B` emits `ep06_wrong_order` and `ep06_reset_start`; reset cutscene emits `ep06_reset_done`.
7. Unlock controller requires `ep06.combat_cleared` + `ep06_puzzle_solved` and emits `ep06_exit_unlocked`.
8. Reward branch sets `ep06.reward_collected` (and `ep06.reward_bonus_collected` on puzzle path).
9. Exit interaction emits `ep06_exit_door_interact`; outro controller emits `ep06_outro_start`.
10. Outro cutscene emits `ep06_complete`.
11. Quest emits `quest_ep06_complete`.

## Quest

Quest ID: `episode_06_ep06`

- `step0`: complete on `ep06_intro_done`
- `step1`: complete on `ep06_exit_unlocked`
- `step2`: complete on `ep06_complete`, emits `quest_ep06_complete`

## Test Scenarios

`tests/test_episode_06_ep06_integration.py` covers:
- fight path completion
- puzzle path completion
- save/restore mid-cutscene
- save/restore mid-combat
- save/restore while reset window is active
- determinism of event + digest artifacts
