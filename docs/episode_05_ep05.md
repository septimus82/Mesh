# Episode 05: Hollowmere Market

## Intent
Episode 05 demonstrates deterministic schedule-driven content using existing systems: `NpcSchedule`, `TimeOfDayGate`, `DialogueRunner`, `ActionListRunner`, `QuestRunner`, and `GameplayEventBus`.

## Entity Table
- `episode_05_ep05_player`: player start.
- `episode_05_ep05_entry_trigger` (`ep05_trigger`): emits `ep05_entered`.
- `episode_05_ep05_vendor` (`ep05_vendor_npc`): morning/afternoon/night schedule + vendor interaction attempt event.
- `episode_05_ep05_notice_board` (`ep05_notice_board`): optional side-objective interactable.
- `episode_05_ep05_night_gate` (`ep05_night_gate`): time-of-day gate that opens at night.
- `episode_05_ep05_mentor` (`ep05_mentor`): intro dialogue host and night tavern interaction objective.
- `episode_05_ep05_reward_cache` (`ep05_reward`): standard reward (forbid `ep05.side_done`).
- `episode_05_ep05_reward_bonus_cache` (`ep05_reward_bonus`): bonus reward (require `ep05.side_done`).
- `episode_05_ep05_exit_door` (`ep05_door`): final exit (requires `ep05.exit_unlocked` and `ep05.reward_collected`).
- `episode_05_ep05_*_ctrl` (`ep05_controller`): deterministic event/flag routing.

## Event Flow
1. Entry trigger emits `ep05_entered` -> intro controller sets `ep05.entered` and emits `ep05_intro_start`.
2. Intro cutscene emits `ep05_intro_done` and starts `ep05_dialogue_intro`.
3. Dialogue choice sets `ep05.rumors_enabled` or `ep05.rumors_disabled` and emits `ep05_choice_made`.
4. Vendor schedule emits `ep05_vendor_opened` / `ep05_vendor_closed`; controllers maintain `ep05.vendor.open`.
5. Vendor interaction emits `ep05_vendor_interact_attempt`; gate controller emits `ep05_vendor_spoken` only when `ep05.vendor.open` is true.
6. Optional side path: notice board emits `ep05_notice_board_read`; controller sets `ep05.side_done` only if rumors path was chosen before vendor completion.
7. Night gate opens via `ep05_night_gate_opened`; controller sets `ep05.night_gate_open`.
8. Mentor interaction emits `ep05_mentor_interact`; tavern controller requires vendor spoken + night gate open, then sets `ep05.tavern_met`, `ep05.exit_unlocked`, and emits `ep05_tavern_met` + `ep05_exit_unlocked`.
9. Quest stage 3 completes on `ep05_tavern_met` and emits `quest_ep05_complete`.
10. Reward branch:
   - Standard: `ep05_reward_collected`.
   - Bonus: `ep05_reward_bonus_collected` + `ep05.reward_bonus_collected`.
11. Exit interaction emits `ep05_exit_door_interact`; outro controller emits `ep05_outro_start`.
12. Outro cutscene emits `ep05_complete`; completion controller sets `ep05.complete`.

## Flags
- Core: `ep05.entered`, `ep05.vendor.open`, `ep05.vendor.spoken`, `ep05.night_gate_open`, `ep05.tavern_met`, `ep05.exit_unlocked`, `ep05.reward_collected`, `ep05.complete`.
- Choice: `ep05.rumors_enabled`, `ep05.rumors_disabled`.
- Side objective: `ep05.side_done`, `ep05.reward_bonus_collected`.

## Test Scenarios
- Required path: direct dialogue choice, vendor in morning, mentor at night, standard reward.
- Side-objective path: rumors choice + notice board before vendor, then bonus reward branch.
- Save/restore mid-day: restore clock/flags/quest and continue to completion.
- Determinism: repeated runs with identical schedule/actions produce identical digest and event sequences.
