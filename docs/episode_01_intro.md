# Episode 01 Intro

## Overview
`scenes/episode_01_intro.json` is a deterministic narrative vertical slice built on existing systems only:
- `CutsceneRunner` (`ep01_intro`, `ep01_outro`)
- `DialogueRunner` (`ep01_dialogue_intro`)
- `ActionListRunner` event/flag gates
- `Interactable` objective + exit
- `QuestRunner` (`episode_01`)
- `GameplayEventBus` event routing

## Wiring Diagram
1. Player enters `episode_01_entry_trigger` -> emits `ep01_entered`.
2. `episode_01_intro_start_ctrl` emits `ep01_intro_start`.
3. Intro cutscene starts, waits, emits `ep01_intro_cutscene_done`, then emits `cutscene_start_dialogue`.
4. Dialogue starts on `episode_01_mentor`.
5. Choice branch emits `dialogue_choice`; controllers map to:
- help path: set `ep01.choice_help` + emit `ep01_choice_made`.
- solo path: set `ep01.choice_solo` + emit `ep01_choice_made`.
6. Interacting with `episode_01_journal` emits `ep01_clue_found`.
7. Unlock controllers gate on choice flags and emit `ep01_exit_unlocked`, setting `ep01.exit_unlocked`.
8. Interacting with `episode_01_exit_door` emits `ep01_exit_door_interact`.
9. Outro controller emits `ep01_outro_start`.
10. Outro cutscene emits `ep01_complete`.
11. Quest `episode_01` completes and emits `quest_episode_01_complete`.

## Entity Table
- `episode_01_player`: player pawn.
- `episode_01_entry_trigger`: entry `TriggerVolume`.
- `episode_01_mentor`: `DialogueRunner`.
- `episode_01_journal`: clue `Interactable`.
- `episode_01_exit_door`: gated `Interactable`.
- `episode_01_intro_start_ctrl`: starts intro flow.
- `episode_01_choice_help_ctrl`: branch A flag/event.
- `episode_01_choice_solo_ctrl`: branch B flag/event.
- `episode_01_unlock_help_ctrl`: unlock gate for help branch.
- `episode_01_unlock_solo_ctrl`: unlock gate for solo branch.
- `episode_01_outro_ctrl`: starts outro.
- `episode_01_complete_ctrl`: sets completion flag.

## Flags
- `ep01.entered`
- `ep01.choice_help`
- `ep01.choice_solo`
- `ep01.exit_unlocked`
- `ep01.complete`
- `episode_01_complete` (quest reward flag)

## Test Notes
`tests/test_episode_01_integration.py` covers:
- happy path (help branch)
- happy path (solo branch)
- save/restore mid-cutscene
- save/restore mid-dialogue
- deterministic replay contract:
  - identical world digest sequence
  - identical emitted event sequence
