# Act 1 Content Plan (Ch2-Ch7)

## Spine quest chain

1. Chapter 2 start (`quest_act1_chapter2_start`) -> camp briefing (`quest_act1_ch2_camp_briefing`) -> ambush clear (`quest_act1_ch2_ambush_clear`) -> existing ruined gate chain (`quest_act1_ch2_ruin_switch` / `quest_act1_ch2_ruin_route`) -> existing Chapter 2 completion (`quest_act1_ch2_complete_a|b`).
2. Chapter 3 start (`quest_act1_chapter3_start`) -> archive briefing (`quest_act1_ch3_archive_briefing`) -> courtyard clear (`quest_act1_ch3_courtyard_clear`) -> existing note+exit chain (`quest_act1_ch3_note`, `quest_act1_ch3_exit`).
3. Chapter 4 start (`quest_act1_chapter4_start`) -> bastion briefing (`quest_act1_ch4_bastion_briefing`) -> bastion clear (`quest_act1_ch4_bastion_clear`) -> existing fork branch chain (`quest_act1_ch4_choice_a|b`, `quest_act1_ch4_complete_a|b`).
4. Chapter 5 start (`quest_act1_chapter5_start`) -> gauntlet clear (`quest_act1_ch5_gauntlet_clear`) -> summit report (`quest_act1_ch5_summit_complete`).

## Balance targets (full-playthrough pass)

| Chapter | Target time-to-clear | Expected deaths | Expected healing pickups consumed |
| --- | --- | --- | --- |
| Chapter 2 | 7-9 min | 0-1 | 1 |
| Chapter 3 | 8-10 min | 0-1 | 1 |
| Chapter 4 | 6-8 min | 0-1 | 1 |
| Chapter 5 | 8-10 min | 0-1 | 1 |
| Chapter 6 (Warden) | 10-14 min | 1-3 | 2 |
| Chapter 7 | 4-6 min | 0 | 0 |

## Chapter beats

## Chapter 2
- Rooms:
  - `Act1_Chapter2_Stub` (start/traversal, unchanged existing gate path).
  - `Act1_Chapter2_Camp` (dialogue + objective handoff).
  - `Act1_Chapter2_Ambush` (combat + lock/switch gate + reward).
  - `Act1_Chapter2_RuinedGate` (existing puzzle/branch payoff).
- Required trigger types used:
  - enter room (`Chapter2StartZone`, `Chapter2CampBriefingZone`, `Ch2AmbushClearZone`)
  - interact object (`SwitchInteract` -> `act1_ch2_ambush_unlock`)
  - dialogue choice (`act1_ch2_briefing_accept`)
  - defeat encounter path (combat scene + clear marker reward quest)
- Reward:
  - gold + chapter-advance flags (`act1_ch2_camp_briefed`, `act1_ch2_ambush_cleared`).

## Chapter 3
- Rooms:
  - `Act1_Chapter3_Stub` (existing start/checkpoint + note/exit).
  - `Act1_Chapter3_Archive` (dialogue + seal switch/lock).
  - `Act1_Chapter3_Courtyard` (combat + clear reward).
- Required trigger types used:
  - enter room (`Chapter3StartZone`, `Chapter3ArchiveNoteZone`, `Ch3CourtyardClearZone`)
  - interact object (`SwitchInteract` -> `act1_ch3_archive_unlock_event`)
  - dialogue choice (`act1_ch3_archive_accept`)
  - encounter clear reward (`quest_act1_ch3_courtyard_clear`)
- Reward:
  - gold + route-open flags (`act1_ch3_archive_briefed`, `act1_ch3_courtyard_cleared`).

## Chapter 4
- Rooms:
  - `Act1_Chapter4_Stub` (existing chapter start/checkpoint).
  - `Act1_Chapter4_Bastion` (dialogue + combat + switch gate + reward).
  - `Act1_Chapter4_Fork` (existing branch/reconverge payoff).
- Required trigger types used:
  - enter room (`Chapter4StartZone`, `Ch4BastionClearZone`)
  - interact object (`SwitchInteract` -> `act1_ch4_bastion_unlock`)
  - dialogue choice (`act1_ch4_bastion_brief`)
  - branch/reconverge completion (existing Ch4 quest chain)
- Reward:
  - gold + bastion cleared flag (`act1_ch4_bastion_cleared`).

## Chapter 5
- Rooms:
  - `Act1_Chapter5_Stub` (existing finale start/checkpoint).
  - `Act1_Chapter5_Gauntlet` (combat + lock/switch gate + clear reward).
  - `Act1_Chapter5_Summit` (dialogue + finale completion handoff).
- Required trigger types used:
  - enter room (`Chapter5StartZone`, `Ch5GauntletClearZone`, `Chapter5SummitSealZone`)
  - interact object (`SwitchInteract` -> `act1_ch5_gauntlet_unlock`)
  - dialogue choice (`act1_ch5_finale_accept`, `act1_ch5_summit_complete`)
  - encounter clear reward (`quest_act1_ch5_gauntlet_clear`)
- Reward:
  - gold + Act 1 completion flags (`act1_ch5_ready_for_summit`, `act1_chapter5_complete`).


## Chapter 6 (Capstone)
- Premise:
  - The Warden mini-boss blocks the final path. The encounter teaches spacing and zone pressure via radius triggers.
- Rooms:
  - `Act1_Chapter6_Approach` (briefing + objective handoff + fail-safe hinting).
  - `Act1_Chapter6_Warden` (mini-boss arena with aggro radius + AoE warning zone + deterministic pickups).
- Required trigger types used:
  - enter room (`Chapter6ApproachBriefingZone`)
  - circle-radius aggro (`Ch6WardenAggroZone`)
  - circle-radius AoE warning (`Ch6WardenAoeWarnZone`)
  - clear marker (`Ch6WardenDefeatZone`)
- Reward:
  - `act1_ch6_warden_defeated`, `act1_ch6_key_fragment`, `act1_ch6_checkpoint`.

## Chapter 7 (Resolution)
- Premise:
  - Aftermath resolution scene pays off the arc and closes Act 1.
- Rooms:
  - `Act1_Chapter7_Aftermath` (dialogue payoff + resolution flag + checkpoint).
- Required trigger types used:
  - enter room / resolve (`Chapter7AftermathResolveZone`)
  - checkpoint (`Ch7CheckpointZone`)
- Reward:
  - `act1_chapter7_complete`, `act1_act1_complete`, `act1_ch7_checkpoint`.
