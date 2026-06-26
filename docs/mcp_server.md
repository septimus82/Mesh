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
| `list_prefabs` | List prefabs (`id` + `display_name`) from `assets/prefabs.json`. |
| `list_behaviours` | List every registered behaviour. |

The inspect tools key on whatever identifier the matching action op uses, so the
AI can build, list what's there, inspect one in detail, then refine it precisely:
`list_entities`/`inspect_entity` on the entity `name` (matching `delete_entity`,
`set_behaviour_params`); `list_quests`/`inspect_quest` on the quest `id` (matching
`edit_quest`, `update_quest_definition`, `delete_quest_definition`); and
`list_lights` on the light `index` (matching `update_light`, `delete_light`).
That closes the **build → inspect → refine** loop for entities, quests, and
lighting.

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
