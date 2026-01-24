"""Serialization helpers for scene data."""

from __future__ import annotations

import copy
from typing import Any, Dict

from .scene_loader import DEFAULT_ENTITY, DEFAULT_LAYERS, DEFAULT_SETTINGS


def compact_scene_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a compacted copy of the scene payload with default values removed.

    This function ensures that:
    - Top-level settings matching DEFAULT_SETTINGS are removed.
    - Layers matching DEFAULT_LAYERS are removed.
    - Entity fields matching DEFAULT_ENTITY are removed, except for identity fields.
    - Behaviour config entries are cleaned up.
    """
    compacted = copy.deepcopy(payload)

    # 1. Compact Settings
    if "settings" in compacted:
        settings = compacted["settings"]
        keys_to_remove = []
        for key, value in settings.items():
            # Check if key is in DEFAULT_SETTINGS and value matches
            # Note: We need to handle float comparison carefully if needed, but exact match is fine for now
            if key in DEFAULT_SETTINGS and value == DEFAULT_SETTINGS[key]:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del settings[key]

        if not settings:
            del compacted["settings"]

    # 2. Compact Layers
    # If layers match DEFAULT_LAYERS exactly, omit them.
    if "layers" in compacted:
        if compacted["layers"] == DEFAULT_LAYERS:
            del compacted["layers"]

    # 3. Compact Entities
    if "entities" in compacted:
        new_entities = []
        for entity in compacted["entities"]:
            new_entity = _compact_entity(entity)
            new_entities.append(new_entity)
        compacted["entities"] = new_entities

        if not compacted["entities"]:
            del compacted["entities"]

    return compacted


def _compact_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Compact a single entity dictionary."""
    compacted = copy.deepcopy(entity)

    # Identity fields that should be retained if present
    # "name", "tag", "behaviours", "spawn_id", "x", "y"

    identity_fields = {"name", "tag", "behaviours", "spawn_id", "x", "y"}

    keys_to_remove = []

    for key, value in compacted.items():
        # Skip identity fields (except behaviours, which we handle via default check)
        if key in identity_fields:
            continue

        if key in DEFAULT_ENTITY:
            default_val = DEFAULT_ENTITY[key]
            if value == default_val:
                # Special handling for behaviour_config?
                # If key is "behaviour_config", value is {}.
                # We will handle behaviour_config separately below.
                if key == "behaviour_config":
                    continue
                keys_to_remove.append(key)

    for key in keys_to_remove:
        del compacted[key]

    # Handle behaviour_config logic
    # "Keep behaviour_config entries even if empty ONLY when the behaviour is listed or when non-default params exist."
    if "behaviour_config" in compacted:
        b_config = compacted["behaviour_config"]
        behaviours = compacted.get("behaviours", [])

        # If behaviour_config is exactly default {}, we can remove it (if we didn't above).
        # But we skipped it above.

        # We need to clean up entries inside b_config
        config_keys_to_remove = []
        for b_name, b_params in b_config.items():
            # If params are empty
            if not b_params:
                # If behaviour is NOT listed, remove this config entry
                if b_name not in behaviours:
                    config_keys_to_remove.append(b_name)
            # If params are NOT empty, we keep it (non-default params exist)

        for k in config_keys_to_remove:
            del b_config[k]

        # Now, if b_config is empty, and default is empty, we can remove the field
        if not b_config and DEFAULT_ENTITY["behaviour_config"] == {}:
            del compacted["behaviour_config"]

    # Finally, check "behaviours" again.
    # If "behaviours" is [] and default is [], remove it?
    # Identity fields says "behaviours" is required identity field?
    # Requirement: "Ensure required identity fields are retained if present: 'name', 'tag', 'behaviours', 'spawn_id', 'x', 'y'"
    # So we should KEEP "behaviours" even if it is empty?
    # "Remove any field whose value equals DEFAULT_ENTITY[field]."
    # These two requirements conflict if behaviours is [].
    # "Ensure required identity fields are retained if present" takes precedence.
    # So we do NOT remove "behaviours" even if it is [].

    # Wait, if I look at my loop above:
    # if key in identity_fields: continue
    # identity_fields = {"name", "tag", "spawn_id", "x", "y"}
    # "behaviours" is NOT in my local identity_fields variable.
    # So it falls through to `if key in DEFAULT_ENTITY`.
    # If value is [], it gets removed.

    # I should add "behaviours" to identity_fields if the requirement says so.
    # Requirement: "Ensure required identity fields are retained if present: 'name', 'tag', 'behaviours', 'spawn_id', 'x', 'y'"
    # So yes, I should keep it.

    # But wait, if I keep "behaviours": [], it's just noise.
    # "Remove any field whose value equals DEFAULT_ENTITY[field]."
    # The requirement lists "behaviours" in the "retained if present" list.
    # So I will respect that.

    return compacted
