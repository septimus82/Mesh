# Scenes

Mesh scene schema lives at `docs/mesh_scene_spec.md`.

Engine version: 0.5.0

## scenes/cellar.json
[ok] Valid

- Entities: 8
- Layers: background, entities, foreground
- Tags: enemy, player, trigger
- Warnings:
  - Entity[4] 'DemoObjectiveCellarZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'

## scenes/combat_tutorial_demo.json
[ok] Valid

- Entities: 14
- Layers: background, entities, foreground
- Tags: enemy, player, prop, spawn_point, trigger
- Warnings:
  - Entity[4] 'CombatTutorialFailZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'
  - Entity[7] 'CombatTutorialV2Phase1Zone' behaviour_config[TriggerZone]: unknown config field 'zone_id'
  - Entity[8] 'CombatTutorialV2Phase2Zone' behaviour_config[TriggerZone]: unknown config field 'zone_id'
  - Entity[9] 'CombatTutorialV2CompleteZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'

## scenes/combat_vignette_01.json
[ok] Valid

- Entities: 8
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'ArenaEntryTrigger' uses prefab_id 'cv_entry_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'SentryArcher' uses prefab_id 'sentry_archer' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RewardChest' uses prefab_id 'chest_reward_cv' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'CombatVignetteInit' uses prefab_id 'cv_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'CombatVignetteOnEnemyDead' uses prefab_id 'cv_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'CombatVignetteOnReward' uses prefab_id 'cv_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'CampaignCombatDone' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/door_field.json
[ok] Valid

- Entities: 17
- Layers: background, entities, foreground
- Tags: player, spawn_point

## scenes/door_interior.json
[ok] Valid

- Entities: 9
- Layers: background, entities, foreground
- Tags: player, spawn_point, trigger
- Warnings:
  - Entity[3] 'DemoObjectiveInteriorZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'

## scenes/episode_01_intro.json
[ok] Valid

- Entities: 20
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Episode01Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01EntryTrigger' uses prefab_id 'ep01_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Mentor' uses prefab_id 'npc_mentor' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Journal' uses prefab_id 'ep01_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01ExitDoor' uses prefab_id 'ep01_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01IntroStart' uses prefab_id 'ep01_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01ChoiceHelp' uses prefab_id 'ep01_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01ChoiceSolo' uses prefab_id 'ep01_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01UnlockHelp' uses prefab_id 'ep01_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01UnlockSolo' uses prefab_id 'ep01_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01OutroStart' uses prefab_id 'ep01_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Complete' uses prefab_id 'ep01_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Campaign02Start' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Campaign02Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01ExitToEpisode02' uses prefab_id 'campaign_portal' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Campaign03HelpPayoff' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Campaign03SoloPayoff' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Campaign03Start' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Campaign03Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode01Campaign04HelpPayoff' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/episode_02_ep02.json
[ok] Valid

- Entities: 25
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Episode02Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02EntryTrigger' uses prefab_id 'ep02_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02Mentor' uses prefab_id 'ep02_mentor' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02SignalTerminal' uses prefab_id 'ep02_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02RelayA' uses prefab_id 'ep02_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02RelayB' uses prefab_id 'ep02_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02RelayC' uses prefab_id 'ep02_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02Breaker' uses prefab_id 'ep02_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02ExitDoor' uses prefab_id 'ep02_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02IntroStart' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02ChoiceStabilize' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02ChoiceShutdown' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02TerminalTouch' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02RelayAController' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02RelayBController' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02RelayCController' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02ShutdownController' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02UnlockStable' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02UnlockShutdown' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02OutroStart' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02Complete' uses prefab_id 'ep02_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02Campaign02Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02ExitToEpisode03' uses prefab_id 'campaign_portal' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02Campaign03Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode02Campaign04Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/episode_03_ep03.json
[ok] Valid

- Entities: 26
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Episode03Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03EntryTrigger' uses prefab_id 'ep03_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03Mentor' uses prefab_id 'ep03_mentor' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03SigilA' uses prefab_id 'ep03_sigil_a' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03SigilB' uses prefab_id 'ep03_sigil_b' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03SigilC' uses prefab_id 'ep03_sigil_c' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03HintPlaque' uses prefab_id 'ep03_hint_plaque' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03ExitDoor' uses prefab_id 'ep03_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03IntroStart' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03ChoiceHelp' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03ChoiceSilent' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03HintController' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03SigilAController' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03SigilBController' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03SigilCController' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03WrongOrderB' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03WrongOrderC' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03WrongOrderReset' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03UnlockController' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03OutroController' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03CompleteController' uses prefab_id 'ep03_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03Campaign02Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03Campaign03Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03ExitToEpisode04' uses prefab_id 'campaign_portal' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03Campaign04Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode03Campaign05Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/episode_04_ep04.json
[ok] Valid

