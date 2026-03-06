# Act 1 Release Checklist (Ch2-Ch7)

## Start and expected flow
- Start scene: `packs/core_regions/scenes/Act1_Chapter2_Camp.json`
- Expected critical path:
  1. Ch2 Camp -> Ch2 Ambush -> Ch2 RuinedGate -> Ch3 Stub
  2. Ch3 Archive -> Ch3 Courtyard -> Ch4 Stub
  3. Ch4 Bastion -> Ch4 Fork -> Ch5 Stub
  4. Ch5 Gauntlet -> Ch5 Summit -> Ch6 Approach
  5. Ch6 Approach -> Ch6 Warden -> Ch7 Aftermath

## Per-chapter checks

| Chapter | Entry scene | Expected objective text | Checkpoint expected + toast | Gating condition (flag) | Expected reward feedback toast(s) | Expected pickups |
| --- | --- | --- | --- | --- | --- | --- |
| Ch2 | `packs/core_regions/scenes/Act1_Chapter2_Camp.json` | `Talk to the camp leader.` then `Survive the ambush. Clear the attackers.` | `act1_ch2_checkpoint` in `Act1_Chapter2_RuinedGate.json` with `Checkpoint reached: Chapter 2` | `act1_ch2_ambush_cleared` | `Objective updated: Head to the ambush lane.` and `Objective complete: Ambush cleared. Gate unlocked.` | 1 |
| Ch3 | `packs/core_regions/scenes/Act1_Chapter3_Archive.json` | `Search the archive for the marked note.` then `Secure the courtyard.` | `act1_ch3_checkpoint` in `Act1_Chapter3_Courtyard.json` with `Checkpoint reached: Chapter 3` | `act1_ch3_courtyard_cleared` | `Objective updated: Secure the courtyard.` and `Objective complete: Courtyard secured.` | 1 |
| Ch4 | `packs/core_regions/scenes/Act1_Chapter4_Bastion.json` | `Check in at the bastion.` then `Clear the bastion approach.` | `act1_ch4_checkpoint` in `Act1_Chapter4_Fork.json` with `Checkpoint reached: Chapter 4` | `act1_ch4_bastion_cleared` | `Objective updated: Clear the approach.` and `Objective complete: Bastion secured.` | 1 |
| Ch5 | `packs/core_regions/scenes/Act1_Chapter5_Gauntlet.json` | `Push through the gauntlet.` then `Reach the summit seal.` | `act1_ch5_checkpoint` in `Act1_Chapter5_Summit.json` with `Checkpoint reached: Chapter 5` | `act1_ch5_ready_for_summit` then `act1_chapter5_complete` | `Objective updated: Ascend to the summit.`, `Objective complete: Act 1 Chapter 5.`, `Key acquired: Summit Cache Key.` | 1 |
| Ch6 | `packs/core_regions/scenes/Act1_Chapter6_Approach.json` | `Check in at the approach watch post.` then `Defeat the Warden and secure the key fragment.` | `act1_ch6_checkpoint` in `Act1_Chapter6_Warden.json` with `Checkpoint reached: Chapter 6` | `act1_ch6_briefed` then `act1_ch6_warden_defeated` | `Objective updated: Enter the Warden arena.`, `Objective updated: Defeat the Warden.`, `Warning: Heavy strike radius. Impact in 2s. Reposition now.`, `Objective complete: Warden defeated. Fragment secured.` | 2 |
| Ch7 | `packs/core_regions/scenes/Act1_Chapter7_Aftermath.json` | `Resolve the aftermath and close Act 1.` | `act1_ch7_checkpoint` in `Act1_Chapter7_Aftermath.json` with `Checkpoint reached: Chapter 7` | `act1_ch6_warden_defeated` | `Objective complete: Act 1 resolved.` | 0 |

## Boss checklist (Ch6 Warden)
- Aggro trigger works once:
  - `Ch6WardenAggroZone` -> sets `act1_ch6_warden_engaged` with `once=true`.
- AoE warning marker visible:
  - entity `Ch6WardenAoeWarnMarker` present in `Act1_Chapter6_Warden.json`.
- AoE warning toast text:
  - `Warning: Heavy strike radius. Impact in 2s. Reposition now.`
- Defeat sets both required flags:
  - `act1_ch6_warden_defeated`
  - `act1_ch6_key_fragment`

## No hard-lock transition checklist
- `Act1_Chapter2_Ambush.json` / `ToRuinedGateFromAmbush` -> `Act1_Chapter2_RuinedGate.json` requires `act1_ch2_ambush_cleared`
- `Act1_Chapter2_RuinedGate.json` / `ToChapter3` -> `Act1_Chapter3_Stub.json` requires `act1_ch2_ambush_cleared`
- `Act1_Chapter3_Courtyard.json` / `ToChapter4FromCourtyard` -> `Act1_Chapter4_Stub.json` requires `act1_ch3_courtyard_cleared`
- `Act1_Chapter4_Fork.json` / `ToChapter5` -> `Act1_Chapter5_Stub.json` requires `act1_ch4_bastion_cleared`
- `Act1_Chapter5_Gauntlet.json` / `ToChapter5Summit` -> `Act1_Chapter5_Summit.json` requires `act1_ch5_ready_for_summit`
- `Act1_Chapter5_Summit.json` / `ToChapter6Approach` -> `Act1_Chapter6_Approach.json` requires `act1_chapter5_complete`
- `Act1_Chapter6_Approach.json` / `ToChapter6Warden` -> `Act1_Chapter6_Warden.json` requires `act1_ch6_briefed`
- `Act1_Chapter6_Warden.json` / `ToChapter7Aftermath` -> `Act1_Chapter7_Aftermath.json` requires `act1_ch6_warden_defeated`
