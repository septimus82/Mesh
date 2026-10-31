# Mesh MCP server

The Mesh MCP server exposes the engine to any [Model Context Protocol](https://modelcontextprotocol.io)
client (Claude Desktop, Claude Code, Cursor, …). Once connected, the AI can
inspect engine state, build content, and have its writes validated — the
foundation for "describe a scene and the AI builds it, you refine it in the
editor."

This is **MVP slice-1**: a minimal, connectable server proving the round-trip
(connect → read state → build → validate). The full op surface lands in later
slices.

## Install

The `mcp` SDK is an *optional* dependency — the engine never requires it:

```bash
pip install -e .[mcp]
```

Both `mcp` 1.x and 2.x work (2.x renamed `FastMCP` to `MCPServer`; the server takes either).

## Quickstart

```bash
pip install -e .[mcp]
mesh mcp install
```

Fully restart Claude Desktop after the install command so it reloads the MCP
configuration.

`mesh mcp install` writes the Claude Desktop config for the current project. It
backs up any existing config to `claude_desktop_config.json.bak`, preserves other
servers, and overwrites only the `mcpServers.mesh` entry.

## Editing a project together with Mesh Studio

These tools use **the same operations Mesh Studio uses** (`engine/authoring.py` over
`engine/project_ops.py`), so a change made by an AI, by a person in the Studio, or with the
`mesh author` command is validated the same way and produces the same documents. They work the
same for any MCP client.

| Tool | Purpose |
| --- | --- |
| `authoring_operations` | Every operation (`place_prefab`, `rename_entity`, `set_dialogue_text`, `add_line`, `set_choice`, `set_show_when`, `paint_tiles`, `add_room`, `link_rooms`, …) with its settings and what it does. Generated from the engine, so it is never out of date. |
| `read_project(root)` | Every room with its objects and map. If Mesh Studio has the project open, this is what the person sees now (unsaved edits included), with a `revision`. |
| `propose_changes(changes, title, base_revision, root)` | Send a batch to the Mesh Studio that has the project open. The person reviews it (top bar **AI**) and accepts or rejects it. Invalid batches are refused at once, with the change and the reason. |
| `proposal_status(proposal_id, root)` | `pending`, `accepted` (with the ids it created), `rejected` or `conflict`. |
| `withdraw_proposal(proposal_id, root)` | Take back a proposal that is still waiting. |
| `apply_changes(changes, root, dry_run)` | Change the project files (all or nothing), or preview with `dry_run`. **If Mesh Studio has the project open, the batch is proposed there instead:** files are never written behind the person's back. |

**When it can't be told whether Studio has the project open (F1):** the project has a session record (`.mesh/live_session.json`) that can't be read or verified. For example, Studio didn't answer, timed out, or answered for another session or folder. In that case these tools write and create nothing, and they don't offer the files as current. They answer `reason: "studio_session_uncertain"`, with `problem` (why), `discovery` (the record's path) and what to do:

- **Studio is open:** make sure it's responding, then try again.
- **Studio isn't running:** open the project in Mesh Studio once, which replaces its leftover record, or delete the record. Then try again.

Only a project with no session record at all is changed directly. `apply_changes` checks again just before it writes. A proposal that fails is never written to the files instead.

A batch is a list of changes:

```json
[
  {"op": "place_prefab", "prefab": "person", "x": 448, "y": 224},
  {"op": "rename_entity", "entity_id": "@0", "name": "Sexton"},
  {"op": "set_dialogue_text", "entity_id": "Sexton", "text": "Who goes there?"},
  {"op": "set_show_when", "entity_id": "Sexton", "require": "lantern_lit", "forbid": ""}
]
```

- **`room`**: each change can name a room (room keys come from `read_project`); the default is the current room.
- **`entity_id`**: takes an object's id or its unique name.
- **`@N`**: the id of the object made by change `N` of the same batch, counting from 0.
- **All or nothing:** a batch applies completely or not at all, and is one Undo step in the Studio.

**Revisions and conflicts.** Pass the `revision` you read as `base_revision`:
- If the person changed other things since you read, both sets of changes survive (they paint the floor while you add an NPC).
- If you both changed the same property, Studio reports a conflict, applies nothing, and the person's version stands. Read again and propose anew.

**No MCP?** `mesh author ops | read | apply | propose | status` does the same from a command line, with JSON in and out.

**Older tools.** `apply_ops` still takes its operation types. On a Mesh Studio project, `add_entity_from_prefab`, `delete_entity`, `set_behaviour_params` and `paint_tiles` now go through this same validated path (and become a proposal while Studio is open). The `live_*` tools serve the legacy editor. Against Mesh Studio, `live_accept_proposal` is refused, because only the person accepts.

## Other MCP Clients

The server speaks MCP over **stdio**, so any MCP client can launch it directly.
For clients other than Claude Desktop, print the config snippet for this project:

```bash
mesh mcp config
```

That prints JSON in this shape:

```json
{
  "mcpServers": {
    "mesh": {
      "command": "C:/path/to/python",
      "args": ["-m", "engine.mcp_server.server"],
      "cwd": "C:/path/to/Mesh"
    }
  }
}
```

Run `mesh mcp config` from the project root so the generated `cwd` lets the
read/action tools resolve `scenes/`, `assets/prefabs.json`, etc. relative to the
right place.

## Tools

Read (the AI's eyes):

| Tool | Purpose |
| --- | --- |
| `list_scenes` | List scene files under `scenes/`. |
| `read_scene` | Parse a scene + entity-count summary. |
| `list_entities` | List a scene's entities as compact summaries (name, tag, pos, behaviours). |
| `inspect_entity` | Return one entity in full detail (summary + behaviour_config + raw entity). |
| `list_lights` | List a scene's lights with their `index` and key fields. |
| `list_quests` | List quest definitions (`id`, title, stage count) from `assets/data/quests.json`. |
| `inspect_quest` | Return one quest in full detail (stages + raw quest). |
| `read_dialogue` | Return an entity's dialogue block (keyed on entity `name`). |
| `read_world` | Return the world graph: `start_scene`/`start_spawn`, scenes, links. |
| `read_tilemap` | Return a scene's tilemap: layers (name/z), per-layer tile arrays, collision layer. |
| `list_prefabs` | List prefabs (`id` + `display_name`) from `assets/prefabs.json`. |
| `list_behaviours` | List every registered behaviour. |

The inspect tools key on whatever identifier the matching action op uses, so the
AI can build, list what's there, inspect one in detail, then refine it precisely:
`list_entities`/`inspect_entity` on the entity `name` (matching `delete_entity`,
`set_behaviour_params`); `list_quests`/`inspect_quest` on the quest `id` (matching
`edit_quest`, `update_quest_definition`, `delete_quest_definition`); and
`list_lights` on the light `index` (matching `update_light`, `delete_light`).
`read_dialogue` keys on the entity `name` (matching `edit_dialogue`), `read_world`
on the `world_path` (matching `add_world_scene`/`link_world_scenes`/
`set_world_start`), and `read_tilemap` on the `scene_path` (matching
`paint_tiles`). The **build → inspect → refine** loop is now closed
symmetrically for entities, quests, lights, dialogue, world, and tilemaps — every
write surface has a structured read counterpart.

Action (the AI's hands), wrapping `engine.ai_ops.AIOps`:

| Tool | Purpose |
| --- | --- |
| `create_scene` | Create a scene from a template. |
| `add_entity_from_prefab` | Place a prefab instance into a scene. |
| `list_op_types` | List every batch operation with its required/optional fields. |
| `apply_ops` | Run a batch of operations (the full 23-op surface) in one call, then validate. |

`apply_ops` is the cost-and-capability lever: instead of one chatty tool call
per change, the model sends the whole batch (e.g. create a scene + place several
entities + set behaviours) in a single request. It returns a per-operation
result list (each echoing its `type` and `ok`/`message`) plus a `validation`
verdict, so the model gets immediate, structured feedback on whether the batch
left the content valid — and can self-correct in one more shot. Per-op failures
are isolated: one bad operation does not abort the rest. Call `list_op_types`
(or read the `mesh://overview` resource) to see the available operations and
their field shapes.

Safety:

| Tool | Purpose |
| --- | --- |
| `validate_scene` | Validate a scene (or the whole world) and return a structured verdict. |
| `playability_check` | Advisory self-verify: does the scene *feel* playable? |

`playability_check(scene_path)` is the advisory self-verify tool the AI can call
after building, to confirm a scene is actually playable rather than just valid.
It resolves prefab references (so both AI-placed inline entities and
`prefab_id`-referenced ones are seen) and returns WARNINGS, never hard failures —
a valid-but-incomplete scene still saves. It checks for: a tagged `"player"`
with `CameraFollow` (camera follows), and at least one enemy (`EnemyAI` or
`ChaseTarget`) whose `target_tag` matches the player's tag (something can chase
the player); it also advises when the only chaser uses `ChaseTarget` in a
tilemap-less scene (no nav grid, so the chase is inert — prefer `EnemyAI`).
Returns `{ok, scene_path, warnings, summary{has_player, player_has_camera,
enemies_targeting_player}}` where `ok` is simply "no warnings" (not an error).

## Resource

`mesh://overview` — a compact briefing (scenes, prefabs, behaviours, and the
operation surface) so a freshly-connected model is immediately fluent in both
what the engine contains and what it can do.

It also includes two keys that brief the model on *how* to assemble a playable
scene, not just what exists:

- `scene_templates` — the list of template names `create_scene` accepts,
  enumerated live from the scaffold registry (`engine/tooling/scaffold.py`) so it
  can't drift from what the tool supports.
- `playable_scene_recipe` — a short, ordered recipe (create a scene, add the
  `player` prefab which already carries `CameraFollow` + tag `"player"`, add at
  least one enemy such as `chaser_enemy`, then validate) using only existing
  tools and prefabs, so the model knows the playable pattern at connect time.

## Architecture

The tool **logic** lives in [`engine/mcp_server/tools.py`](../engine/mcp_server/tools.py)
as plain, dependency-free functions returning JSON-serialisable data — fully
unit-tested in [`tests/test_mcp_server_tools_contract.py`](../tests/test_mcp_server_tools_contract.py)
without a live client or the `mcp` SDK. The thin FastMCP wiring and stdio entry
point live in [`engine/mcp_server/server.py`](../engine/mcp_server/server.py),
which imports `mcp` behind a guard. The tools reuse the engine's existing AI
operations, loaders, and validators — the server is a *wire*, not a rewrite.