- Entities: 26
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Episode04Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04EntryTrigger' uses prefab_id 'ep04_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04Mentor' uses prefab_id 'ep04_mentor' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04SentryEasy' uses prefab_id 'ep04_sentry' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04SentryHardA' uses prefab_id 'ep04_sentry_hard' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04SentryHardB' uses prefab_id 'ep04_sentry_hard' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04RewardCache' uses prefab_id 'ep04_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04ExitDoor' uses prefab_id 'ep04_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04IntroStart' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04ChoiceSafe' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04ChoiceHard' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04CombatStartSafe' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04CombatStartHard' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04EasyDead' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04HardADead' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04HardBDead' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04HardCompleteFromA' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04HardCompleteFromB' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04RewardCtrl' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04Complete' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04RewardBonusCache' uses prefab_id 'ep04_reward_bonus' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04RewardBonusCtrl' uses prefab_id 'ep04_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04Campaign03Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04Campaign04Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04ExitToEpisode05' uses prefab_id 'campaign_portal' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode04Campaign05Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/episode_05_ep05.json
[ok] Valid

- Entities: 26
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Episode05Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05EntryTrigger' uses prefab_id 'ep05_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05Vendor' uses prefab_id 'ep05_vendor_npc' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05NoticeBoard' uses prefab_id 'ep05_notice_board' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05NightGate' uses prefab_id 'ep05_night_gate' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05Mentor' uses prefab_id 'ep05_mentor' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05RewardCache' uses prefab_id 'ep05_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05RewardBonusCache' uses prefab_id 'ep05_reward_bonus' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05ExitDoor' uses prefab_id 'ep05_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05IntroStart' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05ChoiceRumors' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05ChoiceMove' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05VendorOpen' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05VendorClose' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05VendorSpoken' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05NoticeSide' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05NightGateOpen' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05TavernMeet' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05RewardStandard' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05RewardBonus' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05OutroStart' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05Complete' uses prefab_id 'ep05_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05Campaign04BonusReward' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05Campaign04Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05Campaign05Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode05ExitToEpisode06' uses prefab_id 'campaign_portal' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/episode_06_ep06.json
[ok] Valid

- Entities: 25
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Episode06Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06EntryTrigger' uses prefab_id 'ep06_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06Mentor' uses prefab_id 'ep06_mentor' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RuneA' uses prefab_id 'ep06_rune_a' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RuneB' uses prefab_id 'ep06_rune_b' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06FightSentry' uses prefab_id 'ep06_fight_sentry' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06PuzzleSentry' uses prefab_id 'ep06_puzzle_sentry' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RewardCache' uses prefab_id 'ep06_reward' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RewardBonusCache' uses prefab_id 'ep06_reward_bonus' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06ExitDoor' uses prefab_id 'ep06_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06IntroStart' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06ChoiceFight' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06ChoicePuzzle' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06FightDead' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06PuzzleDead' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RuneAController' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RuneBController' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06WrongOrderController' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06ResetDoneController' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06UnlockController' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RewardStandard' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06RewardBonus' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06OutroStart' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06Complete' uses prefab_id 'ep06_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Episode06Campaign05Done' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/guard_patrol_chase_demo.json
[ok] Valid

- Entities: 16
- Layers: background, entities, foreground
- Tags: npc, patrol_waypoint, player, prop, spawn_point, trigger
- Warnings:
  - Entity[3] 'GuardPatrolDemoHintZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'
  - Entity[4] 'GuardPatrolDemoSpottedZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'

## scenes/guard_patrol_chase_duo_demo.json
[ok] Valid

- Entities: 20
- Layers: background, entities, foreground
- Tags: npc, patrol_waypoint_a, patrol_waypoint_b, player, prop, spawn_point, trigger
- Warnings:
  - Entity[3] 'GuardPatrolDuoHintZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'
  - Entity[4] 'GuardPatrolChaseDuoDemoSpottedZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'

## scenes/lighting_showcase.json
[ok] Valid

- Entities: 11
- Layers: background, entities, foreground
- Tags: exit, player, prop, spawn_point, trigger
- Warnings:
  - Entity[1] 'visited_trigger' behaviour_config[TriggerZone]: unknown config field 'zone_id'

## scenes/main_menu.json
[ok] Valid

- Entities: 1
- Layers: ui
- Tags: -

## scenes/micro_stealth_completion_room.json
[ok] Valid

- Entities: 5
- Layers: background, entities, foreground
- Tags: prop, spawn_point

## scenes/outside.json
[ok] Valid

- Entities: 1
- Layers: entities
- Tags: player

## scenes/puzzle_room_01.json
[ok] Valid

- Entities: 15
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'PuzzlePlayer' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RoomEntryTrigger' uses prefab_id 'puzzle_room_entry_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RuneA' uses prefab_id 'puzzle_rune_a' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RuneC' uses prefab_id 'puzzle_rune_c' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RuneB' uses prefab_id 'puzzle_rune_b' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'HintPlaque' uses prefab_id 'puzzle_hint_plaque' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'ExitDoor' uses prefab_id 'puzzle_exit_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleHintStart' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleHintComplete' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleSequenceA' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleSequenceC' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleSequenceB' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleWrongStart' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleWrongSeq1' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleWrongSeq2' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/puzzle_room_02.json
[ok] Valid

