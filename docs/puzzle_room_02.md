# Puzzle Room 02

Puzzle Room 02 extends the rune sequence with a timer and a sentinel hazard.
All logic uses gameplay events + ActionListRunner flag gating.

Entities
- Entry trigger emits `room2_entered` and starts the timer.
- Rune A/B/C prefabs emit `puzzle2_rune_a|b|c` on enter via TriggerVolume.
- HintPlaque02 prefab uses Interactable to emit `hint2_plaque_interact` and a DialogueRunner with id `puzzle2_hint_plaque`.
- ExitDoor02 prefab is Interactable gated by `require_flags: ["puzzle2.solved"]`.
- Sentinel02 prefab patrols a short path; SentinelVision02 emits `sentinel_spotted` when the player enters.

Event flow
- `room2_entered` -> ActionListRunner starts timer and emits `room2_started`.
- `hint2_plaque_interact` starts the DialogueRunner.
- `dialogue_completed` (filtered by `dialogue_id=puzzle2_hint_plaque`) emits `hint2_read`.
- `puzzle2_rune_*` events feed the B-A-C sequence.
- `puzzle2_timeout` or `sentinel_spotted` emits `puzzle2_failed` with reason.
- Reset cutscene emits `puzzle2_reset`, restarting the timer if `puzzle2.restart_pending` is set.

Flags
- `puzzle2.seq1` -> Rune B accepted (expecting A).
- `puzzle2.seq2` -> Rune A accepted (expecting C).
- `puzzle2.solved` -> Puzzle complete; enables ExitDoor02.
- `puzzle2.running` -> Timer active; runes only respond while true.
- `puzzle2.locked` -> Short lockout during wrong-sequence resets.
- `puzzle2.restart_pending` -> Failure reset waits for cutscene.

ActionListRunner controllers
- `PuzzleStart02` starts the timer and emits `room2_started`.
- `PuzzleSequenceB/A/C02` advance the sequence and emit `puzzle2_progress` / `puzzle2_solved`.
- `PuzzleWrongStart/Seq1/Seq2_02` clear sequence flags, emit `puzzle2_wrong`, delay 0.25s, then emit `puzzle2_reset`.
- `PuzzleTimeout02` + `PuzzleSpotted02` emit `puzzle2_failed` and arm restart.
- `PuzzleResetAfterFail02` clears restart flags and restarts the timer on `puzzle2_reset`.

Cutscene
- `cutscenes.json` defines `puzzle_room_02_reset` which waits briefly then emits `puzzle2_reset`.

Quest
- Quest `puzzle_room_02` advances on `room2_entered`, `hint2_read`, `puzzle2_solved` and emits `quest_room2_complete`.
- `PuzzleSequenceC02` also emits `hint2_read` so the optional hint step can be skipped.
