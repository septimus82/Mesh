# Episode 02: Signal in the Dust

`scenes/episode_02_ep02.json` is a deterministic branching episode built only from existing runtime behaviours.

## Wiring Summary

- Cutscenes: `ep02_intro`, `ep02_outro`
- Dialogue: `ep02_dialogue_intro`
- Quest: `episode_02_ep02`
- Objective branches:
  - Stabilize path: relay chain A -> B -> C
  - Shutdown path: breaker

## Entity Table

- `episode_02_ep02_player`: player pawn.
- `episode_02_ep02_entry_trigger`: `TriggerVolume`, emits `ep02_entered`.
- `episode_02_ep02_mentor`: mentor NPC, `DialogueRunner`.
- `episode_02_ep02_signal_terminal`: primary terminal `Interactable`.
- `episode_02_ep02_relay_a`: relay A `Interactable`.
- `episode_02_ep02_relay_b`: relay B `Interactable`.
- `episode_02_ep02_relay_c`: relay C `Interactable`.
- `episode_02_ep02_breaker`: breaker `Interactable`.
- `episode_02_ep02_exit_door`: gated exit `Interactable`.
- `episode_02_ep02_intro_start_ctrl`: starts intro flow.
- `episode_02_ep02_choice_stabilize_ctrl`: dialogue branch A controller.
- `episode_02_ep02_choice_shutdown_ctrl`: dialogue branch B controller.
- `episode_02_ep02_terminal_touch_ctrl`: records first terminal handshake.
- `episode_02_ep02_relay_a_ctrl`: marks relay A progress.
- `episode_02_ep02_relay_b_ctrl`: marks relay B progress.
- `episode_02_ep02_relay_c_ctrl`: completes stabilize objective (`ep02_signal_stable`).
- `episode_02_ep02_shutdown_ctrl`: completes shutdown objective (`ep02_signal_off`).
- `episode_02_ep02_unlock_stable_ctrl`: emits `ep02_exit_unlocked` for stabilize branch.
- `episode_02_ep02_unlock_shutdown_ctrl`: emits `ep02_exit_unlocked` for shutdown branch.
- `episode_02_ep02_outro_ctrl`: emits `ep02_outro_start` after valid exit interact.
- `episode_02_ep02_complete_ctrl`: sets final completion flag.

Entity count: `21` (<= 25 target).

## Event Flow

1. Entry trigger emits `ep02_entered`.
2. Intro controller sets `ep02.entered` and emits `ep02_intro_start`.
3. Intro cutscene emits `ep02_intro_done` and starts dialogue.
4. Dialogue choice:
   - stabilize: set `ep02.choice_stabilize`, emit `ep02_choice_made`.
   - shutdown: set `ep02.choice_shutdown`, emit `ep02_choice_made`.
5. Terminal interaction emits `ep02_terminal_touched`, sets `ep02.terminal_touched`.
6. Objective branch:
   - stabilize: relay A -> relay B -> relay C emits `ep02_signal_stable`.
   - shutdown: breaker emits `ep02_signal_off`.
7. Unlock controller emits `ep02_exit_unlocked` and sets `ep02.exit_unlocked`.
8. Exit door interaction emits `ep02_exit_door_interact`.
9. Outro controller emits `ep02_outro_start`; outro cutscene emits `ep02_complete`.
10. Quest stage 3 completes and emits `quest_ep02_complete`.

## Flags

- `ep02.entered`
- `ep02.choice_stabilize`
- `ep02.choice_shutdown`
- `ep02.terminal_touched`
- `ep02.relay_1_done`
- `ep02.relay_2_done`
- `ep02.signal_stable`
- `ep02.signal_off`
- `ep02.exit_unlocked`
- `ep02.complete`
- `episode_02_ep02_complete` (quest reward flag)

## Test Scenarios

`tests/test_episode_02_ep02_integration.py` covers:

- stabilize path happy flow.
- shutdown path happy flow.
- save/restore mid-cutscene.
- save/restore mid-dialogue.
- save/restore mid-objective (after relay A only).
- determinism contract: same dt + same interaction schedule => identical digest and identical event sequence.
