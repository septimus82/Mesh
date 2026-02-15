# Mini Campaign 03 (Episodes 01-04)

Mini Campaign 03 chains `episode_01` -> `episode_02` -> `episode_03` -> `episode_04` and adds one deterministic cross-episode payoff.

## Payoff

Source choice:
- Episode 01 help branch (`"I can help."`) sets `campaign03.helped_mentor`.

Episode 04 outcome:
- If `campaign03.helped_mentor` is true: bonus cache path emits `ep04_reward_bonus_collected`.
- Otherwise: standard cache path emits `ep04_reward_collected`.

Both paths continue through the same outro and complete `quest_ep04_complete`.

## Campaign Quest

Quest id: `mini_campaign_03`

Stages:
1. `episode_01` completes on `quest_episode_01_complete`
2. `episode_02` completes on `quest_ep02_complete`
3. `episode_03` completes on `quest_ep03_complete`
4. `episode_04` completes on `quest_ep04_complete` and emits `campaign03_complete`

## Scene Wiring

- Episode 01:
  - `episode_01_campaign03_start_ctrl`
  - `episode_01_campaign03_help_payoff_ctrl`
  - `episode_01_campaign03_solo_payoff_ctrl`
  - `episode_01_campaign03_done_ctrl`
- Episode 02:
  - `episode_02_campaign03_done_ctrl`
- Episode 03:
  - `episode_03_campaign03_done_ctrl`
  - portal `episode_03_exit_to_ep04`
- Episode 04:
  - `episode_04_campaign03_done_ctrl`
  - bonus reward entity `episode_04_ep04_reward_bonus_cache`
  - bonus reward controller `episode_04_ep04_reward_bonus_ctrl`

All campaign03 controllers require `campaign03.active` for deterministic activation and to avoid affecting other campaign flows.

## Replay Cases

- `replays/campaign03_help.json`
- `replays/campaign03_silent.json`

Both are registered in `replays/suite.json` with campaign mode and Linux-enforced budget thresholds (via `--budgets-only-on linux`).

## Tests

`tests/test_mini_campaign_03_integration.py` covers:
- Help path -> bonus reward event
- Silent path -> standard reward event
- Save/restore boundaries across episode transitions
- Determinism across repeated full runs
- Registry and scene wiring checks
