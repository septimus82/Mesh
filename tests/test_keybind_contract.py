import json
from pathlib import Path


def test_core_keybinds_have_no_conflicts() -> None:
    """Lock the keybind contract for core gameplay/UI controls.

    This test intentionally ignores editor-only bindings, which may reuse
    gameplay keys depending on mode.
    """

    config_path = Path("config.json")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)

    bindings = raw.get("input_bindings")
    assert isinstance(bindings, dict)

    bare_key_actions = [
        # movement
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        # interact/attack
        "interact",
        "attack",
        # UI overlays
        "toggle_help",
        "toggle_variant_picker",
        "toggle_inspector",
        "toggle_dev_browser",
        "show_inventory",
        # save/load
        "quick_save",
        "quick_load",
        "quickload_last_save",
    ]
    routed_modifier_actions = {"save_game"}

    # Explicitly allowed overlaps (key name, action_a, action_b) as sorted tuples.
    allowed_overlaps: set[tuple[str, str, str]] = set()

    key_to_actions: dict[str, list[str]] = {}

    for action in bare_key_actions:
        keys = bindings.get(action)
        assert isinstance(keys, list) and keys, f"Missing or empty binding for '{action}'"

        seen: set[str] = set()
        for key in keys:
            assert isinstance(key, str) and key.strip(), f"Invalid key name for '{action}': {key!r}"
            name = key.strip().upper()
            if name in seen:
                raise AssertionError(f"Duplicate key '{name}' within action '{action}'")
            seen.add(name)
            key_to_actions.setdefault(name, []).append(action)

    conflicts: list[str] = []
    for key_name in sorted(key_to_actions.keys()):
        actions = sorted(set(key_to_actions[key_name]))
        if len(actions) <= 1:
            continue
        allowed = True
        for i, a in enumerate(actions):
            for b in actions[i + 1 :]:
                if (key_name, *sorted((a, b))) not in allowed_overlaps:
                    allowed = False
        if not allowed:
            conflicts.append(f"{key_name}: {actions}")

    assert not conflicts, "Keybind conflicts in core controls:\n" + "\n".join(conflicts)

    for action in routed_modifier_actions:
        keys = bindings.get(action)
        assert keys in (None, []), f"Routed modifier action '{action}' must not claim a bare-key binding"
