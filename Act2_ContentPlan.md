# Act 2 Content Plan

## Chapter 1 - Threshold of Ash

### Premise
After the Act 1 aftermath, the path forward opens into an unstable corridor where the player learns to read and route around Hazard Zones.

### Objective chain
1. `quest_act2_ch1_briefing`: receive the threshold briefing and route instructions.
2. `quest_act2_ch1_hazard_clear`: cross the hazard hall, avoid sustained hazard contact, and reach the clear marker.
3. `quest_act2_ch1_complete`: secure the safe room, claim the checkpoint, and finish Chapter 1.

### New mechanic: Hazard Zone
- Warning delivery:
  - In-world warning sign at hazard hall entry.
  - Entry toast: `Hazard: stay out of the red zone.`
- Damage application:
  - Hazard lane uses `DamageOnTouch` entities with deterministic per-touch damage.
  - Hazard clear state is driven by zone triggers and flag sync hooks.
- Safety teaching:
  - Upper-lane bypass marker indicates the safe route around the center hazard strip.
  - One deterministic healing pickup appears after the hazard section.

## Chapter 2 - Switch Discipline

### Premise
The player learns to control hazard pressure by activating suppression at the right time.

### Objective chain
1. `quest_act2_ch2_switch_learned`: pull the hazard control switch.
2. `quest_act2_ch2_hazard_run_clear`: cross the run while suppression is active.
3. `quest_act2_ch2_complete`: secure the sanctum and continue.

### Mechanics focus
- Switch activation sets suppression state and enables safe crossing windows.
- Hazard run includes a safe alcove/retry lane and deterministic recovery pickups.

## Chapter 3 - Route Mastery

### Premise
The player chooses a route and learns tradeoffs between speed/risk and safety/length.

### Objective chain
1. `quest_act2_ch3_choose_route`: commit to Route A or Route B.
2. `quest_act2_ch3_route_a_clear` or `quest_act2_ch3_route_b_clear`: complete the selected route.
3. `quest_act2_ch3_complete`: rejoin and continue.

### Mechanics focus
- Route A reinforces suppression timing.
- Route B reinforces safer traversal and optional lore reward.
- Both routes reconverge into one deterministic progression state.

## Chapter 4 - Shard Consequence Hub

### Premise
The previous route reward shard determines which branch can be opened in the hub.

### Objective chain
1. `quest_act2_ch4_enter_hub`: enter the hub and use shard gating.
2. `quest_act2_ch4_path_clear`: clear Path A or Path B.
3. `quest_act2_ch4_complete`: secure the final chamber.

### Mechanics focus
- Shard-gated doors (`A`/`B`) with path-specific challenge flavor.
- Reconvergence at the final chamber with chapter-complete gating.

## Chapter 5 - Overseer Finale

### Premise
A boss finale that combines hazard pressure, suppression windows, and shard payoff assists.

### Objective chain
1. `quest_act2_ch5_ante_briefing`: prepare in the antechamber.
2. `quest_act2_ch5_overseer_defeated`: defeat the Overseer.
3. `quest_act2_ch5_complete`: resolve epilogue and complete Act 2.

### Mechanics focus
- Boss aggro trigger and AoE warning readability.
- Dual suppression switch windows in the arena.
- Shard A suppression assist and Shard B heal assist payoffs.

## RC Balance Targets (Ch1-Ch5)

| Chapter | Target Time-To-Clear (min) | Expected Deaths | Expected Pickups Consumed |
| --- | --- | --- | --- |
| Ch1 | 6 | 0-1 | 1 |
| Ch2 | 8 | 0-1 | 2 |
| Ch3 | 10 | 0-2 | 2 |
| Ch4 | 9 | 0-1 | 0 |
| Ch5 | 12 | 1-3 | 1 |
