"""Clipboard utilities for the tooling module.

This module is a shim re-exporting from the canonical clipboard module.
All clipboard functionality is implemented in engine.tooling_runtime.clipboard.

This shim exists for backwards compatibility with any code that may have
imported from engine.tooling.clipboard.
"""
from __future__ import annotations

from engine.tooling_runtime.clipboard import try_copy_to_clipboard

__all__ = ["try_copy_to_clipboard"]
