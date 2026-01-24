from __future__ import annotations

# Thin compatibility layer: legacy CLI implementation lives in `mesh_cli.legacy_impl`.
from .legacy_impl import create_parser, main


__all__ = ["create_parser", "main"]
