# Act 2 Release Checklist (Ch1-Ch5)

## Start + Flow
- Bridge start scene: `packs/core_regions/scenes/Act1_Chapter7_Aftermath.json`
- Entry transition: `ToAct2Chapter1Threshold`
- Expected linear flow:
  1. Ch1 `Act2_Chapter1_Threshold` -> `Act2_Chapter1_HazardHall` -> `Act2_Chapter1_SafeRoom`
  2. Ch2 `Act2_Chapter2_SwitchRoom` -> `Act2_Chapter2_HazardRun` -> `Act2_Chapter2_Sanctum`
  3. Ch3 `Act2_Chapter3_Fork` -> (`Act2_Chapter3_RouteA_Run` or `Act2_Chapter3_RouteB_Safe`) -> `Act2_Chapter3_Rejoin`
  4. Ch4 `Act2_Chapter4_Hub` -> (`Act2_Chapter4_PathA` or `Act2_Chapter4_PathB`) -> `Act2_Chapter4_Final`
  5. Ch5 `Act2_Chapter5_Antechamber` -> `Act2_Chapter5_Overseer` -> `Act2_Chapter5_Epilogue`

## Chapter Checks

### Chapter 1
- Entry scenes:
  - `Act2_Chapter1_Threshold`
  - `Act2_Chapter1_HazardHall`
  - `Act2_Chapter1_SafeRoom`
- Expected objective text:
  - "Receive the threshold briefing."
  - "Cross the hazard hall and avoid the red zone."
  - "Secure the safe room and mark Chapter 1 complete."
- Checkpoint:
  - Flag: `act2_ch1_checkpoint`
  - Toast: `Checkpoint reached: Act 2 Chapter 1`
- Gating flags:
  - `act2_ch1_briefed` unlocks `ToAct2Chapter1HazardHall`
  - `act2_ch1_hazard_cleared` unlocks `ToAct2Chapter1SafeRoom`
  - `act2_chapter1_complete` unlocks `ToAct2Chapter2SwitchRoom`
- Mechanics taught:
  - Hazard warning/readability and avoidance lane.
- Expected pickups count:
  - 1

### Chapter 2
- Entry scenes:
  - `Act2_Chapter2_SwitchRoom`
  - `Act2_Chapter2_HazardRun`
  - `Act2_Chapter2_Sanctum`
- Expected objective text:
  - "Pull the hazard control switch."
  - "Cross the hazard run while suppression is active."
  - "Secure the sanctum and continue."
- Checkpoint:
  - Flag: `act2_ch2_checkpoint`
  - Toast: `Checkpoint reached: Act 2 Chapter 2`
- Gating flags:
  - `act2_ch2_switch_pulled` unlocks `ToAct2Chapter2HazardRun`
  - `act2_ch2_run_clear` unlocks `ToAct2Chapter2Sanctum`
  - `act2_chapter2_complete` unlocks `ToAct2Chapter3Fork`
- Mechanics taught:
  - Suppression switch timing over hazard lanes.
- Expected pickups count:
  - 2

### Chapter 3
- Entry scenes:
  - `Act2_Chapter3_Fork`
  - `Act2_Chapter3_RouteA_Run`
  - `Act2_Chapter3_RouteB_Safe`
  - `Act2_Chapter3_Rejoin`
- Expected objective text:
  - "Choose a route to reach the rejoin point."
  - "Complete Route A: suppression run."
  - "Complete Route B: safe passage."
  - "Rejoin and continue."
- Checkpoint:
  - Flag: `act2_ch3_checkpoint`
  - Toast: `Checkpoint reached: Act 2 Chapter 3`
- Gating flags:
  - `act2_ch3_route_a_selected` unlocks `ToAct2Chapter3RouteA`
  - `act2_ch3_route_b_selected` unlocks `ToAct2Chapter3RouteB`
  - `act2_ch3_route_a_clear` unlocks `ToAct2Chapter3RejoinFromA`
  - `act2_ch3_route_b_clear` unlocks `ToAct2Chapter3RejoinFromB`
  - `act2_chapter3_complete` unlocks `ToAct2Chapter4Hub`
- Mechanics taught:
  - Route tradeoff (fast/risky vs safe/slower) and reconvergence.
- Expected pickups count:
  - 2

### Chapter 4
- Entry scenes:
  - `Act2_Chapter4_Hub`
  - `Act2_Chapter4_PathA`
  - `Act2_Chapter4_PathB`
  - `Act2_Chapter4_Final`
- Expected objective text:
  - "Use your shard to proceed."
  - "Clear your path and reach the final chamber."
  - "Secure the final chamber."
- Checkpoint:
  - Flag: `act2_ch4_checkpoint`
  - Toast: `Checkpoint reached: Act 2 Chapter 4`
