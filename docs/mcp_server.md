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

## Run

```bash
python -m engine.mcp_server.server
```

The server speaks MCP over **stdio**, so an MCP client launches that command
directly. Example client config (Claude Desktop `mcpServers` entry):

```json
{
  "mcpServers": {
    "mesh": {
      "command": "python",
      "args": ["-m", "engine.mcp_server.server"],
      "cwd": "C:/path/to/Mesh"
    }
  }
}
```

Run it from the project root (or set `cwd`) so the read/action tools resolve
`scenes/`, `assets/prefabs.json`, etc. relative to the right place.

## Tools

Read (the AI's eyes):

| Tool | Purpose |
| --- | --- |
| `list_scenes` | List scene files under `scenes/`. |
| `read_scene` | Parse a scene + entity-count summary. |
| `list_prefabs` | List prefabs (`id` + `display_name`) from `assets/prefabs.json`. |
| `list_behaviours` | List every registered behaviour. |

Action (the AI's hands), wrapping `engine.ai_ops.AIOps`:

| Tool | Purpose |
| --- | --- |
| `create_scene` | Create a scene from a template. |
| `add_entity_from_prefab` | Place a prefab instance into a scene. |

Safety:

| Tool | Purpose |
| --- | --- |
| `validate_scene` | Validate a scene (or the whole world) and return a structured verdict. |

## Resource

`mesh://overview` — a compact briefing (scenes, prefabs, behaviours) so a
freshly-connected model is immediately fluent in what the engine contains.

## Architecture

The tool **logic** lives in [`engine/mcp_server/tools.py`](../engine/mcp_server/tools.py)
as plain, dependency-free functions returning JSON-serialisable data — fully
unit-tested in [`tests/test_mcp_server_tools_contract.py`](../tests/test_mcp_server_tools_contract.py)
without a live client or the `mcp` SDK. The thin FastMCP wiring and stdio entry
point live in [`engine/mcp_server/server.py`](../engine/mcp_server/server.py),
which imports `mcp` behind a guard. The tools reuse the engine's existing AI
operations, loaders, and validators — the server is a *wire*, not a rewrite.
