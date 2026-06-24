"""Mesh MCP server package.

Exposes the engine's existing AI operations, read surface, and context as
Model Context Protocol tools/resources so any MCP-capable model can connect,
inspect engine state, build content, and have its writes validated.

The tool *logic* lives in :mod:`engine.mcp_server.tools` as plain functions
with no MCP dependency, so it is fully unit-testable without a live client.
The thin FastMCP wiring and stdio entry point live in
:mod:`engine.mcp_server.server`, which imports the optional ``mcp`` SDK behind
an import guard (the engine never hard-requires ``mcp``).
"""

from engine.mcp_server import tools

__all__ = ["tools"]
