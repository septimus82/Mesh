# Town Schedule 01

A vertical slice that stress-tests NpcSchedule time-based routines,
TimeOfDayGate access control, and quest progression tied to scheduled
interactions.

## Scenario

A vendor NPC follows a daily schedule:
- **Morning (6–12)**: at stall, vendor open
- **Afternoon (12–20)**: at plaza, vendor closed
- **Night (20–6)**: at home, vendor closed

A gate opens only at night, revealing a secret trigger.
Quest: "Enter town → meet the vendor in the morning → find the secret at night."

## Entities

| Entity | Prefab | Behaviours | Purpose |
|--------|--------|------------|---------|
| Player | `player` | — | Player avatar |
| TownEntryTrigger | `town_entry_trigger` | TriggerVolume | Emits `town_entered` |
| VendorNpc | `town_vendor_npc` | NpcSchedule, Interactable | Schedule-driven vendor |
| NightGate | `town_night_gate` | TimeOfDayGate | Visible only at night, emits `gate_opened` |
| SecretTrigger | `town_secret_trigger` | TriggerVolume | Emits `secret_found` |
| TownInit | `town_controller` | ActionListRunner | Sets `town.entered` on entry |
| VendorOpenCtrl | `town_controller` | ActionListRunner | Sets `vendor.open` on `vendor_opened` |
| VendorCloseCtrl | `town_controller` | ActionListRunner | Clears `vendor.open` on `vendor_closed` |
| VendorInteractGate | `town_controller` | ActionListRunner | Gates interaction: require `vendor.open` → sets `vendor.met`, emits `vendor_interacted` |
| GateOpenCtrl | `town_controller` | ActionListRunner | Sets `gate.open` on `gate_opened` |
| SecretFoundCtrl | `town_controller` | ActionListRunner | Require `gate.open` → sets `secret.found` |

## Event Flow

| Trigger | Event | Effect |
|---------|-------|--------|
| Player enters town | `town_entered` | Sets `town.entered` |
| Clock reaches morning | `vendor_opened` (NpcSchedule enter_event) | Sets `vendor.open` |
| Clock leaves morning | `vendor_closed` (NpcSchedule enter_event) | Clears `vendor.open` |
| Player interacts while open | `vendor_interact_attempt` → `vendor_interacted` | Sets `vendor.met` |
| Clock reaches night | `gate_opened` (TimeOfDayGate open_event) | Sets `gate.open` |
| Player steps on secret (night) | `secret_found` | Sets `secret.found` |

## Flags

| Flag | Meaning |
|------|---------|
| `town.entered` | Player has entered the town |
| `vendor.open` | Vendor is currently open for interaction |
| `vendor.met` | Player has interacted with the vendor |
| `gate.open` | Night gate is currently open |
| `secret.found` | Secret has been discovered |

## NPC Schedule Configuration

| Slot | Hours | Mode | Position | enter_event |
|------|-------|------|----------|-------------|
| Morning | 6–12 | stand | (200, 256) | `vendor_opened` |
| Afternoon | 12–20 | stand | (400, 256) | `vendor_closed` |
| Night | 20–6 | stand | (100, 256) | — |

## TimeOfDayGate (Night Gate)

| Config | Value |
|--------|-------|
| `start_hour` | 20 |
| `end_hour` | 6 |
| `invert` | false |
| `open_event` | `gate_opened` |

Active when hour ≥ 20 or hour < 6 (night window).

## Quest

Quest `town_schedule_01` has three stages:

| Stage | Complete On | Emits |
|-------|-------------|-------|
| `step0` | `town_entered` | — |
| `step1` | `vendor_interacted` | — |
| `step2` | `secret_found` | `quest_town_complete` |

## Save / Restore

All components support save/restore:
- **MockDayNight clock** → `{hour}` (test mock; real game uses `DayNightCycle.hour`)
- **GameState flags** → all `town.*`, `vendor.*`, `gate.*`, `secret.*` flags
- **GameplayEventBus** → pending events
- **ActionListRunner** → per-controller state

NpcSchedule and TimeOfDayGate re-derive their active state from the
clock on the next `update()` call after restore, so saving the clock
hour is sufficient for deterministic restoration.
