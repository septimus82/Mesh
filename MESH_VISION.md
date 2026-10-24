# Mesh Engine — Vision

Mesh is a flexible, visual-first 2D game creation engine. It aims for RPG Maker's accessibility without RPG Maker's restrictions.

## The experience we are building

1. Launch Mesh.
2. Choose a template or a blank project.
3. See an editable game world immediately.
4. Place and select objects directly on the map.
5. Right-click an object to add, remove and configure behaviours.
6. Create rooms and connect them visually.
7. Test gameplay immediately, and return to editing.
8. Save and load naturally.
9. Optionally let an AI perform the same validated operations.

A beginner never needs Python, JSON, the CLI, MCP or engine internals for ordinary tasks. Scripting and AI authoring stay available for those who want them. Templates give a starting point, not a ceiling.

The monster-catching game was a test project. It is not the product.

## Design principles

- **Human workflows are the acceptance standard.** A feature is done when a person can use it in the real window, not when its unit tests pass.
- **Nothing pretends.** Every visible control does what it says, or is visibly disabled with a reason.
- **One operation layer.** Manual edits, AI edits and the CLI call the same validated operations. No parallel implementations.
- **Direct manipulation by default.** Ordinary edits apply immediately with undo. Preview/accept is kept for AI-authored, bulk or destructive changes.
- **Fewer, cohesive systems.** Prefer one clear module over several narrowly specialised controllers.
- **Keep what works, cut what doesn't.** Effort already spent is not a reason to keep code; fashion is not a reason to rewrite it.

## Scope

**In scope now:** the minimum usable workflow below, the operation layer it needs, and removing what obstructs it.

**Not now:** new gameplay genres, art pipeline, a UI-framework switch (no demonstrated benefit yet; see `MESH_SALVAGE.md`), web export changes.

## Minimum usable workflow (milestone 1)

Create a project → open a map → place an NPC → give it dialogue → create another room → connect the rooms with a door → play → save → load → return to editing.

Acceptance: performed end to end through the real window by an automated OS-level input driver (`tooling/gui_driver.py`), with screenshots, on a freshly created project. Human usability testing is still required separately and is not claimed.
