"""FastMCP wiring + stdio entry point for the Mesh MCP server.

The ``mcp`` SDK is an *optional* dependency: this module imports it behind a
guard so the engine never hard-requires it. The actual tool logic lives in
:mod:`engine.mcp_server.tools` (plain, dependency-free, unit-tested). This file
only wires those functions into a FastMCP server and runs it over stdio.

Run it with::

    python -m engine.mcp_server.server

and point any MCP client (Claude Desktop/Code/Cursor) at that command.
"""

from __future__ import annotations

from typing import Any

from engine.mcp_server import tools

HAS_MCP = False
try:  # pragma: no cover - exercised only when the optional SDK is installed
    from mcp.server.fastmcp import FastMCP

    HAS_MCP = True
except ImportError:  # pragma: no cover - the import-guard path
    FastMCP = None  # type: ignore[assignment, misc]


SERVER_NAME = "mesh"


def build_server() -> Any:
    """Construct the FastMCP server with all Mesh tools and resources.

    Raises :class:`RuntimeError` if the optional ``mcp`` SDK is not installed.
    """
    if not HAS_MCP or FastMCP is None:
        raise RuntimeError(
            "The 'mcp' SDK is not installed. Install it with: pip install mcp"
        )

    server = FastMCP(SERVER_NAME)

    # Read tools (the AI's eyes).
    server.tool()(tools.list_scenes)
    server.tool()(tools.read_scene)
    server.tool()(tools.list_prefabs)
    server.tool()(tools.list_behaviours)

    # Action tools (the AI's hands).
    server.tool()(tools.create_scene)
    server.tool()(tools.add_entity_from_prefab)

    # Safety.
    server.tool()(tools.validate_scene)

    # Context resource: instant expertise on connect.
    @server.resource("mesh://overview")
    def overview() -> str:
        return tools.engine_overview_json()

    return server


def main() -> None:
    """Build the server and serve it over stdio."""
    build_server().run()


if __name__ == "__main__":  # pragma: no cover - manual launch path
    main()
