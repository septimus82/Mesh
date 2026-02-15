# Episode 03: The Three Sigils

`scenes/episode_03_ep03.json` is a deterministic puzzle-focused episode built entirely from existing runtime behaviours.

## Core Assets

- Scene: `scenes/episode_03_ep03.json`
- Cutscenes: `ep03_intro`, `ep03_reset_wrong`, `ep03_outro`
- Dialogue: `ep03_dialogue_intro` (+ optional `ep03_dialogue_hint`)
- Quest: `episode_03_ep03`

## Entity Table

- `episode_03_ep03_player`: player pawn.
- `episode_03_ep03_entry_trigger`: `TriggerVolume`, emits `ep03_entered`.
- `episode_03_ep03_mentor`: mentor NPC with `DialogueRunner`.
- `episode_03_ep03_sigil_a`: interactable sigil A.
- `episode_03_ep03_sigil_b`: interactable sigil B.
- `episode_03_ep03_sigil_c`: interactable sigil C.
- `episode_03_ep03_hint_plaque`: optional hint interactable.
- `episode_03_ep03_exit_door`: exit interactable, gated by `ep03.solved`.
- Controller entities use `ActionListRunner` for branching, puzzle sequence, reset, unlock, and outro.

## Event Flow

1. Entry trigger emits `ep03_entered`.
2. Intro controller sets `ep03.entered`, emits `ep03_intro_start`.
3. Intro cutscene emits `ep03_intro_done`, then starts `ep03_dialogue_intro`.
4. Dialogue branch:
   - `Ask for help.` sets `ep03.hints_enabled`.
   - `Stay silent.` sets `ep03.no_hints`.
   - Both emit `ep03_choice_made` and set `ep03.choice_committed`.
5. Hint plaque emits `ep03_hint_requested`; hint controller emits `ep03_hint_shown` only when hints are enabled.
6. Sigil puzzle:
   - Correct order A -> B -> C sets `ep03.seq1`, `ep03.seq2`, `ep03.solved`.
   - Completing C emits `ep03_puzzle_solved` -> unlock controller emits `ep03_exit_unlocked`.
7. Wrong order on B/C emits `ep03_wrong_order`; reset controller clears sequence flags and emits `ep03_reset_start`.
8. `ep03_reset_wrong` cutscene emits `ep03_reset_done`.
9. Door interaction emits `ep03_exit_door_interact`, outro controller emits `ep03_outro_start`.
10. Outro cutscene emits `ep03_complete`; quest stage 3 emits `quest_ep03_complete`.

## Flags

- `ep03.entered`
- `ep03.choice_committed`
- `ep03.hints_enabled`
- `ep03.no_hints`
- `ep03.hint_seen`
- `ep03.seq1`
- `ep03.seq2`
- `ep03.solved`
- `ep03.exit_unlocked`
- `ep03.complete`
- `episode_03_ep03_complete` (quest reward flag)

## Test Scenarios

`tests/test_episode_03_ep03_integration.py` covers:

- happy path with hints enabled
- happy path with no hints
- wrong-order reset flow and recovery
- save/restore mid-puzzle
- deterministic digest/event sequence contract
