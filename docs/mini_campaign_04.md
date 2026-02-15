# Mini Campaign 04 (Episodes 01-05)

Mini Campaign 04 chains `episode_01` -> `episode_02` -> `episode_03` -> `episode_04` -> `episode_05` with two deterministic replay variants.

## Payoff Matrix

- Bonus variant (`campaign04_bonus`):
  - Episode 01 choose `"I can help."` -> sets `campaign04.helped_mentor`
  - Episode 05 complete side objective (`ep05.side_done`)
  - Reward outcome emits `ep05_reward_bonus_collected`
- Standard variant (`campaign04_standard`):
  - Episode 01 choose `"I work alone."`
  - Episode 05 skips side objective
  - Reward outcome emits `ep05_reward_collected`

Both variants complete the same campaign quest and end with `campaign04_complete`.

## Campaign Quest

Quest id: `mini_campaign_04`

Stages:
1. `episode_01` completes on `quest_episode_01_complete`
2. `episode_02` completes on `quest_ep02_complete`
3. `episode_03` completes on `quest_ep03_complete`
4. `episode_04` completes on `quest_ep04_complete`
5. `episode_05` completes on `quest_ep05_complete` and emits `campaign04_complete`

## Scene Wiring

- Episode 01:
  - `episode_01_campaign04_help_payoff_ctrl`
  - campaign start event is emitted by replay/entry flow (`campaign04_started`)
- Episode 02:
  - `episode_02_campaign04_done_ctrl`
- Episode 03:
  - `episode_03_campaign04_done_ctrl`
- Episode 04:
  - `episode_04_campaign04_done_ctrl`
  - portal `episode_04_exit_to_ep05`
- Episode 05:
  - `episode_05_campaign04_bonus_reward_ctrl`
  - `episode_05_campaign04_done_ctrl`

All campaign04 controllers require `campaign04.active` so they do not alter standalone episode behavior or prior campaigns.

## Replay Fixtures

- `replays/campaign04_bonus.json`
- `replays/campaign04_standard.json`

Suite entries:
- `campaign04_bonus`
- `campaign04_standard`

Both are registered in `replays/suite.json` with campaign mode and Linux-enforced budget thresholds (via `--budgets-only-on linux`).

## Tests

`tests/test_mini_campaign_04_integration.py` covers:
- Bonus path reward event contract
- Standard path reward event contract
- Save/restore boundary + Episode 04 -> Episode 05 transition
- Determinism across repeated full runs
- Registry and scene wiring checks