- Gating flags:
  - `act2_ch3_reward_shard_a` unlocks `ToAct2Chapter4PathA`
  - `act2_ch3_reward_shard_b` unlocks `ToAct2Chapter4PathB`
  - `act2_ch4_path_clear` unlocks `ToAct2Chapter4FinalFromA/B`
  - `act2_chapter4_complete` unlocks `ToAct2Chapter5Antechamber`
- Mechanics taught:
  - Shard-consequence branching and path-specific challenge.
- Expected pickups count:
  - 0

### Chapter 5
- Entry scenes:
  - `Act2_Chapter5_Antechamber`
  - `Act2_Chapter5_Overseer`
  - `Act2_Chapter5_Epilogue`
- Expected objective text:
  - "Enter the antechamber and prepare."
  - "Defeat the Overseer."
  - "Resolve the epilogue and close Act 2."
- Checkpoints:
  - Flag: `act2_ch5_checkpoint_ante`
  - Toast: `Checkpoint reached: Act 2 Chapter 5 (Antechamber)`
  - Flag: `act2_ch5_checkpoint_end`
  - Toast: `Checkpoint reached: Act 2 Chapter 5 (Epilogue)`
- Gating flags:
  - `act2_ch5_briefed` unlocks `ToAct2Chapter5Overseer`
  - `act2_ch5_boss_defeated` unlocks `ToAct2Chapter5Epilogue`
- Mechanics taught:
  - Boss readability: aggro + AoE warning + suppression windows + shard payoff assist.
- Expected pickups count:
  - 1

## Boss Checklist (Ch5 Overseer)
- Aggro trigger runs once:
  - zone `Act2Chapter5BossAggroZone` -> `act2_ch5_boss_entered`
- AoE warning readability:
  - marker entity `Act2Ch5AoeWarnMarker`
  - warn toast contains `Impact in 2s...`
- Suppression switches:
  - `Act2Chapter5SuppressionSwitchZoneA` and `Act2Chapter5SuppressionSwitchZoneB`
  - set `act2_ch5_hazard_suppressed`
  - toast `Suppression active.`
- Shard payoffs:
  - shard A assist gated by `act2_ch3_reward_shard_a`
  - shard B heal gated by `act2_ch3_reward_shard_b`
- Defeat + resolution:
  - defeat sets `act2_ch5_boss_defeated`
  - epilogue completion sets `act2_act_complete`

## No-Hard-Lock Transition List
- `Act1_Chapter7_Aftermath` `ToAct2Chapter1Threshold` requires `act1_act1_complete`
- `Act2_Chapter1_Threshold` `ToAct2Chapter1HazardHall` requires `act2_ch1_briefed`
- `Act2_Chapter1_HazardHall` `ToAct2Chapter1SafeRoom` requires `act2_ch1_hazard_cleared`
- `Act2_Chapter1_SafeRoom` `ToAct2Chapter2SwitchRoom` requires `act2_chapter1_complete`
- `Act2_Chapter2_SwitchRoom` `ToAct2Chapter2HazardRun` requires `act2_ch2_switch_pulled`
- `Act2_Chapter2_HazardRun` `ToAct2Chapter2Sanctum` requires `act2_ch2_run_clear`
- `Act2_Chapter2_Sanctum` `ToAct2Chapter3Fork` requires `act2_chapter2_complete`
- `Act2_Chapter3_Fork` `ToAct2Chapter3RouteA` requires `act2_ch3_route_a_selected`
- `Act2_Chapter3_Fork` `ToAct2Chapter3RouteB` requires `act2_ch3_route_b_selected`
- `Act2_Chapter3_RouteA_Run` `ToAct2Chapter3RejoinFromA` requires `act2_ch3_route_a_clear`
- `Act2_Chapter3_RouteB_Safe` `ToAct2Chapter3RejoinFromB` requires `act2_ch3_route_b_clear`
- `Act2_Chapter3_Rejoin` `ToAct2Chapter4Hub` requires `act2_chapter3_complete`
- `Act2_Chapter4_Hub` `ToAct2Chapter4PathA` requires `act2_ch3_reward_shard_a`
- `Act2_Chapter4_Hub` `ToAct2Chapter4PathB` requires `act2_ch3_reward_shard_b`
- `Act2_Chapter4_PathA` `ToAct2Chapter4FinalFromA` requires `act2_ch4_path_clear`
- `Act2_Chapter4_PathB` `ToAct2Chapter4FinalFromB` requires `act2_ch4_path_clear`
- `Act2_Chapter4_Final` `ToAct2Chapter5Antechamber` requires `act2_chapter4_complete`
- `Act2_Chapter5_Antechamber` `ToAct2Chapter5Overseer` requires `act2_ch5_briefed`
- `Act2_Chapter5_Overseer` `ToAct2Chapter5Epilogue` requires `act2_ch5_boss_defeated`
