import json

from engine.tooling.preset_policy import get_preset_policy_snapshot


def test_preset_policy_snapshot_env_is_present_and_deterministic():
    snap1 = get_preset_policy_snapshot()
    snap2 = get_preset_policy_snapshot()

    assert snap1["version"] == 1
    assert "env" in snap1
    assert snap1["env"] == {
        "key_regex": "^[A-Z][A-Z0-9_]{0,63}$",
        "max_key_len": 64,
        "max_value_len": 128,
        "banned_substrings": [".."],
        "banned_chars": ["\\n", "\\r", "\\0", "/", "\\"],
    }

    assert json.dumps(snap1, sort_keys=True) == json.dumps(snap2, sort_keys=True)

