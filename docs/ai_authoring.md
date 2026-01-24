# AI Authoring Guide

This guide explains how to use the Mesh Engine's AI Authoring Kit to generate and apply content plans using external AI agents.

## Workflow Overview

1.  **Generate Schema**: Export the simplified AI Plan Schema.
2.  **Export Context**: Export a compact snapshot of the scene(s) for the AI.
3.  **Generate Plan**: Use an LLM (like GPT-4 or Claude) to generate a plan JSON based on the schema.
4.  **Lint**: Validate the plan against strict AI safety rules.
5.  **Test**: Run the plan in a sandbox environment to verify correctness.
6.  **Apply**: Apply the plan to the workspace.

## 1. Generate Schema

Export the schema to a file that can be provided to an AI agent.

```bash
mesh plan schema --ai-out docs/plan_ai_schema.json
```

The schema defines the allowed actions (`create_scene`, `add_npc`, etc.) and their arguments.

## 2. Export Context

Before asking an AI to modify a scene, it helps to provide the current state of that scene. The `ai-export-context` command generates a simplified, token-efficient JSON summary.

```bash
mesh ai-export-context scenes/hub_town.json --out context.json
```

This file contains:
*   Scene dimensions and properties.
*   List of NPCs (IDs, names, positions).
*   List of transitions (targets, positions).
*   List of quest triggers.

**Example Prompt for AI:**

> Here is the current state of the scene: [paste context.json].
> Please generate a plan to add a new NPC named "Guard" near the east exit.

## 3. Generate Plan

You can use the `ai-generate-plan` command to create a template skeleton.

```bash
mesh ai-generate-plan --out my_plan.json "Create a dungeon with a boss"
```

This creates a file with TODOs. You can then ask an AI to fill it in, or provide the schema to the AI and ask it to generate the full JSON from scratch.

**Example Prompt for AI:**

> I have a game engine that accepts JSON plans. Here is the schema: [paste schema].
> Please generate a plan to create a new scene called "scenes/dungeon_01.json" using the "dungeon" template, and add a "goblin_king" NPC at (10, 10).

## 4. Lint Plan

Run strict validation on the generated plan.

```bash
mesh plan lint-ai my_plan.json
```

This checks for:
*   Disallowed actions (e.g., file deletion).
*   Unsafe paths (e.g., `../`).
*   Missing required arguments.

## 5. Test Plan

Run the plan in a sandbox without modifying your actual workspace.

```bash
mesh plan test-ai my_plan.json
```

This will:
1.  Create a temporary sandbox.
2.  Apply the plan.
3.  Infer and run tests (e.g., check if the scene loads, if the NPC is present).

## 6. Apply Plan

Once verified, apply the plan to your workspace. Use `--ai-safe` to re-run checks automatically.

```bash
mesh apply-plan --ai-safe my_plan.json
```

## Allowed Actions

*   `create_scene`: Create a new scene from a template.
*   `add_npc`: Add an NPC to a scene.
*   `add_transition`: Add a transition trigger.
*   `add_puzzle`: Add a puzzle element.
*   `add_quest`: Define a new quest.

See `docs/plan_ai_schema.json` for details.

## Examples

### Example 1: Add a Vendor to a Hub

```json
{
  "wizard": "ai-generated",
  "version": 1,
  "inputs": {
    "prompt": "Add a vendor to the hub"
  },
  "actions": [
    {
      "type": "add_npc",
      "args": {
        "scene": "scenes/hub_town.json",
        "npc_id": "market_vendor",
        "prefab_id": "npc_merchant",
        "x": 15,
        "y": 20
      },
      "description": "Add the market vendor"
    }
  ]
}
```

### Example 2: Add a Puzzle and Transition to a Dungeon

```json
{
  "wizard": "ai-generated",
  "version": 1,
  "inputs": {
    "prompt": "Add puzzle and transition to dungeon"
  },
  "actions": [
    {
      "type": "add_puzzle",
      "args": {
        "scene": "scenes/dungeon_entrance.json",
        "puzzle_type": "lever_gate",
        "x": 40,
        "y": 10
      },
      "description": "Add a lever puzzle to open the gate"
    },
    {
      "type": "add_transition",
      "args": {
        "scene": "scenes/dungeon_entrance.json",
        "target_scene": "scenes/dungeon_floor1.json",
        "x": 42,
        "y": 10,
        "width": 2,
        "height": 2
      },
      "description": "Add transition to the next floor"
    }
  ]
}
```