- Entities: 23
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'PuzzlePlayer' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RoomEntryTrigger02' uses prefab_id 'puzzle_room2_entry_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RuneB02' uses prefab_id 'puzzle2_rune_b' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RuneA02' uses prefab_id 'puzzle2_rune_a' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RuneC02' uses prefab_id 'puzzle2_rune_c' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'HintPlaque02' uses prefab_id 'puzzle2_hint_plaque' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'ExitDoor02' uses prefab_id 'puzzle2_exit_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Puzzle2Timer' uses prefab_id 'puzzle2_timer' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Sentinel02' uses prefab_id 'puzzle2_sentinel' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'SentinelVision02' uses prefab_id 'puzzle2_sentinel_vision' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleResetCutscene02' uses prefab_id 'puzzle2_cutscene_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleStart02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleHintStart02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleHintComplete02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleSequenceB02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleSequenceA02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleSequenceC02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleWrongStart02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleWrongSeq1_02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleWrongSeq2_02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleTimeout02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleSpotted02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleResetAfterFail02' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/puzzle_room_03.json
[ok] Valid

- Entities: 16
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'PuzzlePlayer' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RoomEntryTrigger03' uses prefab_id 'puzzle_room3_entry_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'LeverLeft03' uses prefab_id 'puzzle3_lever_left' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'LeverRight03' uses prefab_id 'puzzle3_lever_right' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'RuneCenter03' uses prefab_id 'puzzle3_rune_center' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'ExitDoor03' uses prefab_id 'puzzle3_exit_door' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'Puzzle3Timer' uses prefab_id 'puzzle3_timer' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleInit03' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleLeftCorrect03' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleRightCorrect03' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleWrongOrder03' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleRuneSuccess03' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleTimeout03' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleResetAfterFail03' uses prefab_id 'puzzle_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'CampaignPuzzleDone' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'PuzzleExitToCombat' uses prefab_id 'campaign_portal' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/reward_nook_01.json
[ok] Valid

- Entities: 8
- Layers: background, entities, foreground
- Tags: spawn_point, trigger
- Warnings:
  - tilemap.path missing; tilemap will not render unless runtime supports in-scene grids

## scenes/runtime_smoke_scene.json
[ok] Valid

- Entities: 0
- Layers: background, entities, foreground
- Tags: -

## scenes/showcase_dungeon.json
[ok] Valid

- Entities: 8
- Layers: entities
- Tags: enemy, interactable, npc, player, solid, spawn_point, trigger

## scenes/showcase_hub.json
[ok] Valid

- Entities: 12
- Layers: background, entities, foreground
- Tags: exit, npc, player, prop, spawn_point

## scenes/showcase_interior.json
[ok] Valid

- Entities: 3
- Layers: entities
- Tags: npc, trigger
- Warnings:
  - Entity[0] 'Showcase Merchant' behaviour_config[Vendor]: unknown config field 'inventory'

## scenes/side_room_01.json
[ok] Valid

- Entities: 11
- Layers: background, entities, foreground
- Tags: spawn_point, trigger
- Warnings:
  - tilemap.path missing; tilemap will not render unless runtime supports in-scene grids

## scenes/stamp_audit_sandbox.json
[ok] Valid

- Entities: 0
- Layers: -
- Tags: -
- Warnings:
  - tilemap.path missing; tilemap will not render unless runtime supports in-scene grids

## scenes/target.json
[ok] Valid

- Entities: 1
- Layers: entities
- Tags: player

## scenes/test_scene.json
[ok] Valid

- Entities: 1
- Layers: entities
- Tags: npc

## scenes/town_schedule_01.json
[ok] Valid

- Entities: 13
- Layers: background, entities, foreground
- Tags: -
- Warnings:
  - Entity 'Player' uses prefab_id 'player' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'TownEntryTrigger' uses prefab_id 'town_entry_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'VendorNpc' uses prefab_id 'town_vendor_npc' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'NightGate' uses prefab_id 'town_night_gate' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'SecretTrigger' uses prefab_id 'town_secret_trigger' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'TownInit' uses prefab_id 'town_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'VendorOpenCtrl' uses prefab_id 'town_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'VendorCloseCtrl' uses prefab_id 'town_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'VendorInteractGate' uses prefab_id 'town_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'GateOpenCtrl' uses prefab_id 'town_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'SecretFoundCtrl' uses prefab_id 'town_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'CampaignTownDone' uses prefab_id 'campaign_controller' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.
  - Entity 'TownExitToPuzzle' uses prefab_id 'campaign_portal' and must not set 'name'. Use mesh_name for instance naming or variant_id for display changes.

## scenes/upper_hall.json
[ok] Valid

- Entities: 30
- Layers: background, entities, foreground
- Tags: player, prop, spawn_point, trigger
- Warnings:
  - Entity[16] 'DemoObjectiveUpperHallZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'

## scenes/upper_hall_vault.json
[ok] Valid

- Entities: 5
- Layers: background, entities, foreground
- Tags: player, spawn_point, trigger
- Warnings:
  - Entity[3] 'DemoObjectiveUpperHallVaultZone' behaviour_config[TriggerZone]: unknown config field 'zone_id'
