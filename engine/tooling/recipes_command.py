import argparse

RECIPES = {
    "ai_region_creation": {
        "title": "AI-Assisted Region Creation",
        "steps": [
            "1. Export Schema:  mesh plan schema --ai-out docs/plan_ai_schema.json",
            "2. Generate Plan:  (Use external AI to generate plan.json based on schema)",
            "3. Lint Plan:      mesh plan lint-ai plan.json",
            "4. Test Plan:      mesh plan test-ai plan.json",
            "5. Apply Plan:     mesh apply-plan --ai-safe plan.json"
        ]
    },
    "new_scene_flow": {
        "title": "Create New Scene & Polish",
        "steps": [
            "1. Create scene:   mesh new-scene my_scene --template basic",
            "2. Edit scene:     (Open scenes/my_scene.json in editor)",
            "3. Validate:       mesh validate scenes/my_scene.json",
            "4. Polish:         mesh polish scenes/my_scene.json"
        ]
    },
    "add_pack": {
        "title": "Add New Content Pack",
        "steps": [
            "1. Init pack:      mesh init-content-pack my_mod --type mod --wip",
            "2. Add assets:     (Copy files to my_mod/assets/)",
            "3. Lock:           mesh lock-packs",
            "4. Verify:         mesh validate-packs"
        ]
    },
    "demo_build": {
        "title": "Create Demo Build",
        "steps": [
            "1. Check:          mesh release-check worlds/main_world.json --profile demo",
            "2. Build:          mesh build-demo --out dist/demo_v1"
        ]
    },
    "release_build": {
        "title": "Create Release Build",
        "steps": [
            "1. Audit:          mesh audit-content worlds/main_world.json --max-unused-assets 0",
            "2. Check:          mesh release-check worlds/main_world.json --profile release",
            "3. Lock:           mesh lock-packs",
            "4. Package:        (Run external packaging tool)"
        ]
    },
    "update_snapshots": {
        "title": "Update CLI/Schema Snapshots",
        "steps": [
            "1. CLI Snapshot:   mesh cli-snapshot --out docs/generated/cli_snapshot.json",
            "2. Plan Schema:    mesh plan schema --out docs/generated/plan_schema.json",
            "3. Verify:         mesh check --full"
        ]
    },
    "encounter_check": {
        "title": "Check Encounter Balance",
        "steps": [
            "1. Run CI Check:   mesh run-preset encounter-ci",
            "2. Drift Check:    mesh run-preset encounter-ci-diff",
            "3. Full Sweep:     mesh run-preset encounter-balance-sweep",
            "4. View Report:    (Open .mesh/reports/encounter_report.json)"
        ]
    },
    "v0_5_demo": {
        "title": "Build v0.5 Demo Region (Zero-Hand-Edit)",
        "steps": [
            "1. Create Region:  mesh wizard region --name demo_region --template hub-interior-dungeon",
            "2. Wire Hub:       mesh edit-scene scenes/demo_region_hub.json --add-transition demo_region_interior --at 10,10",
            "3. Wire Interior:  mesh edit-scene scenes/demo_region_interior.json --add-transition demo_region_dungeon --at 5,5",
            "4. Add Quest:      mesh new-quest demo_quest --title 'Explore the Dungeon' --objective 'Enter the dungeon'",
            "5. Add NPC:        mesh place-npc --scene scenes/demo_region_hub.json --role vendor --name 'Merchant'",
            "6. Add Puzzle:     mesh add-puzzle --scene scenes/demo_region_dungeon.json --type switch-door",
            "7. Auto-Wire:      mesh auto-wire-transitions worlds/demo_region.json --apply",
            "8. Polish:         mesh polish worlds/demo_region.json",
            "9. Validate:       mesh validate-all worlds/demo_region.json --strict"
        ]
    }
}

def recipes_command(args: argparse.Namespace) -> None:
    """Show curated workflow recipes."""
    print("\n=== Mesh Workflow Recipes ===\n")

    for key, recipe in RECIPES.items():
        print(f"[{recipe['title']}]")
        for step in recipe['steps']:
            print(f"  {step}")
        print("")

    print("Run 'mesh help' for full command list.")
