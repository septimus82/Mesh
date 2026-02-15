# Mini Campaign 02

Mini Campaign 02 chains the three episode vertical slices in order:

1. `scenes/episode_01_intro.json`
2. `scenes/episode_02_ep02.json`
3. `scenes/episode_03_ep03.json`

## Quest Chain

Quest id: `mini_campaign_02`

Stages:

1. `episode_01` completes on `quest_episode_01_complete`
2. `episode_02` completes on `quest_ep02_complete`
3. `episode_03` completes on `quest_ep03_complete` and emits `campaign02_complete`

## Campaign Events

- `campaign02_started`
- `go_to_episode_02_ep02`
- `go_to_episode_03_ep03`
- `campaign02_complete`

## Scene Wiring

- Episode 01 adds `episode_01_campaign02_start_ctrl`, `episode_01_campaign02_done_ctrl`, and portal `episode_01_exit_to_ep02`.
- Episode 02 adds `episode_02_campaign02_done_ctrl` and portal `episode_02_exit_to_ep03`.
- Episode 03 adds `episode_03_campaign02_done_ctrl`.

The scene controllers set campaign flags (`campaign02.*`) and clear transient per-episode progression flags before transition.
Episode transition events are emitted by campaign controllers in-scene:

- Episode 01 controller emits `go_to_episode_02_ep02`
- Episode 02 controller emits `go_to_episode_03_ep03`

## Campaign Replay

Script: `replays/campaign02.json`

The replay executes a deterministic full chain:

- Episode 01 dialogue choice (`I can help.`)
- Episode 02 stabilize path
- Episode 03 sigil solve path
- Boundary save/restore actions after Episode 01 and Episode 02

Replay suite case id: `campaign02` in `replays/suite.json`.

## Integration Tests

`tests/test_mini_campaign_02_integration.py` validates:

- full end-to-end completion across all three episodes
- boundary save/restore progression
- deterministic event/digest traces
- portal/controller wiring
- campaign registry coverage
- player HP persistence contract across scene transitions
