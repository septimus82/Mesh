# Puzzle Room 01

Puzzle Room 01 is wired entirely through gameplay events + ActionListRunner flags.

Entities
- Rune A/B/C prefabs emit `puzzle_rune_a|b|c` on enter via TriggerVolume.
- HintPlaque prefab uses Interactable to emit `hint_plaque_interact` and a DialogueRunner with id `puzzle_hint_plaque`.
- ExitDoor prefab is Interactable gated by `require_flags: ["puzzle.solved"]`.

Event flow
- `room_entered` fires from the entry trigger and completes quest step0.
- `hint_plaque_interact` triggers an ActionListRunner that starts the DialogueRunner.
- `dialogue_completed` (filtered by `dialogue_id=puzzle_hint_plaque`) emits `hint_read` to complete quest step1.
- `puzzle_rune_*` events feed the puzzle sequence ActionListRunners.

Flags
- `puzzle.seq1` -> Rune A accepted (expecting C).
- `puzzle.seq2` -> Rune C accepted (expecting B).
- `puzzle.solved` -> Puzzle complete; enables ExitDoor interaction.
- `puzzle.locked` -> Short lockout during reset after a wrong rune.

ActionListRunner controllers
- `PuzzleSequenceA/C/B` advance the sequence and emit `puzzle_progress` / `puzzle_solved`.
- `PuzzleWrongStart/Seq1/Seq2` clear sequence flags, emit `puzzle_wrong`, delay 0.25s, then emit `puzzle_reset`.

Quest
- Quest `puzzle_room_01` advances on `room_entered`, `hint_read`, `puzzle_solved` and emits `quest_room_complete`.
