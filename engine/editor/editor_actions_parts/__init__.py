"""Decomposed editor action buckets.

Each sub-module owns a cohesive group of action handlers.
The parent :mod:`engine.editor.editor_actions_impl` re-exports everything
so that ``globals()``-based callable lookup continues to work.
"""
