# Mini Campaign 05 (Episodes 01-06)

Mini Campaign 05 extends the deterministic chain through Episode 06:

`episode_01` -> `episode_02` -> `episode_03` -> `episode_04` -> `episode_05` -> `episode_06`

## Campaign Quest

Quest id: `mini_campaign_05`

Stages:
1. `episode_01` complete on `quest_episode_01_complete`
2. `episode_02` complete on `quest_ep02_complete`
3. `episode_03` complete on `quest_ep03_complete`
4. `episode_04` complete on `quest_ep04_complete`
5. `episode_05` complete on `quest_ep05_complete`
6. `episode_06` complete on `quest_ep06_complete`, emits `campaign05_complete`

## Route Variants

- `campaign05_standard`:
  - Episode 06 takes `"Fight through."`
  - Emits `ep06_reward_collected`

- `campaign05_variant`:
  - Episode 06 takes `"Solve first."`
  - Emits `ep06_reward_bonus_collected`

Both variants complete the same campaign quest and produce deterministic replay traces.

## Scene Wiring

- Episode 03: `episode_03_campaign05_done_ctrl` emits `go_to_episode_04_ep04`
- Episode 04: `episode_04_campaign05_done_ctrl` emits `go_to_episode_05_ep05`
- Episode 05:
  - `episode_05_campaign05_done_ctrl` emits `go_to_episode_06_ep06`
  - `episode_05_exit_to_ep06` listens for `go_to_episode_06_ep06` and loads `scenes/episode_06_ep06.json`
- Episode 06:
  - `episode_06_campaign05_done_ctrl` sets `campaign05.ep06_complete`

## Replay Fixtures

- `replays/campaign05_standard.json`
- `replays/campaign05_variant.json`

Suite entries:
- `campaign05_standard`
- `campaign05_variant`

Both are registered in `replays/suite.json` with campaign mode and Linux-enforced budgets (via `--budgets-only-on linux`).
